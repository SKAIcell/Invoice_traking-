
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

    # Outstanding balances for both PURCHASE and SERVICE invoices
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
        .filter(
            Invoice.invoice_type.in_(["PURCHASE", "SERVICE"])
        )
        .scalar()
    )

    # Initialize invoice status counts
    status_counts = {
        "PAID": 0,
        "PART_PAID": 0,
        "OVERDUE": 0,
        "ON_HOLD": 0,
        "UNPAID": 0,
    }

    # Fetch invoices with their actual payment totals
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
        .filter(
            Invoice.invoice_type.in_(["PURCHASE", "SERVICE"])
        )
        .all()
    )

    today = date.today()

    for invoice, total_paid in invoices:
        amount = Decimal(str(invoice.amount or 0))
        paid = Decimal(str(total_paid or 0))

        balance = amount - paid

        if invoice.status == "ON_HOLD":
            status = "ON_HOLD"
        elif balance <= 0:
            status = "PAID"
        elif invoice.due_date and invoice.due_date < today:
            status = "OVERDUE"
        elif paid > 0:
            status = "PART_PAID"
        else:
            status = "UNPAID"

        status_counts[status] += 1

    # IMPORTANT: Return the response expected by DashboardPage.tsx
    return {
        "total_vendor_order_amount": str(
            Decimal(str(total_orders or 0))
        ),
        "total_balance_payout_due": str(
            Decimal(str(total_due or 0))
        ),
        "invoice_status_counts": status_counts,
    }
