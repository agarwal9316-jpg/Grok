from __future__ import annotations

from typing import Any

import httpx

from grok_org_os.config import get_settings
from grok_org_os.connectors.base import Connector


class RestConnector(Connector):
    name = "rest"
    label = "Generic REST"
    description = "Call arbitrary REST endpoints. Uses REST_BASE_URL / REST_API_TOKEN when set."

    def is_available(self) -> bool:
        return True  # can always call absolute URLs

    def status(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "name": self.name,
            "label": self.label,
            "enabled": True,
            "available": True,
            "setup": "Optional REST_BASE_URL and REST_API_TOKEN in .env for default API target.",
            "base_url_set": bool(s.rest_base_url.strip()),
        }

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        s = get_settings()
        method = (payload.get("method") or "GET").upper()
        path = payload.get("path") or payload.get("url") or ""
        if path.startswith("http"):
            url = path
        else:
            base = (payload.get("base_url") or s.rest_base_url).rstrip("/")
            if not base:
                return {"error": "Provide url or configure REST_BASE_URL"}
            url = f"{base}/{path.lstrip('/')}"
        headers = dict(payload.get("headers") or {})
        token = payload.get("token") or s.rest_api_token
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.request(
                method, url, headers=headers, json=payload.get("json"), params=payload.get("params")
            )
            return {
                "status_code": resp.status_code,
                "url": str(resp.url),
                "body": resp.text[:8000],
            }
