
import logging
import hashlib
import secrets
import shutil

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.security import require_roles
from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.invoice_approval_request import InvoiceApprovalRequest
from app.models.order import Order
from app.models.party import Party
from app.models.user import User
from app.schemas.invoice import InvoiceCreate
from app.services.email_service import send_email
from app.services.invoice_excel import read_invoice_excel


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoice-approvals", tags=["Invoice Approvals"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
ORDER_COPY_DIR = BACKEND_DIR / "uploads" / "order-copies"
ORDER_APPROVAL_DIR = BACKEND_DIR / "uploads" / "order-approvals"
INVOICE_COPY_DIR = BACKEND_DIR / "uploads" / "invoice-copies"
APPROVAL_DIR = BACKEND_DIR / "uploads" / "invoice-approval"

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _relative_path(path: Path) -> str:
    return str(path.relative_to(BACKEND_DIR)).replace("\\", "/")


def _safe_stored_file(relative_path: str, allowed_dir: Path) -> Path:
    path = (BACKEND_DIR / relative_path).resolve()

    try:
        path.relative_to(allowed_dir.resolve())
    except ValueError:
        raise HTTPException(404, "Attachment file not found")

    if not path.is_file():
        raise HTTPException(404, "Attachment file is missing")

    return path


async def _read_upload(
    file: UploadFile,
    required: bool = True,
) -> tuple[bytes, str]:
    filename = Path(file.filename or "").name
    ext = Path(filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            422,
            "Attachment must be PDF, JPG/JPEG, or PNG",
        )

    expected_mime, signature = ALLOWED_EXTENSIONS[ext]

    if file.content_type != expected_mime:
        raise HTTPException(
            422,
            "Attachment MIME type does not match its file type",
        )

    content = await file.read(MAX_FILE_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Uploaded attachment is empty")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            413,
            "Each attachment must be 10 MB or smaller",
        )

    if not content.startswith(signature):
        raise HTTPException(
            422,
            "Uploaded attachment is not a valid file",
        )

    return content, ext


def _order_copy_snapshot(order: Order) -> Path:
    if not order.order_file_path:
        raise HTTPException(
            422,
            f"Order {order.order_number} has no uploaded order copy. "
            "Upload it before requesting approval.",
        )

    source = _safe_stored_file(
        order.order_file_path,
        ORDER_COPY_DIR,
    )

    destination_dir = APPROVAL_DIR / "order-copies"
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = (
        destination_dir
        / f"{uuid4().hex}{source.suffix.lower()}"
    )

    shutil.copyfile(source, destination)

    return destination


def _validate_invoice_payload(
    db: Session,
    payload: InvoiceCreate,
) -> Order:
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
            "Invoice vendor/customer must match the order",
        )

    party = db.get(Party, payload.party_id)

    if party is None:
        raise HTTPException(404, "Vendor/customer not found")

    expected_party_type = "VENDOR"

    if (party.party_type or "").strip().upper() != expected_party_type:
        raise HTTPException(
            422,
            f"Invoice requires a {expected_party_type}",
        )

    if not party.is_active:
        raise HTTPException(422, "Vendor/customer is inactive")

    if order.financial_year != payload.financial_year:
        raise HTTPException(
            422,
            "Invoice financial year must match the order",
        )

    if Decimal(str(payload.amount)) > Decimal(str(order.amount)):
        raise HTTPException(
            422,
            "Invoice amount cannot exceed the order amount",
        )

    return order


def _check_duplicate(
    db: Session,
    payload: InvoiceCreate,
) -> None:
    query = db.query(Invoice).filter(
        Invoice.invoice_type == payload.invoice_type,
        Invoice.invoice_number == payload.invoice_number,
        Invoice.party_id == payload.party_id,
    )

    if payload.invoice_type == "SERVICE":
        query = query.filter(
            Invoice.financial_year == payload.financial_year
        )

    if query.first():
        raise HTTPException(
            409,
            f"Invoice '{payload.invoice_number}' already exists",
        )


