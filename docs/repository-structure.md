# Invoice Intelligence Agent - Complete Repository Structure

This document defines the **target repository tree only**. It does not include implementation code.

---

## 1. Repository Tree

```text
invoice-intelligence-agent/
├── README.md
├── .env.example
├── requirements.txt
├── pyproject.toml
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── repository-structure.md
│   ├── decisions/
│   │   ├── adr-001-modular-monolith.md
│   │   ├── adr-002-sqlalchemy-repository-pattern.md
│   │   └── adr-003-langgraph-migration-strategy.md
│   ├── diagrams/
│   │   ├── agent-interaction.mmd
│   │   ├── deployment-architecture.mmd
│   │   └── docker-architecture.mmd
│   └── runbooks/
│       ├── oauth-setup.md
│       ├── incident-response.md
│       └── production-operations.md
├── src/
│   └── invoice_agent/
│       ├── __init__.py
│       ├── config/
│       │   ├── settings.py
│       │   ├── logging.py
│       │   └── security.py
│       ├── domain/
│       │   ├── entities/
│       │   │   ├── email_message.py
│       │   │   ├── invoice.py
│       │   │   ├── payment.py
│       │   │   ├── reminder.py
│       │   │   └── audit_event.py
│       │   ├── value_objects/
│       │   │   ├── money.py
│       │   │   ├── due_window.py
│       │   │   └── match_score.py
│       │   └── enums.py
│       ├── schemas/
│       │   ├── email.py
│       │   ├── invoice.py
│       │   ├── payment.py
│       │   ├── reminder.py
│       │   └── dashboard.py
│       ├── integrations/
│       │   ├── gmail/
│       │   │   ├── auth.py
│       │   │   ├── client.py
│       │   │   ├── inbox_reader.py
│       │   │   ├── attachment_downloader.py
│       │   │   └── draft_sender.py
│       │   ├── openai/
│       │   │   ├── client.py
│       │   │   └── structured_extraction.py
│       │   └── telegram/
│       │       ├── bot_client.py
│       │       └── approval_notifier.py
│       ├── db/
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── models/
│       │   │   ├── email_record.py
│       │   │   ├── invoice_record.py
│       │   │   ├── payment_record.py
│       │   │   ├── reminder_record.py
│       │   │   ├── audit_event_record.py
│       │   │   └── dashboard_snapshot_record.py
│       │   ├── repositories/
│       │   │   ├── emails.py
│       │   │   ├── invoices.py
│       │   │   ├── payments.py
│       │   │   ├── reminders.py
│       │   │   └── audits.py
│       │   └── migrations/
│       ├── services/
│       │   ├── gmail_integration/
│       │   │   ├── email_ingestion_service.py
│       │   │   └── email_classification_service.py
│       │   ├── invoice_extraction/
│       │   │   ├── pdf_parser_service.py
│       │   │   ├── extraction_service.py
│       │   │   └── validation_service.py
│       │   ├── payment_matching/
│       │   │   ├── payment_parser_service.py
│       │   │   ├── matching_service.py
│       │   │   └── reconciliation_service.py
│       │   ├── due_date_monitoring/
│       │   │   ├── due_date_service.py
│       │   │   └── reminder_candidate_service.py
│       │   ├── reminder_generation/
│       │   │   ├── reminder_draft_service.py
│       │   │   └── template_service.py
│       │   ├── notification/
│       │   │   ├── approval_service.py
│       │   │   └── notification_service.py
│       │   ├── dashboard/
│       │   │   ├── metrics_service.py
│       │   │   └── snapshot_service.py
│       │   └── audit/
│       │       └── audit_log_service.py
│       ├── workflows/
│       │   ├── orchestration/
│       │   │   ├── daily_scan_workflow.py
│       │   │   ├── payment_reconciliation_workflow.py
│       │   │   └── reminder_approval_workflow.py
│       │   └── langgraph/
│       │       ├── state.py
│       │       ├── nodes.py
│       │       ├── edges.py
│       │       └── graph_builder.py
│       ├── scheduler/
│       │   ├── jobs.py
│       │   ├── triggers.py
│       │   └── bootstrap.py
│       ├── dashboard/
│       │   ├── app.py
│       │   ├── pages/
│       │   │   ├── 1_overview.py
│       │   │   ├── 2_invoices.py
│       │   │   ├── 3_payments.py
│       │   │   ├── 4_reminders.py
│       │   │   └── 5_audit_logs.py
│       │   └── components/
│       ├── api/
│       │   ├── health.py
│       │   ├── approvals.py
│       │   └── webhooks.py
│       └── utils/
│           ├── time.py
│           ├── idempotency.py
│           ├── hashing.py
│           └── file_storage.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── fixtures/
├── storage/
│   ├── raw_emails/
│   ├── attachments/
│   └── exports/
├── scripts/
│   ├── bootstrap_local.sh
│   ├── seed_demo_data.py
│   └── rotate_tokens.py
└── .github/
    └── workflows/
        ├── ci.yml
        ├── docker.yml
        └── release.yml
```

