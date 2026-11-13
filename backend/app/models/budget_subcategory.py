
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BudgetSubcategory(Base):
    __tablename__ = "budget_subcategories"

    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "name",
            name="uq_budget_subcategory_budget_name",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_budget_subcategory_name",
        ),
        CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_subcategory_planned_positive",
        ),
        CheckConstraint(
            "approved_amount >= 0",
            name="ck_budget_subcategory_approved_positive",
        ),
        CheckConstraint(
            "approved_amount <= planned_amount",
            name="ck_budget_subcategory_approved_limit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    budget_id: Mapped[int] = mapped_column(
        ForeignKey("budgets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    planned_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    approved_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    approval_copy_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @property
    def has_approval_copy(self) -> bool:
        return bool(self.approval_copy_path)
