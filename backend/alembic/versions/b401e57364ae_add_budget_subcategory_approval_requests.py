"""add budget subcategory approval requests

Revision ID: b401e57364ae
Revises: b64ea31c329a
Create Date: 2026-11-06 15:25:31.204901
"""

from alembic import op
import sqlalchemy as sa

revision = 'b401e57364ae'
down_revision = 'b64ea31c329a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'budget_subcategory_approval_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('budget_id', sa.Integer(), nullable=False),
        sa.Column('subcategory_id', sa.Integer(), nullable=True),
        sa.Column('request_type', sa.String(length=10), nullable=False),
        sa.Column(
            'status',
            sa.String(length=10),
            server_default='PENDING',
            nullable=False,
        ),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column(
            'planned_amount',
            sa.Numeric(precision=18, scale=2),
            nullable=False,
        ),
        sa.Column(
            'approved_amount',
            sa.Numeric(precision=18, scale=2),
            nullable=True,
        ),
        sa.Column('requested_by_id', sa.Integer(), nullable=False),
        sa.Column('decided_by_id', sa.Integer(), nullable=True),
        sa.Column(
            'requested_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('approval_token_hash', sa.String(length=64), nullable=True),
        sa.Column(
            'approval_token_expires_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            'approval_token_used_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "request_type IN ('CREATE', 'UPDATE')",
            name='ck_budget_subcategory_request_type',
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name='ck_budget_subcategory_request_status',
        ),
        sa.CheckConstraint(
            'approved_amount IS NULL OR approved_amount <= planned_amount',
            name='ck_budget_subcategory_request_approved_limit',
        ),
        sa.CheckConstraint(
            'approved_amount IS NULL OR approved_amount >= 0',
            name='ck_budget_subcategory_request_approved_positive',
        ),
        sa.CheckConstraint(
            'length(trim(name)) > 0',
            name='ck_budget_subcategory_request_name',
        ),
        sa.CheckConstraint(
            'planned_amount >= 0',
            name='ck_budget_subcategory_request_planned_positive',
        ),
        sa.ForeignKeyConstraint(
            ['budget_id'],
            ['budgets.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['decided_by_id'],
            ['users.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['requested_by_id'],
            ['users.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['subcategory_id'],
            ['budget_subcategories.id'],
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('approval_token_hash'),
    )

    op.create_index(
        op.f('ix_budget_subcategory_approval_requests_budget_id'),
        'budget_subcategory_approval_requests',
        ['budget_id'],
        unique=False,
    )

    op.create_index(
        op.f('ix_budget_subcategory_approval_requests_status'),
        'budget_subcategory_approval_requests',
        ['status'],
        unique=False,
    )

    op.create_index(
        op.f('ix_budget_subcategory_approval_requests_subcategory_id'),
        'budget_subcategory_approval_requests',
        ['subcategory_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f('ix_budget_subcategory_approval_requests_subcategory_id'),
        table_name='budget_subcategory_approval_requests',
    )

    op.drop_index(
        op.f('ix_budget_subcategory_approval_requests_status'),
        table_name='budget_subcategory_approval_requests',
    )

    op.drop_index(
        op.f('ix_budget_subcategory_approval_requests_budget_id'),
        table_name='budget_subcategory_approval_requests',
    )

    op.drop_table('budget_subcategory_approval_requests')
