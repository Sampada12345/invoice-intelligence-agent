from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable
from uuid import UUID

from langgraph.runtime import Runtime

from .state import (
    ApprovalOutcome,
    EmailEnvelope,
    ExtractedInvoicePayload,
    InvoiceIntelligenceState,
    WorkflowServicesContext,
    stringify_uuid,
)


@dataclass(slots=True)
class _ClassifiedEmails:
    invoice_emails: list[EmailEnvelope]
    payment_emails: list[EmailEnvelope]
    other_emails: list[EmailEnvelope]


def email_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    context = runtime.context
    emails = list(state.get("emails", []))
    loaded_emails: list[EmailEnvelope] = []

    if not emails and context.get("gmail_reader") is not None:
        gmail_reader = context["gmail_reader"]
        query = state.get("email_query")

        if state.get("load_inbox", True):
            for message in gmail_reader.read_inbox(query=query):
                loaded_emails.append(_gmail_message_to_email_envelope(message))
        if state.get("load_sent_mail", False):
            for message in gmail_reader.read_sent_mail(query=query):
                loaded_emails.append(_gmail_message_to_email_envelope(message))

    source_emails = emails or loaded_emails
    classified = _classify_emails(source_emails)

    return {
        "emails": loaded_emails if loaded_emails else [],
        "invoice_emails": classified.invoice_emails,
        "payment_emails": classified.payment_emails,
        "other_emails": classified.other_emails,
        "event_log": [
            (
                "email_agent loaded and classified "
                f"{len(source_emails)} email(s): "
                f"{len(classified.invoice_emails)} invoice, "
                f"{len(classified.payment_emails)} payment, "
                f"{len(classified.other_emails)} other"
            )
        ],
        "route_history": ["email_agent"],
    }


def invoice_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    extraction_service = runtime.context.get("invoice_extraction_service")
    invoice_emails = state.get("invoice_emails", [])
    extracted: list[ExtractedInvoicePayload] = []
    errors: list[str] = []

    if extraction_service is None:
        return {
            "event_log": ["invoice_agent skipped because no extraction service is configured"],
            "route_history": ["invoice_agent"],
        }

    for email in invoice_emails:
        try:
            extracted.append(_extract_invoice_from_email(extraction_service, email))
        except Exception as exc:
            identifier = email.get("message_id") or email.get("subject") or "unknown-email"
            errors.append(f"invoice_agent failed for {identifier}: {exc}")

    return {
        "extracted_invoices": extracted,
        "errors": errors,
        "event_log": [f"invoice_agent extracted {len(extracted)} invoice payload(s)"],
        "route_history": ["invoice_agent"],
    }


def payment_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    payment_ids = state.get("payment_ids", [])
    matching_service = runtime.context.get("payment_matching_service")
    session_factory = runtime.context.get("db_session_factory")

    if not payment_ids or matching_service is None or session_factory is None:
        return {
            "event_log": ["payment_agent skipped because no payment work was available"],
            "route_history": ["payment_agent"],
        }

    matched_ids: list[str] = []
    unmatched_ids: list[str] = []
    errors: list[str] = []

    with session_factory() as session:
        for payment_id in payment_ids:
            try:
                result = matching_service.match_payment(session, UUID(payment_id))
                if result.matched:
                    matched_ids.append(str(result.payment_id))
                else:
                    unmatched_ids.append(str(result.payment_id))
            except Exception as exc:
                errors.append(f"payment_agent failed for payment {payment_id}: {exc}")
        session.commit()

    return {
        "matched_payment_ids": matched_ids,
        "unmatched_payment_ids": unmatched_ids,
        "errors": errors,
        "event_log": [
            f"payment_agent processed {len(payment_ids)} payment(s): "
            f"{len(matched_ids)} matched, {len(unmatched_ids)} unmatched"
        ],
        "route_history": ["payment_agent"],
    }


