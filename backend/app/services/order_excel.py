from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook


REQUIRED_COLUMNS = [
    "Order Type",
    "Order Number",
    "Vendor Name",
    "Vendor Code",
    "Budget Name",
    "Financial Year",
    "Order Date",
    "Amount",
    "Approved By",
]


OPTIONAL_COLUMNS = [
    "Subcategory",
    "OPEX Subcategory",  # Backward compatibility
    "Order Period",
    "Location",
    "Materials Description",
    "Material Description",
    "Description",
]


def normalize_header(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).strip().lower().split()
    )


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_vendor_code(value: Any) -> str:
    return normalize_text(value).upper()


def parse_order_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        for date_format in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(
                    value.strip(),
                    date_format,
                ).date()

            except ValueError:
                continue

    raise ValueError(
        "Invalid Order Date. Use DD-MM-YYYY or YYYY-MM-DD."
    )


def parse_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(
            str(value).replace(",", "").strip()
        )

    except (
        InvalidOperation,
        AttributeError,
        TypeError,
    ):
        raise ValueError("Invalid Amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError(
            "Amount must be greater than zero."
        )

    return amount.quantize(
        Decimal("0.01")
    )


def validate_financial_year(value: Any) -> str:
    financial_year = normalize_text(value)

    if (
        len(financial_year) != 9
        or financial_year[4] != "-"
        or not financial_year[:4].isdigit()
        or not financial_year[5:].isdigit()
        or int(financial_year[5:])
        != int(financial_year[:4]) + 1
    ):
        raise ValueError(
            "Financial Year must be in YYYY-YYYY format."
        )

    return financial_year


def excel_value_to_string(value: Any) -> Any:
    """
    Convert Excel cell values into JSON-compatible values.
    """

    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")

    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    if isinstance(value, Decimal):
        return str(value)

    return str(value).strip()


