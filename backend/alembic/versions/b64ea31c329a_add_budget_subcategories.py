
"""add budget subcategories

Revision ID: b64ea31c329a
Revises: 48cd4508eeba
Create Date: 2026-11-06 15:13:02.097441
"""

from alembic import op
import sqlalchemy as sa


revision = "b64ea31c329a"
down_revision = "48cd4508eeba"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "budget_subcategories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("budget_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "planned_amount",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
        ),
        sa.Column(
            "approved_amount",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "approved_amount <= planned_amount",
            name="ck_budget_subcategory_approved_limit",
        ),
        sa.CheckConstraint(
            "approved_amount >= 0",
            name="ck_budget_subcategory_approved_positive",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_budget_subcategory_name",
        ),
        sa.CheckConstraint(
            "planned_amount >= 0",
            name="ck_budget_subcategory_planned_positive",
        ),
        sa.ForeignKeyConstraint(
            ["budget_id"],
            ["budgets.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "budget_id",
            "name",
            name="uq_budget_subcategory_budget_name",
        ),
    )

    op.create_index(
        op.f("ix_budget_subcategories_budget_id"),
        "budget_subcategories",
        ["budget_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_budget_subcategories_budget_id"),
        table_name="budget_subcategories",
    )

    op.drop_table("budget_subcategories")
