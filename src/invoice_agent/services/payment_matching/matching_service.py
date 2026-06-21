from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_agent.db.models import Invoice, InvoiceStatus, Payment, PaymentStatus


class PaymentMatchStrategy(str, Enum):
    INVOICE_NUMBER = "invoice_number"
    AMOUNT_AND_CLIENT = "amount_and_client"
    CLIENT_ONLY = "client_only"


@dataclass(frozen=True, slots=True)
class PaymentMatchResult:
    matched: bool
    strategy: PaymentMatchStrategy | None
    payment_id: UUID
    invoice_id: UUID | None
    payment_status: PaymentStatus
    invoice_status: InvoiceStatus | None
    reason: str | None = None


class PaymentMatchingError(RuntimeError):
    """Raised when a payment matching request is invalid."""


class PaymentMatchingService:
    """
    Matches payments to invoices and applies status transitions.

    Matching order:
    1. invoice number reference
    2. exact amount within the same client
    3. single open invoice for the same client
    """

    OPEN_INVOICE_STATUSES: tuple[InvoiceStatus, ...] = (
        InvoiceStatus.OPEN,
        InvoiceStatus.PARTIALLY_PAID,
        InvoiceStatus.OVERDUE,
    )

    def __init__(
        self,
        *,
        strict_currency: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self._strict_currency = strict_currency
        self._logger = logger or logging.getLogger(__name__)

    def match_payment(
        self,
        session: Session,
        payment_or_id: Payment | UUID,
        *,
        auto_commit: bool = False,
    ) -> PaymentMatchResult:
        payment = self._resolve_payment(session, payment_or_id)

        if payment.invoice_id and payment.status in {
            PaymentStatus.MATCHED,
            PaymentStatus.PARTIALLY_MATCHED,
        }:
            invoice_status = payment.invoice.status if payment.invoice else None
            return PaymentMatchResult(
                matched=True,
                strategy=None,
                payment_id=payment.id,
                invoice_id=payment.invoice_id,
                payment_status=payment.status,
                invoice_status=invoice_status,
                reason="Payment is already associated with an invoice.",
            )

        candidate_invoices = self.find_candidate_invoices(session, payment)
        selected_invoice, strategy, reason = self._select_match(payment, candidate_invoices)
        if selected_invoice is None:
            payment.status = PaymentStatus.UNMATCHED
            if auto_commit:
                session.commit()
            return PaymentMatchResult(
                matched=False,
                strategy=None,
                payment_id=payment.id,
                invoice_id=None,
                payment_status=payment.status,
                invoice_status=None,
                reason=reason,
            )

        result = self.apply_payment_to_invoice(payment, selected_invoice)
        result = PaymentMatchResult(
            matched=True,
            strategy=strategy,
            payment_id=payment.id,
            invoice_id=selected_invoice.id,
            payment_status=result.payment_status,
            invoice_status=result.invoice_status,
            reason=None,
        )
        if auto_commit:
            session.commit()
        return result

    def find_candidate_invoices(
        self,
        session: Session,
        payment: Payment,
        *,
        include_closed: bool = False,
    ) -> list[Invoice]:
        stmt = select(Invoice).where(Invoice.client_id == payment.client_id)
        if self._strict_currency:
            stmt = stmt.where(Invoice.currency == payment.currency)
        if not include_closed:
            stmt = stmt.where(Invoice.status.in_(self.OPEN_INVOICE_STATUSES))
        stmt = stmt.order_by(Invoice.due_date.asc(), Invoice.issue_date.asc())
        return list(session.scalars(stmt))

    def apply_payment_to_invoice(self, payment: Payment, invoice: Invoice) -> PaymentMatchResult:
        if payment.amount <= 0:
            raise PaymentMatchingError("Payment amount must be positive.")
        if invoice.status not in self.OPEN_INVOICE_STATUSES and invoice.status != InvoiceStatus.OPEN:
            raise PaymentMatchingError(
                f"Invoice {invoice.id} is not in a payable state: {invoice.status.value}."
            )
        if self._strict_currency and payment.currency != invoice.currency:
            raise PaymentMatchingError("Payment and invoice currencies do not match.")
        if payment.amount > invoice.balance_due:
            raise PaymentMatchingError(
                f"Payment amount {payment.amount} exceeds invoice balance {invoice.balance_due}."
            )

        new_amount_paid = self._to_money(invoice.amount_paid) + self._to_money(payment.amount)
        new_balance = self._to_money(invoice.total_amount) - new_amount_paid

        invoice.amount_paid = new_amount_paid
        invoice.balance_due = max(new_balance, Decimal("0.00"))

        if invoice.balance_due == Decimal("0.00"):
            invoice.status = InvoiceStatus.PAID
            payment.status = PaymentStatus.MATCHED
        else:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
            payment.status = PaymentStatus.PARTIALLY_MATCHED

        payment.invoice = invoice
        payment.invoice_id = invoice.id

        self._logger.debug(
            "Applied payment %s to invoice %s. Invoice status=%s payment status=%s",
            payment.id,
            invoice.id,
            invoice.status.value,
            payment.status.value,
        )

        return PaymentMatchResult(
            matched=True,
            strategy=None,
            payment_id=payment.id,
            invoice_id=invoice.id,
            payment_status=payment.status,
            invoice_status=invoice.status,
            reason=None,
        )

    def _resolve_payment(self, session: Session, payment_or_id: Payment | UUID) -> Payment:
        if isinstance(payment_or_id, Payment):
            return payment_or_id

        payment = session.get(Payment, payment_or_id)
        if payment is None:
            raise PaymentMatchingError(f"Payment not found: {payment_or_id}")
        return payment

    def _select_match(
        self,
        payment: Payment,
        invoices: Sequence[Invoice],
    ) -> tuple[Invoice | None, PaymentMatchStrategy | None, str | None]:
        if not invoices:
            return None, None, "No candidate invoices found for the payment client."

        invoice_number_match = self._match_by_invoice_number(payment, invoices)
        if invoice_number_match:
            return invoice_number_match, PaymentMatchStrategy.INVOICE_NUMBER, None

        amount_client_match = self._match_by_amount(payment, invoices)
        if amount_client_match:
            return amount_client_match, PaymentMatchStrategy.AMOUNT_AND_CLIENT, None

        client_only_match, client_reason = self._match_by_client(payment, invoices)
        if client_only_match:
            return client_only_match, PaymentMatchStrategy.CLIENT_ONLY, None
        return None, None, client_reason or "No safe automatic match found."

    def _match_by_invoice_number(self, payment: Payment, invoices: Sequence[Invoice]) -> Invoice | None:
        references = self._normalized_references(payment)
        if not references:
            return None

        matches = [invoice for invoice in invoices if self._invoice_in_references(invoice.invoice_number, references)]
        return self._resolve_ambiguity(payment, matches)

    def _match_by_amount(self, payment: Payment, invoices: Sequence[Invoice]) -> Invoice | None:
        matches = [
            invoice
            for invoice in invoices
            if self._to_money(invoice.balance_due) == self._to_money(payment.amount)
        ]
        return self._resolve_ambiguity(payment, matches)

    def _match_by_client(
        self,
        payment: Payment,
        invoices: Sequence[Invoice],
    ) -> tuple[Invoice | None, str | None]:
        if len(invoices) != 1:
            return None, "Client-only matching is ambiguous because multiple open invoices exist."

        invoice = invoices[0]
        if self._to_money(payment.amount) > self._to_money(invoice.balance_due):
            return None, "Payment exceeds the only open invoice balance for the client."
        return invoice, None

    def _resolve_ambiguity(self, payment: Payment, matches: Sequence[Invoice]) -> Invoice | None:
        if not matches:
            return None
        if len(matches) == 1:
            invoice = matches[0]
            if self._to_money(payment.amount) <= self._to_money(invoice.balance_due):
                return invoice
            return None
        exact_balance_matches = [
            invoice
            for invoice in matches
            if self._to_money(invoice.balance_due) == self._to_money(payment.amount)
        ]
        if len(exact_balance_matches) == 1:
            return exact_balance_matches[0]
        return None

    @staticmethod
    def _normalized_references(payment: Payment) -> set[str]:
        values = {payment.payment_reference or "", payment.transaction_reference or ""}
        normalized = {PaymentMatchingService._normalize_token(value) for value in values if value}
        return {value for value in normalized if value}

    @staticmethod
    def _normalize_token(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    def _invoice_in_references(self, invoice_number: str, references: set[str]) -> bool:
        normalized_invoice_number = self._normalize_token(invoice_number)
        return any(normalized_invoice_number and normalized_invoice_number in reference for reference in references)

    @staticmethod
    def _to_money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"))
