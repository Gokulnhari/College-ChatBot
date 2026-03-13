"""
agents/email_agent.py  — fixed version

Key fixes:
  1. Skip sending to placeholder addresses (*.placeholder) — report as skipped, not failed
  2. Surface per-recipient SMTP errors clearly
  3. No markdown-mangling of email addresses in error messages
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict, List, Optional
import pandas as pd

from config import settings

SMTP_HOST    = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("EMAIL_SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("EMAIL_SENDER", "")
SENDER_PASS  = os.getenv("EMAIL_PASSWORD", "")


# ── recipient resolution ────────────────────────────────────────────────────────

def resolve_recipients(filters: List[Dict], df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    for f in filters:
        col = f.get("column") or f.get("field")
        op  = f.get("operator", "==")
        val = f.get("value")

        if col not in result.columns:
            continue

        if pd.api.types.is_numeric_dtype(result[col]):
            try:
                val = float(val) if "." in str(val) else int(val)
            except (ValueError, TypeError):
                pass

        if op == "==":
            result = result[result[col].astype(str).str.lower() == str(val).lower()] \
                if result[col].dtype == object else result[result[col] == val]
        elif op == "!=":
            result = result[result[col] != val]
        elif op == ">":
            result = result[result[col] > val]
        elif op == "<":
            result = result[result[col] < val]
        elif op == ">=":
            result = result[result[col] >= val]
        elif op == "<=":
            result = result[result[col] <= val]
        elif op == "contains":
            result = result[result[col].astype(str).str.contains(str(val), case=False, na=False)]
        elif op == "in":
            if isinstance(val, list):
                try:
                    val = [float(v) if "." in str(v) else int(v) for v in val]
                except (ValueError, TypeError):
                    val = [str(v) for v in val]
            result = result[result[col].isin(val) if isinstance(val, list) else result[col] == val]

    return result


# ── email address resolution ────────────────────────────────────────────────────

def get_email_addresses(
    recipients_df: pd.DataFrame,
    target: str = "student",
) -> List[Dict]:
    col_priority = {
        "student":  ["Email", "Student_Email", "email"],
        "parent":   ["Parent_Email", "Guardian_Email", "Parent_Contact"],
        "guardian": ["Guardian_Email", "Parent_Email"],
    }

    email_col = None
    for candidate in col_priority.get(target, ["Email"]):
        if candidate in recipients_df.columns:
            email_col = candidate
            break

    name_col = next(
        (c for c in ["Full_Name", "Name", "Student_Name"] if c in recipients_df.columns),
        None,
    )

    results = []
    for _, row in recipients_df.iterrows():
        name = str(row[name_col]) if name_col else "Student"

        raw_email = row.get(email_col) if email_col else None
        is_valid = (
            email_col
            and pd.notna(raw_email)
            and str(raw_email).strip() != ""
            and "@" in str(raw_email)
        )

        if is_valid:
            email = str(raw_email).strip()
            has_real_email = True
        else:
            # Placeholder — will be skipped at send time, not failed
            slug  = name.lower().replace(" ", ".")
            email = f"{slug}@school.placeholder"
            has_real_email = False

        results.append({
            "name":           name,
            "email":          email,
            "has_real_email": has_real_email,
            "row":            row.to_dict(),
        })

    return results


# ── email composition ───────────────────────────────────────────────────────────

def compose_email(
    recipient_name: str,
    subject: str,
    body_template: str,
    row_data: Optional[Dict] = None,
) -> str:
    body = body_template.replace("{name}", recipient_name)
    body = body.replace("[name]", recipient_name)
    body = body.replace("[Name]", recipient_name)
    if row_data:
        for key, value in row_data.items():
            str_val = str(value)
            # Support {key}, {KEY}, [key], [Key], [KEY] style placeholders
            body = body.replace("{" + str(key).lower() + "}", str_val)
            body = body.replace("{" + str(key) + "}", str_val)
            body = body.replace("[" + str(key).lower() + "]", str_val)
            body = body.replace("[" + str(key) + "]", str_val)
            body = body.replace("[" + str(key).upper() + "]", str_val)
    return body


# ── email preview ───────────────────────────────────────────────────────────────

def preview_email(intent: Dict, recipients: List[Dict]) -> Dict:
    # Only show real recipients in preview
    real = [r for r in recipients if r.get("has_real_email", True)]
    sample = real[0] if real else (recipients[0] if recipients else {"name": "Student", "row": {}})

    sample_body = compose_email(
        sample["name"],
        intent["subject"],
        intent["body_template"],
        sample.get("row", {}),
    )

    skipped = [r for r in recipients if not r.get("has_real_email", True)]

    return {
        "subject":         intent["subject"],
        "sample_body":     sample_body,
        "body_template":   intent["body_template"],
        "recipient_count": len(real),
        "recipients":      [{"name": r["name"], "email": r["email"]} for r in real],
        "skipped_count":   len(skipped),
        "skipped":         [{"name": r["name"], "reason": "no email on record"} for r in skipped],
        "target":          intent.get("target", "student"),
    }


# ── SMTP send ───────────────────────────────────────────────────────────────────

def send_emails(
    intent: Dict,
    recipients: List[Dict],
    sender_email: str = None,
    sender_pass:  str = None,
    dry_run: bool = False,
) -> Dict:
    # Always read from env at call time (not import time)
    sender_email = sender_email or os.getenv("EMAIL_SENDER", "")
    sender_pass  = sender_pass  or os.getenv("EMAIL_PASSWORD", "")
    # Separate real emails from placeholders
    real     = [r for r in recipients if r.get("has_real_email", "@" in r["email"] and ".placeholder" not in r["email"])]
    skipped  = [r for r in recipients if r not in real]
    sent     = []
    failed   = []
    errors   = []

    if dry_run:
        return {
            "success":      True,
            "sent_count":   len(real),
            "sent":         [r["email"] for r in real],
            "failed":       [],
            "skipped":      [r["email"] for r in skipped],
            "dry_run":      True,
        }

    if not sender_email or not sender_pass:
        return {
            "success":    False,
            "error":      "EMAIL_SENDER and EMAIL_PASSWORD are not set in your .env file.",
            "sent_count": 0,
            "failed":     [r["email"] for r in real],
        }

    if not real:
        names = ", ".join(r["name"] for r in skipped) if skipped else "the selected students"
        return {
            "success":    False,
            "error":      f"No valid email addresses found for {names}. Check the Email column in your CSV.",
            "sent_count": 0,
            "failed":     [],
            "skipped":    [r["email"] for r in skipped],
        }

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.login(sender_email, sender_pass)

        for r in real:
            try:
                body = compose_email(
                    r["name"],
                    intent["subject"],
                    intent["body_template"],
                    r.get("row", {}),
                )
                msg            = MIMEMultipart("alternative")
                msg["Subject"] = intent["subject"]
                msg["From"]    = sender_email
                msg["To"]      = r["email"]
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(
                    f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>",
                    "html",
                ))
                server.sendmail(sender_email, r["email"], msg.as_string())
                sent.append(r["email"])
                print(f"[email_agent] ✅ Sent to {r['email']}")
            except Exception as e:
                failed.append(r["email"])
                errors.append(f"{r['email']}: {str(e)}")
                print(f"[email_agent] ❌ Failed {r['email']}: {e}")

        server.quit()

    except smtplib.SMTPAuthenticationError:
        return {
            "success":    False,
            "error":      (
                "Gmail authentication failed. Make sure you are using an App Password "
                "(not your regular password). "
                "Generate one at https://myaccount.google.com/apppasswords"
            ),
            "sent_count": 0,
            "failed":     [r["email"] for r in real],
        }
    except Exception as e:
        return {
            "success":    False,
            "error":      f"SMTP connection error: {str(e)}",
            "sent_count": 0,
            "failed":     [r["email"] for r in real],
        }

    return {
        "success":    len(sent) > 0,
        "sent_count": len(sent),
        "sent":       sent,
        "failed":     failed,
        "errors":     errors,
        "skipped":    [r["email"] for r in skipped],
    }