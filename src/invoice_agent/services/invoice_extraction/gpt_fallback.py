from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

from .schema import InvoiceExtractionResult


class GPTExtractionError(RuntimeError):
    """Raised when the GPT fallback cannot extract a valid invoice payload."""


class GPTInvoiceExtractor:
    """
    Uses OpenAI as a final extraction fallback when deterministic parsing fails.

    The model is instructed to emit only the target JSON structure.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model or os.getenv("OPENAI_INVOICE_EXTRACTION_MODEL", "gpt-4.1-mini")
        self._logger = logger or logging.getLogger(__name__)

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def extract(self, document_text: str) -> InvoiceExtractionResult:
        if not self.is_configured():
            raise GPTExtractionError("OPENAI_API_KEY is not configured for GPT fallback extraction.")

        client = OpenAI(api_key=self._api_key)
        schema_definition = InvoiceExtractionResult.output_json_schema()
        prompt = (
            "Extract invoice details from the supplied text.\n"
            "Return ONLY valid JSON matching this schema.\n"
            f"{json.dumps(schema_definition, indent=2, default=str)}\n\n"
            "If a field is unavailable, set dates and client_email to null, "
            "status to \"unknown\", and use your best supported currency and amount values.\n\n"
            f"Document text:\n{document_text}"
        )

        try:
            response = client.responses.create(
                model=self._model,
                input=prompt,
            )
        except Exception as exc:  # pragma: no cover - network/service failure path
            raise GPTExtractionError(f"OpenAI extraction request failed: {exc}") from exc

        output_text = getattr(response, "output_text", "").strip()
        if not output_text:
            raise GPTExtractionError("OpenAI extraction returned an empty response.")

        try:
            payload: dict[str, Any] = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise GPTExtractionError("OpenAI extraction did not return valid JSON.") from exc

        self._logger.debug("GPT fallback produced invoice extraction payload.")
        return InvoiceExtractionResult.model_validate(payload)
