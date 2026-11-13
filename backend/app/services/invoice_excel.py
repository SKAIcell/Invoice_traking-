from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
import re

from openpyxl import load_workbook


def normalize_header(value: Any) -> str:
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", "")
    )


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip()

    text = text.strip()

    if text.upper() == "NULL":
        return ""

    return text


def parse_invoice_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)):
        from openpyxl.utils.datetime import from_excel

        converted = from_excel(value)

        if isinstance(converted, datetime):
            return converted.date()

        return converted

    text = normalize_text(value)

    for fmt in (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError(
        "Invalid date. Use DD-MM-YYYY or YYYY-MM-DD."
    )


def parse_invoice_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(
            str(value).replace(",", "").strip()
        )
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid invoice amount.")

    if not amount.is_finite() or amount <= 0:
        raise ValueError(
            "Invoice amount must be greater than zero."
        )

    return amount.quantize(Decimal("0.01"))


def validate_invoice_financial_year(value: Any) -> str:
    financial_year = normalize_text(value)

    if not re.fullmatch(
        r"\d{4}-\d{4}",
        financial_year,
    ):
        raise ValueError(
            "Financial Year must be in YYYY-YYYY format."
        )

    start_year, end_year = map(
        int,
        financial_year.split("-"),
    )

    if end_year != start_year + 1:
        raise ValueError(
            "Financial Year must contain consecutive years."
        )

    return financial_year


def get_financial_year(invoice_date: date) -> str:
    if invoice_date.month >= 4:
        start_year = invoice_date.year
    else:
        start_year = invoice_date.year - 1

    return f"{start_year}-{start_year + 1}"


def validate_invoice_date_in_fy(
    invoice_date: date,
    financial_year: str,
) -> None:
    start_year = int(
        financial_year.split("-")[0]
    )

    fy_start = date(start_year, 4, 1)
    fy_end = date(start_year + 1, 3, 31)

    if not fy_start <= invoice_date <= fy_end:
        raise ValueError(
            "Invoice Date must fall within the selected Financial Year."
        )


def read_invoice_excel(
    file_content: bytes,
) -> dict[str, Any]:

    workbook = load_workbook(
        filename=BytesIO(file_content),
        read_only=True,
        data_only=True,
    )

    try:
        worksheet = workbook.active

        if worksheet is None:
            raise ValueError(
                "Excel workbook has no active worksheet."
            )

        header_values = next(
            worksheet.iter_rows(values_only=True),
            None,
        )

        if not header_values:
            raise ValueError(
                "Excel worksheet is empty."
            )

        headers = [
            normalize_header(cell)
            for cell in header_values
        ]

        column_map = {
            header: index
            for index, header in enumerate(headers)
            if header
        }

        # Supports both standard and company Excel templates.
        aliases = {
            "invoice type": [
                "invoice type",
            ],
            "invoice number": [
                "invoice number",
                "invoice no",
            ],
            "order number": [
                "order number",
                "po/so no",
                "po/so no.",
                "po so no",
            ],
            "vendor code": [
                "vendor code",
            ],
            "financial year": [
                "financial year",
                "financialyear",
                "fy",
            ],
            "invoice date": [
                "invoice date",
            ],
            "due date": [
                "due date",
            ],
            "amount": [
                "amount",
                "invoice amount",
            ],
            "period": [
                "period",
            ],
            "location": [
                "location",
            ],
            "description": [
                "description",
                "service details",
            ],
            "remarks": [
                "remarks",
            ],
        }

        resolved_columns = {}

        for standard_name, possible_headers in aliases.items():
            for possible_header in possible_headers:
                normalized = normalize_header(
                    possible_header
                )

                if normalized in column_map:
                    resolved_columns[standard_name] = (
                        column_map[normalized]
                    )
                    break

        # Required columns for both supported templates.
        required_columns = [
            "invoice number",
            "order number",
            "vendor code",
            "invoice date",
            "due date",
            "amount",
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in resolved_columns
        ]

        if missing_columns:
            display_names = {
                "invoice number": "Invoice Number / Invoice No.",
                "order number": "Order Number / PO/SO No.",
                "vendor code": "Vendor Code",
                "invoice date": "Invoice Date",
                "due date": "Due Date",
                "amount": "Amount / Invoice Amount",
            }

            raise ValueError(
                "Missing required columns: "
                + ", ".join(
                    display_names[column]
                    for column in missing_columns
                )
            )

        valid_rows = []
        invalid_rows = []
        total_rows = 0

        for excel_row, values in enumerate(
            worksheet.iter_rows(
                min_row=2,
                values_only=True,
            ),
            start=2,
        ):
            if not any(
                value is not None
                for value in values
            ):
                continue

            total_rows += 1

            def get_value(column: str):
                index = resolved_columns.get(column)

                if index is None or index >= len(values):
                    return None

                return values[index]

            errors = []

            invoice_type = normalize_text(
                get_value("invoice type")
            ).upper()

            invoice_number = normalize_text(
                get_value("invoice number")
            )

            order_number = normalize_text(
                get_value("order number")
            )

            vendor_code = normalize_text(
                get_value("vendor code")
            )

            # Invoice Type may be absent in the company template.
            # The backend must determine it from the order type.
            if invoice_type and invoice_type not in {
                "PURCHASE",
                "SERVICE",
            }:
                errors.append(
                    "Invoice Type must be PURCHASE or SERVICE."
                )

            if not invoice_number:
                errors.append(
                    "Invoice Number is required."
                )

            if not order_number:
                errors.append(
                    "Order Number is required."
                )

            if not vendor_code:
                errors.append(
                    "Vendor Code is required."
                )

            try:
                invoice_date = parse_invoice_date(
                    get_value("invoice date")
                )
            except ValueError as exc:
                invoice_date = None
                errors.append(
                    f"Invoice Date: {exc}"
                )

            try:
                due_date = parse_invoice_date(
                    get_value("due date")
                )
            except ValueError as exc:
                due_date = None
                errors.append(
                    f"Due Date: {exc}"
                )

            if invoice_date and due_date:
                if due_date < invoice_date:
                    errors.append(
                        "Due Date cannot be earlier than Invoice Date."
                    )

            raw_financial_year = normalize_text(
                get_value("financial year")
            )

            if raw_financial_year:
                try:
                    financial_year = (
                        validate_invoice_financial_year(
                            raw_financial_year
                        )
                    )
                except ValueError as exc:
                    financial_year = raw_financial_year
                    errors.append(str(exc))
            elif invoice_date:
                financial_year = get_financial_year(
                    invoice_date
                )
            else:
                financial_year = ""

            if invoice_date and re.fullmatch(
                r"\d{4}-\d{4}",
                financial_year,
            ):
                try:
                    validate_invoice_date_in_fy(
                        invoice_date,
                        financial_year,
                    )
                except ValueError as exc:
                    errors.append(str(exc))

            try:
                amount = parse_invoice_amount(
                    get_value("amount")
                )
            except ValueError as exc:
                amount = None
                errors.append(str(exc))

            parsed_row = {
                "excel_row": excel_row,
                "invoice_type": invoice_type or None,
                "invoice_number": invoice_number,
                "order_number": order_number,
                "vendor_code": vendor_code,
                "financial_year": financial_year,
                "invoice_date": (
                    invoice_date.isoformat()
                    if invoice_date
                    else None
                ),
                "due_date": (
                    due_date.isoformat()
                    if due_date
                    else None
                ),
                "amount": (
                    str(amount)
                    if amount is not None
                    else None
                ),
                "period": normalize_text(
                    get_value("period")
                ) or None,
                "location": normalize_text(
                    get_value("location")
                ) or None,
                "description": normalize_text(
                    get_value("description")
                ) or None,
                "remarks": normalize_text(
                    get_value("remarks")
                ) or None,
                "errors": errors,
                "is_valid": len(errors) == 0,
            }

            if parsed_row["is_valid"]:
                valid_rows.append(parsed_row)
            else:
                invalid_rows.append(parsed_row)

        return {
            "total_rows": total_rows,
            "valid_rows": len(valid_rows),
            "invalid_rows": len(invalid_rows),
            "rows": valid_rows + invalid_rows,
        }

    finally:
        workbook.close()