
from datetime import date
from decimal import Decimal
from io import BytesIO
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
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db.session import get_db
from app.models.budget import Budget
from app.models.budget_subcategory import BudgetSubcategory
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


def normalize_vendor_name(value: str) -> str:
    return " ".join(
        str(value or "").strip().casefold().split()
    )


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


# =========================================================
# BULK ORDER IMPORT â€” EXCEL TEMPLATE DOWNLOAD
# =========================================================

# =========================================================
# BULK ORDER IMPORT â€” EXCEL TEMPLATE DOWNLOAD
# =========================================================

@router.get(
    "/import/template",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def download_order_import_template():

    workbook = Workbook()
    worksheet = workbook.active

    worksheet.title = "Order Import Template"

    headers = [
        "Order Type",
        "Order Number",
        "Vendor Code",
        "Vendor Name",
        "Budget Name",
        "Subcategory",
        "Financial Year",
        "Order Date",
        "Amount",
        "Approved By",
        "Order Period",
        "Location",
        "Materials Description",
    ]

    worksheet.append(headers)

    # -----------------------------------------------------
    # Demo row
    # -----------------------------------------------------

    worksheet.append([
        "PO",
        "DEMO-PO-001",
        "DEMO-V001",
        "Demo Vendor Name",
        "Demo CAPEX Budget",
        "",
        "2026-2027",
        "2026-11-18",
        100000,
        "Demo Approver",
        "Nov 2026",
        "Kolkata",
        "Demo material description - replace or leave blank",
    ])

    # -----------------------------------------------------
    # Header styling
    # -----------------------------------------------------

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="17365D",
    )

    header_font = Font(
        bold=True,
        color="FFFFFF",
    )

    for cell in worksheet[1]:

        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    worksheet.row_dimensions[1].height = 30

    # -----------------------------------------------------
    # Demo row styling
    # -----------------------------------------------------

    demo_fill = PatternFill(
        fill_type="solid",
        fgColor="FFF2CC",
    )

    for cell in worksheet[2]:

        cell.fill = demo_fill
        cell.alignment = Alignment(
            vertical="center",
        )

    # -----------------------------------------------------
    # Column widths
    # -----------------------------------------------------

    column_widths = {
        "A": 15,
        "B": 22,
        "C": 18,
        "D": 30,
        "E": 30,
        "F": 30,
        "G": 18,
        "H": 18,
        "I": 18,
        "J": 25,
        "K": 20,
        "L": 22,
        "M": 45,
    }

    for column, width in column_widths.items():

        worksheet.column_dimensions[column].width = width

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    # -----------------------------------------------------
    # Date format
    # -----------------------------------------------------

    worksheet["H2"].number_format = "yyyy-mm-dd"

    # -----------------------------------------------------
    # Instructions sheet
    # -----------------------------------------------------

    instructions = workbook.create_sheet(
        "Instructions"
    )

    instruction_rows = [
        ["BULK ORDER IMPORT INSTRUCTIONS"],
        [""],
        ["Required columns"],
        [
            "Order Type",
            "PO for CAPEX orders or SO for OPEX orders",
        ],
        [
            "Order Number",
            "Unique order number",
        ],
        [
            "Vendor Code",
            "Vendor code",
        ],
        [
            "Vendor Name",
            "Vendor name",
        ],
        [
            "Budget Name",
            "Existing budget name matching the order type",
        ],
        [
            "Subcategory",
            "Required for SO orders. Must match an approved "
            "subcategory under the selected OPEX budget. "
            "Leave blank for PO orders.",
        ],
        [
            "Financial Year",
            "Example: 2026-2027",
        ],
        [
            "Order Date",
            "Format: YYYY-MM-DD",
        ],
        [
            "Amount",
            "Order amount greater than zero",
        ],
        [
            "Approved By",
            "Name of the person who approved the order. "
            "Required for both PO and SO.",
        ],
        [""],
        ["Optional columns"],
        [
            "Order Period",
            "Optional order period",
        ],
        [
            "Location",
            "Optional location",
        ],
        [
            "Materials Description",
            "Optional. Leave blank if not applicable, "
            "including OPEX orders.",
        ],
        [""],
        ["IMPORTANT"],
        [
            "Replace the demo row with your actual order data "
            "before importing."
        ],
        [
            "Vendor codes and names must match if the vendor "
            "already exists."
        ],
        [
            "New vendors can be created automatically during "
            "import confirmation."
        ],
        [
            "Budget Name must match an existing budget for "
            "the selected financial year and order type."
        ],
        [
            "PO orders must use CAPEX budgets and must not "
            "contain a subcategory."
        ],
        [
            "SO orders must use OPEX budgets and must contain "
            "a valid approved subcategory."
        ],
        [
            "Approved By is mandatory for every order."
        ],
        [
            "Materials Description is optional."
        ],
    ]

    for row in instruction_rows:

        instructions.append(row)

    instructions.column_dimensions["A"].width = 35
    instructions.column_dimensions["B"].width = 110

    instructions["A1"].font = Font(
        bold=True,
        size=16,
        color="17365D",
    )

    for row in instructions.iter_rows():

        for cell in row:

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    # -----------------------------------------------------
    # Generate Excel file
    # -----------------------------------------------------

    file_buffer = BytesIO()

    workbook.save(file_buffer)

    file_buffer.seek(0)

    return StreamingResponse(
        file_buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                'attachment; filename="Bulk_Order_Import_Template.xlsx"'
            )
        },
    )

# =========================================================
# BULK ORDER IMPORT â€” PREVIEW
# =========================================================


