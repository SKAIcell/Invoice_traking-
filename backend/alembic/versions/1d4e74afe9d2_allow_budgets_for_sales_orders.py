
"""Allow budgets for sales orders.

Revision ID: 1d4e74afe9d2
Revises: 23f20d9707e8
"""

from alembic import op


revision = "1d4e74afe9d2"
down_revision = "23f20d9707e8"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_orders_budget_type",
        "orders",
        type_="check",
    )

    op.create_check_constraint(
        "ck_orders_budget_type",
        "orders",
        "budget_id IS NOT NULL",
    )


def downgrade():
    op.drop_constraint(
        "ck_orders_budget_type",
        "orders",
        type_="check",
    )

    op.create_check_constraint(
        "ck_orders_budget_type",
        "orders",
        """
        (order_type = 'PO' AND budget_id IS NOT NULL)
        OR
        (order_type = 'SO' AND budget_id IS NULL)
        """,
    )
