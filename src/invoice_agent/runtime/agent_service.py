from __future__ import annotations

import json
import logging
import os
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(slots=True)
class AgentServiceConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    heartbeat_interval_seconds: int = 30
    app_env: str = "production"
    service_name: str = "invoice-intelligence-agent"

    @classmethod
    def from_env(cls) -> "AgentServiceConfig":
        return cls(
            host=os.getenv("AGENT_SERVICE_HOST", "0.0.0.0"),
            port=int(os.getenv("AGENT_SERVICE_PORT", "8080")),
            log_level=os.getenv("AGENT_SERVICE_LOG_LEVEL", "INFO"),
            heartbeat_interval_seconds=int(os.getenv("AGENT_SERVICE_HEARTBEAT_SECONDS", "30")),
            app_env=os.getenv("APP_ENV", "production"),
            service_name=os.getenv("SERVICE_NAME", "invoice-intelligence-agent"),
        )


class AgentService:
    """Long-running agent runtime with HTTP health endpoints."""

    def __init__(
        self,
        config: AgentServiceConfig | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config or AgentServiceConfig.from_env()
        self._logger = logger or logging.getLogger(__name__)
        self._server: ThreadingHTTPServer | None = None
        self._stop_event = threading.Event()
        self._started_at = datetime.now(tz=timezone.utc)

    def run(self) -> None:
        self._configure_logging()
        self._logger.info(
            "Starting %s on %s:%s",
            self._config.service_name,
            self._config.host,
            self._config.port,
        )

        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="agent-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()

        server = ThreadingHTTPServer(
            (self._config.host, self._config.port),
            self._build_handler(),
        )
        self._server = server
        self._install_signal_handlers()

        try:
            server.serve_forever()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._logger.info("Shutting down agent service.")
        self._stop_event.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": self._config.service_name,
            "environment": self._config.app_env,
            "started_at": self._started_at.isoformat(),
            "now": datetime.now(tz=timezone.utc).isoformat(),
            "langgraph_enabled": self._langgraph_available(),
        }

    def _configure_logging(self) -> None:
        logging.basicConfig(
            level=getattr(logging, self._config.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._config.heartbeat_interval_seconds):
            self._logger.info(
                "Agent service heartbeat | env=%s | langgraph_enabled=%s",
                self._config.app_env,
                self._langgraph_available(),
            )

    def _build_handler(self):
        parent = self

        class AgentRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path in {"/", "/healthz", "/readyz", "/livez"}:
                    self._write_json(HTTPStatus.OK, parent.health_payload())
                    return
                if self.path == "/info":
                    self._write_json(HTTPStatus.OK, parent.health_payload())
                    return
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "error", "message": f"Unknown path: {self.path}"},
                )

            def log_message(self, fmt: str, *args: object) -> None:
                parent._logger.info("agent_http %s - %s", self.address_string(), fmt % args)

            def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status.value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return AgentRequestHandler

    def _install_signal_handlers(self) -> None:
        def _handle_signal(signum: int, _frame: object) -> None:
            self._logger.info("Received signal %s; initiating shutdown.", signum)
            self.shutdown()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

    @staticmethod
    def _langgraph_available() -> bool:
        try:
            from invoice_agent.workflows.langgraph import compile_invoice_intelligence_graph  # noqa: F401
        except Exception:
            return False
        return True


def main() -> None:
    AgentService().run()


if __name__ == "__main__":
    main()
