from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Channel, Organisation
from grok_org_os.schemas import ChannelCreate, ChannelRead, ChannelUpdate

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post("", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def create_channel(payload: ChannelCreate, db: Session = Depends(get_db)) -> Channel:
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(status_code=404, detail="Organisation not found")
    channel = Channel(
        organisation_id=payload.organisation_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("", response_model=list[ChannelRead])
def list_channels(
    organisation_id: int | None = None, db: Session = Depends(get_db)
) -> list[Channel]:
    q = db.query(Channel)
    if organisation_id is not None:
        q = q.filter(Channel.organisation_id == organisation_id)
    return q.order_by(Channel.id).all()


@router.get("/{channel_id}", response_model=ChannelRead)
def get_channel(channel_id: int, db: Session = Depends(get_db)) -> Channel:
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.patch("/{channel_id}", response_model=ChannelRead)
def update_channel(
    channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_db)
) -> Channel:
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(channel, k, v)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: int, db: Session = Depends(get_db)) -> None:
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(channel)
    db.commit()