def due_date_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    reminder_agent = runtime.context.get("reminder_agent")
    session_factory = runtime.context.get("db_session_factory")

    if reminder_agent is None or session_factory is None:
        return {
            "event_log": ["due_date_agent skipped because reminder dependencies are unavailable"],
            "route_history": ["due_date_agent"],
        }

    as_of = state.get("as_of_date")
    with session_factory() as session:
        due_invoices = reminder_agent.detect_due_invoices(session, as_of=as_of)
        overdue_invoices = reminder_agent.detect_overdue_invoices(session, as_of=as_of, update_status=True)
        session.commit()

    return {
        "due_invoice_ids": [stringify_uuid(invoice.id) for invoice in due_invoices],
        "overdue_invoice_ids": [stringify_uuid(invoice.id) for invoice in overdue_invoices],
        "event_log": [
            f"due_date_agent detected {len(due_invoices)} due and {len(overdue_invoices)} overdue invoice(s)"
        ],
        "route_history": ["due_date_agent"],
    }


def reminder_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    reminder_agent = runtime.context.get("reminder_agent")
    session_factory = runtime.context.get("db_session_factory")

    target_invoice_ids = _unique_preserving_order([
        *state.get("due_invoice_ids", []),
        *state.get("overdue_invoice_ids", []),
    ])
    if reminder_agent is None or session_factory is None or not target_invoice_ids:
        return {
            "event_log": ["reminder_agent skipped because no reminder work was available"],
            "route_history": ["reminder_agent"],
        }

    created_draft_ids: list[str] = []
    errors: list[str] = []
    with session_factory() as session:
        for invoice_id in target_invoice_ids:
            try:
                record = reminder_agent.generate_reminder_for_invoice(
                    session,
                    UUID(invoice_id),
                    as_of=state.get("as_of_date"),
                    auto_commit=False,
                )
                created_draft_ids.append(stringify_uuid(record.draft_id))
            except Exception as exc:
                errors.append(f"reminder_agent failed for invoice {invoice_id}: {exc}")
        session.commit()

    return {
        "reminder_draft_ids": created_draft_ids,
        "pending_draft_ids": created_draft_ids,
        "errors": errors,
        "event_log": [f"reminder_agent generated {len(created_draft_ids)} draft reminder(s)"],
        "route_history": ["reminder_agent"],
    }


def approval_agent_node(
    state: InvoiceIntelligenceState,
    runtime: Runtime[WorkflowServicesContext],
) -> dict[str, Any]:
    workflow = runtime.context.get("telegram_approval_workflow")
    session_factory = runtime.context.get("db_session_factory")

    if workflow is None or session_factory is None:
        return {
            "event_log": ["approval_agent skipped because Telegram workflow dependencies are unavailable"],
            "route_history": ["approval_agent"],
        }

    pending_draft_ids = _unique_preserving_order(state.get("pending_draft_ids", []))
    callback_updates = state.get("telegram_callback_updates", [])

    approval_results: list[ApprovalOutcome] = []
    errors: list[str] = []
    notifications_sent = 0

    with session_factory() as session:
        if callback_updates:
            for update in callback_updates:
                try:
                    result = workflow.handle_callback_update(session, update, auto_commit=False)
                    approval_results.append(
                        {
                            "draft_id": stringify_uuid(result.draft_id),
                            "status": result.status.value,
                            "action": result.action,
                            "email_message_id": result.email_message_id,
                        }
                    )
                except Exception as exc:
                    errors.append(f"approval_agent callback handling failed: {exc}")
        else:
            for draft_id in pending_draft_ids:
                try:
                    workflow.notify_draft_created(session, UUID(draft_id), auto_commit=False)
                    notifications_sent += 1
                except Exception as exc:
                    errors.append(f"approval_agent notification failed for draft {draft_id}: {exc}")
        session.commit()

    if callback_updates:
        event = f"approval_agent processed {len(approval_results)} Telegram callback approval decision(s)"
    else:
        event = f"approval_agent sent {notifications_sent} Telegram approval notification(s)"

    return {
        "approval_results": approval_results,
        "errors": errors,
        "event_log": [event],
        "route_history": ["approval_agent"],
    }


