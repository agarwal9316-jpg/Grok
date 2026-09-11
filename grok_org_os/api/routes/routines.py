from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Agent, Channel, Organisation, Routine
from grok_org_os.scheduler import fire_routine, schedule_routine, unschedule_routine
from grok_org_os.schemas import RoutineCreate, RoutineRead, RoutineUpdate

router = APIRouter(prefix="/routines", tags=["routines"])


@router.get("", response_model=list[RoutineRead])
def list_routines(
    organisation_id: int | None = None, db: Session = Depends(get_db)
) -> list[Routine]:
    q = db.query(Routine)
    if organisation_id is not None:
        q = q.filter(Routine.organisation_id == organisation_id)
    return q.order_by(Routine.id).all()


@router.post("", response_model=RoutineRead, status_code=status.HTTP_201_CREATED)
def create_routine(payload: RoutineCreate, db: Session = Depends(get_db)) -> Routine:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    if not payload.cron and not payload.every_seconds:
        raise HTTPException(status_code=400, detail="Provide cron or every_seconds")
    if payload.target_agent_id and not db.get(Agent, payload.target_agent_id):
        raise HTTPException(status_code=404, detail="Target agent not found")
    if payload.channel_id and not db.get(Channel, payload.channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    r = Routine(
        organisation_id=payload.organisation_id,
        name=payload.name,
        prompt=payload.prompt,
        cron=payload.cron,
        every_seconds=payload.every_seconds,
        target_agent_id=payload.target_agent_id,
        channel_id=payload.channel_id,
        enabled=payload.enabled,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    schedule_routine(r)
    return r


@router.patch("/{routine_id}", response_model=RoutineRead)
def update_routine(
    routine_id: int, payload: RoutineUpdate, db: Session = Depends(get_db)
) -> Routine:
    r = db.get(Routine, routine_id)
    if not r:
        raise HTTPException(status_code=404, detail="Routine not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.add(r)
    db.commit()
    db.refresh(r)
    schedule_routine(r)
    return r


@router.delete("/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routine(routine_id: int, db: Session = Depends(get_db)) -> None:
    r = db.get(Routine, routine_id)
    if not r:
        raise HTTPException(status_code=404, detail="Routine not found")
    unschedule_routine(routine_id)
    db.delete(r)
    db.commit()


@router.post("/{routine_id}/run", response_model=RoutineRead)
def run_routine_now(routine_id: int, db: Session = Depends(get_db)) -> Routine:
    r = db.get(Routine, routine_id)
    if not r:
        raise HTTPException(status_code=404, detail="Routine not found")
    fire_routine(routine_id)
    db.refresh(r)
    return r
