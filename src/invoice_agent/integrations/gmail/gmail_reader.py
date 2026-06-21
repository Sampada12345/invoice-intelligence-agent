from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from .gmail_client import GmailServiceProvider


@dataclass(frozen=True, slots=True)
class InvoiceSearchFilters:
    """Search controls for locating invoice-related Gmail messages."""

    newer_than_days: int | None = 30
    unread_only: bool = False
    include_sent: bool = False
    has_pdf_attachment: bool = True
    extra_terms: tuple[str, ...] = ()


@dataclass(slots=True)
class GmailAttachment:
    """Normalized Gmail attachment metadata."""

    attachment_id: str | None
    filename: str
    mime_type: str
    size: int
    part_id: str | None = None
    is_inline: bool = False
    data: bytes | None = None

    @property
    def is_pdf(self) -> bool:
        if self.mime_type.lower() == "application/pdf":
            return True
        return self.filename.lower().endswith(".pdf")


@dataclass(slots=True)
class GmailMessage:
    """Normalized Gmail message representation for application use."""

    message_id: str
    thread_id: str | None
    label_ids: list[str]
    snippet: str | None
    subject: str | None
    sender: str | None
    recipients: list[str] = field(default_factory=list)
    cc_recipients: list[str] = field(default_factory=list)
    bcc_recipients: list[str] = field(default_factory=list)
    received_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[GmailAttachment] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def pdf_attachments(self) -> list[GmailAttachment]:
        return [attachment for attachment in self.attachments if attachment.is_pdf]

    @property
    def has_pdf_attachments(self) -> bool:
        return any(attachment.is_pdf for attachment in self.attachments)


class GmailQueryBuilder:
    """Builds Gmail search queries without coupling callers to search syntax."""

    INVOICE_TERMS: tuple[str, ...] = (
        "invoice",
        "\"payment due\"",
        "billing",
        "\"invoice attached\"",
        "\"invoice number\"",
    )

    @classmethod
    def invoice_query(cls, filters: InvoiceSearchFilters | None = None) -> str:
        filters = filters or InvoiceSearchFilters()

        terms: list[str] = [f"({' OR '.join(cls.INVOICE_TERMS)})"]
        if filters.has_pdf_attachment:
            terms.extend(["has:attachment", "filename:pdf"])
        if filters.unread_only:
            terms.append("is:unread")
        if not filters.include_sent:
            terms.append("-label:sent")
        if filters.newer_than_days is not None:
            terms.append(f"newer_than:{filters.newer_than_days}d")
        terms.extend(filters.extra_terms)
        return " ".join(term for term in terms if term)


