import json, os, uuid
from datetime import datetime

CHATS_DIR = "chats"
os.makedirs(CHATS_DIR, exist_ok=True)

def new_chat_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]

def save_chat(chat_id: str, messages: list, title: str = ""):
    path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    with open(path, "w") as f:
        json.dump({
            "title": title,
            "messages": messages,
            "updated": datetime.now().isoformat()
        }, f)

def load_chat(chat_id: str):
    path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if not os.path.exists(path):
        return [], ""
    with open(path) as f:
        data = json.load(f)
    return data.get("messages", []), data.get("title", "Untitled")

def list_chats():
    chats = []
    for fname in sorted(os.listdir(CHATS_DIR), reverse=True):
        if fname.endswith(".json"):
            chat_id = fname[:-5]
            with open(os.path.join(CHATS_DIR, fname)) as f:
                data = json.load(f)
            chats.append({
                "id": chat_id,
                "title": data.get("title") or "Untitled",
                "updated": data.get("updated", "")
            })
    return chats

def delete_chat(chat_id: str):
    path = os.path.join(CHATS_DIR, f"{chat_id}.json")
    if os.path.exists(path):
        os.remove(path)

def derive_title(messages: list) -> str:
    for m in messages:
        if m["role"] == "user":
            return m["content"][:40]
    return "Untitled"