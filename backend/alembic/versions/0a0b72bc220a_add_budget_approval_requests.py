"""add budget approval requests

Revision ID: 0a0b72bc220a
Revises: 7932f95d4f95
"""

from alembic import op
import sqlalchemy as sa


revision = "0a0b72bc220a"
down_revision = "7932f95d4f95"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "budget_approval_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=True),
        sa.Column("request_type", sa.String(length=10), nullable=False),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("financial_year", sa.String(length=9), nullable=False),
        sa.Column("budget_type", sa.String(length=5), nullable=False),
        sa.Column("planned_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("approved_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
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
            "budget_type IN ('OPEX', 'CAPEX')",
            name="ck_budget_approval_budget_type",
        ),
        sa.CheckConstraint(
            "request_type IN ('CREATE', 'UPDATE')",
            name="ck_budget_approval_request_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_budget_approval_status",
        ),
        sa.CheckConstraint(
            "approved_amount <= planned_amount",
            name="ck_budget_approval_amount_limit",
        ),
        sa.CheckConstraint(
            "approved_amount >= 0",
            name="ck_budget_approval_amount_positive",
        ),
        sa.CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_approval_planned_positive",
        ),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["budgets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
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
        "ix_budget_approval_requests_budget_id",
        "budget_approval_requests",
        ["budget_id"],
    )
    op.create_index(
        "ix_budget_approval_requests_financial_year",
        "budget_approval_requests",
        ["financial_year"],
    )
    op.create_index(
        "ix_budget_approval_requests_status",
        "budget_approval_requests",
        ["status"],
    )


def downgrade():
    op.drop_index(
        "ix_budget_approval_requests_status",
        table_name="budget_approval_requests",
    )
    op.drop_index(
        "ix_budget_approval_requests_financial_year",
        table_name="budget_approval_requests",
    )
    op.drop_index(
        "ix_budget_approval_requests_budget_id",
        table_name="budget_approval_requests",
    )
    op.drop_table("budget_approval_requests")
