"""Built-in agent tools + OpenAI tool schemas."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from grok_org_os.config import get_settings
from grok_org_os.models import (
    Agent,
    AgentRole,
    AgentStatus,
    Approval,
    ApprovalStatus,
    Channel,
    Message,
    Task,
    TaskStatus,
    utcnow,
)

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Post a message to the current channel (or specified channel_id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "channel_id": {"type": "integer"},
                    "parent_id": {"type": "integer", "description": "Optional reply parent message id"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a task, optionally assign by assignee_id or assignee_hint (ops/research/comms).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assignee_id": {"type": "integer"},
                    "assignee_hint": {"type": "string"},
                    "channel_id": {"type": "integer"},
                    "parent_task_id": {"type": "integer"},
                    "run": {"type": "boolean", "description": "Whether to queue assignee to run (default false for subtasks created mid-loop)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_task",
            "description": "Hand off a task to another agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "to_agent_id": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["task_id", "to_agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_channel",
            "description": "Read recent messages from a channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List agents in the organisation.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "http_fetch",
            "description": "Fetch a public URL (web connector) and return truncated text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_list",
            "description": "List files in the sandboxed workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "Read a text file from the sandboxed workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "Write a text file into the sandboxed workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": "Request human CEO approval; pauses sensitive actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "related_task_id": {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    },
]


class ToolContext:
    def __init__(
        self,
        db: Session,
        agent: Agent,
        *,
        channel: Optional[Channel] = None,
        task: Optional[Task] = None,
        organisation_id: Optional[int] = None,
        created_task_ids: Optional[list[int]] = None,
    ) -> None:
        self.db = db
        self.agent = agent
        self.channel = channel
        self.task = task
        self.organisation_id = organisation_id or agent.organisation_id
        self.created_task_ids = created_task_ids if created_task_ids is not None else []
        self.pending_approval: Approval | None = None


class ToolExecutor:
    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    def __call__(self, name: str, args: dict[str, Any]) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = handler(**{k: v for k, v in args.items() if not k.startswith("_")})
            if not isinstance(result, str):
                return json.dumps(result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %s failed", name)
            return json.dumps({"error": str(exc)})

    def _resolve_channel(self, channel_id: int | None = None) -> Channel | None:
        if channel_id:
            return self.ctx.db.get(Channel, channel_id)
        return self.ctx.channel

    def _safe_workspace(self, rel: str = ".") -> Path:
        root = get_settings().workspace_path()
        target = (root / (rel or ".")).resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError("Path escapes workspace sandbox")
        return target

    def _tool_send_message(
        self,
        content: str,
        channel_id: int | None = None,
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        channel = self._resolve_channel(channel_id)
        if channel is None:
            return {"error": "No channel"}
        msg = Message(
            channel_id=channel.id,
            agent_id=self.ctx.agent.id,
            content=content,
            parent_id=parent_id,
        )
        self.ctx.db.add(msg)
        self.ctx.db.commit()
        self.ctx.db.refresh(msg)
        return {"ok": True, "message_id": msg.id, "channel_id": channel.id}

    def _tool_create_task(
        self,
        title: str,
        description: str | None = None,
        assignee_id: int | None = None,
        assignee_hint: str | None = None,
        channel_id: int | None = None,
        parent_task_id: int | None = None,
        run: bool = False,
    ) -> dict[str, Any]:
        db = self.ctx.db
        assignee: Agent | None = None
        if assignee_id:
            assignee = db.get(Agent, assignee_id)
        elif assignee_hint:
            hint = assignee_hint.lower()
            agents = (
                db.query(Agent)
                .filter(Agent.organisation_id == self.ctx.organisation_id)
                .all()
            )
            for a in agents:
                name = (a.name or "").lower()
                if hint in name or (a.team and hint in (a.team.name or "").lower()):
                    assignee = a
                    break
        channel = self._resolve_channel(channel_id)
        parent_id = parent_task_id or (self.ctx.task.id if self.ctx.task else None)
        task = Task(
            organisation_id=self.ctx.organisation_id,
            title=title,
            description=description,
            status=TaskStatus.assigned if assignee else TaskStatus.pending,
            assignee_id=assignee.id if assignee else None,
            channel_id=channel.id if channel else None,
            parent_task_id=parent_id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        self.ctx.created_task_ids.append(task.id)
        if channel and assignee:
            note = Message(
                channel_id=channel.id,
                agent_id=self.ctx.agent.id,
                content=f"Assigned subtask #{task.id} to {assignee.name}: {title}",
            )
            db.add(note)
            db.commit()
        return {
            "ok": True,
            "task_id": task.id,
            "assignee_id": assignee.id if assignee else None,
            "run_requested": run,
        }

    def _tool_handoff_task(
        self, task_id: int, to_agent_id: int, note: str | None = None
    ) -> dict[str, Any]:
        db = self.ctx.db
        task = db.get(Task, task_id)
        to_agent = db.get(Agent, to_agent_id)
        if not task or not to_agent:
            return {"error": "Task or agent not found"}
        task.status = TaskStatus.handed_off
        db.add(task)
        db.commit()
        task.assignee_id = to_agent.id
        task.status = TaskStatus.assigned
        db.add(task)
        db.commit()
        channel = task.channel or self.ctx.channel
        if channel:
            msg = f"Handing off task #{task.id} to {to_agent.name}."
            if note:
                msg += f" Note: {note}"
            db.add(
                Message(channel_id=channel.id, agent_id=self.ctx.agent.id, content=msg)
            )
            db.commit()
        return {"ok": True, "task_id": task.id, "assignee_id": to_agent.id}

    def _tool_read_channel(
        self, channel_id: int | None = None, limit: int = 20
    ) -> dict[str, Any]:
        channel = self._resolve_channel(channel_id)
        if channel is None:
            return {"error": "No channel"}
        limit = max(1, min(int(limit or 20), 100))
        rows = (
            self.ctx.db.query(Message)
            .filter(Message.channel_id == channel.id)
            .order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        rows = list(reversed(rows))
        return {
            "channel_id": channel.id,
            "messages": [
                {
                    "id": m.id,
                    "agent_id": m.agent_id,
                    "content": m.content[:2000],
                    "parent_id": m.parent_id,
                }
                for m in rows
            ],
        }

    def _tool_list_agents(self) -> dict[str, Any]:
        agents = (
            self.ctx.db.query(Agent)
            .filter(Agent.organisation_id == self.ctx.organisation_id)
            .all()
        )
        return {
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role.value if hasattr(a.role, "value") else str(a.role),
                    "is_human": a.is_human,
                    "status": a.status,
                    "team": a.team.name if a.team else None,
                }
                for a in agents
            ]
        }

    def _tool_http_fetch(self, url: str, max_chars: int = 4000) -> dict[str, Any]:
        from grok_org_os.connectors.registry import get_connector

        web = get_connector("web")
        if web is None or not web.is_available():
            # direct fallback
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(url)
                text = resp.text[: max(100, min(int(max_chars or 4000), 50000))]
                return {"status_code": resp.status_code, "url": str(resp.url), "body": text}
        return web.invoke({"action": "fetch", "url": url, "max_chars": max_chars})

    def _tool_fs_list(self, path: str = ".") -> dict[str, Any]:
        target = self._safe_workspace(path)
        if not target.exists():
            return {"error": "Path not found", "path": str(path)}
        if target.is_file():
            return {"path": path, "type": "file", "size": target.stat().st_size}
        entries = []
        for child in sorted(target.iterdir())[:200]:
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"path": path, "entries": entries}

    def _tool_fs_read(self, path: str, max_chars: int = 8000) -> dict[str, Any]:
        target = self._safe_workspace(path)
        if not target.is_file():
            return {"error": "Not a file"}
        data = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": data[: max(100, min(int(max_chars or 8000), 100000))]}

    def _tool_fs_write(self, path: str, content: str) -> dict[str, Any]:
        target = self._safe_workspace(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": path, "bytes": len(content.encode("utf-8"))}

    def _tool_request_approval(
        self,
        title: str,
        description: str | None = None,
        related_task_id: int | None = None,
    ) -> dict[str, Any]:
        db = self.ctx.db
        approval = Approval(
            organisation_id=self.ctx.organisation_id,
            requester_agent_id=self.ctx.agent.id,
            title=title,
            description=description,
            status=ApprovalStatus.pending,
            related_task_id=related_task_id
            or (self.ctx.task.id if self.ctx.task else None),
        )
        db.add(approval)
        if self.ctx.task:
            self.ctx.task.status = TaskStatus.awaiting_approval
            db.add(self.ctx.task)
        self.ctx.agent.status = AgentStatus.waiting_approval.value
        db.add(self.ctx.agent)
        db.commit()
        db.refresh(approval)
        self.ctx.pending_approval = approval
        channel = self.ctx.channel
        if channel:
            db.add(
                Message(
                    channel_id=channel.id,
                    agent_id=self.ctx.agent.id,
                    content=f"⏳ Approval requested #{approval.id}: {title}",
                )
            )
            db.commit()
        return {
            "ok": True,
            "approval_id": approval.id,
            "status": "pending",
            "message": "Paused for human CEO approval",
        }
