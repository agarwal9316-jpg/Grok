from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Agent, Organisation, Team
from grok_org_os.schemas import AgentCreate, AgentRead, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> Agent:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    if payload.team_id is not None and not db.get(Team, payload.team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    agent = Agent(
        organisation_id=payload.organisation_id,
        team_id=payload.team_id,
        name=payload.name,
        role=payload.role,
        is_human=payload.is_human,
        system_prompt=payload.system_prompt,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=list[AgentRead])
def list_agents(
    organisation_id: int | None = None, db: Session = Depends(get_db)
) -> list[Agent]:
    q = db.query(Agent)
    if organisation_id is not None:
        q = q.filter(Agent.organisation_id == organisation_id)
    return q.order_by(Agent.id).all()


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: int, db: Session = Depends(get_db)) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)
) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(agent, k, v)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, db: Session = Depends(get_db)) -> None:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
