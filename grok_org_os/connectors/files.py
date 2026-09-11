from __future__ import annotations

from pathlib import Path
from typing import Any

from grok_org_os.config import get_settings
from grok_org_os.connectors.base import Connector


class FilesConnector(Connector):
    name = "files"
    label = "Files (workspace)"
    description = "Sandboxed filesystem under workspace/. Always available."

    def is_available(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        root = get_settings().workspace_path()
        return {
            "name": self.name,
            "label": self.label,
            "enabled": True,
            "available": True,
            "workspace": str(root),
            "setup": "Files are stored under the workspace/ directory.",
        }

    def _safe(self, rel: str) -> Path:
        root = get_settings().workspace_path()
        target = (root / (rel or ".")).resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError("Path escapes workspace")
        return target

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = (payload.get("action") or "list").lower()
        path = payload.get("path") or "."
        if action == "list":
            target = self._safe(path)
            if not target.exists():
                return {"error": "not found"}
            if target.is_file():
                return {"type": "file", "path": path, "size": target.stat().st_size}
            return {
                "entries": [
                    {"name": c.name, "type": "dir" if c.is_dir() else "file"}
                    for c in sorted(target.iterdir())
                ]
            }
        if action == "read":
            data = self._safe(path).read_text(encoding="utf-8", errors="replace")
            return {"content": data[: int(payload.get("max_chars") or 8000)]}
        if action == "write":
            target = self._safe(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            content = payload.get("content") or ""
            target.write_text(content, encoding="utf-8")
            return {"ok": True, "path": path}
        return {"error": f"Unknown action {action}"}
