# app/services/supervity.py
"""Client for the Supervity Auto workflow API.

This is the only place the backend talks to Auto. Everything else works off the
rows this writes.

Endpoint facts, verified by probing the live API on 2026-08-08 (the published
docs were wrong on two counts — see the warnings below):

  POST /api/v1/workflow-runs/execute/stream   run a workflow, SSE response
  POST /api/v1/workflow-runs/execute          same, blocking
  GET  /api/v1/workflow-runs/:runId           one run with activity detail
  GET  /api/v1/workflow-runs                  list / filter
  POST /api/v1/workflow-runs/cancel           cancel

  Headers   Authorization: Bearer <workflow api key>
            x-source: external
            x-active-org: <org key>

  *** The API host is auto-workflow-api.supervity.ai, NOT auto.supervity.ai. ***
  auto.supervity.ai is the Remix web app. It answers /api/v1/* with a generic
  400 {"message":"Unexpected Server Error"} and header `x-remix-error: yes` --
  and it does so whether or not you send credentials, so a wrong host looks
  exactly like a broken key. Confirmed by the app's own CSP connect-src.

  *** execute takes multipart/form-data, and `inputs` is a RECORD, not a blob. ***
  Each input is its own bracketed field: inputs[invoice_ref], inputs[run_id], ...
  Sending `inputs` as one JSON string is rejected with
  "expected record, received string". Sending a JSON body hangs and never
  starts a run. Values are strings; objects must be JSON-serialized per field.

  *** Rate limit is 1000 requests/minute per IP (ratelimit-policy: 1000;w=60). ***

Operator results do NOT appear in the parent run. Each Operator step is a
subworkflow call whose `output` is an empty string; the real §B1 contract lives
in the child run, reachable only through the link in displayData.html.
`collect_run_outputs` walks those links -- see it for the full explanation.

The SSE payload shape is not contractual, so parsing here is deliberately
loose: we normalize the fields we recognise and always keep the raw frame in
`payload` so nothing is lost if the shape differs from what we expect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://auto-workflow-api.supervity.ai"
EXECUTE_STREAM = "/api/v1/workflow-runs/execute/stream"
EXECUTE = "/api/v1/workflow-runs/execute"
GET_RUN = "/api/v1/workflow-runs/{run_id}"
LIST_RUNS = "/api/v1/workflow-runs"
CANCEL = "/api/v1/workflow-runs/cancel"

# Orchestrator step id -> the Operator result key the Command Center stores.
# Keyed on step id rather than step name because a rename in the Auto builder
# must not silently drop an Operator's evidence.
STEP_TO_OPERATOR_KEY = {
    "step_intake": "intake_result",
    "step_duplicate_screen": "duplicate_result",
    "step_bank_screen": "bank_result",
    "step_po_resolver": "po_entity_result",
    "step_three_way_match": "match_result",
    "step_entity_approval": "entity_result",
}

# The child run id inside a subworkflow step's displayData link.
_SUBWORKFLOW_RUN = re.compile(r"/runs/([0-9a-fA-F-]{8}-[0-9a-fA-F-]{27})")

# Live `activity-run` frames identify a step only by id — no display name — so the
# Command Center's activity feed would otherwise show a column of blanks.
STEP_DISPLAY_NAMES = {
    "step_intake": "AP - Intake and Normalize",
    "step_duplicate_screen": "AP - Duplicate and Fraud Screen",
    "step_bank_screen": "AP - Bank Change Verification",
    "step_po_resolver": "AP - PO Entity Resolver",
    "step_three_way_match": "AP - Three Way Match",
    "step_entity_approval": "AP - Entity and Approval Control",
    "step_decide_verdict": "Decide Verdict",
    "step_send_slack_alert": "Send Slack Alert",
}


class SupervityError(RuntimeError):
    """Any failure talking to Auto."""


class SupervityNotConfigured(SupervityError):
    """Credentials are missing. Raised early so the cause is obvious."""


@dataclass
class SupervityConfig:
    api_key: str
    active_org: str
    base_url: str = DEFAULT_BASE_URL
    orchestrator_workflow_id: str = ""
    timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> "SupervityConfig":
        return cls(
            api_key=os.getenv("SUPERVITY_API_KEY", "").strip(),
            active_org=os.getenv("SUPERVITY_ACTIVE_ORG", "").strip(),
            base_url=os.getenv("SUPERVITY_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            orchestrator_workflow_id=os.getenv("SUPERVITY_ORCHESTRATOR_WORKFLOW_ID", "").strip(),
            timeout_seconds=float(os.getenv("SUPERVITY_TIMEOUT_SECONDS", "300")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.active_org)

    def headers(self) -> dict[str, str]:
        if not self.configured:
            raise SupervityNotConfigured(
                "SUPERVITY_API_KEY and SUPERVITY_ACTIVE_ORG must be set in .env. "
                "Generate the key at https://auto.supervity.ai/u/api-keys"
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "x-source": "external",
            "x-active-org": self.active_org,
            "Accept": "text/event-stream",
        }


@dataclass
class AutoEvent:
    """One normalized SSE frame."""

    seq: int
    event_type: str           # normalized: activity | status | reasoning | result | error | ping
    raw_type: str             # whatever Auto called it
    operator_name: str | None = None
    summary: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.event_type in {"result", "error"}


# Auto's own event names mapped onto ours. Unknown names fall through to "activity"
# rather than being dropped — losing a frame is worse than mislabelling one.
_TYPE_MAP = {
    "activity": "activity",
    "activity_update": "activity",
    "activity-run": "activity",       # observed live
    "step": "activity",
    "node": "activity",
    "workflow_status": "status",
    "status": "status",
    "run_status": "status",
    "workflow-run": "status",         # observed live
    "reasoning": "reasoning",
    "ai_reasoning": "reasoning",
    "thinking": "reasoning",          # observed live
    "thought": "reasoning",
    "result": "result",
    "workflow_result": "result",
    "complete": "result",
    "completed": "result",
    "error": "error",
    "failed": "error",
    "ping": "ping",
    "keepalive": "ping",
    "hello": "ping",
}


def _normalize_type(raw: str) -> str:
    return _TYPE_MAP.get((raw or "").strip().lower(), "activity")


def _dig(d: Any, *keys: str) -> Any:
    """First non-empty value among `keys`, searched one level deep."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    for v in d.values():
        if isinstance(v, dict):
            got = _dig(v, *keys)
            if got not in (None, "", [], {}):
                return got
    return None


