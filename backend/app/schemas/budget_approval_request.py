from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ApprovalRequestType = Literal["CREATE", "UPDATE"]
ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class BudgetApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    budget_id: int | None
    request_type: ApprovalRequestType
    status: ApprovalStatus

    name: str
    financial_year: str
    budget_type: Literal["OPEX", "CAPEX"]
    planned_amount: Decimal

    # The IT Head decides this during approval.
    # It remains None while the request is pending or rejected.
    approved_amount: Decimal | None

    requested_by_id: int
    decided_by_id: int | None

    requested_at: datetime
    decided_at: datetime | None

    remarks: str | None


class BudgetApprovalDecision(BaseModel):
    # Required only when approving.
    # The backend will validate that it is present and within the
    # requested planned amount before approving.
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
