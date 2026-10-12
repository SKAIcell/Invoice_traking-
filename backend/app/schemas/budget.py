from datetime import datetime
from decimal import Decimal
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    financial_year: str
    planned_amount: Decimal = Field(
        ge=0, max_digits=18, decimal_places=2
    )
    approved_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=18,
        decimal_places=2,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Budget name cannot be empty")
        return value

    @field_validator("financial_year")
    @classmethod
    def validate_fy(cls, value):
        match = re.fullmatch(
            r"(\d{4})-(\d{4})", value
        )

        if not match:
            raise ValueError(
                "Use FY format YYYY-YYYY"
            )

        start, end = map(int, match.groups())

        if end != start + 1:
            raise ValueError(
                "Financial year must span one year"
            )

        return value

    @model_validator(mode="after")
    def check_amounts(self):
        if self.approved_amount > self.planned_amount:
            raise ValueError(
                "Approved amount cannot exceed planned amount"
            )
        return self


class BudgetUpdate(BaseModel):
    planned_amount: Decimal | None = Field(
        default=None, ge=0,
        max_digits=18, decimal_places=2
    )
    approved_amount: Decimal | None = Field(
        default=None, ge=0,
        max_digits=18, decimal_places=2
    )


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    financial_year: str
    planned_amount: Decimal
    approved_amount: Decimal
    created_at: datetime
