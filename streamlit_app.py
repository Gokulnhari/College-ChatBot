"""
Streamlit frontend for the College AI Chatbot.

# ============================================================
# CHANGES FROM ORIGINAL — streamlit_app.py
# ─────────────────────────────────────────────────────────────
# ADDED: Sidebar file uploader  → upload PDF/Excel/XML/CSV to index
# ADDED: Sidebar status panel   → shows indexed files + current mode
# ADDED: Sidebar remove button  → delete a file from the index
# ADDED: RAG source citations   → expandable panel under RAG answers
# ADDED: Mode badge             → shows "RAG Mode" or "CSV Mode"
# Model selector position and chat logic are UNCHANGED.
# ============================================================
"""
import requests
import streamlit as st

# ── RAG ADDITION: backend URLs ────────────────────────────────────────────────
API_BASE    = "http://127.0.0.1:8000/api/v1"
ASK_URL     = f"{API_BASE}/ask"
UPLOAD_URL  = f"{API_BASE}/upload"
STATUS_URL  = f"{API_BASE}/status"
REMOVE_URL  = f"{API_BASE}/remove-file"
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="College AI Chatbot", layout="wide", page_icon="🎓")

# ── styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Mode badges */
.badge-rag  { background:#1a6b3a; color:#fff; padding:3px 10px;
              border-radius:12px; font-size:12px; font-weight:600; }
.badge-csv  { background:#1a3a6b; color:#fff; padding:3px 10px;
              border-radius:12px; font-size:12px; font-weight:600; }
/* Source chips */
.src-chip   { background:#2d2d2d; color:#ccc; padding:2px 8px;
              border-radius:8px; font-size:11px; margin:2px; display:inline-block; }
