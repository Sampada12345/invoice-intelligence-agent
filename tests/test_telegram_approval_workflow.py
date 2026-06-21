from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from invoice_agent.db.db import get_session_factory, init_db
from invoice_agent.db.models import (
    AuditLog,
    Client,
    Draft,
    DraftStatus,
    EmailLog,
    EmailType,
    Invoice,
    InvoiceStatus,
    User,
    UserRole,
)
from invoice_agent.services.notification import (
    TelegramApprovalCodec,
    TelegramApprovalWorkflow,
)


class FakeTelegramBotClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.answers: list[dict] = []

    def send_message(self, **payload):
        self.messages.append(payload)
        return {"ok": True, "result": {"message_id": 999, **payload}}

    def answer_callback_query(self, **payload):
        self.answers.append(payload)
        return {"ok": True, "result": True, **payload}


class FakeSendResult:
    def __init__(self, message_id: str = "gmail-message-1", thread_id: str | None = "thread-1") -> None:
        self.message_id = message_id
        self.thread_id = thread_id
        self.label_ids = ["SENT"]
        self.raw_response = {"id": message_id, "threadId": thread_id, "labelIds": ["SENT"]}


class FakeGmailSender:
    def __init__(self) -> None:
        self.sent_payloads: list[dict] = []

    def send_email(self, **payload):
        self.sent_payloads.append(payload)
        return FakeSendResult()


class TelegramApprovalWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_url = f"sqlite:///{Path(self._temp_dir.name) / 'telegram_workflow.db'}"
        init_db(self._db_url)
        self._session_factory = get_session_factory(self._db_url)
        self._telegram_client = FakeTelegramBotClient()
        self._gmail_sender = FakeGmailSender()
        self._codec = TelegramApprovalCodec("workflow-secret")
        self._workflow = TelegramApprovalWorkflow(
            telegram_client=self._telegram_client,
            gmail_sender=self._gmail_sender,
            approval_codec=self._codec,
            sender_email="billing@example.com",
        )

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_notify_draft_created_sends_telegram_message(self) -> None:
        with self._session_factory() as session:
            user, draft = self._create_user_client_invoice_and_draft(session)

            response = self._workflow.notify_draft_created(session, draft, auto_commit=False)
            session.flush()

            self.assertEqual(len(self._telegram_client.messages), 1)
            payload = self._telegram_client.messages[0]
            self.assertEqual(payload["chat_id"], user.telegram_chat_id)
            self.assertIn("Reminder draft created for approval", payload["text"])
            self.assertIn("inline_keyboard", payload["reply_markup"])
            self.assertEqual(response["result"]["message_id"], 999)

            audits = session.query(AuditLog).filter(AuditLog.entity_id == str(draft.id)).all()
            self.assertEqual([entry.action for entry in audits], ["telegram_notification_sent"])
            self.assertIsNotNone(draft.approval_requested_at)

    def test_approve_callback_sends_email_and_marks_draft_sent(self) -> None:
        with self._session_factory() as session:
            user, draft = self._create_user_client_invoice_and_draft(session)
            update = self._build_callback_update("approve", draft.id, telegram_user_id=user.telegram_chat_id or "12345")

            result = self._workflow.handle_callback_update(session, update, auto_commit=False)
            session.flush()

            self.assertEqual(result.status, DraftStatus.SENT)
            self.assertEqual(result.action, "approve")
            self.assertEqual(len(self._gmail_sender.sent_payloads), 1)
            self.assertEqual(self._gmail_sender.sent_payloads[0]["to"], draft.client.email)
            self.assertEqual(draft.status, DraftStatus.SENT)
            self.assertEqual(draft.external_message_id, "gmail-message-1")
            self.assertIsNotNone(draft.sent_at)

            email_logs = session.query(EmailLog).filter(EmailLog.draft_id == draft.id).all()
            self.assertEqual(len(email_logs), 1)
            self.assertEqual(email_logs[0].email_type, EmailType.REMINDER)
            self.assertEqual(email_logs[0].gmail_message_id, "gmail-message-1")

            audits = session.query(AuditLog).filter(AuditLog.entity_id == str(draft.id)).order_by(AuditLog.created_at.asc()).all()
            self.assertEqual(
                [entry.action for entry in audits],
                ["draft_approved", "draft_sent"],
            )
            self.assertEqual(len(self._telegram_client.answers), 1)

    def test_reject_callback_closes_workflow_without_sending_email(self) -> None:
        with self._session_factory() as session:
            user, draft = self._create_user_client_invoice_and_draft(session)
            update = self._build_callback_update("reject", draft.id, telegram_user_id=user.telegram_chat_id or "12345")

            result = self._workflow.handle_callback_update(session, update, auto_commit=False)
            session.flush()

            self.assertEqual(result.status, DraftStatus.REJECTED)
            self.assertEqual(result.action, "reject")
            self.assertEqual(len(self._gmail_sender.sent_payloads), 0)
            self.assertEqual(draft.status, DraftStatus.REJECTED)
            self.assertIn("Rejected via Telegram", draft.approval_notes or "")

            audits = session.query(AuditLog).filter(AuditLog.entity_id == str(draft.id)).all()
            self.assertEqual([entry.action for entry in audits], ["draft_rejected"])
            email_logs = session.query(EmailLog).filter(EmailLog.draft_id == draft.id).all()
            self.assertEqual(email_logs, [])

    def _create_user_client_invoice_and_draft(self, session) -> tuple[User, Draft]:
        user = User(
            email="approver@example.com",
            full_name="Approver User",
            role=UserRole.ADMIN,
            telegram_chat_id="12345",
        )
        client = Client(
            name="Acme Corp",
            email="billing@acme.example.com",
            payment_terms_days=30,
        )
        session.add_all([user, client])
        session.flush()

        invoice = Invoice(
            client_id=client.id,
            invoice_number="INV-TG-1",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 6, 25),
            currency="USD",
            subtotal_amount=Decimal("125.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("125.00"),
            amount_paid=Decimal("0.00"),
            balance_due=Decimal("125.00"),
            status=InvoiceStatus.OPEN,
        )
        session.add(invoice)
        session.flush()

        draft = Draft(
            client_id=client.id,
            invoice_id=invoice.id,
            created_by_user_id=user.id,
            subject="Reminder for invoice INV-TG-1",
            body_text="Please pay invoice INV-TG-1.",
            body_html="<p>Please pay invoice INV-TG-1.</p>",
            status=DraftStatus.PENDING_APPROVAL,
        )
        session.add(draft)
        session.flush()
        return user, draft

    def _build_callback_update(self, action: str, draft_id: UUID, *, telegram_user_id: str) -> dict:
        return {
            "callback_query": {
                "id": "callback-id-1",
                "data": self._codec.encode(action, draft_id),
                "from": {
                    "id": int(telegram_user_id),
                    "username": "approver_user",
                    "first_name": "Approver",
                },
            }
        }


if __name__ == "__main__":
    unittest.main()