---

## 2. Folders and Their Role

| Folder | Purpose | Depends On |
|---|---|---|
| `/docs` | architecture, ADRs, diagrams, and operational documentation | repository root files |
| `/docs/decisions` | ADRs that capture architectural trade-offs | `docs/architecture.md` |
| `/docs/diagrams` | Mermaid diagrams for workflows and deployment | `docs/architecture.md` |
| `/docs/runbooks` | operational procedures for setup and incidents | `src/invoice_agent/config`, `integrations`, `scheduler` |
| `/src` | application source root | `pyproject.toml` |
| `/src/invoice_agent` | main package namespace | all application subfolders |
| `/src/invoice_agent/config` | settings, logging, and security configuration | `.env.example`, `pyproject.toml` |
| `/src/invoice_agent/domain` | framework-independent business concepts | none outside standard Python typing |
| `/src/invoice_agent/domain/entities` | domain entities representing core business records | `domain/value_objects`, `domain/enums` |
| `/src/invoice_agent/domain/value_objects` | reusable business value types | `domain/enums` where relevant |
| `/src/invoice_agent/schemas` | Pydantic data contracts | `domain`, `config` |
| `/src/invoice_agent/integrations` | external system adapters | `config`, `schemas`, `utils` |
| `/src/invoice_agent/db` | SQLAlchemy models, sessions, repositories, migrations | `config`, `domain`, `schemas` |
| `/src/invoice_agent/db/models` | ORM records mapped to database tables | `db/base.py`, `domain/enums` |
| `/src/invoice_agent/db/repositories` | database access abstraction | `db/session.py`, `db/models/*` |
| `/src/invoice_agent/services` | business capability modules | `integrations`, `db`, `schemas`, `domain`, `utils` |
| `/src/invoice_agent/workflows` | orchestration layers | `services`, `scheduler`, `schemas` |
| `/src/invoice_agent/workflows/orchestration` | class-based workflow execution | `services/*` |
| `/src/invoice_agent/workflows/langgraph` | LangGraph-ready orchestration definitions | `services/*`, `schemas`, `domain` |
| `/src/invoice_agent/scheduler` | APScheduler registration and runtime bootstrapping | `workflows/orchestration`, `config` |
| `/src/invoice_agent/dashboard` | Streamlit UI | `services/dashboard`, `db/repositories`, `schemas/dashboard.py` |
| `/src/invoice_agent/dashboard/pages` | dashboard page modules | `dashboard/app.py`, `services/dashboard/*` |
| `/src/invoice_agent/dashboard/components` | reusable UI widgets | `dashboard/pages/*` |
| `/src/invoice_agent/api` | approval and health API endpoints | `services/notification`, `config`, `db/repositories` |
| `/src/invoice_agent/utils` | shared helper modules | used by all layers |
| `/tests` | automated validation structure | all runtime folders |
| `/storage` | local persistent artifacts | `utils/file_storage.py`, Gmail and extraction services |
| `/scripts` | operational helper scripts | `src/invoice_agent/config`, `db`, `integrations` |
| `/.github/workflows` | CI/CD workflow definitions | `pyproject.toml`, `Dockerfile`, `docker-compose.yml` |

---

## 3. File-by-File Purpose and Dependencies