def read_order_excel(file_content: bytes) -> dict:
    """
    Read and validate an uploaded Excel workbook.

    Supports:
        - PO / CAPEX orders
        - SO / OPEX orders
        - Vendor Name and Vendor Code
        - Parent Budget Name
        - Subcategory
        - Legacy OPEX Subcategory column
        - Approved By
        - Materials Description
        - Original Excel data
        - Row-level validation errors

    This function does not save anything to the database.
    """

    try:
        workbook = load_workbook(
            filename=BytesIO(file_content),
            read_only=True,
            data_only=True,
        )

    except Exception:
        raise ValueError(
            "Unable to read the Excel file. "
            "Please upload a valid .xlsx file."
        )

    worksheet = workbook.active

    if worksheet.max_row < 2:
        workbook.close()

        raise ValueError(
            "The Excel file does not contain any order rows."
        )

    original_headers = [
        normalize_text(cell.value)
        for cell in worksheet[1]
    ]

    normalized_headers = [
        normalize_header(cell.value)
        for cell in worksheet[1]
    ]

    header_map = {
        header: index
        for index, header in enumerate(normalized_headers)
        if header
    }

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if normalize_header(column) not in header_map
    ]

    if missing_columns:
        workbook.close()

        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    preview_rows = []

    for row_number, row in enumerate(
        worksheet.iter_rows(
            min_row=2,
            values_only=True,
        ),
        start=2,
    ):

        # Ignore completely empty Excel rows.
        if not any(
            value is not None
            and str(value).strip()
            for value in row
        ):
            continue

        errors = []

        def get_value(column_name: str):
            index = header_map.get(
                normalize_header(column_name)
            )

            if index is None or index >= len(row):
                return None

            return row[index]

        # -------------------------------------------------
        # Original Excel data
        # -------------------------------------------------

        raw_data = {}

        for index, header in enumerate(original_headers):
            if not header:
                continue

            value = (
                row[index]
                if index < len(row)
                else None
            )

            raw_data[header] = excel_value_to_string(
                value
            )

        # -------------------------------------------------
        # Standard order fields
        # -------------------------------------------------

        order_type = normalize_text(
            get_value("Order Type")
        ).upper()

        order_number = normalize_text(
            get_value("Order Number")
        ).upper()

        vendor_name = normalize_text(
            get_value("Vendor Name")
        )

        vendor_code = normalize_vendor_code(
            get_value("Vendor Code")
        )

        budget_name = normalize_text(
            get_value("Budget Name")
        )

        approved_by = normalize_text(
            get_value("Approved By")
        )

        order_period = (
            normalize_text(
                get_value("Order Period")
            )
            or None
        )

        location = (
            normalize_text(
                get_value("Location")
            )
            or None
        )

        # -------------------------------------------------
        # SUBCATEGORY
        #
        # Preferred column:
        #     Subcategory
        #
        # Backward compatibility:
        #     OPEX Subcategory
        #
        # If both columns exist and contain different
        # values, an error is raised.
        # -------------------------------------------------

        new_subcategory_value = normalize_text(
            get_value("Subcategory")
        )

        legacy_subcategory_value = normalize_text(
            get_value("OPEX Subcategory")
        )

        if (
            new_subcategory_value
            and legacy_subcategory_value
            and new_subcategory_value.lower()
            != legacy_subcategory_value.lower()
        ):
            errors.append(
                "Conflicting values found in "
                "'Subcategory' and 'OPEX Subcategory' columns."
            )

        budget_subcategory_name = (
            new_subcategory_value
            or legacy_subcategory_value
            or None
        )

        # -------------------------------------------------
        # MATERIAL DESCRIPTION
        #
        # Priority:
        # 1. Materials Description
        # 2. Material Description
        # 3. Description
        # -------------------------------------------------

        material_description = (
            normalize_text(
                get_value("Materials Description")
            )
            or normalize_text(
                get_value("Material Description")
            )
            or normalize_text(
                get_value("Description")
            )
            or None
        )

        description = material_description

        financial_year = None
        order_date = None
        amount = None

        # -------------------------------------------------
        # BASIC VALIDATIONS
        # -------------------------------------------------

        if order_type not in ("PO", "SO"):
            errors.append(
                "Order Type must be PO or SO."
            )

        if not order_number:
            errors.append(
                "Order Number is required."
            )

        if not vendor_name:
            errors.append(
                "Vendor Name is required."
            )

        if not vendor_code:
            errors.append(
                "Vendor Code is required."
            )

        if not budget_name:
            errors.append(
                "Budget Name is required."
            )

        # -------------------------------------------------
        # APPROVED BY VALIDATION
        # -------------------------------------------------

        if not approved_by:
            errors.append(
                "Approved By is required for both "
                "Purchase Orders (PO) and Service Orders (SO)."
            )

        # -------------------------------------------------
        # SUBCATEGORY VALIDATION
        #
        # PO:
        #     CAPEX
        #     Subcategory must be blank
        #
        # SO:
        #     OPEX
        #     Subcategory is mandatory
        # -------------------------------------------------

        if order_type == "PO":

            if budget_subcategory_name:
                errors.append(
                    "Subcategory is not applicable for "
                    "Purchase Orders (PO). "
                    "Please leave this field blank."
                )

        elif order_type == "SO":

            if not budget_subcategory_name:
                errors.append(
                    "Subcategory is required for "
                    "Service Orders (SO)."
                )

        # -------------------------------------------------
        # FINANCIAL YEAR VALIDATION
        # -------------------------------------------------

        try:
            financial_year = validate_financial_year(
                get_value("Financial Year")
            )

        except ValueError as exc:
            errors.append(str(exc))

        # -------------------------------------------------
        # ORDER DATE VALIDATION
        # -------------------------------------------------

        try:
            order_date = parse_order_date(
                get_value("Order Date")
            )

        except ValueError as exc:
            errors.append(str(exc))

        # -------------------------------------------------
        # AMOUNT VALIDATION
        # -------------------------------------------------

        try:
            amount = parse_amount(
                get_value("Amount")
            )

        except ValueError as exc:
            errors.append(str(exc))

        # -------------------------------------------------
        # FINANCIAL YEAR AND ORDER DATE CONSISTENCY
        # -------------------------------------------------

        if financial_year and order_date:

            start_year = int(
                financial_year[:4]
            )

            end_year = int(
                financial_year[5:]
            )

            if not (
                date(start_year, 4, 1)
                <= order_date
                <= date(end_year, 3, 31)
            ):
                errors.append(
                    "Order Date must fall within "
                    "the selected Financial Year."
                )

        # -------------------------------------------------
        # PREVIEW ROW
        # -------------------------------------------------

        preview_rows.append(
            {
                "excel_row": row_number,

                "order_type": order_type,
                "order_number": order_number,

                "vendor_name": vendor_name,
                "vendor_code": vendor_code,

                "budget_name": budget_name,

                "budget_subcategory_name": (
                    budget_subcategory_name
                ),

                "approved_by": approved_by,

                "financial_year": financial_year,

                "order_date": (
                    order_date.isoformat()
                    if order_date
                    else None
                ),

                "order_period": order_period,
                "location": location,

                "amount": (
                    str(amount)
                    if amount is not None
                    else None
                ),

                "description": description,

                "raw_data": raw_data,

                "errors": errors,
                "is_valid": len(errors) == 0,
            }
        )

    workbook.close()

    if not preview_rows:
        raise ValueError(
            "No order data rows were found in the Excel file."
        )

    valid_rows = sum(
        1
        for item in preview_rows
        if item["is_valid"]
    )

    invalid_rows = sum(
        1
        for item in preview_rows
        if not item["is_valid"]
    )

    return {
        "total_rows": len(preview_rows),
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,

        "excel_columns": [
            header
            for header in original_headers
            if header
        ],

        "rows": preview_rows,
    }