from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Agent, Channel, Organisation, Task, TaskStatus
from grok_org_os.schemas import (
    TaskAssign,
    TaskCreate,
    TaskHandoff,
    TaskRead,
    TaskUpdate,
)
from grok_org_os.task_runner import TaskRunner

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    if payload.assignee_id is not None and not db.get(Agent, payload.assignee_id):
        raise HTTPException(status_code=404, detail="Assignee not found")
    if payload.channel_id is not None and not db.get(Channel, payload.channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    task = Task(
        organisation_id=payload.organisation_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        assignee_id=payload.assignee_id,
        channel_id=payload.channel_id,
        parent_task_id=payload.parent_task_id,
    )
    if payload.assignee_id is not None and payload.status == TaskStatus.pending:
        task.status = TaskStatus.assigned
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
def list_tasks(
    organisation_id: int | None = None,
    status_filter: TaskStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[Task]:
    q = db.query(Task)
    if organisation_id is not None:
        q = q.filter(Task.organisation_id == organisation_id)
    if status_filter is not None:
        q = q.filter(Task.status == status_filter)
    return q.order_by(Task.id).all()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(task, k, v)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)) -> None:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()


@router.post("/{task_id}/assign", response_model=TaskRead)
def assign_task(
    task_id: int,
    payload: TaskAssign,
    run: bool = Query(True, description="Run AI agent after assign"),
    db: Session = Depends(get_db),
) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    agent = db.get(Agent, payload.assignee_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Assignee not found")
    channel = None
    if payload.channel_id is not None:
        channel = db.get(Channel, payload.channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")
    elif task.channel_id:
        channel = db.get(Channel, task.channel_id)

    runner = TaskRunner(db)
    return runner.assign_task(task, agent, channel, run=run)


@router.post("/{task_id}/handoff", response_model=TaskRead)
def handoff_task(
    task_id: int,
    payload: TaskHandoff,
    run: bool = Query(True),
    db: Session = Depends(get_db),
) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    agent = db.get(Agent, payload.to_agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Target agent not found")
    runner = TaskRunner(db)
    return runner.handoff(task, agent, note=payload.note, run=run)


@router.post("/{task_id}/run", response_model=TaskRead)
def run_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.assignee_id:
        raise HTTPException(status_code=400, detail="Task has no assignee")
    runner = TaskRunner(db)
    return runner.run_task(task_id)