### 3.1 Root Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `README.md` | repository entry point and contributor orientation | `docs/architecture.md`, `docs/repository-structure.md` | contributors, CI reviewers |
| `.env.example` | documents required environment variables | `config/settings.py`, `config/security.py` | local setup, Docker, scripts |
| `requirements.txt` | pip-compatible dependency list mirroring runtime packages | `pyproject.toml` | Docker builds, local installs, CI |
| `pyproject.toml` | Python package metadata and dependency declarations | none | all Python source, CI, Docker build |
| `alembic.ini` | database migration configuration | `db/session.py`, `db/base.py` | migration commands, CI |
| `Dockerfile` | production image definition | `pyproject.toml`, `src/`, `scripts/` | `docker-compose.yml`, CI docker build |
| `docker-compose.yml` | local multi-container orchestration | `Dockerfile`, `.env.example` | local development, integration testing |

### 3.2 Documentation Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `docs/architecture.md` | master architecture blueprint | business requirements | all docs, implementation planning |
| `docs/repository-structure.md` | target tree, file roles, and dependencies | `docs/architecture.md` | contributors, scaffolding work |
| `docs/decisions/adr-001-modular-monolith.md` | explains modular monolith choice | `docs/architecture.md` | implementation design decisions |
| `docs/decisions/adr-002-sqlalchemy-repository-pattern.md` | explains DB abstraction strategy | `docs/architecture.md`, `db/repositories/*` | DB implementation |
| `docs/decisions/adr-003-langgraph-migration-strategy.md` | explains orchestration migration plan | `docs/architecture.md`, `workflows/langgraph/*` | future LangGraph transition |
| `docs/diagrams/agent-interaction.mmd` | Mermaid source for agent flow diagram | `docs/architecture.md` | docs consumers |
| `docs/diagrams/deployment-architecture.mmd` | Mermaid source for deployment topology | `docs/architecture.md` | docs consumers |
| `docs/diagrams/docker-architecture.mmd` | Mermaid source for container layout | `docs/architecture.md`, `Dockerfile`, `docker-compose.yml` | docs consumers |
| `docs/runbooks/oauth-setup.md` | Gmail OAuth setup instructions | `integrations/gmail/auth.py`, `.env.example` | operators |
| `docs/runbooks/incident-response.md` | failure handling procedures | `scheduler/jobs.py`, `services/audit/audit_log_service.py`, logging config | operators |
| `docs/runbooks/production-operations.md` | deployment and support procedures | `Dockerfile`, `docker-compose.yml`, CI/CD workflows | operators |

### 3.3 Package Root and Configuration

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/__init__.py` | package marker and version surface | `pyproject.toml` | all package imports |
| `src/invoice_agent/config/settings.py` | environment-backed application settings | `.env.example`, Pydantic settings support | all runtime modules |
| `src/invoice_agent/config/logging.py` | structured logging configuration | `config/settings.py` | scheduler, services, API, dashboard |
| `src/invoice_agent/config/security.py` | secret handling, token encryption, security constants | `config/settings.py` | Gmail auth, Telegram, DB, API |

### 3.4 Domain Layer

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/domain/enums.py` | shared enums for statuses and classifications | none | entities, DB models, services, schemas |
| `src/invoice_agent/domain/entities/email_message.py` | domain model for inbound/outbound email | `domain/enums.py` | Gmail services, repositories, workflows |
| `src/invoice_agent/domain/entities/invoice.py` | domain model for invoice state and lifecycle | `domain/enums.py`, `value_objects/money.py` | extraction, matching, reminders |
| `src/invoice_agent/domain/entities/payment.py` | domain model for payment events | `domain/enums.py`, `value_objects/money.py` | payment parsing and matching |
| `src/invoice_agent/domain/entities/reminder.py` | domain model for reminder draft and approval flow | `domain/enums.py` | reminder generation, notification, API |
| `src/invoice_agent/domain/entities/audit_event.py` | domain model for immutable business events | `domain/enums.py` | audit service, repositories |
| `src/invoice_agent/domain/value_objects/money.py` | value object for amount and currency behavior | none | invoice, payment, matching, dashboard |
| `src/invoice_agent/domain/value_objects/due_window.py` | value object for due-date window calculations | none | due date services, reminder candidates |
| `src/invoice_agent/domain/value_objects/match_score.py` | value object for match confidence interpretation | none | payment matching services |

