"""
OTP Service - app/utils/otp.py

In-memory OTP store (replace with Redis in production).
"""

import random
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

# In-memory store: { email: { "otp": "123456", "expires_at": float } }
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


def send_invitation(email: str, temp_password: str) -> bool:
    """Send OTP + temporary password to a newly invited user."""
    otp = generate_otp()
    save_otp(email, otp)

    frontend_url = settings.FRONTEND_URL
    verify_url = f"{frontend_url}/auth/verify-invite?email={email}"

    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        print(f"[DEV INVITE] {email} → OTP: {otp} | Temp Password: {temp_password}")
        return True

    subject = "SkiTech – You've Been Invited"
    body = f"""<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px">
        <h2 style="color:#111">Welcome to SkiTech!</h2>
        <p>You have been invited to join the SkiTech platform. Use the details below to verify your account and get started.</p>

        <div style="background:#f5f4f0;border-radius:12px;padding:20px;margin:20px 0">
            <p style="margin:0 0 8px;color:#555;font-size:14px">Your temporary password:</p>
            <code style="font-size:18px;font-weight:bold;color:#111;letter-spacing:2px">{temp_password}</code>
        </div>

        <div style="background:#f5f4f0;border-radius:12px;padding:20px;margin:20px 0">
            <p style="margin:0 0 8px;color:#555;font-size:14px">Your verification OTP (valid 5 minutes):</p>
            <h1 style="letter-spacing:10px;margin:0;color:#111;font-size:32px">{otp}</h1>
        </div>

        <p style="margin-bottom:20px">Click below to verify your email and activate your account:</p>
        <a href="{verify_url}" style="display:inline-block;background:#111;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:15px">Verify My Account</a>

        <p style="color:#888;font-size:13px;margin-top:24px">
            After verification, log in at
            <a href="{frontend_url}/auth/login" style="color:#555">{frontend_url}/auth/login</a>
            using your email and temporary password.
        </p>
        <p style="color:#bbb;font-size:12px">If you did not expect this invitation, please ignore this email.</p>
    </body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_EMAIL
        msg["To"] = email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_EMAIL, email, msg.as_string())

        return True
    except Exception as e:
        print(f"[INVITE ERROR] {e}")
        return False


def send_otp(email: str, purpose: str = "verification") -> bool:
    otp = generate_otp()
    save_otp(email, otp)

    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        # Dev mode: just print the OTP
        print(f"[DEV OTP] {email} → {otp}")
        return True

    if purpose == "password_reset":
        subject = "SkiTech – Password Reset OTP"
        body = f"""<html><body>
            <h2>Password Reset</h2>
            <p>Use this OTP to reset your password:</p>
            <h1 style="letter-spacing:8px">{otp}</h1>
            <p>Valid for 5 minutes.</p>
        </body></html>"""
    else:
        subject = "SkiTech – Email Verification OTP"
        body = f"""<html><body>
            <h2>Welcome to SkiTech!</h2>
            <p>Verify your email with this OTP:</p>
            <h1 style="letter-spacing:8px">{otp}</h1>
            <p>Valid for 5 minutes.</p>
        </body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_EMAIL
        msg["To"] = email
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_EMAIL, email, msg.as_string())

        return True
    except Exception as e:
        print(f"[OTP ERROR] {e}")
        return False
