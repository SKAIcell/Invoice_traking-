
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.order import Order
from app.models.invoice import Invoice
from app.models.payment import Payment


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
):
    # Total value of vendor purchase orders
    total_orders = (
        db.query(
            func.coalesce(func.sum(Order.amount), 0)
        )
        .filter(Order.order_type == "PO")
        .scalar()
    )

    # Total payments recorded against each invoice
    payment_totals = (
        db.query(
            Payment.invoice_id.label("invoice_id"),
            func.sum(Payment.amount).label("total_paid"),
        )
        .group_by(Payment.invoice_id)
        .subquery()
    )

    # Outstanding balances for purchase invoices
    remaining_balance = (
        Invoice.amount
        - func.coalesce(payment_totals.c.total_paid, 0)
    )

    total_due = (
        db.query(
            func.coalesce(
                func.sum(
                    func.greatest(remaining_balance, 0)
                ),
                0,
            )
        )
        .outerjoin(
            payment_totals,
            Invoice.id == payment_totals.c.invoice_id,
        )
        .filter(Invoice.invoice_type == "PURCHASE")
        .scalar()
    )

    # Fetch purchase invoices with their recorded payments
    invoices = (
        db.query(
            Invoice,
            func.coalesce(
                payment_totals.c.total_paid, 0
            ).label("total_paid"),
        )
        .outerjoin(
            payment_totals,
            Invoice.id == payment_totals.c.invoice_id,
        )
        .filter(Invoice.invoice_type == "PURCHASE")
        .all()
    )

    status_counts = {
        "PAID": 0,
        "PART_PAID": 0,
        "OVERDUE": 0,
        "ON_HOLD": 0,
        "UNPAID": 0,
    }

    today = date.today()

    for invoice, paid_value in invoices:
        amount = Decimal(str(invoice.amount))
        total_paid = Decimal(str(paid_value))
        balance_due = amount - total_paid

        # Workflow status takes precedence over payment status
        if (invoice.status or "").strip().upper() == "ON_HOLD":
            status = "ON_HOLD"
        elif balance_due <= 0:
            status = "PAID"
        elif invoice.due_date < today:
            status = "OVERDUE"
        elif total_paid > 0:
            status = "PART_PAID"
        else:
            status = "UNPAID"

        status_counts[status] += 1

    return {
        "total_vendor_order_amount": str(
            Decimal(str(total_orders))
        ),
        "total_balance_payout_due": str(
            Decimal(str(total_due))
        ),
        "invoice_status_counts": status_counts,
    }
