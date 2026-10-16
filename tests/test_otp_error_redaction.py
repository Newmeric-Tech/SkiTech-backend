"""
otp._send_email: a SendGrid failure still returns False, but the log keeps
only the exception class and frames, never the recipient or the error text.
SendGrid is faked; nothing is sent.
"""
import logging

import sendgrid

from app.utils import otp

RECIPIENT = "guest-secret@example.com"
SECRET = "sendgrid-body-secret-123"


def test_send_email_failure_logs_no_recipient_or_message(monkeypatch, caplog):
    def fail(self, message):
        raise RuntimeError(f"403 Forbidden for {RECIPIENT}: {SECRET}")

    monkeypatch.setattr(otp.settings, "SENDGRID_API_KEY", "SG.fake")
    monkeypatch.setattr(sendgrid.SendGridAPIClient, "send", fail)
    with caplog.at_level(logging.ERROR, logger="skitech"):
        assert otp._send_email(RECIPIENT, "subject", "<p>x</p>") is False

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    logs = "\n".join(r.getMessage() for r in errors)
    assert "[SendGrid] ❌ Failed to send email: RuntimeError" in logs
    assert RECIPIENT not in logs
    assert SECRET not in logs
    assert all(r.exc_info is None for r in errors)
