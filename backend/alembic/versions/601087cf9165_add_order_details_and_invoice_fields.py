
"""add order details and invoice fields

Revision ID: 601087cf9165
Revises: aaeaf8af5985
"""

from alembic import op
import sqlalchemy as sa


revision = "601087cf9165"
down_revision = "aaeaf8af5985"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("order_period", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("location", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("approval_file_path", sa.String(length=500), nullable=True),
    )

    op.add_column(
        "invoices",
        sa.Column("period", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("location", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("remarks", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("invoices", "remarks")
    op.drop_column("invoices", "location")
    op.drop_column("invoices", "period")

    op.drop_column("orders", "approval_file_path")
    op.drop_column("orders", "location")
    op.drop_column("orders", "order_period")
