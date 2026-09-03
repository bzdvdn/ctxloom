"""ctxloom.replay — deterministic reproduction of runs (§55).

Two complementary halves:

1. `ReplayLLM` — a provider-level recording studio. `mode="record"` wraps a real
   provider and appends every `(request → response)` pair to a JSONL file;
   `mode="replay"` answers *exactly* the recorded calls and raises `ReplayMiss`
   when a call diverges from the recording — a divergent call must not be
   answered with a wrong result (§59, §55).

   Record once (real model), then re-run the runtime with the replaying LLM:
   because every deterministic path is unchanged, the run reproduces the same
   artifacts, and "why did the agent produce this answer?" (§55) can be answered
   by walking the reproduced state.

2. `replay_context` / `replay_summary` — reconstruct a saved session's state at
   a specific commit (the commit chain is deterministic, §14), i.e. a cheap,
   offline "what was the state when the agent said that".
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .context import Context
from .providers import LLMProvider, LLMRequest, LLMResponse, LLMResponseChunk

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from .session import SessionStore

logger = logging.getLogger(__name__)


class ReplayMiss(RuntimeError):
    """A replaying call did not match the recording (§55)."""


def _request_key(model: str, request: LLMRequest) -> str:
    payload = {
        "model": model,
        "temperature": request.temperature,
        "response_format": request.response_format,
        "messages": [{"role": m.role, "content": m.content} for m in request.messages],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ReplayLLM(LLMProvider):
    """Records LLM calls to a JSONL file, or replays them exactly.

        recorder = ReplayLLM("calls.jsonl", mode="record", inner=real_llm)
        resources = RuntimeResources(llm=recorder)
        runtime.run()                      # record pass

        replay = ReplayLLM("calls.jsonl", mode="replay")
        resources = RuntimeResources(llm=replay)
        runtime.run()                      # deterministic reproduction (§55)

    A recording also answers the "why" question: every call carries the exact
    prompt and the exact response, so the product story is reproducible.
    """

    def __init__(
        self,
        recording: str | Path,
        *,
        mode: Literal["record", "replay"] = "replay",
        inner: LLMProvider | None = None,
        model: str = "",
    ):
        if mode == "record" and inner is None:
            raise ValueError("mode='record' requires an `inner` provider")
        self.recording = Path(recording)
        self.mode = mode
        self._inner = inner
        self.model = model
        self._cache: dict[str, dict[str, Any]] | None = None

    # -- LLMProvider ---------------------------------------------------------

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self.mode == "replay":
            return self._replay(request)
        assert self._inner is not None
        response = await self._inner.complete(request)
        self._append(request, response)
        return response

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        if self.mode == "record" and self._inner is not None:
            async for chunk in self._inner.stream(request):
                yield chunk
            return
        raise ReplayMiss(
            "stream() is not replayed; record stream calls or use complete()"
        )

    # -- recording -----------------------------------------------------------

    def _append(self, request: LLMRequest, response: LLMResponse) -> None:
        entry = {
            "key": _request_key(self.model, request),
            "model": self.model,
            "response": {
                "text": response.text,
                "finish_reason": response.finish_reason,
            },
            "usage": response.usage,
        }
        self.recording.parent.mkdir(parents=True, exist_ok=True)
        with self.recording.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- replaying -----------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        cache: dict[str, dict[str, Any]] = {}
        if self.recording.exists():
            for line in self.recording.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                cache[entry["key"]] = entry
        self._cache = cache
        return cache

    def _replay(self, request: LLMRequest) -> LLMResponse:
        key = _request_key(self.model, request)
        entry = self._load().get(key)
        if entry is None:
            logger.warning("replay miss for %r", key)
            raise ReplayMiss(
                "the run diverged from the recording — a call was not recorded. "
                "Re-record with mode='record', or check whether the prompt "
                "changed since the recording was made."
            )
        response = entry["response"]
        return LLMResponse(
            text=response["text"],
            finish_reason=response.get("finish_reason"),
            usage=dict(entry.get("usage") or {}),
        )


def replay_context(
    store: SessionStore,
    session_id: str,
    *,
    version: int | None = None,
) -> Context:
    """Reconstructs a saved session's state, optionally at a past commit (§55).

    The session checkpoint carries the full deterministic commit chain (§14), so
    replaying to a version needs no agent execution — it is pure state recovery.
    """
    context = store.load_session(session_id)
    if context is None:
        raise KeyError(f"session {session_id!r} not found")
    if version is not None:
        context.checkout(version)
    return context


def replay_summary(context: Context) -> dict[str, Any]:
    """A compact "state at this point" summary for the replay CLI."""
    artifacts = context.list_artifacts()
    by_type: dict[str, int] = {}
    for artifact in artifacts:
        tname = artifact.data.__class__.__name__
        by_type[tname] = by_type.get(tname, 0) + 1
    return {
        "version": context.version,
        "artifacts": len(artifacts),
        "by_type": by_type,
        "relations": len(context.relations()),
        "pending_questions": len(context.pending_questions()),
    }


__all__ = ["ReplayLLM", "ReplayMiss", "replay_context", "replay_summary"]
