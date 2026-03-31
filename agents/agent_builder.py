import json
import os

CUSTOM_AGENTS_FILE = "agents/custom_agents.json"

def save_custom_agent(agent: dict) -> None:
    agents = load_custom_agents()
    # Replace if same name exists
    agents = [a for a in agents if a.get("name") != agent.get("name")]
    agents.append(agent)
    os.makedirs("agents", exist_ok=True)
    with open(CUSTOM_AGENTS_FILE, "w") as f:
        json.dump(agents, f, indent=2)

def load_custom_agents() -> list:
    if not os.path.exists(CUSTOM_AGENTS_FILE):
        return []
    try:
        with open(CUSTOM_AGENTS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def delete_custom_agent(agent_name: str) -> bool:
    """
    Delete a custom agent by name.
    Returns True if deleted successfully, False if not found.
    """
    agents = load_custom_agents()

    # Filter out the agent with the given name
    filtered_agents = [a for a in agents if a.get("name") != agent_name]

    # If no agent was removed, it means it didn't exist
    if len(filtered_agents) == len(agents):
        return False

    # Save the updated list
    try:
        os.makedirs("agents", exist_ok=True)
        with open(CUSTOM_AGENTS_FILE, "w") as f:
            json.dump(filtered_agents, f, indent=2)
        return True
    except Exception:
        return False

def match_custom_agent(question: str) -> dict | None:
    """Check if question matches any custom agent trigger phrase."""
    q = question.lower()
    for agent in load_custom_agents():
        if any(phrase.lower() in q
               for phrase in agent.get("trigger_phrases", [])):
            return agent
    return None