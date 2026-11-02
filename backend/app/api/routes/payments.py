from app.core.security import require_roles
from decimal import Decimal
from sqlalchemy import func


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.schemas.payment import PaymentCreate, PaymentResponse


router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=201,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)

def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == payload.invoice_id)
        .with_for_update()
        .one_or_none()
    )

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found",
        )

    total_paid = (
        db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        )
        .filter(Payment.invoice_id == invoice.id)
        .scalar()
    )

    total_paid = Decimal(str(total_paid))
    invoice_amount = Decimal(str(invoice.amount))
    balance_due = invoice_amount - total_paid

    if payload.amount > balance_due:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Payment exceeds outstanding balance",
                "balance_due": str(max(balance_due, Decimal("0.00"))),
                "requested_amount": str(payload.amount),
            },
        )

    payment = Payment(**payload.model_dump())
    db.add(payment)

    try:
        db.commit()
        db.refresh(payment)
    except Exception:
        db.rollback()
        raise

    return payment

@router.get(
    "",
    response_model=list[PaymentResponse],
)
def list_payments(
    invoice_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Payment)

    if invoice_id is not None:
        if invoice_id <= 0:
            raise HTTPException(
                status_code=422,
                detail="Invoice ID must be positive",
            )

        if db.get(Invoice, invoice_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Invoice not found",
            )

        query = query.filter(
            Payment.invoice_id == invoice_id
        )

    return query.order_by(Payment.id.desc()).limit(100).all()
