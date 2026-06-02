"""
OTP Service - app/utils/otp.py
"""

import logging
import random
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger("skitech")

_otp_store: dict = {}
OTP_EXPIRY_SECONDS = 300  # 5 minutes


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def save_otp(email: str, otp: str) -> None:
    _otp_store[email] = {"otp": otp, "expires_at": time.time() + OTP_EXPIRY_SECONDS}


def get_otp(email: str) -> str | None:
    record = _otp_store.get(email)
    if not record:
        return None
    if time.time() > record["expires_at"]:
        delete_otp(email)
        return None
    return record["otp"]


def delete_otp(email: str) -> None:
    _otp_store.pop(email, None)


def verify_otp(email: str, otp: str) -> bool:
    stored = get_otp(email)
    if stored and stored == otp:
        delete_otp(email)
        return True
    return False


def _send_via_smtp(to: str, subject: str, html: str) -> bool:
    smtp_email = settings.SMTP_EMAIL
    smtp_password = settings.SMTP_PASSWORD

    if not smtp_email or not smtp_password:
        logger.warning(f"[SMTP] No credentials set — email to {to} skipped")
        return False

    logger.info(f"[SMTP] Sending '{subject}' to {to} via {smtp_email}")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_email
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to, msg.as_string())

        logger.info(f"[SMTP] ✅ Email sent successfully to {to}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[SMTP] ❌ Auth failed for {smtp_email}: {e}")
        return False
    except Exception as e:
        logger.error(f"[SMTP] ❌ Error sending to {to}: {type(e).__name__}: {e}", exc_info=True)
        return False


def send_invitation(email: str, temp_password: str) -> bool:
    logger.info(f"[Invite] Background task started for {email}")

    otp = generate_otp()
    save_otp(email, otp)

    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        logger.warning(f"[Invite] No SMTP credentials — OTP: {otp} | Pass: {temp_password}")
        return True

    frontend_url = settings.FRONTEND_URL
    verify_url = f"{frontend_url}/auth/verify-invite?email={email}"

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

    return _send_via_smtp(email, "You've been invited to SkiTech", html)


def send_otp(email: str, purpose: str = "verification") -> bool:
    otp = generate_otp()
    save_otp(email, otp)

    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        logger.info(f"[DEV OTP] {email} → {otp}")
        return True

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

    return _send_via_smtp(email, subject, html)
