from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    FINANCE = "finance"
    VIEWER = "viewer"
    SYSTEM = "system"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PaymentStatus(str, enum.Enum):
    RECEIVED = "received"
    MATCHED = "matched"
    PARTIALLY_MATCHED = "partially_matched"
    UNMATCHED = "unmatched"
    FAILED = "failed"
    REVERSED = "reversed"


class EmailDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class EmailType(str, enum.Enum):
    INVOICE = "invoice"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    REMINDER = "reminder"
    SYSTEM = "system"
    OTHER = "other"


class EmailProcessingStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DraftStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"
    EXPIRED = "expired"


class AuditStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INFO = "info"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.VIEWER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_drafts: Mapped[list["Draft"]] = relationship(
        "Draft",
        back_populates="created_by",
        foreign_keys="Draft.created_by_user_id",
    )
    approved_drafts: Mapped[list["Draft"]] = relationship(
        "Draft",
        back_populates="approved_by",
        foreign_keys="Draft.approved_by_user_id",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor_user")


class Client(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    billing_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payment_terms_days: Mapped[int] = mapped_column(nullable=False, default=30, server_default="30")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoices: Mapped[list["Invoice"]] = relationship("Invoice", back_populates="client")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="client")
    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="client")
    drafts: Mapped[list["Draft"]] = relationship("Draft", back_populates="client")


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("client_id", "invoice_number", name="uq_invoices_client_invoice_number"),
        CheckConstraint("subtotal_amount >= 0", name="subtotal_amount_non_negative"),
        CheckConstraint("tax_amount >= 0", name="tax_amount_non_negative"),
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="amount_paid_non_negative"),
        CheckConstraint("balance_due >= 0", name="balance_due_non_negative"),
        Index("ix_invoices_due_date_status", "due_date", "status"),
    )

    client_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    balance_due: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status_enum"),
        nullable=False,
        default=InvoiceStatus.OPEN,
        server_default=InvoiceStatus.OPEN.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="invoice")
    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="invoice")
    drafts: Mapped[list["Draft"]] = relationship("Draft", back_populates="invoice")


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="payment_amount_positive"),
        Index("ix_payments_date_status", "payment_date", "status"),
        Index("ix_payments_reference", "payment_reference"),
        Index("ix_payments_transaction_reference", "transaction_reference"),
    )

    client_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"),
        nullable=False,
        default=PaymentStatus.RECEIVED,
        server_default=PaymentStatus.RECEIVED.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="payments")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="payments")
    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="payment")


class Draft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("ix_drafts_status_sent_at", "status", "sent_at"),
        Index("ix_drafts_invoice_status", "invoice_id", "status"),
    )

    client_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email", server_default="email")
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, name="draft_status_enum"),
        nullable=False,
        default=DraftStatus.PENDING_APPROVAL,
        server_default=DraftStatus.PENDING_APPROVAL.value,
    )
    approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_draft_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    client: Mapped["Client"] = relationship("Client", back_populates="drafts")
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="drafts")
    created_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="created_drafts",
        foreign_keys=[created_by_user_id],
    )
    approved_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="approved_drafts",
        foreign_keys=[approved_by_user_id],
    )
    email_logs: Mapped[list["EmailLog"]] = relationship("EmailLog", back_populates="draft")


class EmailLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_logs"
    __table_args__ = (
        UniqueConstraint("gmail_message_id", name="uq_email_logs_gmail_message_id"),
        Index("ix_email_logs_received_type", "received_at", "email_type"),
        Index("ix_email_logs_processing_status", "processing_status"),
    )

    client_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    internet_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sender: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    bcc_recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    direction: Mapped[EmailDirection] = mapped_column(
        Enum(EmailDirection, name="email_direction_enum"),
        nullable=False,
    )
    email_type: Mapped[EmailType] = mapped_column(
        Enum(EmailType, name="email_type_enum"),
        nullable=False,
        default=EmailType.OTHER,
        server_default=EmailType.OTHER.value,
    )
    processing_status: Mapped[EmailProcessingStatus] = mapped_column(
        Enum(EmailProcessingStatus, name="email_processing_status_enum"),
        nullable=False,
        default=EmailProcessingStatus.PENDING,
        server_default=EmailProcessingStatus.PENDING.value,
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    attachment_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    attachment_metadata: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    client: Mapped["Client | None"] = relationship("Client", back_populates="email_logs")
    invoice: Mapped["Invoice | None"] = relationship("Invoice", back_populates="email_logs")
    payment: Mapped["Payment | None"] = relationship("Payment", back_populates="email_logs")
    draft: Mapped["Draft | None"] = relationship("Draft", back_populates="email_logs")


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_action", "created_at", "action"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status_enum"),
        nullable=False,
        default=AuditStatus.INFO,
        server_default=AuditStatus.INFO.value,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    actor_user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
