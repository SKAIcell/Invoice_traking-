
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    Text,
    CheckConstraint,
    Computed,
    Index,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    invoice_type = Column(String(20), nullable=False)
    invoice_number = Column(String(100), nullable=False)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False)

    financial_year = Column(String(9), nullable=False)

    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    # Date on which the invoice was sent to Accounts
    date_sent_to_accounts = Column(Date, nullable=True)

    amount = Column(Numeric(18, 2), nullable=False)

    status = Column(String(20), nullable=False, default="UNPAID")

    description = Column(Text, nullable=True)
    period = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    remarks = Column(Text, nullable=True)

    # Uploaded invoice document path
    invoice_file_path = Column(String(500), nullable=True)

    purchase_invoice_key = Column(
        String(300),
        Computed(
            "CASE WHEN invoice_type = 'PURCHASE' "
            "THEN CONCAT(party_id, '-', LOWER(TRIM(invoice_number))) "
            "ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )

    sales_invoice_key = Column(
        String(300),
        Computed(
            "CASE WHEN invoice_type = 'SALES' "
            "THEN CONCAT(financial_year, '-', LOWER(TRIM(invoice_number))) "
            "ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    order = relationship("Order", back_populates="invoices")
    party = relationship("Party", back_populates="invoices")
    payments = relationship(
        "Payment",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "invoice_type IN ('PURCHASE', 'SALES')",
            name="ck_invoice_type",
        ),
        CheckConstraint(
            "status IN ('UNPAID', 'PART_PAID', 'PAID', 'OVERDUE', 'ON_HOLD')",
            name="ck_invoice_status",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_invoice_amount_positive",
        ),
        Index(
            "uq_purchase_invoice_vendor_number",
            "party_id",
            "purchase_invoice_key",
            unique=True,
        ),
        Index(
            "uq_sales_invoice_fy_number",
            "sales_invoice_key",
            unique=True,
        ),
    )
