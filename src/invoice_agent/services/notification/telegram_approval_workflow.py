from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from invoice_agent.db.models import (
    AuditLog,
    AuditStatus,
    Client,
    Draft,
    DraftStatus,
    EmailDirection,
    EmailLog,
    EmailProcessingStatus,
    EmailType,
    Invoice,
    User,
)
from invoice_agent.integrations.gmail.gmail_sender import GmailSender, SendResult
from invoice_agent.integrations.telegram.telegram_client import TelegramBotClient


class TelegramApprovalError(RuntimeError):
    """Raised when the Telegram approval workflow cannot proceed."""


class InvalidTelegramApprovalCallback(TelegramApprovalError):
    """Raised when Telegram callback data is malformed or fails validation."""


@dataclass(frozen=True, slots=True)
class TelegramApprovalResult:
    draft_id: UUID
    status: DraftStatus
    action: str
    email_message_id: str | None = None
    telegram_response: dict[str, Any] | None = None


class TelegramApprovalCodec:
    """
    Encodes signed Telegram callback payloads that fit within Telegram's
    callback_data size limit.
    """

    def __init__(self, secret: str) -> None:
        if not secret:
            raise TelegramApprovalError("Telegram approval secret must not be empty.")
        self._secret = secret.encode("utf-8")

    @classmethod
    def from_env(cls) -> "TelegramApprovalCodec":
        secret = (
            os.getenv("TELEGRAM_APPROVAL_SECRET")
            or os.getenv("TELEGRAM_BOT_TOKEN")
            or ""
        ).strip()
        if not secret:
            raise TelegramApprovalError(
                "TELEGRAM_APPROVAL_SECRET or TELEGRAM_BOT_TOKEN must be configured."
            )
        return cls(secret)

    def encode(self, action: str, draft_id: UUID) -> str:
        action_code = self._action_to_code(action)
        draft_hex = draft_id.hex
        signature = self._sign(action_code, draft_hex)
        return f"{action_code}:{draft_hex}:{signature}"

    def decode(self, callback_data: str) -> tuple[str, UUID]:
        try:
            action_code, draft_hex, signature = callback_data.split(":")
        except ValueError as exc:
            raise InvalidTelegramApprovalCallback("Callback data is malformed.") from exc

        expected_signature = self._sign(action_code, draft_hex)
        if not hmac.compare_digest(signature, expected_signature):
            raise InvalidTelegramApprovalCallback("Callback signature is invalid.")

        try:
            draft_id = UUID(hex=draft_hex)
        except ValueError as exc:
            raise InvalidTelegramApprovalCallback("Draft identifier is invalid.") from exc

        return self._code_to_action(action_code), draft_id

    def _sign(self, action_code: str, draft_hex: str) -> str:
        payload = f"{action_code}:{draft_hex}".encode("utf-8")
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()[:12]

    @staticmethod
    def _action_to_code(action: str) -> str:
        mapping = {"approve": "A", "reject": "R"}
        try:
            return mapping[action]
        except KeyError as exc:
            raise TelegramApprovalError(f"Unsupported Telegram approval action: {action}") from exc

    @staticmethod
    def _code_to_action(code: str) -> str:
        mapping = {"A": "approve", "R": "reject"}
        try:
            return mapping[code]
        except KeyError as exc:
            raise InvalidTelegramApprovalCallback(f"Unsupported callback action code: {code}") from exc


