
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


ApprovalRequestType = Literal["CREATE", "UPDATE"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class BudgetApprovalRequest(Base):
    __tablename__ = "budget_approval_requests"

    __table_args__ = (
        CheckConstraint(
            "request_type IN ('CREATE', 'UPDATE')",
            name="ck_budget_approval_request_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_budget_approval_status",
        ),
        CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_approval_planned_positive",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount >= 0",
            name="ck_budget_approval_amount_positive",
        ),
        CheckConstraint(
            "approved_amount IS NULL OR approved_amount <= planned_amount",
            name="ck_budget_approval_amount_limit",
        ),
        CheckConstraint(
            "budget_type IN ('OPEX', 'CAPEX')",
            name="ck_budget_approval_budget_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Existing budget for UPDATE requests.
    # NULL for CREATE requests until approval creates the budget.
    budget_id: Mapped[int | None] = mapped_column(
        ForeignKey("budgets.id", ondelete="RESTRICT"),
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

    # Proposed budget values
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

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

    # Assigned by IT Head during approval.
    # NULL while pending or rejected.
    approved_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    # Optional uploaded budget approval copy.
    approval_copy_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Requester and approver
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

    # Optional remarks from IT Head
    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Secure email approval token hash
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
