from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook


REQUIRED_COLUMNS = [
    "Order Type",
    "Order Number",
    "Vendor Code",
    "Budget Name",
    "Financial Year",
    "Order Date",
    "Amount",
]

OPTIONAL_COLUMNS = [
    "Order Period",
    "Location",
    "Description",
]


def normalize_header(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().lower().split())


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def parse_order_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), date_format).date()
            except ValueError:
                continue

    raise ValueError("Invalid Order Date. Use DD-MM-YYYY or YYYY-MM-DD.")


def parse_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError, TypeError):
        raise ValueError("Invalid Amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return amount.quantize(Decimal("0.01"))


def validate_financial_year(value: Any) -> str:
    financial_year = normalize_text(value)

    if (
        len(financial_year) != 9
        or financial_year[4] != "-"
        or not financial_year[:4].isdigit()
        or not financial_year[5:].isdigit()
        or int(financial_year[5:]) != int(financial_year[:4]) + 1
    ):
        raise ValueError("Financial Year must be in YYYY-YYYY format.")

    return financial_year


def read_order_excel(file_content: bytes) -> dict:
    """
    Read and validate an uploaded Excel workbook.

    This function does not save anything to the database.
    It only prepares rows for preview.
    """

    try:
        workbook = load_workbook(
            filename=BytesIO(file_content),
            read_only=True,
            data_only=True,
        )
    except Exception:
        raise ValueError("Unable to read the Excel file. Please upload a valid .xlsx file.")

    worksheet = workbook.active

    if worksheet.max_row < 2:
        workbook.close()
        raise ValueError("The Excel file does not contain any order rows.")

    headers = [
        normalize_header(cell.value)
        for cell in worksheet[1]
    ]

    header_map = {
        header: index
        for index, header in enumerate(headers)
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
            "Missing required columns: " + ", ".join(missing_columns)
        )

    preview_rows = []

    for row_number, row in enumerate(
        worksheet.iter_rows(min_row=2, values_only=True),
        start=2,
    ):
        if not any(value is not None and str(value).strip() for value in row):
            continue

        errors = []

        def get_value(column_name: str):
            index = header_map.get(normalize_header(column_name))

            if index is None or index >= len(row):
                return None

            return row[index]

        order_type = normalize_text(get_value("Order Type")).upper()
        order_number = normalize_text(get_value("Order Number")).upper()
        vendor_code = normalize_text(get_value("Vendor Code"))
        budget_name = normalize_text(get_value("Budget Name"))
        order_period = normalize_text(get_value("Order Period")) or None
        location = normalize_text(get_value("Location")) or None
        description = normalize_text(get_value("Description")) or None

        financial_year = None
        order_date = None
        amount = None

        if order_type not in ("PO", "SO"):
            errors.append("Order Type must be PO or SO.")

        if not order_number:
            errors.append("Order Number is required.")

        if not vendor_code:
            errors.append("Vendor Code is required.")

        if not budget_name:
            errors.append("Budget Name is required.")

        try:
            financial_year = validate_financial_year(
                get_value("Financial Year")
            )
        except ValueError as exc:
            errors.append(str(exc))

        try:
            order_date = parse_order_date(get_value("Order Date"))
        except ValueError as exc:
            errors.append(str(exc))

        try:
            amount = parse_amount(get_value("Amount"))
        except ValueError as exc:
            errors.append(str(exc))

        if financial_year and order_date:
            start_year = int(financial_year[:4])
            end_year = int(financial_year[5:])

            if not (
                date(start_year, 4, 1)
                <= order_date
                <= date(end_year, 3, 31)
            ):
                errors.append(
                    "Order Date must fall within the selected Financial Year."
                )

        preview_rows.append(
            {
                "excel_row": row_number,
                "order_type": order_type,
                "order_number": order_number,
                "vendor_code": vendor_code,
                "budget_name": budget_name,
                "financial_year": financial_year,
                "order_date": order_date.isoformat() if order_date else None,
                "order_period": order_period,
                "location": location,
                "amount": str(amount) if amount is not None else None,
                "description": description,
                "errors": errors,
                "is_valid": len(errors) == 0,
            }
        )

    workbook.close()

    if not preview_rows:
        raise ValueError("No order data rows were found in the Excel file.")

    return {
        "total_rows": len(preview_rows),
        "valid_rows": sum(
            1 for item in preview_rows if item["is_valid"]
        ),
        "invalid_rows": sum(
            1 for item in preview_rows if not item["is_valid"]
        ),
        "rows": preview_rows,
    }