@router.post(
    "/import/preview",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
async def preview_order_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    from app.models.budget_subcategory_approval_request import (
        BudgetSubcategoryApprovalRequest,
    )

    # -----------------------------------------------------
    # File validation
    # -----------------------------------------------------

    if Path(file.filename or "").suffix.lower() != ".xlsx":

        raise HTTPException(
            422,
            "Please upload an Excel .xlsx file",
        )

    content = await file.read(
        10 * 1024 * 1024 + 1
    )

    await file.close()

    if not content:

        raise HTTPException(
            422,
            "Uploaded Excel file is empty",
        )

    if len(content) > 10 * 1024 * 1024:

        raise HTTPException(
            413,
            "Excel file must be 10 MB or smaller",
        )

    try:

        result = read_order_excel(content)

    except ValueError as exc:

        raise HTTPException(
            422,
            str(exc),
        )

    # -----------------------------------------------------
    # Tracking
    # -----------------------------------------------------

    seen_order_numbers = set()
    seen_vendor_codes = {}

    requested_by_budget = {}
    requested_by_subcategory = {}

    # -----------------------------------------------------
    # Helpers
    # -----------------------------------------------------

    def money(value):

        value = Decimal(
            str(value or 0)
        ).quantize(
            Decimal("0.01")
        )

        return f"â‚¹{value:,.2f}"

    def normalized(value):

        return str(
            value or ""
        ).strip().casefold()

    # -----------------------------------------------------
    # Validate individual rows
    # -----------------------------------------------------

    for row in result["rows"]:

        errors = row["errors"]

        order_type = row["order_type"]
        order_number = row["order_number"]

        vendor_code = row["vendor_code"]
        vendor_name = row["vendor_name"]

        budget_name = row["budget_name"]

        budget_subcategory_name = (
            row.get("budget_subcategory_name")
        )

        approved_by = row.get("approved_by")

        financial_year = row["financial_year"]

        row["vendor_status"] = None
        row["vendor_id"] = None

        row["budget_id"] = None
        row["budget_subcategory_id"] = None

        row["budget_subcategory_approved_amount"] = None

        # -------------------------------------------------
        # Approved By validation
        # -------------------------------------------------

        if not approved_by or not str(approved_by).strip():

            errors.append(
                "Approved By is required for both Purchase "
                "Orders (PO) and Service Orders (SO)."
            )

        # -------------------------------------------------
        # Order type validation
        # -------------------------------------------------

        if order_type not in ("PO", "SO"):

            errors.append(
                "Order type must be PO or SO."
            )

        # -------------------------------------------------
        # Duplicate order validation
        # -------------------------------------------------

        if order_type and order_number:

            duplicate_key = (
                order_type,
                str(order_number).strip().upper(),
            )

            if duplicate_key in seen_order_numbers:

                errors.append(
                    "Duplicate order number within this Excel file."
                )

            else:

                seen_order_numbers.add(
                    duplicate_key
                )

            existing_order = (
                db.query(Order.id)
                .filter(
                    Order.order_type == order_type,
                    Order.order_number
                    == str(order_number).strip(),
                )
                .first()
            )

            if existing_order:

                errors.append(
                    "This order number already exists."
                )

        # -------------------------------------------------
        # Vendor validation
        # -------------------------------------------------

        if vendor_code and vendor_name:

            vendor_code = str(
                vendor_code
            ).strip().upper()

            normalized_name = normalize_vendor_name(
                vendor_name
            )

            previous_name = seen_vendor_codes.get(
                vendor_code
            )

            if previous_name is not None:

                if previous_name != normalized_name:

                    errors.append(
                        f"Vendor code '{vendor_code}' is associated "
                        "with different vendor names in this Excel file."
                    )

            else:

                seen_vendor_codes[vendor_code] = (
                    normalized_name
                )

            vendor = (
                db.query(Party)
                .filter(
                    Party.code == vendor_code,
                    Party.party_type == "VENDOR",
                )
                .one_or_none()
            )

            if vendor is not None:

                if not vendor.is_active:

                    errors.append(
                        f"Vendor '{vendor_code}' is inactive."
                    )

                elif normalize_vendor_name(
                    vendor.name
                ) != normalized_name:

                    errors.append(
                        f"Vendor code '{vendor_code}' already exists "
                        f"with name '{vendor.name}', but Excel contains "
                        f"'{vendor_name}'."
                    )

                else:

                    row["vendor_id"] = vendor.id
                    row["vendor_status"] = "EXISTING"

            else:

                row["vendor_status"] = "NEW"

        # -------------------------------------------------
        # Budget validation
        # -------------------------------------------------

        budget = None

        if (
            budget_name
            and financial_year
            and order_type in ("PO", "SO")
        ):

            required_type = expected_budget_type(
                order_type
            )

            budget = (
                db.query(Budget)
                .filter(
                    func.lower(Budget.name)
                    == normalized(budget_name),
                    Budget.financial_year
                    == financial_year,
                    Budget.budget_type
                    == required_type,
                )
                .one_or_none()
            )

            if budget is None:

                if order_type == "PO":

                    errors.append(
                        f"CAPEX budget '{budget_name}' not found "
                        f"for the selected financial year."
                    )

                else:

                    errors.append(
                        f"OPEX budget '{budget_name}' not found "
                        f"for the selected financial year. "
                        f"Please create and approve the budget "
                        f"before importing."
                    )

            else:

                row["budget_id"] = budget.id

        # -------------------------------------------------
        # PO subcategory validation
        # -------------------------------------------------

        if order_type == "PO":

            if budget_subcategory_name:

                errors.append(
                    "Subcategory is not applicable for Purchase "
                    "Orders (PO). Please leave this field blank."
                )

            row["budget_subcategory_name"] = None
            row["budget_subcategory_id"] = None

        # -------------------------------------------------
        # SO subcategory validation
        # -------------------------------------------------

        elif order_type == "SO":

            if not budget_subcategory_name:

                errors.append(
                    "Subcategory is required for Service Orders (SO)."
                )

            elif budget is not None:

                subcategory = (
                    db.query(BudgetSubcategory)
                    .filter(
                        BudgetSubcategory.budget_id
                        == budget.id,
                        func.lower(
                            BudgetSubcategory.name
                        )
                        == normalized(
                            budget_subcategory_name
                        ),
                    )
                    .one_or_none()
                )

                # -----------------------------------------
                # Subcategory not found under selected parent
                # -----------------------------------------

                if subcategory is None:

                    # Check whether the name exists under
                    # another OPEX budget for the same FY.

                    wrong_parent = (
                        db.query(
                            BudgetSubcategory,
                            Budget,
                        )
                        .join(
                            Budget,
                            Budget.id
                            == BudgetSubcategory.budget_id,
                        )
                        .filter(
                            func.lower(
                                BudgetSubcategory.name
                            )
                            == normalized(
                                budget_subcategory_name
                            ),
                            Budget.financial_year
                            == financial_year,
                            Budget.budget_type
                            == "OPEX",
                        )
                        .first()
                    )

                    if wrong_parent is not None:

                        errors.append(
                            f"Subcategory "
                            f"'{budget_subcategory_name}' does not "
                            f"belong to OPEX budget '{budget_name}'."
                        )

                    else:

                        pending_request = (
                            db.query(
                                BudgetSubcategoryApprovalRequest.id
                            )
                            .filter(
                                BudgetSubcategoryApprovalRequest
                                .budget_id
                                == budget.id,
                                func.lower(
                                    BudgetSubcategoryApprovalRequest
                                    .name
                                )
                                == normalized(
                                    budget_subcategory_name
                                ),
                                BudgetSubcategoryApprovalRequest
                                .status
                                == "PENDING",
                            )
                            .first()
                        )

                        if pending_request is not None:

                            errors.append(
                                f"Subcategory "
                                f"'{budget_subcategory_name}' has "
                                f"not yet been approved."
                            )

                        else:

                            errors.append(
                                f"Subcategory "
                                f"'{budget_subcategory_name}' not "
                                f"found under OPEX budget "
                                f"'{budget_name}'. Please create "
                                f"and approve the subcategory "
                                f"before importing."
                            )

                # -----------------------------------------
                # Subcategory exists under correct parent
                # -----------------------------------------

                else:

                    row["budget_subcategory_id"] = (
                        subcategory.id
                    )

                    approved_amount = Decimal(
                        str(
                            subcategory.approved_amount
                            or 0
                        )
                    )

                    row[
                        "budget_subcategory_approved_amount"
                    ] = str(
                        approved_amount
                    )

                    if approved_amount <= 0:

                        errors.append(
                            f"Subcategory "
                            f"'{budget_subcategory_name}' "
                            f"does not have an approved allocation."
                        )

        # -------------------------------------------------
        # Track PO requests
        # -------------------------------------------------

        if (
            not errors
            and order_type == "PO"
            and row["budget_id"]
            and row["amount"] is not None
        ):

            budget_id = row["budget_id"]

            requested_by_budget[budget_id] = (
                requested_by_budget.get(
                    budget_id,
                    Decimal("0.00"),
                )
                + Decimal(
                    str(row["amount"])
                )
            )

        # -------------------------------------------------
        # Track SO requests
        # -------------------------------------------------

        if (
            not errors
            and order_type == "SO"
            and row["budget_subcategory_id"]
            and row["amount"] is not None
        ):

            subcategory_id = (
                row["budget_subcategory_id"]
            )

            requested_by_subcategory[
                subcategory_id
            ] = (
                requested_by_subcategory.get(
                    subcategory_id,
                    Decimal("0.00"),
                )
                + Decimal(
                    str(row["amount"])
                )
            )

        row["is_valid"] = (
            len(errors) == 0
        )

    # =====================================================
    # COMBINED CAPEX / PO BUDGET VALIDATION
    # =====================================================

    for budget_id, requested_amount in (
        requested_by_budget.items()
    ):

        budget = db.get(
            Budget,
            budget_id,
        )

        if budget is None:
            continue

        committed = get_committed_budget(
            db,
            budget_id,
        )

        approved_amount = Decimal(
            str(
                budget.approved_amount or 0
            )
        )

        available = (
            approved_amount
            - committed
        )

        if requested_amount > available:

            for row in result["rows"]:

                if (
                    row["order_type"] == "PO"
                    and row["budget_id"] == budget_id
                    and row["is_valid"]
                ):

                    row["errors"].append(
                        "Combined PO amount in this file exceeds "
                        "available CAPEX budget. "
                        f"Approved budget: {money(approved_amount)}. "
                        f"Already committed: {money(committed)}. "
                        f"Available: {money(available)}. "
                        f"Requested: {money(requested_amount)}."
                    )

                    row["is_valid"] = False

    # =====================================================
    # COMBINED OPEX SUBCATEGORY ALLOCATION VALIDATION
    # =====================================================

    for subcategory_id, requested_amount in (
        requested_by_subcategory.items()
    ):

        subcategory = db.get(
            BudgetSubcategory,
            subcategory_id,
        )

        if subcategory is None:
            continue

        approved_amount = Decimal(
            str(
                subcategory.approved_amount or 0
            )
        )

        # -------------------------------------------------
        # Existing SO commitments
        # -------------------------------------------------

        committed = Decimal(
            str(
                db.query(
                    func.coalesce(
                        func.sum(Order.amount),
                        0,
                    )
                )
                .filter(
                    Order.budget_subcategory_id
                    == subcategory_id,
                    Order.order_type == "SO",
                    Order.status != "CANCELLED",
                )
                .scalar()
                or 0
            )
        )

        available = (
            approved_amount
            - committed
        )

        # -------------------------------------------------
        # Combined import validation
        # -------------------------------------------------

        if requested_amount > available:

            for row in result["rows"]:

                if (
                    row["order_type"] == "SO"
                    and row["budget_subcategory_id"]
                    == subcategory_id
                    and row["is_valid"]
                ):

                    row["errors"].append(
                        "Combined SO amount in this file "
                        "exceeds the available approved "
                        "allocation for this OPEX subcategory. "
                        f"Approved allocation: "
                        f"{money(approved_amount)}. "
                        f"Already committed: "
                        f"{money(committed)}. "
                        f"Available: {money(available)}. "
                        f"Requested: {money(requested_amount)}."
                    )

                    row["is_valid"] = False

    # =====================================================
    # FINAL COUNTS
    # =====================================================

    result["valid_rows"] = sum(
        1
        for row in result["rows"]
        if row["is_valid"]
    )

    result["invalid_rows"] = sum(
        1
        for row in result["rows"]
        if not row["is_valid"]
    )

    return result


# =========================================================
# BULK ORDER IMPORT â€” CONFIRM
# =========================================================

@router.post(
    "/import/confirm",
    dependencies=[Depends(require_roles("ADMIN", "ACCOUNTS"))],
)
def confirm_order_import(
    rows: list[dict] = Body(...),
    db: Session = Depends(get_db),
):
    import logging

    from app.models.budget_subcategory_approval_request import (
        BudgetSubcategoryApprovalRequest,
    )

    logger = logging.getLogger(__name__)

    if not rows:
        raise HTTPException(
            422,
            "No order rows were provided",
        )

    if len(rows) > 1000:
        raise HTTPException(
            422,
            "A maximum of 1000 orders can be imported at once",
        )

    created_orders = []
    created_vendors = []

    try:

        # -------------------------------------------------
        # Validate all rows before inserting anything
        # -------------------------------------------------

        prepared_rows = []

        seen_order_numbers = set()
        seen_vendor_codes = {}
        pending_vendors = {}

        requested_by_budget = {}
        requested_by_subcategory = {}

        def normalize_text(value):
            return str(value or "").strip().casefold()

        def money(value):
            return f"â‚¹{Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"

        for index, row in enumerate(rows, start=1):

            excel_row = row.get("excel_row", index)

            order_type = str(
                row.get("order_type", "")
            ).strip().upper()

            order_number = str(
                row.get("order_number", "")
            ).strip().upper()

            vendor_code = str(
                row.get("vendor_code", "")
            ).strip().upper()

            vendor_name = str(
                row.get("vendor_name", "")
            ).strip()

            budget_name = str(
                row.get("budget_name", "")
            ).strip()

            financial_year = str(
                row.get("financial_year", "")
            ).strip()

            subcategory_name = str(
                row.get("budget_subcategory_name")
                or row.get("subcategory")
                or row.get("Subcategory")
                or row.get("OPEX Subcategory")
                or ""
            ).strip()

            approved_by = str(
                row.get("approved_by", "")
            ).strip()

            # -------------------------------------------------
            # Required fields
            # -------------------------------------------------

            if order_type not in ("PO", "SO"):
                raise HTTPException(
                    422,
                    f"Invalid order type in Excel row {excel_row}",
                )

            if (
                not order_number
                or not vendor_code
                or not vendor_name
                or not budget_name
                or not financial_year
            ):
                raise HTTPException(
                    422,
                    f"Missing required information in Excel row {excel_row}",
                )

            if not approved_by:
                raise HTTPException(
                    422,
                    "Approved By is required for both Purchase Orders (PO) "
                    "and Service Orders (SO).",
                )

            # -------------------------------------------------
            # Order type / subcategory validation
            # -------------------------------------------------

            if order_type == "PO" and subcategory_name:

                raise HTTPException(
                    422,
                    "Subcategory is not applicable for Purchase Orders (PO). "
                    "Please leave this field blank.",
                )

            if order_type == "SO" and not subcategory_name:

                raise HTTPException(
                    422,
                    f"Subcategory is required for Service Orders (SO) "
                    f"in Excel row {excel_row}",
                )

            # -------------------------------------------------
            # Duplicate order numbers
            # -------------------------------------------------

            duplicate_key = (
                order_type,
                order_number,
            )

            if duplicate_key in seen_order_numbers:

                raise HTTPException(
                    409,
                    f"Duplicate order number '{order_number}' "
                    f"in the import",
                )

            seen_order_numbers.add(
                duplicate_key
            )

            existing_order = db.query(Order.id).filter(
                Order.order_type == order_type,
                Order.order_number == order_number,
            ).first()

            if existing_order:

                raise HTTPException(
                    409,
                    f"Order number '{order_number}' already exists",
                )

            # -------------------------------------------------
            # Vendor validation
            # -------------------------------------------------

            normalized_vendor_name = normalize_vendor_name(
                vendor_name
            )

            previous_name = seen_vendor_codes.get(
                vendor_code
            )

            if previous_name is not None:

                if previous_name != normalized_vendor_name:

                    raise HTTPException(
                        422,
                        f"Vendor code '{vendor_code}' has "
                        "different vendor names in the import",
                    )

            else:

                seen_vendor_codes[vendor_code] = (
                    normalized_vendor_name
                )

            vendor = db.query(Party).filter(
                Party.code == vendor_code,
                Party.party_type == "VENDOR",
            ).with_for_update().one_or_none()

            if vendor is not None:

                if not vendor.is_active:

                    raise HTTPException(
                        422,
                        f"Vendor '{vendor_code}' is inactive",
                    )

                if normalize_vendor_name(
                    vendor.name
                ) != normalized_vendor_name:

                    raise HTTPException(
                        422,
                        f"Vendor code '{vendor_code}' already exists "
                        f"with name '{vendor.name}', but Excel contains "
                        f"'{vendor_name}'",
                    )

                vendor_id = vendor.id

            else:

                pending_vendor = pending_vendors.get(
                    vendor_code
                )

                if pending_vendor is None:

                    pending_vendors[vendor_code] = {
                        "name": vendor_name,
                        "code": vendor_code,
                        "party_type": "VENDOR",
                    }

                    vendor_id = None

                else:

                    if normalize_vendor_name(
                        pending_vendor["name"]
                    ) != normalized_vendor_name:

                        raise HTTPException(
                            422,
                            f"Vendor code '{vendor_code}' "
                            "has conflicting names in the import",
                        )

                    vendor_id = None

            # -------------------------------------------------
            # Budget validation
            # -------------------------------------------------

            required_type = expected_budget_type(
                order_type
            )

            budget = (
                db.query(Budget)
                .filter(
                    func.lower(Budget.name)
                    == budget_name.lower(),
                    Budget.financial_year == financial_year,
                    Budget.budget_type == required_type,
                )
                .with_for_update()
                .one_or_none()
            )

            if budget is None:

                if order_type == "PO":

                    raise HTTPException(
                        422,
                        f"CAPEX budget '{budget_name}' not found "
                        f"for the selected financial year.",
                    )

                raise HTTPException(
                    422,
                    f"OPEX budget '{budget_name}' not found "
                    f"for the selected financial year. "
                    f"Please create and approve the budget before importing.",
                )

            # -------------------------------------------------
            # OPEX subcategory validation for SO
            # -------------------------------------------------

            budget_subcategory_id = None
            subcategory_approved_amount = Decimal("0.00")

            if order_type == "SO":

                subcategory = (
                    db.query(BudgetSubcategory)
                    .filter(
                        BudgetSubcategory.budget_id == budget.id,
                        func.lower(BudgetSubcategory.name)
                        == subcategory_name.lower(),
                    )
                    .with_for_update()
                    .one_or_none()
                )

                if subcategory is None:

                    # Check whether the subcategory exists
                    # under another OPEX budget.

                    another_parent = (
                        db.query(
                            BudgetSubcategory,
                            Budget,
                        )
                        .join(
                            Budget,
                            Budget.id
                            == BudgetSubcategory.budget_id,
                        )
                        .filter(
                            Budget.budget_type == "OPEX",
                            Budget.financial_year
                            == financial_year,
                            func.lower(BudgetSubcategory.name)
                            == subcategory_name.lower(),
                        )
                        .first()
                    )

                    if another_parent:

                        raise HTTPException(
                            422,
                            f"Subcategory '{subcategory_name}' "
                            f"does not belong to OPEX budget "
                            f"'{budget_name}'.",
                        )

                    # Check for pending approval request.

                    pending_request = (
                        db.query(
                            BudgetSubcategoryApprovalRequest.id
                        )
                        .filter(
                            BudgetSubcategoryApprovalRequest.budget_id
                            == budget.id,
                            func.lower(
                                BudgetSubcategoryApprovalRequest.name
                            )
                            == subcategory_name.lower(),
                            BudgetSubcategoryApprovalRequest.status
                            == "PENDING",
                        )
                        .first()
                    )

                    if pending_request:

                        raise HTTPException(
                            422,
                            f"Subcategory '{subcategory_name}' "
                            f"has not yet been approved.",
                        )

                    raise HTTPException(
                        422,
                        f"Subcategory '{subcategory_name}' "
                        f"not found under OPEX budget '{budget_name}'. "
                        f"Please create and approve the subcategory "
                        f"before importing.",
                    )

                budget_subcategory_id = subcategory.id

                subcategory_approved_amount = Decimal(
                    str(
                        subcategory.approved_amount
                        or Decimal("0.00")
                    )
                )

                if subcategory_approved_amount <= 0:

                    raise HTTPException(
                        422,
                        f"Subcategory '{subcategory_name}' "
                        f"has not yet been approved.",
                    )

                requested_by_subcategory[
                    budget_subcategory_id
                ] = (
                    requested_by_subcategory.get(
                        budget_subcategory_id,
                        Decimal("0.00"),
                    )
                )

            # -------------------------------------------------
            # Date and amount validation
            # -------------------------------------------------

            try:

                order_date = date.fromisoformat(
                    str(row.get("order_date", ""))
                )

                validate_fy_date(
                    financial_year,
                    order_date,
                )

                amount = Decimal(
                    str(row.get("amount", ""))
                )

            except (
                ValueError,
                TypeError,
                ArithmeticError,
            ):

                raise HTTPException(
                    422,
                    f"Invalid date, financial year, or amount "
                    f"in Excel row {excel_row}",
                )

            if (
                not amount.is_finite()
                or amount <= 0
            ):

                raise HTTPException(
                    422,
                    f"Amount must be greater than zero "
                    f"in Excel row {excel_row}",
                )

            # -------------------------------------------------
            # Combined PO budget tracking
            # -------------------------------------------------

            if order_type == "PO":

                requested_by_budget[budget.id] = (
                    requested_by_budget.get(
                        budget.id,
                        Decimal("0.00"),
                    )
                    + amount
                )

            # -------------------------------------------------
            # Combined SO subcategory tracking
            # -------------------------------------------------

            elif order_type == "SO":

                requested_by_subcategory[
                    budget_subcategory_id
                ] = (
                    requested_by_subcategory.get(
                        budget_subcategory_id,
                        Decimal("0.00"),
                    )
                    + amount
                )

            # -------------------------------------------------
            # Prepared row
            # -------------------------------------------------

            prepared_rows.append({
                "order_type": order_type,
                "order_number": order_number,
                "vendor_code": vendor_code,
                "vendor_name": vendor_name,
                "party_id": vendor_id,
                "budget_id": budget.id,
                "budget_subcategory_id": budget_subcategory_id,
                "approved_by": approved_by,
                "financial_year": financial_year,
                "order_date": order_date,
                "order_period": row.get("order_period") or None,
                "location": row.get("location") or None,
                "amount": amount,
                "description": (
                    str(row.get("description") or "").strip()
                    or None
                ),
            })

        # -----------------------------------------------------
        # Combined PO budget validation
        # -----------------------------------------------------

        for budget_id, requested_amount in (
            requested_by_budget.items()
        ):

            budget = db.query(Budget).filter(
                Budget.id == budget_id,
            ).with_for_update().one_or_none()

            if budget is None:

                raise HTTPException(
                    422,
                    "Linked CAPEX budget no longer exists",
                )

            committed = get_committed_budget(
                db,
                budget_id,
            )

            available = (
                Decimal(str(budget.approved_amount or 0))
                - committed
            )

            if requested_amount > available:

                raise HTTPException(
                    422,
                    detail={
                        "message": (
                            f"Insufficient approved CAPEX budget "
                            f"for bulk import. Available: "
                            f"{money(available)}, Requested: "
                            f"{money(requested_amount)}."
                        ),
                        "budget_id": budget_id,
                        "available": str(available),
                        "requested": str(requested_amount),
                    },
                )

        # -----------------------------------------------------
        # Combined SO subcategory allocation validation
        # -----------------------------------------------------

        for subcategory_id, requested_amount in (
            requested_by_subcategory.items()
        ):

            subcategory = (
                db.query(BudgetSubcategory)
                .filter(
                    BudgetSubcategory.id
                    == subcategory_id,
                )
                .with_for_update()
                .one_or_none()
            )

            if subcategory is None:

                raise HTTPException(
                    422,
                    "Linked OPEX subcategory no longer exists",
                )

            approved_amount = Decimal(
                str(
                    subcategory.approved_amount
                    or Decimal("0.00")
                )
            )

            committed_result = (
                db.query(
                    func.coalesce(
                        func.sum(Order.amount),
                        0,
                    )
                )
                .filter(
                    Order.budget_subcategory_id
                    == subcategory_id,
                    Order.order_type == "SO",
                    Order.status != "CANCELLED",
                )
                .with_for_update()
                .scalar()
            )

            committed = Decimal(
                str(committed_result or "0.00")
            )

            available = approved_amount - committed

            if requested_amount > available:

                raise HTTPException(
                    422,
                    detail={
                        "message": (
                            f"Insufficient approved allocation "
                            f"for OPEX subcategory "
                            f"'{subcategory.name}'. "
                            f"Available: {money(available)}, "
                            f"Requested: {money(requested_amount)}."
                        ),
                        "subcategory_id": subcategory_id,
                        "available": str(available),
                        "requested": str(requested_amount),
                    },
                )

        # -----------------------------------------------------
        # Create new vendors
        # -----------------------------------------------------

        vendor_ids = {}

        # Existing vendors

        for row in prepared_rows:

            if row["party_id"] is not None:

                vendor_ids[
                    row["vendor_code"]
                ] = row["party_id"]

        # New vendors

        for vendor_code, vendor_data in (
            pending_vendors.items()
        ):

            existing_vendor = db.query(Party).filter(
                Party.code == vendor_code,
                Party.party_type == "VENDOR",
            ).with_for_update().one_or_none()

            if existing_vendor is not None:

                if not existing_vendor.is_active:

                    raise HTTPException(
                        422,
                        f"Vendor '{vendor_code}' is inactive",
                    )

                if normalize_vendor_name(
                    existing_vendor.name
                ) != normalize_vendor_name(
                    vendor_data["name"]
                ):

                    raise HTTPException(
                        409,
                        f"Vendor code '{vendor_code}' was created "
                        "or changed by another transaction",
                    )

                vendor_ids[
                    vendor_code
                ] = existing_vendor.id

            else:

                new_vendor = Party(
                    party_type="VENDOR",
                    code=vendor_code,
                    name=vendor_data["name"],
                    is_active=True,
                )

                db.add(new_vendor)

                db.flush()

                vendor_ids[
                    vendor_code
                ] = new_vendor.id

                created_vendors.append(
                    new_vendor
                )

        # -----------------------------------------------------
        # Create orders
        # -----------------------------------------------------

        for values in prepared_rows:

            order = Order(
                order_type=values["order_type"],
                order_number=values["order_number"],
                party_id=vendor_ids[
                    values["vendor_code"]
                ],
                budget_id=values["budget_id"],
                budget_subcategory_id=(
                    values["budget_subcategory_id"]
                ),
                approved_by=values["approved_by"],
                financial_year=values["financial_year"],
                order_date=values["order_date"],
                order_period=values["order_period"],
                location=values["location"],
                amount=values["amount"],
                description=values["description"],
                status="OPEN",
            )

            db.add(order)

            created_orders.append(
                order
            )

        # -----------------------------------------------------
        # Commit everything together
        # -----------------------------------------------------

        db.flush()

        created_order_ids = [
            order.id
            for order in created_orders
        ]

        created_vendor_ids = [
            vendor.id
            for vendor in created_vendors
        ]

        db.commit()

        return {
            "message": "Orders and vendors imported successfully",
            "created_count": len(created_order_ids),
            "created_order_ids": created_order_ids,
            "created_vendor_count": len(created_vendor_ids),
            "created_vendor_ids": created_vendor_ids,
        }

    except HTTPException:

        db.rollback()
        raise

    except IntegrityError:

        db.rollback()

        logger.exception(
            "Integrity error during bulk order import"
        )

        raise HTTPException(
            409,
            "Import failed because of a duplicate or invalid "
            "database record. No vendors or orders were saved.",
        )

    except Exception:

        db.rollback()

        logger.exception(
            "Unexpected error during bulk order import"
        )

        raise HTTPException(
            500,
            "Order import failed. No vendors or orders were saved.",
        )

# =========================================================
# ORDER VALIDATION AND HELPERS
# =========================================================

def validate_party(db, party_id, order_type):

    if order_type not in ("PO", "SO"):

        raise HTTPException(
            status_code=422,
            detail="Order type must be PO or SO",
        )

    party = db.get(
        Party,
        party_id,
    )

    if party is None:

        raise HTTPException(
            status_code=404,
            detail="Vendor not found",
        )

    if (
        party.party_type or ""
    ).strip().upper() != "VENDOR":

        raise HTTPException(
            status_code=422,
            detail=(
                "Both Purchase Orders and Service Orders "
                "require a vendor"
            ),
        )

    if not party.is_active:

        raise HTTPException(
            status_code=422,
            detail="Vendor is inactive",
        )

    return party


def get_committed_budget(
    db,
    budget_id,
    exclude_id=None,
):

    query = db.query(
        func.coalesce(
            func.sum(Order.amount),
            0,
        )
    ).filter(
        Order.budget_id == budget_id,
        Order.order_type == "PO",
        Order.status != "CANCELLED",
    )

    if exclude_id is not None:

        query = query.filter(
            Order.id != exclude_id
        )

    return Decimal(
        str(query.scalar() or 0)
    )


def get_order_summary(
    db: Session,
    order: Order,
):

    submitted_amount = Decimal(
        str(
            db.query(
                func.coalesce(
                    func.sum(Invoice.amount),
                    0,
                )
            )
            .filter(
                Invoice.order_id == order.id
            )
            .scalar()
            or 0
        )
    )

    invoice_count = (
        db.query(
            func.count(Invoice.id)
        )
        .filter(
            Invoice.order_id == order.id
        )
        .scalar()
        or 0
    )

    party = db.get(
        Party,
        order.party_id,
    )

    budget = (
        db.get(Budget, order.budget_id)
        if order.budget_id
        else None
    )

    order_amount = Decimal(
        str(order.amount)
    )

    result = (
        OrderResponse
        .model_validate(order)
        .model_dump()
    )

    result["party_name"] = (
        party.name
        if party
        else None
    )

    result["budget_name"] = (
        budget.name
        if budget
        else None
    )

    result["submitted_invoice_amount"] = (
        submitted_amount
    )

    result["available_order_value"] = (
        order_amount - submitted_amount
    )

    result["total_submitted_invoice"] = (
        invoice_count
    )

    return result


def get_invoice_payment_status(
    db: Session,
    invoice: Invoice,
):

    total_paid = Decimal(
        str(
            db.query(
                func.coalesce(
                    func.sum(Payment.amount),
                    0,
                )
            )
            .filter(
                Payment.invoice_id == invoice.id
            )
            .scalar()
            or 0
        )
    )

    balance_due = (
        Decimal(str(invoice.amount))
        - total_paid
    )

    if balance_due <= 0:
        return "PAID"

    if invoice.due_date < date.today():
        return "OVERDUE"

    if total_paid > 0:
        return "PART_PAID"

    return "UNPAID"


# =========================================================
# CREATE ORDER
# =========================================================

@router.post(
    "",
    response_model=OrderResponse,
    status_code=201,
    dependencies=[
        Depends(require_roles("ADMIN", "ACCOUNTS"))
    ],
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):

    from app.schemas.order import expected_budget_type

    budget = (
        db.query(Budget)
        .filter(
            Budget.id == payload.budget_id
        )
        .with_for_update()
        .one_or_none()
    )

    if budget is None:

        raise HTTPException(
            404,
            "Budget not found",
        )

    required_type = expected_budget_type(
        payload.order_type
    )

    if budget.budget_type != required_type:

        raise HTTPException(
            422,
            f"{payload.order_type} requires a "
            f"{required_type} budget",
        )

    if (
        budget.financial_year
        != payload.financial_year
    ):

        raise HTTPException(
            422,
            "Budget financial year mismatch",
        )

    validate_party(
        db,
        payload.party_id,
        payload.order_type,
    )

    existing = db.query(Order).filter(
        Order.order_type == payload.order_type,
        Order.order_number == payload.order_number,
    ).first()

    if existing:

        raise HTTPException(
            409,
            "Order number already exists",
        )

    if payload.order_type == "PO":

        committed = get_committed_budget(
            db,
            budget.id,
        )

        available = (
            Decimal(str(budget.approved_amount))
            - committed
        )

        if payload.amount > available:

            raise HTTPException(
                422,
                detail={
                    "message": "Insufficient approved budget",
                    "available": str(available),
                    "requested": str(payload.amount),
                },
            )

    order = Order(
        **payload.model_dump(),
        status="OPEN",
    )

    db.add(order)

    try:

        db.commit()
        db.refresh(order)

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            409,
            "Duplicate or invalid order",
        )

    return get_order_summary(
        db,
        order,
    )


