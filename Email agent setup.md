# Email Agent Setup Guide

## What Was Added

### New Files
```
agents/
├── __init__.py          # Package exports
├── email_agent.py       # Core email logic (resolve, compose, send)
└── agent_router.py      # Intent detection + email parsing via LLM
```

### Modified Files
- `routes.py`         — Added /agent/email/preview and /agent/email/send endpoints
                        + agent detection before the normal CSV/RAG pipeline
- `streamlit_app.py`  — Added email preview card with Confirm/Cancel flow
                        + Dry-run toggle in sidebar

---

## How the Email Agent Works

```
Teacher types: "Send email to all Class 10 students about exam schedule"
         │
         ▼
   /ask endpoint
   detect_agent_intent()  ──► "send_email"
         │
         ▼
   Frontend calls /agent/email/preview
   parse_email_intent()   ──► {filters: [{Class == 10}], subject: ..., body: ...}
   resolve_recipients()   ──► 45 matching students from CSV
   get_email_addresses()  ──► list of {name, email} pairs
         │
         ▼
   Streamlit shows preview card:
   ┌─────────────────────────────────┐
   │ 📧 Email Preview                │
   │ Recipients: 45  Target: Student │
   │ Subject: Exam Schedule Notice   │
   │ [Sample body personalised...]   │
   │ [View recipient list ▼]         │
   │                                 │
   │  ✅ Confirm & Send  ❌ Cancel   │
   └─────────────────────────────────┘
         │
   Teacher clicks ✅
         │
         ▼
   /agent/email/send
   send_emails()  ──► SMTP sends personalised email to each student
         │
         ▼
   "✅ Emails sent! Successfully delivered to 45 recipient(s)."
```

---

## Setup — Gmail SMTP

1. Enable 2-Factor Authentication on your Gmail account

2. Generate an App Password:
   - Go to: https://myaccount.google.com/apppasswords
   - App: Mail  |  Device: Other (name it "CollegeAI")
   - Copy the 16-character password

3. Add to your `.env` file:

```env
EMAIL_SENDER=yourschool@gmail.com
EMAIL_PASSWORD=abcd efgh ijkl mnop   # 16-char app password (spaces OK)
EMAIL_SMTP_HOST=smtp.gmail.com       # optional, this is the default
EMAIL_SMTP_PORT=587                  # optional, this is the default
```

4. Load .env before starting the app:
```bash
pip install python-dotenv
```
Add to `main.py` (top):
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## Email Personalisation

The body template supports `{placeholder}` substitution using any column name:

| Placeholder              | Replaced with               |
|-------------------------|-----------------------------|
| `{name}`                | Student's full name         |
| `{Class}`               | Class number                |
| `{Section}`             | Section letter              |
| `{Attendance_Percentage}` | Attendance %              |
| `{Math_Marks}`          | Math marks                  |
| `{Student_ID}`          | Student ID                  |

Example template:
```
Dear {name},

Your current attendance is {Attendance_Percentage}%, which is below the required 75%.

Please contact your class teacher (Class {Class}, Section {Section}) immediately.

Regards,
School Administration
```

---

## Adding a Parent Email Column

To email parents, add a `Parent_Email` column to your CSV:

```csv
Student_ID,Full_Name,...,Email,Parent_Email
S001,Ravi Kumar,...,ravi@school.edu,ravi.parent@gmail.com
```

Then ask: *"Email parents of students with attendance below 75%"*
The agent will automatically use the `Parent_Email` column.

---

## Example Prompts

```
"Send email to all class 10 students about the annual sports day"
"Email students with attendance below 75% about the attendance warning"
"Send a fee reminder to students who haven't paid fees"
"Notify parents of Class 8 Section B about the parent-teacher meeting"
"Send email to all students about the holiday on Friday"
"Email top 5 students with a congratulations message"
```

---

## Dry-Run Mode (Testing)

By default, **Dry-run mode is ON** in the sidebar checkbox.
- Emails are simulated but NOT actually sent
- Perfect for testing the flow
- Turn OFF only when you're ready to send real emails

---

## File Structure

```
your_project/
├── agents/
│   ├── __init__.py
│   ├── email_agent.py       ← NEW
│   └── agent_router.py      ← NEW
├── routes.py                ← MODIFIED
├── streamlit_app.py         ← MODIFIED
├── .env                     ← ADD YOUR EMAIL CREDENTIALS
└── ...existing files...
```