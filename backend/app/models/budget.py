from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Budget(Base):
    __tablename__ = "budgets"

    __table_args__ = (
        UniqueConstraint(
    "financial_year",
    "name",
    "budget_type",
    name="uq_budget_fy_name_type",
),CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_planned_positive",
        ),
        CheckConstraint(
            "approved_amount >= 0",
            name="ck_budget_approved_positive",
        ),
        CheckConstraint(
            "approved_amount <= planned_amount",
            name="ck_budget_approved_limit",
        ),
        CheckConstraint(
            "REGEXP_LIKE(financial_year, '^[0-9]{4}-[0-9]{4}$')",
            name="ck_budget_fy_format",
        ),
        CheckConstraint(
            "CAST(SUBSTRING(financial_year, 6, 4) AS UNSIGNED) = "
            "CAST(SUBSTRING(financial_year, 1, 4) AS UNSIGNED) + 1",
            name="ck_budget_fy_sequence",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_budget_name",
        ),
        CheckConstraint(
            "budget_type IN ('OPEX', 'CAPEX')",
            name="ck_budget_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    financial_year: Mapped[str] = mapped_column(
        String(9),
        nullable=False,
        index=True,
    )

    budget_type: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
    )

    planned_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    approved_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )