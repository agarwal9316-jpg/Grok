from __future__ import annotations

from typing import Any

from grok_org_os.connectors.base import Connector
from grok_org_os.connectors.files import FilesConnector
from grok_org_os.connectors.google_stubs import (
    GoogleCalendarStub,
    GoogleChatStub,
    GoogleMailStub,
)
from grok_org_os.connectors.rest import RestConnector
from grok_org_os.connectors.smtp_email import SmtpEmailConnector
from grok_org_os.connectors.web import WebConnector
from grok_org_os.connectors.webhook import WebhookConnector

_REGISTRY: dict[str, Connector] = {}
_ENABLED: dict[str, bool] = {}


def register(connector: Connector) -> None:
    _REGISTRY[connector.name] = connector
    _ENABLED.setdefault(connector.name, True)


def register_builtins() -> None:
    if _REGISTRY:
        return
    for c in (
        FilesConnector(),
        WebConnector(),
        WebhookConnector(),
        SmtpEmailConnector(),
        RestConnector(),
        GoogleMailStub(),
        GoogleCalendarStub(),
        GoogleChatStub(),
    ):
        register(c)


def get_connector(name: str) -> Connector | None:
    register_builtins()
    return _REGISTRY.get(name)


def list_connectors() -> list[dict[str, Any]]:
    register_builtins()
    out = []
    for name, c in _REGISTRY.items():
        st = c.status()
        enabled = _ENABLED.get(name, True)
        st["enabled"] = enabled and st.get("available", True)
        st["user_enabled"] = enabled
        out.append(st)
    return out


def set_connector_enabled(name: str, enabled: bool) -> dict[str, Any]:
    register_builtins()
    if name not in _REGISTRY:
        raise KeyError(name)
    _ENABLED[name] = enabled
    st = _REGISTRY[name].status()
    st["user_enabled"] = enabled
    st["enabled"] = enabled and st.get("available", True)
    return st
