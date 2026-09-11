from __future__ import annotations

from typing import Any

import httpx

from grok_org_os.connectors.base import Connector


class WebConnector(Connector):
    name = "web"
    label = "Web (HTTP fetch)"
    description = "Fetch public HTTP(S) URLs via httpx. Always available."

    def is_available(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "enabled": True,
            "available": True,
            "setup": "No configuration required.",
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = payload.get("url")
        if not url:
            return {"error": "url required"}
        max_chars = max(100, min(int(payload.get("max_chars") or 4000), 50000))
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(url)
            return {
                "status_code": resp.status_code,
                "url": str(resp.url),
                "headers": {"content-type": resp.headers.get("content-type")},
                "body": resp.text[:max_chars],
            }
