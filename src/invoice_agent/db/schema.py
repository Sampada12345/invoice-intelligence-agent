from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    AuditStatus,
    DraftStatus,
    EmailDirection,
    EmailProcessingStatus,
    EmailType,
    InvoiceStatus,
    PaymentStatus,
    UserRole,
)


class SchemaBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="forbid",
    )


class TimestampedSchema(SchemaBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None


class UserBase(SchemaBase):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    telegram_chat_id: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserCreate(UserBase):
    pass


class UserUpdate(SchemaBase):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    telegram_chat_id: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()


class UserRead(TimestampedSchema, UserBase):
    pass


class ClientBase(SchemaBase):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: str | None = None
    tax_id: str | None = Field(default=None, max_length=128)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    is_active: bool = True
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_client_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()


class ClientCreate(ClientBase):
    pass


class ClientUpdate(SchemaBase):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: str | None = None
    tax_id: str | None = Field(default=None, max_length=128)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None
    notes: str | None = None


class ClientRead(TimestampedSchema, ClientBase):
    pass


class InvoiceBase(SchemaBase):
    client_id: UUID
    invoice_number: str = Field(min_length=1, max_length=128)
    issue_date: date
    due_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    subtotal_amount: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total_amount: Decimal = Field(ge=0)
    amount_paid: Decimal = Field(default=Decimal("0.00"), ge=0)
    balance_due: Decimal | None = Field(default=None, ge=0)
    status: InvoiceStatus = InvoiceStatus.OPEN
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("invoice_number")
    @classmethod
    def normalize_invoice_number(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_invoice_amounts(self) -> "InvoiceBase":
        if self.due_date < self.issue_date:
            raise ValueError("due_date cannot be earlier than issue_date")

        expected_total = self.subtotal_amount + self.tax_amount
        if self.total_amount != expected_total:
            raise ValueError("total_amount must equal subtotal_amount + tax_amount")

        if self.amount_paid > self.total_amount:
            raise ValueError("amount_paid cannot exceed total_amount")

        calculated_balance = self.total_amount - self.amount_paid
        if self.balance_due is None:
            self.balance_due = calculated_balance
        elif self.balance_due != calculated_balance:
            raise ValueError("balance_due must equal total_amount - amount_paid")

        return self


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(SchemaBase):
    client_id: UUID | None = None
    invoice_number: str | None = Field(default=None, min_length=1, max_length=128)
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    subtotal_amount: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, ge=0)
    amount_paid: Decimal | None = Field(default=None, ge=0)
    balance_due: Decimal | None = Field(default=None, ge=0)
    status: InvoiceStatus | None = None
    notes: str | None = None


class InvoiceRead(TimestampedSchema, InvoiceBase):
    pass


class PaymentBase(SchemaBase):
    client_id: UUID
    invoice_id: UUID | None = None
    payment_reference: str | None = Field(default=None, max_length=128)
    transaction_reference: str | None = Field(default=None, max_length=128)
    payment_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    amount: Decimal = Field(gt=0)
    payment_method: str | None = Field(default=None, max_length=64)
    status: PaymentStatus = PaymentStatus.RECEIVED
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_payment_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("payment_reference", "transaction_reference")
    @classmethod
    def normalize_references(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(SchemaBase):
    client_id: UUID | None = None
    invoice_id: UUID | None = None
    payment_reference: str | None = Field(default=None, max_length=128)
    transaction_reference: str | None = Field(default=None, max_length=128)
    payment_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount: Decimal | None = Field(default=None, gt=0)
    payment_method: str | None = Field(default=None, max_length=64)
    status: PaymentStatus | None = None
    notes: str | None = None


class PaymentRead(TimestampedSchema, PaymentBase):
    pass


class EmailLogBase(SchemaBase):
    client_id: UUID | None = None
    invoice_id: UUID | None = None
    payment_id: UUID | None = None
    draft_id: UUID | None = None
    gmail_message_id: str | None = Field(default=None, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    internet_message_id: str | None = Field(default=None, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(default_factory=list)
    bcc_recipients: list[str] = Field(default_factory=list)
    subject: str | None = Field(default=None, max_length=255)
    direction: EmailDirection
    email_type: EmailType = EmailType.OTHER
    processing_status: EmailProcessingStatus = EmailProcessingStatus.PENDING
    received_at: datetime
    processed_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    attachment_count: int = Field(default=0, ge=0)
    attachment_paths: list[str] = Field(default_factory=list)
    attachment_metadata: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    raw_payload: dict[str, Any] | None = None

    @field_validator("sender")
    @classmethod
    def normalize_sender(cls, value: str) -> str:
        return value.strip().lower()


class EmailLogCreate(EmailLogBase):
    pass


class EmailLogUpdate(SchemaBase):
    client_id: UUID | None = None
    invoice_id: UUID | None = None
    payment_id: UUID | None = None
    draft_id: UUID | None = None
    gmail_message_id: str | None = Field(default=None, max_length=255)
    thread_id: str | None = Field(default=None, max_length=255)
    internet_message_id: str | None = Field(default=None, max_length=255)
    sender: str | None = Field(default=None, min_length=1, max_length=255)
    recipients: list[str] | None = None
    cc_recipients: list[str] | None = None
    bcc_recipients: list[str] | None = None
    subject: str | None = Field(default=None, max_length=255)
    direction: EmailDirection | None = None
    email_type: EmailType | None = None
    processing_status: EmailProcessingStatus | None = None
    received_at: datetime | None = None
    processed_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    attachment_count: int | None = Field(default=None, ge=0)
    attachment_paths: list[str] | None = None
    attachment_metadata: list[dict[str, Any]] | None = None
    error_message: str | None = None
    raw_payload: dict[str, Any] | None = None


class EmailLogRead(TimestampedSchema, EmailLogBase):
    pass


class DraftBase(SchemaBase):
    client_id: UUID
    invoice_id: UUID
    created_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    subject: str = Field(min_length=1, max_length=255)
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    channel: str = Field(default="email", min_length=1, max_length=32)
    status: DraftStatus = DraftStatus.PENDING_APPROVAL
    approval_notes: str | None = None
    approval_requested_at: datetime | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    external_draft_id: str | None = Field(default=None, max_length=255)
    external_message_id: str | None = Field(default=None, max_length=255)


class DraftCreate(DraftBase):
    pass


class DraftUpdate(SchemaBase):
    client_id: UUID | None = None
    invoice_id: UUID | None = None
    created_by_user_id: UUID | None = None
    approved_by_user_id: UUID | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    body_text: str | None = Field(default=None, min_length=1)
    body_html: str | None = None
    channel: str | None = Field(default=None, min_length=1, max_length=32)
    status: DraftStatus | None = None
    approval_notes: str | None = None
    approval_requested_at: datetime | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    external_draft_id: str | None = Field(default=None, max_length=255)
    external_message_id: str | None = Field(default=None, max_length=255)


class DraftRead(TimestampedSchema, DraftBase):
    pass


class AuditLogBase(SchemaBase):
    actor_user_id: UUID | None = None
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=128)
    status: AuditStatus = AuditStatus.INFO
    request_id: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=64)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=255)
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogUpdate(SchemaBase):
    actor_user_id: UUID | None = None
    entity_type: str | None = Field(default=None, min_length=1, max_length=64)
    entity_id: str | None = Field(default=None, min_length=1, max_length=64)
    action: str | None = Field(default=None, min_length=1, max_length=128)
    status: AuditStatus | None = None
    request_id: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=64)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=255)
    details: dict[str, Any] | None = None


class AuditLogRead(SchemaBase):
    id: UUID
    actor_user_id: UUID | None = None
    entity_type: str
    entity_id: str
    action: str
    status: AuditStatus
    request_id: str | None = None
    source: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, Any]
    created_at: datetime
