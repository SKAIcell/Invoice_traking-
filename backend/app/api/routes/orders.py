
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
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
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
from app.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    validate_fy_date,
    expected_budget_type,
)
from app.schemas.invoice import OrderInvoiceResponse
from app.services.order_excel import read_order_excel

router = APIRouter(prefix="/orders", tags=["Orders"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
APPROVAL_DIR = BACKEND_DIR / "uploads" / "order-approvals"
MAX_APPROVAL_SIZE = 10 * 1024 * 1024
ORDER_COPY_DIR = BACKEND_DIR / "uploads" / "order-copies"
MAX_ORDER_COPY_SIZE = 10 * 1024 * 1024

ALLOWED_ORDER_COPY_TYPES = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}
ALLOWED_APPROVAL_TYPES = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}

@router.post(
    "/import/preview",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def preview_order_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if Path(file.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(
            422,
            "Please upload an Excel .xlsx file",
        )

    content = await file.read(10 * 1024 * 1024 + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded Excel file is empty")

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Excel file must be 10 MB or smaller")

    try:
        result = read_order_excel(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    seen_order_numbers = set()

    for row in result["rows"]:
        if not row["is_valid"]:
            continue

        errors = row["errors"]
        order_type = row["order_type"]
        order_number = row["order_number"]
        vendor_code = row["vendor_code"]
        budget_name = row["budget_name"]
        financial_year = row["financial_year"]

        duplicate_key = (order_type, order_number)

        if duplicate_key in seen_order_numbers:
            errors.append("Duplicate order number within this Excel file.")
        else:
            seen_order_numbers.add(duplicate_key)

        existing_order = db.query(Order.id).filter(
            Order.order_type == order_type,
            Order.order_number == order_number,
        ).first()

        if existing_order:
            errors.append("This order number already exists.")

        vendor = db.query(Party).filter(
            Party.code == vendor_code,
            Party.party_type == "VENDOR",
        ).one_or_none()

        if vendor is None:
            errors.append(f"Vendor code '{vendor_code}' was not found.")
        elif not vendor.is_active:
            errors.append(f"Vendor '{vendor_code}' is inactive.")

        required_type = expected_budget_type(order_type)

        budget = db.query(Budget).filter(
            Budget.name == budget_name,
            Budget.financial_year == financial_year,
            Budget.budget_type == required_type,
        ).one_or_none()

        if budget is None:
            errors.append(
                f"Budget '{budget_name}' for {financial_year} "
                f"with type {required_type} was not found."
            )
        else:
            row["vendor_id"] = vendor.id if vendor else None
            row["budget_id"] = budget.id

            if order_type == "PO":
                committed = get_committed_budget(db, budget.id)

                requested_in_file = sum(
                    Decimal(str(other["amount"]))
                    for other in result["rows"]
                    if (
                        other["order_type"] == "PO"
                        and other["budget_name"] == budget_name
                        and other["financial_year"] == financial_year
                        and other["is_valid"]
                        and other["amount"] is not None
                    )
                )

                available = (
                    Decimal(str(budget.approved_amount))
                    - committed
                )

                if requested_in_file > available:
                    errors.append(
                        "Combined PO amount in this file exceeds "
                        f"available budget. Available: {available}"
                    )

        row["is_valid"] = len(errors) == 0

    result["valid_rows"] = sum(
        1 for row in result["rows"] if row["is_valid"]
    )
    result["invalid_rows"] = sum(
        1 for row in result["rows"] if not row["is_valid"]
    )

    return result



@router.post(
    "/import/confirm",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def confirm_order_import(
    rows: list[dict] = Body(...),
    db: Session = Depends(get_db),
):
    if not rows:
        raise HTTPException(422, "No order rows were provided")

    if len(rows) > 1000:
        raise HTTPException(422, "A maximum of 1000 orders can be imported at once")

    created_orders = []

    try:
        # Validate all rows before inserting anything.
        prepared_rows = []
        seen_order_numbers = set()
        requested_by_budget = {}

        for index, row in enumerate(rows, start=1):
            if row.get("is_valid") is not True:
                raise HTTPException(
                    422,
                    f"Excel row {row.get('excel_row', index)} is not marked valid",
                )

            order_type = str(row.get("order_type", "")).strip().upper()
            order_number = str(row.get("order_number", "")).strip()
            vendor_code = str(row.get("vendor_code", "")).strip()
            budget_name = str(row.get("budget_name", "")).strip()
            financial_year = str(row.get("financial_year", "")).strip()

            if order_type not in ("PO", "SO"):
                raise HTTPException(422, f"Invalid order type in row {index}")

            if not order_number or not vendor_code or not budget_name:
                raise HTTPException(422, f"Missing required information in row {index}")

            duplicate_key = (order_type, order_number)

            if duplicate_key in seen_order_numbers:
                raise HTTPException(
                    409,
                    f"Duplicate order number '{order_number}' in the import",
                )

            seen_order_numbers.add(duplicate_key)

            existing = db.query(Order.id).filter(
                Order.order_type == order_type,
                Order.order_number == order_number,
            ).first()

            if existing:
                raise HTTPException(
                    409,
                    f"Order number '{order_number}' already exists",
                )

            vendor = db.query(Party).filter(
                Party.code == vendor_code,
                Party.party_type == "VENDOR",
            ).one_or_none()

            if vendor is None or not vendor.is_active:
                raise HTTPException(
                    422,
                    f"Vendor '{vendor_code}' was not found or is inactive",
                )

            required_type = expected_budget_type(order_type)

            budget = (
                db.query(Budget)
                .filter(
                    Budget.name == budget_name,
                    Budget.financial_year == financial_year,
                    Budget.budget_type == required_type,
                )
                .with_for_update()
                .one_or_none()
            )

            if budget is None:
                raise HTTPException(
                    422,
                    f"Budget '{budget_name}' for {financial_year} "
                    f"with type {required_type} was not found",
                )

            try:
                order_date = date.fromisoformat(str(row.get("order_date", "")))
                validate_fy_date(financial_year, order_date)
                amount = Decimal(str(row.get("amount", "")))
            except (ValueError, TypeError, ArithmeticError):
                raise HTTPException(
                    422,
                    f"Invalid date, financial year, or amount in row {index}",
                )

            if not amount.is_finite() or amount <= 0:
                raise HTTPException(
                    422,
                    f"Amount must be greater than zero in row {index}",
                )

            if order_type == "PO":
                requested_by_budget[budget.id] = (
                    requested_by_budget.get(budget.id, Decimal("0.00"))
                    + amount
                )

            prepared_rows.append({
                "order_type": order_type,
                "order_number": order_number,
                "party_id": vendor.id,
                "budget_id": budget.id,
                "financial_year": financial_year,
                "order_date": order_date,
                "order_period": row.get("order_period") or None,
                "location": row.get("location") or None,
                "amount": amount,
                "description": row.get("description") or None,
            })

        # Check the combined PO amounts against each budget.
        for budget_id, requested_amount in requested_by_budget.items():
            budget = db.get(Budget, budget_id)

            committed = get_committed_budget(db, budget_id)
            available = Decimal(str(budget.approved_amount)) - committed

            if requested_amount > available:
                raise HTTPException(
                    422,
                    detail={
                        "message": "Insufficient approved budget for bulk import",
                        "budget_id": budget_id,
                        "available": str(available),
                        "requested": str(requested_amount),
                    },
                )

        # Insert only after every row has passed validation.
        for values in prepared_rows:
            order = Order(**values, status="OPEN")
            db.add(order)
            created_orders.append(order)

        db.flush()

        created_ids = [order.id for order in created_orders]

        db.commit()

        return {
            "message": "Orders imported successfully",
            "created_count": len(created_ids),
            "created_order_ids": created_ids,
        }

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Import failed because of a duplicate or invalid database record. No orders were saved.",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            500,
            "Order import failed. No orders were saved.",
        )



def validate_party(db, party_id, order_type):
    if order_type not in ("PO", "SO"):
        raise HTTPException(
            status_code=422,
            detail="Order type must be PO or SO",
        )

    party = db.get(Party, party_id)

    if party is None:
        raise HTTPException(
            status_code=404,
            detail="Vendor not found",
        )

    if (party.party_type or "").strip().upper() != "VENDOR":
        raise HTTPException(
            status_code=422,
            detail="Both Purchase Orders and Service Orders require a vendor",
        )

    if not party.is_active:
        raise HTTPException(
            status_code=422,
            detail="Vendor is inactive",
        )

    return party



def get_committed_budget(db, budget_id, exclude_id=None):
    query = db.query(
        func.coalesce(func.sum(Order.amount), 0)
    ).filter(
        Order.budget_id == budget_id,
        Order.order_type == "PO",
        Order.status != "CANCELLED",
    )

    if exclude_id is not None:
        query = query.filter(Order.id != exclude_id)

    return Decimal(str(query.scalar() or 0))


def get_order_summary(db: Session, order: Order):
    submitted_amount = Decimal(str(
        db.query(func.coalesce(func.sum(Invoice.amount), 0))
        .filter(Invoice.order_id == order.id)
        .scalar() or 0
    ))

    invoice_count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.order_id == order.id)
        .scalar() or 0
    )

    party = db.get(Party, order.party_id)
    budget = db.get(Budget, order.budget_id) if order.budget_id else None

    order_amount = Decimal(str(order.amount))

    result = OrderResponse.model_validate(order).model_dump()
    result["party_name"] = party.name if party else None
    result["budget_name"] = budget.name if budget else None
    result["submitted_invoice_amount"] = submitted_amount
    result["available_order_value"] = order_amount - submitted_amount
    result["total_submitted_invoice"] = invoice_count

    return result


def get_invoice_payment_status(db: Session, invoice: Invoice):
    total_paid = Decimal(str(
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.invoice_id == invoice.id)
        .scalar() or 0
    ))

    balance_due = Decimal(str(invoice.amount)) - total_paid

    if balance_due <= 0:
        return "PAID"
    if invoice.due_date < date.today():
        return "OVERDUE"
    if total_paid > 0:
        return "PART_PAID"
    return "UNPAID"



@router.post(
    "",
    response_model=OrderResponse,
    status_code=201,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):
    from app.schemas.order import expected_budget_type

    budget = (
        db.query(Budget)
        .filter(Budget.id == payload.budget_id)
        .with_for_update()
        .one_or_none()
    )

    if budget is None:
        raise HTTPException(404, "Budget not found")

    required_type = expected_budget_type(payload.order_type)

    if budget.budget_type != required_type:
        raise HTTPException(
            422,
            f"{payload.order_type} requires a {required_type} budget",
        )

    if budget.financial_year != payload.financial_year:
        raise HTTPException(422, "Budget financial year mismatch")

    validate_party(db, payload.party_id, payload.order_type)

    existing = db.query(Order).filter(
        Order.order_type == payload.order_type,
        Order.order_number == payload.order_number,
    ).first()

    if existing:
        raise HTTPException(409, "Order number already exists")

    if payload.order_type == "PO":
        committed = get_committed_budget(db, budget.id)
        available = Decimal(str(budget.approved_amount)) - committed

        if payload.amount > available:
            raise HTTPException(
                422,
                detail={
                    "message": "Insufficient approved budget",
                    "available": str(available),
                    "requested": str(payload.amount),
                },
            )

    order = Order(**payload.model_dump(), status="OPEN")
    db.add(order)

    try:
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Duplicate or invalid order")

    return get_order_summary(db, order)



@router.get("/search", response_model=list[OrderResponse])
def search_orders(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
):
    q = q.strip()

    if not q:
        raise HTTPException(422, "Search text required")

    orders = (
        db.query(Order)
        .filter(Order.order_number.ilike(f"%{q}%"))
        .order_by(Order.id.desc())
        .limit(100)
        .all()
    )

    return [get_order_summary(db, order) for order in orders]


@router.get("", response_model=list[OrderResponse])
def list_orders(
    order_type: str | None = None,
    financial_year: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Order)

    if order_type:
        order_type = order_type.upper()
        if order_type not in ("PO", "SO"):
            raise HTTPException(422, "Invalid order type")
        query = query.filter(Order.order_type == order_type)

    if financial_year:
        query = query.filter(Order.financial_year == financial_year)

    orders = query.order_by(Order.id.desc()).limit(100).all()
    return [get_order_summary(db, order) for order in orders]





@router.get(
    "/{order_id}/invoices",
    response_model=list[OrderInvoiceResponse],
)
def list_order_invoices(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    invoices = (
        db.query(Invoice)
        .filter(Invoice.order_id == order_id)
        .order_by(Invoice.id.desc())
        .all()
    )

    vendor = db.get(Party, order.party_id)
    vendor_name = vendor.name if vendor else None

    budget = (
        db.get(Budget, order.budget_id)
        if order.budget_id
        else None
    )

    results = []

    for invoice in invoices:
        total_paid = Decimal(str(
            db.query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(Payment.invoice_id == invoice.id)
            .scalar() or 0
        ))

        invoice_amount = Decimal(str(invoice.amount))
        balance_due = max(
            Decimal("0.00"),
            invoice_amount - total_paid,
        )

        if balance_due <= 0:
            payment_status = "PAID"
        elif invoice.due_date < date.today():
            payment_status = "OVERDUE"
        elif total_paid > 0:
            payment_status = "PART_PAID"
        else:
            payment_status = "UNPAID"

        results.append({
            "id": invoice.id,
            "invoice_type": invoice.invoice_type,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "entry_date": invoice.created_at,
            "due_date": invoice.due_date,
            "party_id": invoice.party_id,
            "party_name": vendor_name,
            "vendor_name": vendor_name,
            "order_id": invoice.order_id,
            "order_number": order.order_number,
            "financial_year": invoice.financial_year,
            "budget_name": budget.name if budget else None,
            "budget_type": budget.budget_type if budget else None,
            "amount": invoice_amount,
            "total_paid": total_paid,
            "balance_due": balance_due,
            "period": invoice.period,
            "location": invoice.location,
            "remarks": invoice.remarks,
            "date_sent_to_accounts": invoice.date_sent_to_accounts,
            "invoice_file_path": invoice.invoice_file_path,
            "payment_status": payment_status,
            "status": payment_status,
        })

    return results



@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    return get_order_summary(db, order)


@router.patch(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(400, "No changes provided")

    if (
        ("amount" in changes and changes["amount"] is None)
        or ("order_date" in changes and changes["order_date"] is None)
    ):
        raise HTTPException(422, "Amount and order date cannot be null")

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .one_or_none()
    )

    if order is None:
        raise HTTPException(404, "Order not found")

    if order.status != "OPEN":
        raise HTTPException(409, "Only OPEN orders can be edited")

    budget = None

    if order.order_type == "PO":
        budget = (
            db.query(Budget)
            .filter(Budget.id == order.budget_id)
            .with_for_update()
            .one_or_none()
        )

        if budget is None:
            raise HTTPException(409, "Linked budget missing")

    new_date = changes.get("order_date", order.order_date)

    try:
        validate_fy_date(order.financial_year, new_date)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    new_amount = Decimal(str(changes.get("amount", order.amount)))

    submitted_amount = Decimal(str(
        db.query(func.coalesce(func.sum(Invoice.amount), 0))
        .filter(Invoice.order_id == order.id)
        .scalar() or 0
    ))

    if new_amount < submitted_amount:
        raise HTTPException(
            422,
            "Order amount cannot be less than submitted invoice amounts",
        )

    if budget is not None:
        committed = get_committed_budget(db, budget.id, exclude_id=order.id)

        if committed + new_amount > Decimal(str(budget.approved_amount)):
            raise HTTPException(
                422,
                "Updated order exceeds approved budget",
            )

    for field, value in changes.items():
        setattr(order, field, value)

    try:
        db.commit()
        db.refresh(order)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Order update failed")

    return get_order_summary(db, order)


@router.post(
    "/{order_id}/approval",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def upload_order_approval(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    extension = Path(file.filename or "").suffix.lower()
    allowed_types = ALLOWED_APPROVAL_TYPES.get(extension)

    if allowed_types is None or file.content_type not in allowed_types:
        raise HTTPException(
            422,
            "Approval file must be a PDF or JPG/JPEG image",
        )

    content = await file.read(MAX_APPROVAL_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded file is empty")

    if len(content) > MAX_APPROVAL_SIZE:
        raise HTTPException(413, "Approval file must be 10 MB or smaller")

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF file")
    if extension in (".jpg", ".jpeg") and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, "Invalid JPEG file")

    APPROVAL_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    destination = APPROVAL_DIR / stored_name

    try:
        destination.write_bytes(content)
        previous_path = order.approval_file_path
        order.approval_file_path = str(
            Path("uploads") / "order-approvals" / stored_name
        )
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(500, "Could not save approval attachment")

    if previous_path:
        old_file = (BACKEND_DIR / previous_path).resolve()
        try:
            old_file.relative_to(APPROVAL_DIR.resolve())
            old_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    return {
        "message": "Approval attachment uploaded",
        "download_url": f"/api/orders/{order_id}/approval",
    }


@router.get("/{order_id}/approval")
def download_order_approval(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    if not order.approval_file_path:
        raise HTTPException(404, "No approval attachment found")

    stored_path = (BACKEND_DIR / order.approval_file_path).resolve()

    try:
        stored_path.relative_to(APPROVAL_DIR.resolve())
    except ValueError:
        raise HTTPException(404, "Approval attachment not found")

    if not stored_path.is_file():
        raise HTTPException(404, "Approval attachment file is missing")

    extension = stored_path.suffix.lower()

    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    return FileResponse(
        stored_path,
        media_type=media_types.get(
            extension,
            "application/octet-stream",
        ),
        headers={
            "Content-Disposition": f'inline; filename="{stored_path.name}"'
        },
    )
@router.post(
    "/{order_id}/order-copy",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def upload_order_copy(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    extension = Path(file.filename or "").suffix.lower()
    allowed_types = ALLOWED_ORDER_COPY_TYPES.get(extension)

    if allowed_types is None or file.content_type not in allowed_types:
        raise HTTPException(
            422,
            "Order copy must be a PDF, JPG/JPEG, or PNG file",
        )

    content = await file.read(MAX_ORDER_COPY_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded file is empty")

    if len(content) > MAX_ORDER_COPY_SIZE:
        raise HTTPException(413, "Order copy must be 10 MB or smaller")

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF file")

    if extension in (".jpg", ".jpeg") and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, "Invalid JPEG file")

    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(422, "Invalid PNG file")

    ORDER_COPY_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}{extension}"
    destination = ORDER_COPY_DIR / stored_name

    try:
        destination.write_bytes(content)

        previous_path = order.order_file_path

        order.order_file_path = str(
            Path("uploads") / "order-copies" / stored_name
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise HTTPException(500, "Could not save order copy")

    if previous_path:
        old_file = (BACKEND_DIR / previous_path).resolve()

        try:
            old_file.relative_to(ORDER_COPY_DIR.resolve())
            old_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    return {
        "message": "Order copy uploaded successfully",
        "view_url": f"/api/orders/{order_id}/order-copy",
    }


@router.get("/{order_id}/order-copy")
def view_order_copy(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    if not order.order_file_path:
        raise HTTPException(404, "No order copy found")

    stored_path = (BACKEND_DIR / order.order_file_path).resolve()

    try:
        stored_path.relative_to(ORDER_COPY_DIR.resolve())
    except ValueError:
        raise HTTPException(404, "Order copy not found")

    if not stored_path.is_file():
        raise HTTPException(404, "Order copy file is missing")

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
    "/{order_id}",
    status_code=204,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    linked_invoice = (
        db.query(Invoice.id)
        .filter(Invoice.order_id == order_id)
        .first()
    )

    if linked_invoice:
        raise HTTPException(
            409,
            "Cannot delete this order because an invoice is linked to it.",
        )

    approval_path = order.approval_file_path
    order_copy_path = order.order_file_path

    db.delete(order)
    db.commit()

    # Remove the stored approval attachment.
    if approval_path:
        stored_path = (BACKEND_DIR / approval_path).resolve()

        try:
            stored_path.relative_to(APPROVAL_DIR.resolve())
            stored_path.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    # Remove the stored order copy.
    if order_copy_path:
        stored_path = (BACKEND_DIR / order_copy_path).resolve()

        try:
            stored_path.relative_to(ORDER_COPY_DIR.resolve())
            stored_path.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    return None