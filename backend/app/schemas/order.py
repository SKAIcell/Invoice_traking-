

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


def validate_fy_date(financial_year: str, order_date: date):
    match = re.fullmatch(
        r"([1-9]\d{3})-([1-9]\d{3})",
        financial_year,
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


class OrderCreate(BaseModel):
    order_type: Literal["PO", "SO"]
    order_number: str = Field(min_length=1, max_length=64)
    party_id: int = Field(gt=0)
    budget_id: int | None = Field(default=None, gt=0)
    financial_year: str
    order_date: date
    amount: Decimal = Field(
        gt=0, max_digits=18, decimal_places=2
    )
    description: str | None = None

    @field_validator("order_number")
    @classmethod
    def normalize_order_number(cls, value):
        value = value.strip().upper()

        if not value:
            raise ValueError("Order number is required")

        return value

    @model_validator(mode="after")
    def validate_order(self):
        if self.order_type == "PO" and self.budget_id is None:
            raise ValueError("PO requires a budget")

        if self.order_type == "SO" and self.budget_id is not None:
            raise ValueError("SO cannot use an expense budget")

        validate_fy_date(
            self.financial_year,
            self.order_date,
        )

        return self


class OrderUpdate(BaseModel):
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=2,
    )
    order_date: date | None = None
    description: str | None = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_type: str
    order_number: str
    party_id: int
    budget_id: int | None
    financial_year: str
    order_date: date
    amount: Decimal
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
