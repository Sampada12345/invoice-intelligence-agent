from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader


class PDFParsingError(RuntimeError):
    """Raised when a PDF cannot be parsed into text."""


class PDFTextExtractor:
    """Extracts machine-readable text from PDF files."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def extract_text(self, pdf_path: str | Path) -> str:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            reader = PdfReader(str(path))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:  # pragma: no cover - third-party parser failure path
            raise PDFParsingError(f"Failed to parse PDF {path}: {exc}") from exc

        text = "\n".join(page for page in pages if page).strip()
        self._logger.debug("Extracted %s characters from PDF %s.", len(text), path)
        return text
