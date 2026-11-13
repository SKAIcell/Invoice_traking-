
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

    invoice_type = Column(String(10), nullable=False)
    invoice_number = Column(String(100), nullable=False)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    party_id = Column(Integer, ForeignKey("parties.id"), nullable=False)

    financial_year = Column(String(9), nullable=False)

    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    date_sent_to_accounts = Column(Date, nullable=True)

    amount = Column(Numeric(18, 2), nullable=False)

    status = Column(String(20), nullable=False, default="UNPAID")

    description = Column(Text, nullable=True)
    period = Column(String(100), nullable=True)
    location = Column(String(200), nullable=True)
    remarks = Column(Text, nullable=True)

    invoice_file_path = Column(String(500), nullable=True)

    # Purchase invoice uniqueness is maintained per vendor.
    purchase_invoice_key = Column(
        String(100),
        Computed(
            "CASE WHEN invoice_type = 'PURCHASE' "
            "THEN invoice_number ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )

    # Service invoice uniqueness is maintained per financial year.
    service_invoice_key = Column(
        String(110),
        Computed(
            "CASE WHEN invoice_type = 'SERVICE' "
            "THEN CONCAT(financial_year, ':', invoice_number) "
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
            "invoice_type IN ('PURCHASE', 'SERVICE')",
            name="ck_invoice_type",
        ),
        CheckConstraint(
            "due_date >= invoice_date",
            name="ck_invoice_due_date",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_invoice_positive_amount",
        ),
        Index(
            "uq_purchase_invoice_vendor_number",
            "party_id",
            "purchase_invoice_key",
            unique=True,
        ),
        Index(
            "uq_service_invoice_fy_number",
            "service_invoice_key",
            unique=True,
        ),
    )