# =========================================================
# SEARCH ORDERS
# =========================================================

@router.get(
    "/search",
    response_model=list[OrderResponse],
)
def search_orders(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
):

    q = q.strip()

    if not q:

        raise HTTPException(
            422,
            "Search text required",
        )

    orders = (
        db.query(Order)
        .filter(
            Order.order_number.ilike(
                f"%{q}%"
            )
        )
        .order_by(
            Order.id.desc()
        )
        .limit(100)
        .all()
    )

    return [
        get_order_summary(
            db,
            order,
        )
        for order in orders
    ]


# =========================================================
# LIST ORDERS
# =========================================================

@router.get(
    "",
    response_model=list[OrderResponse],
)
def list_orders(
    order_type: str | None = None,
    financial_year: str | None = None,
    db: Session = Depends(get_db),
):

    query = db.query(Order)

    if order_type:

        order_type = order_type.upper()

        if order_type not in ("PO", "SO"):

            raise HTTPException(
                422,
                "Invalid order type",
            )

        query = query.filter(
            Order.order_type == order_type
        )

    if financial_year:

        query = query.filter(
            Order.financial_year == financial_year
        )

    orders = (
        query
        .order_by(Order.id.desc())
        .limit(100)
        .all()
    )

    return [
        get_order_summary(
            db,
            order,
        )
        for order in orders
    ]


