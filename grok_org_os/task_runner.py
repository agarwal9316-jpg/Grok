"""Task runner: CoS + specialists via tool-calling agent runtime (with legacy fallback)."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from grok_org_os.llm import LLMClient, get_llm_client
from grok_org_os.models import Agent, AgentRole, Channel, Message, Task, TaskStatus
from grok_org_os.runtime import get_runtime

logger = logging.getLogger(__name__)


class TaskRunner:
    def __init__(self, db: Session, llm: Optional[LLMClient] = None) -> None:
        self.db = db
        self.llm = llm or get_llm_client()

    def assign_task(
        self,
        task: Task,
        assignee: Agent,
        channel: Optional[Channel] = None,
        *,
        run: bool = True,
    ) -> Task:
        task.assignee_id = assignee.id
        task.status = TaskStatus.assigned
        if channel is not None:
            task.channel_id = channel.id
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        if channel is not None:
            self.post_message(channel, assignee, f"Accepted task #{task.id}: {task.title}")

        if run and not assignee.is_human:
            return self.run_task(task.id)
        return task

    def handoff(
        self,
        task: Task,
        to_agent: Agent,
        note: Optional[str] = None,
        *,
        run: bool = True,
    ) -> Task:
        from_agent = task.assignee
        task.status = TaskStatus.handed_off
        self.db.add(task)
        self.db.commit()

        channel = task.channel
        if channel and from_agent:
            msg = f"Handing off task #{task.id} to {to_agent.name}."
            if note:
                msg += f" Note: {note}"
            self.post_message(channel, from_agent, msg)

        return self.assign_task(task, to_agent, channel, run=run)

    def run_task(self, task_id: int) -> Task:
        task = self.db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        assignee = task.assignee
        if assignee is None:
            raise ValueError(f"Task {task_id} has no assignee")

        if assignee.is_human:
            return task

        # Prefer tool-calling multi-agent runtime (works with live OpenAI + mock tools)
        try:
            runtime = get_runtime()
            runtime.llm = self.llm
            return runtime.run_agent_on_task(self.db, task, assignee)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Runtime tool path failed (%s); legacy fallback", exc)
            return self._legacy_run(task, assignee)

    def _legacy_run(self, task: Task, assignee: Agent) -> Task:
        task.status = TaskStatus.in_progress
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        try:
            if assignee.role == AgentRole.chief_of_staff:
                return self._run_chief_of_staff(task, assignee)
            if assignee.role == AgentRole.specialist:
                return self._run_specialist(task, assignee)
            if assignee.role == AgentRole.ceo:
                return self._run_ceo_ack(task, assignee)
            return task
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s failed", task.id)
            task.status = TaskStatus.failed
            task.result = str(exc)
            self.db.add(task)
            self.db.commit()
            self.db.refresh(task)
            if task.channel:
                self.post_message(
                    task.channel, assignee, f"Task #{task.id} failed: {exc}"
                )
            return task

    def run_pending_for_org(self, organisation_id: int, max_steps: int = 20) -> list[Task]:
        processed: list[Task] = []
        for _ in range(max_steps):
            tasks = (
                self.db.query(Task)
                .filter(
                    Task.organisation_id == organisation_id,
                    Task.status.in_([TaskStatus.assigned]),
                )
                .all()
            )
            runnable = [t for t in tasks if t.assignee and not t.assignee.is_human]
            if not runnable:
                break
            for task in runnable:
                result = self.run_task(task.id)
                processed.append(result)
        return processed

    def post_message(
        self,
        channel: Channel,
        agent: Agent,
        content: str,
        *,
        parent_id: int | None = None,
    ) -> Message:
        msg = Message(
            channel_id=channel.id,
            agent_id=agent.id,
            content=content,
            parent_id=parent_id,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def _run_chief_of_staff(self, task: Task, cos: Agent) -> Task:
        channel = task.channel
        specialists = (
            self.db.query(Agent)
            .filter(
                Agent.organisation_id == task.organisation_id,
                Agent.role == AgentRole.specialist,
                Agent.is_human.is_(False),
            )
            .all()
        )

        prompt = (
            f"Decompose the following organisational task into subtasks for Ops, Research, "
            f"and Comms specialists. Title: {task.title}\n"
            f"Description: {task.description or 'N/A'}\n"
            "Break down into clear subtasks and assign each to a specialist team."
        )
        messages = [
            {
                "role": "system",
                "content": cos.system_prompt
                or "You are the Chief of Staff. Coordinate teams and decompose work.",
            },
            {"role": "user", "content": prompt},
        ]
        plan = self.llm.chat(messages)

        if channel:
            self.post_message(
                channel, cos, f"Decomposition plan for task #{task.id}:\n{plan}"
            )

        created: list[Task] = []
        for specialist in specialists:
            team_name = specialist.team.name if specialist.team else specialist.name
            sub = Task(
                organisation_id=task.organisation_id,
                title=f"{team_name}: {task.title}",
                description=(
                    f"Subtask derived from parent #{task.id}.\n"
                    f"Focus area: {team_name}\n"
                    f"Parent description: {task.description or task.title}\n"
                    f"CoS plan excerpt:\n{plan}"
                ),
                status=TaskStatus.assigned,
                assignee_id=specialist.id,
                channel_id=task.channel_id,
                parent_task_id=task.id,
            )
            self.db.add(sub)
            self.db.commit()
            self.db.refresh(sub)
            if channel:
                self.post_message(
                    channel,
                    cos,
                    f"Assigned subtask #{sub.id} to {specialist.name} ({team_name}).",
                )
            created.append(sub)

        results: list[str] = []
        for sub in created:
            assert sub.assignee is not None
            done = self._run_specialist(sub, sub.assignee)
            if done.result:
                name = done.assignee.name if done.assignee else "?"
                results.append(f"- {name}: {done.result}")

        synth_messages = [
            {
                "role": "system",
                "content": cos.system_prompt
                or "You are the Chief of Staff. Synthesize team outputs for the CEO.",
            },
            {
                "role": "user",
                "content": (
                    f"Synthesize results for parent task '{task.title}':\n"
                    + "\n".join(results)
                ),
            },
        ]
        summary = self.llm.chat(synth_messages)
        task.result = summary
        task.status = TaskStatus.done
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        if channel:
            self.post_message(
                channel, cos, f"Executive summary for task #{task.id}:\n{summary}"
            )

        return task

    def _run_specialist(self, task: Task, agent: Agent) -> Task:
        channel = task.channel
        task.status = TaskStatus.in_progress
        self.db.add(task)
        self.db.commit()

        messages = [
            {
                "role": "system",
                "content": agent.system_prompt
                or f"You are specialist agent {agent.name}. Produce a concise useful result.",
            },
            {
                "role": "user",
                "content": (
                    f"Complete this task.\nTitle: {task.title}\n"
                    f"Description: {task.description or 'N/A'}"
                ),
            },
        ]
        result = self.llm.chat(messages)
        task.result = result
        task.status = TaskStatus.done
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        if channel:
            self.post_message(channel, agent, f"Completed task #{task.id}:\n{result}")

        return task

    def _run_ceo_ack(self, task: Task, ceo: Agent) -> Task:
        channel = task.channel
        messages = [
            {
                "role": "system",
                "content": ceo.system_prompt
                or "You are the CEO. Acknowledge and set direction.",
            },
            {
                "role": "user",
                "content": f"Review and acknowledge: {task.title}\n{task.description or ''}",
            },
        ]
        result = self.llm.chat(messages)
        task.result = result
        task.status = TaskStatus.done
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        if channel:
            self.post_message(channel, ceo, result)
        return task
