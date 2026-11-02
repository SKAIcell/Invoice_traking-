
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


OrderType = Literal["PO", "SO"]


def validate_fy_date(financial_year: str, order_date: date) -> None:
    match = re.fullmatch(
        r"([1-9]\d{3})-([1-9]\d{3})",
        financial_year or "",
    )

    if not match:
        raise ValueError("FY must use YYYY-YYYY format")

    start_year, end_year = map(int, match.groups())

    if end_year != start_year + 1:
        raise ValueError("Invalid financial year")

    if not (
        date(start_year, 4, 1)
        <= order_date
        <= date(end_year, 3, 31)
    ):
        raise ValueError("Order date is outside selected FY")


def expected_budget_type(order_type: str) -> str:
    if order_type == "PO":
        return "CAPEX"
    if order_type == "SO":
        return "OPEX"
    raise ValueError("Order type must be PO or SO")


class OrderCreate(BaseModel):
    order_type: OrderType
    order_number: str = Field(min_length=1, max_length=64)
    party_id: int = Field(gt=0)

    # Both PO and SO require a budget.
    budget_id: int = Field(gt=0)

    financial_year: str
    order_date: date
    order_period: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    description: str | None = None

    @field_validator("order_number")
    @classmethod
    def normalize_order_number(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Order number is required")
        return value

    @model_validator(mode="after")
    def validate_order(self):
        if self.budget_id is None:
            raise ValueError(
                f"{self.order_type} requires a "
                f"{expected_budget_type(self.order_type)} budget"
            )

        validate_fy_date(self.financial_year, self.order_date)
        return self


class OrderUpdate(BaseModel):
    # PATCH fields are optional; the route validates final values.
    order_type: OrderType | None = None
    order_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )
    party_id: int | None = Field(default=None, gt=0)
    budget_id: int | None = Field(default=None, gt=0)
    financial_year: str | None = None
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=2,
    )
    order_date: date | None = None
    order_period: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = None

    @field_validator("order_number")
    @classmethod
    def normalize_order_number(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not value:
            raise ValueError("Order number is required")
        return value

    @field_validator("financial_year")
    @classmethod
    def normalize_financial_year(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        match = re.fullmatch(r"([1-9]\d{3})-([1-9]\d{3})", value)

        if not match:
            raise ValueError("FY must use YYYY-YYYY format")

        start_year, end_year = map(int, match.groups())
        if end_year != start_year + 1:
            raise ValueError("Invalid financial year")

        return value

    @field_validator("order_period", "location", "description")
    @classmethod
    def normalize_optional_text(cls, value: str | None):
        if value is None:
            return None
        value = value.strip()
        return value or None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_type: str
    order_number: str
    party_id: int
    party_name: str | None = None
    budget_id: int | None
    budget_name: str | None = None
    financial_year: str
    order_date: date
    order_period: str | None = None
    location: str | None = None
    amount: Decimal
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    submitted_invoice_amount: Decimal = Decimal("0.00")
    available_order_value: Decimal = Decimal("0.00")
    total_submitted_invoice: int = 0

    # Document paths are returned so the frontend can show
    # persistent upload status after refresh and navigation.
    order_file_path: str | None = None
    approval_file_path: str | None = None
