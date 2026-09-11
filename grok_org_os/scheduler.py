"""Cron-like routines scheduler (APScheduler) persisted in SQLite."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from grok_org_os import db as db_module
from grok_org_os.models import Agent, Channel, Message, Routine, Task, TaskStatus

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
    return _scheduler


def start_scheduler() -> BackgroundScheduler:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        reload_routines()
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def _job_id(routine_id: int) -> str:
    return f"routine-{routine_id}"


def fire_routine(routine_id: int) -> None:
    db = db_module.SessionLocal()
    try:
        routine = db.get(Routine, routine_id)
        if not routine or not routine.enabled:
            return
        agent = routine.target_agent
        channel = routine.channel
        if channel is None:
            channel = (
                db.query(Channel)
                .filter(Channel.organisation_id == routine.organisation_id)
                .first()
            )
        if agent is None:
            agent = (
                db.query(Agent)
                .filter(
                    Agent.organisation_id == routine.organisation_id,
                    Agent.is_human.is_(False),
                )
                .first()
            )
        # Post to channel
        if channel and agent:
            db.add(
                Message(
                    channel_id=channel.id,
                    agent_id=agent.id,
                    content=f"⏰ Routine '{routine.name}' fired:\n{routine.prompt}",
                )
            )
        # Create task for target agent
        if agent:
            task = Task(
                organisation_id=routine.organisation_id,
                title=f"[Routine] {routine.name}",
                description=routine.prompt,
                status=TaskStatus.assigned,
                assignee_id=agent.id,
                channel_id=channel.id if channel else None,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            if not agent.is_human:
                try:
                    from grok_org_os.runtime import get_runtime

                    get_runtime().submit_task(task.id)
                except Exception:  # noqa: BLE001
                    logger.exception("Could not submit routine task %s", task.id)
        routine.last_run_at = datetime.now(timezone.utc)
        db.add(routine)
        db.commit()
        logger.info("Routine %s fired", routine_id)
    except Exception:  # noqa: BLE001
        logger.exception("Routine %s failed", routine_id)
    finally:
        db.close()


def schedule_routine(routine: Routine) -> None:
    sched = get_scheduler()
    jid = _job_id(routine.id)
    try:
        sched.remove_job(jid)
    except Exception:  # noqa: BLE001
        pass
    if not routine.enabled:
        return
    if routine.every_seconds and routine.every_seconds > 0:
        trigger = IntervalTrigger(seconds=routine.every_seconds)
    elif routine.cron:
        # 5-field cron
        parts = routine.cron.split()
        if len(parts) != 5:
            logger.warning("Invalid cron for routine %s: %s", routine.id, routine.cron)
            return
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    else:
        return
    sched.add_job(
        fire_routine,
        trigger=trigger,
        id=jid,
        args=[routine.id],
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )


def unschedule_routine(routine_id: int) -> None:
    sched = get_scheduler()
    try:
        sched.remove_job(_job_id(routine_id))
    except Exception:  # noqa: BLE001
        pass


def reload_routines() -> None:
    db = db_module.SessionLocal()
    try:
        routines = db.query(Routine).all()
        for r in routines:
            schedule_routine(r)
    finally:
        db.close()
