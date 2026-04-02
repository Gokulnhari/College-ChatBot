# 🤖 Custom Agent System — How It Works

## Overview

The custom agent system lets you create specialized AI assistants inside the College AI Chatbot. Each agent has its own name, personality, instructions, and knowledge — and gets its own dedicated chat view just like Copilot Studio.

---

## Architecture — Full Flow

```
User clicks "Create New Agent"
        ↓
Fills in Name, Description, Instructions, Trigger Phrases, Action
        ↓
Optionally uploads a Knowledge File (PDF, CSV, XLSX, XML)
        ↓
Clicks "💾 Save Agent"
        ↓
┌─────────────────────────────────────────────────────┐
│  streamlit_app.py (Frontend)                                  │
│  1. save_custom_agent() → writes to custom_agents.json │
│  2. If knowledge file → POST /api/v1/upload         │
└─────────────────────────────────────────────────────┘
        ↓
Agent appears in sidebar under "Agent Library"
        ↓
User clicks the agent → dedicated chat opens
        ↓
User sends a message
        ↓
┌─────────────────────────────────────────────────────┐
│  app.py sends payload:                              │
│  {                                                  │
│    "question": "...",                               │
│    "model": "...",                                  │
│    "selected_agent": "AgentName",   ← key field    │
│    "conversation_history": [...]                    │
│  }                                                  │
└─────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────┐
│  routes/api.py (Backend)                            │
│  1. Reads selected_agent from request               │
│  2. Loads agent from custom_agents.json             │
│  3. Prepends instructions to conversation_history:  │
│     [{"role": "system", "content": instructions}]   │
│  4. Proceeds with normal ask pipeline               │
└─────────────────────────────────────────────────────┘
        ↓
LLM receives the system instruction + user question
        ↓
LLM responds according to the agent's personality/rules
```

---

## File-by-File Breakdown

### 1. `agents/agent_builder.py`
The core utility file. Handles all read/write operations for agents.

| Function | What it does |
|---|---|
| `save_custom_agent(agent)` | Saves agent to `custom_agents.json`. Replaces if same name exists. |
| `load_custom_agents()` | Reads and returns all saved agents as a list. |
| `delete_custom_agent(name)` | Removes agent by name from JSON. Returns True/False. |
| `match_custom_agent(question)` | Checks if a question matches any agent's trigger phrases. |

---

### 2. `agents/custom_agents.json`
The persistent store for all custom agents. Auto-created on first save.

```json
[
  {
    "name": "AttendanceBot",
    "description": "Handles attendance queries",
    "instructions": "You only answer attendance-related questions. Be concise.",
    "trigger_phrases": ["attendance", "absent", "present"],
    "action": "chat"
  }
]
```

---

### 3. `app.py` — Frontend (3 places involved)

#### A) Sidebar — Agent Library
```python
saved_agents = load_custom_agents()
for ag in saved_agents:
    if col_a.button(f"🤖 {ag['name']}"):
        st.session_state.selected_agent = ag   # ← stores full agent dict
        st.session_state.messages = []          # ← fresh chat
        st.rerun()
```

#### B) render_agent_builder() — Create/Edit Form
Collects: Name, Description, Instructions, Trigger Phrases, Action, Knowledge File.

On Save:
1. Calls `save_custom_agent()` → writes JSON
2. If knowledge file uploaded → POSTs to `/api/v1/upload` → indexes into vector store
3. Redirects back to chat view

#### C) Chat Input — Payload Construction
```python
payload = {
    "question": prompt,
    "model": st.session_state.model_option,
    "mode_override": st.session_state.get("manual_mode", "Auto-detect"),
    "conversation_history": conversation_history,
}
if st.session_state.get("selected_agent"):
    payload["selected_agent"] = st.session_state.selected_agent["name"]
```

#### D) render_chat() — Agent Header
When an agent is selected, shows the agent name + description at the top of the chat:
```python
agent = st.session_state.get("selected_agent")
if agent:
    st.markdown(f'<div class="agent-header">🤖 {agent["name"]}</div>')
    st.caption(agent["description"])
```

---

### 4. `models.py` — Request Model
```python
class QuestionRequest(BaseModel):
    question:             str
    model:                str
    mode_override:        Optional[str] = "Auto-detect"
    conversation_history: Optional[List[Dict[str, str]]] = None  
    selected_agent:       Optional[str] = None   # ← carries agent name to backend
```

---

### 5. `routes/api.py` — Instruction Injection
This is the key backend step. Runs at the very start of `ask_question()`:

```python
conversation_history = request.conversation_history or []

if request.selected_agent:
    from agents.agent_builder import load_custom_agents
    custom_agents = load_custom_agents()
    active_agent = next(
        (a for a in custom_agents if a["name"] == request.selected_agent), None
    )
    if active_agent and active_agent.get("instructions"):
        conversation_history = [
            {"role": "system", "content": active_agent["instructions"]}
        ] + conversation_history
```

The system message is prepended — so the LLM always sees the agent's rules first, before any user message or history.

---

## Agent Fields Explained

| Field | Required | Purpose |
|---|---|---|
| **Name** | ✅ | Unique identifier, shown in sidebar and chat header |
| **Description** | ❌ | Shown as subtitle under agent name in chat |
| **Instructions** | ❌ | Injected as system prompt — controls LLM behavior |
| **Trigger Phrases** | ✅ | Comma-separated keywords (used by `match_custom_agent`) |
| **Action** | ✅ | `chat`, `email`, `report`, or `alert` |
| **Knowledge File** | ❌ | PDF/CSV/XLSX/XML — indexed into vector store on save |

---

## Knowledge File — How It Works

When you upload a file in the agent builder:

```
PDF/XML  → vector_store.add_file() → chunked + embedded → RAG mode
CSV/XLSX → settings.set_uploaded_dataframe() → query_executor.df → CSV mode
```

After saving the agent with a PDF, the system automatically switches to RAG mode. When you chat with that agent and ask "summarize the pdf", the backend:
1. Detects `mode = rag`
2. Classifies intent as `summarize`
3. Retrieves top chunks from the vector store
4. Passes them to the LLM for summarization

---

## What Happens When You Chat With an Agent

```
1. You type a message in TestBot's chat
2. Frontend sends: { question, model, selected_agent: "TestBot", history }
3. Backend loads TestBot's instructions from custom_agents.json
4. Instructions prepended to history as {"role": "system", "content": "..."}
5. Normal pipeline runs (csv / rag / email / general)
6. LLM answers — but constrained by the system instruction
7. Response returned and displayed in chat
```

---

## Current Limitations

| Limitation | Status |
|---|---|
| Knowledge file is shared globally, not per-agent | Known — all agents share the same vector store |
| No edit button — must re-save with same name to update | Known workaround |
| Trigger phrases don't auto-switch agents in chat | Not implemented yet |
| Agent instructions only affect LLM tone/behavior, not routing | By design |

---

## Quick Test Checklist

- [ ] Create agent with pirate instructions → reply should say "Arrr!"
- [ ] `agents/custom_agents.json` contains the saved agent
- [ ] Backend terminal shows `[AGENT] Active agent: ...` when chatting
- [ ] Backend terminal shows `[AGENT] Instructions injected: ...`
- [ ] Uploading PDF via agent builder → terminal shows `[upload] ...`
- [ ] Asking "summarize the pdf" → logs show `[routes] Mode: rag`
- [ ] Deleting agent → removed from sidebar and JSON file