def _check_order_totals(
    db: Session,
    invoice_payloads: list[InvoiceCreate],
) -> None:
    totals: dict[int, Decimal] = {}

    for payload in invoice_payloads:
        totals[payload.order_id] = (
            totals.get(payload.order_id, Decimal("0.00"))
            + Decimal(str(payload.amount))
        )

    for order_id, proposed in totals.items():
        order = (
            db.query(Order)
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(404, "Order not found")

        from sqlalchemy import func

        existing = Decimal(
            str(
                db.query(
                    func.coalesce(func.sum(Invoice.amount), 0)
                )
                .filter(Invoice.order_id == order_id)
                .scalar()
                or 0
            )
        )

        if existing + proposed > Decimal(str(order.amount)):
            raise HTTPException(
                422,
                f"Approved invoice total would exceed order "
                f"{order.order_number}. "
                f"Available value: "
                f"{Decimal(str(order.amount)) - existing:.2f}",
            )


def _payload_from_excel_row(
    db: Session,
    row: dict[str, Any],
) -> InvoiceCreate:

    invoice_type = (
        str(row.get("invoice_type") or "")
        .strip()
        .upper()
    )

    order_number = str(
        row.get("order_number") or ""
    ).strip()

    vendor_code = str(
        row.get("vendor_code") or ""
    ).strip()

    if not order_number:
        raise HTTPException(
            422,
            "Order Number is required.",
        )

    # Find the order without assuming PO or SO.
    order = (
        db.query(Order)
        .filter(
            Order.order_number == order_number,
        )
        .first()
    )

    if order is None:
        raise HTTPException(
            422,
            f"Order '{order_number}' not found.",
        )

    # Derive invoice type from the actual order.
    if order.order_type == "PO":
        expected_invoice_type = "PURCHASE"
    elif order.order_type == "SO":
        expected_invoice_type = "SERVICE"
    else:
        raise HTTPException(
            422,
            f"Unsupported order type '{order.order_type}'.",
        )

    # If the Excel contains Invoice Type, validate it.
    # If absent, use the order's type.
    if invoice_type:
        if invoice_type not in {
            "PURCHASE",
            "SERVICE",
        }:
            raise HTTPException(
                422,
                "Invoice Type must be PURCHASE or SERVICE.",
            )

        if invoice_type != expected_invoice_type:
            raise HTTPException(
                422,
                f"Order '{order_number}' is a "
                f"{order.order_type} order and requires "
                f"a {expected_invoice_type} invoice.",
            )

    invoice_type = expected_invoice_type

    # Both PO and SO invoices must belong to vendors.
    party = (
        db.query(Party)
        .filter(
            Party.code == vendor_code,
            Party.party_type == "VENDOR",
        )
        .first()
    )

    if party is None or not party.is_active:
        raise HTTPException(
            422,
            f"Active vendor '{vendor_code}' not found.",
        )

    return InvoiceCreate(
        invoice_type=invoice_type,
        invoice_number=str(
            row.get("invoice_number") or ""
        ).strip(),
        order_id=order.id,
        party_id=party.id,
        financial_year=str(
            row.get("financial_year") or ""
        ).strip(),
        invoice_date=row["invoice_date"],
        due_date=row["due_date"],
        period=row.get("period"),
        location=row.get("location"),
        amount=Decimal(str(row["amount"])),
        description=row.get("description"),
        remarks=row.get("remarks"),
        status="UNPAID",
    )
def _validate_batch(
    db: Session,
    raw_rows: list[dict[str, Any]],
    expected_order_id: int,
) -> list[InvoiceCreate]:
    if not raw_rows:
        raise HTTPException(
            422,
            "Excel file contains no invoice rows",
        )

    if len(raw_rows) > 1000:
        raise HTTPException(
            422,
            "Maximum 1000 invoices can be submitted at once",
        )

    payloads: list[InvoiceCreate] = []
    seen: set[tuple] = set()

    for row in raw_rows:
        if not row.get("is_valid", True):
            raise HTTPException(
                422,
                "Excel contains invalid rows. "
                "Fix the preview errors first.",
            )

        payload = _payload_from_excel_row(db, row)
        order = _validate_invoice_payload(db, payload)

        if order.id != expected_order_id:
            raise HTTPException(
                422,
                "All rows in one approval batch must belong "
                "to the selected order",
            )

        key = (
            payload.invoice_type,
            payload.invoice_number.casefold(),
            payload.party_id,
            (
                payload.financial_year
                if payload.invoice_type == "SERVICE"
                else None
            ),
        )

        if key in seen:
            raise HTTPException(
                409,
                f"Duplicate invoice '{payload.invoice_number}' "
                "in the Excel file",
            )

        seen.add(key)
        _check_duplicate(db, payload)
        payloads.append(payload)

    _check_order_totals(db, payloads)

    return payloads


def _invoice_payload_json(
    payload: InvoiceCreate,
) -> dict[str, Any]:
    data = payload.model_dump(mode="json")

    # Status is not user-controlled. Official invoices begin unpaid.
    data["status"] = "UNPAID"

    return data


def _approval_email_html(
    request_id: int,
    token: str,
    request_type: str,
    count: int,
    order_number: str,
) -> str:
    settings = get_settings()

    base_url = (
        settings.public_backend_url
        or "http://127.0.0.1:8000"
    ).rstrip("/")

    review_url = (
        f"{base_url}/api/invoice-approvals/review/{token}"
    )

    kind = (
        "single invoice"
        if request_type == "MANUAL"
        else f"Excel batch ({count} invoices)"
    )

    return f"""
    <div style="font-family:Arial,sans-serif;color:#1f2937;max-width:640px">
      <h2>Invoice approval required</h2>
      <p>An invoice approval request has been submitted for your review.</p>
      <table style="border-collapse:collapse">
        <tr>
          <td style="padding:6px 14px 6px 0"><b>Request ID</b></td>
          <td>{request_id}</td>
        </tr>
        <tr>
          <td style="padding:6px 14px 6px 0"><b>Type</b></td>
          <td>{escape(kind)}</td>
        </tr>
        <tr>
          <td style="padding:6px 14px 6px 0"><b>Order</b></td>
          <td>{escape(order_number)}</td>
        </tr>
      </table>
      <p>The order copy, order approval copy (if available), and supporting invoice file are attached.</p>
      <p>
        <a href="{escape(review_url, quote=True)}"
          style="display:inline-block;background:#123b63;color:white;
          padding:12px 20px;text-decoration:none;border-radius:5px">
          Review and decide
        </a>
      </p>
      <p>This secure link expires in 24 hours and can be used only once.</p>
    </div>
    """


def _send_request_email(
    request: InvoiceApprovalRequest,
    token: str,
    order: Order,
) -> None:
    order_number = order.order_number
    settings = get_settings()

    if not settings.it_head_email:
        raise RuntimeError("IT_HEAD_EMAIL is not configured")

    attachments = []

    order_path = _safe_stored_file(
        request.order_copy_path,
        APPROVAL_DIR / "order-copies",
    )

    attachments.append({
        "filename": f"Order_{order_number}{order_path.suffix}",
        "content": order_path.read_bytes(),
        "maintype": (
            "application"
            if order_path.suffix.lower() == ".pdf"
            else "image"
        ),
        "subtype": (
            "pdf"
            if order_path.suffix.lower() == ".pdf"
            else (
                "jpeg"
                if order_path.suffix.lower() in (".jpg", ".jpeg")
                else "png"
            )
        ),
    })

    # Attach the separately uploaded Order Approval Copy from the Order record.
    # It is optional: invoice approval can still be requested if no approval
    # copy has been uploaded for this order.
    if order.approval_file_path:
        order_approval_path = _safe_stored_file(
            order.approval_file_path,
            ORDER_APPROVAL_DIR,
        )
        approval_extension = order_approval_path.suffix.lower()
        approval_mime = ALLOWED_EXTENSIONS.get(approval_extension)

        if approval_mime is None:
            raise RuntimeError(
                f"Unsupported Order Approval Copy file type: {approval_extension}"
            )

        attachments.append({
            "filename": f"Order_Approval_{order_number}{approval_extension}",
            "content": order_approval_path.read_bytes(),
            "maintype": "application" if approval_extension == ".pdf" else "image",
            "subtype": (
                "pdf" if approval_extension == ".pdf"
                else "jpeg" if approval_extension in (".jpg", ".jpeg")
                else "png"
            ),
        })

    if (
        request.request_type == "MANUAL"
        and request.invoice_copy_path
    ):
        invoice_path = _safe_stored_file(
            request.invoice_copy_path,
            APPROVAL_DIR / "invoice-copies",
        )

        attachments.append({
            "filename": f"Invoice_{request.id}{invoice_path.suffix}",
            "content": invoice_path.read_bytes(),
            "maintype": (
                "application"
                if invoice_path.suffix.lower() == ".pdf"
                else "image"
            ),
            "subtype": (
                "pdf"
                if invoice_path.suffix.lower() == ".pdf"
                else (
                    "jpeg"
                    if invoice_path.suffix.lower() in (".jpg", ".jpeg")
                    else "png"
                )
            ),
        })

    if (
        request.request_type == "BULK"
        and request.excel_file_path
    ):
        excel_path = _safe_stored_file(
            request.excel_file_path,
            APPROVAL_DIR / "excel-files",
        )

        attachments.append({
            "filename": f"Invoice_Batch_{request.id}{excel_path.suffix}",
            "content": excel_path.read_bytes(),
            "maintype": "application",
            "subtype": (
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        })

    count = (
        len(request.invoice_data)
        if isinstance(request.invoice_data, list)
        else 1
    )

    send_email(
        recipient=settings.it_head_email,
        subject=(
            f"Invoice approval required — Request #{request.id}"
        ),
        html_body=_approval_email_html(
            request.id,
            token,
            request.request_type,
            count,
            order_number,
        ),
        attachments=attachments,
    )


def _create_request(
    db: Session,
    *,
    order: Order,
    request_type: str,
    invoice_data: dict | list,
    order_copy_snapshot: Path,
    invoice_copy_path: Path | None,
    excel_path: Path | None,
    requester: User,
) -> tuple[InvoiceApprovalRequest, str]:
    settings = get_settings()

    if not settings.it_head_email:
        raise HTTPException(
            500,
            "IT_HEAD_EMAIL is not configured in backend .env",
        )

    raw_token = secrets.token_urlsafe(32)

    request = InvoiceApprovalRequest(
        order_id=order.id,
        request_type=request_type,
        status="PENDING",
        invoice_data=invoice_data,
        order_copy_path=_relative_path(order_copy_snapshot),
        invoice_copy_path=(
            _relative_path(invoice_copy_path)
            if invoice_copy_path
            else None
        ),
        excel_file_path=(
            _relative_path(excel_path)
            if excel_path
            else None
        ),
        requested_by_id=requester.id,
        approval_token_hash=_token_hash(raw_token),
        approval_token_expires_at=(
            _utc_now() + timedelta(hours=24)
        ),
    )

    db.add(request)
    db.commit()
    db.refresh(request)

    try:
        _send_request_email(
            request,
            raw_token,
            order,
        )
    except Exception:
        request.status = "REJECTED"
        request.remarks = (
            "Approval email could not be sent; "
            "request closed automatically."
        )
        request.decided_at = _utc_now()
        request.approval_token_hash = None
        request.approval_token_used_at = _utc_now()
        db.commit()

        raise HTTPException(
            502,
            "Could not send approval email. "
            "Please check SMTP configuration and try again.",
        )

    return request, raw_token


@router.get(
    "/template",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def download_invoice_import_template(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    vendor = db.get(Party, order.party_id)

    if vendor is None or vendor.party_type != "VENDOR":
        raise HTTPException(404, "Order vendor not found")

    invoice_type = (
        "PURCHASE" if order.order_type == "PO" else "SERVICE"
    )

    workbook = Workbook()

    # Main import sheet: the parser reads the active sheet.
    worksheet = workbook.active
    worksheet.title = "Invoice Import"

    headers = [
        "Invoice Type",
        "Invoice Number",
        "Order Number",
        "Vendor Code",
        "Financial Year",
        "Invoice Date",
        "Due Date",
        "Amount",
        "Period",
        "Location",
        "Description",
        "Remarks",
    ]

    worksheet.append(headers)

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="17365D",
    )
    header_font = Font(
        bold=True,
        color="FFFFFF",
    )

    thin_grey = Side(
        style="thin",
        color="D9E2F3",
    )

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )
        cell.border = Border(bottom=thin_grey)

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = "A1:L1001"

    column_widths = {
        "A": 18,
        "B": 22,
        "C": 22,
        "D": 18,
        "E": 18,
        "F": 16,
        "G": 16,
        "H": 18,
        "I": 18,
        "J": 22,
        "K": 32,
        "L": 32,
    }

    for column, width in column_widths.items():
        worksheet.column_dimensions[column].width = width

    # Allow only the two supported invoice types.
    invoice_type_validation = DataValidation(
        type="list",
        formula1='"PURCHASE,SERVICE"',
        allow_blank=True,
    )
    invoice_type_validation.error = (
        "Select PURCHASE or SERVICE."
    )
    invoice_type_validation.errorTitle = "Invalid Invoice Type"
    invoice_type_validation.showErrorMessage = True
    worksheet.add_data_validation(invoice_type_validation)
    invoice_type_validation.add("A2:A1001")

    # Date and amount formats for rows users fill in.
    for row_number in range(2, 1002):
        worksheet[f"F{row_number}"].number_format = "DD-MM-YYYY"
        worksheet[f"G{row_number}"].number_format = "DD-MM-YYYY"
        worksheet[f"H{row_number}"].number_format = '#,##0.00'

    # Separate example sheet: never read by the import parser.
    example = workbook.create_sheet("Example")

    example.append(headers)
    example.append([
        invoice_type,
        "INV-EXAMPLE-001",
        order.order_number,
        vendor.code,
        order.financial_year or "",
        "12-11-2026",
        "12-12-2026",
        1000.00,
        "November 2026",
        order.location or "",
        "Example invoice description",
        "Example remarks",
    ])

    for cell in example[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    for column, width in column_widths.items():
        example.column_dimensions[column].width = width

    example.freeze_panes = "A2"

    example["F2"].number_format = "DD-MM-YYYY"
    example["G2"].number_format = "DD-MM-YYYY"
    example["H2"].number_format = '#,##0.00'

    example["A4"] = "IMPORTANT"
    example["A4"].font = Font(
        bold=True,
        color="C00000",
    )
    example["A5"] = (
        "The Example sheet is for reference only. "
        "Enter your actual invoices in the Invoice Import sheet."
    )
    example.merge_cells("A5:L5")
    example["A5"].alignment = Alignment(
        wrap_text=True,
        vertical="center",
    )
    example.row_dimensions[5].height = 32

    example["A7"] = "Required columns"
    example["A7"].font = Font(bold=True)
    example["A8"] = (
        "Invoice Number, Order Number, Vendor Code, "
        "Invoice Date, Due Date and Amount"
    )
    example.merge_cells("A8:L8")
    example["A8"].alignment = Alignment(wrap_text=True)

    example["A10"] = "Optional columns"
    example["A10"].font = Font(bold=True)
    example["A11"] = (
        "Invoice Type, Financial Year, Period, Location, "
        "Description and Remarks"
    )
    example.merge_cells("A11:L11")
    example["A11"].alignment = Alignment(wrap_text=True)

    example["A13"] = "Date format"
    example["A13"].font = Font(bold=True)
    example["B13"] = "DD-MM-YYYY or YYYY-MM-DD"

    example["A14"] = "Amount format"
    example["A14"].font = Font(bold=True)
    example["B14"] = "Positive number, up to 2 decimal places"

    example["A15"] = "Financial Year"
    example["A15"].font = Font(bold=True)
    example["B15"] = (
        "YYYY-YYYY format. Leave blank to derive it from Invoice Date."
    )

    example["A16"] = "Invoice Type"
    example["A16"].font = Font(bold=True)
    example["B16"] = (
        "PURCHASE or SERVICE. Leave blank to derive it from the order."
    )

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    workbook.close()

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="Invoice_Bulk_Import_Template.xlsx"'
            )
        },
    )



