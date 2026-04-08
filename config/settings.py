"""
Configuration settings for the application.
Centralized place for all constants and configurations.

# ============================================================
# CHANGES FROM ORIGINAL — config.py
# ─────────────────────────────────────────────────────────────
# ADDED: get_mode()         → returns "rag" or "csv" based on index state
# ADDED: RAG_TOP_K          → how many chunks to retrieve per query
# ADDED: SUPPORTED_FORMATS  → list of accepted upload file types
# ADDED: DOMAIN CONFIG      → domain-agnostic configuration system
# Everything else is UNCHANGED.
# ============================================================
"""
import os
import pandas as pd
from pathlib import Path
from config.domains import DomainConfig, get_domain, list_domains


class Settings:
    """Application settings"""

    # ── existing settings (UNCHANGED) ──────────────────────────────────────────
    OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
    OLLAMA_TIMEOUT  = 10000.0

    AVAILABLE_MODELS = {
        "Qwen 2.5":    "qwen2.5:7b",
        "Phi 3":       "phi3:14b",
        "Mistral":     "mistral:7b",
        "Llama 3.1":   "llama3.1:8b",
        "Qwen 3.5":    "qwen3.5:35b"
    }

    DEFAULT_MODEL = "qwen2.5:7b"

    # ── DOMAIN CONFIGURATION ───────────────────────────────────────────────────
    # Set active domain via environment variable or hardcode here
    # Options: education, banking, healthcare, retail, hr, inventory
    ACTIVE_DOMAIN = os.getenv("DOMAIN", "education")

    _domain: DomainConfig = None
    _df = None
    _uploaded_df = None  # ADDITION: temporary uploaded CSV DataFrame

    @classmethod
    def get_domain(cls) -> DomainConfig:
        """Get active domain configuration"""
        if cls._domain is None:
            cls._domain = get_domain(cls.ACTIVE_DOMAIN)
        return cls._domain

    @classmethod
    def set_domain(cls, domain_name: str) -> None:
        """
        Change active domain at runtime.

        Args:
            domain_name: Name of domain (education, banking, healthcare, etc.)
        """
        cls._domain = get_domain(domain_name)
        cls.ACTIVE_DOMAIN = domain_name
        # Clear cached dataframe so it reloads with new domain CSV
        cls._df = None
        print(f"✅ Switched to domain: {domain_name}")
        print(f"   Entity: {cls._domain.entity_name_plural}")
        print(f"   CSV: {cls._domain.csv_file_path}")

    DEFAULT_LIST_LIMIT = 20

    # ── BACKWARD COMPATIBILITY (deprecated, use get_domain() instead) ─────────
    @classmethod
    def get_csv_file_path(cls) -> str:
        """Get CSV file path from active domain"""
        return cls.get_domain().csv_file_path

    @classmethod
    def get_available_columns(cls) -> list:
        """Get available columns from active domain"""
        return cls.get_domain().field_names

    @classmethod
    def set_uploaded_dataframe(cls, df, filename=None) -> None:
        """ADDITION: Set temporary uploaded CSV (session only)"""
        cls._uploaded_df = df
        cls._uploaded_filename = filename

    @classmethod
    def clear_uploaded_dataframe(cls) -> None:
        """ADDITION: Revert to original CSV"""
        cls._uploaded_df = None

    # Marks columns used to compute Total_Marks
    MARKS_COLUMNS = ["Math_Marks", "Science_Marks", "English_Marks",
                     "Social_Marks", "Computer_Marks"]

    @classmethod
    def _add_computed_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived columns that the query planner can reference."""
        marks_present = [c for c in cls.MARKS_COLUMNS if c in df.columns]
        if marks_present and "Total_Marks" not in df.columns:
            df = df.copy()
            df["Total_Marks"] = df[marks_present].sum(axis=1)
        return df

    @classmethod
    def get_dataframe(cls) -> pd.DataFrame:
        """MODIFIED: Returns uploaded CSV if present, else original from active domain.
        Computed columns (e.g. Total_Marks) are added automatically."""
        if cls._uploaded_df is not None:
            return cls._add_computed_columns(cls._uploaded_df)
        if cls._df is None:
            domain = cls.get_domain()
            csv_path = domain.csv_file_path
            if not Path(csv_path).exists():
                raise FileNotFoundError(
                    f"CSV file not found: {csv_path}\n"
                    f"Domain: {domain.name}\n"
                    f"Please ensure the CSV file exists or change the domain."
                )
            cls._df = cls._add_computed_columns(pd.read_csv(csv_path))
        return cls._df

    # ── RAG ADDITION: new settings ─────────────────────────────────────────────
    RAG_TOP_K = 5                    # chunks retrieved per query

    SUPPORTED_FORMATS = [".pdf", ".xlsx", ".xls", ".xml", ".csv"]

    @classmethod
    def get_mode(cls) -> str:
        """
        # RAG ADDITION
        Auto-detect whether to run in RAG mode or CSV mode.

        Logic:
          - If the vector store has indexed data → "rag"
          - Otherwise                            → "csv"

        This is called per-request in routes.py so it reacts live
        when the user uploads a file.
        """
        try:
            from vector_store import vector_store   # local import avoids circular dep
            return "rag" if vector_store.status()["has_data"] else "csv"
        except Exception:
            return "csv"
    # ──────────────────────────────────────────────────────────────────────────


# Create singleton instance
settings = Settings()