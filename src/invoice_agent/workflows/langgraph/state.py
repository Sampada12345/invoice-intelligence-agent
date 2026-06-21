from __future__ import annotations

import operator
from datetime import date
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session
from typing_extensions import Annotated, NotRequired, TypedDict


class EmailEnvelope(TypedDict, total=False):
    message_id: str
    subject: str
    sender: str
    recipients: list[str]
    body_text: str
    body_html: str
    attachment_paths: list[str]
    label_ids: list[str]
    detected_type: str


class ExtractedInvoicePayload(TypedDict, total=False):
    invoice_number: str
    client_name: str
    client_email: str | None
    invoice_date: str | None
    due_date: str | None
    amount: str
    currency: str
    status: str


class ApprovalOutcome(TypedDict, total=False):
    draft_id: str
    status: str
    action: str
    email_message_id: str | None


class WorkflowServicesContext(TypedDict, total=False):
    gmail_reader: Any
    invoice_extraction_service: Any
    payment_matching_service: Any
    reminder_agent: Any
    telegram_approval_workflow: Any
    db_session_factory: Callable[[], Session]


class InvoiceIntelligenceState(TypedDict, total=False):
    """
    Shared LangGraph state for the Invoice Intelligence workflow.

    Reducers are used on collection fields so repeated invocations on the same
    thread can accumulate memory rather than replace it.
    """

    run_id: NotRequired[str]
    as_of_date: NotRequired[date]
    email_query: NotRequired[str]
    load_inbox: NotRequired[bool]
    load_sent_mail: NotRequired[bool]
    payment_ids: Annotated[list[str], operator.add]
    pending_draft_ids: Annotated[list[str], operator.add]
    telegram_callback_updates: Annotated[list[dict[str, Any]], operator.add]
    emails: Annotated[list[EmailEnvelope], operator.add]
    invoice_emails: Annotated[list[EmailEnvelope], operator.add]
    payment_emails: Annotated[list[EmailEnvelope], operator.add]
    other_emails: Annotated[list[EmailEnvelope], operator.add]
    extracted_invoices: Annotated[list[ExtractedInvoicePayload], operator.add]
    matched_payment_ids: Annotated[list[str], operator.add]
    unmatched_payment_ids: Annotated[list[str], operator.add]
    due_invoice_ids: Annotated[list[str], operator.add]
    overdue_invoice_ids: Annotated[list[str], operator.add]
    reminder_draft_ids: Annotated[list[str], operator.add]
    approval_results: Annotated[list[ApprovalOutcome], operator.add]
    event_log: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    route_history: Annotated[list[str], operator.add]


def stringify_uuid(value: UUID | str) -> str:
    return str(value)
