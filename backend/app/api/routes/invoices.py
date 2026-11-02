
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db.session import get_db
from app.models.budget import Budget
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.party import Party
from app.models.payment import Payment
from app.services.invoice_excel import read_invoice_excel
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceDateSentUpdate,
    InvoiceRegisterResponse,
    InvoiceResponse,
    InvoiceSummaryResponse,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])
BACKEND_DIR = Path(__file__).resolve().parents[2]
INVOICE_COPY_DIR = BACKEND_DIR / "uploads" / "invoice-copies"

MAX_INVOICE_COPY_SIZE = 10 * 1024 * 1024

ALLOWED_INVOICE_COPY_TYPES = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}


def validate_invoice_links(db: Session, payload: InvoiceCreate):
    order = db.get(Order, payload.order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    expected_order_type = (
        "PO" if payload.invoice_type == "PURCHASE" else "SO"
    )

    if order.order_type != expected_order_type:
        raise HTTPException(
            422,
            f"{payload.invoice_type} invoice requires a "
            f"{expected_order_type} order",
        )

    if order.party_id != payload.party_id:
        raise HTTPException(
            422,
            "Invoice vendor/customer must match the selected order",
        )

    party = db.get(Party, payload.party_id)

    if party is None:
        raise HTTPException(404, "Vendor/customer not found")

    expected_party_type = (
        "VENDOR" if payload.invoice_type == "PURCHASE" else "CUSTOMER"
    )

    if (party.party_type or "").strip().upper() != expected_party_type:
        raise HTTPException(
            422,
            f"{payload.invoice_type} invoice requires a "
            f"{expected_party_type}",
        )

    if not party.is_active:
        raise HTTPException(422, "Vendor/customer is inactive")

    if order.financial_year != payload.financial_year:
        raise HTTPException(
            422,
            "Invoice financial year must match the order",
        )

    if payload.amount > Decimal(str(order.amount)):
        raise HTTPException(
            422,
            "Invoice amount cannot exceed the order amount",
        )

    return order


def validate_order_invoice_total(
    db: Session,
    order: Order,
    amount: Decimal,
    exclude_invoice_id: int | None = None,
):
    query = db.query(
        func.coalesce(func.sum(Invoice.amount), 0)
    ).filter(Invoice.order_id == order.id)

    if exclude_invoice_id is not None:
        query = query.filter(Invoice.id != exclude_invoice_id)

    existing_total = Decimal(str(query.scalar() or 0))
    new_total = existing_total + Decimal(str(amount))
    order_amount = Decimal(str(order.amount))

    if new_total > order_amount:
        available = order_amount - existing_total

        raise HTTPException(
            422,
            (
                "Total submitted invoice amount cannot exceed the "
                f"order amount. Available order value: {available:.2f}"
            ),
        )



@router.post(
    "/import/preview",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def preview_invoice_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()

    if not filename.endswith(".xlsx"):
        raise HTTPException(
            422,
            "Please upload an Excel .xlsx file",
        )

    content = await file.read(10 * 1024 * 1024 + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded Excel file is empty")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            413,
            "Excel file must be 10 MB or smaller",
        )

    try:
        preview = read_invoice_excel(content)
    except Exception as exc:
        raise HTTPException(
            422,
            f"Could not read Excel file: {exc}",
        )

    rows = preview["rows"]

    seen_in_file = set()

    for row in rows:
        if not row["is_valid"]:
            continue

        errors = row["errors"]

        invoice_type = row["invoice_type"]
        invoice_number = row["invoice_number"]
        vendor_code = row["vendor_code"]
        order_number = row["order_number"]
        financial_year = row["financial_year"]

        # Detect duplicate invoice numbers within the workbook.
        duplicate_key = (
            invoice_type,
            invoice_number.casefold(),
            vendor_code.casefold(),
            financial_year if invoice_type == "SALES" else None,
        )

        if duplicate_key in seen_in_file:
            errors.append(
                "Duplicate invoice number within this Excel file."
            )
        else:
            seen_in_file.add(duplicate_key)

        expected_order_type = (
            "PO" if invoice_type == "PURCHASE" else "SO"
        )

        order = (
            db.query(Order)
            .filter(
                Order.order_number == order_number,
                Order.order_type == expected_order_type,
            )
            .first()
        )

        if order is None:
            errors.append(
                f"{expected_order_type} order '{order_number}' not found."
            )

        expected_party_type = (
            "VENDOR" if invoice_type == "PURCHASE" else "CUSTOMER"
        )

        party = (
            db.query(Party)
            .filter(
                Party.code == vendor_code,
                Party.party_type == expected_party_type,
            )
            .first()
        )

        if party is None:
            errors.append(
                f"{expected_party_type} code '{vendor_code}' not found."
            )
        elif not party.is_active:
            errors.append(
                f"{expected_party_type} '{vendor_code}' is inactive."
            )

        if order and party:
            if order.party_id != party.id:
                errors.append(
                    "Order and vendor/customer do not match."
                )

            if order.financial_year != financial_year:
                errors.append(
                    "Invoice financial year must match the order."
                )

            if Decimal(row["amount"]) > Decimal(str(order.amount)):
                errors.append(
                    "Invoice amount cannot exceed order amount."
                )

            existing_total = Decimal(
                str(
                    db.query(
                        func.coalesce(func.sum(Invoice.amount), 0)
                    )
                    .filter(Invoice.order_id == order.id)
                    .scalar()
                    or 0
                )
            )

            if existing_total + Decimal(row["amount"]) > Decimal(
                str(order.amount)
            ):
                errors.append(
                    "Total invoices would exceed the order amount."
                )

        duplicate_query = db.query(Invoice).filter(
            Invoice.invoice_type == invoice_type,
            Invoice.invoice_number == invoice_number,
            Invoice.party_id == party.id if party else -1,
        )

        if invoice_type == "SALES":
            duplicate_query = duplicate_query.filter(
                Invoice.financial_year == financial_year
            )

        if duplicate_query.first():
            errors.append(
                "This invoice already exists in the database."
            )

        row["order_id"] = order.id if order else None
        row["party_id"] = party.id if party else None
        row["errors"] = errors
        row["is_valid"] = len(errors) == 0

    preview["valid_rows"] = sum(
        1 for row in rows if row["is_valid"]
    )

    preview["invalid_rows"] = sum(
        1 for row in rows if not row["is_valid"]
    )

    return preview


@router.post(
    "/import/confirm",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def confirm_invoice_import(
    rows: list[dict] = Body(...),
    db: Session = Depends(get_db),
):
    if not rows:
        raise HTTPException(422, "No invoice rows provided")

    if len(rows) > 1000:
        raise HTTPException(
            422,
            "Maximum 1000 invoices can be imported at once",
        )

    if any(not row.get("is_valid", False) for row in rows):
        raise HTTPException(
            422,
            "Import contains invalid rows. Correct them before confirming.",
        )

    seen_in_file = set()
    order_totals = {}
    invoices_to_create = []

    try:
        for row in rows:
            invoice_type = str(row["invoice_type"]).strip().upper()
            invoice_number = str(row["invoice_number"]).strip()
            order_number = str(row["order_number"]).strip()
            vendor_code = str(row["vendor_code"]).strip()
            financial_year = str(row["financial_year"]).strip()

            if invoice_type not in ("PURCHASE", "SALES"):
                raise HTTPException(422, "Invalid invoice type")

            expected_order_type = (
                "PO" if invoice_type == "PURCHASE" else "SO"
            )

            expected_party_type = (
                "VENDOR" if invoice_type == "PURCHASE" else "CUSTOMER"
            )

            order = (
                db.query(Order)
                .filter(
                    Order.order_number == order_number,
                    Order.order_type == expected_order_type,
                )
                .first()
            )

            if order is None:
                raise HTTPException(
                    422,
                    f"Order '{order_number}' not found",
                )

            party = (
                db.query(Party)
                .filter(
                    Party.code == vendor_code,
                    Party.party_type == expected_party_type,
                )
                .first()
            )

            if party is None:
                raise HTTPException(
                    422,
                    f"{expected_party_type} '{vendor_code}' not found",
                )

            if not party.is_active:
                raise HTTPException(
                    422,
                    f"{expected_party_type} '{vendor_code}' is inactive",
                )

            amount = Decimal(str(row["amount"]))

            payload = InvoiceCreate(
                invoice_type=invoice_type,
                invoice_number=invoice_number,
                order_id=order.id,
                party_id=party.id,
                financial_year=financial_year,
                invoice_date=row["invoice_date"],
                due_date=row["due_date"],
                period=row.get("period"),
                location=row.get("location"),
                amount=amount,
                description=row.get("description"),
                remarks=row.get("remarks"),
            )

            order = validate_invoice_links(db, payload)

            duplicate_key = (
                invoice_type,
                invoice_number.casefold(),
                party.id,
                financial_year if invoice_type == "SALES" else None,
            )

            if duplicate_key in seen_in_file:
                raise HTTPException(
                    409,
                    f"Duplicate invoice '{invoice_number}' in Excel file",
                )

            seen_in_file.add(duplicate_key)

            duplicate_query = db.query(Invoice).filter(
                Invoice.invoice_type == invoice_type,
                Invoice.invoice_number == invoice_number,
                Invoice.party_id == party.id,
            )

            if invoice_type == "SALES":
                duplicate_query = duplicate_query.filter(
                    Invoice.financial_year == financial_year
                )

            if duplicate_query.first():
                raise HTTPException(
                    409,
                    f"Invoice '{invoice_number}' already exists",
                )

            order_totals[order.id] = (
                order_totals.get(order.id, Decimal("0.00"))
                + amount
            )

            invoices_to_create.append(
                (payload, order)
            )

        # Validate combined invoice amounts per order.
        for order_id, import_total in order_totals.items():
            order = db.get(Order, order_id)

            validate_order_invoice_total(
                db,
                order,
                import_total,
            )

        # Create all invoices in one transaction.
        created_invoices = []

        for payload, order in invoices_to_create:
            invoice = Invoice(**payload.model_dump())
            db.add(invoice)
            created_invoices.append(invoice)

        db.commit()

        for invoice in created_invoices:
            db.refresh(invoice)

        return {
            "message": "Invoices imported successfully",
            "created_count": len(created_invoices),
            "invoice_ids": [
                invoice.id for invoice in created_invoices
            ],
            "invoice_numbers": [
                invoice.invoice_number
                for invoice in created_invoices
            ],
        }

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Invoice import failed because of a duplicate or data conflict",
        )

    except Exception:
        db.rollback()
        raise


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=201,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
):
    order = validate_invoice_links(db, payload)

    validate_order_invoice_total(
        db,
        order,
        payload.amount,
    )

    query = db.query(Invoice).filter(
        Invoice.invoice_type == payload.invoice_type,
        Invoice.invoice_number == payload.invoice_number,
        Invoice.party_id == payload.party_id,
    )

    if payload.invoice_type == "SALES":
        query = query.filter(
            Invoice.financial_year == payload.financial_year
        )

    existing = query.first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=jsonable_encoder({
                "message": "Duplicate invoice",
                "invoice": {
                    "invoice_date": existing.invoice_date,
                    "invoice_number": existing.invoice_number,
                    "po_number": (
                        existing.order.order_number
                        if existing.order
                        and existing.order.order_type == "PO"
                        else None
                    ),
                    "entry_date": existing.created_at,
                    "date_sent_to_accounts": (
                        existing.date_sent_to_accounts
                    ),
                    "amount": existing.amount,
                },
            }),
        )

    invoice = Invoice(**payload.model_dump())
    db.add(invoice)

    try:
        db.commit()
        db.refresh(invoice)

    except IntegrityError:
        db.rollback()

        existing = (
            db.query(Invoice)
            .filter(
                Invoice.invoice_type == payload.invoice_type,
                Invoice.invoice_number == payload.invoice_number,
                Invoice.party_id == payload.party_id,
            )
            .first()
        )

        raise HTTPException(
            status_code=409,
            detail=jsonable_encoder({
                "message": "Duplicate invoice or data conflict",
                "invoice": {
                    "invoice_date": existing.invoice_date,
                    "invoice_number": existing.invoice_number,
                    "po_number": (
                        existing.order.order_number
                        if existing.order
                        and existing.order.order_type == "PO"
                        else None
                    ),
                    "entry_date": existing.created_at,
                    "date_sent_to_accounts": (
                        existing.date_sent_to_accounts
                    ),
                    "amount": existing.amount,
                } if existing else None,
            }),
        )

    return invoice


