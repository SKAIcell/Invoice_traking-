
"""add budget approval copy attachments

Revision ID: e3749d0d51a9
Revises: c9d4f2a71b63
Create Date: 2026-11-12 16:16:13.763560
"""

from alembic import op
import sqlalchemy as sa


revision = "e3749d0d51a9"
down_revision = "c9d4f2a71b63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "budget_approval_requests",
        sa.Column(
            "approval_copy_path",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "budgets",
        sa.Column(
            "approval_copy_path",
            sa.String(length=500),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("budgets", "approval_copy_path")
    op.drop_column("budget_approval_requests", "approval_copy_path")
