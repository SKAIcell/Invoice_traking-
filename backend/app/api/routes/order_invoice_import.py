
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.party import Party
from app.schemas.invoice import InvoiceCreate
from app.services.order_invoice_excel import (
    read_order_invoice_excel,
)


router = APIRouter(
    prefix="/orders",
    tags=["Order Invoice Import"],
)


def get_order_and_party(
    db: Session,
    order_id: int,
):
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    party = (
        db.query(Party)
        .filter(Party.id == order.party_id)
        .first()
    )

    if not party:
        raise HTTPException(
            status_code=404,
            detail="Vendor linked to this order was not found.",
        )

    if not party.is_active:
        raise HTTPException(
            status_code=400,
            detail="The vendor linked to this order is inactive.",
        )

    # This company uses vendors for both PO and SO orders.
    if party.party_type != "VENDOR":
        raise HTTPException(
            status_code=400,
            detail="Both PO and SO orders must be linked to a vendor.",
        )

    return order, party


def validate_import_rows(
    db: Session,
    order: Order,
    party: Party,
    rows: list[dict],
):
    expected_invoice_type = (
        "PURCHASE" if order.order_type == "PO" else "SALES"
    )

    existing_total = (
        db.query(
            func.coalesce(
                func.sum(Invoice.amount),
                0,
            )
        )
        .filter(Invoice.order_id == order.id)
        .scalar()
    )

    existing_total = Decimal(
        str(existing_total or 0)
    )

    proposed_total = Decimal("0.00")
    seen_invoice_numbers = set()

    for row in rows:
        errors = list(row.get("errors") or [])

        invoice_number = str(
            row.get("invoice_number") or ""
        ).strip()

        excel_order_number = str(
            row.get("order_number") or ""
        ).strip()

        excel_party_name = str(
            row.get("vendor_name") or ""
        ).strip()

        excel_party_code = str(
            row.get("vendor_code") or ""
        ).strip()

        # Validate selected PO/SO number.
        if excel_order_number.casefold() != (
            order.order_number.strip().casefold()
        ):
            errors.append(
                "PO/SO Number does not match selected order "
                f"{order.order_number}."
            )

        # Validate vendor name.
        if excel_party_name.casefold() != (
            party.name.strip().casefold()
        ):
            errors.append(
                "Vendor Name does not match "
                f"{party.name} linked to this order."
            )

        # Validate vendor code.
        expected_party_code = str(
            party.code or ""
        ).strip()

        if excel_party_code.casefold() != (
            expected_party_code.casefold()
        ):
            errors.append(
                "Vendor Code does not match "
                f"{expected_party_code} linked to this order."
            )

        # Validate duplicate invoice numbers in Excel.
        invoice_key = invoice_number.casefold()

        if invoice_key:
            if invoice_key in seen_invoice_numbers:
                errors.append(
                    "Duplicate Invoice Number in this Excel file."
                )
            else:
                seen_invoice_numbers.add(invoice_key)

            # Validate invoice number against existing invoices.
            existing_invoice = (
                db.query(Invoice)
                .filter(
                    Invoice.party_id == party.id,
                    Invoice.invoice_number == invoice_number,
                )
                .first()
            )

            if existing_invoice:
                errors.append(
                    "This invoice number already exists "
                    "for the selected vendor."
                )

        invoice_date = row.get("invoice_date")
        due_date = row.get("due_date")
        amount = row.get("amount")

        # Validate invoice date against order financial year.
        if invoice_date:
            try:
                parsed_invoice_date = date.fromisoformat(
                    str(invoice_date)
                )

                start_year = int(
                    order.financial_year.split("-")[0]
                )

                fy_start = date(
                    start_year,
                    4,
                    1,
                )

                fy_end = date(
                    start_year + 1,
                    3,
                    31,
                )

                if not (
                    fy_start
                    <= parsed_invoice_date
                    <= fy_end
                ):
                    errors.append(
                        "Invoice Date must fall within the "
                        f"order Financial Year {order.financial_year}."
                    )

            except (ValueError, TypeError):
                errors.append(
                    "Invalid Invoice Date."
                )

        # Validate due date.
        if due_date and invoice_date:
            try:
                parsed_due_date = date.fromisoformat(
                    str(due_date)
                )

                parsed_invoice_date = date.fromisoformat(
                    str(invoice_date)
                )

                if parsed_due_date < parsed_invoice_date:
                    errors.append(
                        "Due Date cannot be earlier than Invoice Date."
                    )

            except (ValueError, TypeError):
                errors.append(
                    "Invalid Due Date."
                )

        # Validate and accumulate invoice amount.
        if amount is not None:
            try:
                parsed_amount = Decimal(
                    str(amount)
                )

                if parsed_amount <= Decimal("0"):
                    errors.append(
                        "Invoice amount must be greater than zero."
                    )
                else:
                    proposed_total += parsed_amount

            except Exception:
                errors.append(
                    "Invalid invoice amount."
                )

        # Assign values from the selected order.
        row["invoice_type"] = expected_invoice_type
        row["financial_year"] = order.financial_year
        row["order_id"] = order.id
        row["party_id"] = party.id

        row["errors"] = list(
            dict.fromkeys(errors)
        )

        row["is_valid"] = not row["errors"]

    total_after_import = (
        existing_total + proposed_total
    )

    # Ensure the invoices do not exceed the order amount.
    if total_after_import > Decimal(
        str(order.amount)
    ):
        remaining = (
            Decimal(str(order.amount))
            - existing_total
        )

        for row in rows:
            if row.get("is_valid"):
                row["errors"].append(
                    "The combined invoice amount exceeds the "
                    f"remaining order value of {remaining:.2f}."
                )

                row["is_valid"] = False

    return {
        "existing_invoice_total": str(
            existing_total
        ),
        "proposed_invoice_total": str(
            proposed_total
        ),
        "remaining_order_value": str(
            Decimal(str(order.amount))
            - existing_total
        ),
        "rows": rows,
    }


