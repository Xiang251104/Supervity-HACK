"""Add AP Control Tower tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6g7h8
Create Date: 2026-08-01 12:00:00.000000

Creates the nine tables behind the Command Center and seeds the five starting
policies. Policy keys deliberately match the dataset's own POLICY_REF vocabulary
(DOA-BAND, PRICE-TOLERANCE, BANK-CHANGE-FREEZE, ...) so decisions can be checked
against Approval_Log.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6g7h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------- policies
    op.create_table(
        "ap_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="number"),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="escalate"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_ap_policies_key"), "ap_policies", ["key"])
    op.create_index(op.f("ix_ap_policies_active"), "ap_policies", ["active"])

    op.create_table(
        "ap_policy_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_key", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("changed_by", sa.String(length=255), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_key", "version", name="uq_policy_version"),
    )
    op.create_index(op.f("ix_ap_policy_versions_policy_key"), "ap_policy_versions", ["policy_key"])

    # -------------------------------------------------------------------- runs
    op.create_table(
        "ap_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("invoice_ref", sa.String(length=64), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=True),
        sa.Column("workflow_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("trigger_source", sa.String(length=50), nullable=False, server_default="api"),
        sa.Column("policy_version_label", sa.String(length=64), nullable=True),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    for col in ("run_id", "invoice_ref", "workflow_run_id", "status", "started_at",
                "policy_version_label"):
        op.create_index(op.f(f"ix_ap_runs_{col}"), "ap_runs", [col])

    op.create_table(
        "ap_run_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("operator_name", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ap_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("run_id", "event_type", "operator_name", "ts"):
        op.create_index(op.f(f"ix_ap_run_events_{col}"), "ap_run_events", [col])

    # --------------------------------------------------------------- decisions
    op.create_table(
        "ap_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("belnr", sa.String(length=32), nullable=False),
        sa.Column("lifnr", sa.String(length=32), nullable=True),
        sa.Column("ebeln", sa.String(length=32), nullable=True),
        sa.Column("vendor_name", sa.String(length=255), nullable=True),
        sa.Column("bukrs", sa.String(length=10), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("amount_myr", sa.Float(), nullable=True),
        sa.Column("fx_rate", sa.Float(), nullable=True),
        sa.Column("fx_rate_date", sa.String(length=20), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("money_protected", sa.Float(), nullable=False, server_default="0"),
        sa.Column("spend_under_review", sa.Float(), nullable=False, server_default="0"),
        sa.Column("policy_version_label", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("human_status", sa.String(length=30), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_action", sa.String(length=30), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="auto_run"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ap_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("run_id", "belnr", "lifnr", "ebeln", "bukrs", "verdict",
                "policy_version_label", "human_status", "source", "created_at"):
        op.create_index(op.f(f"ix_ap_decisions_{col}"), "ap_decisions", [col])

    op.create_table(
        "ap_policy_evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("belnr", sa.String(length=32), nullable=True),
        sa.Column("policy_key", sa.String(length=50), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("threshold_value", sa.JSON(), nullable=True),
        sa.Column("observed_value", sa.JSON(), nullable=True),
        sa.Column("fired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["ap_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("run_id", "belnr", "policy_key", "fired", "evaluated_at"):
        op.create_index(op.f(f"ix_ap_policy_evaluations_{col}"), "ap_policy_evaluations", [col])

    # --------------------------------------------------------------- workbench
    op.create_table(
        "ap_workbench_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("belnr", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("exception_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("assigned_role", sa.String(length=80), nullable=True),
        sa.Column("assigned_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["ap_runs.run_id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["ap_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("run_id", "decision_id", "belnr", "exception_type", "priority",
                "status", "created_at"):
        op.create_index(op.f(f"ix_ap_workbench_items_{col}"), "ap_workbench_items", [col])

    # ------------------------------------------------ insights & integrations
    op.create_table(
        "ap_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_unit", sa.String(length=20), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("action_label", sa.String(length=120), nullable=True),
        sa.Column("action_type", sa.String(length=50), nullable=True),
        sa.Column("action_payload", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("key", "severity", "computed_at"):
        op.create_index(op.f(f"ix_ap_insights_{col}"), "ap_insights", [col])

    op.create_table(
        "ap_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_ap_integrations_key"), "ap_integrations", ["key"])
    op.create_index(op.f("ix_ap_integrations_category"), "ap_integrations", ["category"])
    op.create_index(op.f("ix_ap_integrations_status"), "ap_integrations", ["status"])

    _seed()


def _seed() -> None:
    """Seed the five starting policies and the integration registry."""
    op.execute(
        """
        INSERT INTO ap_policies (key, name, description, value_type, value, options, unit,
                                 severity, active, version, updated_by) VALUES
        ('PRICE-TOLERANCE',
         'PO price tolerance',
         'How far an invoice amount may differ from a matched PO line before it is treated as a price variance.',
         'number', '2'::json, NULL, '%', 'escalate', true, 1, 'system'),

        ('BANK-CHANGE-FREEZE',
         'Bank change freeze window',
         'Days after a vendor bank change during which a payment is frozen pending out-of-band verification.',
         'number', '30'::json, NULL, 'days', 'block', true, 1, 'system'),

        ('DOA-BAND',
         'Auto-pay limit',
         'Invoices at or below this amount (MYR) may clear without a delegated approver. Above it, the DOA band applies.',
         'number', '5000'::json, NULL, 'MYR', 'escalate', true, 1, 'system'),

        ('GR-POLICY',
         'Goods receipt requirement',
         'strict_require_gr holds every invoice without a goods receipt. fo_aware exempts framework (BSART=FO) orders.',
         'enum', '"fo_aware"'::json, '["strict_require_gr","fo_aware"]'::json, NULL,
         'escalate', true, 1, 'system'),

        ('RETRO-PO',
         'Retroactive PO handling',
         'advisory records a retroactive or out-of-validity PO without holding payment. review escalates it to a human.',
         'enum', '"advisory"'::json, '["advisory","review"]'::json, NULL,
         'advise', true, 1, 'system'),

        ('MIN-CONFIDENCE',
         'Minimum extraction confidence',
         'Invoices extracted below this confidence are routed to a human rather than auto-cleared.',
         'number', '0.70'::json, NULL, NULL, 'escalate', true, 1, 'system'),

        ('AS-OF-DATE',
         'Operational as-of date',
         'The date all ageing, discount and FX calculations are measured against. Keeps date-relative metrics reproducible.',
         'date', '"2026-07-15"'::json, NULL, NULL, 'advise', true, 1, 'system'),

        ('HIGH-VALUE-THRESHOLD',
         'High-value invoice threshold',
         'Amount (MYR) above which an invoice counts as high value. Used as the fourth fraud signal in bank-change verification.',
         'number', '500000'::json, NULL, 'MYR', 'escalate', true, 1, 'system'),

        ('NEAR-DUP-TOLERANCE',
         'Near-duplicate amount tolerance',
         'How far two amounts may differ and still be treated as the same invoice re-submitted through another channel.',
         'number', '0.1'::json, NULL, '%', 'escalate', true, 1, 'system'),

        ('DEFAULT-KOSTL',
         'Default cost centre',
         'Cost centre used to select a delegation-of-authority band when the invoice does not carry one.',
         'enum', '"CC100"'::json, '["CC100","CC200"]'::json, NULL, 'advise', true, 1, 'system')
        """
    )
    op.execute(
        """
        INSERT INTO ap_policy_versions (policy_key, version, value, changed_by, note)
        SELECT key, 1, value, 'system', 'Initial seed' FROM ap_policies
        """
    )
    op.execute(
        """
        INSERT INTO ap_integrations (key, name, category, purpose, status) VALUES
        ('outlook',  'Microsoft Outlook', 'channel',
         'Invoice intake inbox. Invoices arrive here and trigger a run.', 'unknown'),
        ('supabase', 'Supabase Postgres', 'system_of_record',
         'AP system of record: vendors, purchase orders, goods receipts, invoices, banks, FX.', 'unknown'),
        ('slack',    'Slack',             'channel',
         'Exception alerts to the AP team. Bank details are always redacted.', 'unknown'),
        ('supervity','Supervity Auto',    'agent_platform',
         'Runs the Orchestrator and the five Operator Agents.', 'unknown')
        """
    )


def downgrade() -> None:
    for t in ("ap_integrations", "ap_insights", "ap_workbench_items",
              "ap_policy_evaluations", "ap_decisions", "ap_run_events",
              "ap_runs", "ap_policy_versions", "ap_policies"):
        op.drop_table(t)
