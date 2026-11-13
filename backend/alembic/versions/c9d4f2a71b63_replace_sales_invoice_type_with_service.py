
"""replace SALES invoice type with SERVICE

Revision ID: c9d4f2a71b63
Revises: b401e57364ae
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d4f2a71b63"
down_revision = "b401e57364ae"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Remove the old unique index before dropping its generated column.
    op.drop_index(
        "uq_sales_invoice_fy_number",
        table_name="invoices",
    )

    # 2. Remove the old invoice type constraint.
    op.drop_constraint(
        "ck_invoice_type",
        "invoices",
        type_="check",
    )

    # 3. Remove the old generated column.
    op.drop_column("invoices", "sales_invoice_key")

    # 4. Convert existing SALES invoices to SERVICE.
    op.execute(
        """
        UPDATE invoices
        SET invoice_type = 'SERVICE'
        WHERE invoice_type = 'SALES'
        """
    )

    # 5. Allow PURCHASE and SERVICE only.
    op.create_check_constraint(
        "ck_invoice_type",
        "invoices",
        "invoice_type IN ('PURCHASE', 'SERVICE')",
    )

    # 6. Create the new generated SERVICE invoice key.
    op.add_column(
        "invoices",
        sa.Column(
            "service_invoice_key",
            sa.String(length=110),
            sa.Computed(
                """
                CASE
                    WHEN invoice_type = 'SERVICE'
                    THEN CONCAT(financial_year, ':', invoice_number)
                    ELSE NULL
                END
                """,
                persisted=True,
            ),
            nullable=True,
        ),
    )

    # 7. Preserve financial-year invoice number uniqueness.
    op.create_index(
        "uq_service_invoice_fy_number",
        "invoices",
        ["service_invoice_key"],
        unique=True,
    )


def downgrade():
    # Restore the old unique index structure.
    op.drop_index(
        "uq_service_invoice_fy_number",
        table_name="invoices",
    )

    op.drop_constraint(
        "ck_invoice_type",
        "invoices",
        type_="check",
    )

    op.drop_column("invoices", "service_invoice_key")

    # Restore the old generated SALES invoice key.
    op.add_column(
        "invoices",
        sa.Column(
            "sales_invoice_key",
            sa.String(length=110),
            sa.Computed(
                """
                CASE
                    WHEN invoice_type = 'SALES'
                    THEN CONCAT(financial_year, ':', invoice_number)
                    ELSE NULL
                END
                """,
                persisted=True,
            ),
            nullable=True,
        ),
    )

    op.create_index(
        "uq_sales_invoice_fy_number",
        "invoices",
        ["sales_invoice_key"],
        unique=True,
    )

    op.execute(
        """
        UPDATE invoices
        SET invoice_type = 'SALES'
        WHERE invoice_type = 'SERVICE'
        """
    )

    op.create_check_constraint(
        "ck_invoice_type",
        "invoices",
        "invoice_type IN ('PURCHASE', 'SALES')",
    )