@router.post(
    "/manual",
    status_code=201,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def submit_manual_invoice_for_approval(
    payload_json: str = Form(...),
    invoice_copy: UploadFile = File(...),
    db: Session = Depends(get_db),
    requester: User = Depends(
        require_roles("ADMIN", "ACCOUNTS")
    ),
):
    try:
        payload = InvoiceCreate.model_validate_json(payload_json)
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors())

    order = _validate_invoice_payload(db, payload)

    _check_duplicate(db, payload)
    _check_order_totals(db, [payload])

    invoice_content, invoice_ext = await _read_upload(
        invoice_copy
    )

    if not order.order_file_path:
        raise HTTPException(
            422,
            f"Order {order.order_number} has no uploaded order copy.",
        )

    approval_order_dir = APPROVAL_DIR / "order-copies"
    approval_invoice_dir = APPROVAL_DIR / "invoice-copies"

    approval_order_dir.mkdir(parents=True, exist_ok=True)
    approval_invoice_dir.mkdir(parents=True, exist_ok=True)

    order_snapshot = _order_copy_snapshot(order)

    invoice_path = (
        approval_invoice_dir
        / f"{uuid4().hex}{invoice_ext}"
    )

    invoice_path.write_bytes(invoice_content)

    try:
        request, _ = _create_request(
            db,
            order=order,
            request_type="MANUAL",
            invoice_data=_invoice_payload_json(payload),
            order_copy_snapshot=order_snapshot,
            invoice_copy_path=invoice_path,
            excel_path=None,
            requester=requester,
        )
    except Exception:
        order_snapshot.unlink(missing_ok=True)
        invoice_path.unlink(missing_ok=True)
        raise

    return {
        "message": "Invoice approval request sent to IT Head.",
        "approval_request_id": request.id,
        "status": request.status,
    }


