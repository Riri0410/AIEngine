"""
Email Sender — CreativeOps AI

Sends real emails via async SMTP (aiosmtplib).
Configuration is read from environment variables:

  SMTP_HOST      — e.g. smtp.gmail.com        (required)
  SMTP_PORT      — e.g. 587                   (default: 587)
  SMTP_USER      — your email / login         (required)
  SMTP_PASSWORD  — app password / password    (required)
  SMTP_FROM      — display from address       (default: SMTP_USER)
  SMTP_TLS       — "true" / "false"           (default: true — STARTTLS on 587)

Gmail tip: create an App Password at myaccount.google.com → Security → App passwords.
"""

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

# ── aiosmtplib (optional dependency) ────────────────────────────────────────
try:
    import aiosmtplib
    _AIOSMTP_AVAILABLE = True
except ImportError:
    _AIOSMTP_AVAILABLE = False


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------

def _smtp_config() -> dict:
    return {
        "host":     os.environ.get("SMTP_HOST", ""),
        "port":     int(os.environ.get("SMTP_PORT", "587")),
        "user":     os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_":    os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")),
        "use_tls":  os.environ.get("SMTP_TLS", "true").lower() == "true",
    }


def smtp_configured() -> bool:
    """Return True if SMTP environment variables are fully set."""
    cfg = _smtp_config()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------

async def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    reply_to: str = "",
) -> dict:
    """
    Send a plain-text email via async SMTP.

    Returns:
        {"success": True, "message": "Sent to <to>"}
        {"success": False, "error": "<reason>"}
    """
    if not _AIOSMTP_AVAILABLE:
        return {"success": False, "error": "aiosmtplib not installed. Run: pip install aiosmtplib"}

    if not smtp_configured():
        return {
            "success": False,
            "error": (
                "SMTP not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD "
                "environment variables."
            ),
        }

    cfg = _smtp_config()

    # Build message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = cfg["from_"]
    msg["To"]      = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Also attach a minimal HTML version for nicer display
    html_body = _plain_to_html(body)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    recipients = [to] + ([cc] if cc else [])

    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            username=cfg["user"],
            password=cfg["password"],
            start_tls=cfg["use_tls"],
        )
        return {"success": True, "message": f"Email sent to {to}"}

    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Minimal plain→HTML converter
# ---------------------------------------------------------------------------

def _plain_to_html(text: str) -> str:
    """
    Convert plain text email body to simple HTML.
    Preserves line breaks, bolds **..** markers, converts URLs to links.
    """
    import html as html_lib
    import re

    lines = text.split("\n")
    html_lines = []

    for line in lines:
        # Escape HTML entities
        safe = html_lib.escape(line)
        # Bold **text**
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        # Numbered list items
        if re.match(r"^\d+\.", safe.strip()):
            safe = f"<li>{safe.strip()[2:].strip()}</li>"
        # Bullet list items
        elif safe.strip().startswith("- "):
            safe = f"<li>{safe.strip()[2:]}</li>"
        else:
            safe = safe + "<br>"
        html_lines.append(safe)

    body_content = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 14px; color: #2d2d35; line-height: 1.6; max-width: 620px; margin: 0 auto; padding: 24px; }}
  strong {{ color: #1a1a22; }}
  li {{ margin: 4px 0; }}
  hr {{ border: none; border-top: 1px solid #e5e5e8; margin: 20px 0; }}
  .footer {{ font-size: 11px; color: #9ca3af; margin-top: 24px; padding-top: 16px;
             border-top: 1px solid #e5e5e8; }}
  .amber {{ color: #b47a0a; font-weight: bold; }}
</style>
</head>
<body>
<div class="amber">CreativeOps Studio</div>
<hr>
{body_content}
<div class="footer">
  This email was generated by CreativeOps AI — Autonomous Creative Agency Platform
</div>
</body>
</html>"""
