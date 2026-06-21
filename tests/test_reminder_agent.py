from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_agent.db.db import get_session_factory, init_db
from invoice_agent.db.models import (
    Client,
    Draft,
    DraftStatus,
    Invoice,
    InvoiceStatus,
)
from invoice_agent.services.reminder_agent import (
    OpenAIReminderContentGenerator,
    ReminderAgent,
    ReminderContent,
    ReminderGenerationContext,
    ReminderKind,
)


class StubReminderContentGenerator:
    def __init__(self) -> None:
        self.calls: list[ReminderGenerationContext] = []

    def generate(self, context: ReminderGenerationContext) -> ReminderContent:
        self.calls.append(context)
        prefix = "Overdue" if context.reminder_kind == ReminderKind.OVERDUE else "Upcoming"
        return ReminderContent(
            subject=f"{prefix} invoice reminder: {context.invoice_number}",
            body_text=f"Reminder for {context.client_name} about invoice {context.invoice_number}.",
            body_html=f"<p>Reminder for {context.client_name} about invoice {context.invoice_number}.</p>",
        )


class ReminderAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_url = f"sqlite:///{Path(self._temp_dir.name) / 'reminder_agent.db'}"
        init_db(self._db_url)
        self._session_factory = get_session_factory(self._db_url)
        self._generator = StubReminderContentGenerator()
        self._agent = ReminderAgent(content_generator=self._generator, due_window_days=7)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_detect_due_invoices(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, "Acme Corp")
            due_invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-DUE-1",
                due_date=date(2026, 6, 25),
                status=InvoiceStatus.OPEN,
            )
            self._create_invoice(
                session,
                client=client,
                invoice_number="INV-LATE-1",
                due_date=date(2026, 7, 10),
                status=InvoiceStatus.OPEN,
            )

            due_invoices = self._agent.detect_due_invoices(
                session,
                as_of=date(2026, 6, 20),
                within_days=7,
            )

            self.assertEqual([invoice.id for invoice in due_invoices], [due_invoice.id])

    def test_detect_overdue_invoices_marks_status(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, "Globex Ltd")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-OD-1",
                due_date=date(2026, 6, 10),
                status=InvoiceStatus.OPEN,
            )

            overdue = self._agent.detect_overdue_invoices(
                session,
                as_of=date(2026, 6, 20),
                update_status=True,
            )
            session.flush()

            self.assertEqual([item.id for item in overdue], [invoice.id])
            self.assertEqual(invoice.status, InvoiceStatus.OVERDUE)

    def test_generate_reminder_stores_draft_and_history(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, "Initech")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-REM-1",
                due_date=date(2026, 6, 25),
                status=InvoiceStatus.OPEN,
                balance_due=Decimal("250.00"),
            )

            record = self._agent.generate_reminder_for_invoice(
                session,
                invoice,
                as_of=date(2026, 6, 20),
            )
            session.flush()

            draft = session.get(Draft, record.draft_id)
            self.assertIsNotNone(draft)
            assert draft is not None
            self.assertEqual(draft.status, DraftStatus.PENDING_APPROVAL)
            self.assertEqual(record.reminder_kind, ReminderKind.DUE_SOON)
            self.assertEqual(record.subject, "Upcoming invoice reminder: INV-REM-1")

            history = self._agent.get_reminder_history(session, invoice)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].action, "draft_created")
            self.assertEqual(history[0].details["draft_id"], str(draft.id))

    def test_generate_reminder_reuses_existing_pending_draft(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, "Umbrella Corp")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-REM-2",
                due_date=date(2026, 6, 25),
                status=InvoiceStatus.OPEN,
            )

            first_record = self._agent.generate_reminder_for_invoice(
                session,
                invoice,
                as_of=date(2026, 6, 20),
            )
            second_record = self._agent.generate_reminder_for_invoice(
                session,
                invoice,
                as_of=date(2026, 6, 20),
            )
            session.flush()

            self.assertEqual(first_record.draft_id, second_record.draft_id)
            self.assertEqual(len(self._generator.calls), 1)
            history = self._agent.get_reminder_history(session, invoice)
            self.assertEqual([entry.action for entry in history], ["draft_created", "draft_reused"])

    @staticmethod
    def _create_client(session, name: str) -> Client:
        client = Client(
            name=name,
            email=f"{name.lower().replace(' ', '')}@example.com",
            payment_terms_days=30,
        )
        session.add(client)
        session.flush()
        return client

    @staticmethod
    def _create_invoice(
        session,
        *,
        client: Client,
        invoice_number: str,
        due_date: date,
        status: InvoiceStatus,
        balance_due: Decimal = Decimal("100.00"),
    ) -> Invoice:
        invoice = Invoice(
            client_id=client.id,
            invoice_number=invoice_number,
            issue_date=date(2026, 6, 1),
            due_date=due_date,
            currency="USD",
            subtotal_amount=balance_due,
            tax_amount=Decimal("0.00"),
            total_amount=balance_due,
            amount_paid=Decimal("0.00"),
            balance_due=balance_due,
            status=status,
        )
        session.add(invoice)
        session.flush()
        return invoice


class ReminderGeneratorFallbackTests(unittest.TestCase):
    def test_template_fallback_without_openai_key(self) -> None:
        generator = OpenAIReminderContentGenerator(api_key=None, fallback_to_template=True)
        content = generator.generate(
            ReminderGenerationContext(
                reminder_kind=ReminderKind.OVERDUE,
                client_name="Soylent Corp",
                invoice_number="INV-OPENAI-1",
                due_date=date(2026, 6, 10),
                amount_due=Decimal("125.50"),
                currency="USD",
                days_delta=-5,
                invoice_status="overdue",
            )
        )

        self.assertIn("Overdue invoice reminder", content.subject)
        self.assertIn("Soylent Corp", content.body_text)
        self.assertIn("INV-OPENAI-1", content.body_text)


if __name__ == "__main__":
    unittest.main()
