"""Multi-agent runtime: concurrent workers with LLM + tool loops."""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from sqlalchemy.orm import Session

from grok_org_os import db as db_module
from grok_org_os.llm import LLMClient, get_llm_client
from grok_org_os.models import Agent, AgentRole, AgentStatus, Channel, Task, TaskStatus
from grok_org_os.tools import TOOL_DEFINITIONS, ToolContext, ToolExecutor

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Process agent work with tool-calling LLM; supports concurrent execution."""

    def __init__(self, llm: Optional[LLMClient] = None, max_workers: int = 4) -> None:
        self.llm = llm or get_llm_client()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-worker")
        self._lock = threading.Lock()
        self._statuses: dict[int, str] = {}
        self._bg_task: asyncio.Task | None = None
        self._stop = threading.Event()

    def get_status(self, agent_id: int) -> str:
        return self._statuses.get(agent_id, AgentStatus.idle.value)

    def all_statuses(self, db: Session) -> list[dict]:
        agents = db.query(Agent).all()
        return [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role.value if hasattr(a.role, "value") else str(a.role),
                "status": self._statuses.get(a.id) or a.status or AgentStatus.idle.value,
                "is_human": a.is_human,
            }
            for a in agents
        ]

    def _set_status(self, db: Session, agent: Agent, status: str) -> None:
        self._statuses[agent.id] = status
        agent.status = status
        db.add(agent)
        db.commit()

    def run_agent_on_task(self, db: Session, task: Task, agent: Agent) -> Task:
        """Synchronous tool-calling turn for one agent/task (used by TaskRunner + workers)."""
        if agent.is_human:
            return task

        channel = task.channel
        self._set_status(db, agent, AgentStatus.thinking.value)
        task.status = TaskStatus.in_progress
        db.add(task)
        db.commit()

        created_ids: list[int] = []
        ctx = ToolContext(
            db, agent, channel=channel, task=task, created_task_ids=created_ids
        )
        executor = ToolExecutor(ctx)

        system = agent.system_prompt or f"You are agent {agent.name}."
        system += (
            "\nYou have tools. Use them to coordinate: send_message, create_task, "
            "handoff_task, read_channel, list_agents, http_fetch, fs_list/fs_read/fs_write, "
            "request_approval. Prefer tools over prose when taking action."
        )
        user = (
            f"Complete this organisational task.\n"
            f"Title: {task.title}\n"
            f"Description: {task.description or 'N/A'}\n"
        )
        if agent.role == AgentRole.chief_of_staff:
            user += (
                "Decompose into Ops/Research/Comms subtasks via create_task (with assignee_hint), "
                "post updates via send_message, then summarize."
            )

        def on_tool(name: str, _args: dict) -> None:
            self._set_status(db, agent, AgentStatus.tool.value)

        try:
            result = self.llm.chat_with_tools(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                TOOL_DEFINITIONS,
                executor,
                on_tool=on_tool,
                max_rounds=10,
            )
            if ctx.pending_approval:
                task.status = TaskStatus.awaiting_approval
                task.result = result or f"Awaiting approval #{ctx.pending_approval.id}"
                db.add(task)
                db.commit()
                db.refresh(task)
                return task

            task.result = result or task.result or "Done"
            task.status = TaskStatus.done
            db.add(task)
            db.commit()

            if channel and result:
                from grok_org_os.models import Message

                db.add(
                    Message(
                        channel_id=channel.id,
                        agent_id=agent.id,
                        content=f"Completed task #{task.id}:\n{result}",
                    )
                )
                db.commit()

            # Run newly created assigned specialist tasks (CoS spawn)
            for tid in list(created_ids):
                sub = db.get(Task, tid)
                if (
                    sub
                    and sub.assignee_id
                    and sub.status == TaskStatus.assigned
                    and sub.assignee
                    and not sub.assignee.is_human
                ):
                    self.run_agent_on_task(db, sub, sub.assignee)

            # CoS synthesize if we created subs
            if agent.role == AgentRole.chief_of_staff and created_ids:
                self._set_status(db, agent, AgentStatus.thinking.value)
                subs = [db.get(Task, i) for i in created_ids]
                lines = []
                for s in subs:
                    if s and s.result:
                        name = s.assignee.name if s.assignee else "?"
                        lines.append(f"- {name}: {s.result}")
                if lines:
                    summary = self.llm.chat(
                        [
                            {
                                "role": "system",
                                "content": agent.system_prompt
                                or "You are the Chief of Staff. Synthesize for the CEO.",
                            },
                            {
                                "role": "user",
                                "content": f"Synthesize results for '{task.title}':\n"
                                + "\n".join(lines),
                            },
                        ]
                    )
                    task.result = summary
                    db.add(task)
                    db.commit()
                    if channel:
                        from grok_org_os.models import Message

                        db.add(
                            Message(
                                channel_id=channel.id,
                                agent_id=agent.id,
                                content=f"Executive summary for task #{task.id}:\n{summary}",
                            )
                        )
                        db.commit()

            db.refresh(task)
            return task
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent %s task %s failed", agent.id, task.id)
            task.status = TaskStatus.failed
            task.result = str(exc)
            db.add(task)
            db.commit()
            db.refresh(task)
            return task
        finally:
            if agent.status != AgentStatus.waiting_approval.value:
                self._set_status(db, agent, AgentStatus.idle.value)

    def _ensure_pool(self) -> ThreadPoolExecutor:
        if self._pool is None or getattr(self._pool, "_shutdown", False):
            self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-worker")
        return self._pool

    def submit_task(self, task_id: int) -> None:
        """Run a task in the thread pool (concurrent workers)."""

        def _job() -> None:
            db = db_module.SessionLocal()
            try:
                task = db.get(Task, task_id)
                if not task or not task.assignee_id:
                    return
                agent = db.get(Agent, task.assignee_id)
                if not agent or agent.is_human:
                    return
                self.run_agent_on_task(db, task, agent)
            finally:
                db.close()

        self._ensure_pool().submit(_job)

    async def start_background_poller(self, interval: float = 2.0) -> None:
        """Poll for assigned AI tasks and run them concurrently."""
        self._stop.clear()

        async def _loop() -> None:
            while not self._stop.is_set():
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._claim_and_submit
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Background poller error")
                await asyncio.sleep(interval)

        self._bg_task = asyncio.create_task(_loop())

    def _claim_and_submit(self) -> None:
        """Claim assigned AI tasks atomically, then run concurrently."""
        db = db_module.SessionLocal()
        try:
            tasks = (
                db.query(Task)
                .filter(Task.status == TaskStatus.assigned)
                .limit(8)
                .all()
            )
            claimed: list[int] = []
            for task in tasks:
                if not task.assignee or task.assignee.is_human:
                    continue
                # Conditional update avoids double-run vs sync TaskRunner
                updated = (
                    db.query(Task)
                    .filter(Task.id == task.id, Task.status == TaskStatus.assigned)
                    .update(
                        {"status": TaskStatus.in_progress},
                        synchronize_session=False,
                    )
                )
                db.commit()
                if updated:
                    claimed.append(task.id)
            for tid in claimed:
                self.submit_task(tid)
        finally:
            db.close()

    def stop(self) -> None:
        self._stop.set()
        if self._bg_task:
            self._bg_task.cancel()
            self._bg_task = None
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._pool = None  # type: ignore[assignment]


_runtime: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def set_runtime(runtime: AgentRuntime | None) -> None:
    global _runtime
    _runtime = runtime
