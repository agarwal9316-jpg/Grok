from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Organisation, Team
from grok_org_os.schemas import TeamCreate, TeamRead, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamCreate, db: Session = Depends(get_db)) -> Team:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    team = Team(
        organisation_id=payload.organisation_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.get("", response_model=list[TeamRead])
def list_teams(
    organisation_id: int | None = None, db: Session = Depends(get_db)
) -> list[Team]:
    q = db.query(Team)
    if organisation_id is not None:
        q = q.filter(Team.organisation_id == organisation_id)
    return q.order_by(Team.id).all()


@router.get("/{team_id}", response_model=TeamRead)
def get_team(team_id: int, db: Session = Depends(get_db)) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.patch("/{team_id}", response_model=TeamRead)
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db)) -> Team:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(team, k, v)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: int, db: Session = Depends(get_db)) -> None:
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(team)
    db.commit()
