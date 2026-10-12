from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.budget import Budget
from app.schemas.budget import (
    BudgetCreate,
    BudgetUpdate,
    BudgetResponse,
)

router = APIRouter(
    prefix="/budgets",
    tags=["Budgets"],
)


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=201,
)
def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(Budget)
        .filter(
            Budget.name == payload.name,
            Budget.financial_year == payload.financial_year,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Budget already exists for this FY",
        )

    budget = Budget(**payload.model_dump())

    db.add(budget)

    try:
        db.commit()
        db.refresh(budget)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Budget violates a database constraint",
        )

    return budget


@router.get(
    "",
    response_model=list[BudgetResponse],
)
def list_budgets(
    financial_year: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Budget)

    if financial_year:
        query = query.filter(
            Budget.financial_year == financial_year
        )

    return query.order_by(Budget.id.desc()).all()


@router.get(
    "/{budget_id}",
    response_model=BudgetResponse,
)
def get_budget(
    budget_id: int,
    db: Session = Depends(get_db),
):
    budget = db.get(Budget, budget_id)

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found",
        )

    return budget


@router.patch(
    "/{budget_id}",
    response_model=BudgetResponse,
)
def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
):
    budget = db.get(Budget, budget_id)

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found",
        )

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No fields provided",
        )

    if any(value is None for value in changes.values()):
        raise HTTPException(
            status_code=422,
            detail="Budget amounts cannot be null",
        )

    planned = changes.get(
        "planned_amount", budget.planned_amount
    )
    approved = changes.get(
        "approved_amount", budget.approved_amount
    )

    if approved > planned:
        raise HTTPException(
            status_code=422,
            detail="Approved budget exceeds planned budget",
        )

    for field, value in changes.items():
        setattr(budget, field, value)

    try:
        db.commit()
        db.refresh(budget)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Budget update violates a database constraint",
        )

    return budget
