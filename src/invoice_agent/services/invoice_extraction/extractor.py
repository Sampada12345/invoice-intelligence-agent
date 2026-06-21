from __future__ import annotations

import logging
from pathlib import Path

from .email_body_parser import EmailBodyInvoiceParser
from .gpt_fallback import GPTExtractionError, GPTInvoiceExtractor
from .ocr import OCRUnavailableError, PDFOCRExtractor
from .pdf_parser import PDFTextExtractor
from .schema import ExtractedInvoiceStatus, InvoiceExtractionResult


class InvoiceExtractionError(RuntimeError):
    """Raised when invoice extraction cannot produce the required schema."""


class InvoiceExtractionService:
    """
    Orchestrates invoice extraction from PDFs and email content.

    Extraction order:
    1. PDF text extraction
    2. OCR fallback for low-text PDFs
    3. email body parsing
    4. rule-based field extraction
    5. GPT fallback if required fields remain missing
    """

    def __init__(
        self,
        *,
        pdf_text_extractor: PDFTextExtractor | None = None,
        ocr_extractor: PDFOCRExtractor | None = None,
        email_body_parser: EmailBodyInvoiceParser | None = None,
        gpt_extractor: GPTInvoiceExtractor | None = None,
        minimum_text_length_for_pdf: int = 40,
        logger: logging.Logger | None = None,
    ) -> None:
        self._pdf_text_extractor = pdf_text_extractor or PDFTextExtractor()
        self._ocr_extractor = ocr_extractor or PDFOCRExtractor()
        self._email_body_parser = email_body_parser or EmailBodyInvoiceParser()
        self._gpt_extractor = gpt_extractor or GPTInvoiceExtractor()
        self._minimum_text_length_for_pdf = minimum_text_length_for_pdf
        self._logger = logger or logging.getLogger(__name__)

    def extract(
        self,
        *,
        pdf_path: str | Path | None = None,
        email_body: str | None = None,
        use_ocr: bool = True,
        use_gpt_fallback: bool = True,
    ) -> InvoiceExtractionResult:
        combined_fragments: list[str] = []
        parsed_fields: dict[str, object] = {}

        if pdf_path:
            pdf_text = self._extract_pdf_text_with_fallback(pdf_path, use_ocr=use_ocr)
            if pdf_text:
                combined_fragments.append(pdf_text)
                parsed_fields.update(self._email_body_parser.parse(pdf_text))

        if email_body:
            combined_fragments.append(email_body)
            parsed_fields = self._merge_fields(parsed_fields, self._email_body_parser.parse(email_body))

        deterministic_result = self._build_result_if_complete(parsed_fields)
        if deterministic_result:
            return deterministic_result

        if use_gpt_fallback and self._gpt_extractor.is_configured():
            combined_text = "\n\n".join(fragment.strip() for fragment in combined_fragments if fragment.strip())
            if combined_text:
                try:
                    return self._gpt_extractor.extract(combined_text)
                except GPTExtractionError as exc:
                    self._logger.warning("GPT fallback extraction failed: %s", exc)

        missing_fields = self._missing_required_fields(parsed_fields)
        raise InvoiceExtractionError(
            "Unable to extract a complete invoice payload. "
            f"Missing required fields: {', '.join(missing_fields)}"
        )

    def extract_from_pdf(
        self,
        pdf_path: str | Path,
        *,
        use_ocr: bool = True,
        use_gpt_fallback: bool = True,
    ) -> InvoiceExtractionResult:
        return self.extract(
            pdf_path=pdf_path,
            use_ocr=use_ocr,
            use_gpt_fallback=use_gpt_fallback,
        )

    def extract_from_email(
        self,
        email_body: str,
        *,
        use_gpt_fallback: bool = True,
    ) -> InvoiceExtractionResult:
        return self.extract(
            email_body=email_body,
            use_ocr=False,
            use_gpt_fallback=use_gpt_fallback,
        )

    def _extract_pdf_text_with_fallback(self, pdf_path: str | Path, *, use_ocr: bool) -> str:
        pdf_text = self._pdf_text_extractor.extract_text(pdf_path).strip()
        if pdf_text and len(pdf_text) >= self._minimum_text_length_for_pdf:
            return pdf_text

        if not use_ocr:
            return pdf_text

        try:
            ocr_text = self._ocr_extractor.extract_text(pdf_path).strip()
        except OCRUnavailableError as exc:
            self._logger.info("OCR unavailable for %s: %s", pdf_path, exc)
            return pdf_text

        return "\n".join(part for part in (pdf_text, ocr_text) if part).strip()

    def _build_result_if_complete(self, parsed_fields: dict[str, object]) -> InvoiceExtractionResult | None:
        if self._missing_required_fields(parsed_fields):
            return None

        normalized_payload = dict(parsed_fields)
        status = normalized_payload.get("status")
        if status:
            try:
                normalized_payload["status"] = ExtractedInvoiceStatus(str(status).lower())
            except ValueError:
                normalized_payload["status"] = ExtractedInvoiceStatus.UNKNOWN
        else:
            normalized_payload["status"] = ExtractedInvoiceStatus.UNKNOWN
        return InvoiceExtractionResult.model_validate(normalized_payload)

    @staticmethod
    def _merge_fields(primary: dict[str, object], secondary: dict[str, object]) -> dict[str, object]:
        merged = dict(primary)
        for key, value in secondary.items():
            if key not in merged or merged[key] in (None, "", 0):
                merged[key] = value
        return merged

    @staticmethod
    def _missing_required_fields(parsed_fields: dict[str, object]) -> list[str]:
        required_fields = ("invoice_number", "client_name", "amount", "currency")
        missing = []
        for field_name in required_fields:
            value = parsed_fields.get(field_name)
            if value is None or value == "":
                missing.append(field_name)
        return missing
