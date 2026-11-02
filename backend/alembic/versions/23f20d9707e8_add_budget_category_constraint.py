
"""add budget category constraint

Revision ID: 23f20d9707e8
Revises: 6dc209ead8da
Create Date: 2026-10-28 11:58:11.348280
"""

from alembic import op


revision = "23f20d9707e8"
down_revision = "6dc209ead8da"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_budget_category_by_type",
        "budgets",
        """
        (
            budget_type = 'OPEX'
            AND name IN (
                'AMC & IT CONSUMABLES',
                'APPLICATION SUBSCRIPTION SUPPORT',
                'INFRASTRUCTURE MANAGED SERVICES & CLOUD',
                'NETWORK CONNECTIVITY'
            )
        )
        OR
        (
            budget_type = 'CAPEX'
            AND name = 'CAPEX'
        )
        """,
    )


def downgrade():
    op.drop_constraint(
        "ck_budget_category_by_type",
        "budgets",
        type_="check",
    )
