from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Sequence

from .gmail_client import GmailServiceProvider


@dataclass(frozen=True, slots=True)
class OutboundAttachment:
    """Represents an attachment for a draft or outbound Gmail message."""

    filename: str
    data: bytes
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class DraftResult:
    """Normalized response for a created Gmail draft."""

    draft_id: str
    message_id: str | None
    thread_id: str | None
    raw_response: dict


@dataclass(frozen=True, slots=True)
class SendResult:
    """Normalized response for a sent Gmail message."""

    message_id: str
    thread_id: str | None
    label_ids: list[str]
    raw_response: dict


class GmailSender:
    """
    High-level outbound Gmail service.

    Responsibilities:
    - build RFC822 email messages
    - create Gmail drafts
    - send Gmail messages
    """

    def __init__(
        self,
        gmail_client: GmailServiceProvider,
        *,
        default_sender: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._gmail_client = gmail_client
        self._default_sender = default_sender
        self._logger = logger or logging.getLogger(__name__)

    def create_draft(
        self,
        *,
        to: Sequence[str] | str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc: Sequence[str] | str | None = None,
        bcc: Sequence[str] | str | None = None,
        sender: str | None = None,
        reply_to: str | None = None,
        attachments: Sequence[str | Path | OutboundAttachment] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: Sequence[str] | None = None,
        user_id: str = "me",
    ) -> DraftResult:
        message = self.build_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            sender=sender,
            reply_to=reply_to,
            attachments=attachments,
            in_reply_to=in_reply_to,
            references=references,
        )
        raw_message = self._encode_message(message)
        response = self._gmail_client.create_draft_from_raw(
            raw_message,
            user_id=user_id,
            thread_id=thread_id,
        )
        message_payload = response.get("message", {})
        return DraftResult(
            draft_id=response["id"],
            message_id=message_payload.get("id"),
            thread_id=message_payload.get("threadId"),
            raw_response=response,
        )

    def send_email(
        self,
        *,
        to: Sequence[str] | str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc: Sequence[str] | str | None = None,
        bcc: Sequence[str] | str | None = None,
        sender: str | None = None,
        reply_to: str | None = None,
        attachments: Sequence[str | Path | OutboundAttachment] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: Sequence[str] | None = None,
        user_id: str = "me",
    ) -> SendResult:
        message = self.build_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            sender=sender,
            reply_to=reply_to,
            attachments=attachments,
            in_reply_to=in_reply_to,
            references=references,
        )
        return self.send_message(
            message,
            user_id=user_id,
            thread_id=thread_id,
        )

    def send_message(
        self,
        message: EmailMessage,
        *,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> SendResult:
        raw_message = self._encode_message(message)
        response = self._gmail_client.send_message_from_raw(
            raw_message,
            user_id=user_id,
            thread_id=thread_id,
        )
        return SendResult(
            message_id=response["id"],
            thread_id=response.get("threadId"),
            label_ids=list(response.get("labelIds", [])),
            raw_response=response,
        )

    def build_message(
        self,
        *,
        to: Sequence[str] | str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc: Sequence[str] | str | None = None,
        bcc: Sequence[str] | str | None = None,
        sender: str | None = None,
        reply_to: str | None = None,
        attachments: Sequence[str | Path | OutboundAttachment] | None = None,
        in_reply_to: str | None = None,
        references: Sequence[str] | None = None,
    ) -> EmailMessage:
        message = EmailMessage(policy=SMTP)
        final_sender = sender or self._default_sender
        if final_sender:
            message["From"] = final_sender
        message["To"] = self._normalize_recipients(to)
        if cc:
            message["Cc"] = self._normalize_recipients(cc)
        if bcc:
            message["Bcc"] = self._normalize_recipients(bcc)
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid()
        if reply_to:
            message["Reply-To"] = reply_to
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = " ".join(references)

        message.set_content(body_text)
        if body_html:
            message.add_alternative(body_html, subtype="html")

        for attachment in self._normalize_attachments(attachments or ()):
            maintype, subtype = self._resolve_content_type(attachment)
            message.add_attachment(
                attachment.data,
                maintype=maintype,
                subtype=subtype,
                filename=attachment.filename,
            )

        return message

    @staticmethod
    def _normalize_recipients(recipients: Sequence[str] | str) -> str:
        if isinstance(recipients, str):
            normalized = [recipient.strip() for recipient in recipients.split(",") if recipient.strip()]
        else:
            normalized = [recipient.strip() for recipient in recipients if recipient.strip()]

        if not normalized:
            raise ValueError("At least one recipient email address is required.")
        return ", ".join(normalized)

    def _normalize_attachments(
        self,
        attachments: Sequence[str | Path | OutboundAttachment],
    ) -> list[OutboundAttachment]:
        normalized: list[OutboundAttachment] = []
        for attachment in attachments:
            if isinstance(attachment, OutboundAttachment):
                normalized.append(attachment)
                continue

            attachment_path = Path(attachment)
            if not attachment_path.exists():
                raise FileNotFoundError(f"Attachment file not found: {attachment_path}")
            normalized.append(
                OutboundAttachment(
                    filename=attachment_path.name,
                    data=attachment_path.read_bytes(),
                    mime_type=mimetypes.guess_type(str(attachment_path))[0],
                )
            )
        return normalized

    @staticmethod
    def _resolve_content_type(attachment: OutboundAttachment) -> tuple[str, str]:
        mime_type = attachment.mime_type or mimetypes.guess_type(attachment.filename)[0]
        if not mime_type:
            return "application", "octet-stream"

        maintype, subtype = mime_type.split("/", 1)
        return maintype, subtype

    @staticmethod
    def _encode_message(message: EmailMessage) -> str:
        return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
