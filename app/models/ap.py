# app/models/ap.py
"""AP Control Tower data model.

Nine tables behind the Command Center:

  ap_policies / ap_policy_versions   the rules a business owns, and their history
  ap_runs / ap_run_events            one Orchestrator execution and its live step stream
  ap_decisions                       the immutable AI verdict, plus a separate human resolution
  ap_policy_evaluations              every policy evaluation, logged for audit
  ap_workbench_items                 the human queue
  ap_insights                        computed observations with a severity and an action
  ap_integrations                    the Data Manager registry and health

Two rules encoded here on purpose:

1. The AI verdict is immutable. A human resolution is written to separate columns on
   ap_decisions and never overwrites verdict / reason_codes / evidence.
2. Every decision row carries `source`. Rows backfilled from the oracle for development
   are marked `oracle_backfill` and MUST be purged before submission — shipping computed
   demo data as agent output is a disqualifying offence.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from ..core.database import Base

# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


class Policy(Base):
    """One editable business rule. Key matches the dataset's own POLICY_REF vocabulary."""

    __tablename__ = "ap_policies"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")

    # value_type drives the input control the Policies UI renders
    value_type = Column(String(20), nullable=False, default="number")  # number|enum|boolean|date
    value = Column(JSON, nullable=False)
    options = Column(JSON, nullable=True)  # allowed values when value_type == "enum"
    unit = Column(String(20), nullable=True)  # "%", "days", "MYR"

    severity = Column(String(20), nullable=False, default="escalate")  # block|escalate|advise
    active = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(255), nullable=True)


