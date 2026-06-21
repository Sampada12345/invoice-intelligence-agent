from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx


class TelegramConfigurationError(ValueError):
    """Raised when Telegram bot settings are missing or invalid."""


class TelegramRequestError(RuntimeError):
    """Raised when a Telegram Bot API request fails."""


@dataclass(slots=True)
class TelegramBotConfig:
    bot_token: str
    api_base_url: str = "https://api.telegram.org"
    timeout_seconds: float = 10.0

    @property
    def base_api_url(self) -> str:
        return f"{self.api_base_url.rstrip('/')}/bot{self.bot_token}"

    def validate(self) -> None:
        if not self.bot_token:
            raise TelegramConfigurationError("Telegram bot token is required.")

    @classmethod
    def from_env(cls) -> "TelegramBotConfig":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise TelegramConfigurationError("TELEGRAM_BOT_TOKEN must be configured.")
        return cls(
            bot_token=token,
            api_base_url=os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org"),
            timeout_seconds=float(os.getenv("TELEGRAM_TIMEOUT_SECONDS", "10")),
        )


class TelegramBotClient:
    """Thin wrapper over the Telegram Bot API."""

    def __init__(
        self,
        config: TelegramBotConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._logger = logger or logging.getLogger(__name__)

    @classmethod
    def from_env(cls) -> "TelegramBotClient":
        return cls(TelegramBotConfig.from_env())

    def send_message(
        self,
        *,
        chat_id: str | int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._post("sendMessage", payload)

    def answer_callback_query(
        self,
        *,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        return self._post("answerCallbackQuery", payload)

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._config.base_api_url}/{method}"
        try:
            with httpx.Client(timeout=self._config.timeout_seconds) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network/API failure path
            raise TelegramRequestError(
                f"Telegram API request failed with status {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network/API failure path
            raise TelegramRequestError(f"Telegram API request failed: {exc}") from exc

        body = response.json()
        if not body.get("ok", False):  # pragma: no cover - depends on live Telegram response
            raise TelegramRequestError(f"Telegram API returned failure payload: {body}")
        return body
