"""
otp._send_email: on a SendGrid failure it logs one extra line of non-secret
key facts (status, lengths, edge booleans, SHA-256 prefix of the cleaned key,
sender domain) and never the key, the recipient or the error body. The key
is cleaned of surrounding whitespace/quotes before use. SendGrid is faked.
"""
import hashlib
import logging

import sendgrid

from app.utils import otp

RECIPIENT = "guest-secret@example.com"
KEY_BODY = "SG.fakeKeyId.fakeKeySecretText123"
RAW_KEY = f'"{KEY_BODY}"\n'
SENDER = "noreply-local@mail.example.org"
BODY = "unauthorized-body-text"


class Unauthorized(Exception):
    status_code = 401


def test_failure_logs_key_diagnostics_without_secrets(monkeypatch, caplog):
    used_keys = []

    def init(self, api_key=None, *args, **kwargs):
        used_keys.append(api_key)

    def fail(self, message):
        raise Unauthorized(f"401 for {RECIPIENT} with {KEY_BODY}: {BODY}")

    monkeypatch.setattr(otp.settings, "SENDGRID_API_KEY", RAW_KEY)
    monkeypatch.setattr(otp.settings, "SMTP_EMAIL", SENDER)
    monkeypatch.setattr(sendgrid.SendGridAPIClient, "__init__", init)
    monkeypatch.setattr(sendgrid.SendGridAPIClient, "send", fail)
    with caplog.at_level(logging.INFO, logger="skitech"):
        assert otp._send_email(RECIPIENT, "subject", "<p>x</p>") is False

    assert used_keys == [KEY_BODY]
    diagnostics = [r.getMessage() for r in caplog.records if "key diagnostics" in r.getMessage()]
    assert len(diagnostics) == 1
    line = diagnostics[0]
    for fact in ("status=401", f"raw_len={len(RAW_KEY)}", f"clean_len={len(KEY_BODY)}",
                 "starts_with_SG=False", "edge_whitespace=True", "edge_quote=True", "edge_newline=True",
                 f"sha256_prefix={hashlib.sha256(KEY_BODY.encode()).hexdigest()[:8]}",
                 "sender_domain=mail.example.org"):
        assert fact in line

    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "[SendGrid] ❌ Failed to send email: Unauthorized" in logs
    for secret in (KEY_BODY, "fakeKeyId", "fakeKeySecretText123", RECIPIENT, BODY, "noreply-local"):
        assert secret not in logs
    assert all(r.exc_info is None for r in caplog.records)


def test_clean_key_reports_no_edge_problems(monkeypatch, caplog):
    def fail(self, message):
        raise Unauthorized("401")

    monkeypatch.setattr(otp.settings, "SENDGRID_API_KEY", KEY_BODY)
    monkeypatch.setattr(sendgrid.SendGridAPIClient, "send", fail)
    with caplog.at_level(logging.ERROR, logger="skitech"):
        assert otp._send_email(RECIPIENT, "subject", "<p>x</p>") is False

    line = next(r.getMessage() for r in caplog.records if "key diagnostics" in r.getMessage())
    assert "starts_with_SG=True edge_whitespace=False edge_quote=False edge_newline=False" in line
