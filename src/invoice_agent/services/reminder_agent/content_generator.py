from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

from .schema import ReminderContent, ReminderGenerationContext, ReminderKind


class ReminderGenerationError(RuntimeError):
    """Raised when reminder content generation fails."""


class OpenAIReminderContentGenerator:
    """
    Generates reminder drafts with OpenAI and falls back to a deterministic
    template when the API is unavailable or unconfigured.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        fallback_to_template: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model or os.getenv("OPENAI_REMINDER_MODEL", "gpt-4.1-mini")
        self._fallback_to_template = fallback_to_template
        self._logger = logger or logging.getLogger(__name__)

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def generate(self, context: ReminderGenerationContext) -> ReminderContent:
        if self.is_configured():
            try:
                return self._generate_with_openai(context)
            except Exception as exc:  # pragma: no cover - network/service error path
                if not self._fallback_to_template:
                    raise ReminderGenerationError(f"OpenAI reminder generation failed: {exc}") from exc
                self._logger.warning(
                    "OpenAI reminder generation failed; falling back to template: %s",
                    exc,
                )

        if not self._fallback_to_template:
            raise ReminderGenerationError(
                "OPENAI_API_KEY is not configured and template fallback is disabled."
            )
        return self._generate_template(context)

    def _generate_with_openai(self, context: ReminderGenerationContext) -> ReminderContent:
        client = OpenAI(api_key=self._api_key)
        prompt = self._build_prompt(context)
        schema_definition = ReminderContent.model_json_schema()

        response = client.responses.create(
            model=self._model,
            input=(
                "You generate professional invoice payment reminder emails.\n"
                "Return ONLY valid JSON matching this schema:\n"
                f"{json.dumps(schema_definition, indent=2)}\n\n"
                f"{prompt}"
            ),
        )

        output_text = getattr(response, "output_text", "").strip()
        if not output_text:
            raise ReminderGenerationError("OpenAI returned an empty reminder payload.")

        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ReminderGenerationError("OpenAI reminder response was not valid JSON.") from exc

        return ReminderContent.model_validate(payload)

    def _generate_template(self, context: ReminderGenerationContext) -> ReminderContent:
        if context.reminder_kind == ReminderKind.OVERDUE:
            subject = f"Overdue invoice reminder: {context.invoice_number}"
            body_text = (
                f"Hello {context.client_name},\n\n"
                f"This is a reminder that invoice {context.invoice_number} for "
                f"{context.currency} {context.amount_due:.2f} was due on {context.due_date.isoformat()} "
                f"and is now {abs(context.days_delta)} day(s) overdue.\n\n"
                "Please let us know the payment status or arrange payment at your earliest convenience.\n\n"
                "Thank you."
            )
        else:
            subject = f"Upcoming payment reminder: {context.invoice_number}"
            body_text = (
                f"Hello {context.client_name},\n\n"
                f"This is a friendly reminder that invoice {context.invoice_number} for "
                f"{context.currency} {context.amount_due:.2f} is due on {context.due_date.isoformat()} "
                f"in {context.days_delta} day(s).\n\n"
                "Please let us know if the payment is already scheduled or if you need any supporting details.\n\n"
                "Thank you."
            )

        body_html = (
            "<p>Hello {client_name},</p>"
            "<p>{paragraph_one}</p>"
            "<p>{paragraph_two}</p>"
            "<p>Thank you.</p>"
        ).format(
            client_name=context.client_name,
            paragraph_one=body_text.split("\n\n")[1],
            paragraph_two=body_text.split("\n\n")[2],
        )

        return ReminderContent(subject=subject, body_text=body_text, body_html=body_html)

    @staticmethod
    def _build_prompt(context: ReminderGenerationContext) -> str:
        timing = (
            f"{abs(context.days_delta)} day(s) overdue"
            if context.reminder_kind == ReminderKind.OVERDUE
            else f"due in {context.days_delta} day(s)"
        )
        return (
            "Generate a concise, professional, non-threatening reminder email.\n"
            f"Client name: {context.client_name}\n"
            f"Invoice number: {context.invoice_number}\n"
            f"Invoice due date: {context.due_date.isoformat()}\n"
            f"Amount due: {context.currency} {context.amount_due:.2f}\n"
            f"Reminder timing: {timing}\n"
            f"Invoice status: {context.invoice_status}\n"
            "Use clear payment-reminder language and avoid overly aggressive wording."
        )