def _parse_step_output(raw: Any) -> dict[str, Any] | None:
    """A step's `output` is a JSON string, an empty string, or already a dict."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _contract_result(run_detail: dict[str, Any]) -> dict[str, Any] | None:
    """The §B1 contract from a child run — the last step that returned one.

    Operators end on a `Return Result` step, but the step is not always named
    that, so we identify the contract by its shape instead of its name and fall
    back to the last structured output if no step carries the full contract.
    """
    fallback: dict[str, Any] | None = None
    for activity in reversed(run_detail.get("activityRuns") or []):
        parsed = _parse_step_output((activity.get("outputs") or {}).get("output"))
        if parsed is None:
            continue
        if "operator_name" in parsed and "status" in parsed:
            return parsed
        if fallback is None:
            fallback = parsed
    return fallback


class _RateLimiter:
    """Auto allows 1000 requests/minute per IP (ratelimit-policy: 1000;w=60).

    One invoice costs about seven calls -- the run itself plus a child-run fetch
    per Operator -- so the ceiling here has to leave room for a batch demo.
    """

    def __init__(self, max_calls: int = 400, per_seconds: float = 60.0) -> None:
        self._max = max_calls
        self._per = per_seconds
        self._calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < self._per]
            if len(self._calls) >= self._max:
                sleep_for = self._per - (now - self._calls[0]) + 0.05
                logger.info("Supervity rate limit reached, sleeping %.1fs", sleep_for)
                await asyncio.sleep(max(sleep_for, 0))
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < self._per]
            self._calls.append(time.monotonic())


_limiter = _RateLimiter()


class SupervityClient:
    def __init__(self, config: SupervityConfig | None = None) -> None:
        self.config = config or SupervityConfig.from_env()

    # ------------------------------------------------------------------ run
    async def execute_stream(
        self,
        inputs: dict[str, Any],
        workflow_id: str | None = None,
        envs: dict[str, Any] | None = None,
    ) -> AsyncIterator[AutoEvent]:
        """Run a workflow and yield normalized SSE events as they arrive.

        Every input goes in its own bracketed multipart field. Auto validates
        `inputs` as a record, so one combined JSON blob is rejected outright.
        """
        wf = workflow_id or self.config.orchestrator_workflow_id
        if not wf:
            raise SupervityNotConfigured(
                "No workflow id. Set SUPERVITY_ORCHESTRATOR_WORKFLOW_ID or pass workflow_id."
            )

        await _limiter.acquire()

        # Auto requires multipart/form-data here. httpx only encodes multipart when
        # `files` is truthy -- `files={}` silently falls back to urlencoded and Auto
        # rejects it with a 4xx. Passing every field as a (None, value) tuple in
        # `files` is the supported way to send a multipart body with no file parts.
        form: dict[str, tuple[None, str]] = {"workflowId": (None, wf)}

        # inputs[<name>] per field. Strings pass through untouched so a value that
        # is already text is not double-encoded into a quoted JSON string; anything
        # structured (the policy snapshot) is serialized, which is what the Operators
        # parse on the other side.
        for name, value in inputs.items():
            if value is None:
                continue
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            form[f"inputs[{name}]"] = (None, text)

        for name, value in (envs or {}).items():
            text = value if isinstance(value, str) else json.dumps(value, default=str)
            form[f"envs[{name}]"] = (None, text)

        url = f"{self.config.base_url}{EXECUTE_STREAM}"
        seq = 0

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                async with client.stream(
                    "POST", url, headers=self.config.headers(), files=form
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")[:500]
                        raise SupervityError(
                            f"Auto returned {resp.status_code} for {url}: {body}"
                        )

                    event_name = "message"
                    data_lines: list[str] = []

                    async for line in resp.aiter_lines():
                        if line.startswith(":"):          # SSE comment / keepalive
                            continue
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                            continue
                        if line == "":                     # blank line ends a frame
                            if data_lines:
                                seq += 1
                                ev = self._build_event(seq, event_name, "\n".join(data_lines))
                                if ev is not None:
                                    yield ev
                            event_name, data_lines = "message", []

                    if data_lines:                         # stream ended without a blank line
                        seq += 1
                        ev = self._build_event(seq, event_name, "\n".join(data_lines))
                        if ev is not None:
                            yield ev

        except httpx.TimeoutException as exc:
            raise SupervityError(f"Auto timed out after {self.config.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise SupervityError(f"Auto request failed: {exc}") from exc

    @staticmethod
    def _build_event(seq: int, raw_type: str, raw_data: str) -> AutoEvent | None:
        if raw_data in ("", "[DONE]"):
            return None
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            payload = {"raw": raw_data}
        if not isinstance(payload, dict):
            payload = {"raw": payload}

        # Auto may name the event in the frame body rather than the `event:` line.
        body_type = _dig(payload, "type", "eventType", "event", "kind")
        chosen = raw_type if raw_type not in ("", "message") else (body_type or raw_type)

        operator = _dig(payload, "operator", "operatorName", "agentName",
                        "nodeName", "stepName")
        if not operator:
            step_id = _dig(payload, "stepId")
            if step_id:
                operator = STEP_DISPLAY_NAMES.get(str(step_id), str(step_id))

        # `thinking` frames carry their text as a bare string in `content`, which the
        # key search below cannot reach.
        content = payload.get("content")
        summary = content if isinstance(content, str) and content else None
        if summary is None:
            summary = _dig(payload, "summary", "message", "description", "text", "status")

        return AutoEvent(
            seq=seq,
            event_type=_normalize_type(str(chosen)),
            raw_type=str(chosen),
            operator_name=operator,
            summary=summary,
            payload=payload,
        )

    # ------------------------------------------------------------ flattening
    async def collect_run_outputs(self, result_payload: dict[str, Any]) -> dict[str, Any]:
        """Flatten a finished run into the keys the Command Center stores.

        The parent run alone is not enough. Each Operator is a subworkflow call
        whose own `output` is an empty string — its §B1 contract, and with it the
        canonical invoice and every protected_value_candidate, exists only inside
        the child run. So we take the verdict from the parent and follow one link
        per Operator to recover the evidence behind it.

        A child that cannot be read is logged and skipped, never invented: a
        missing Operator result must not be mistaken for a passing one.
        """
        workflow_run = result_payload.get("workflowRun")
        if not isinstance(workflow_run, dict):
            workflow_run = _dig(result_payload, "workflowRun") or {}

        flat: dict[str, Any] = {
            "runId": workflow_run.get("id"),
            "run_status": workflow_run.get("status"),
        }
        children: dict[str, str] = {}

        for activity in workflow_run.get("activityRuns") or []:
            if activity.get("kind") != "step":
                continue
            outputs = activity.get("outputs") or {}
            parsed = _parse_step_output(outputs.get("output"))

            # The verdict step publishes its answer directly on the parent run.
            if parsed and "verdict" in parsed:
                flat["verdict"] = parsed.get("verdict")
                codes = parsed.get("combined_reason_codes") or parsed.get("reason_codes") or []
                flat["reason_codes"] = [str(c) for c in codes if c]
                if parsed.get("module_statuses"):
                    flat["module_statuses"] = parsed["module_statuses"]

            key = STEP_TO_OPERATOR_KEY.get(activity.get("stepId") or "")
            if key is None:
                continue
            if parsed is not None:
                flat[key] = parsed
                continue
            html = (outputs.get("displayData") or {}).get("html") or ""
            link = _SUBWORKFLOW_RUN.search(html)
            if link:
                children[key] = link.group(1)
            else:
                logger.warning("No child run link for Operator step %s", key)

        for key, child_run_id in children.items():
            try:
                detail = await self.get_run(child_run_id)
            except SupervityError as exc:
                logger.warning("Could not read %s child run %s: %s", key, child_run_id, exc)
                continue
            contract = _contract_result(detail)
            if contract is not None:
                flat[key] = contract

        canonical = flat.get("intake_result")
        if isinstance(canonical, dict) and isinstance(canonical.get("canonical_invoice"), dict):
            flat["canonical_invoice"] = canonical["canonical_invoice"]

        return flat

    # -------------------------------------------------------------- inspect
    async def get_run(self, workflow_run_id: str) -> dict[str, Any]:
        await _limiter.acquire()
        url = f"{self.config.base_url}{GET_RUN.format(run_id=workflow_run_id)}"
        headers = {**self.config.headers(), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                raise SupervityError(f"Auto returned {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    async def list_runs(self, **params: Any) -> dict[str, Any]:
        await _limiter.acquire()
        url = f"{self.config.base_url}{LIST_RUNS}"
        headers = {**self.config.headers(), "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code >= 400:
                raise SupervityError(f"Auto returned {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    async def cancel(self, run_ids: list[str], reason: str = "") -> dict[str, Any]:
        await _limiter.acquire()
        url = f"{self.config.base_url}{CANCEL}"
        headers = {**self.config.headers(), "Accept": "application/json"}
        body: dict[str, Any] = {"runIds": run_ids}
        if reason:
            body["reason"] = reason
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                raise SupervityError(f"Auto returned {resp.status_code}: {resp.text[:300]}")
            return resp.json()

    # --------------------------------------------------------------- health
    async def health(self) -> tuple[str, int | None, dict[str, Any]]:
        """Used by the Data Manager. Returns (status, latency_ms, detail)."""
        if not self.config.configured:
            return "down", None, {"error": "SUPERVITY_API_KEY / SUPERVITY_ACTIVE_ORG not set"}
        started = time.monotonic()
        try:
            data = await self.list_runs(limit=1)
            latency = int((time.monotonic() - started) * 1000)
            return "healthy", latency, {"endpoint": LIST_RUNS, "sample": _shallow(data)}
        except SupervityError as exc:
            latency = int((time.monotonic() - started) * 1000)
            return "down", latency, {"error": str(exc)[:300]}


def _shallow(data: Any) -> Any:
    """Keep health detail small — never store a full run dump in the registry."""
    if isinstance(data, dict):
        return {k: (f"<{type(v).__name__}>" if isinstance(v, (dict, list)) else v)
                for k, v in list(data.items())[:8]}
    if isinstance(data, list):
        return {"count": len(data)}
    return data
