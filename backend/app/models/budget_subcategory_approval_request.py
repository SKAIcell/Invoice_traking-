
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


SubcategoryRequestType = Literal["CREATE", "UPDATE"]
SubcategoryApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class BudgetSubcategoryApprovalRequest(Base):
    __tablename__ = "budget_subcategory_approval_requests"

    __table_args__ = (
        CheckConstraint(
            "request_type IN ('CREATE', 'UPDATE')",
            name="ck_budget_subcategory_request_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_budget_subcategory_request_status",
        ),
        CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_subcategory_request_planned_positive",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0",
            name="ck_budget_subcategory_request_approved_positive",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount <= planned_amount",
            name="ck_budget_subcategory_request_approved_limit",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_budget_subcategory_request_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Parent OPEX category
    budget_id: Mapped[int] = mapped_column(
        ForeignKey("budgets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # NULL for CREATE requests until approval creates the allocation.
    subcategory_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_subcategories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    request_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )

    # Selected predefined name or manually entered name.
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Requested target allocation, not the increase difference.
    planned_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    # Amount decided by IT_HEAD.
    approved_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    approval_copy_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    requested_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Secure email approval token
    approval_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
    )

    approval_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    approval_token_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def has_approval_copy(self) -> bool:
        return bool(self.approval_copy_path)
