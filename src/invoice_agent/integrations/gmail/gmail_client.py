from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow


DEFAULT_GMAIL_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailConfigurationError(ValueError):
    """Raised when the Gmail client is configured incorrectly."""


class GmailAuthenticationError(RuntimeError):
    """Raised when Gmail OAuth credentials cannot be loaded or refreshed."""


class GmailRequestError(RuntimeError):
    """Raised when the Gmail API returns a non-recoverable error."""


class CredentialStore(Protocol):
    """Persistence contract for OAuth token payloads."""

    def load(self) -> dict[str, Any] | None:
        """Load a previously stored OAuth token payload."""

    def save(self, payload: dict[str, Any]) -> None:
        """Persist an OAuth token payload."""

    def delete(self) -> None:
        """Delete any persisted OAuth token payload."""


class GmailServiceProvider(Protocol):
    """Minimal protocol needed by reader and sender services."""

    def list_messages(
        self,
        *,
        user_id: str = "me",
        query: str | None = None,
        label_ids: Sequence[str] | None = None,
        include_spam_trash: bool = False,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List Gmail messages."""

    def get_message(
        self,
        message_id: str,
        *,
        user_id: str = "me",
        format: str = "full",
        metadata_headers: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch a Gmail message."""

    def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
        *,
        user_id: str = "me",
    ) -> bytes:
        """Download a Gmail attachment."""

    def create_draft_from_raw(
        self,
        raw_message: str,
        *,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a Gmail draft from a raw RFC822 message."""

    def send_message_from_raw(
        self,
        raw_message: str,
        *,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a Gmail message from a raw RFC822 payload."""


@dataclass(slots=True)
class GmailClientConfig:
    """
    Runtime configuration for Gmail OAuth and API access.

    The defaults are geared toward production-safe unattended execution while
    still allowing a one-time interactive consent flow during setup.
    """

    client_secret_file: Path
    token_file: Path
    scopes: tuple[str, ...] = field(default_factory=lambda: DEFAULT_GMAIL_SCOPES)
    application_name: str = "Invoice Intelligence Agent"
    allow_user_interaction: bool = True
    oauth_host: str = "localhost"
    oauth_port: int = 0
    open_browser: bool = False
    api_retries: int = 3
    service_cache_enabled: bool = True

    def validate(self) -> None:
        if not self.client_secret_file.exists():
            raise GmailConfigurationError(
                f"Gmail OAuth client secrets file not found: {self.client_secret_file}"
            )
        if not self.client_secret_file.is_file():
            raise GmailConfigurationError(
                f"Gmail OAuth client secrets path is not a file: {self.client_secret_file}"
            )
        if not self.scopes:
            raise GmailConfigurationError("At least one Gmail OAuth scope is required.")

    @classmethod
    def from_env(cls) -> "GmailClientConfig":
        client_secret = os.getenv("GMAIL_OAUTH_CLIENT_SECRET_FILE")
        token_file = os.getenv("GMAIL_OAUTH_TOKEN_FILE", ".gmail_token.json")
        scopes = os.getenv("GMAIL_OAUTH_SCOPES")

        if not client_secret:
            raise GmailConfigurationError(
                "GMAIL_OAUTH_CLIENT_SECRET_FILE must point to the Google OAuth client secrets JSON file."
            )

        parsed_scopes = (
            tuple(scope.strip() for scope in scopes.split(",") if scope.strip())
            if scopes
            else DEFAULT_GMAIL_SCOPES
        )

        return cls(
            client_secret_file=Path(client_secret),
            token_file=Path(token_file),
            scopes=parsed_scopes,
            application_name=os.getenv("GMAIL_APPLICATION_NAME", "Invoice Intelligence Agent"),
            allow_user_interaction=_env_flag("GMAIL_ALLOW_USER_INTERACTION", default=True),
            oauth_host=os.getenv("GMAIL_OAUTH_HOST", "localhost"),
            oauth_port=int(os.getenv("GMAIL_OAUTH_PORT", "0")),
            open_browser=_env_flag("GMAIL_OAUTH_OPEN_BROWSER", default=False),
            api_retries=int(os.getenv("GMAIL_API_RETRIES", "3")),
            service_cache_enabled=_env_flag("GMAIL_SERVICE_CACHE_ENABLED", default=True),
        )


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class FileCredentialStore:
    """File-backed OAuth token persistence."""

    def __init__(self, token_file: str | Path) -> None:
        self._token_file = Path(token_file)

    def load(self) -> dict[str, Any] | None:
        if not self._token_file.exists():
            return None
        with self._token_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, payload: dict[str, Any]) -> None:
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        with self._token_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

    def delete(self) -> None:
        if self._token_file.exists():
            self._token_file.unlink()


