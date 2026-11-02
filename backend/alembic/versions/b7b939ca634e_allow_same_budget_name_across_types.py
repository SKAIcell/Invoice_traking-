"""allow same budget name across types

Revision ID: b7b939ca634e
Revises: 3fae3a5b82b2
Create Date: 2026-10-13 15:55:34.104157
"""

from alembic import op

revision = "b7b939ca634e"
down_revision = "3fae3a5b82b2"
branch_labels = None
depends_on = None


def upgrade():
    # Replace the old uniqueness rule with one that includes budget_type.
    op.drop_constraint(
        "uq_budget_fy_name",
        "budgets",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_budget_fy_name_type",
        "budgets",
        ["financial_year", "name", "budget_type"],
    )


def downgrade():
    # Restore the original uniqueness rule if rolling back.
    op.drop_constraint(
        "uq_budget_fy_name_type",
        "budgets",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_budget_fy_name",
        "budgets",
        ["financial_year", "name"],
    )