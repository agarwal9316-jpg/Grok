from __future__ import annotations

from typing import Any

import httpx

from grok_org_os.config import get_settings
from grok_org_os.connectors.base import Connector


class WebhookConnector(Connector):
    name = "webhook"
    label = "Webhook (outbound)"
    description = "POST JSON to WEBHOOK_URL when set."

    def is_available(self) -> bool:
        return bool(get_settings().webhook_url.strip())

    def status(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "name": self.name,
            "label": self.label,
            "enabled": self.is_available(),
            "available": self.is_available(),
            "setup": "Set WEBHOOK_URL in .env / settings to enable outbound webhooks.",
            "url_set": bool(s.webhook_url.strip()),
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = payload.get("url") or get_settings().webhook_url
        if not url:
            return {"error": "WEBHOOK_URL not configured"}
        body = payload.get("body") or payload
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=body)
            return {"status_code": resp.status_code, "body": resp.text[:2000]}
