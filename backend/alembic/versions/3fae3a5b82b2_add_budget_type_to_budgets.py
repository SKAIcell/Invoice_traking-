"""add budget type to budgets

Revision ID: 3fae3a5b82b2
Revises: 17ca04cf366c
Create Date: 2026-10-13 15:22:52.987799
"""

from alembic import op
import sqlalchemy as sa


revision = "3fae3a5b82b2"
down_revision = "17ca04cf366c"
branch_labels = None
depends_on = None


def upgrade():
    # Add the new column with a temporary default so existing rows are preserved.
    op.add_column(
        "budgets",
        sa.Column(
            "budget_type",
            sa.String(length=5),
            nullable=False,
            server_default="OPEX",
        ),
    )

    # Existing budgets are classified as OPEX for this migration.
    op.alter_column(
        "budgets",
        "budget_type",
        existing_type=sa.String(length=5),
        nullable=False,
        server_default=None,
    )

    # Only OPEX and CAPEX are valid budget types.
    op.create_check_constraint(
        "ck_budget_type_valid",
        "budgets",
        "budget_type IN ('OPEX', 'CAPEX')",
    )


def downgrade():
    op.drop_constraint(
        "ck_budget_type_valid",
        "budgets",
        type_="check",
    )
    op.drop_column("budgets", "budget_type")