from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from grok_org_os.config import get_settings
from grok_org_os.connectors.base import Connector


class SmtpEmailConnector(Connector):
    name = "smtp_email"
    label = "Email (SMTP)"
    description = "Send email via SMTP when SMTP_HOST / credentials are set."

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.smtp_host.strip())

    def status(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "name": self.name,
            "label": self.label,
            "enabled": self.is_available(),
            "available": self.is_available(),
            "setup": (
                "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM "
                "in .env to enable outbound email."
            ),
            "host": s.smtp_host or None,
            "from": s.smtp_from or None,
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        s = get_settings()
        if not s.smtp_host:
            return {"error": "SMTP not configured"}
        to = payload.get("to")
        subject = payload.get("subject") or "(no subject)"
        body = payload.get("body") or ""
        if not to:
            return {"error": "to required"}
        msg = EmailMessage()
        msg["From"] = s.smtp_from or s.smtp_user or "grok-org-os@localhost"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if s.smtp_use_tls:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        return {"ok": True, "to": to, "subject": subject}
