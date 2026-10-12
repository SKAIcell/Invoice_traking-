from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartyCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    party_type: Literal["VENDOR", "CUSTOMER"]
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)

    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("party_type", "code", mode="before")
    @classmethod
    def normalize_codes(cls, value):
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PartyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    party_type: str
    code: str
    name: str
    email: str | None
    phone: str | None
    address: str | None
    is_active: bool
    created_at: datetime
