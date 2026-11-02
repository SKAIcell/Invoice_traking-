
"""add budget type

Revision ID: 6dc209ead8da
Revises: 601087cf9165
"""

from alembic import op


revision = "6dc209ead8da"
down_revision = "601087cf9165"
branch_labels = None
depends_on = None


def upgrade():
    # budget_type already exists in the database.
    # This migration records the schema change in Alembic history.
    pass


def downgrade():
    # Keep the existing column; it predates this migration.
    pass
