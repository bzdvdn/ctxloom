"""Trace delivery: `Tracer` (observer) and `CompositeTracer` (fan-out).

`Tracer` is what the Runtime sees as the source of run events. It is configured
with one or more sinks (`TraceStore`, later Langfuse/Postgres) and on
`on_turn_end` pushes the collected `RunTrace` to each sink:

    Runtime(ctx, agents, tracer=Tracer(store=TraceStore("traces.db")))

`RecordingLLM` is a wrapper over the LLM provider: while tracing is enabled, it intercepts
`complete()` and writes `LLMCall` (tokens from `usage`, attribution to the agent via
`asyncio.current_task()`). Producers know nothing about it — they simply
call `context.resources.llm` as before.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterable
from datetime import datetime
from typing import Any

from ..providers import LLMProvider, LLMRequest, LLMResponse, LLMResponseChunk
from .models import AgentSpan, LLMCall, RunTrace
from .store import TraceSink, TraceStore

#: Up to what size to truncate artifact/response data in a trace.
TRACE_TRUNCATE = 1500


def _clip(value: str, limit: int = TRACE_TRUNCATE) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _clip_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": msg.get("role", ""),
            "content": _clip(str(msg.get("content") or "")),
        }
        for msg in messages
    ]


class Tracer:
    """Observer of runs for the Runtime (§54).

    Runtime invokes `on_turn_begin` / `on_span` (sync, no I/O) and
    `on_turn_end` (async — the sinks write to SQLite/Postgres/Langfuse).
    `on_turn_end` awaits each sink's `export`, so sinks are async stores.
    """

    def __init__(
        self,
        sink: TraceSink | None = None,
        *,
        store: TraceStore | None = None,
        sinks: Iterable[TraceSink] | None = None,
    ):
        self.sinks: list[TraceSink] = []
        if sink is not None:
            self.sinks.append(sink)
        if store is not None:
            self.sinks.append(store)
        if sinks is not None:
            self.sinks.extend(sinks)

    def on_turn_begin(
        self, run_id: str, *, session_id: str, started_at: datetime
    ) -> None:
        pass

    def on_span(self, span: AgentSpan) -> None:
        pass

    async def on_turn_end(self, trace: RunTrace) -> None:
        for sink in self.sinks:
            await sink.export(trace)


class RecordingLLM(LLMProvider):
    """LLM wrapper: records calls (prompt/response/tokens) into `on_call`."""

    def __init__(
        self,
        inner: LLMProvider,
        on_call: Callable[[LLMCall], None],
        agent_of: Callable[[], str],
        provider: str = "",
    ):
        self._inner = inner
        self._on_call = on_call
        self._agent_of = agent_of
        self._provider = provider or type(inner).__name__

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.monotonic()
        try:
            response = await self._inner.complete(request)
        except Exception as exc:  # noqa: BLE001 — record and re-raise
            self._record(request, None, (time.monotonic() - started) * 1000, str(exc))
            raise
        self._record(request, response, (time.monotonic() - started) * 1000, None)
        return response

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        return self._inner.stream(request)

    def _record(
        self,
        request: LLMRequest,
        response: LLMResponse | None,
        latency_ms: float,
        error: str | None,
    ) -> None:
        usage = dict(response.usage if response is not None else {})
        call = LLMCall(
            agent=self._agent_of(),
            provider=self._provider,
            model=str(getattr(self._inner, "model", "") or ""),
            messages=_clip_messages(
                [
                    m.model_dump() if hasattr(m, "model_dump") else m.__dict__
                    for m in request.messages
                ]
            ),
            response=_clip(response.text) if response is not None else "",
            prompt_tokens=int(usage.get("prompt_tokens") or usage.get("prompt") or 0),
            completion_tokens=int(
                usage.get("completion_tokens") or usage.get("completion") or 0
            ),
            latency_ms=round(latency_ms, 1),
            error=error,
        )
        self._on_call(call)


class CompositeTracer:
    """Distributes events to all passed observers (local + Langfuse)."""

    def __init__(self, tracers: Iterable[Tracer]):
        self.tracers = list(tracers)

    def on_turn_begin(
        self, run_id: str, *, session_id: str, started_at: datetime
    ) -> None:
        for tracer in self.tracers:
            tracer.on_turn_begin(run_id, session_id=session_id, started_at=started_at)

    def on_span(self, span: AgentSpan) -> None:
        for tracer in self.tracers:
            tracer.on_span(span)

    async def on_turn_end(self, trace: RunTrace) -> None:
        for tracer in self.tracers:
            await tracer.on_turn_end(trace)
