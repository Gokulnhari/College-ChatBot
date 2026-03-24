"""
agents/agent_router.py
"""

import json
import re
import httpx
from typing import Dict, Optional

from config import settings


AGENT_DETECTION_PROMPT = """You are an intent classifier for a school management chatbot.

Classify the user message into ONE of these intents:
- "send_email"   → user wants to send an email to students, parents, or a class
- "none"         → regular question, data lookup, or anything else

Return ONLY valid JSON:
{{"intent": "send_email"}} OR {{"intent": "none"}}

User message: {question}
"""

EMAIL_PARSE_PROMPT = """You are an email intent parser for a school management system.

Extract the email details from the user message.

Available columns in the student database:
Student_ID, Full_Name, Gender, Class, Section, Math_Marks, Science_Marks,
English_Marks, Social_Marks, Computer_Marks, Attendance_Percentage, Fee_Paid

Return ONLY valid JSON in this exact format:
{
  "target": "student" | "parent" | "guardian",
  "filters": [
    {{"column": "ColumnName", "operator": "==", "value": <value>}}
],
  "subject": "Email subject line here",
  "body_template": "Dear {name},\n\nEmail body here.\n\nRegards,\nSchool Administration",
  "send_all": true | false
}

User message: {question}
"""


def _fix_name_placeholders(body: str) -> str:
    body = re.sub(r'\[Full_Name\]', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'\[Student_Name\]', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'\[Name\]', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'\[name\]', '{name}', body)
    body = re.sub(r'<Full_Name>', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'<name>', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'\{Full_Name\}', '{name}', body, flags=re.IGNORECASE)
    body = re.sub(r'\{Student_Name\}', '{name}', body, flags=re.IGNORECASE)
    return body


async def detect_agent_intent(question: str, model_name: str = None) -> str:
    # Check negative keywords first — these are NEVER email intents
    q = question.lower()
    non_email_patterns = [
        "give the", "show me", "fetch", "get", "find", "details",
        "what is", "whats", "who is", "list", "display"
    ]
    if any(p in q for p in non_email_patterns) and "email" not in q:
        return "none"
    

    model  = model_name or settings.DEFAULT_MODEL
    prompt = AGENT_DETECTION_PROMPT.format(question=question)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.OLLAMA_TIMEOUT)) as client:
            resp = await client.post(
                settings.OLLAMA_URL,
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            )
            resp.raise_for_status()
        data   = resp.json()
        parsed = json.loads(data.get("response", "{}"))
        return parsed.get("intent", "none")
    except Exception:
        q = question.lower()
        if any(kw in q for kw in ["send email", "email to", "mail to", "notify", "inform via email"]):
            return "send_email"
        return "none"


async def parse_email_intent(question: str, model_name: str = None) -> Dict:
    model  = model_name or settings.DEFAULT_MODEL
    prompt = EMAIL_PARSE_PROMPT.replace("{question}", question)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.OLLAMA_TIMEOUT)) as client:
            resp = await client.post(
                settings.OLLAMA_URL,
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            )
            resp.raise_for_status()
        data = resp.json()
        raw  = data.get("response", "{}").strip()
        try:
            intent = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                intent = json.loads(match.group())
            else:
                return _fallback_intent(question)
        if "body_template" in intent:
            intent["body_template"] = _fix_name_placeholders(intent["body_template"])
        return intent
    except Exception:
        return _fallback_intent(question)


def _fallback_intent(question: str) -> Dict:
    return {
        "target": "student",
        "filters": [],
        "subject": "Important Announcement from School",
        "body_template": (
            "Dear {name},\n\n"
            "This is an important announcement from the school administration.\n\n"
            "Please contact the school office for more details.\n\n"
            "Regards,\nSchool Administration"
        ),
        "send_all": True,
    }