# =========================================================
# ORDER INVOICES
# =========================================================

@router.get(
    "/{order_id}/invoices",
    response_model=list[OrderInvoiceResponse],
)
def list_order_invoices(
    order_id: int,
    db: Session = Depends(get_db),
):

    order = db.get(
        Order,
        order_id,
    )

    if order is None:

        raise HTTPException(
            404,
            "Order not found",
        )

    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.order_id == order_id
        )
        .order_by(
            Invoice.id.desc()
        )
        .all()
    )

    vendor = db.get(
        Party,
        order.party_id,
    )

    vendor_name = (
        vendor.name
        if vendor
        else None
    )

    budget = (
        db.get(Budget, order.budget_id)
        if order.budget_id
        else None
    )

    results = []

    for invoice in invoices:

        total_paid = Decimal(
            str(
                db.query(
                    func.coalesce(
                        func.sum(Payment.amount),
                        0,
                    )
                )
                .filter(
                    Payment.invoice_id == invoice.id
                )
                .scalar()
                or 0
            )
        )

        invoice_amount = Decimal(
            str(invoice.amount)
        )

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


# =========================================================
# GET SINGLE ORDER
# =========================================================

@router.get(
    "/{order_id}",
    response_model=OrderResponse,
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):

    order = db.get(
        Order,
        order_id,
    )

    if order is None:

        raise HTTPException(
            404,
            "Order not found",
        )

    return get_order_summary(
        db,
        order,
    )


