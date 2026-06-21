from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import fitz

from invoice_agent.services.invoice_extraction import (
    ExtractedInvoiceStatus,
    GPTInvoiceExtractor,
    InvoiceExtractionResult,
    InvoiceExtractionService,
    PDFTextExtractor,
)


class StubPDFTextExtractor:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, pdf_path: str | Path) -> str:
        return self._text


class StubOCRExtractor:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, pdf_path: str | Path) -> str:
        return self._text


@dataclass
class StubGPTExtractor:
    result: InvoiceExtractionResult
    configured: bool = True
    called: bool = False

    def is_configured(self) -> bool:
        return self.configured

    def extract(self, document_text: str) -> InvoiceExtractionResult:
        self.called = True
        return self.result


class InvoiceExtractionSchemaTests(unittest.TestCase):
    def test_output_json_schema_contains_required_fields(self) -> None:
        schema = InvoiceExtractionResult.output_json_schema()
        properties = schema["properties"]

        self.assertEqual(
            set(properties.keys()),
            {
                "invoice_number",
                "client_name",
                "client_email",
                "invoice_date",
                "due_date",
                "amount",
                "currency",
                "status",
            },
        )


class PDFTextExtractorTests(unittest.TestCase):
    def test_extract_text_from_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "invoice.pdf"
            self._create_pdf(
                pdf_path,
                (
                    "Invoice Number: INV-1001\n"
                    "Client: Acme Corp\n"
                    "Client Email: billing@acme.example.com\n"
                    "Invoice Date: 2026-06-01\n"
                    "Due Date: 2026-06-15\n"
                    "Amount Due: USD 1234.56\n"
                    "Status: open"
                ),
            )

            extractor = PDFTextExtractor()
            extracted = extractor.extract_text(pdf_path)

            self.assertIn("INV-1001", extracted)
            self.assertIn("Acme Corp", extracted)
            self.assertIn("1234.56", extracted)

    @staticmethod
    def _create_pdf(path: Path, text: str) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=12)
        document.save(path)
        document.close()


class InvoiceExtractionServiceTests(unittest.TestCase):
    def test_extract_from_email_body_deterministically(self) -> None:
        service = InvoiceExtractionService()

        result = service.extract_from_email(
            (
                "Invoice Number: INV-2002\n"
                "Client: Globex Ltd\n"
                "Client Email: ap@globex.example.com\n"
                "Invoice Date: 2026-07-10\n"
                "Due Date: 2026-07-20\n"
                "Amount Due: EUR 450.00\n"
                "Status: open"
            ),
            use_gpt_fallback=False,
        )

        self.assertEqual(result.invoice_number, "INV-2002")
        self.assertEqual(result.client_name, "Globex Ltd")
        self.assertEqual(str(result.client_email), "ap@globex.example.com")
        self.assertEqual(result.amount, Decimal("450.00"))
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.status, ExtractedInvoiceStatus.OPEN)

    def test_extract_from_pdf_uses_real_text_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "invoice.pdf"
            PDFTextExtractorTests._create_pdf(
                pdf_path,
                (
                    "Invoice Number: INV-3003\n"
                    "Client: Initech\n"
                    "Client Email: finance@initech.example.com\n"
                    "Invoice Date: 2026-08-01\n"
                    "Due Date: 2026-08-08\n"
                    "Amount Due: GBP 999.99\n"
                    "Status: overdue"
                ),
            )

            service = InvoiceExtractionService()
            result = service.extract_from_pdf(pdf_path, use_gpt_fallback=False)

            self.assertEqual(result.invoice_number, "INV-3003")
            self.assertEqual(result.client_name, "Initech")
            self.assertEqual(result.amount, Decimal("999.99"))
            self.assertEqual(result.currency, "GBP")
            self.assertEqual(result.status, ExtractedInvoiceStatus.OVERDUE)

    def test_ocr_fallback_is_used_for_low_text_pdfs(self) -> None:
        service = InvoiceExtractionService(
            pdf_text_extractor=StubPDFTextExtractor(""),
            ocr_extractor=StubOCRExtractor(
                (
                    "Invoice Number: INV-4004\n"
                    "Client: Umbrella Corp\n"
                    "Client Email: invoices@umbrella.example.com\n"
                    "Invoice Date: 2026-09-01\n"
                    "Due Date: 2026-09-15\n"
                    "Amount Due: USD 800.00\n"
                    "Status: paid"
                )
            ),
            gpt_extractor=StubGPTExtractor(
                result=InvoiceExtractionResult(
                    invoice_number="UNUSED",
                    client_name="Unused",
                    client_email=None,
                    invoice_date=None,
                    due_date=None,
                    amount=Decimal("0.00"),
                    currency="USD",
                    status=ExtractedInvoiceStatus.UNKNOWN,
                ),
                configured=False,
            ),
        )

        result = service.extract_from_pdf("ignored.pdf", use_gpt_fallback=False)

        self.assertEqual(result.invoice_number, "INV-4004")
        self.assertEqual(result.client_name, "Umbrella Corp")
        self.assertEqual(result.amount, Decimal("800.00"))
        self.assertEqual(result.status, ExtractedInvoiceStatus.PAID)

    def test_gpt_fallback_is_used_when_rule_based_parsing_is_incomplete(self) -> None:
        gpt_result = InvoiceExtractionResult(
            invoice_number="INV-5005",
            client_name="Soylent Corp",
            client_email="billing@soylent.example.com",
            invoice_date=None,
            due_date=None,
            amount=Decimal("700.25"),
            currency="USD",
            status=ExtractedInvoiceStatus.OPEN,
        )
        gpt_extractor = StubGPTExtractor(result=gpt_result)
        service = InvoiceExtractionService(
            pdf_text_extractor=StubPDFTextExtractor("garbled content"),
            ocr_extractor=StubOCRExtractor(""),
            gpt_extractor=gpt_extractor,
        )

        result = service.extract(
            email_body="please see attached document",
            use_ocr=False,
            use_gpt_fallback=True,
        )

        self.assertTrue(gpt_extractor.called)
        self.assertEqual(result.invoice_number, "INV-5005")
        self.assertEqual(result.client_name, "Soylent Corp")


class GPTExtractorConfigurationTests(unittest.TestCase):
    def test_gpt_extractor_configuration_flag(self) -> None:
        extractor = GPTInvoiceExtractor(api_key=None)
        self.assertFalse(extractor.is_configured())


if __name__ == "__main__":
    unittest.main()
