
from datetime import datetime
from decimal import Decimal
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


BudgetType = Literal["OPEX", "CAPEX"]


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    financial_year: str
    budget_type: BudgetType = "OPEX"
    planned_amount: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    approved_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=18,
        decimal_places=2,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Budget name cannot be empty.")
        return value

    @field_validator("financial_year")
    @classmethod
    def validate_financial_year(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"\d{4}-\d{4}", value):
            raise ValueError("Financial year must use YYYY-YYYY format.")

        start_year = int(value[:4])
        end_year = int(value[5:])
        if end_year != start_year + 1:
            raise ValueError(
                "Financial year must cover consecutive years, e.g. 2026-2027."
            )
        return value

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.approved_amount > self.planned_amount:
            raise ValueError(
                "Approved amount cannot exceed planned amount."
            )
        return self


class BudgetUpdate(BaseModel):
    planned_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    approved_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=18,
        decimal_places=2,
    )


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    financial_year: str
    budget_type: BudgetType
    planned_amount: Decimal
    approved_amount: Decimal
    created_at: datetime
