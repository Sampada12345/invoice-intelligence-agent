from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_agent.db.models import (
    AuditLog,
    AuditStatus,
    Draft,
    DraftStatus,
    Invoice,
    InvoiceStatus,
)

from .content_generator import OpenAIReminderContentGenerator, ReminderGenerationError
from .schema import (
    ReminderContentGenerator,
    ReminderDraftRecord,
    ReminderGenerationContext,
    ReminderHistoryEntry,
    ReminderKind,
)


class ReminderAgentError(RuntimeError):
    """Raised when the reminder agent cannot complete a requested operation."""


class ReminderAgent:
    """
    Detects due and overdue invoices, generates reminder drafts, stores them,
    and persists reminder history in audit logs.
    """

    REMINDABLE_STATUSES: tuple[InvoiceStatus, ...] = (
        InvoiceStatus.OPEN,
        InvoiceStatus.PARTIALLY_PAID,
        InvoiceStatus.OVERDUE,
    )

    def __init__(
        self,
        *,
        content_generator: ReminderContentGenerator | None = None,
        due_window_days: int = 7,
        logger: logging.Logger | None = None,
    ) -> None:
        self._content_generator = content_generator or OpenAIReminderContentGenerator()
        self._due_window_days = due_window_days
        self._logger = logger or logging.getLogger(__name__)

    def detect_due_invoices(
        self,
        session: Session,
        *,
        as_of: date | None = None,
        within_days: int | None = None,
    ) -> list[Invoice]:
        today = as_of or date.today()
        day_window = within_days if within_days is not None else self._due_window_days
        upper_bound = today + timedelta(days=day_window)

        stmt = (
            select(Invoice)
            .where(Invoice.status.in_((InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID)))
            .where(Invoice.due_date >= today)
            .where(Invoice.due_date <= upper_bound)
            .order_by(Invoice.due_date.asc(), Invoice.issue_date.asc())
        )
        return list(session.scalars(stmt))

    def detect_overdue_invoices(
        self,
        session: Session,
        *,
        as_of: date | None = None,
        update_status: bool = True,
    ) -> list[Invoice]:
        today = as_of or date.today()
        stmt = (
            select(Invoice)
            .where(Invoice.status.in_(self.REMINDABLE_STATUSES))
            .where(Invoice.due_date < today)
            .order_by(Invoice.due_date.asc(), Invoice.issue_date.asc())
        )
        invoices = list(session.scalars(stmt))

        if update_status:
            for invoice in invoices:
                if invoice.status in {InvoiceStatus.OPEN, InvoiceStatus.PARTIALLY_PAID}:
                    invoice.status = InvoiceStatus.OVERDUE

        return invoices

    def generate_reminder_for_invoice(
        self,
        session: Session,
        invoice_or_id: Invoice | UUID,
        *,
        actor_user_id: UUID | None = None,
        as_of: date | None = None,
        auto_commit: bool = False,
    ) -> ReminderDraftRecord:
        invoice = self._resolve_invoice(session, invoice_or_id)
        reminder_kind = self._classify_invoice(invoice, as_of=as_of)
        existing_draft = self._find_existing_pending_draft(session, invoice.id)
        if existing_draft:
            self._record_history(
                session,
                invoice=invoice,
                action="draft_reused",
                actor_user_id=actor_user_id,
                details={
                    "draft_id": str(existing_draft.id),
                    "reminder_kind": reminder_kind.value,
                    "reason": "Existing pending approval draft reused.",
                },
            )
            if auto_commit:
                session.commit()
            return self._to_record(existing_draft, reminder_kind)

        context = self._build_context(invoice, reminder_kind, as_of=as_of)
        try:
            content = self._content_generator.generate(context)
        except ReminderGenerationError as exc:
            raise ReminderAgentError(str(exc)) from exc

        draft = Draft(
            client_id=invoice.client_id,
            invoice_id=invoice.id,
            created_by_user_id=actor_user_id,
            subject=content.subject,
            body_text=content.body_text,
            body_html=content.body_html,
            channel="email",
            status=DraftStatus.PENDING_APPROVAL,
        )
        session.add(draft)
        session.flush()

        self._record_history(
            session,
            invoice=invoice,
            action="draft_created",
            actor_user_id=actor_user_id,
            details={
                "draft_id": str(draft.id),
                "reminder_kind": reminder_kind.value,
                "subject": draft.subject,
                "due_date": invoice.due_date.isoformat(),
                "balance_due": f"{invoice.balance_due:.2f}",
                "currency": invoice.currency,
            },
        )

        if auto_commit:
            session.commit()
        return self._to_record(draft, reminder_kind)

    def generate_reminders(
        self,
        session: Session,
        *,
        as_of: date | None = None,
        within_days: int | None = None,
        include_overdue: bool = True,
        actor_user_id: UUID | None = None,
        auto_commit: bool = False,
    ) -> list[ReminderDraftRecord]:
        today = as_of or date.today()
        due_invoices = self.detect_due_invoices(session, as_of=today, within_days=within_days)
        overdue_invoices = self.detect_overdue_invoices(session, as_of=today) if include_overdue else []

        records: list[ReminderDraftRecord] = []
        seen_invoice_ids: set[UUID] = set()
        for invoice in [*due_invoices, *overdue_invoices]:
            if invoice.id in seen_invoice_ids:
                continue
            seen_invoice_ids.add(invoice.id)
            records.append(
                self.generate_reminder_for_invoice(
                    session,
                    invoice,
                    actor_user_id=actor_user_id,
                    as_of=today,
                    auto_commit=False,
                )
            )

        if auto_commit:
            session.commit()
        return records

    def get_reminder_history(
        self,
        session: Session,
        invoice_or_id: Invoice | UUID,
    ) -> list[ReminderHistoryEntry]:
        invoice_id = invoice_or_id.id if isinstance(invoice_or_id, Invoice) else invoice_or_id
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == "invoice_reminder")
            .where(AuditLog.entity_id == str(invoice_id))
            .order_by(AuditLog.created_at.asc())
        )
        return [
            ReminderHistoryEntry(
                invoice_id=UUID(log.entity_id),
                action=log.action,
                created_at=log.created_at,
                details=log.details,
            )
            for log in session.scalars(stmt)
        ]

    def _resolve_invoice(self, session: Session, invoice_or_id: Invoice | UUID) -> Invoice:
        if isinstance(invoice_or_id, Invoice):
            return invoice_or_id

        invoice = session.get(Invoice, invoice_or_id)
        if invoice is None:
            raise ReminderAgentError(f"Invoice not found: {invoice_or_id}")
        return invoice

    def _classify_invoice(self, invoice: Invoice, *, as_of: date | None = None) -> ReminderKind:
        today = as_of or date.today()
        if invoice.due_date < today:
            return ReminderKind.OVERDUE
        return ReminderKind.DUE_SOON

    def _build_context(
        self,
        invoice: Invoice,
        reminder_kind: ReminderKind,
        *,
        as_of: date | None = None,
    ) -> ReminderGenerationContext:
        today = as_of or date.today()
        days_delta = (invoice.due_date - today).days
        return ReminderGenerationContext(
            reminder_kind=reminder_kind,
            client_name=invoice.client.name if invoice.client else "Customer",
            invoice_number=invoice.invoice_number,
            due_date=invoice.due_date,
            amount_due=invoice.balance_due,
            currency=invoice.currency,
            days_delta=days_delta,
            invoice_status=invoice.status.value,
        )

    def _find_existing_pending_draft(self, session: Session, invoice_id: UUID) -> Draft | None:
        stmt = (
            select(Draft)
            .where(Draft.invoice_id == invoice_id)
            .where(Draft.status == DraftStatus.PENDING_APPROVAL)
            .order_by(Draft.created_at.desc())
        )
        return session.scalars(stmt).first()

    def _record_history(
        self,
        session: Session,
        *,
        invoice: Invoice,
        action: str,
        actor_user_id: UUID | None,
        details: dict[str, str],
    ) -> None:
        audit_log = AuditLog(
            actor_user_id=actor_user_id,
            entity_type="invoice_reminder",
            entity_id=str(invoice.id),
            action=action,
            status=AuditStatus.SUCCESS,
            source="reminder_agent",
            details=details,
        )
        session.add(audit_log)

    @staticmethod
    def _to_record(draft: Draft, reminder_kind: ReminderKind) -> ReminderDraftRecord:
        return ReminderDraftRecord(
            draft_id=draft.id,
            invoice_id=draft.invoice_id,
            client_id=draft.client_id,
            reminder_kind=reminder_kind,
            draft_status=draft.status.value,
            subject=draft.subject,
            body_text=draft.body_text,
            created_at=draft.created_at.replace(tzinfo=timezone.utc)
            if draft.created_at.tzinfo is None
            else draft.created_at,
        )
