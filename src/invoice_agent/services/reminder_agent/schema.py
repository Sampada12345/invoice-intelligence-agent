from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReminderKind(str, Enum):
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"


class ReminderContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=255)
    body_text: str = Field(min_length=1)
    body_html: str | None = None


class ReminderDraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: UUID
    invoice_id: UUID
    client_id: UUID
    reminder_kind: ReminderKind
    draft_status: str
    subject: str
    body_text: str
    created_at: datetime


class ReminderHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: UUID
    action: str
    created_at: datetime
    details: dict[str, Any]


class ReminderGenerationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder_kind: ReminderKind
    client_name: str
    invoice_number: str
    due_date: date
    amount_due: Decimal
    currency: str
    days_delta: int
    invoice_status: str


class ReminderContentGenerator(Protocol):
    def generate(self, context: ReminderGenerationContext) -> ReminderContent:
        """Generate reminder content for an invoice context."""