### 3.5 Schemas

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/schemas/email.py` | validated email ingestion and classification schemas | `domain/enums.py` | Gmail integration, workflows |
| `src/invoice_agent/schemas/invoice.py` | validated invoice extraction schemas | `domain/enums.py`, `value_objects/money.py` | extraction services, DB repositories |
| `src/invoice_agent/schemas/payment.py` | validated payment parsing and match schemas | `domain/enums.py`, `value_objects/money.py` | payment services, workflows |
| `src/invoice_agent/schemas/reminder.py` | reminder draft and approval schemas | `domain/enums.py` | reminder generation, notification, API |
| `src/invoice_agent/schemas/dashboard.py` | dashboard query/result schemas | `domain/enums.py` | dashboard services and Streamlit pages |

### 3.6 Gmail Integration Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/integrations/gmail/auth.py` | OAuth flow, token refresh, credential loading | `config/settings.py`, `config/security.py` | `client.py`, scripts, scheduler health checks |
| `src/invoice_agent/integrations/gmail/client.py` | low-level Gmail API wrapper | `auth.py`, `config/logging.py` | inbox reader, attachment downloader, draft sender |
| `src/invoice_agent/integrations/gmail/inbox_reader.py` | reads inbox messages and metadata | `client.py`, `schemas/email.py` | email ingestion service |
| `src/invoice_agent/integrations/gmail/attachment_downloader.py` | downloads and stores Gmail attachments | `client.py`, `utils/file_storage.py`, `utils/hashing.py` | extraction workflow |
| `src/invoice_agent/integrations/gmail/draft_sender.py` | creates drafts and sends approved reminders | `client.py`, `schemas/reminder.py` | reminder and approval workflows |

### 3.7 OpenAI Integration Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/integrations/openai/client.py` | low-level OpenAI API wrapper | `config/settings.py`, `config/logging.py` | structured extraction service |
| `src/invoice_agent/integrations/openai/structured_extraction.py` | prompt and schema-driven extraction adapter | `client.py`, `schemas/invoice.py` | extraction service |

### 3.8 Telegram Integration Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/integrations/telegram/bot_client.py` | low-level Telegram Bot API wrapper | `config/settings.py`, `config/logging.py` | approval notifier, notification service |
| `src/invoice_agent/integrations/telegram/approval_notifier.py` | formats and sends approval prompts | `bot_client.py`, `schemas/reminder.py` | notification service |

### 3.9 Database Core Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/db/base.py` | declarative ORM base and shared metadata | SQLAlchemy settings, `domain/enums.py` | all ORM model files |
| `src/invoice_agent/db/session.py` | engine/session factory for SQLite and PostgreSQL | `config/settings.py`, `config/security.py` | repositories, migrations, services |
| `src/invoice_agent/db/models/email_record.py` | ORM model for email messages and attachments | `db/base.py`, `domain/enums.py` | `repositories/emails.py`, related services |
| `src/invoice_agent/db/models/invoice_record.py` | ORM model for invoices and line items | `db/base.py`, `domain/enums.py` | `repositories/invoices.py`, dashboard, matching |
| `src/invoice_agent/db/models/payment_record.py` | ORM model for payments and payment matches | `db/base.py`, `domain/enums.py` | `repositories/payments.py`, reconciliation |
| `src/invoice_agent/db/models/reminder_record.py` | ORM model for reminder drafts and approvals | `db/base.py`, `domain/enums.py` | `repositories/reminders.py`, notification |
| `src/invoice_agent/db/models/audit_event_record.py` | ORM model for audit logs | `db/base.py`, `domain/enums.py` | `repositories/audits.py`, audit service |
| `src/invoice_agent/db/models/dashboard_snapshot_record.py` | ORM model for dashboard snapshots | `db/base.py` | dashboard snapshot service |
| `src/invoice_agent/db/repositories/emails.py` | email persistence and lookup queries | `db/session.py`, `models/email_record.py`, `schemas/email.py` | Gmail services, workflows |
| `src/invoice_agent/db/repositories/invoices.py` | invoice persistence and due-date queries | `db/session.py`, `models/invoice_record.py`, `schemas/invoice.py` | extraction, due date, dashboard |
| `src/invoice_agent/db/repositories/payments.py` | payment persistence and matching queries | `db/session.py`, `models/payment_record.py`, `schemas/payment.py` | payment services, workflows |
| `src/invoice_agent/db/repositories/reminders.py` | reminder persistence and approval status queries | `db/session.py`, `models/reminder_record.py`, `schemas/reminder.py` | reminder generation, notification, API |
| `src/invoice_agent/db/repositories/audits.py` | audit event persistence and retrieval | `db/session.py`, `models/audit_event_record.py` | audit service, dashboard audit page |
| `src/invoice_agent/db/migrations/` | database migration scripts directory | `alembic.ini`, `db/base.py`, `db/models/*` | deployment, CI |

