from __future__ import annotations

import unittest

from invoice_agent.dashboard.app import safe_database_url
from invoice_agent.runtime.agent_service import AgentService, AgentServiceConfig


class DeploymentRuntimeTests(unittest.TestCase):
    def test_agent_service_health_payload(self) -> None:
        service = AgentService(
            AgentServiceConfig(
                host="0.0.0.0",
                port=8080,
                app_env="test",
                service_name="invoice-intelligence-agent-test",
            )
        )

        payload = service.health_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["environment"], "test")
        self.assertEqual(payload["service"], "invoice-intelligence-agent-test")
        self.assertIn("started_at", payload)
        self.assertIn("langgraph_enabled", payload)

    def test_safe_database_url_masks_credentials(self) -> None:
        import os

        previous = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = "postgresql+psycopg://user:secret@postgres:5432/invoice_agent"
            masked = safe_database_url()
            self.assertEqual(
                masked,
                "postgresql+psycopg://user:********@postgres:5432/invoice_agent",
            )
        finally:
            if previous is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous


if __name__ == "__main__":
    unittest.main()