</style>
""", unsafe_allow_html=True)


# ── session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []


# ── RAG ADDITION: sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    # DOMAIN SELECTOR
    st.header("🎯 Domain Selection")
    try:
        domain_resp = requests.get(f"{API_BASE}/domain-info", timeout=3)
        if domain_resp.ok:
            domain_info = domain_resp.json()
            current_domain = domain_info.get("current_domain", "education")
            available_domains = domain_info.get("available_domains", ["education"])
            entity_plural = domain_info.get("entity_plural", "records")

            # Domain selector
            selected_domain = st.selectbox(
                "Active Domain:",
                available_domains,
                index=available_domains.index(current_domain) if current_domain in available_domains else 0,
                help="Switch between different industries/use-cases"
            )

            # If domain changed, switch it
            if selected_domain != current_domain:
                try:
                    switch_resp = requests.post(
                        f"{API_BASE}/set-domain",
                        json={"domain_name": selected_domain},
                        timeout=5
                    )
                    if switch_resp.ok:
                        st.success(f"Switched to {selected_domain}")
                        st.rerun()
                    else:
                        st.error(f"Failed to switch domain: {switch_resp.text}")
                except Exception as e:
                    st.error(f"Error switching domain: {e}")

            # Show current domain info
            st.caption(f"📊 Working with {entity_plural}")
        else:
            st.caption("Domain info unavailable")
    except Exception:
        pass

    st.divider()

    st.header("📁 Document Index")

    # Fetch current status
    try:
        status_resp = requests.get(STATUS_URL, timeout=5)
        status      = status_resp.json() if status_resp.ok else {}
    except Exception:
        status = {}

    mode          = status.get("mode", "csv")
    indexed_files = status.get("indexed_files", [])
    total_chunks  = status.get("total_chunks", 0)

    # Mode badge
    if mode == "rag":
        st.markdown('<span class="badge-rag">🟢 RAG Mode — documents active</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-csv">🔵 CSV Mode — using school database</span>',
                    unsafe_allow_html=True)

    st.caption(f"{total_chunks} chunks indexed across {len(indexed_files)} file(s)")

    # ADDITION: show active CSV notice
    try:
        active_resp = requests.get(f"{API_BASE}/active-csv", timeout=3)
        if active_resp.ok:
            active = active_resp.json()
            if active.get("uploaded"):
                st.info(f"📊 Active CSV: `{active['filename']}`\n\n"
                        f"{active['rows']} rows | {active['columns']} columns\n\n"
                        f"Remove it to revert to original database.")
    except Exception:
        pass
    # ADDITION END

    # Upload widget
    # Query Mode Selector
    st.subheader("⚙️ Query Mode")
    manual_mode = st.radio(
        "Select mode:",
        ["Auto-detect", "CSV only (student database)", "RAG only (uploaded documents)"],
        index=0
    )
    st.session_state["manual_mode"] = manual_mode
    st.divider()

    # Upload widget
    st.subheader("Upload a file")
    uploaded = st.file_uploader(
        "Supported: PDF, Excel, XML, CSV",
        type=["pdf", "xlsx", "xls", "xml", "csv"],
        help="Uploaded files are chunked and indexed. Chat will auto-switch to RAG mode."
    )

    if uploaded and st.button("📥 Index File", use_container_width=True):
        with st.spinner(f"Indexing {uploaded.name}…"):
            try:
                resp = requests.post(
                    UPLOAD_URL,
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    timeout=60,
                )
                if resp.ok:
                    data = resp.json()
                    st.success(
                        f"✅ **{data['filename']}** indexed!\n\n"
                        f"Added **{data['chunks_added']}** chunks "
                        f"({data['total_chunks']} total)"
                    )
                    if data.get("warning"):
                        st.warning(data["warning"])
                    st.rerun()
                else:
                    st.error(f"Upload failed: {resp.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")

    # Indexed files list + remove buttons
    if indexed_files:
        st.subheader("Indexed files")
        for fname in indexed_files:
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"📄 `{fname}`")
            if col2.button("🗑️", key=f"remove_{fname}", help=f"Remove {fname}"):
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
        st.info("No files indexed yet.\nUpload a file above to enable RAG mode.")

    st.divider()
    st.caption("When files are indexed, answers come from your documents.\nRemove all files to switch back to CSV mode.")
# ── END RAG ADDITION: sidebar ─────────────────────────────────────────────────


# ── main chat area ────────────────────────────────────────────────────────────
st.title("🎓 College System AI Chatbot")

# Display previous messages (UNCHANGED logic, added RAG source display)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # UNCHANGED: structured query expander (CSV mode)
        if message.get("structured_query"):
            with st.expander("🔍 Structured Query (CSV mode)"):
                st.json(message["structured_query"])

        # RAG ADDITION: source citations expander
        if message.get("rag_sources"):
            with st.expander(f"📚 Sources ({len(message['rag_sources'])} chunks)"):
                for i, src in enumerate(message["rag_sources"], 1):
                    meta = src.get("meta", {})
                    loc_parts = []
                    if "page" in meta:
                        loc_parts.append(f"page {meta['page']}")
                    if "sheet" in meta:
                        loc_parts.append(f"sheet '{meta['sheet']}'")
                    if "row" in meta:
                        loc_parts.append(f"row {meta['row']}")
                    loc = ", ".join(loc_parts) or "chunk"
                    score = src.get("score", 0)

                    st.markdown(
                        f"**Source {i}:** `{src.get('filename', '?')}` — {loc} "
                        f"*(relevance: {score:.2f})*"
                    )
                    st.caption(src.get("text", "")[:300] + ("…" if len(src.get("text","")) > 300 else ""))
                    st.divider()

        # RAG ADDITION: mode badge in history
        if message.get("mode"):
            badge_cls = "badge-rag" if message["mode"] == "rag" else "badge-csv"
            label     = "RAG" if message["mode"] == "rag" else "CSV"
            st.markdown(f'<span class="{badge_cls}">{label}</span>', unsafe_allow_html=True)


# UNCHANGED: model selector
model_option = st.selectbox(
    "Select Model",
    # ["qwen2.5:1.5b", "deepseek-r1:1.5b", "phi3:3.8b-mini-4k-instruct-q4_0"],
    ["qwen2.5:7b", "phi3:14b", "qwen3.5:35b", "mistral:7b", "llama3.1:8b"],
    index=0,
)

# UNCHANGED: chat input — only RAG fields added inside the block
if prompt := st.chat_input("Ask about your documents or the school dataset…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Thinking with {model_option}…"):
            try:
                # Build conversation history (exclude current question)
                conversation_history = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in st.session_state.messages[:-1]  # Exclude the just-added user message
                ]

                response = requests.post(
                    ASK_URL,
                    json={
                        "question": prompt,
                        "model": model_option,
                        "mode_override": st.session_state.get("manual_mode", "Auto-detect"),
                        "conversation_history": conversation_history  # Send context
                    },
                    timeout=10000,
                )

                if response.status_code == 200:
                    data   = response.json()
                    answer = data.get("response", "No answer received.")
                    resp_mode = data.get("mode", "csv")

                    st.markdown(answer)

                    # RAG ADDITION: show sources inline for RAG answers
                    rag_sources = data.get("rag_sources") or []
                    if rag_sources:
                        with st.expander(f"📚 Sources ({len(rag_sources)} chunks)"):
                            for i, src in enumerate(rag_sources, 1):
                                meta = src.get("meta", {})
                                loc_parts = []
                                if "page" in meta:
                                    loc_parts.append(f"page {meta['page']}")
                                if "sheet" in meta:
                                    loc_parts.append(f"sheet '{meta['sheet']}'")
                                if "row" in meta:
                                    loc_parts.append(f"row {meta['row']}")
                                loc   = ", ".join(loc_parts) or "chunk"
                                score = src.get("score", 0)
                                st.markdown(
                                    f"**Source {i}:** `{src.get('filename','?')}` — {loc} "
                                    f"*(relevance: {score:.2f})*"
                                )
                                st.caption(src.get("text","")[:300])
                                st.divider()

                    # RAG ADDITION: mode badge
                    badge_cls = "badge-rag" if resp_mode == "rag" else "badge-csv"
                    label     = "RAG Mode" if resp_mode == "rag" else "CSV Mode"
                    st.markdown(f'<span class="{badge_cls}">{label}</span>', unsafe_allow_html=True)

                    # Save to history
                    msg = {
                        "role":    "assistant",
                        "content": answer,
                        "mode":    resp_mode,
                    }
                    if data.get("structured_query"):
                        msg["structured_query"] = data["structured_query"]
                    if rag_sources:
                        msg["rag_sources"] = rag_sources

                    st.session_state.messages.append(msg)

                else:
                    error_text = f"Backend error ({response.status_code}): {response.text}"
                    st.error(error_text)
                    st.session_state.messages.append({"role": "assistant", "content": error_text})

            except requests.exceptions.RequestException as e:
                error_msg = f"Connection failed: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})