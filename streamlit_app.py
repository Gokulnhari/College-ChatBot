"""
Streamlit frontend for the College AI Chatbot
Dedicated per-agent chat like Copilot Studio
"""
import requests
import streamlit as st
from chat_history import new_chat_id, save_chat, load_chat, list_chats, delete_chat, derive_title
from agents.agent_builder import save_custom_agent, load_custom_agents, delete_custom_agent

API_BASE          = "http://127.0.0.1:8000/api/v1"
ASK_URL           = f"{API_BASE}/ask"
UPLOAD_URL        = f"{API_BASE}/upload"
STATUS_URL        = f"{API_BASE}/status"
REMOVE_URL        = f"{API_BASE}/remove-file"
EMAIL_PREVIEW_URL = f"{API_BASE}/agent/email/preview"
EMAIL_SEND_URL    = f"{API_BASE}/agent/email/send"
REPORT_URL        = f"{API_BASE}/agent/report/generate"  # ← must exist

st.set_page_config(
    page_title="College AI Chatbot",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {
    padding-top: 2rem !important;
    max-width: 960px !important;
    margin: auto;
    padding-bottom: 140px !important;
}
.perplexity-title {
    text-align: center; font-size: 3rem; font-weight: 300;
    color: #ffffff; margin-top: 5rem; margin-bottom: 3rem; letter-spacing: -1px;
}
.agent-header {
    font-size: 1.9rem; font-weight: 600; color: #fff;
    margin-bottom: 1.2rem; display: flex; align-items: center; gap: 12px;
}
.badge-rag   { background:#1a6b3a; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-csv   { background:#1a3a6b; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-agent { background:#6b3a1a; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ── Session State ──────────────────────────────────────────────────────────────
if "messages"           not in st.session_state: st.session_state.messages = []
if "model_option"       not in st.session_state: st.session_state.model_option = "qwen2.5:1.5b"
if "pending_email"      not in st.session_state: st.session_state.pending_email = None
if "last_uploaded"      not in st.session_state: st.session_state.last_uploaded = None
if "upload_done"        not in st.session_state: st.session_state.upload_done = False
if "last_uploaded_name" not in st.session_state: st.session_state.last_uploaded_name = None
if "current_chat_id"    not in st.session_state: st.session_state.current_chat_id = new_chat_id()
if "current_view"       not in st.session_state: st.session_state.current_view = "chat"
if "editing_agent"      not in st.session_state: st.session_state.editing_agent = None
if "selected_agent"     not in st.session_state: st.session_state.selected_agent = None  # Active agent for dedicated chat


# ── Fetch status ───────────────────────────────────────────────────────────────
try:
    status_resp = requests.get(STATUS_URL, timeout=5)
    status = status_resp.json() if status_resp.ok else {}
except Exception:
    status = {}

mode          = status.get("mode", "csv")
indexed_files = status.get("indexed_files", [])
total_chunks  = status.get("total_chunks", 0)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:

    if st.button("➕ New Chat", use_container_width=True, key="new_chat_sidebar"):
        st.session_state.messages = []
        st.session_state.pending_email = None
        st.session_state.current_chat_id = new_chat_id()
        st.session_state.current_view = "chat"
        st.session_state.selected_agent = None
        st.rerun()

    st.subheader("🤖 Agent Library")

    if st.button("➕ Create New Agent", use_container_width=True, key="create_agent_btn"):
        st.session_state.current_view = "create_agent"
        st.session_state.editing_agent = None
        st.rerun()

    saved_agents = load_custom_agents()
    if saved_agents:
        st.caption(f"**{len(saved_agents)} Custom Agents**")
        for ag in saved_agents:
            col_a, col_b = st.columns([5, 1])
            if col_a.button(f"🤖 {ag['name']}", key=f"ag_{ag['name']}", use_container_width=True):
                st.session_state.selected_agent = ag
                st.session_state.messages = []                    # Clear chat for new agent
                st.session_state.current_chat_id = new_chat_id()
                st.session_state.current_view = "chat"
                st.rerun()
            if col_b.button("🗑️", key=f"del_ag_{ag['name']}"):
                delete_custom_agent(ag["name"])
                if st.session_state.selected_agent and st.session_state.selected_agent.get("name") == ag["name"]:
                    st.session_state.selected_agent = None
                st.rerun()
    else:
        st.info("No custom agents yet. Create one above.")

    st.divider()

    # Chat History
    st.subheader("🕘 Recent chats")
    for chat in list_chats():
        col_a, col_b = st.columns([5, 1])
        label = chat["title"][:28] + ("…" if len(chat["title"]) > 28 else "")
        active = chat["id"] == st.session_state.current_chat_id
        if col_a.button(("▶ " if active else "") + label, key=f"ch_{chat['id']}", use_container_width=True):
            msgs, _ = load_chat(chat["id"])
            st.session_state.messages = msgs
            st.session_state.current_chat_id = chat["id"]
            st.session_state.pending_email = None
            st.rerun()
        if col_b.button("🗑️", key=f"del_{chat['id']}"):
            delete_chat(chat["id"])
            if chat["id"] == st.session_state.current_chat_id:
                st.session_state.messages = []
                st.session_state.current_chat_id = new_chat_id()
            st.rerun()

    st.divider()

    # ── Domain Selection ───────────────────────────────────────────
    st.header("🎯 Domain Selection")
    try:
        domain_resp = requests.get(f"{API_BASE}/domain-info", timeout=3)
        if domain_resp.ok:
            domain_info       = domain_resp.json()
            current_domain    = domain_info.get("current_domain", "education")
            available_domains = domain_info.get("available_domains", ["education"])
            entity_plural     = domain_info.get("entity_plural", "records")

            selected_domain = st.selectbox(
                "Active Domain:", available_domains,
                index=available_domains.index(current_domain)
                      if current_domain in available_domains else 0,
            )
            if selected_domain != current_domain:
                try:
                    r = requests.post(f"{API_BASE}/set-domain",
                                      json={"domain_name": selected_domain}, timeout=5)
                    if r.ok:
                        st.success(f"Switched to {selected_domain}")
                        st.rerun()
                    else:
                        st.error(f"Failed: {r.text}")
                except Exception as e:
                    st.error(str(e))
            st.caption(f"📊 Working with {entity_plural}")
    except Exception:
        pass

    st.divider()

    # ── Document Index & Uploaded Files ───────────────────────────
    st.header("📁 Uploaded Files")

    if mode == "rag":
        st.markdown('<span class="badge-rag">🟢 RAG Mode — documents active</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-csv">🔵 CSV Mode — using database</span>',
                    unsafe_allow_html=True)

    st.caption(
        "📄 **PDF, XML** → RAG mode (document reading)\n\n"
        "📊 **Excel, CSV** → CSV mode (database queries)\n\n"
        "Upload using the 📎 box below the chat."
    )

    # ── Show active CSV/Excel ──────────────────────────────────────
    active_resp = None
    try:
        active_resp = requests.get(f"{API_BASE}/active-csv", timeout=3)
        if active_resp.ok:
            active = active_resp.json()
            if active.get("uploaded"):
                fname = active["filename"]
                ext   = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                icon  = "📊" if ext in ("csv", "xlsx", "xls") else "📄"
                st.info(f"{icon} **{fname}**\n\n"
                        f"{active['rows']} rows | {active['columns']} columns")
                if st.button("🗑️ Remove", key="remove_active_csv", use_container_width=True):
                    try:
                        requests.post(REMOVE_URL, json={"filename": fname}, timeout=5)
                        st.session_state.last_uploaded      = None
                        st.session_state.last_uploaded_name = None
                        st.session_state.upload_done        = False
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    except Exception:
        pass

    # ── Show indexed RAG files ─────────────────────────────────────
    if indexed_files:
        st.caption(f"{total_chunks} chunks indexed across {len(indexed_files)} file(s)")
        for fname in indexed_files:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"📄 `{fname}`")
            if c2.button("🗑️", key=f"remove_{fname}"):
                with st.spinner(f"Removing {fname}…"):
                    try:
                        r = requests.post(REMOVE_URL, json={"filename": fname}, timeout=10)
                        if r.ok:
                            st.session_state.pending_email = None
                            st.rerun()
                        else:
                            st.error(r.text)
                    except Exception as e:
                        st.error(str(e))
    elif not (active_resp is not None and active_resp.ok and active_resp.json().get("uploaded")):
        st.info("No files uploaded yet.\nUse the 📎 box below the chat to upload.")

    st.divider()

    # ── Query Mode ─────────────────────────────────────────────────
    st.subheader("⚙️ Query Mode")
    manual_mode = st.radio(
        "Select mode:",
        ["Auto-detect", "CSV only (student database)", "RAG only (uploaded documents)"],
        index=0,
    )
    st.session_state["manual_mode"] = manual_mode

    st.divider()

    # ── Email Agent ────────────────────────────────────────────────
    st.header("📧 Email Agent")
    st.caption(
        "Send emails to students/parents from chat.\n\n"
        "**Try:** *'Send email to all class 10 students about exam schedule'*\n\n"
        "**Setup:** Add `EMAIL_SENDER` and `EMAIL_PASSWORD` to your `.env`."
    )
    dry_run_mode = st.checkbox(
        "🧪 Dry-run (simulate, don't send)",
        value=False,
        help="Turn ON to simulate without sending real emails.",
    )
    st.session_state["dry_run"] = dry_run_mode


# ── Email Preview Modal ────────────────────────────────────────────────────────
def render_email_preview(pending: dict):
    preview         = pending.get("preview") or {}
    intent          = pending.get("intent") or {}
    recipients_full = pending.get("recipients", [])
    warning         = pending.get("warning")

    if warning:
        st.warning(warning)

    if not preview:
        st.error("⚠️ No recipients found. The uploaded CSV may have been removed.")
        if st.button("❌ Close"):
            st.session_state.pending_email = None
            st.rerun()
        return

    st.markdown("### 📧 Email Preview — Please Review Before Sending")
    col1, col2 = st.columns(2)
    col1.metric("Recipients", preview.get("recipient_count", 0))
    col2.metric("Target", intent.get("target", "student").title())
    st.markdown(f"**Subject:** {preview.get('subject', '')}")

    with st.expander("📝 Sample Email Body", expanded=True):
        st.text(preview.get("sample_body", ""))

    with st.expander(f"👥 Recipient List ({preview.get('recipient_count', 0)} total)"):
        for i, r in enumerate(preview.get("recipients", [])[:20], 1):
            st.markdown(f"{i}. **{r['name']}** — `{r['email']}`")
        if preview.get("recipient_count", 0) > 20:
            st.caption(f"... and {preview['recipient_count'] - 20} more")

    dry_run = st.session_state.get("dry_run", False)
    if dry_run:
        st.info("🧪 **Dry-run ON** — emails will be simulated, not sent.")

    col_ok, col_no = st.columns(2)
    with col_ok:
        if st.button("✅ Confirm & Send", use_container_width=True, type="primary"):
            with st.spinner("Sending…"):
                try:
                    sr = requests.post(
                        EMAIL_SEND_URL,
                        json={"intent": intent, "recipients": recipients_full,
                              "dry_run": dry_run},
                        timeout=120,
                    )
                    if sr.ok:
                        res  = sr.json()
                        sent = res.get("sent_count", 0)
                        fail = res.get("failed", [])
                        msg  = (f"🧪 **Dry-run complete!** Would have sent to **{sent}** recipient(s)."
                                if dry_run else
                                f"✅ **Sent!** Delivered to **{sent}** recipient(s).")
                        if fail:
                            failed_list = ", ".join(f"`{e}`" for e in fail)
                            msg += f"\n\n⚠️ Failed: {failed_list}"
                        if res.get("error"):
                            msg += f"\n\n🔴 Error: {res['error']}"
                        if res.get("errors"):
                            msg += "\n\n**SMTP errors:**\n" + "\n".join(f"- `{e}`" for e in res["errors"])
                    else:
                        msg = f"❌ Failed: {sr.json().get('detail', sr.text)}"
                except Exception as e:
                    msg = f"❌ Connection error: {e}"
            st.session_state.messages.append(
                {"role": "assistant", "content": msg, "mode": "agent"})
            st.session_state.pending_email = None
            st.rerun()
    with col_no:
        if st.button("❌ Cancel", use_container_width=True):
            st.session_state.messages.append(
                {"role": "assistant",
                 "content": "📧 Email cancelled. No messages were sent.",
                 "mode": "agent"})
            st.session_state.pending_email = None
            st.rerun()


# ── Chat Rendering Function ────────────────────────────────────────────────────
def render_chat():
    """Renders the main chat messages and email preview"""
    agent = st.session_state.get("selected_agent")

    if agent:
        # Show dedicated agent header (from file 2)
        st.markdown(f'<div class="agent-header">🤖 {agent["name"]}</div>',
                    unsafe_allow_html=True)
        if agent.get("description"):
            st.caption(agent["description"])
    else:
        if not st.session_state.messages:
            st.markdown('<div class="perplexity-title">🎓 College AI</div>',
                        unsafe_allow_html=True)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("structured_query"):
                sq = message["structured_query"]
                if sq.get("agent") != "email":
                    with st.expander("🔍 Structured Query"):
                        st.json(sq)
            if message.get("rag_sources"):
                with st.expander(f"📚 Sources ({len(message['rag_sources'])} chunks)"):
                    for i, src in enumerate(message["rag_sources"], 1):
                        meta      = src.get("meta", {})
                        loc_parts = []
                        if "page"  in meta: loc_parts.append(f"page {meta['page']}")
                        if "sheet" in meta: loc_parts.append(f"sheet '{meta['sheet']}'")
                        if "row"   in meta: loc_parts.append(f"row {meta['row']}")
                        loc = ", ".join(loc_parts) or "chunk"
                        st.markdown(f"*Source {i}:* `{src.get('filename','?')}` — "
                                    f"{loc} (relevance: {src.get('score',0):.2f})")
                        st.caption(src.get("text","")[:300] +
                                   ("…" if len(src.get("text","")) > 300 else ""))
                        st.divider()
            if message.get("mode"):
                badge_map = {"rag": ("badge-rag","RAG"), "csv": ("badge-csv","CSV"),
                             "agent": ("badge-agent","🤖 Agent")}
                cls, lbl = badge_map.get(message["mode"], ("badge-csv","CSV"))
                st.markdown(f'<span class="{cls}">{lbl}</span>', unsafe_allow_html=True)

    if st.session_state.pending_email:
        with st.chat_message("assistant"):
            render_email_preview(st.session_state.pending_email)


# ── Agent Builder View (Full Page) ─────────────────────────────────────────────
def render_agent_builder():
    editing = st.session_state.get("editing_agent")
    title   = f"Edit — {editing['name']}" if editing else "Create New Agent"

    # Header with back button
    col_back, col_title = st.columns([1, 5])
    if col_back.button("← Back"):
        st.session_state.current_view  = "chat"
        st.session_state.editing_agent = None
        st.rerun()
    col_title.markdown(f"## 🤖 {title}")

    st.divider()

    # Two column layout
    col_config, col_preview = st.columns([1, 1], gap="large")

    with col_config:
        st.subheader("Configure")

        tab_desc, tab_config = st.tabs(["Describe", "Configure"])

        with tab_desc:
            agent_name = st.text_input("Agent Name",
                value=editing.get("name", "") if editing else "",
                placeholder="e.g. AttendanceBot")
            agent_desc = st.text_area("Description",
                value=editing.get("description", "") if editing else "",
                placeholder="A friendly agent that helps with attendance queries.",
                height=100)

        with tab_config:
            agent_instructions = st.text_area("Instructions",
                value=editing.get("instructions", "") if editing else "",
                placeholder=(
                    "- Respond concisely\n"
                    "- Only use database data\n"
                    "- If not found, say 'I don't have that information'"
                ),
                height=150)
            trigger_phrases = st.text_input("Trigger phrases (comma separated)",
                value=", ".join(editing.get("trigger_phrases", [])) if editing else "",
                placeholder="attendance report, low attendance, flag students")
            agent_action = st.selectbox("Action type",
                ["email", "report", "alert", "chat"],
                index=["email","report","alert","chat"].index(
                    editing.get("action","chat")) if editing else 3)

        st.divider()

        # Knowledge sources
        st.subheader("Knowledge")
        st.caption("Files and data this agent uses to answer questions.")
        knowledge_file = st.file_uploader(
            "Upload knowledge file",
            type=["pdf", "xlsx", "csv", "xml"],
            key="agent_knowledge_file"
        )
        if knowledge_file:
            st.success(f"📎 {knowledge_file.name} will be used as knowledge source")

        st.divider()

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("💾 Save Agent", use_container_width=True, type="primary"):
                if agent_name and trigger_phrases:
                    save_custom_agent({
                        "name":            agent_name,
                        "description":     agent_desc,
                        "instructions":    agent_instructions,
                        "trigger_phrases": [t.strip() for t in trigger_phrases.split(",") if t.strip()],
                        "action":          agent_action,
                    })

                    # ← Upload knowledge file if provided
                    if knowledge_file:
                        with st.spinner(f"Indexing {knowledge_file.name}…"):
                            try:
                                resp = requests.post(
                                    UPLOAD_URL,
                                    files={"file": (knowledge_file.name,
                                                    knowledge_file.getvalue(),
                                                    knowledge_file.type)},
                                    timeout=300,
                                )
                                if resp.ok:
                                    st.success(f"📎 {knowledge_file.name} indexed!")
                                else:
                                    st.warning(f"Agent saved but file upload failed: {resp.text}")
                            except Exception as e:
                                st.warning(f"Agent saved but file upload error: {e}")

                    st.success(f"✅ Agent '{agent_name}' saved!")
                    st.session_state.current_view  = "chat"
                    st.session_state.editing_agent = None
                    st.rerun()
                else:
                    st.error("Name and trigger phrases are required.")
        with col_cancel:
            if st.button("Cancel", use_container_width=True):
                st.session_state.current_view  = "chat"
                st.session_state.editing_agent = None
                st.rerun()

    with col_preview:
        st.subheader("Preview")
        name_display = agent_name if 'agent_name' in locals() else "Your Agent"
        desc_display = agent_desc if 'agent_desc' in locals() else "Your agent description will appear here."

        st.markdown(f"""
        <div style="background:#1a1a2e; border-radius:16px; padding:24px; text-align:center; margin-bottom:16px;">
            <div style="font-size:48px;">🤖</div>
            <h3 style="color:#fff; margin:8px 0;">{name_display}</h3>
            <p style="color:#aaa; font-size:14px;">{desc_display}</p>
        </div>
        """, unsafe_allow_html=True)

# ── View Router ───────────────────────────────────────────────────────────────
if st.session_state.get("current_view") == "create_agent":
    render_agent_builder()
else:
    render_chat()


# ── Bottom Toolbar ─────────────────────────────────────────────────────────────
models      = ["qwen2.5:1.5b", "phi3:3.8b-mini-4k-instruct-q4_0"]
current_mdl = st.session_state.get("model_option", "qwen2.5:1.5b")
safe_index  = models.index(current_mdl) if current_mdl in models else 0

# ── UNIFIED uploader (bottom only) ────────────────────────────────────────────
bottom_file = st.file_uploader(
    "Upload file",
    type=["pdf", "xlsx", "xls", "xml", "csv"],
    label_visibility="collapsed",
    key="bottom_uploader",
)

if bottom_file is not None:
    file_id = f"{bottom_file.name}_{bottom_file.size}"
    if file_id != st.session_state.last_uploaded:
        st.session_state.last_uploaded      = file_id
        st.session_state.last_uploaded_name = bottom_file.name
        st.session_state.upload_done        = False
else:
    if st.session_state.last_uploaded is not None:
        fname = st.session_state.get("last_uploaded_name", "uploaded_file.csv")
        try:
            requests.post(REMOVE_URL, json={"filename": fname}, timeout=5)
        except Exception:
            pass
        st.session_state.last_uploaded      = None
        st.session_state.last_uploaded_name = None
        st.session_state.upload_done        = False
        st.rerun()

if bottom_file is not None and not st.session_state.upload_done:
    with st.spinner(f"Uploading {bottom_file.name}…"):
        try:
            resp = requests.post(
                UPLOAD_URL,
                files={"file": (bottom_file.name,
                                bottom_file.getvalue(),
                                bottom_file.type)},
                timeout=300,
            )
            if resp.ok:
                data        = resp.json()
                source_type = data.get("source_type", "")
                st.session_state.upload_done = True
                if source_type in ("csv", "excel"):
                    st.success(f"✅ **{data['filename']}** — loaded as database ({data['chunks_added']} rows)")
                else:
                    st.success(f"✅ **{data['filename']}** — {data['chunks_added']} chunks indexed")
                if data.get("warning"):
                    st.info(data["warning"])
                st.rerun()
            else:
                st.session_state.upload_done = True
                st.error(f"Upload failed: {resp.text}")
        except Exception as e:
            st.session_state.upload_done = True
            st.error(str(e))

# ── Model selector + new chat ──────────────────────────────────────────────────
col_model, col_newchat = st.columns([3, 1])
with col_model:
    st.session_state.model_option = st.selectbox(
        "Model", models, index=safe_index,
        label_visibility="collapsed", key="model_selector_bottom",
    )
with col_newchat:
    if st.button("New Chat", use_container_width=True, key="new_chat_bottom"):
        st.session_state.messages      = []
        st.session_state.pending_email = None
        st.session_state.current_view  = "chat"
        st.session_state.selected_agent = None
        # Clear files on new chat
        try:
            sr = requests.get(STATUS_URL, timeout=3)
            if sr.ok:
                for fname in sr.json().get("indexed_files", []):
                    requests.post(REMOVE_URL, json={"filename": fname}, timeout=10)
        except Exception:
            pass
        if st.session_state.get("last_uploaded_name"):
            try:
                requests.post(REMOVE_URL, json={"filename": st.session_state.last_uploaded_name}, timeout=5)
            except Exception:
                pass
        st.session_state.last_uploaded      = None
        st.session_state.last_uploaded_name = None
        st.session_state.upload_done        = False
        st.rerun()


# ── Chat Input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask about your documents, the school dataset, or say 'send email to…'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Thinking with {st.session_state.model_option}…"):
            try:
                conversation_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                payload = {
                    "question":             prompt,
                    "model":                st.session_state.model_option,
                    "mode_override":        st.session_state.get("manual_mode", "Auto-detect"),
                    "conversation_history": conversation_history,
                }
                # Pass selected agent to backend (from file 2)
                if st.session_state.get("selected_agent"):
                    payload["selected_agent"] = st.session_state.selected_agent["name"]
                    print(f"[FRONTEND] Sending with agent: {payload['selected_agent']}")
                else:
                    print(f"[FRONTEND] No agent selected")

                response = requests.post(ASK_URL, json=payload, timeout=10000)

                if response.status_code == 200:
                    data      = response.json()
                    answer    = data.get("response", "No answer received.")
                    resp_mode = data.get("mode", "csv")

                    st.markdown(answer)

                    if resp_mode == "agent":
                        sq = data.get("structured_query", {})

                        if sq.get("agent") == "email":
                            with st.spinner("Preparing email preview…"):
                                try:
                                    pr = requests.post(
                                        EMAIL_PREVIEW_URL,
                                        json={
                                            "question": prompt,
                                            "model": st.session_state.model_option,
                                            "parsed_intent": sq.get("parsed_intent"),
                                        },
                                        timeout=120,
                                    )
                                    if pr.ok:
                                        st.session_state.messages.append({
                                            "role": "assistant",
                                            "content": answer,
                                            "mode": resp_mode,
                                        })
                                        st.session_state.pending_email = pr.json()
                                        st.rerun()
                                    else:
                                        st.error(f"Preview error: {pr.text}")
                                except Exception as e:
                                    st.error(f"Preview error: {e}")

                        elif sq.get("agent") == "report":
                            with st.spinner("Generating report..."):
                                try:
                                    # ── Detect format directly from prompt — don't trust LLM ──────
                                    q_lower = prompt.lower()
                                    if "pdf" in q_lower:
                                        forced_format = "pdf"
                                    else:
                                        forced_format = "excel"

                                    # ── Get intent from structured_query ──────────────────────────
                                    intent = sq.get("parsed_intent", {})

                                    # ── Always override format from prompt ────────────────────────
                                    intent["output_format"] = forced_format

                                    report_resp = requests.post(
                                        REPORT_URL,
                                        json={
                                            "question":      prompt,
                                            "model":         st.session_state.model_option,
                                            "parsed_intent": intent,   # ← pass full intent with correct format
                                        },
                                        timeout=120,
                                    )

                                    if report_resp.ok:
                                        # ── Correct extension and mime type ───────────────────────
                                        if forced_format == "pdf":
                                            ext       = "pdf"
                                            mime_type = "application/pdf"
                                        else:
                                            ext       = "xlsx"
                                            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

                                        filename = intent.get("filename", "report")
                                        fname    = f"{filename}.{ext}"

                                        st.success(f"✅ Report ready — {fname}")
                                        st.download_button(
                                            label     = f"📥 Download {ext.upper()} Report",
                                            data      = report_resp.content,
                                            file_name = fname,
                                            mime      = mime_type,
                                        )
                                    else:
                                        st.error(f"❌ Failed to generate report: {report_resp.text}")

                                except Exception as e:
                                    st.error(f"Report generation failed: {e}")

                        elif sq.get("agent") == "alert":
                            triggered = sq.get("triggered", [])

                            if triggered:
                                for alert in triggered:
                                    st.warning(
                                        f"⚠️ {alert['rule']['name']}: "
                                        f"{alert['count']} students matched"
                                    )
                            else:
                                st.info("No alerts triggered.")

                    rag_sources = data.get("rag_sources") or []
                    if rag_sources:
                        with st.expander(f"📚 Sources ({len(rag_sources)} chunks)"):
                            for i, src in enumerate(rag_sources, 1):
                                meta      = src.get("meta", {})
                                loc_parts = []
                                if "page"  in meta: loc_parts.append(f"page {meta['page']}")
                                if "sheet" in meta: loc_parts.append(f"sheet '{meta['sheet']}'")
                                if "row"   in meta: loc_parts.append(f"row {meta['row']}")
                                loc = ", ".join(loc_parts) or "chunk"
                                st.markdown(f"*Source {i}:* `{src.get('filename','?')}` — "
                                            f"{loc} (relevance: {src.get('score',0):.2f})")
                                st.caption(src.get("text","")[:300])
                                st.divider()

                    badge_map = {"rag": ("badge-rag","RAG Mode"), "csv": ("badge-csv","CSV Mode"),
                                 "agent": ("badge-agent","🤖 Agent Mode")}
                    cls, lbl = badge_map.get(resp_mode, ("badge-csv","CSV Mode"))
                    st.markdown(f'<span class="{cls}">{lbl}</span>', unsafe_allow_html=True)

                    msg = {"role": "assistant", "content": answer, "mode": resp_mode}
                    if data.get("structured_query") and data["structured_query"].get("agent") != "email":
                        msg["structured_query"] = data["structured_query"]
                    if rag_sources:
                        msg["rag_sources"] = rag_sources
                    st.session_state.messages.append(msg)

                    save_chat(st.session_state.current_chat_id,
                              st.session_state.messages,
                              title=derive_title(st.session_state.messages))

                else:
                    err = f"Backend error ({response.status_code}): {response.text}"
                    st.error(err)
                    st.session_state.messages.append({"role": "assistant", "content": err})

            except requests.exceptions.RequestException as e:
                err = f"Connection failed: {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

        try:
            _is_agent = (response.status_code == 200 and response.json().get("mode") == "agent")
        except Exception:
            _is_agent = False
        if not _is_agent:
            st.rerun()