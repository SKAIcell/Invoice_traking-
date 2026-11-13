
"""add OPEX subcategory approval copies

Revision ID: 8eeb4a3b48a8
Revises: e3749d0d51a9
Create Date: 2026-11-12 16:43:48.198597
"""

from alembic import op
import sqlalchemy as sa


revision = "8eeb4a3b48a8"
down_revision = "e3749d0d51a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "budget_subcategories",
        sa.Column(
            "approval_copy_path",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "budget_subcategory_approval_requests",
        sa.Column(
            "approval_copy_path",
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column(
        "budget_subcategory_approval_requests",
        "approval_copy_path",
    )

    op.drop_column(
        "budget_subcategories",
        "approval_copy_path",
    )
