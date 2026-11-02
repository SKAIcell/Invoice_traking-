
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    Text,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint(
            "order_type",
            "order_number",
            name="uq_orders_type_number",
        ),
        CheckConstraint(
            "order_type IN ('PO', 'SO')",
            name="ck_orders_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_orders_positive_amount",
        ),
        CheckConstraint(
            "budget_id IS NOT NULL",
            name="ck_orders_budget_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    order_type = Column(String(2), nullable=False)
    order_number = Column(String(64), nullable=False)

    party_id = Column(
        Integer,
        ForeignKey("parties.id"),
        nullable=False,
        index=True,
    )

    budget_id = Column(
        Integer,
        ForeignKey("budgets.id"),
        nullable=False,
        index=True,
    )

    financial_year = Column(String(9), nullable=False)
    order_date = Column(Date, nullable=False)
    order_period = Column(String(100), nullable=True)
    location = Column(String(200), nullable=True)

    amount = Column(Numeric(18, 2), nullable=False)

    description = Column(Text, nullable=True)

    # Uploaded document paths
    order_file_path = Column(String(500), nullable=True)
    approval_file_path = Column(String(500), nullable=True)

    status = Column(
        String(20),
        nullable=False,
        default="OPEN",
    )

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

    party = relationship("Party")
    budget = relationship("Budget")

    # Invoices linked to this order
    invoices = relationship("Invoice", back_populates="order")
