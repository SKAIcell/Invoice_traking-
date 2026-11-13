
"""add invoice approval requests

Revision ID: 48cd4508eeba
Revises: 06ad6a17ea02
Create Date: 2026-11-04 15:48:05.201777
"""

from alembic import op
import sqlalchemy as sa


revision = "48cd4508eeba"
down_revision = "06ad6a17ea02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("request_type", sa.String(length=10), nullable=False),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("invoice_data", sa.JSON(), nullable=False),
        sa.Column("order_copy_path", sa.String(length=500), nullable=False),
        sa.Column("invoice_copy_path", sa.String(length=500), nullable=True),
        sa.Column("excel_file_path", sa.String(length=500), nullable=True),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("result_invoice_ids", sa.JSON(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("approval_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "approval_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "approval_token_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "request_type IN ('MANUAL', 'BULK')",
            name="ck_invoice_approval_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_invoice_approval_status",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_token_hash"),
    )

    op.create_index(
        op.f("ix_invoice_approval_requests_order_id"),
        "invoice_approval_requests",
        ["order_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_invoice_approval_requests_status"),
        "invoice_approval_requests",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_invoice_approval_requests_status"),
        table_name="invoice_approval_requests",
    )

    op.drop_index(
        op.f("ix_invoice_approval_requests_order_id"),
        table_name="invoice_approval_requests",
    )

    op.drop_table("invoice_approval_requests")
