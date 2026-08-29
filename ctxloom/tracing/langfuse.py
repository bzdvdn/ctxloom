"""Langfuse sink: pushes `RunTrace` to Langfuse via the HTTP Public API.

Mapping: RunTrace → trace (`POST /api/public/traces`), AgentSpan → SPAN observation,
LLMCall → GENERATION observation (`POST /api/public/observations`). Authentication is
Basic (public_key:secret_key). Only `on_turn_end`; the sink requires network — Langfuse
is external.

Uses httpx (base dependency). For tests you can inject `client`.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from .models import RunTrace
from .tracer import Tracer


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _type_summary(refs: list[Any]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for ref in refs:
        kind = getattr(ref, "data_type", None) or type(ref).__name__
        summary[kind] = summary.get(kind, 0) + 1
    return summary


class LangfuseTracer(Tracer):
    """Observer that exports traces to Langfuse."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
        api_url: str | None = None,
        client: Any | None = None,
    ):
        self._base = (api_url or host).rstrip("/") + "/api/public"
        token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self._headers = {"Authorization": f"Basic {token}"}
        if client is not None:
            self._client = client
        else:
            import httpx

            self._client = httpx.Client(headers=self._headers)

    def on_turn_end(self, trace: RunTrace) -> None:
        self._post(
            "/traces",
            {
                "id": trace.id,
                "name": "ctxloom run",
                "timestamp": _iso(trace.started_at),
                "sessionId": trace.session_id or None,
                "metadata": {
                    "duration_ms": trace.duration_ms,
                    "outcome": trace.outcome,
                    "spans": len(trace.spans),
                },
            },
        )
        for span in trace.spans:
            self._post(
                "/observations",
                {
                    "id": f"{trace.id}:span:{span.agent}",
                    "traceId": trace.id,
                    "name": span.agent,
                    "type": "SPAN",
                    "startTime": _iso(span.started_at),
                    # Meaningful input/output for the Langfuse UI: what the agent
                    # received (reads) and what it produced (writes), with
                    # per-type counts that mirror the trace dashboard grouping.
                    "input": {
                        "reads": [r.model_dump() for r in span.reads],
                        "read_summary": _type_summary(span.reads),
                    },
                    "output": {
                        "writes": [w.model_dump() for w in span.writes],
                        "write_summary": _type_summary(span.writes),
                    },
                    "metadata": {
                        "event_type": span.event_type,
                        "latency_ms": span.latency_ms,
                        "error": span.error,
                        "reads": [r.model_dump() for r in span.reads],
                        "writes": [w.model_dump() for w in span.writes],
                    },
                },
            )
            for call in span.llm_calls:
                self._post(
                    "/observations",
                    {
                        "id": f"{trace.id}:llm:{call.agent}:{span.agent}",
                        "traceId": trace.id,
                        "name": f"llm:{call.model or call.provider}",
                        "type": "GENERATION",
                        "model": call.model or None,
                        "input": {"messages": call.messages},
                        "output": call.response or None,
                        "usage": {
                            "input": call.prompt_tokens,
                            "output": call.completion_tokens,
                            "unit": "TOKENS",
                        },
                        "metadata": {
                            "agent": call.agent,
                            "provider": call.provider,
                            "latency_ms": call.latency_ms,
                            "error": call.error,
                        },
                    },
                )

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        self._client.post(self._base + path, json=payload)
