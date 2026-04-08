"""
Runtime-configurable agent prompt store.

Storage layout in config/agent_prompts.json:
{
  "response_generator": {
    "active": "at_risk",
    "profiles": {
      "default":        "..template..",
      "at_risk":        "..template..",
      "parent_friendly":"..template.."
    }
  },
  "classification": {
    "active": "strict",
    "profiles": {
      "strict": "..template.."
    }
  }
}

If a key has no entry (or active==null) the hardcoded default in
prompts/templates.py is used — nothing breaks.

Override templates use $placeholder syntax (Python string.Template).
This avoids collision with JSON { } characters inside prompt bodies.

Available placeholders per key:
  classification      $domain_description  $entity_plural  $field_names  $question
  query_planner       $domain_description  $entity_plural  $entity_name  $field_descriptions  $example_queries
  response_generator  $domain_description  $question  $result
  rag                 $domain_description  $context  $question
  chat                $domain_description  $entity_plural  $field_names
"""

import json
from pathlib import Path
from string import Template
from typing import Dict, List, Optional

PROMPTS_FILE = Path(__file__).parent / "agent_prompts.json"

VALID_KEYS: frozenset = frozenset(
    {"classification", "query_planner", "response_generator", "rag", "chat"}
)

PLACEHOLDERS: Dict[str, List[str]] = {
    "classification":     ["domain_description", "entity_plural", "field_names", "question"],
    "query_planner":      ["domain_description", "entity_plural", "entity_name", "field_descriptions", "example_queries"],
    "response_generator": ["domain_description", "question", "result"],
    "rag":                ["domain_description", "context", "question", "intent"],
    "chat":               ["domain_description", "entity_plural", "field_names"],
}

# RAG intents that can each have their own named profile under the "rag" key
RAG_INTENTS = ("summarize", "compare", "list", "explain", "lookup", "general")


class PromptStore:
    """
    Persistent store for admin-configurable agent prompt profiles.

    Each prompt key (e.g. 'response_generator') can hold multiple named
    profiles. Only the 'active' profile is used at runtime; switching profiles
    is instant and requires no restart.
    """

    def __init__(self) -> None:
        # { key: { "active": str|None, "profiles": { name: template } } }
        self._data: Dict[str, dict] = {}
        self._load()

    # ── persistence ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not PROMPTS_FILE.exists():
            return
        try:
            raw = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        # Migrate old flat format {"key": "template string"} to new profile format
        for key, value in raw.items():
            if isinstance(value, str):
                raw[key] = {"active": "default", "profiles": {"default": value}}
        self._data = raw

    def _save(self) -> None:
        PROMPTS_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _key_data(self, key: str) -> dict:
        """Return the mutable dict for *key*, creating it if absent."""
        if key not in self._data:
            self._data[key] = {"active": None, "profiles": {}}
        return self._data[key]

    # ── profile management ─────────────────────────────────────────────────────

    def set_profile(self, key: str, name: str, template: str) -> None:
        """
        Create or update a named profile for *key*.
        If this is the first profile for the key, it is automatically activated.
        """
        self._validate_key(key)
        entry = self._key_data(key)
        entry["profiles"][name] = template
        if entry["active"] is None:
            entry["active"] = name
        self._save()

    def activate_profile(self, key: str, name: str) -> None:
        """Switch the active profile for *key* to *name*."""
        self._validate_key(key)
        entry = self._key_data(key)
        if name not in entry["profiles"]:
            raise ValueError(
                f"Profile '{name}' not found for key '{key}'. "
                f"Available: {', '.join(entry['profiles']) or 'none'}"
            )
        entry["active"] = name
        self._save()

    def delete_profile(self, key: str, name: str) -> bool:
        """
        Delete a named profile. If it was active, active is set to None
        (reverts to hardcoded default). Returns True if profile existed.
        """
        self._validate_key(key)
        entry = self._key_data(key)
        if name not in entry["profiles"]:
            return False
        del entry["profiles"][name]
        if entry["active"] == name:
            # Fall back to another profile if one exists, else use default
            remaining = list(entry["profiles"])
            entry["active"] = remaining[0] if remaining else None
        if not entry["profiles"]:
            del self._data[key]
        self._save()
        return True

    def list_profiles(self, key: str) -> dict:
        """Return profile info for *key*: active name + all profile names."""
        self._validate_key(key)
        entry = self._data.get(key, {"active": None, "profiles": {}})
        return {
            "active": entry.get("active"),
            "profiles": list(entry.get("profiles", {}).keys()),
        }

    def list_all(self) -> dict:
        """Return profile info for every valid key."""
        return {k: self.list_profiles(k) for k in sorted(VALID_KEYS)}

    # ── runtime rendering ──────────────────────────────────────────────────────

    def get_active_template(self, key: str) -> Optional[str]:
        """Return the raw template string for the active profile, or None."""
        entry = self._data.get(key)
        if not entry:
            return None
        active = entry.get("active")
        if not active:
            return None
        return entry.get("profiles", {}).get(active)

    def render(self, key: str, **kwargs: str) -> Optional[str]:
        """
        Render the active profile for *key* with *kwargs* substituted.
        Returns None when no profile is active (caller falls back to default).
        """
        tmpl = self.get_active_template(key)
        if tmpl is None:
            return None
        return Template(tmpl).safe_substitute(**kwargs)

    def render_profile(self, key: str, name: str, **kwargs: str) -> Optional[str]:
        """
        Render a specific named profile for *key*, regardless of which profile
        is currently active. Used by rag_answer() to select by intent name.
        Returns None if the profile does not exist (caller falls back to default).
        """
        entry = self._data.get(key)
        if not entry:
            return None
        tmpl = entry.get("profiles", {}).get(name)
        if tmpl is None:
            return None
        return Template(tmpl).safe_substitute(**kwargs)

    # ── backward-compat shims used by existing routes ──────────────────────────

    def set(self, key: str, template: str) -> None:
        """Shorthand: save template as profile named 'default' and activate it."""
        self.set_profile(key, "default", template)

    def delete(self, key: str) -> bool:
        """Shorthand: delete the 'default' profile (or deactivate if others exist)."""
        entry = self._data.get(key)
        if not entry:
            return False
        if "default" in entry["profiles"]:
            return self.delete_profile(key, "default")
        # No 'default' profile — just clear active to revert to hardcoded
        entry["active"] = None
        self._save()
        return True

    # ── internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_key(key: str) -> None:
        if key not in VALID_KEYS:
            raise ValueError(
                f"Unknown prompt key '{key}'. "
                f"Valid keys: {', '.join(sorted(VALID_KEYS))}"
            )


# Module-level singleton — imported by prompts/templates.py and routes/api.py
prompt_store = PromptStore()
