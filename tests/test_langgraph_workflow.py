from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from invoice_agent.db.db import get_session_factory, init_db
from invoice_agent.db.models import Client, Draft, DraftStatus, Invoice, InvoiceStatus, User, UserRole
from invoice_agent.workflows.langgraph.graph import compile_invoice_intelligence_graph


class FakeInvoiceExtractionService:
    def extract_from_pdf(self, pdf_path: str, *, use_gpt_fallback: bool = True):
        raise AssertionError("PDF extraction should not be used in this test.")

    def extract_from_email(self, email_body: str, *, use_gpt_fallback: bool = True):
        return _ModelDumpResult(
            {
                "invoice_number": "INV-LANG-1",
                "client_name": "Acme Corp",
                "client_email": "billing@acme.example.com",
                "invoice_date": "2026-06-01",
                "due_date": "2026-06-20",
                "amount": "125.00",
                "currency": "USD",
                "status": "open",
            }
        )


class FakePaymentMatchingService:
    def match_payment(self, session, payment_id):
        return _MatchResult(payment_id=str(payment_id), matched=False)


class FakeTelegramApprovalWorkflow:
    def __init__(self) -> None:
        self.notified_draft_ids: list[str] = []
        self.callback_actions: list[str] = []

    def notify_draft_created(self, session, draft_id, *, auto_commit: bool = False):
        self.notified_draft_ids.append(str(draft_id))
        return {"ok": True}

    def handle_callback_update(self, session, update, *, auto_commit: bool = False):
        self.callback_actions.append("approve")
        draft_id = UUID(update["draft_id"])
        draft = session.get(Draft, draft_id)
        draft.status = DraftStatus.SENT
        return _ApprovalResult(draft_id=str(draft_id), status="sent", action="approve", email_message_id="gmail-1")


class _ModelDumpResult:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self, *, mode: str = "json"):
        return dict(self._payload)


@dataclass
class _MatchResult:
    payment_id: str
    matched: bool


@dataclass
class _ApprovalResult:
    draft_id: str
    status: str
    action: str
    email_message_id: str | None = None


class LangGraphWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_url = f"sqlite:///{Path(self._temp_dir.name) / 'langgraph.db'}"
        init_db(self._db_url)
        self._session_factory = get_session_factory(self._db_url)
        self._seed_data()

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_routes_through_due_reminder_and_approval_agents(self) -> None:
        workflow = compile_invoice_intelligence_graph()
        telegram_workflow = FakeTelegramApprovalWorkflow()

        result = workflow.invoke(
            {
                "as_of_date": date(2026, 6, 15),
                "emails": [
                    {
                        "message_id": "msg-1",
                        "subject": "Invoice INV-LANG-1",
                        "sender": "vendor@example.com",
                        "recipients": ["billing@example.com"],
                        "body_text": (
                            "Invoice Number: INV-LANG-1\n"
                            "Client: Acme Corp\n"
                            "Client Email: billing@acme.example.com\n"
                            "Invoice Date: 2026-06-01\n"
                            "Due Date: 2026-06-20\n"
                            "Amount Due: USD 125.00\n"
                            "Status: open"
                        ),
                        "attachment_paths": [],
                    }
                ],
            },
            config={"configurable": {"thread_id": "workflow-thread-1"}},
            context={
                "db_session_factory": self._session_factory,
                "invoice_extraction_service": FakeInvoiceExtractionService(),
                "payment_matching_service": FakePaymentMatchingService(),
                "reminder_agent": __import__(
                    "invoice_agent.services.reminder_agent", fromlist=["ReminderAgent"]
                ).ReminderAgent(),
                "telegram_approval_workflow": telegram_workflow,
            },
        )

        self.assertIn("email_agent", result["route_history"])
        self.assertIn("invoice_agent", result["route_history"])
        self.assertIn("due_date_agent", result["route_history"])
        self.assertIn("reminder_agent", result["route_history"])
        self.assertIn("approval_agent", result["route_history"])
        self.assertEqual(len(result["extracted_invoices"]), 1)
        self.assertGreaterEqual(len(result["reminder_draft_ids"]), 1)
        self.assertEqual(len(telegram_workflow.notified_draft_ids), 1)

    def test_checkpoint_memory_accumulates_event_log_across_invocations(self) -> None:
        workflow = compile_invoice_intelligence_graph()
        config = {"configurable": {"thread_id": "memory-thread-1"}}

        context = {
            "db_session_factory": self._session_factory,
            "invoice_extraction_service": FakeInvoiceExtractionService(),
            "reminder_agent": __import__(
                "invoice_agent.services.reminder_agent", fromlist=["ReminderAgent"]
            ).ReminderAgent(),
            "telegram_approval_workflow": FakeTelegramApprovalWorkflow(),
        }

        workflow.invoke(
            {
                "as_of_date": date(2026, 6, 15),
                "emails": [],
            },
            config=config,
            context=context,
        )
        workflow.invoke(
            {
                "as_of_date": date(2026, 6, 15),
                "pending_draft_ids": [self._existing_draft_id],
            },
            config=config,
            context=context,
        )

        state = workflow.get_state(config).values
        self.assertGreaterEqual(len(state["event_log"]), 4)
        self.assertIn("approval_agent", state["route_history"])

    def _seed_data(self) -> None:
        with self._session_factory() as session:
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
                invoice_number="INV-LIVE-1",
                issue_date=date(2026, 6, 1),
                due_date=date(2026, 6, 20),
                currency="USD",
                subtotal_amount=Decimal("150.00"),
                tax_amount=Decimal("0.00"),
                total_amount=Decimal("150.00"),
                amount_paid=Decimal("0.00"),
                balance_due=Decimal("150.00"),
                status=InvoiceStatus.OPEN,
            )
            session.add(invoice)
            session.flush()

            draft = Draft(
                client_id=client.id,
                invoice_id=invoice.id,
                created_by_user_id=user.id,
                subject="Pending Reminder",
                body_text="Reminder body",
                body_html="<p>Reminder body</p>",
                status=DraftStatus.PENDING_APPROVAL,
            )
            session.add(draft)
            session.commit()
            self._existing_draft_id = str(draft.id)


if __name__ == "__main__":
    unittest.main()
