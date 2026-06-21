from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ExtractedInvoiceStatus(str, Enum):
    OPEN = "open"
    PAID = "paid"
    OVERDUE = "overdue"
    DRAFT = "draft"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class InvoiceExtractionResult(BaseModel):
    """
    Canonical output schema for invoice extraction.

    This schema maps exactly to the requested JSON payload fields.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    invoice_number: str = Field(min_length=1, max_length=128)
    client_name: str = Field(min_length=1, max_length=255)
    client_email: EmailStr | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    status: ExtractedInvoiceStatus = ExtractedInvoiceStatus.UNKNOWN

    @field_validator("invoice_number", "client_name")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @classmethod
    def output_json_schema(cls) -> dict[str, Any]:
        return cls.model_json_schema()
