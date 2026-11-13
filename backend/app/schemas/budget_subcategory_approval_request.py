
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SubcategoryRequestType = Literal["CREATE", "UPDATE"]
SubcategoryApprovalStatus = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
]


class BudgetSubcategoryRequestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    planned_amount: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=2,
    )


class BudgetSubcategoryRequestUpdate(BaseModel):
    planned_amount: Decimal = Field(
        ge=0,
        max_digits=18,
        decimal_places=2,
    )


class BudgetSubcategoryApprovalDecision(BaseModel):
    approved_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    remarks: str | None = Field(
        default=None,
        max_length=2000,
    )


class BudgetSubcategoryApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    budget_id: int
    subcategory_id: int | None
    request_type: SubcategoryRequestType
    status: SubcategoryApprovalStatus
    name: str
    planned_amount: Decimal
    approved_amount: Decimal | None
    has_approval_copy: bool = False
    requested_by_id: int
    decided_by_id: int | None
    requested_at: datetime
    decided_at: datetime | None
    remarks: str | None


class BudgetSubcategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    budget_id: int
    name: str
    planned_amount: Decimal
    approved_amount: Decimal
    has_approval_copy: bool = False
    created_at: datetime