def route_after_email(state: InvoiceIntelligenceState) -> str:
    if state.get("invoice_emails"):
        return "invoice_agent"
    if state.get("payment_ids") or state.get("payment_emails"):
        return "payment_agent"
    return "due_date_agent"


def route_after_invoice(state: InvoiceIntelligenceState) -> str:
    if state.get("payment_ids") or state.get("payment_emails"):
        return "payment_agent"
    return "due_date_agent"


def route_after_due_date(state: InvoiceIntelligenceState) -> str:
    if state.get("due_invoice_ids") or state.get("overdue_invoice_ids"):
        return "reminder_agent"
    if state.get("pending_draft_ids") or state.get("telegram_callback_updates"):
        return "approval_agent"
    return "__end__"


def route_after_reminder(state: InvoiceIntelligenceState) -> str:
    if state.get("pending_draft_ids") or state.get("telegram_callback_updates"):
        return "approval_agent"
    return "__end__"


def _classify_emails(emails: Iterable[EmailEnvelope]) -> _ClassifiedEmails:
    invoice_emails: list[EmailEnvelope] = []
    payment_emails: list[EmailEnvelope] = []
    other_emails: list[EmailEnvelope] = []

    for email in emails:
        detected_type = _detect_email_type(email)
        decorated_email = dict(email)
        decorated_email["detected_type"] = detected_type
        if detected_type == "invoice":
            invoice_emails.append(decorated_email)
        elif detected_type == "payment":
            payment_emails.append(decorated_email)
        else:
            other_emails.append(decorated_email)

    return _ClassifiedEmails(
        invoice_emails=invoice_emails,
        payment_emails=payment_emails,
        other_emails=other_emails,
    )


def _detect_email_type(email: EmailEnvelope) -> str:
    text_parts = [
        email.get("subject", ""),
        email.get("body_text", ""),
        email.get("body_html", ""),
    ]
    haystack = " ".join(text_parts).lower()
    has_pdf_attachment = any(
        path.lower().endswith(".pdf") for path in email.get("attachment_paths", [])
    )

    if ("invoice" in haystack or "billing" in haystack) and (has_pdf_attachment or "invoice" in haystack):
        return "invoice"
    if any(token in haystack for token in ("payment received", "payment confirmation", "paid", "receipt", "transaction")):
        return "payment"
    return "other"


def _gmail_message_to_email_envelope(message: Any) -> EmailEnvelope:
    attachment_paths = [
        getattr(attachment, "filename", "")
        for attachment in getattr(message, "attachments", [])
        if getattr(attachment, "filename", "")
    ]
    return {
        "message_id": getattr(message, "message_id", ""),
        "subject": getattr(message, "subject", "") or "",
        "sender": getattr(message, "sender", "") or "",
        "recipients": list(getattr(message, "recipients", []) or []),
        "body_text": getattr(message, "body_text", "") or "",
        "body_html": getattr(message, "body_html", "") or "",
        "attachment_paths": attachment_paths,
        "label_ids": list(getattr(message, "label_ids", []) or []),
    }


def _extract_invoice_from_email(extraction_service: Any, email: EmailEnvelope) -> ExtractedInvoicePayload:
    attachment_paths = email.get("attachment_paths", [])
    result = None

    for attachment_path in attachment_paths:
        if attachment_path.lower().endswith(".pdf"):
            result = extraction_service.extract_from_pdf(attachment_path, use_gpt_fallback=True)
            break

    if result is None:
        email_body = email.get("body_text") or email.get("body_html") or ""
        result = extraction_service.extract_from_email(email_body, use_gpt_fallback=True)

    return result.model_dump(mode="json")


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered
