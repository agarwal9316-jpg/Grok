from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import (
    Agent,
    AgentStatus,
    Approval,
    ApprovalStatus,
    Message,
    Organisation,
    Task,
    TaskStatus,
)
from grok_org_os.schemas import ApprovalCreate, ApprovalDecision, ApprovalRead
from grok_org_os.task_runner import TaskRunner

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _to_read(a: Approval) -> ApprovalRead:
    return ApprovalRead(
        id=a.id,
        organisation_id=a.organisation_id,
        requester_agent_id=a.requester_agent_id,
        title=a.title,
        description=a.description,
        status=a.status,
        decision_note=a.decision_note,
        related_task_id=a.related_task_id,
        created_at=a.created_at,
        resolved_at=a.resolved_at,
        requester_name=a.requester.name if a.requester else None,
    )


@router.get("", response_model=list[ApprovalRead])
def list_approvals(
    organisation_id: int | None = None,
    status_filter: ApprovalStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[ApprovalRead]:
    q = db.query(Approval)
    if organisation_id is not None:
        q = q.filter(Approval.organisation_id == organisation_id)
    if status_filter is not None:
        q = q.filter(Approval.status == status_filter)
    return [_to_read(a) for a in q.order_by(Approval.id.desc()).all()]


@router.post("", response_model=ApprovalRead, status_code=status.HTTP_201_CREATED)
def create_approval(payload: ApprovalCreate, db: Session = Depends(get_db)) -> ApprovalRead:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    a = Approval(
        organisation_id=payload.organisation_id,
        title=payload.title,
        description=payload.description,
        requester_agent_id=payload.requester_agent_id,
        related_task_id=payload.related_task_id,
        status=ApprovalStatus.pending,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _to_read(a)


@router.post("/{approval_id}/approve", response_model=ApprovalRead)
def approve(
    approval_id: int,
    payload: ApprovalDecision | None = None,
    db: Session = Depends(get_db),
) -> ApprovalRead:
    a = db.get(Approval, approval_id)
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    if a.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Already resolved")
    a.status = ApprovalStatus.approved
    a.decision_note = (payload.decision_note if payload else None) or "Approved by CEO"
    a.resolved_at = datetime.now(timezone.utc)
    db.add(a)
    if a.requester_agent_id:
        agent = db.get(Agent, a.requester_agent_id)
        if agent:
            agent.status = AgentStatus.idle.value
            db.add(agent)
    if a.related_task_id:
        task = db.get(Task, a.related_task_id)
        if task and task.status == TaskStatus.awaiting_approval:
            task.status = TaskStatus.assigned
            db.add(task)
            db.commit()
            if task.assignee and not task.assignee.is_human:
                TaskRunner(db).run_task(task.id)
            else:
                db.commit()
        else:
            db.commit()
    else:
        db.commit()
    db.refresh(a)
    # notify channel via related task
    if a.related_task_id:
        task = db.get(Task, a.related_task_id)
        if task and task.channel_id and a.requester_agent_id:
            db.add(
                Message(
                    channel_id=task.channel_id,
                    agent_id=a.requester_agent_id,
                    content=f"✅ Approval #{a.id} approved: {a.title}",
                )
            )
            db.commit()
    return _to_read(a)


@router.post("/{approval_id}/reject", response_model=ApprovalRead)
def reject(
    approval_id: int,
    payload: ApprovalDecision | None = None,
    db: Session = Depends(get_db),
) -> ApprovalRead:
    a = db.get(Approval, approval_id)
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    if a.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Already resolved")
    a.status = ApprovalStatus.rejected
    a.decision_note = (payload.decision_note if payload else None) or "Rejected by CEO"
    a.resolved_at = datetime.now(timezone.utc)
    db.add(a)
    if a.requester_agent_id:
        agent = db.get(Agent, a.requester_agent_id)
        if agent:
            agent.status = AgentStatus.idle.value
            db.add(agent)
    if a.related_task_id:
        task = db.get(Task, a.related_task_id)
        if task:
            task.status = TaskStatus.failed
            task.result = f"Rejected: {a.decision_note}"
            db.add(task)
    db.commit()
    db.refresh(a)
    return _to_read(a)
