from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from grok_org_os.api.deps import get_db
from grok_org_os.models import Organisation
from grok_org_os.schemas import OrganisationCreate, OrganisationRead, OrganisationUpdate

router = APIRouter(prefix="/orgs", tags=["organisations"])


@router.post("", response_model=OrganisationRead, status_code=status.HTTP_201_CREATED)
def create_org(payload: OrganisationCreate, db: Session = Depends(get_db)) -> Organisation:
    existing = db.query(Organisation).filter(Organisation.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Organisation name already exists")
    org = Organisation(name=payload.name, description=payload.description)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=list[OrganisationRead])
def list_orgs(db: Session = Depends(get_db)) -> list[Organisation]:
    return db.query(Organisation).order_by(Organisation.id).all()


@router.get("/{org_id}", response_model=OrganisationRead)
def get_org(org_id: int, db: Session = Depends(get_db)) -> Organisation:
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.patch("/{org_id}", response_model=OrganisationRead)
def update_org(
    org_id: int, payload: OrganisationUpdate, db: Session = Depends(get_db)
) -> Organisation:
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(org, k, v)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(org_id: int, db: Session = Depends(get_db)) -> None:
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    db.delete(org)
    db.commit()
