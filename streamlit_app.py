import streamlit as st
import requests
import json

API_URL = "http://127.0.0.1:8000/api/v1/ask"

st.set_page_config(page_title="School System AI", layout="wide")

st.title("🎓 College System AI Chatbot")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages (survives reruns)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Show structured query if present (debug view)
        if "structured_query" in message and message["structured_query"]:
            with st.expander("🔍 Structured Query"):
                st.json(message["structured_query"])

# Model selector (can be placed anywhere – here at bottom for simplicity)
model_option = st.selectbox(
    "Select Model",
    ["qwen2.5:1.5b", "deepseek-r1:1.5b", "phi3:3.8b-mini-4k-instruct-q4_0"],
    index=0,
)

# Chat input – triggers only on real user submit (Enter / send)
if prompt := st.chat_input("Ask your question about the school dataset..."):
    # 1. Immediately show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Generate & show assistant response
    with st.chat_message("assistant"):
        with st.spinner(f"Querying dataset with {model_option.upper()}..."):
            try:
                response = requests.post(
                    API_URL,
                    json={"question": prompt, "model": model_option},
                    timeout=10000,  # increase if queries are slow
                )

                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("response", "No answer received from backend.")
                    
                    # Display main answer
                    st.markdown(answer)

                    # Save to history + optional debug info
                    msg = {
                        "role": "assistant",
                        "content": answer,
                    }
                    if data.get("structured_query"):
                        msg["structured_query"] = data["structured_query"]
                    
                    st.session_state.messages.append(msg)

                else:
                    error_text = f"Backend error ({response.status_code}): {response.text}"
                    st.error(error_text)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_text
                    })

            except requests.exceptions.RequestException as e:
                error_msg = f"Connection failed: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg
                })