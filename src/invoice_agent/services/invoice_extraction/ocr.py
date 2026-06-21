from __future__ import annotations

import io
import logging
import shutil
from pathlib import Path

import fitz
import pytesseract
from PIL import Image


class OCRUnavailableError(RuntimeError):
    """Raised when OCR support is requested but not available."""


class OCRParsingError(RuntimeError):
    """Raised when OCR processing fails for a document."""


class PDFOCRExtractor:
    """
    Runs OCR against PDF page renderings.

    Uses PyMuPDF for page rasterization and pytesseract for text recognition.
    """

    def __init__(
        self,
        *,
        dpi: int = 200,
        tesseract_cmd: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._dpi = dpi
        self._logger = logger or logging.getLogger(__name__)
        self._tesseract_cmd = tesseract_cmd
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def extract_text(self, pdf_path: str | Path) -> str:
        self._ensure_ocr_available()
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            zoom = self._dpi / 72
            matrix = fitz.Matrix(zoom, zoom)
            document = fitz.open(str(path))
            pages_text: list[str] = []
            for page in document:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                pages_text.append(pytesseract.image_to_string(image).strip())
            document.close()
        except Exception as exc:  # pragma: no cover - third-party tool failure path
            raise OCRParsingError(f"Failed OCR processing for {path}: {exc}") from exc

        text = "\n".join(fragment for fragment in pages_text if fragment).strip()
        self._logger.debug("OCR extracted %s characters from PDF %s.", len(text), path)
        return text

    def is_available(self) -> bool:
        return self._resolve_tesseract_binary() is not None

    def _ensure_ocr_available(self) -> None:
        if not self.is_available():
            raise OCRUnavailableError(
                "OCR requested but the Tesseract binary is not installed or not available on PATH."
            )

    def _resolve_tesseract_binary(self) -> str | None:
        if self._tesseract_cmd:
            return self._tesseract_cmd
        return shutil.which("tesseract")
