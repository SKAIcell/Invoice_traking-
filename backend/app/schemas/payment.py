
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    invoice_id: int = Field(gt=0)
    payment_date: date
    amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
    )
    reference_number: str | None = Field(
        default=None,
        max_length=100,
    )
    notes: str | None = None


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    payment_date: date
    amount: Decimal
    reference_number: str | None
    notes: str | None
    created_at: datetime
