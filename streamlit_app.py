"""
Streamlit frontend for the College AI Chatbot.
FIXES:
  - Sidebar CSS restored so toggle button works
  - Bottom uploader fixed (resets upload_done when new file selected)
  - Email preview renders immediately after agent response
"""
import requests
import streamlit as st

API_BASE          = "http://127.0.0.1:8000/api/v1"
ASK_URL           = f"{API_BASE}/ask"
UPLOAD_URL        = f"{API_BASE}/upload"
STATUS_URL        = f"{API_BASE}/status"
REMOVE_URL        = f"{API_BASE}/remove-file"
EMAIL_PREVIEW_URL = f"{API_BASE}/agent/email/preview"
EMAIL_SEND_URL    = f"{API_BASE}/agent/email/send"

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
    max-width: 860px !important;
    margin: auto;
    padding-bottom: 140px !important;
}
header { visibility: hidden; }
header [data-testid="stToolbar"] { visibility: visible !important; }

[data-testid="stSidebar"] {
    background-color: #0e1117 !important;
    min-width: 280px !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem !important;
}

.badge-rag   { background:#1a6b3a; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-csv   { background:#1a3a6b; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-agent { background:#6b3a1a; color:#fff; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600; }

.perplexity-title {
    text-align: center; font-size: 3rem; font-weight: 300;
    color: #ffffff; margin-top: 5rem; margin-bottom: 3rem; letter-spacing: -1px;
}

[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    display: flex; flex-direction: row-reverse !important;
    background: transparent !important; border: none !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stMarkdownContainer"] p {
    background: #1e2a3a; padding: 10px 18px;
    border-radius: 20px 20px 4px 20px; display: inline-block;
    max-width: 75%; float: right; color: #fff; font-size: 15px;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: transparent !important; border: none !important; padding-left: 0 !important;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] { display: none !important; }

[data-testid="stFileUploader"] {
    border: 1px dashed #444 !important; border-radius: 12px !important;
    padding: 6px !important; background: #111 !important;
}
[data-testid="stFileUploaderDropzone"] { padding: 8px !important; min-height: 0 !important; }

div[data-testid="stSelectbox"] > label { visibility: hidden; height: 0; margin: 0; padding: 0; }
div[data-testid="stSelectbox"] > div > div {
    background: #1a1a2e !important; border: 1px solid #333 !important;
    border-radius: 999px !important; color: #ccc !important; font-size: 13px !important;
}

div[data-testid="stButton"] button {
    background: #1a1a2e !important; border: 1px solid #333 !important;
    border-radius: 999px !important; color: #ccc !important;
    font-size: 13px !important; padding: 6px 20px !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stButton"] button:hover {
    background: #2a2a4a !important; border-color: #666 !important;
    color: #fff !important; box-shadow: 0 0 12px rgba(100,100,255,0.15) !important;
}

[data-testid="stChatInput"] {
    border-radius: 999px !important; background: #111827 !important;
    border: 1px solid #2a2a4a !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
}
[data-testid="stChatInput"] textarea {
    border-radius: 999px !important; background: transparent !important;
    font-size: 15px !important; color: #ccc !important; padding: 14px 20px !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #555 !important; }
[data-testid="stChatInputSubmitButton"] button {
    border-radius: 50% !important; background: #4a4a8a !important; border: none !important;
}
[data-testid="stChatInputSubmitButton"] button:hover { background: #6a6aba !important; }
</style>
""", unsafe_allow_html=True)


# ── session state ──────────────────────────────────────────────────────────────
if "messages"      not in st.session_state: st.session_state.messages = []
if "model_option"  not in st.session_state: st.session_state.model_option = "qwen2.5:1.5b"
if "pending_email" not in st.session_state: st.session_state.pending_email = None
if "last_uploaded" not in st.session_state: st.session_state.last_uploaded = None
if "upload_done"   not in st.session_state: st.session_state.upload_done = False


# ── sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
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
    st.header("📁 Document Index")

    try:
        status_resp = requests.get(STATUS_URL, timeout=5)
        status      = status_resp.json() if status_resp.ok else {}
    except Exception:
        status = {}

    mode          = status.get("mode", "csv")
    indexed_files = status.get("indexed_files", [])
    total_chunks  = status.get("total_chunks", 0)

    if mode == "rag":
        st.markdown('<span class="badge-rag">🟢 RAG Mode — documents active</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-csv">🔵 CSV Mode — using school database</span>',
                    unsafe_allow_html=True)

    st.caption(f"{total_chunks} chunks indexed across {len(indexed_files)} file(s)")

    try:
        active_resp = requests.get(f"{API_BASE}/active-csv", timeout=3)
        if active_resp.ok:
            active = active_resp.json()
            if active.get("uploaded"):
                st.info(f"📊 Active CSV: {active['filename']}\n\n"
                        f"{active['rows']} rows | {active['columns']} columns")
    except Exception:
        pass

    st.subheader("⚙️ Query Mode")
    manual_mode = st.radio(
        "Select mode:",
        ["Auto-detect", "CSV only (student database)", "RAG only (uploaded documents)"],
        index=0,
    )
    st.session_state["manual_mode"] = manual_mode
    st.divider()

    st.subheader("📤 Upload a file")
    sidebar_file = st.file_uploader(
        "PDF, Excel, XML, CSV (max 200MB)",
        type=["pdf", "xlsx", "xls", "xml", "csv"],
        key="sidebar_uploader",
    )
    if sidebar_file and st.button("📥 Index File", use_container_width=True):
        with st.spinner(f"Indexing {sidebar_file.name}…"):
            try:
                resp = requests.post(
                    UPLOAD_URL,
                    files={"file": (sidebar_file.name,
                                    sidebar_file.getvalue(),
                                    sidebar_file.type)},
                    timeout=300,
                )
                if resp.ok:
                    data = resp.json()
                    st.success(f"✅ **{data['filename']}** — {data['chunks_added']} chunks added")
                    if data.get("warning"):
                        st.warning(data["warning"])
                    st.rerun()
                else:
                    st.error(f"Upload failed: {resp.text}")
            except Exception as e:
                st.error(str(e))

    if indexed_files:
        st.subheader("Indexed files")
        for fname in indexed_files:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"📄 `{fname}`")
            if c2.button("🗑️", key=f"remove_{fname}"):
                with st.spinner(f"Removing {fname}…"):
                    try:
                        r = requests.post(REMOVE_URL, json={"filename": fname}, timeout=10)
                        if r.ok:
                            st.success(f"Removed {fname}")
                            st.rerun()
                        else:
                            st.error(r.text)
                    except Exception as e:
                        st.error(str(e))
    else:
        st.info("No files indexed yet.\nUpload above to start.")

    st.divider()
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
    st.divider()
    st.caption("Files indexed here switch the chatbot to RAG mode.\n"
               "Remove all files to return to CSV mode.")


# ── email preview modal ────────────────────────────────────────────────────────
def render_email_preview(pending: dict):
    preview         = pending.get("preview", {})
    intent          = pending.get("intent", {})
    recipients_full = pending.get("recipients", [])
    warning         = pending.get("warning")

    if warning:
        st.warning(warning)

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


# ── main chat area ─────────────────────────────────────────────────────────────
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


# ── bottom toolbar ─────────────────────────────────────────────────────────────
models      = ["qwen2.5:1.5b", "phi3:3.8b-mini-4k-instruct-q4_0"]
current_mdl = st.session_state.get("model_option", "qwen2.5:1.5b")
safe_index  = models.index(current_mdl) if current_mdl in models else 0

bottom_file = st.file_uploader(
    "Upload file",
    type=["pdf", "xlsx", "xls", "xml", "csv"],
    label_visibility="collapsed",
    key="bottom_uploader",
)

if bottom_file is not None:
    file_id = f"{bottom_file.name}_{bottom_file.size}"
    if file_id != st.session_state.last_uploaded:
        st.session_state.last_uploaded = file_id
        st.session_state.upload_done   = False

if bottom_file is not None and not st.session_state.upload_done:
    with st.spinner(f"Indexing {bottom_file.name}…"):
        try:
            resp = requests.post(
                UPLOAD_URL,
                files={"file": (bottom_file.name,
                                bottom_file.getvalue(),
                                bottom_file.type)},
                timeout=300,
            )
            if resp.ok:
                data = resp.json()
                st.session_state.upload_done = True
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
        try:
            sr = requests.get(STATUS_URL, timeout=3)
            if sr.ok:
                for fname in sr.json().get("indexed_files", []):
                    requests.post(REMOVE_URL, json={"filename": fname}, timeout=10)
        except Exception:
            pass
        st.rerun()


# ── chat input ─────────────────────────────────────────────────────────────────
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
                response = requests.post(
                    ASK_URL,
                    json={
                        "question":             prompt,
                        "model":                st.session_state.model_option,
                        "mode_override":        st.session_state.get("manual_mode", "Auto-detect"),
                        "conversation_history": conversation_history,
                    },
                    timeout=10000,
                )

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
                                            "question":      prompt,
                                            "model":         st.session_state.model_option,
                                            "parsed_intent": sq.get("parsed_intent"),
                                        },
                                        timeout=120,
                                    )
                                    if pr.ok:
                                        # ★ KEY FIX: save message first, then rerun to show preview
                                        st.session_state.messages.append({
                                            "role":    "assistant",
                                            "content": answer,
                                            "mode":    resp_mode,
                                        })
                                        st.session_state.pending_email = pr.json()
                                        st.rerun()
                                    else:
                                        st.error(f"Preview error: {pr.text}")
                                except Exception as e:
                                    st.error(f"Preview error: {e}")

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
                    if data.get("structured_query") and \
                            data["structured_query"].get("agent") != "email":
                        msg["structured_query"] = data["structured_query"]
                    if rag_sources:
                        msg["rag_sources"] = rag_sources
                    st.session_state.messages.append(msg)

                else:
                    err = f"Backend error ({response.status_code}): {response.text}"
                    st.error(err)
                    st.session_state.messages.append({"role": "assistant", "content": err})

            except requests.exceptions.RequestException as e:
                err = f"Connection failed: {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})

        try:
            _is_agent = (response.status_code == 200
                         and response.json().get("mode") == "agent")
        except Exception:
            _is_agent = False
        if not _is_agent:
            st.rerun()