class TelegramApprovalWorkflow:
    """
    Draft Created
      -> Telegram Notification
      -> Approve Button
      -> Reject Button

    If approved:
      send email via GmailSender.

    If rejected:
      close the workflow by marking the draft rejected.
    """

    def __init__(
        self,
        *,
        telegram_client: TelegramBotClient,
        gmail_sender: GmailSender,
        approval_codec: TelegramApprovalCodec | None = None,
        sender_email: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._telegram_client = telegram_client
        self._gmail_sender = gmail_sender
        self._approval_codec = approval_codec or TelegramApprovalCodec.from_env()
        self._sender_email = sender_email or os.getenv("GMAIL_FROM_EMAIL")
        self._logger = logger or logging.getLogger(__name__)

    def notify_draft_created(
        self,
        session: Session,
        draft_or_id: Draft | UUID,
        *,
        chat_id: str | int | None = None,
        actor_user_id: UUID | None = None,
        auto_commit: bool = False,
    ) -> dict[str, Any]:
        draft = self._resolve_draft(session, draft_or_id)
        target_chat_id = str(chat_id) if chat_id is not None else self._resolve_chat_id(session, draft)
        if not target_chat_id:
            raise TelegramApprovalError("No Telegram chat id is available for the approval notification.")

        draft.approval_requested_at = self._utcnow()
        message_text = self._build_notification_text(draft)
        response = self._telegram_client.send_message(
            chat_id=target_chat_id,
            text=message_text,
            reply_markup=self._build_reply_markup(draft.id),
        )

        self._record_audit(
            session,
            draft=draft,
            action="telegram_notification_sent",
            actor_user_id=actor_user_id,
            details={
                "chat_id": target_chat_id,
                "telegram_message_id": str(response.get("result", {}).get("message_id", "")),
            },
        )
        if auto_commit:
            session.commit()
        return response

    def handle_callback_update(
        self,
        session: Session,
        update_payload: dict[str, Any],
        *,
        auto_commit: bool = False,
    ) -> TelegramApprovalResult:
        callback_query = update_payload.get("callback_query")
        if not callback_query:
            raise InvalidTelegramApprovalCallback("Telegram update does not contain callback_query.")

        callback_query_id = str(callback_query.get("id", ""))
        callback_data = str(callback_query.get("data", ""))
        action, draft_id = self._approval_codec.decode(callback_data)

        user_payload = callback_query.get("from", {}) or {}
        telegram_user_id = str(user_payload.get("id", ""))
        telegram_username = user_payload.get("username") or user_payload.get("first_name") or "telegram-user"
        actor_user = self._find_user_by_telegram_id(session, telegram_user_id)

        if action == "approve":
            result = self._approve_draft(
                session,
                draft_id,
                approver_user=actor_user,
                approver_identity=telegram_username,
            )
            answer_text = "Draft approved and email sent."
        else:
            result = self._reject_draft(
                session,
                draft_id,
                approver_user=actor_user,
                approver_identity=telegram_username,
            )
            answer_text = "Draft rejected."

        telegram_response = self._telegram_client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=answer_text,
            show_alert=False,
        )

        finalized = TelegramApprovalResult(
            draft_id=result.draft_id,
            status=result.status,
            action=result.action,
            email_message_id=result.email_message_id,
            telegram_response=telegram_response,
        )
        if auto_commit:
            session.commit()
        return finalized

    def _approve_draft(
        self,
        session: Session,
        draft_id: UUID,
        *,
        approver_user: User | None,
        approver_identity: str,
    ) -> TelegramApprovalResult:
        draft = self._resolve_draft(session, draft_id)
        if draft.status == DraftStatus.SENT:
            return TelegramApprovalResult(draft_id=draft.id, status=draft.status, action="approve")
        if draft.status == DraftStatus.REJECTED:
            raise TelegramApprovalError("Cannot approve a draft that has already been rejected.")

        recipient_email = draft.client.email if draft.client else None
        if not recipient_email:
            raise TelegramApprovalError("Cannot send approved draft because the client email is missing.")

        draft.status = DraftStatus.APPROVED
        draft.approved_by_user_id = approver_user.id if approver_user else None
        draft.approved_at = self._utcnow()
        draft.approval_notes = f"Approved via Telegram by {approver_identity}"

        self._record_audit(
            session,
            draft=draft,
            action="draft_approved",
            actor_user_id=approver_user.id if approver_user else None,
            details={"channel": "telegram", "approver_identity": approver_identity},
        )

        try:
            send_result = self._send_approved_draft(draft)
        except Exception as exc:
            draft.status = DraftStatus.FAILED
            draft.approval_notes = f"Approved via Telegram by {approver_identity}; send failed: {exc}"
            self._record_audit(
                session,
                draft=draft,
                action="draft_send_failed",
                actor_user_id=approver_user.id if approver_user else None,
                details={"channel": "gmail", "error": str(exc)},
            )
            raise TelegramApprovalError(f"Approved draft could not be sent: {exc}") from exc

        draft.status = DraftStatus.SENT
        draft.sent_at = self._utcnow()
        draft.external_message_id = send_result.message_id

        self._persist_email_log(session, draft, recipient_email, send_result.message_id)
        self._record_audit(
            session,
            draft=draft,
            action="draft_sent",
            actor_user_id=approver_user.id if approver_user else None,
            details={
                "channel": "gmail",
                "message_id": send_result.message_id,
                "thread_id": send_result.thread_id or "",
            },
        )

        return TelegramApprovalResult(
            draft_id=draft.id,
            status=draft.status,
            action="approve",
            email_message_id=send_result.message_id,
        )

    def _reject_draft(
        self,
        session: Session,
        draft_id: UUID,
        *,
        approver_user: User | None,
        approver_identity: str,
    ) -> TelegramApprovalResult:
        draft = self._resolve_draft(session, draft_id)
        if draft.status == DraftStatus.SENT:
            raise TelegramApprovalError("Cannot reject a draft that has already been sent.")

        draft.status = DraftStatus.REJECTED
        draft.approved_by_user_id = approver_user.id if approver_user else None
        draft.approval_notes = f"Rejected via Telegram by {approver_identity}"

        self._record_audit(
            session,
            draft=draft,
            action="draft_rejected",
            actor_user_id=approver_user.id if approver_user else None,
            details={"channel": "telegram", "approver_identity": approver_identity},
        )

        return TelegramApprovalResult(
            draft_id=draft.id,
            status=draft.status,
            action="reject",
            email_message_id=None,
        )

    def _send_approved_draft(self, draft: Draft) -> SendResult:
        return self._gmail_sender.send_email(
            to=draft.client.email or "",
            subject=draft.subject,
            body_text=draft.body_text,
            body_html=draft.body_html,
            sender=self._sender_email,
        )

    def _persist_email_log(self, session: Session, draft: Draft, recipient_email: str, message_id: str) -> None:
        email_log = EmailLog(
            client_id=draft.client_id,
            invoice_id=draft.invoice_id,
            draft_id=draft.id,
            gmail_message_id=message_id,
            sender=self._sender_email or "system@local",
            recipients=[recipient_email],
            cc_recipients=[],
            bcc_recipients=[],
            subject=draft.subject,
            direction=EmailDirection.OUTBOUND,
            email_type=EmailType.REMINDER,
            processing_status=EmailProcessingStatus.PROCESSED,
            received_at=self._utcnow(),
            processed_at=self._utcnow(),
            body_text=draft.body_text,
            body_html=draft.body_html,
            attachment_count=0,
            attachment_paths=[],
            attachment_metadata=[],
            raw_payload={"draft_id": str(draft.id), "external_message_id": message_id},
        )
        session.add(email_log)

    def _record_audit(
        self,
        session: Session,
        *,
        draft: Draft,
        action: str,
        actor_user_id: UUID | None,
        details: dict[str, str],
    ) -> None:
        audit_log = AuditLog(
            actor_user_id=actor_user_id,
            entity_type="draft_approval",
            entity_id=str(draft.id),
            action=action,
            status=AuditStatus.SUCCESS,
            source="telegram_approval_workflow",
            details=details,
        )
        session.add(audit_log)

    def _resolve_draft(self, session: Session, draft_or_id: Draft | UUID) -> Draft:
        if isinstance(draft_or_id, Draft):
            return draft_or_id
        draft = session.get(Draft, draft_or_id)
        if draft is None:
            raise TelegramApprovalError(f"Draft not found: {draft_or_id}")
        return draft

    def _resolve_chat_id(self, session: Session, draft: Draft) -> str | None:
        invoice_creator = draft.created_by
        if invoice_creator and invoice_creator.telegram_chat_id:
            return invoice_creator.telegram_chat_id

        creator = draft.created_by_user_id and session.get(User, draft.created_by_user_id)
        if creator and creator.telegram_chat_id:
            return creator.telegram_chat_id

        stmt_user = session.query(User).filter(User.telegram_chat_id.is_not(None)).order_by(User.created_at.asc())
        fallback_user = stmt_user.first()
        if fallback_user and fallback_user.telegram_chat_id:
            return fallback_user.telegram_chat_id
        return None

    def _find_user_by_telegram_id(self, session: Session, telegram_user_id: str) -> User | None:
        if not telegram_user_id:
            return None
        return (
            session.query(User)
            .filter(User.telegram_chat_id == telegram_user_id)
            .order_by(User.created_at.asc())
            .first()
        )

    def _build_reply_markup(self, draft_id: UUID) -> dict[str, Any]:
        approve_data = self._approval_codec.encode("approve", draft_id)
        reject_data = self._approval_codec.encode("reject", draft_id)
        return {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": approve_data},
                    {"text": "Reject", "callback_data": reject_data},
                ]
            ]
        }

    def _build_notification_text(self, draft: Draft) -> str:
        invoice = draft.invoice
        client = draft.client
        if invoice is None or client is None:
            raise TelegramApprovalError("Draft must be associated with an invoice and client.")

        days_due = (invoice.due_date - datetime.now(tz=timezone.utc).date()).days
        due_label = (
            f"{abs(days_due)} day(s) overdue" if days_due < 0 else f"due in {days_due} day(s)"
        )
        amount_due = Decimal(invoice.balance_due).quantize(Decimal("0.01"))

        return (
            "Reminder draft created for approval.\n\n"
            f"Client: {client.name}\n"
            f"Invoice: {invoice.invoice_number}\n"
            f"Amount due: {invoice.currency} {amount_due:.2f}\n"
            f"Due date: {invoice.due_date.isoformat()} ({due_label})\n"
            f"Subject: {draft.subject}\n\n"
            "Choose Approve to send the email now or Reject to close the workflow."
        )

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(tz=timezone.utc)
