"""SMS / notification helper - free-tier safe.

Default: demo-log (writes to sms_log table + console).
To go live in Tanzania, set sms_provider to 'beem' or 'africastalking'
and fill sms_api_key / sms_sender in Admin > Settings, then implement
the HTTP call in send_sms() using requests/urllib.
"""
import os
from datetime import datetime
import database as db


def send_sms(phone: str, message: str, reference_number: str = "") -> dict:
    provider = db.get_setting("sms_provider", "demo-log")
    api_key = db.get_setting("sms_api_key", "")
    sender = db.get_setting("sms_sender", "RUCU")
    status = "logged"
    # --- Live providers (fill in when you buy credit) ---
    # Example Beem Africa:
    #   POST https://apisms.beem.africa/v1/send with api_key
    # Example Africa's Talking:
    #   POST https://api.africastalking.com/version1/messaging
    # We deliberately do NOT call paid APIs unless configured.
    if provider in ("beem", "africastalking", "nextsms") and api_key:
        status = f"queued-via-{provider} (configure HTTP call)"
    conn = db.get_db()
    conn.execute(
        "INSERT INTO sms_log (phone, message, reference_number, provider, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (phone, message, reference_number, provider or "demo-log", status,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    print(f"[SMS:{provider}/{sender}] to {phone}: {message}")
    return {"provider": provider, "status": status}
