from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_agent.db.db import get_session_factory, init_db
from invoice_agent.db.models import Client, Invoice, InvoiceStatus, Payment, PaymentStatus
from invoice_agent.services.payment_matching import (
    PaymentMatchStrategy,
    PaymentMatchingService,
)


class PaymentMatchingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_url = f"sqlite:///{Path(self._temp_dir.name) / 'payment_matching.db'}"
        init_db(self._db_url)
        self._session_factory = get_session_factory(self._db_url)
        self._service = PaymentMatchingService()

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_matches_by_invoice_number_and_marks_paid(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, name="Acme Corp")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-1001",
                total_amount=Decimal("150.00"),
            )
            payment = self._create_payment(
                session,
                client=client,
                amount=Decimal("150.00"),
                payment_reference="Payment for INV-1001",
            )

            result = self._service.match_payment(session, payment)
            session.flush()

            self.assertTrue(result.matched)
            self.assertEqual(result.strategy, PaymentMatchStrategy.INVOICE_NUMBER)
            self.assertEqual(payment.invoice_id, invoice.id)
            self.assertEqual(payment.status, PaymentStatus.MATCHED)
            self.assertEqual(invoice.amount_paid, Decimal("150.00"))
            self.assertEqual(invoice.balance_due, Decimal("0.00"))
            self.assertEqual(invoice.status, InvoiceStatus.PAID)

    def test_matches_by_amount_within_same_client(self) -> None:
        with self._session_factory() as session:
            client_a = self._create_client(session, name="Acme Corp")
            client_b = self._create_client(session, name="Globex Ltd")
            self._create_invoice(
                session,
                client=client_a,
                invoice_number="INV-A",
                total_amount=Decimal("200.00"),
            )
            invoice_b = self._create_invoice(
                session,
                client=client_b,
                invoice_number="INV-B",
                total_amount=Decimal("200.00"),
            )
            payment = self._create_payment(
                session,
                client=client_b,
                amount=Decimal("200.00"),
            )

            result = self._service.match_payment(session, payment)
            session.flush()

            self.assertTrue(result.matched)
            self.assertEqual(result.strategy, PaymentMatchStrategy.AMOUNT_AND_CLIENT)
            self.assertEqual(payment.invoice_id, invoice_b.id)
            self.assertEqual(invoice_b.status, InvoiceStatus.PAID)
            self.assertEqual(payment.status, PaymentStatus.MATCHED)

    def test_matches_single_open_invoice_by_client(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, name="Initech")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-CLIENT-1",
                total_amount=Decimal("500.00"),
            )
            payment = self._create_payment(
                session,
                client=client,
                amount=Decimal("200.00"),
            )

            result = self._service.match_payment(session, payment)
            session.flush()

            self.assertTrue(result.matched)
            self.assertEqual(result.strategy, PaymentMatchStrategy.CLIENT_ONLY)
            self.assertEqual(payment.invoice_id, invoice.id)
            self.assertEqual(payment.status, PaymentStatus.PARTIALLY_MATCHED)
            self.assertEqual(invoice.amount_paid, Decimal("200.00"))
            self.assertEqual(invoice.balance_due, Decimal("300.00"))
            self.assertEqual(invoice.status, InvoiceStatus.PARTIALLY_PAID)

    def test_apply_payment_to_invoice_marks_paid(self) -> None:
        with self._session_factory() as session:
            client = self._create_client(session, name="Umbrella Corp")
            invoice = self._create_invoice(
                session,
                client=client,
                invoice_number="INV-PAID-1",
                total_amount=Decimal("99.99"),
            )
            payment = self._create_payment(
                session,
                client=client,
                amount=Decimal("99.99"),
            )

            result = self._service.apply_payment_to_invoice(payment, invoice)
            session.flush()

            self.assertTrue(result.matched)
            self.assertEqual(payment.status, PaymentStatus.MATCHED)
            self.assertEqual(invoice.status, InvoiceStatus.PAID)
            self.assertEqual(invoice.balance_due, Decimal("0.00"))
            self.assertEqual(invoice.amount_paid, Decimal("99.99"))

    @staticmethod
    def _create_client(session, *, name: str) -> Client:
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
        total_amount: Decimal,
    ) -> Invoice:
        invoice = Invoice(
            client_id=client.id,
            invoice_number=invoice_number,
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 6, 15),
            currency="USD",
            subtotal_amount=total_amount,
            tax_amount=Decimal("0.00"),
            total_amount=total_amount,
            amount_paid=Decimal("0.00"),
            balance_due=total_amount,
            status=InvoiceStatus.OPEN,
        )
        session.add(invoice)
        session.flush()
        return invoice

    @staticmethod
    def _create_payment(
        session,
        *,
        client: Client,
        amount: Decimal,
        payment_reference: str | None = None,
    ) -> Payment:
        payment = Payment(
            client_id=client.id,
            payment_date=date(2026, 6, 10),
            currency="USD",
            amount=amount,
            payment_reference=payment_reference,
            status=PaymentStatus.RECEIVED,
        )
        session.add(payment)
        session.flush()
        return payment


if __name__ == "__main__":
    unittest.main()
