from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.order import Order
from app.models.party import Party
from app.models.budget import Budget

from app.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    validate_fy_date,
)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


def validate_party(db, party_id, order_type):
    party = db.get(Party, party_id)

    if party is None:
        raise HTTPException(404, "Party not found")

    expected = "VENDOR" if order_type == "PO" else "CUSTOMER"

    if (party.party_type or "").strip().upper() != expected:
        raise HTTPException(
            422,
            f"{order_type} requires a {expected}",
        )

    if not party.is_active:
        raise HTTPException(422, "Party is inactive")

    return party


def get_committed_budget(db, budget_id, exclude_id=None):
    query = db.query(
        func.coalesce(func.sum(Order.amount), 0)
    ).filter(
        Order.budget_id == budget_id,
        Order.order_type == "PO",
        Order.status != "CANCELLED",
    )

    if exclude_id is not None:
        query = query.filter(Order.id != exclude_id)

    return Decimal(str(query.scalar()))


@router.post(
    "",
    response_model=OrderResponse,
    status_code=201,
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):
    budget = None

    if payload.order_type == "PO":
        budget = (
            db.query(Budget)
            .filter(Budget.id == payload.budget_id)
            .with_for_update()
            .one_or_none()
        )

        if budget is None:
            raise HTTPException(404, "Budget not found")

        if budget.financial_year != payload.financial_year:
            raise HTTPException(
                422, "Budget financial year mismatch"
            )

    validate_party(db, payload.party_id, payload.order_type)

    existing = db.query(Order).filter(
        Order.order_type == payload.order_type,
        Order.order_number == payload.order_number,
    ).first()

    if existing:
        raise HTTPException(409, "Order number already exists")

    if budget is not None:
        committed = get_committed_budget(db, budget.id)
        available = budget.approved_amount - committed

        if payload.amount > available:
            raise HTTPException(
                422,
                detail={
                    "message": "Insufficient approved budget",
                    "available": str(available),
                    "requested": str(payload.amount),
                },
            )

    order = Order(
        **payload.model_dump(),
        status="OPEN",
    )

    db.add(order)

    try:
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate or invalid order")

    return order


@router.get(
    "/search",
    response_model=list[OrderResponse],
)
def search_orders(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
):
    q = q.strip()

    if not q:
        raise HTTPException(422, "Search text required")

    return (
        db.query(Order)
        .filter(Order.order_number.ilike(f"%{q}%"))
        .order_by(Order.id.desc())
        .limit(100)
        .all()
    )


@router.get(
    "",
    response_model=list[OrderResponse],
)
def list_orders(
    order_type: str | None = None,
    financial_year: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Order)

    if order_type:
        order_type = order_type.upper()

        if order_type not in ("PO", "SO"):
            raise HTTPException(422, "Invalid order type")

        query = query.filter(Order.order_type == order_type)

    if financial_year:
        query = query.filter(
            Order.financial_year == financial_year
        )

    return query.order_by(Order.id.desc()).limit(100).all()


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    return order


@router.patch(
    "/{order_id}",
    response_model=OrderResponse,
)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(400, "No changes provided")

    if (
        ("amount" in changes and changes["amount"] is None)
        or ("order_date" in changes and changes["order_date"] is None)
    ):
        raise HTTPException(
            422, "Amount and order date cannot be null"
        )

    original = db.get(Order, order_id)

    if original is None:
        raise HTTPException(404, "Order not found")

    budget = None

    if original.order_type == "PO":
        budget = (
            db.query(Budget)
            .filter(Budget.id == original.budget_id)
            .with_for_update()
            .one_or_none()
        )

        if budget is None:
            raise HTTPException(409, "Linked budget missing")

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .one_or_none()
    )

    if order is None:
        raise HTTPException(404, "Order not found")

    if order.status != "OPEN":
        raise HTTPException(
            409, "Only OPEN orders can be edited"
        )

    new_date = changes.get("order_date", order.order_date)

    try:
        validate_fy_date(order.financial_year, new_date)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    new_amount = changes.get("amount", order.amount)

    if budget is not None:
        committed = get_committed_budget(
            db, budget.id, exclude_id=order.id
        )

        if committed + new_amount > budget.approved_amount:
            raise HTTPException(
                422, "Updated order exceeds approved budget"
            )

    for field, value in changes.items():
        setattr(order, field, value)

    try:
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Order update failed")

    return order
