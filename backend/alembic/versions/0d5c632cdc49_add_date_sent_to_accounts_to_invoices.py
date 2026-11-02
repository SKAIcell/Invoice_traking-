
"""add date sent to accounts to invoices

Revision ID: 0d5c632cdc49
Revises: 1d4e74afe9d2
Create Date: 2026-10-30 11:03:20.573964
"""

from alembic import op
import sqlalchemy as sa

revision = '0d5c632cdc49'
down_revision = '1d4e74afe9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'invoices',
        sa.Column(
            'date_sent_to_accounts',
            sa.Date(),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column('invoices', 'date_sent_to_accounts')
