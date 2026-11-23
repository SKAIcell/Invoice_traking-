"""add order subcategory and approved by

Revision ID: 092a8b2d1947
Revises: 8eeb4a3b48a8
Create Date: 2026-11-18 16:37:10.546192
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "092a8b2d1947"
down_revision = "8eeb4a3b48a8"
branch_labels = None
depends_on = None


def upgrade():
    # Add OPEX subcategory reference to orders
    op.add_column(
        "orders",
        sa.Column(
            "budget_subcategory_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Add order approver
    op.add_column(
        "orders",
        sa.Column(
            "approved_by",
            sa.String(length=200),
            nullable=True,
        ),
    )

    # Ensure budget is mandatory
    op.alter_column(
        "orders",
        "budget_id",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )

    # Index for subcategory lookup
    op.create_index(
        "ix_orders_budget_subcategory_id",
        "orders",
        ["budget_subcategory_id"],
        unique=False,
    )

    # Foreign key to OPEX budget subcategories
    op.create_foreign_key(
        "fk_orders_budget_subcategory_id_budget_subcategories",
        "orders",
        "budget_subcategories",
        ["budget_subcategory_id"],
        ["id"],
    )


def downgrade():
    # Remove foreign key
    op.drop_constraint(
        "fk_orders_budget_subcategory_id_budget_subcategories",
        "orders",
        type_="foreignkey",
    )

    # Remove index
    op.drop_index(
        "ix_orders_budget_subcategory_id",
        table_name="orders",
    )

    # Restore previous budget_id nullability
    op.alter_column(
        "orders",
        "budget_id",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )

    # Remove new columns
    op.drop_column("orders", "approved_by")
    op.drop_column("orders", "budget_subcategory_id")