class PolicyVersion(Base):
    """Append-only history. One row per change, so any decision can be replayed."""

    __tablename__ = "ap_policy_versions"
    __table_args__ = (UniqueConstraint("policy_key", "version", name="uq_policy_version"),)

    id = Column(Integer, primary_key=True, index=True)
    policy_key = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    value = Column(JSON, nullable=False)
    previous_value = Column(JSON, nullable=True)
    changed_by = Column(String(255), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    note = Column(Text, nullable=True)


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #


class Run(Base):
    """One execution of the Auto Orchestrator."""

    __tablename__ = "ap_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    invoice_ref = Column(String(64), nullable=True, index=True)

    # Supervity's own run identifier, so a judge can cross-check in the Auto Audit Trail
    workflow_run_id = Column(String(128), nullable=True, index=True)
    workflow_id = Column(String(128), nullable=True)

    status = Column(String(20), nullable=False, default="queued", index=True)
    trigger_source = Column(String(50), nullable=False, default="api")  # api|outlook|batch|rerun

    # exactly what was sent to Auto — this is what makes a decision reproducible
    policy_version_label = Column(String(64), nullable=True, index=True)
    policy_snapshot = Column(JSON, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)


class RunEvent(Base):
    """A single SSE frame from Auto. This is what makes the dashboard move live."""

    __tablename__ = "ap_run_events"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), ForeignKey("ap_runs.run_id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)

    event_type = Column(String(64), nullable=False, index=True)
    operator_name = Column(String(120), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #


class Decision(Base):
    """The AI verdict for one invoice. Immutable — human resolution lives in its own columns."""

    __tablename__ = "ap_decisions"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), ForeignKey("ap_runs.run_id"), nullable=False, index=True)

    belnr = Column(String(32), nullable=False, index=True)
    lifnr = Column(String(32), nullable=True, index=True)
    ebeln = Column(String(32), nullable=True, index=True)
    vendor_name = Column(String(255), nullable=True)
    bukrs = Column(String(10), nullable=True, index=True)

    currency = Column(String(8), nullable=True)
    amount = Column(Float, nullable=True)
    amount_myr = Column(Float, nullable=True)
    fx_rate = Column(Float, nullable=True)
    fx_rate_date = Column(String(20), nullable=True)

    # ---- immutable AI verdict ----
    verdict = Column(String(20), nullable=False, index=True)  # PAY_READY|HUMAN_REVIEW|PAYMENT_HOLD|DATA_ERROR
    reason_codes = Column(JSON, nullable=False, default=list)
    evidence = Column(JSON, nullable=True)  # keyed per Operator
    money_protected = Column(Float, nullable=False, default=0.0)
    spend_under_review = Column(Float, nullable=False, default=0.0)
    policy_version_label = Column(String(64), nullable=True, index=True)
    confidence = Column(Float, nullable=True)

    # ---- human resolution, written separately, never overwrites the above ----
    human_status = Column(String(30), nullable=True, index=True)
    resolved_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_action = Column(String(30), nullable=True)  # approve|reject|modify|request_info
    resolution_note = Column(Text, nullable=True)

    # ---- integrity ----
    # "auto_run" = produced by a real Auto execution.
    # "oracle_backfill" = computed locally for development ONLY. Purge before submission.
    source = Column(String(30), nullable=False, default="auto_run", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class PolicyEvaluation(Base):
    """Every policy evaluated on every run — fired or not. Required for auditability."""

    __tablename__ = "ap_policy_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), ForeignKey("ap_runs.run_id"), nullable=False, index=True)
    belnr = Column(String(32), nullable=True, index=True)

    policy_key = Column(String(50), nullable=False, index=True)
    policy_version = Column(Integer, nullable=False)
    threshold_value = Column(JSON, nullable=True)
    observed_value = Column(JSON, nullable=True)

    fired = Column(Boolean, nullable=False, default=False, index=True)
    # delegated = applied by an Operator from the snapshot, not decided by the gate
    outcome = Column(String(30), nullable=True)  # allow|hold|escalate|advise|delegated
    explanation = Column(Text, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# --------------------------------------------------------------------------- #
# Workbench
# --------------------------------------------------------------------------- #


class WorkbenchItem(Base):
    """One exception awaiting a human. Arrives with full context and a recommendation."""

    __tablename__ = "ap_workbench_items"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(64), ForeignKey("ap_runs.run_id"), nullable=False, index=True)
    decision_id = Column(Integer, ForeignKey("ap_decisions.id"), nullable=True, index=True)
    belnr = Column(String(32), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    exception_type = Column(String(50), nullable=False, index=True)  # the primary reason code
    priority = Column(String(20), nullable=False, default="normal", index=True)  # critical|high|normal
    recommendation = Column(Text, nullable=True)
    context = Column(JSON, nullable=True)  # everything the reviewer needs, no lookups required

    assigned_role = Column(String(80), nullable=True)
    assigned_email = Column(String(255), nullable=True)

    status = Column(String(20), nullable=False, default="open", index=True)  # open|resolved
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    action = Column(String(30), nullable=True)
    note = Column(Text, nullable=True)


# --------------------------------------------------------------------------- #
# Insights and integrations
# --------------------------------------------------------------------------- #


class Insight(Base):
    """A computed observation. Must carry a severity and end in an action path."""

    __tablename__ = "ap_insights"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(80), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    severity = Column(String(20), nullable=False, default="info", index=True)  # critical|warning|info
    body = Column(Text, nullable=False)

    metric_value = Column(Float, nullable=True)
    metric_unit = Column(String(20), nullable=True)
    evidence = Column(JSON, nullable=True)  # the rows behind it, so it can be verified

    action_label = Column(String(120), nullable=True)
    action_type = Column(String(50), nullable=True)  # create_policy|open_workbench|rerun|investigate
    action_payload = Column(JSON, nullable=True)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    dismissed = Column(Boolean, nullable=False, default=False)


class Integration(Base):
    """The Data Manager registry. Health is measured, never hardcoded."""

    __tablename__ = "ap_integrations"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # channel|system_of_record|agent_platform|document_store
    purpose = Column(Text, nullable=False, default="")

    status = Column(String(20), nullable=False, default="unknown", index=True)  # healthy|degraded|down|unknown
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    detail = Column(JSON, nullable=True)
    last_error = Column(Text, nullable=True)

    # proves the integration actually carries data rather than merely being connected
    records_seen = Column(Integer, nullable=False, default=0)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
