from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Agent, Channel, Message
from grok_org_os.schemas import MessageCreate, MessageRead

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageCreate, db: Session = Depends(get_db)) -> Message:
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
    return msg


@router.get("", response_model=list[MessageRead])
def list_messages(
    channel_id: int | None = None, db: Session = Depends(get_db)
) -> list[Message]:
    q = db.query(Message)
    if channel_id is not None:
        q = q.filter(Message.channel_id == channel_id)
    return q.order_by(Message.id).all()


@router.get("/{message_id}", response_model=MessageRead)
def get_message(message_id: int, db: Session = Depends(get_db)) -> Message:
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(message_id: int, db: Session = Depends(get_db)) -> None:
    msg = db.get(Message, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