class GmailReader:
    """
    High-level reader for Gmail mailboxes.

    Responsibilities:
    - read inbox and sent mail
    - search for invoice-related mail
    - normalize Gmail message payloads
    - download PDF attachments
    """

    def __init__(
        self,
        gmail_client: GmailServiceProvider,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._gmail_client = gmail_client
        self._logger = logger or logging.getLogger(__name__)

    def read_inbox(
        self,
        *,
        user_id: str = "me",
        max_results: int = 100,
        query: str | None = None,
    ) -> list[GmailMessage]:
        return self.list_messages(
            user_id=user_id,
            label_ids=("INBOX",),
            query=query,
            max_results=max_results,
        )

    def read_sent_mail(
        self,
        *,
        user_id: str = "me",
        max_results: int = 100,
        query: str | None = None,
    ) -> list[GmailMessage]:
        return self.list_messages(
            user_id=user_id,
            label_ids=("SENT",),
            query=query,
            max_results=max_results,
        )

    def search_invoice_emails(
        self,
        *,
        user_id: str = "me",
        filters: InvoiceSearchFilters | None = None,
        max_results: int = 100,
    ) -> list[GmailMessage]:
        search_query = GmailQueryBuilder.invoice_query(filters)
        label_ids: tuple[str, ...] | None = None if (filters and filters.include_sent) else ("INBOX",)
        return self.list_messages(
            user_id=user_id,
            label_ids=label_ids,
            query=search_query,
            max_results=max_results,
        )

    def list_messages(
        self,
        *,
        user_id: str = "me",
        label_ids: Sequence[str] | None = None,
        query: str | None = None,
        max_results: int = 100,
    ) -> list[GmailMessage]:
        messages: list[GmailMessage] = []
        next_page_token: str | None = None

        while len(messages) < max_results:
            remaining = max_results - len(messages)
            response = self._gmail_client.list_messages(
                user_id=user_id,
                query=query,
                label_ids=label_ids,
                max_results=min(remaining, 500),
                page_token=next_page_token,
            )

            for message_ref in response.get("messages", []):
                messages.append(
                    self.get_message(
                        message_ref["id"],
                        user_id=user_id,
                    )
                )
                if len(messages) >= max_results:
                    break

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return messages

    def get_message(
        self,
        message_id: str,
        *,
        user_id: str = "me",
    ) -> GmailMessage:
        payload = self._gmail_client.get_message(message_id, user_id=user_id, format="full")
        return self._parse_message(payload)

    def download_pdf_attachments(
        self,
        message: str | GmailMessage,
        destination_dir: str | Path,
        *,
        user_id: str = "me",
        overwrite: bool = False,
    ) -> list[Path]:
        normalized_message = (
            self.get_message(message, user_id=user_id) if isinstance(message, str) else message
        )
        output_directory = Path(destination_dir)
        output_directory.mkdir(parents=True, exist_ok=True)

        downloaded_files: list[Path] = []
        for attachment in normalized_message.pdf_attachments:
            if not attachment.attachment_id:
                if attachment.data is None:
                    self._logger.debug(
                        "Skipping attachment without downloadable data for message %s",
                        normalized_message.message_id,
                    )
                    continue
                file_bytes = attachment.data
            else:
                file_bytes = self._gmail_client.get_attachment(
                    normalized_message.message_id,
                    attachment.attachment_id,
                    user_id=user_id,
                )
            safe_filename = self._sanitize_filename(
                attachment.filename or f"{normalized_message.message_id}.pdf"
            )
            output_path = output_directory / safe_filename
            if output_path.exists() and not overwrite:
                output_path = self._resolve_collision(output_path)

            output_path.write_bytes(file_bytes)
            downloaded_files.append(output_path)

        return downloaded_files

    def _parse_message(self, message_payload: dict[str, Any]) -> GmailMessage:
        payload = message_payload.get("payload", {})
        headers = self._extract_headers(payload.get("headers", []))
        body_text, body_html, attachments = self._extract_body_and_attachments(payload)
        received_at = self._extract_received_at(message_payload, headers.get("date"))

        recipients = self._split_addresses(headers.get("to"))
        cc_recipients = self._split_addresses(headers.get("cc"))
        bcc_recipients = self._split_addresses(headers.get("bcc"))

        return GmailMessage(
            message_id=message_payload["id"],
            thread_id=message_payload.get("threadId"),
            label_ids=list(message_payload.get("labelIds", [])),
            snippet=message_payload.get("snippet"),
            subject=headers.get("subject"),
            sender=headers.get("from"),
            recipients=recipients,
            cc_recipients=cc_recipients,
            bcc_recipients=bcc_recipients,
            received_at=received_at,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
            raw_payload=message_payload,
        )

    def _extract_body_and_attachments(
        self,
        payload: dict[str, Any],
    ) -> tuple[str | None, str | None, list[GmailAttachment]]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[GmailAttachment] = []

        for part in self._walk_parts(payload):
            mime_type = (part.get("mimeType") or "").lower()
            body = part.get("body", {})
            filename = part.get("filename") or ""

            if filename:
                attachments.append(
                    GmailAttachment(
                        attachment_id=body.get("attachmentId"),
                        filename=filename,
                        mime_type=part.get("mimeType") or "application/octet-stream",
                        size=int(body.get("size", 0) or 0),
                        part_id=part.get("partId"),
                        is_inline=bool(part.get("headers")) and self._is_inline_part(part),
                        data=self._decode_binary_body_data(body["data"]) if body.get("data") else None,
                    )
                )
                continue

            body_data = body.get("data")
            if not body_data:
                continue

            decoded = self._decode_body_data(body_data)
            if mime_type == "text/plain":
                plain_parts.append(decoded)
            elif mime_type == "text/html":
                html_parts.append(decoded)

        plain_text = "\n".join(part for part in plain_parts if part).strip() or None
        html_text = "\n".join(part for part in html_parts if part).strip() or None
        return plain_text, html_text, attachments

    def _walk_parts(self, payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        yield payload
        for child_part in payload.get("parts", []) or []:
            yield from self._walk_parts(child_part)

    @staticmethod
    def _extract_headers(headers: Sequence[dict[str, str]]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for header in headers:
            name = (header.get("name") or "").strip().lower()
            value = (header.get("value") or "").strip()
            if name and value:
                normalized[name] = value
        return normalized

    @staticmethod
    def _extract_received_at(
        message_payload: dict[str, Any],
        date_header: str | None,
    ) -> datetime | None:
        internal_date = message_payload.get("internalDate")
        if internal_date:
            try:
                return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                pass

        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, IndexError):
                return None
        return None

    @staticmethod
    def _split_addresses(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _decode_body_data(data: str) -> str:
        from .gmail_client import GmailClient

        return GmailClient._decode_base64url(data).decode("utf-8", errors="replace")

    @staticmethod
    def _decode_binary_body_data(data: str) -> bytes:
        from .gmail_client import GmailClient

        return GmailClient._decode_base64url(data)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip())
        return sanitized or "attachment.pdf"

    @staticmethod
    def _resolve_collision(candidate: Path) -> Path:
        counter = 1
        while True:
            replacement = candidate.with_name(
                f"{candidate.stem}_{counter}{candidate.suffix}"
            )
            if not replacement.exists():
                return replacement
            counter += 1

    @staticmethod
    def _is_inline_part(part: dict[str, Any]) -> bool:
        for header in part.get("headers", []) or []:
            if (header.get("name") or "").lower() == "content-disposition":
                return "inline" in (header.get("value") or "").lower()
        return False
