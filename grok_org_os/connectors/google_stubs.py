from __future__ import annotations

from typing import Any

from grok_org_os.config import get_settings
from grok_org_os.connectors.base import Connector


class GoogleMailStub(Connector):
    name = "google_mail"
    label = "Google Mail (stub)"
    description = "Activates when GOOGLE_CLIENT_ID / SECRET / REFRESH_TOKEN are set. Stub until OAuth wired."

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_refresh_token)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "enabled": self.is_available(),
            "available": self.is_available(),
            "setup": (
                "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN. "
                "Full Gmail API wiring is stubbed in v2 — connector reports ready when tokens present."
            ),
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "Google credentials not configured", "setup": self.setup_docs()}
        return {
            "ok": True,
            "stub": True,
            "action": payload.get("action") or "list",
            "message": "Google Mail stub — configure OAuth and extend connector for live Gmail.",
        }


class GoogleCalendarStub(Connector):
    name = "google_calendar"
    label = "Google Calendar (stub)"
    description = "Activates when GOOGLE_* tokens set. Stub until Calendar API wired."

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_refresh_token)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "enabled": self.is_available(),
            "available": self.is_available(),
            "setup": (
                "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN. "
                "Calendar API is stubbed in v2."
            ),
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "Google credentials not configured", "setup": self.setup_docs()}
        return {
            "ok": True,
            "stub": True,
            "action": payload.get("action") or "list_events",
            "message": "Google Calendar stub — ready for live API extension.",
        }


class GoogleChatStub(Connector):
    name = "google_chat"
    label = "Google Chat (stub)"
    description = "Chat connector stub; activates with GOOGLE_* tokens."

    def is_available(self) -> bool:
        s = get_settings()
        return bool(s.google_client_id and s.google_refresh_token)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "enabled": self.is_available(),
            "available": self.is_available(),
            "setup": "Set GOOGLE_* credentials. Chat API stubbed in v2.",
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available():
            return {"error": "Google credentials not configured"}
        return {"ok": True, "stub": True, "message": "Google Chat stub."}
