"""Plain-text email delivery over SMTP or application logs."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from surgite import config

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "email"


def render_template(name: str, context: dict) -> tuple[str, str]:
    """Render a plain-text template into its subject and body."""
    raw = (_TEMPLATE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    filled = raw.format(**context)
    first, _, body = filled.partition("\n")
    if not first.lower().startswith("subject:"):
        raise ValueError(f"email template {name!r} must start with a 'Subject:' line")
    subject = first.split(":", 1)[1].strip()
    return subject, body.lstrip("\n")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...

    def send_template(self, to: str, template: str, context: dict) -> None: ...


class LoggingMailer:
    """Log email when SMTP is not configured."""

    def send(self, to: str, subject: str, body: str) -> None:
        log.info(
            "email (not sent — no SMTP configured) to=%s subject=%s\n%s",
            to,
            subject,
            body,
            extra={"email_to": to, "email_subject": subject},
        )

    def send_template(self, to: str, template: str, context: dict) -> None:
        subject, body = render_template(template, context)
        self.send(to, subject, body)


class SMTPMailer:
    """Send email over plain SMTP, STARTTLS, or implicit TLS."""

    def __init__(self) -> None:
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.username = config.SMTP_USERNAME
        self.password = config.SMTP_PASSWORD
        self.from_addr = config.SMTP_FROM
        self.tls = config.SMTP_TLS

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        if self.tls == "ssl":
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
        else:
            smtp = smtplib.SMTP(self.host, self.port, timeout=30)
        try:
            if self.tls == "starttls":
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        finally:
            smtp.quit()
        log.info("email sent to=%s subject=%s", to, subject, extra={"email_to": to})

    def send_template(self, to: str, template: str, context: dict) -> None:
        subject, body = render_template(template, context)
        self.send(to, subject, body)


def get_mailer() -> Mailer:
    """SMTPMailer when SMTP_HOST is configured, else LoggingMailer."""
    return SMTPMailer() if config.SMTP_HOST else LoggingMailer()
