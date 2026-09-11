from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from grok_org_os.api.deps import get_db
from grok_org_os.models import Agent, Channel, Message
from grok_org_os.schemas import MessageCreate, MessageRead

router = APIRouter(prefix="/messages", tags=["messages"])


def _to_read(msg: Message) -> MessageRead:
    agent = msg.agent
    return MessageRead(
        id=msg.id,
        channel_id=msg.channel_id,
        agent_id=msg.agent_id,
        content=msg.content,
        created_at=msg.created_at,
        agent_name=agent.name if agent else None,
        agent_role=agent.role if agent else None,
    )


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageCreate, db: Session = Depends(get_db)) -> MessageRead:
    if not db.get(Channel, payload.channel_id):
        raise HTTPException(status_code=404, detail="Channel not found")
    if not db.get(Agent, payload.agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    msg = Message(
        channel_id=payload.channel_id,
        agent_id=payload.agent_id,
        content=payload.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    msg = (
        db.query(Message)
        .options(joinedload(Message.agent))
        .filter(Message.id == msg.id)
        .one()
    )
    return _to_read(msg)


@router.get("", response_model=list[MessageRead])
def list_messages(
    channel_id: int | None = None, db: Session = Depends(get_db)
) -> list[MessageRead]:
    q = db.query(Message).options(joinedload(Message.agent))
    if channel_id is not None:
        q = q.filter(Message.channel_id == channel_id)
    return [_to_read(m) for m in q.order_by(Message.id).all()]


@router.get("/{message_id}", response_model=MessageRead)
def get_message(message_id: int, db: Session = Depends(get_db)) -> MessageRead:
    msg = (
        db.query(Message)
        .options(joinedload(Message.agent))
        .filter(Message.id == message_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return _to_read(msg)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: int, db: Session = Depends(get_db)) -> None:
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