@router.get("", response_model=list[InvoiceResponse])
def list_invoices(
    invoice_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Invoice)

    if invoice_type:
        invoice_type = invoice_type.upper()

        if invoice_type not in ("PURCHASE", "SALES"):
            raise HTTPException(
                422,
                "Invoice type must be PURCHASE or SALES",
            )

        query = query.filter(Invoice.invoice_type == invoice_type)

    return query.order_by(Invoice.id.desc()).limit(100).all()


@router.get("/search", response_model=list[InvoiceResponse])
def search_invoices(
    q: str,
    db: Session = Depends(get_db),
):
    q = q.strip()

    if not q:
        raise HTTPException(422, "Search text required")

    return (
        db.query(Invoice)
        .join(Order, Invoice.order_id == Order.id)
        .join(Party, Invoice.party_id == Party.id)
        .filter(
            (Invoice.invoice_number.ilike(f"%{q}%"))
            | (Order.order_number.ilike(f"%{q}%"))
            | (Party.name.ilike(f"%{q}%"))
            | (Party.code.ilike(f"%{q}%"))
        )
        .order_by(Invoice.id.desc())
        .limit(100)
        .all()
    )


@router.get("/register", response_model=list[InvoiceRegisterResponse])
def list_invoice_register(
    db: Session = Depends(get_db),
):
    """Return expanded invoice register rows with payment totals."""

    payment_totals = (
        db.query(
            Payment.invoice_id.label("invoice_id"),
            func.sum(Payment.amount).label("total_paid"),
        )
        .group_by(Payment.invoice_id)
        .subquery()
    )

    rows = (
        db.query(
            Invoice,
            Order,
            Party,
            Budget,
            func.coalesce(payment_totals.c.total_paid, 0).label(
                "total_paid"
            ),
        )
        .join(Order, Invoice.order_id == Order.id)
        .join(Party, Invoice.party_id == Party.id)
        .outerjoin(Budget, Order.budget_id == Budget.id)
        .outerjoin(
            payment_totals,
            payment_totals.c.invoice_id == Invoice.id,
        )
        .order_by(Invoice.id.desc())
        .limit(100)
        .all()
    )

    results = []

    for invoice, order, party, budget, paid_value in rows:
        amount = Decimal(str(invoice.amount))
        total_paid = Decimal(str(paid_value or 0))
        balance_due = amount - total_paid

        if balance_due <= 0:
            payment_status = "PAID"
        elif invoice.due_date < date.today():
            payment_status = "OVERDUE"
        elif total_paid > 0:
            payment_status = "PART_PAID"
        else:
            payment_status = "UNPAID"

        results.append(
            InvoiceRegisterResponse(
                id=invoice.id,
                invoice_type=invoice.invoice_type,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                entry_date=invoice.created_at,
                order_id=order.id,
                order_number=order.order_number,
                party_id=party.id,
                party_name=party.name,
                financial_year=invoice.financial_year,
                budget_name=budget.name if budget else "N/A",
                budget_type=budget.budget_type if budget else "N/A",
                amount=amount,
                total_paid=total_paid,
                balance_due=balance_due,
                due_date=invoice.due_date,
                date_sent_to_accounts=invoice.date_sent_to_accounts,
                payment_status=payment_status,
            )
        )

    return results


