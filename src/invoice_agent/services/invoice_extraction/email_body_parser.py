from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


class EmailBodyInvoiceParser:
    """Extracts invoice fields from plaintext or HTML-stripped email content."""

    _invoice_number_patterns = (
        r"^invoice(?:\s+number|\s+no\.?|\s+#|#)\s*[:\-]?\s*([A-Z0-9\-\/]+)\s*$",
        r"^inv(?:oice)?(?:\s+number|\s+no\.?)?\s*[:#\-]\s*([A-Z0-9\-\/]+)\s*$",
    )
    _client_name_patterns = (
        r"^client(?:\s+name)?\s*[:\-]\s*(.+)$",
        r"^bill\s+to\s*[:\-]\s*(.+)$",
        r"^customer\s*[:\-]\s*(.+)$",
    )
    _client_email_patterns = (
        r"^client\s+email\s*[:\-]\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})$",
        r"^email\s*[:\-]\s*([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})$",
    )
    _invoice_date_patterns = (
        r"^invoice\s+date\s*[:\-]\s*([A-Z0-9,\/\-\s]+)$",
        r"^date\s*[:\-]\s*([A-Z0-9,\/\-\s]+)$",
    )
    _due_date_patterns = (
        r"^due\s+date\s*[:\-]\s*([A-Z0-9,\/\-\s]+)$",
        r"^payment\s+due\s*[:\-]\s*([A-Z0-9,\/\-\s]+)$",
    )
    _amount_patterns = (
        r"^(?:total|amount\s+due|invoice\s+amount)\s*[:\-]?\s*([$EURGBPUSDINRJPYCADAUD]{0,4})\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*$",
    )
    _status_patterns = (
        r"^status\s*[:\-]\s*(paid|open|overdue|draft|cancelled|disputed)\s*$",
        r"^invoice\s+status\s*[:\-]\s*(paid|open|overdue|draft|cancelled|disputed)\s*$",
    )

    _currency_symbol_map = {
        "$": "USD",
        "USD": "USD",
        "EUR": "EUR",
        "GBP": "GBP",
        "INR": "INR",
        "JPY": "JPY",
        "CAD": "CAD",
        "AUD": "AUD",
    }

    def parse(self, text: str) -> dict[str, object]:
        normalized_text = self._normalize_text(text)
        parsed: dict[str, object] = {}

        invoice_number = self._search_first_group(normalized_text, self._invoice_number_patterns)
        if invoice_number:
            parsed["invoice_number"] = invoice_number

        client_name = self._search_first_group(normalized_text, self._client_name_patterns)
        if client_name:
            parsed["client_name"] = self._cleanup_line_value(client_name)

        client_email = self._search_first_group(normalized_text, self._client_email_patterns)
        if client_email:
            parsed["client_email"] = client_email.lower()

        invoice_date = self._search_first_group(normalized_text, self._invoice_date_patterns)
        parsed_date = self._parse_date(invoice_date)
        if parsed_date:
            parsed["invoice_date"] = parsed_date

        due_date = self._search_first_group(normalized_text, self._due_date_patterns)
        parsed_due_date = self._parse_date(due_date)
        if parsed_due_date:
            parsed["due_date"] = parsed_due_date

        amount_match = self._search_amount(normalized_text)
        if amount_match:
            currency, amount = amount_match
            parsed["currency"] = currency
            parsed["amount"] = amount

        status = self._search_first_group(normalized_text, self._status_patterns)
        if status:
            parsed["status"] = status.lower()

        return parsed

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"[ \t]+", " ", text.replace("\r", "\n"))

    @classmethod
    def _search_first_group(cls, text: str, patterns: tuple[str, ...]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        return None

    @classmethod
    def _search_amount(cls, text: str) -> tuple[str, Decimal] | None:
        for pattern in cls._amount_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if not match:
                continue
            raw_currency = (match.group(1) or "").strip().upper()
            raw_amount = match.group(2).replace(",", "")
            try:
                amount = Decimal(raw_amount)
            except InvalidOperation:
                return None
            currency = cls._currency_symbol_map.get(raw_currency or "$", raw_currency or "USD")
            return currency, amount
        return None

    @staticmethod
    def _cleanup_line_value(value: str) -> str:
        return value.split("\n", 1)[0].strip(" .,:;")

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None

        candidate = value.split("\n", 1)[0].strip()
        for fmt in (
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ):
            try:
                from datetime import datetime

                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
        return None