### 3.10 Gmail Integration Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/gmail_integration/email_ingestion_service.py` | orchestrates email fetch, dedupe, persistence, and attachment capture | Gmail integration files, `repositories/emails.py`, `audit_log_service.py` | daily scan workflow |
| `src/invoice_agent/services/gmail_integration/email_classification_service.py` | classifies emails into invoice, payment, or irrelevant | `schemas/email.py`, `integrations/openai/client.py` optional, `domain/enums.py` | daily scan workflow |

### 3.11 Invoice Extraction Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/invoice_extraction/pdf_parser_service.py` | extracts raw text and metadata from PDF files | `utils/file_storage.py`, `config/logging.py` | extraction service |
| `src/invoice_agent/services/invoice_extraction/extraction_service.py` | converts PDFs into structured invoice objects | `pdf_parser_service.py`, `integrations/openai/structured_extraction.py`, `schemas/invoice.py`, `repositories/invoices.py` | daily scan workflow |
| `src/invoice_agent/services/invoice_extraction/validation_service.py` | validates required invoice fields and confidence thresholds | `schemas/invoice.py`, `domain/entities/invoice.py` | extraction service, workflows |

### 3.12 Payment Matching Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/payment_matching/payment_parser_service.py` | parses payment confirmation emails into structured payments | `schemas/payment.py`, `repositories/emails.py`, `integrations/openai/client.py` optional | reconciliation workflow |
| `src/invoice_agent/services/payment_matching/matching_service.py` | matches payments to invoices using deterministic and heuristic rules | `repositories/payments.py`, `repositories/invoices.py`, `value_objects/match_score.py` | reconciliation workflow |
| `src/invoice_agent/services/payment_matching/reconciliation_service.py` | updates invoice balances and payment statuses after matches | `matching_service.py`, `repositories/payments.py`, `repositories/invoices.py`, `audit_log_service.py` | reconciliation workflow, dashboard |

### 3.13 Due Date Monitoring Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/due_date_monitoring/due_date_service.py` | computes due-soon and overdue invoice states | `repositories/invoices.py`, `value_objects/due_window.py`, `utils/time.py` | reminder candidate service, dashboard |
| `src/invoice_agent/services/due_date_monitoring/reminder_candidate_service.py` | selects invoices eligible for reminder generation | `due_date_service.py`, `repositories/reminders.py`, `repositories/invoices.py` | reminder approval workflow |

### 3.14 Reminder Generation Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/reminder_generation/template_service.py` | stores and renders reminder templates | `schemas/reminder.py`, `domain/entities/invoice.py` | reminder draft service |
| `src/invoice_agent/services/reminder_generation/reminder_draft_service.py` | creates reminder draft records and email content | `template_service.py`, `repositories/reminders.py`, `integrations/gmail/draft_sender.py`, `audit_log_service.py` | reminder approval workflow |

### 3.15 Notification and Approval Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/notification/approval_service.py` | manages approve/reject decisions and send gating | `repositories/reminders.py`, `integrations/gmail/draft_sender.py`, `audit_log_service.py` | API approvals endpoint, reminder workflow |
| `src/invoice_agent/services/notification/notification_service.py` | delivers approval-needed notifications | `integrations/telegram/approval_notifier.py`, `repositories/reminders.py`, `audit_log_service.py` | reminder approval workflow |