# =========================================================
# UPDATE ORDER
# =========================================================

@router.put(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[
        Depends(require_roles("ADMIN", "ACCOUNTS"))
    ],
)
def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
):

    changes = payload.model_dump(
        exclude_unset=True
    )

    if not changes:

        raise HTTPException(
            400,
            "No changes provided",
        )

    if (
        ("amount" in changes and changes["amount"] is None)
        or (
            "order_date" in changes
            and changes["order_date"] is None
        )
    ):

        raise HTTPException(
            422,
            "Amount and order date cannot be null",
        )

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id
        )
        .with_for_update()
        .one_or_none()
    )

    if order is None:

        raise HTTPException(
            404,
            "Order not found",
        )

    if order.status != "OPEN":

        raise HTTPException(
            409,
            "Only OPEN orders can be edited",
        )

    budget = None

    if order.order_type == "PO":

        budget = (
            db.query(Budget)
            .filter(
                Budget.id == order.budget_id
            )
            .with_for_update()
            .one_or_none()
        )

        if budget is None:

            raise HTTPException(
                409,
                "Linked budget missing",
            )

    new_date = changes.get(
        "order_date",
        order.order_date,
    )

    try:

        validate_fy_date(
            order.financial_year,
            new_date,
        )

    except ValueError as exc:

        raise HTTPException(
            422,
            str(exc),
        )

    new_amount = Decimal(
        str(
            changes.get(
                "amount",
                order.amount,
            )
        )
    )

    submitted_amount = Decimal(
        str(
            db.query(
                func.coalesce(
                    func.sum(Invoice.amount),
                    0,
                )
            )
            .filter(
                Invoice.order_id == order.id
            )
            .scalar()
            or 0
        )
    )

    if new_amount < submitted_amount:

        raise HTTPException(
            422,
            "Order amount cannot be less than submitted invoice amounts",
        )

    if budget is not None:

        committed = get_committed_budget(
            db,
            budget.id,
            exclude_id=order.id,
        )

        if (
            committed + new_amount
            > Decimal(str(budget.approved_amount))
        ):

            raise HTTPException(
                422,
                "Updated order exceeds approved budget",
            )

    for field, value in changes.items():

        setattr(
            order,
            field,
            value,
        )

    try:

        db.commit()
        db.refresh(order)

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            409,
            "Order update failed",
        )

    return get_order_summary(
        db,
        order,
    )


