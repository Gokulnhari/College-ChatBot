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

Extract the email details FROM THE USER MESSAGE BELOW.
Use the EXACT topic, event, date, and details mentioned in the message for the subject and body.
Do NOT use generic placeholders like "Important Announcement".

Available columns in the student database:
Student_ID, Full_Name, Gender, Class, Section, Math_Marks, Science_Marks,
English_Marks, Social_Marks, Computer_Marks, Attendance_Percentage, Fee_Paid

Return ONLY valid JSON in this exact format:
{{
  "target": "student",
  "filters": [
    {{"column": "ColumnName", "operator": "==", "value": <value>}}
  ],
  "subject": "Write a specific subject based on the user message",
  "body_template": "Dear {{name}},\\n\\nWrite a specific body based on the user message.\\n\\nRegards,\\nSchool Administration",
  "send_all": false
}}

EXAMPLES:
User: "send email to class 10 about sports day on 31-03-26"
Subject: "Sports Day - 31st March 2026"
Body: "Dear {{name}},\\n\\nThis is to inform you that Sports Day will be held on 31st March 2026.\\n\\nKindly make necessary arrangements to attend.\\n\\nRegards,\\nSchool Administration"

User: "send email to student id 5001 about fee due"
Subject: "Fee Payment Reminder"
Body: "Dear {{name}},\\n\\nThis is a reminder that your fee payment is due. Please clear your dues at the earliest.\\n\\nRegards,\\nSchool Administration"

User message: {question}
"""

REPORT_PARSE_PROMPT = """
Extract report details from the user message. Be precise.

report_type rules:
- "attendance" → mentions attendance, absent, present, percentage
- "marks"      → mentions marks, score, grades, result, exam
- "fee"        → mentions fee, payment, due, paid, unpaid
- "full"       → only if no specific type mentioned

output_format rules:
- "pdf"   → if user says pdf, PDF, document, print   ← CHECK THIS
- "excel" → if user says excel, xlsx, spreadsheet, default if not mentioned

Return ONLY valid JSON, no explanation:
{{
  "report_type": "attendance",
  "filters": [
    {{"column": "Class",   "operator": "==", "value": 8}},
    {{"column": "Section", "operator": "==", "value": "A"}}
  ],
  "output_format": "pdf",
  "filename": "attendance_class8_sectionA"
}}

IMPORTANT:
- Class values are integers: use 8 not "8"
- Section values are strings: use "A" not A
- output_format must be exactly "pdf" or "excel" — nothing else

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
        "what is", "whats", "who is", "list", "display",
        "how many", "total number", "count", "how much",
        "average", "marks", "attendance", "section", "class",
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
        print(f"[email_parse] raw LLM response: {raw[:200]}")
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


async def parse_report_intent(question: str, model_name: str = None) -> Dict:
    model  = model_name or settings.DEFAULT_MODEL
    prompt = REPORT_PARSE_PROMPT.format(question=question)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.OLLAMA_TIMEOUT)) as client:
            resp = await client.post(
                settings.OLLAMA_URL,
                json={"model": model, "prompt": prompt,
                      "stream": False, "format": "json"}
            )
            resp.raise_for_status()
        intent = json.loads(resp.json().get("response", "{}"))
        return intent
    except Exception:
        return {
            "report_type":   "full",
            "filters":       [],
            "output_format": "excel",
            "filename":      "report"
        }


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