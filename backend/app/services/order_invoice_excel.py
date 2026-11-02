
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.services.invoice_excel import (
    normalize_header,
    normalize_text,
    parse_invoice_date,
    parse_invoice_amount,
)


REQUIRED_COLUMNS = [
    "Invoice Number",
    "PO/SO Number",
    "Vendor Name",
    "Vendor Code",
    "Invoice Date",
    "Due Date",
    "Amount",
]

OPTIONAL_COLUMNS = [
    "Period",
    "Location",
    "Description",
    "Remarks",
]


HEADER_ALIASES = {
    "Invoice Number": [
        "invoice number",
        "invoice no",
        "invoice no.",
    ],
    "PO/SO Number": [
        "po/so number",
        "po so number",
        "order number",
        "po number",
        "so number",
        "po/so no",
        "po/so no.",
    ],
    "Vendor Name": [
        "vendor name",
        "customer name",
        "party name",
        "vendor/customer name",
    ],
    "Vendor Code": [
        "vendor code",
        "customer code",
        "party code",
        "vendor/customer code",
    ],
    "Invoice Date": ["invoice date"],
    "Due Date": ["due date"],
    "Amount": ["amount", "invoice amount"],
    "Period": ["period"],
    "Location": ["location"],
    "Description": ["description"],
    "Remarks": ["remarks", "remark"],
}


def read_order_invoice_excel(file_content: bytes) -> dict[str, Any]:
    workbook = load_workbook(
        filename=BytesIO(file_content),
        read_only=True,
        data_only=True,
    )

    try:
        worksheet = workbook.active

        if worksheet is None:
            raise ValueError("Excel workbook has no active worksheet.")

        header_values = next(
            worksheet.iter_rows(values_only=True),
            None,
        )

        if not header_values:
            raise ValueError("Excel worksheet is empty.")

        headers = [
            normalize_header(value)
            for value in header_values
        ]

        column_map = {
            header: index
            for index, header in enumerate(headers)
            if header
        }

        resolved_columns = {}

        for column, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                normalized_alias = normalize_header(alias)

                if normalized_alias in column_map:
                    resolved_columns[column] = column_map[
                        normalized_alias
                    ]
                    break

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in resolved_columns
        ]

        if missing_columns:
            raise ValueError(
                "Missing required columns: "
                + ", ".join(missing_columns)
            )

        rows = []
        total_rows = 0

        for excel_row, values in enumerate(
            worksheet.iter_rows(
                min_row=2,
                values_only=True,
            ),
            start=2,
        ):
            if not any(value is not None for value in values):
                continue

            total_rows += 1
            errors = []

            def get_value(column: str):
                index = resolved_columns.get(column)

                if index is None or index >= len(values):
                    return None

                return values[index]

            invoice_number = normalize_text(
                get_value("Invoice Number")
            )

            order_number = normalize_text(
                get_value("PO/SO Number")
            )

            vendor_name = normalize_text(
                get_value("Vendor Name")
            )

            vendor_code = normalize_text(
                get_value("Vendor Code")
            )

            if not invoice_number:
                errors.append("Invoice Number is required.")

            if not order_number:
                errors.append("PO/SO Number is required.")

            if not vendor_name:
                errors.append("Vendor Name is required.")

            if not vendor_code:
                errors.append("Vendor Code is required.")

            try:
                invoice_date = parse_invoice_date(
                    get_value("Invoice Date")
                )
            except ValueError as exc:
                invoice_date = None
                errors.append(f"Invoice Date: {exc}")

            try:
                due_date = parse_invoice_date(
                    get_value("Due Date")
                )
            except ValueError as exc:
                due_date = None
                errors.append(f"Due Date: {exc}")

            if invoice_date and due_date:
                if due_date < invoice_date:
                    errors.append(
                        "Due Date cannot be earlier than Invoice Date."
                    )

            try:
                amount = parse_invoice_amount(
                    get_value("Amount")
                )
            except ValueError as exc:
                amount = None
                errors.append(str(exc))

            optional_values = {}

            for column in OPTIONAL_COLUMNS:
                optional_values[column.lower()] = (
                    normalize_text(get_value(column)) or None
                )

            rows.append({
                "excel_row": excel_row,
                "invoice_number": invoice_number,
                "order_number": order_number,
                "vendor_name": vendor_name,
                "vendor_code": vendor_code,
                "invoice_date": (
                    invoice_date.isoformat()
                    if invoice_date else None
                ),
                "due_date": (
                    due_date.isoformat()
                    if due_date else None
                ),
                "amount": (
                    str(amount)
                    if amount is not None
                    else None
                ),
                "period": optional_values["period"],
                "location": optional_values["location"],
                "description": optional_values["description"],
                "remarks": optional_values["remarks"],
                "errors": errors,
                "is_valid": not errors,
            })

        if total_rows == 0:
            raise ValueError(
                "Excel file contains no invoice rows."
            )

        return {
            "total_rows": total_rows,
            "rows": rows,
        }

    finally:
        workbook.close()
