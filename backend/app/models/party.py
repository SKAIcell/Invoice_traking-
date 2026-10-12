from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Party(Base):
    __tablename__ = "parties"

    __table_args__ = (
        UniqueConstraint(
            "party_type", "code",
            name="uq_party_type_code",
        ),
        CheckConstraint(
            "party_type IN ('VENDOR', 'CUSTOMER')",
            name="ck_party_type",
        ),
        CheckConstraint(
            "code = upper(trim(code)) AND length(code) > 0",
            name="ck_party_code_format",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_party_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    party_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True
    )

    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(500))

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
