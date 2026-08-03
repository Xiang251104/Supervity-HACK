# app/services/supervity.py
"""Client for the Supervity Auto workflow API.

This is the only place the backend talks to Auto. Everything else works off the
rows this writes.

Endpoint facts, verified against https://auto.supervity.ai/docs/api-docs :

  POST /api/v1/workflow-runs/execute/stream   run a workflow, SSE response
  POST /api/v1/workflow-runs/execute          same, blocking
  GET  /api/v1/workflow-runs/:runId           one run with activity detail
  GET  /api/v1/workflow-runs                  list / filter
  POST /api/v1/workflow-runs/cancel           cancel

  Headers   Authorization: Bearer <workflow api key>
            x-source: external
            x-active-org: <org key>

  *** The execute endpoints take multipart/form-data, NOT json. ***
  Fields: workflowId (required), inputs, envs. Posting JSON returns 4xx.

  *** Rate limit is 60 requests/minute per IP. ***
  Batch runs must go through the limiter below, not fire concurrently.

The SSE payload shape is not fully documented, so parsing here is deliberately
loose: we normalize the fields we recognise and always keep the raw frame in
`payload` so nothing is lost if the shape differs from what we expect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://auto.supervity.ai"
EXECUTE_STREAM = "/api/v1/workflow-runs/execute/stream"
EXECUTE = "/api/v1/workflow-runs/execute"
GET_RUN = "/api/v1/workflow-runs/{run_id}"
LIST_RUNS = "/api/v1/workflow-runs"
CANCEL = "/api/v1/workflow-runs/cancel"


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
    "step": "activity",
    "node": "activity",
    "workflow_status": "status",
    "status": "status",
    "run_status": "status",
    "reasoning": "reasoning",
    "ai_reasoning": "reasoning",
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


class _RateLimiter:
    """Auto allows 60 requests/minute per IP. Stay under it."""

    def __init__(self, max_calls: int = 55, per_seconds: float = 60.0) -> None:
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

        `inputs` is sent as a JSON string inside a multipart field — Auto expects
        multipart/form-data here, not a JSON body.
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
        form: dict[str, tuple[None, str]] = {
            "workflowId": (None, wf),
            "inputs": (None, json.dumps(inputs, default=str)),
        }
        if envs:
            form["envs"] = (None, json.dumps(envs, default=str))

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

        return AutoEvent(
            seq=seq,
            event_type=_normalize_type(str(chosen)),
            raw_type=str(chosen),
            operator_name=_dig(payload, "operator", "operatorName", "agentName",
                               "nodeName", "stepName", "name"),
            summary=_dig(payload, "summary", "message", "description", "text", "status"),
            payload=payload,
        )

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
