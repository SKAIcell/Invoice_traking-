
"""add order and invoice document paths

Revision ID: 7932f95d4f95
Revises: 0d5c632cdc49
"""

from alembic import op
import sqlalchemy as sa


revision = "7932f95d4f95"
down_revision = "0d5c632cdc49"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("order_file_path", sa.String(length=500), nullable=True),
    )

    op.add_column(
        "invoices",
        sa.Column("invoice_file_path", sa.String(length=500), nullable=True),
    )


def downgrade():
    op.drop_column("invoices", "invoice_file_path")
    op.drop_column("orders", "order_file_path")