### 3.16 Dashboard and Audit Services

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/services/dashboard/metrics_service.py` | calculates live dashboard aggregates | `repositories/invoices.py`, `repositories/payments.py`, `repositories/reminders.py`, `schemas/dashboard.py` | Streamlit pages, snapshots |
| `src/invoice_agent/services/dashboard/snapshot_service.py` | persists periodic metric snapshots | `metrics_service.py`, `models/dashboard_snapshot_record.py`, `db/session.py` | dashboard trends |
| `src/invoice_agent/services/audit/audit_log_service.py` | central audit writer and reader facade | `repositories/audits.py`, `config/logging.py`, `schemas/*` as needed | nearly all workflows and services |

### 3.17 Workflow Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/workflows/orchestration/daily_scan_workflow.py` | end-to-end 9:00 AM inbox scan and invoice processing flow | Gmail integration services, extraction services, audit service | scheduler jobs |
| `src/invoice_agent/workflows/orchestration/payment_reconciliation_workflow.py` | payment parsing and matching execution flow | payment matching services, audit service | scheduler jobs, manual admin triggers |
| `src/invoice_agent/workflows/orchestration/reminder_approval_workflow.py` | due-soon detection, draft generation, and notification flow | due date services, reminder services, notification services | scheduler jobs, API |
| `src/invoice_agent/workflows/langgraph/state.py` | shared LangGraph state contract | `schemas/*`, `domain/enums.py` | LangGraph nodes and builder |
| `src/invoice_agent/workflows/langgraph/nodes.py` | LangGraph node functions wrapping existing services | `state.py`, `services/*` | graph builder |
| `src/invoice_agent/workflows/langgraph/edges.py` | conditional edge definitions and routing rules | `state.py`, `nodes.py`, `domain/enums.py` | graph builder |
| `src/invoice_agent/workflows/langgraph/graph_builder.py` | assembles the final LangGraph workflow | `state.py`, `nodes.py`, `edges.py` | future orchestration entry points |

### 3.18 Scheduler Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/scheduler/jobs.py` | registers concrete scheduled jobs | orchestration workflows, `config/logging.py`, `audit_log_service.py` | bootstrap |
| `src/invoice_agent/scheduler/triggers.py` | defines cron and maintenance triggers | `config/settings.py`, APScheduler types | jobs, bootstrap |
| `src/invoice_agent/scheduler/bootstrap.py` | starts the scheduler runtime | `jobs.py`, `triggers.py`, `config/settings.py`, `config/logging.py` | Docker app/scheduler process |

### 3.19 Dashboard Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/dashboard/app.py` | Streamlit dashboard entry point | `config/settings.py`, `services/dashboard/metrics_service.py` | dashboard pages |
| `src/invoice_agent/dashboard/pages/1_overview.py` | summary dashboard page | `app.py`, `metrics_service.py`, `snapshot_service.py` | end users |
| `src/invoice_agent/dashboard/pages/2_invoices.py` | invoice list and due status page | `app.py`, `repositories/invoices.py`, `schemas/dashboard.py` | end users |
| `src/invoice_agent/dashboard/pages/3_payments.py` | payment status and match review page | `app.py`, `repositories/payments.py`, `schemas/dashboard.py` | end users |
| `src/invoice_agent/dashboard/pages/4_reminders.py` | reminder queue and approval status page | `app.py`, `repositories/reminders.py`, `schemas/reminder.py` | end users |
| `src/invoice_agent/dashboard/pages/5_audit_logs.py` | audit event inspection page | `app.py`, `repositories/audits.py` | end users |
| `src/invoice_agent/dashboard/components/` | reusable UI widgets, filters, and cards | `dashboard/app.py`, `pages/*`, `schemas/dashboard.py` | all dashboard pages |

### 3.20 API Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/api/health.py` | health and readiness endpoints | `db/session.py`, Gmail auth, scheduler status, `config/logging.py` | load balancers, CI smoke tests |
| `src/invoice_agent/api/approvals.py` | approve/reject reminder actions | `services/notification/approval_service.py`, `schemas/reminder.py`, `repositories/reminders.py` | Telegram callbacks, dashboard actions |
| `src/invoice_agent/api/webhooks.py` | optional webhook endpoints for callbacks and integrations | `services/notification/approval_service.py`, `config/security.py` | Telegram or future integrations |

### 3.21 Utility Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `src/invoice_agent/utils/time.py` | timezone normalization and date helpers | `config/settings.py` | due date services, scheduler, dashboards |
| `src/invoice_agent/utils/idempotency.py` | idempotency key generation and duplicate protection helpers | `utils/hashing.py` | ingestion, scheduler, reminders |
| `src/invoice_agent/utils/hashing.py` | checksums for attachments and message identity | standard hashing libraries | Gmail downloader, storage, idempotency |
| `src/invoice_agent/utils/file_storage.py` | safe filesystem path handling and artifact persistence | `config/settings.py`, `utils/hashing.py` | Gmail downloader, PDF parser, scripts |

### 3.22 Scripts

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `scripts/bootstrap_local.sh` | local environment setup helper | `.env.example`, `pyproject.toml`, `docker-compose.yml` | developers |
| `scripts/seed_demo_data.py` | creates demo invoices/payments for dashboard testing | `db/session.py`, `db/models/*`, `schemas/*` | local demos, tests |
| `scripts/rotate_tokens.py` | controlled token rotation utility | `integrations/gmail/auth.py`, `config/security.py`, `db/repositories/*` | operations |

### 3.23 GitHub Workflow Files

| File | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `.github/workflows/ci.yml` | lint, type-check, and test pipeline | `pyproject.toml`, `tests/`, `src/` | pull requests, main branch |
| `.github/workflows/docker.yml` | Docker image build and validation pipeline | `Dockerfile`, `docker-compose.yml`, `pyproject.toml` | release readiness |
| `.github/workflows/release.yml` | tagged build and deployment workflow | CI outputs, Docker image, deployment secrets | staging/production delivery |

### 3.24 Test and Storage Directories

| Path | Purpose | Direct Dependencies | Downstream Dependents |
|---|---|---|---|
| `tests/unit/` | isolated tests for small modules | source modules under `src/invoice_agent` | CI |
| `tests/integration/` | end-to-end module interaction tests | `db`, `integrations`, `services`, Docker/SQLite/PostgreSQL | CI, release confidence |
| `tests/contract/` | stable interface tests for migration-safe contracts | `schemas/*`, `services/*`, `workflows/langgraph/*` | LangGraph migration safety |
| `tests/fixtures/` | sample emails, PDFs, payments, and DB fixtures | tests and schemas | all test suites |
| `storage/raw_emails/` | archived raw email bodies or provider payloads | Gmail ingestion, file storage utils | audit, debugging |
| `storage/attachments/` | stored invoice PDFs and related files | Gmail attachment downloader, PDF parser | extraction workflows |
| `storage/exports/` | generated exports and operational reports | dashboard export features, scripts | end users, operations |

---

## 4. High-Level Dependency Flow

```text
Root Config
  -> config/*
  -> db/session.py
  -> Docker/CI

config/*
  -> integrations/*
  -> db/*
  -> services/*
  -> scheduler/*
  -> api/*
  -> dashboard/*

domain/*
  -> schemas/*
  -> db/models/*
  -> services/*

schemas/*
  -> integrations/*
  -> services/*
  -> workflows/*
  -> api/*
  -> dashboard/*

integrations/*
  -> services/*

db/models/*
  -> db/repositories/*
  -> services/*
  -> dashboard/*

db/repositories/*
  -> services/*
  -> workflows/*
  -> api/*
  -> dashboard/*

services/*
  -> workflows/orchestration/*
  -> workflows/langgraph/nodes.py
  -> scheduler/jobs.py
  -> api/*
  -> dashboard/*

workflows/orchestration/*
  -> scheduler/jobs.py

workflows/langgraph/*
  -> future workflow runtime entrypoints

scheduler/*
  -> Docker runtime

api/*
  -> dashboard actions
  -> Telegram callbacks

dashboard/*
  -> end users
```

---

## 5. Repository Construction Order

To physically create this repository later without adding implementation logic yet, create files in this order:

1. root files
2. documentation files
3. package root and config
4. domain and schemas
5. DB base/session/models
6. repositories
7. integrations
8. services
9. workflows
10. scheduler
11. dashboard
12. API
13. utils
14. scripts
15. tests and fixtures

This order respects the declared dependency graph and avoids forward-reference confusion during scaffolding.