@router.patch(
    "/{invoice_id}/date-sent-to-accounts",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def update_invoice_date_sent_to_accounts(
    invoice_id: int,
    payload: InvoiceDateSentUpdate,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    invoice.date_sent_to_accounts = payload.date_sent_to_accounts

    db.commit()
    db.refresh(invoice)

    return invoice


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    return invoice


@router.put(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def update_invoice(
    invoice_id: int,
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    order = validate_invoice_links(db, payload)

    validate_order_invoice_total(
        db,
        order,
        payload.amount,
        exclude_invoice_id=invoice_id,
    )

    total_paid = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.invoice_id == invoice_id)
        .scalar()
    )

    if payload.amount < Decimal(str(total_paid or 0)):
        raise HTTPException(
            422,
            "Invoice amount cannot be less than payments already recorded",
        )

    duplicate_query = db.query(Invoice).filter(
        Invoice.id != invoice_id,
        Invoice.invoice_type == payload.invoice_type,
        Invoice.invoice_number == payload.invoice_number,
        Invoice.party_id == payload.party_id,
    )

    if payload.invoice_type == "SALES":
        duplicate_query = duplicate_query.filter(
            Invoice.financial_year == payload.financial_year
        )

    if duplicate_query.first():
        raise HTTPException(409, "Duplicate invoice")

    for field, value in payload.model_dump().items():
        setattr(invoice, field, value)

    try:
        db.commit()
        db.refresh(invoice)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Invoice could not be updated because of a data conflict",
        )

    return invoice

@router.post(
    "/{invoice_id}/invoice-copy",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def upload_invoice_copy(
    invoice_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    extension = Path(file.filename or "").suffix.lower()
    allowed_types = ALLOWED_INVOICE_COPY_TYPES.get(extension)

    if allowed_types is None or file.content_type not in allowed_types:
        raise HTTPException(
            422,
            "Invoice copy must be a PDF, JPG/JPEG, or PNG file",
        )

    content = await file.read(MAX_INVOICE_COPY_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded file is empty")

    if len(content) > MAX_INVOICE_COPY_SIZE:
        raise HTTPException(413, "Invoice copy must be 10 MB or smaller")

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF file")

    if extension in (".jpg", ".jpeg") and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, "Invalid JPEG file")

    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(422, "Invalid PNG file")

    INVOICE_COPY_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}{extension}"
    destination = INVOICE_COPY_DIR / stored_name

    try:
        destination.write_bytes(content)

        previous_path = invoice.invoice_file_path

        invoice.invoice_file_path = str(
            Path("uploads") / "invoice-copies" / stored_name
        )

        db.commit()
        db.refresh(invoice)

    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(500, "Could not save invoice copy")

    if previous_path:
        old_file = (BACKEND_DIR / previous_path).resolve()

        try:
            old_file.relative_to(INVOICE_COPY_DIR.resolve())
            old_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    return {
        "message": "Invoice copy uploaded successfully",
        "view_url": f"/api/invoices/{invoice_id}/invoice-copy",
    }


@router.get("/{invoice_id}/invoice-copy")
def view_invoice_copy(
    invoice_id: int,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    if not invoice.invoice_file_path:
        raise HTTPException(404, "No invoice copy found")

    stored_path = (BACKEND_DIR / invoice.invoice_file_path).resolve()

    try:
        stored_path.relative_to(INVOICE_COPY_DIR.resolve())
    except ValueError:
        raise HTTPException(404, "Invoice copy not found")

    if not stored_path.is_file():
        raise HTTPException(404, "Invoice copy file is missing")

    extension = stored_path.suffix.lower()

    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    return FileResponse(
        stored_path,
        media_type=media_types.get(extension, "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{stored_path.name}"'
        },
    )

@router.delete(
    "/{invoice_id}",
    status_code=204,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)

    if invoice is None:
        raise HTTPException(404, "Invoice not found")

    existing_payment = (
        db.query(Payment)
        .filter(Payment.invoice_id == invoice_id)
        .first()
    )

    if existing_payment:
        raise HTTPException(
            409,
            "This invoice has recorded payments and cannot be deleted",
        )

    invoice_copy_path = invoice.invoice_file_path

    db.delete(invoice)
    db.commit()

    # Remove the stored invoice copy after successful database deletion.
    if invoice_copy_path:
        stored_path = (BACKEND_DIR / invoice_copy_path).resolve()

        try:
            stored_path.relative_to(INVOICE_COPY_DIR.resolve())
            stored_path.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    return None