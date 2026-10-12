from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.party import Party
from app.schemas.party import PartyCreate, PartyResponse


router = APIRouter(
    prefix="/parties",
    tags=["Vendors and Customers"],
)


@router.post(
    "",
    response_model=PartyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_party(
    payload: PartyCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(Party).where(
            Party.party_type == payload.party_type,
            Party.code == payload.code,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This code already exists for this party type.",
        )

    party = Party(**payload.model_dump())
    db.add(party)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail="This code already exists for this party type.",
            ) from None

        raise HTTPException(
            status_code=400,
            detail="The record violates a database validation rule.",
        ) from None

    db.refresh(party)
    return party


@router.get("", response_model=list[PartyResponse])
def list_parties(
    party_type: Literal["VENDOR", "CUSTOMER"] | None = None,
    q: str | None = Query(default=None, max_length=200),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    statement = select(Party)

    if party_type:
        statement = statement.where(
            Party.party_type == party_type
        )

    if is_active is not None:
        statement = statement.where(
            Party.is_active == is_active
        )

    if q and q.strip():
        search = q.strip()

        statement = statement.where(
            or_(
                Party.code.icontains(search, autoescape=True),
                Party.name.icontains(search, autoescape=True),
                Party.email.icontains(search, autoescape=True),
                Party.phone.icontains(search, autoescape=True),
            )
        )

    statement = (
        statement
        .order_by(Party.name, Party.id)
        .offset(offset)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


@router.get("/{party_id}", response_model=PartyResponse)
def get_party(
    party_id: int,
    db: Session = Depends(get_db),
):
    party = db.get(Party, party_id)

    if party is None:
        raise HTTPException(
            status_code=404,
            detail="Vendor or customer not found.",
        )

    return party
