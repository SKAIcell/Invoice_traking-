
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


InvoiceApprovalRequestType = Literal["MANUAL", "BULK"]
InvoiceApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class InvoiceApprovalRequest(Base):
    __tablename__ = "invoice_approval_requests"

    __table_args__ = (
        CheckConstraint(
            "request_type IN ('MANUAL', 'BULK')",
            name="ck_invoice_approval_request_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_invoice_approval_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
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

    # Contains the manual invoice or the complete bulk invoice batch.
    invoice_data: Mapped[dict | list] = mapped_column(
        JSON,
        nullable=False,
    )

    # Attachment paths relative to the backend directory.
    order_copy_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    invoice_copy_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    excel_file_path: Mapped[str | None] = mapped_column(
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

    # IDs of official invoices created after successful approval.
    result_invoice_ids: Mapped[list | None] = mapped_column(
        JSON,
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
