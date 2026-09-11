"""Email rendering and delivery-selection tests."""

import logging

import pytest

from surgite import config, mail


def test_render_template_splits_subject_and_fills_fields():
    subject, body = mail.render_template(
        "password-reset", {"reset_url": "https://x/password-reset?token=pr_a_b", "ttl_minutes": 15}
    )
    assert subject == "Reset your surgite password"
    assert "https://x/password-reset?token=pr_a_b" in body
    assert "15 minutes" in body
    assert "Subject:" not in body


def test_render_template_missing_field_raises():
    with pytest.raises(KeyError):
        mail.render_template("password-reset", {"reset_url": "https://x"})


def test_logging_mailer_writes_the_email(caplog):
    with caplog.at_level(logging.INFO, logger="surgite.mail"):
        mail.LoggingMailer().send_template(
            "u@example.com",
            "password-reset",
            {"reset_url": "https://x/password-reset?token=pr_a_b", "ttl_minutes": 15},
        )
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name == "surgite.mail")
    assert "u@example.com" in logged
    assert "pr_a_b" in logged


def test_get_mailer_defaults_to_logging_without_smtp(monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "")
    assert isinstance(mail.get_mailer(), mail.LoggingMailer)


def test_get_mailer_uses_smtp_when_configured(monkeypatch):
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.com")
    assert isinstance(mail.get_mailer(), mail.SMTPMailer)
