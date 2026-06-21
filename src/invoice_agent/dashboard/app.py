from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_agent.db.db import get_session_factory, normalize_database_url
from invoice_agent.db.models import AuditLog, Client, Draft, Invoice, Payment


st.set_page_config(
    page_title="Invoice Intelligence Agent",
    page_icon=":money_with_wings:",
    layout="wide",
)


def load_dashboard_snapshot(session: Session) -> dict[str, int]:
    return {
        "clients": session.scalar(select(func.count(Client.id))) or 0,
        "invoices": session.scalar(select(func.count(Invoice.id))) or 0,
        "payments": session.scalar(select(func.count(Payment.id))) or 0,
        "drafts": session.scalar(select(func.count(Draft.id))) or 0,
        "audit_logs": session.scalar(select(func.count(AuditLog.id))) or 0,
    }


def safe_database_url() -> str:
    raw_url = normalize_database_url()
    if "@" not in raw_url or "://" not in raw_url:
        return raw_url
    prefix, remainder = raw_url.split("://", 1)
    if "@" not in remainder:
        return raw_url
    credentials, host = remainder.split("@", 1)
    if ":" not in credentials:
        return raw_url
    username, _password = credentials.split(":", 1)
    return f"{prefix}://{username}:********@{host}"


def main() -> None:
    st.title("Invoice Intelligence Agent")
    st.caption("Operational dashboard for the deployed Streamlit interface.")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Deployment status")
        st.write(
            {
                "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
                "app_env": os.getenv("APP_ENV", "production"),
                "database_url": safe_database_url(),
                "agent_service_url": os.getenv("AGENT_SERVICE_INTERNAL_URL", "http://agent-service:8080"),
            }
        )

    with right:
        st.subheader("Configured features")
        st.write(
            {
                "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
                "telegram_enabled": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
                "gmail_oauth_enabled": bool(os.getenv("GMAIL_OAUTH_CLIENT_SECRET_FILE")),
            }
        )

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            snapshot = load_dashboard_snapshot(session)
            recent_drafts = session.scalars(
                select(Draft).order_by(Draft.created_at.desc()).limit(5)
            ).all()
    except Exception as exc:  # pragma: no cover - depends on deployment environment
        st.error(f"Database connection failed: {exc}")
        return

    st.subheader("Core metrics")
    metric_columns = st.columns(5)
    metric_columns[0].metric("Clients", snapshot["clients"])
    metric_columns[1].metric("Invoices", snapshot["invoices"])
    metric_columns[2].metric("Payments", snapshot["payments"])
    metric_columns[3].metric("Drafts", snapshot["drafts"])
    metric_columns[4].metric("Audit Logs", snapshot["audit_logs"])

    st.subheader("Recent drafts")
    if not recent_drafts:
        st.info("No drafts available yet.")
    else:
        rows: list[dict[str, Any]] = []
        for draft in recent_drafts:
            rows.append(
                {
                    "draft_id": str(draft.id),
                    "invoice_id": str(draft.invoice_id),
                    "client_id": str(draft.client_id),
                    "status": draft.status.value,
                    "subject": draft.subject,
                    "created_at": draft.created_at.isoformat(),
                }
            )
        st.dataframe(rows, use_container_width=True)


if __name__ == "__main__":
    main()