@router.post(
    "/bulk",
    status_code=201,
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def submit_bulk_invoice_for_approval(
    order_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    requester: User = Depends(
        require_roles("ADMIN", "ACCOUNTS")
    ),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(404, "Order not found")

    if not order.order_file_path:
        raise HTTPException(
            422,
            f"Order {order.order_number} has no uploaded order copy.",
        )

    filename = (file.filename or "").lower()

    if not filename.endswith(".xlsx"):
        raise HTTPException(
            422,
            "Please upload an Excel .xlsx file",
        )

    content = await file.read(MAX_FILE_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(422, "Excel file is empty")

    if len(content) > MAX_FILE_SIZE:
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

    payloads = _validate_batch(
        db,
        preview.get("rows", []),
        order_id,
    )

    invoice_json = [
        _invoice_payload_json(payload)
        for payload in payloads
    ]

    excel_dir = APPROVAL_DIR / "excel-files"
    excel_dir.mkdir(parents=True, exist_ok=True)

    excel_path = excel_dir / f"{uuid4().hex}.xlsx"
    excel_path.write_bytes(content)

    order_snapshot = _order_copy_snapshot(order)

    try:
        request, _ = _create_request(
            db,
            order=order,
            request_type="BULK",
            invoice_data=invoice_json,
            order_copy_snapshot=order_snapshot,
            invoice_copy_path=None,
            excel_path=excel_path,
            requester=requester,
        )
    except Exception:
        order_snapshot.unlink(missing_ok=True)
        excel_path.unlink(missing_ok=True)
        raise

    return {
        "message": "Bulk invoice approval request sent to IT Head.",
        "approval_request_id": request.id,
        "status": request.status,
        "invoice_count": len(invoice_json),
    }


@router.get(
    "/requests",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def get_invoice_approval_requests(
    db: Session = Depends(get_db),
):
    requests = (
        db.query(InvoiceApprovalRequest)
        .order_by(desc(InvoiceApprovalRequest.requested_at))
        .all()
    )

    results = []

    for request in requests:
        order = db.get(Order, request.order_id)
        requester = db.get(User, request.requested_by_id)

        decided_by = (
            db.get(User, request.decided_by_id)
            if request.decided_by_id
            else None
        )

        invoice_items = (
            request.invoice_data
            if isinstance(request.invoice_data, list)
            else [request.invoice_data]
        )

        results.append({
            "id": request.id,
            "order_id": request.order_id,
            "order_number": (
                order.order_number if order else "—"
            ),
            "request_type": request.request_type,
            "status": request.status,
            "invoice_count": len(invoice_items),
            "invoice_data": invoice_items,
            "requested_by": (
                requester.username if requester else "—"
            ),
            "requested_at": request.requested_at,
            "decided_by": (
                decided_by.username if decided_by else None
            ),
            "decided_at": request.decided_at,
            "remarks": request.remarks,
            "result_invoice_ids": (
                request.result_invoice_ids or []
            ),
        })

    return results


def _load_pending_request(
    db: Session,
    token: str,
    lock: bool = False,
) -> InvoiceApprovalRequest:
    digest = _token_hash(token)

    query = db.query(InvoiceApprovalRequest).filter(
        InvoiceApprovalRequest.approval_token_hash == digest
    )

    if lock:
        query = query.with_for_update()

    request = query.first()

    if request is None:
        raise HTTPException(
            404,
            "Approval link is invalid or has already been used",
        )

    if (
        request.status != "PENDING"
        or request.approval_token_used_at is not None
    ):
        raise HTTPException(
            410,
            "This approval request has already been decided",
        )

    expiry = request.approval_token_expires_at

    if expiry is None:
        raise HTTPException(
            410,
            "Approval link has expired",
        )

    # MySQL may return timezone-aware columns as naive datetimes.
    # Treat those values as UTC before comparing.
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if expiry < _utc_now():
        raise HTTPException(
            410,
            "Approval link has expired",
        )

    return request


def _review_html(
    request: InvoiceApprovalRequest,
    token: str,
    message: str = "",
) -> str:
    rows = (
        request.invoice_data
        if isinstance(request.invoice_data, list)
        else [request.invoice_data]
    )

    details = []

    for item in rows[:1000]:
        details.append(
            "<tr>"
            f"<td>{escape(str(item.get('invoice_number', '')))}</td>"
            f"<td>{escape(str(item.get('invoice_type', '')))}</td>"
            f"<td>{escape(str(item.get('invoice_date', '')))}</td>"
            f"<td style='text-align:right'>"
            f"{escape(str(item.get('amount', '')))}</td>"
            "</tr>"
        )

    total = sum(
        (
            Decimal(str(item.get("amount", 0)))
            for item in rows
        ),
        Decimal("0.00"),
    )

    note = (
        f"<p style='color:#b91c1c'>{escape(message)}</p>"
        if message
        else ""
    )

    return f"""<!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width">
    <title>Invoice Approval</title>
    </head>
    <body style="font-family:Arial,sans-serif;background:#f3f6fa;
    padding:24px;color:#172033">
    <main style="max-width:900px;margin:auto;background:white;
    padding:28px;border-radius:10px">
    <h1>Invoice approval review</h1>{note}
    <p><b>Request:</b> #{request.id} &nbsp;
    <b>Type:</b> {escape(request.request_type)} &nbsp;
    <b>Invoice count:</b> {len(rows)}</p>
    <p><b>Batch total:</b> {total:,.2f}</p>
    <table style="width:100%;border-collapse:collapse">
    <thead><tr>
    <th style="text-align:left;border-bottom:1px solid #ddd;padding:8px">
    Invoice number</th>
    <th style="text-align:left;border-bottom:1px solid #ddd;padding:8px">
    Type</th>
    <th style="text-align:left;border-bottom:1px solid #ddd;padding:8px">
    Invoice date</th>
    <th style="text-align:right;border-bottom:1px solid #ddd;padding:8px">
    Amount</th>
    </tr></thead>
    <tbody>{''.join(details)}</tbody>
    </table>
    <p>Approving will create all invoice records in this request.
    Bulk requests are approved as one unit.</p>
    <form method="post"
    action="/api/invoice-approvals/decide/{escape(token, quote=True)}">
    <label for="remarks">Remarks (optional)</label><br>
    <textarea id="remarks" name="remarks" rows="3"
    style="width:100%;margin:8px 0 16px"></textarea><br>
    <button name="decision" value="approve"
    style="background:#166534;color:white;padding:12px 22px;
    border:0;border-radius:5px">Approve</button>
    <button name="decision" value="reject"
    style="background:#991b1b;color:white;padding:12px 22px;
    border:0;border-radius:5px;margin-left:10px">Reject</button>
    </form>
    </main>
    </body>
    </html>"""


@router.get("/review/{token}", response_class=HTMLResponse)
def review_invoice_approval(
    token: str,
    db: Session = Depends(get_db),
):
    request = _load_pending_request(db, token)

    return HTMLResponse(
        _review_html(request, token)
    )


@router.post("/decide/{token}", response_class=HTMLResponse)
def decide_invoice_approval(
    token: str,
    decision: str = Form(...),
    remarks: str = Form(""),
    db: Session = Depends(get_db),
):
    decision = decision.strip().lower()

    if decision not in ("approve", "reject"):
        raise HTTPException(
            422,
            "Decision must be approve or reject",
        )

    request = _load_pending_request(
        db,
        token,
        lock=True,
    )

    requester = db.get(User, request.requested_by_id)

    order = (
        db.query(Order)
        .filter(Order.id == request.order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            409,
            "Related order no longer exists",
        )

    now = _utc_now()

    if decision == "reject":
        request.status = "REJECTED"
        request.remarks = (
            remarks.strip()
            or "Rejected by IT Head via email approval link"
        )
        request.decided_at = now
        request.approval_token_used_at = now
        request.approval_token_hash = None

        db.commit()

        _notify_requester(
            requester,
            request,
            approved=False,
            remarks=request.remarks,
        )

        return HTMLResponse(
            "<h2>Invoice approval request rejected.</h2>"
            "<p>You may close this page.</p>"
        )

    try:
        raw_items = (
            request.invoice_data
            if isinstance(request.invoice_data, list)
            else [request.invoice_data]
        )

        payloads = [
            InvoiceCreate.model_validate(item)
            for item in raw_items
        ]

        if any(
            payload.order_id != request.order_id
            for payload in payloads
        ):
            raise HTTPException(
                422,
                "Approval request contains an unexpected order",
            )

        for payload in payloads:
            _validate_invoice_payload(db, payload)
            _check_duplicate(db, payload)

        _check_order_totals(db, payloads)

        created_ids = []

        for payload in payloads:
            data = payload.model_dump()
            data["status"] = "UNPAID"
            data["invoice_file_path"] = None

            # Copy manual invoice attachment to the official
            # invoice-copy directory only after IT Head approval.
            if (
                request.request_type == "MANUAL"
                and request.invoice_copy_path
            ):
                approval_file = _safe_stored_file(
                    request.invoice_copy_path,
                    APPROVAL_DIR / "invoice-copies",
                )

                INVOICE_COPY_DIR.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                official_file = (
                    INVOICE_COPY_DIR
                    / f"{uuid4().hex}{approval_file.suffix.lower()}"
                )

                shutil.copyfile(
                    approval_file,
                    official_file,
                )

                data["invoice_file_path"] = _relative_path(
                    official_file
                )

            invoice = Invoice(**data)

            db.add(invoice)
            db.flush()

            created_ids.append(invoice.id)

        request.status = "APPROVED"
        request.result_invoice_ids = created_ids
        request.remarks = (
            remarks.strip()
            or "Approved by IT Head via email approval link"
        )
        request.decided_at = now
        request.approval_token_used_at = now
        request.approval_token_hash = None

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            409,
            "Approval failed because an invoice duplicate or "
            "data conflict was detected. No invoices were created.",
        )

    except Exception:
        db.rollback()

        raise HTTPException(
            500,
            "Approval failed. No invoices were created.",
        )

    # Notify the requester after the approval has been committed.
    _notify_requester(
        requester,
        request,
        approved=True,
        remarks=request.remarks,
    )

    # Send exactly one Accounts notification after approval.
    logger.info(
        "APPROVAL DEBUG: Calling Accounts notification. "
        "Request ID: %s, Invoice IDs: %s",
        request.id,
        created_ids,
    )

    _notify_accounts_after_approval(
        db,
        request,
        order,
        created_ids,
    )

    logger.info(
        "APPROVAL DEBUG: Accounts notification function returned. "
        "Request ID: %s",
        request.id,
    )

    return HTMLResponse(
        f"<h2>Approved successfully.</h2>"
        f"<p>{len(created_ids)} invoice(s) created.</p>"
        f"<p>You may close this page.</p>"
    )


def _notify_requester(
    requester: User | None,
    request: InvoiceApprovalRequest,
    *,
    approved: bool,
    remarks: str,
) -> None:
    if not requester or not requester.email:
        return

    status_text = "approved" if approved else "rejected"

    count = (
        len(request.result_invoice_ids or [])
        if approved
        else (
            len(request.invoice_data)
            if isinstance(request.invoice_data, list)
            else 1
        )
    )

    body = f"""
    <div style="font-family:Arial,sans-serif">
      <h2>Invoice approval {status_text}</h2>
      <p>Your invoice approval request #{request.id} was
      {status_text} by the IT Head.</p>
      <p><b>Invoice count:</b> {count}</p>
      <p><b>Remarks:</b> {escape(remarks or "—")}</p>
    </div>
    """

    try:
        send_email(
            recipient=requester.email,
            subject=(
                f"Invoice approval {status_text} — Request #{request.id}"
            ),
            html_body=body,
        )

    except Exception:
        # Approval is already committed. Notification failure
        # must not undo the approval or cause a second attempt.
        logger.exception(
            "Failed to send requester notification for approval "
            "request %s",
            request.id,
        )


def _notify_accounts_after_approval(
    db: Session,
    request: InvoiceApprovalRequest,
    order: Order,
    created_ids: list[int],
) -> None:
    settings = get_settings()

    accounts_email = settings.accounts_email

    logger.info(
        "APPROVAL DEBUG: Accounts recipient loaded: %r",
        accounts_email,
    )

    if not accounts_email:
        logger.warning(
            "Accounts notification skipped: "
            "ACCOUNTS_EMAIL is not configured."
        )
        return

    try:
        invoices = (
            db.query(Invoice)
            .filter(Invoice.id.in_(created_ids))
            .all()
        )

        vendor = (
            db.query(Party)
            .filter(Party.id == order.party_id)
            .first()
        )

        vendor_name = (
            vendor.name if vendor else "Unknown vendor"
        )

        invoice_rows = ""

        for invoice in invoices:
            invoice_rows += (
                "<tr>"
                f"<td>{escape(invoice.invoice_number or '')}</td>"
                f"<td>{escape(str(invoice.invoice_date or ''))}</td>"
                f"<td>{escape(str(invoice.amount))}</td>"
                "</tr>"
            )

        subject = (
            "Invoice Approval Completed - "
            f"Order {order.order_number}"
        )

        html_body = f"""
        <html>
        <body>
            <h2>Invoice Approval Completed</h2>

            <p>The IT Head has approved the invoice request.</p>

            <p>
                <strong>Request ID:</strong> {request.id}<br>
                <strong>Order Number:</strong>
                {escape(order.order_number)}<br>
                <strong>Vendor:</strong> {escape(vendor_name)}<br>
                <strong>Approved Invoice Count:</strong>
                {len(invoices)}
            </p>

            <table border="1" cellpadding="6" cellspacing="0">
                <thead>
                    <tr>
                        <th>Invoice Number</th>
                        <th>Invoice Date</th>
                        <th>Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {invoice_rows}
                </tbody>
            </table>

            <p>
                <strong>Remarks:</strong>
                {escape(request.remarks or "No remarks")}
            </p>

            <p>Please proceed with the necessary Accounts processing.</p>
        </body>
        </html>
        """

        logger.info(
            "APPROVAL DEBUG: Sending Accounts email. "
            "Request ID: %s, Recipient: %r, Invoice count: %s",
            request.id,
            accounts_email,
            len(invoices),
        )

        send_email(
            recipient=accounts_email,
            subject=subject,
            html_body=html_body,
        )

        logger.info(
            "APPROVAL DEBUG: Accounts email send_email completed. "
            "Request ID: %s",
            request.id,
        )

    except Exception:
        logger.exception(
            "Failed to send Accounts notification for approval "
            "request %s",
            request.id,
        )
