
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class InvoiceCreate(BaseModel):
    invoice_type: Literal["PURCHASE", "SALES"]
    invoice_number: str = Field(min_length=1, max_length=100)
    order_id: int = Field(gt=0)
    party_id: int = Field(gt=0)
    financial_year: str = Field(
        min_length=9,
        max_length=9,
        pattern=r"^\d{4}-\d{4}$",
    )
    invoice_date: date
    due_date: date
    period: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    status: str = Field(default="DRAFT", max_length=20)
    description: str | None = None
    remarks: str | None = None

    @field_validator("period", "location")
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_dates_and_financial_year(self):
        if self.due_date < self.invoice_date:
            raise ValueError("Due date cannot be before invoice date")

        start_year, end_year = self.financial_year.split("-")
        if int(end_year) != int(start_year) + 1:
            raise ValueError(
                "Financial year must be consecutive, e.g. 2026-2027"
            )

        if not self.invoice_number.strip():
            raise ValueError("Invoice number cannot be blank")

        return self


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_type: str
    invoice_number: str
    order_id: int
    party_id: int
    financial_year: str
    invoice_date: date
    due_date: date
    date_sent_to_accounts: date | None = None
    period: str | None = None
    location: str | None = None
    amount: Decimal
    status: str
    description: str | None
    remarks: str | None = None
    invoice_file_path: str | None = None
    created_at: datetime
    updated_at: datetime


class InvoiceDateSentUpdate(BaseModel):
    date_sent_to_accounts: date | None = None


class OrderInvoiceResponse(BaseModel):
    """Invoice row returned in an order's invoice register."""

    id: int
    invoice_type: str
    invoice_number: str
    invoice_date: date
    entry_date: datetime | None = None
    due_date: date
    party_id: int
    party_name: str | None = None
    vendor_name: str | None = None
    order_id: int
    order_number: str | None = None
    financial_year: str
    budget_name: str | None = None
    budget_type: str | None = None
    amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    period: str | None = None
    location: str | None = None
    remarks: str | None = None
    date_sent_to_accounts: date | None = None
    invoice_file_path: str | None = None
    payment_status: str
    status: str


class InvoiceSummaryResponse(BaseModel):
    id: int
    invoice_number: str
    invoice_date: date
    due_date: date
    amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    payment_status: str


class DuplicateInvoiceDetails(BaseModel):
    message: str
    invoice_date: date
    invoice_number: str
    po_number: str | None
    entry_date: datetime
    date_sent_to_accounts: date | None = None
    amount: Decimal


class InvoiceRegisterResponse(BaseModel):
    """Expanded invoice register row for the finance UI."""

    id: int
    invoice_type: str
    invoice_number: str
    invoice_date: date
    entry_date: datetime
    order_id: int
    order_number: str
    party_id: int
    party_name: str
    financial_year: str
    budget_name: str
    budget_type: str
    amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    due_date: date
    date_sent_to_accounts: date | None = None
    payment_status: str
    invoice_file_path: str | None = None