# =========================================================
# ORDER APPROVAL ATTACHMENT
# =========================================================

@router.post(
    "/{order_id}/approval",
    dependencies=[
        Depends(require_roles("ADMIN", "ACCOUNTS"))
    ],
)
async def upload_order_approval(
    order_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    order = db.get(
        Order,
        order_id,
    )

    if order is None:

        raise HTTPException(
            404,
            "Order not found",
        )

    extension = Path(
        file.filename or ""
    ).suffix.lower()

    allowed_types = (
        ALLOWED_APPROVAL_TYPES.get(extension)
    )

    if (
        allowed_types is None
        or file.content_type not in allowed_types
    ):

        raise HTTPException(
            422,
            "Approval file must be a PDF or JPG/JPEG image",
        )

    content = await file.read(
        MAX_APPROVAL_SIZE + 1
    )

    await file.close()

    if not content:

        raise HTTPException(
            422,
            "Uploaded file is empty",
        )

    if len(content) > MAX_APPROVAL_SIZE:

        raise HTTPException(
            413,
            "Approval file must be 10 MB or smaller",
        )

    if (
        extension == ".pdf"
        and not content.startswith(b"%PDF-")
    ):

        raise HTTPException(
            422,
            "Invalid PDF file",
        )

    if (
        extension in (".jpg", ".jpeg")
        and not content.startswith(b"\xff\xd8\xff")
    ):

        raise HTTPException(
            422,
            "Invalid JPEG file",
        )

    APPROVAL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