class OAuthCredentialsProvider:
    """Loads, refreshes, and optionally bootstraps Gmail OAuth credentials."""

    def __init__(
        self,
        config: GmailClientConfig,
        credential_store: CredentialStore,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._credential_store = credential_store
        self._logger = logger or logging.getLogger(__name__)

    def get_credentials(self, *, force_refresh: bool = False) -> Credentials:
        self._config.validate()

        credentials = self._load_credentials()
        if credentials and credentials.valid and not force_refresh:
            return credentials

        if credentials and credentials.refresh_token:
            self._logger.debug("Refreshing Gmail OAuth credentials.")
            try:
                credentials.refresh(Request())
            except Exception as exc:  # pragma: no cover - library/network error path
                self._logger.warning("Gmail credential refresh failed: %s", exc)
                credentials = None
            else:
                self._save_credentials(credentials)
                return credentials

        if not self._config.allow_user_interaction:
            raise GmailAuthenticationError(
                "No valid Gmail OAuth credentials are available and interactive login is disabled."
            )

        self._logger.info("Starting interactive Gmail OAuth consent flow.")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self._config.client_secret_file),
                scopes=list(self._config.scopes),
            )
            credentials = flow.run_local_server(
                host=self._config.oauth_host,
                port=self._config.oauth_port,
                open_browser=self._config.open_browser,
                authorization_prompt_message=(
                    "Authorize the Invoice Intelligence Agent to access Gmail. "
                    "Complete the browser flow to continue."
                ),
                success_message=(
                    "Gmail authorization completed successfully. "
                    "You may now close this window."
                ),
                access_type="offline",
                prompt="consent",
            )
        except Exception as exc:  # pragma: no cover - library/network error path
            raise GmailAuthenticationError("Interactive Gmail OAuth flow failed.") from exc

        if not credentials or not credentials.valid:
            raise GmailAuthenticationError("Interactive Gmail OAuth flow did not return valid credentials.")

        self._save_credentials(credentials)
        return credentials

    def revoke_cached_credentials(self) -> None:
        """Delete the cached token to force a clean OAuth flow on the next call."""

        self._credential_store.delete()

    def _load_credentials(self) -> Credentials | None:
        payload = self._credential_store.load()
        if not payload:
            return None

        try:
            return Credentials.from_authorized_user_info(payload, scopes=list(self._config.scopes))
        except Exception as exc:  # pragma: no cover - corrupted token file path
            raise GmailAuthenticationError("Stored Gmail OAuth token is invalid or unreadable.") from exc

    def _save_credentials(self, credentials: Credentials) -> None:
        token_payload = json.loads(credentials.to_json())
        self._credential_store.save(token_payload)


class GmailClient(GmailServiceProvider):
    """
    Low-level Gmail API client.

    This class owns OAuth credential management and raw Gmail API interactions.
    Higher-level readers/senders should depend on this abstraction rather than
    binding directly to the Google SDK.
    """

    def __init__(
        self,
        credentials_provider: OAuthCredentialsProvider,
        config: GmailClientConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._credentials_provider = credentials_provider
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        self._service: Resource | None = None

    @classmethod
    def from_env(cls) -> "GmailClient":
        config = GmailClientConfig.from_env()
        credentials_provider = OAuthCredentialsProvider(
            config=config,
            credential_store=FileCredentialStore(config.token_file),
        )
        return cls(credentials_provider=credentials_provider, config=config)

    def get_service(self, *, refresh: bool = False) -> Resource:
        if self._service is None or refresh or not self._config.service_cache_enabled:
            credentials = self._credentials_provider.get_credentials(force_refresh=refresh)
            self._service = build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
        return self._service

    def get_profile(self, *, user_id: str = "me") -> dict[str, Any]:
        return self._execute(lambda service: service.users().getProfile(userId=user_id))

    def list_messages(
        self,
        *,
        user_id: str = "me",
        query: str | None = None,
        label_ids: Sequence[str] | None = None,
        include_spam_trash: bool = False,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            lambda service: service.users()
            .messages()
            .list(
                userId=user_id,
                q=query,
                labelIds=list(label_ids) if label_ids else None,
                includeSpamTrash=include_spam_trash,
                maxResults=max_results,
                pageToken=page_token,
            )
        )

    def get_message(
        self,
        message_id: str,
        *,
        user_id: str = "me",
        format: str = "full",
        metadata_headers: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return self._execute(
            lambda service: service.users()
            .messages()
            .get(
                userId=user_id,
                id=message_id,
                format=format,
                metadataHeaders=list(metadata_headers) if metadata_headers else None,
            )
        )

    def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
        *,
        user_id: str = "me",
    ) -> bytes:
        response = self._execute(
            lambda service: service.users()
            .messages()
            .attachments()
            .get(
                userId=user_id,
                messageId=message_id,
                id=attachment_id,
            )
        )
        data = response.get("data")
        if not data:
            return b""
        return self._decode_base64url(data)

    def create_draft_from_raw(
        self,
        raw_message: str,
        *,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": {"raw": raw_message}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        return self._execute(
            lambda service: service.users().drafts().create(userId=user_id, body=payload)
        )

    def send_message_from_raw(
        self,
        raw_message: str,
        *,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"raw": raw_message}
        if thread_id:
            payload["threadId"] = thread_id
        return self._execute(
            lambda service: service.users().messages().send(userId=user_id, body=payload)
        )

    def _execute(
        self,
        request_factory: Callable[[Resource], Any],
        *,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        try:
            request = request_factory(self.get_service())
            return request.execute(num_retries=self._config.api_retries)
        except HttpError as exc:
            if retry_on_unauthorized and getattr(exc.resp, "status", None) == 401:
                self._logger.warning("Received 401 from Gmail API; rebuilding authenticated service.")
                request = request_factory(self.get_service(refresh=True))
                return request.execute(num_retries=self._config.api_retries)
            raise GmailRequestError(self._format_http_error(exc)) from exc
        except Exception as exc:  # pragma: no cover - network/client library error path
            raise GmailRequestError(f"Unexpected Gmail API failure: {exc}") from exc

    @staticmethod
    def _format_http_error(exc: HttpError) -> str:
        body = ""
        if getattr(exc, "content", None):
            try:
                body = exc.content.decode("utf-8", errors="replace")
            except Exception:
                body = repr(exc.content)
        return f"Gmail API request failed with status {getattr(exc.resp, 'status', 'unknown')}: {body}"

    @staticmethod
    def _decode_base64url(encoded_value: str) -> bytes:
        padding = "=" * (-len(encoded_value) % 4)
        return base64.urlsafe_b64decode(f"{encoded_value}{padding}")
