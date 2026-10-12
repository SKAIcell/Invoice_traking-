from sqlalchemy import (
    Column, Integer, String, Date, DateTime,
    Numeric, ForeignKey, Text, CheckConstraint,
    Index, func, text
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    invoice_type = Column(String(10), nullable=False)
    invoice_number = Column(String(100), nullable=False)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    party_id = Column(
        Integer,
        ForeignKey("parties.id"),
        nullable=False,
        index=True,
    )

    financial_year = Column(String(9), nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    amount = Column(Numeric(18, 2), nullable=False)

    status = Column(
        String(20), nullable=False, default="DRAFT"
    )

    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    order = relationship("Order")
    party = relationship("Party")

    __table_args__ = (
        CheckConstraint(
            "invoice_type IN ('PURCHASE', 'SALES')",
            name="ck_invoice_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_invoice_positive_amount",
        ),
        CheckConstraint(
            "due_date >= invoice_date",
            name="ck_invoice_due_date",
        ),
        Index(
            "uq_purchase_invoice_vendor_number",
            "party_id",
            "invoice_number",
            unique=True,
            postgresql_where=text(
                "invoice_type = 'PURCHASE'"
            ),
        ),
        Index(
            "uq_sales_invoice_fy_number",
            "financial_year",
            "invoice_number",
            unique=True,
            postgresql_where=text(
                "invoice_type = 'SALES'"
            ),
        ),
    )
