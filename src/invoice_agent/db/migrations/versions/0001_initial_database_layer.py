"""Initial database layer

Revision ID: 0001_initial_database_layer
Revises:
Create Date: 2026-06-21 08:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial_database_layer"
down_revision = None
branch_labels = None
depends_on = None


user_role_enum = sa.Enum("admin", "finance", "viewer", "system", name="user_role_enum")
invoice_status_enum = sa.Enum(
    "draft",
    "open",
    "partially_paid",
    "paid",
    "overdue",
    "cancelled",
    "disputed",
    name="invoice_status_enum",
)
payment_status_enum = sa.Enum(
    "received",
    "matched",
    "partially_matched",
    "unmatched",
    "failed",
    "reversed",
    name="payment_status_enum",
)
email_direction_enum = sa.Enum("inbound", "outbound", name="email_direction_enum")
email_type_enum = sa.Enum(
    "invoice",
    "payment_confirmation",
    "reminder",
    "system",
    "other",
    name="email_type_enum",
)
email_processing_status_enum = sa.Enum(
    "pending",
    "processed",
    "failed",
    "skipped",
    name="email_processing_status_enum",
)
draft_status_enum = sa.Enum(
    "pending_approval",
    "approved",
    "rejected",
    "sent",
    "failed",
    "expired",
    name="draft_status_enum",
)
audit_status_enum = sa.Enum("success", "failure", "info", name="audit_status_enum")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("telegram_chat_id", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "clients",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("tax_id", sa.String(length=128), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        sa.UniqueConstraint("name", name=op.f("uq_clients_name")),
    )
    op.create_index(op.f("ix_clients_name"), "clients", ["name"], unique=True)
    op.create_index(op.f("ix_clients_email"), "clients", ["email"], unique=False)
    op.create_index(op.f("ix_clients_tax_id"), "clients", ["tax_id"], unique=False)

    op.create_table(
        "invoices",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=128), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("subtotal_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=18, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("balance_due", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status", invoice_status_enum, nullable=False, server_default=sa.text("'open'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("amount_paid >= 0", name=op.f("ck_invoices_amount_paid_non_negative")),
        sa.CheckConstraint("balance_due >= 0", name=op.f("ck_invoices_balance_due_non_negative")),
        sa.CheckConstraint("subtotal_amount >= 0", name=op.f("ck_invoices_subtotal_amount_non_negative")),
        sa.CheckConstraint("tax_amount >= 0", name=op.f("ck_invoices_tax_amount_non_negative")),
        sa.CheckConstraint("total_amount >= 0", name=op.f("ck_invoices_total_amount_non_negative")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_invoices_client_id_clients"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("client_id", "invoice_number", name="uq_invoices_client_invoice_number"),
    )
    op.create_index(op.f("ix_invoices_client_id"), "invoices", ["client_id"], unique=False)
    op.create_index(op.f("ix_invoices_due_date"), "invoices", ["due_date"], unique=False)
    op.create_index("ix_invoices_due_date_status", "invoices", ["due_date", "status"], unique=False)
    op.create_index(op.f("ix_invoices_invoice_number"), "invoices", ["invoice_number"], unique=False)
    op.create_index(op.f("ix_invoices_issue_date"), "invoices", ["issue_date"], unique=False)

    op.create_table(
        "payments",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("payment_reference", sa.String(length=128), nullable=True),
        sa.Column("transaction_reference", sa.String(length=128), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=64), nullable=True),
        sa.Column("status", payment_status_enum, nullable=False, server_default=sa.text("'received'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_payment_amount_positive")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_payments_client_id_clients"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name=op.f("fk_payments_invoice_id_invoices"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(op.f("ix_payments_client_id"), "payments", ["client_id"], unique=False)
    op.create_index(op.f("ix_payments_invoice_id"), "payments", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_payments_payment_date"), "payments", ["payment_date"], unique=False)
    op.create_index("ix_payments_date_status", "payments", ["payment_date", "status"], unique=False)
    op.create_index("ix_payments_reference", "payments", ["payment_reference"], unique=False)
    op.create_index("ix_payments_transaction_reference", "payments", ["transaction_reference"], unique=False)

    op.create_table(
        "drafts",
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default=sa.text("'email'")),
        sa.Column("status", draft_status_enum, nullable=False, server_default=sa.text("'pending_approval'")),
        sa.Column("approval_notes", sa.Text(), nullable=True),
        sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_draft_id", sa.String(length=255), nullable=True),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], name=op.f("fk_drafts_approved_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_drafts_client_id_clients"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_drafts_created_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name=op.f("fk_drafts_invoice_id_invoices"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drafts")),
    )
    op.create_index(op.f("ix_drafts_client_id"), "drafts", ["client_id"], unique=False)
    op.create_index(op.f("ix_drafts_invoice_id"), "drafts", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_drafts_created_by_user_id"), "drafts", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_drafts_approved_by_user_id"), "drafts", ["approved_by_user_id"], unique=False)
    op.create_index(op.f("ix_drafts_external_draft_id"), "drafts", ["external_draft_id"], unique=False)
    op.create_index(op.f("ix_drafts_external_message_id"), "drafts", ["external_message_id"], unique=False)
    op.create_index("ix_drafts_status_sent_at", "drafts", ["status", "sent_at"], unique=False)
    op.create_index("ix_drafts_invoice_status", "drafts", ["invoice_id", "status"], unique=False)

    op.create_table(
        "email_logs",
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=True),
        sa.Column("thread_id", sa.String(length=255), nullable=True),
        sa.Column("internet_message_id", sa.String(length=255), nullable=True),
        sa.Column("sender", sa.String(length=255), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("cc_recipients", sa.JSON(), nullable=False),
        sa.Column("bcc_recipients", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("direction", email_direction_enum, nullable=False),
        sa.Column("email_type", email_type_enum, nullable=False, server_default=sa.text("'other'")),
        sa.Column("processing_status", email_processing_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("attachment_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attachment_paths", sa.JSON(), nullable=False),
        sa.Column("attachment_metadata", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_email_logs_client_id_clients"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], name=op.f("fk_email_logs_draft_id_drafts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], name=op.f("fk_email_logs_invoice_id_invoices"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], name=op.f("fk_email_logs_payment_id_payments"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_logs")),
        sa.UniqueConstraint("gmail_message_id", name="uq_email_logs_gmail_message_id"),
    )
    op.create_index(op.f("ix_email_logs_client_id"), "email_logs", ["client_id"], unique=False)
    op.create_index(op.f("ix_email_logs_invoice_id"), "email_logs", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_email_logs_payment_id"), "email_logs", ["payment_id"], unique=False)
    op.create_index(op.f("ix_email_logs_draft_id"), "email_logs", ["draft_id"], unique=False)
    op.create_index(op.f("ix_email_logs_received_at"), "email_logs", ["received_at"], unique=False)
    op.create_index("ix_email_logs_received_type", "email_logs", ["received_at", "email_type"], unique=False)
    op.create_index(op.f("ix_email_logs_sender"), "email_logs", ["sender"], unique=False)
    op.create_index(op.f("ix_email_logs_subject"), "email_logs", ["subject"], unique=False)
    op.create_index(op.f("ix_email_logs_thread_id"), "email_logs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_email_logs_internet_message_id"), "email_logs", ["internet_message_id"], unique=False)
    op.create_index("ix_email_logs_processing_status", "email_logs", ["processing_status"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("status", audit_status_enum, nullable=False, server_default=sa.text("'info'")),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_audit_logs_actor_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_request_id"), "audit_logs", ["request_id"], unique=False)
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_audit_logs_created_action", "audit_logs", ["created_at", "action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_email_logs_processing_status", table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_internet_message_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_thread_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_subject"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_sender"), table_name="email_logs")
    op.drop_index("ix_email_logs_received_type", table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_received_at"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_draft_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_payment_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_invoice_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_client_id"), table_name="email_logs")
    op.drop_table("email_logs")

    op.drop_index("ix_drafts_invoice_status", table_name="drafts")
    op.drop_index("ix_drafts_status_sent_at", table_name="drafts")
    op.drop_index(op.f("ix_drafts_external_message_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_external_draft_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_approved_by_user_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_created_by_user_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_invoice_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_client_id"), table_name="drafts")
    op.drop_table("drafts")

    op.drop_index("ix_payments_transaction_reference", table_name="payments")
    op.drop_index("ix_payments_reference", table_name="payments")
    op.drop_index("ix_payments_date_status", table_name="payments")
    op.drop_index(op.f("ix_payments_payment_date"), table_name="payments")
    op.drop_index(op.f("ix_payments_invoice_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_client_id"), table_name="payments")
    op.drop_table("payments")

    op.drop_index(op.f("ix_invoices_issue_date"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_invoice_number"), table_name="invoices")
    op.drop_index("ix_invoices_due_date_status", table_name="invoices")
    op.drop_index(op.f("ix_invoices_due_date"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_client_id"), table_name="invoices")
    op.drop_table("invoices")

    op.drop_index(op.f("ix_clients_tax_id"), table_name="clients")
    op.drop_index(op.f("ix_clients_email"), table_name="clients")
    op.drop_index(op.f("ix_clients_name"), table_name="clients")
    op.drop_table("clients")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        audit_status_enum.drop(bind, checkfirst=True)
        draft_status_enum.drop(bind, checkfirst=True)
        email_processing_status_enum.drop(bind, checkfirst=True)
        email_type_enum.drop(bind, checkfirst=True)
        email_direction_enum.drop(bind, checkfirst=True)
        payment_status_enum.drop(bind, checkfirst=True)
        invoice_status_enum.drop(bind, checkfirst=True)
        user_role_enum.drop(bind, checkfirst=True)