async def read_uploaded_excel(
    file: UploadFile,
) -> bytes:
    filename = (
        file.filename or ""
    ).lower()

    if not filename.endswith(
        (".xlsx", ".xlsm")
    ):
        raise HTTPException(
            status_code=400,
            detail="Please upload an Excel .xlsx or .xlsm file.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Uploaded Excel file is empty.",
        )

    return content


@router.post(
    "/{order_id}/invoices/import/preview"
)
async def preview_order_invoice_import(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    order, party = get_order_and_party(
        db,
        order_id,
    )

    content = await read_uploaded_excel(
        file
    )

    try:
        parsed = read_order_invoice_excel(
            content
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    validation = validate_import_rows(
        db=db,
        order=order,
        party=party,
        rows=parsed["rows"],
    )

    rows = validation["rows"]

    return {
        "order_id": order.id,
        "order_type": order.order_type,
        "order_number": order.order_number,
        "party_id": party.id,
        "party_name": party.name,
        "financial_year": order.financial_year,
        "total_rows": parsed["total_rows"],
        "valid_rows": sum(
            1
            for row in rows
            if row["is_valid"]
        ),
        "invalid_rows": sum(
            1
            for row in rows
            if not row["is_valid"]
        ),
        "existing_invoice_total": validation[
            "existing_invoice_total"
        ],
        "proposed_invoice_total": validation[
            "proposed_invoice_total"
        ],
        "remaining_order_value": validation[
            "remaining_order_value"
        ],
        "rows": rows,
    }


@router.post(
    "/{order_id}/invoices/import/confirm"
)
async def confirm_order_invoice_import(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    order, party = get_order_and_party(
        db,
        order_id,
    )

    content = await read_uploaded_excel(
        file
    )

    try:
        parsed = read_order_invoice_excel(
            content
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    validation = validate_import_rows(
        db=db,
        order=order,
        party=party,
        rows=parsed["rows"],
    )

    rows = validation["rows"]

    invalid_rows = [
        row
        for row in rows
        if not row["is_valid"]
    ]

    if invalid_rows:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Import validation failed. "
                    "No invoices were saved."
                ),
                "invalid_rows": invalid_rows,
            },
        )

    invoices_to_create = []

    for row in rows:
        payload = {
            "invoice_type": (
                "PURCHASE"
                if order.order_type == "PO"
                else "SALES"
            ),
            "invoice_number": row["invoice_number"],
            "order_id": order.id,
            "party_id": party.id,
            "financial_year": order.financial_year,
            "invoice_date": row["invoice_date"],
            "due_date": row["due_date"],
            "period": row.get("period"),
            "location": row.get("location"),
            "amount": row["amount"],
            "status": "DRAFT",
            "description": row.get("description"),
            "remarks": row.get("remarks"),
        }

        invoice_data = InvoiceCreate.model_validate(
            payload
        )

        invoices_to_create.append(
            Invoice(
                **invoice_data.model_dump()
            )
        )

    try:
        db.add_all(
            invoices_to_create
        )

        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "An invoice conflict occurred while saving. "
                "No invoices were imported. Please preview again."
            ),
        )

    except Exception:
        db.rollback()
        raise

    for invoice in invoices_to_create:
        db.refresh(invoice)

    return {
        "message": (
            f"{len(invoices_to_create)} invoice(s) "
            "imported successfully."
        ),
        "order_id": order.id,
        "order_number": order.order_number,
        "imported_count": len(
            invoices_to_create
        ),
        "invoice_ids": [
            invoice.id
            for invoice in invoices_to_create
        ],
    }
