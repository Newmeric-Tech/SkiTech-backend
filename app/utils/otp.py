"""
OTP Service - app/utils/otp.py

OTPs are generated here and persisted in the users table (otp_code, otp_expires_at).
These functions only handle email delivery; callers save/verify OTPs via the DB.
"""

import hashlib
import logging
import random

from app.core.config import settings
from app.utils.safe_errors import log_safe_exception

logger = logging.getLogger("skitech")


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _key_diagnostics(raw: str, key: str, from_email: str, err: Exception) -> str:
    """Non-secret facts about the configured key, to compare with a key tested elsewhere.

    Only lengths, booleans, an 8-hex-char SHA-256 prefix of the cleaned key and the
    sender domain: never the key or any part of it, the recipient or the error body.
    """
    edges = [c for c in (raw[:1], raw[-1:]) if c]
    edge_whitespace = any(c.isspace() for c in edges)
    edge_quote = any(c in "\"'" for c in edges)
    edge_newline = any(c in "\r\n" for c in edges)
    sha_prefix = hashlib.sha256(key.encode()).hexdigest()[:8]
    sender_domain = from_email.rpartition("@")[2] if "@" in from_email else "(none)"
    return (
        "[SendGrid] key diagnostics:"
        f" status={getattr(err, 'status_code', None)}"
        f" raw_len={len(raw)} clean_len={len(key)}"
        f" starts_with_SG={raw.startswith('SG.')}"
        f" edge_whitespace={edge_whitespace} edge_quote={edge_quote} edge_newline={edge_newline}"
        f" sha256_prefix={sha_prefix} sender_domain={sender_domain}"
    )


def _send_email(to: str, subject: str, html: str) -> bool:
    raw_key = settings.SENDGRID_API_KEY
    if not raw_key:
        logger.warning("[Email] No SENDGRID_API_KEY set — skipping email")
        return False

    # Pasted values sometimes carry whitespace or surrounding quotes
    key = raw_key.strip().strip('"').strip("'")
    from_email = settings.SMTP_EMAIL or "skitech.noreply@gmail.com"
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=(from_email, "SkiTech"),
            to_emails=to,
            subject=subject,
            html_content=html,
        )
        sg = SendGridAPIClient(key)
        response = sg.send(message)
        logger.info(f"[SendGrid] ✅ Email sent — status: {response.status_code}")
        return True
    except Exception as e:
        # str(e) and exc_info can carry the recipient and SendGrid's response body.
        log_safe_exception(logger, "[SendGrid] ❌ Failed to send email", e)
        logger.error(_key_diagnostics(raw_key, key, from_email, e))
        return False


def send_invitation(email: str, temp_password: str, otp: str) -> bool:
    """Send invite email with temp password + OTP + verify button."""
    logger.info("[Invite] Sending invitation email")

    from urllib.parse import quote
    frontend_url = settings.FRONTEND_URL
    verify_url = f"{frontend_url}/auth/verify-invite?email={quote(email)}"

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px;background:#fff">
      <div style="text-align:center;margin-bottom:24px">
        <h1 style="font-size:24px;font-weight:bold;color:#111;margin:0">Welcome to SkiTech</h1>
        <p style="color:#666;margin-top:8px">You've been invited to join the platform.</p>
      </div>
      <div style="background:#f5f4f0;border-radius:12px;padding:20px;margin-bottom:16px">
        <p style="margin:0 0 6px;color:#888;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">Temporary Password</p>
        <code style="font-size:20px;font-weight:bold;color:#111;letter-spacing:2px">{temp_password}</code>
      </div>
      <div style="background:#f5f4f0;border-radius:12px;padding:20px;margin-bottom:24px">
        <p style="margin:0 0 6px;color:#888;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">Verification OTP <span style="color:#e07b00">(valid 5 min)</span></p>
        <p style="font-size:36px;font-weight:bold;letter-spacing:12px;color:#111;margin:0">{otp}</p>
      </div>
      <div style="text-align:center;margin-bottom:24px">
        <a href="{verify_url}" style="display:inline-block;background:#111;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px">Verify My Account</a>
      </div>
      <p style="color:#999;font-size:12px;text-align:center">
        After verification, log in at {frontend_url}/auth/login using your email and temporary password.
      </p>
    </div>
    """

    return _send_email(email, "You've been invited to SkiTech", html)


def send_otp(email: str, otp: str, purpose: str = "verification") -> bool:
    """Send a plain OTP email (resend-verification or password-reset)."""
    if purpose == "password_reset":
        subject = "SkiTech – Password Reset OTP"
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
          <h2 style="color:#111">Password Reset</h2>
          <p style="color:#555">Use this OTP to reset your password:</p>
          <p style="font-size:36px;font-weight:bold;letter-spacing:12px;color:#111">{otp}</p>
          <p style="color:#888;font-size:13px">Valid for 5 minutes. If you did not request this, ignore this email.</p>
        </div>"""
    else:
        subject = "SkiTech – Email Verification OTP"
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
          <h2 style="color:#111">Verify your email</h2>
          <p style="color:#555">Enter this OTP to verify your account:</p>
          <p style="font-size:36px;font-weight:bold;letter-spacing:12px;color:#111">{otp}</p>
          <p style="color:#888;font-size:13px">Valid for 5 minutes.</p>
        </div>"""

    return _send_email(email, subject, html)
