"""Make budget approval amount nullable

Revision ID: 06ad6a17ea02
Revises: 0a0b72bc220a
Create Date: 2026-11-04 13:03:55.966127
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "06ad6a17ea02"
down_revision = "0a0b72bc220a"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "budget_approval_requests",
        "approved_amount",
        existing_type=mysql.DECIMAL(precision=18, scale=2),
        existing_nullable=False,
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "budget_approval_requests",
        "approved_amount",
        existing_type=mysql.DECIMAL(precision=18, scale=2),
        existing_nullable=True,
        nullable=False,
    )
