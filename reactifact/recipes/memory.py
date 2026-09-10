"""recipes — bounded conversation memory: periodic summarization + pruning.

Long-running chat memory is just state (§27, §37): message artifacts
accumulate, a `WindowSummarizer` condenses the recent window into a summary
artifact every N messages, and a `WindowPruner` keeps the window bounded by
deleting the oldest messages. Both are plain `Produce`s — drop them into an
`Agent.produces` list next to whatever else reacts to the message type.

Domain owns *how* to summarize (the `summarize` callback) and *what* the
summary artifact looks like (`build`); this recipe only owns the window size,
cadence, and idempotency bookkeeping — the same split as `materialize_doc`
owning provenance while the caller owns the document factory.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from ..artifacts import Artifact
from ..context import Context
from ..events import Event
from ..produce import Produce
from ..structured import OnStructuredError, llm_reply

MsgT = TypeVar("MsgT", bound=BaseModel)
SummaryT = TypeVar("SummaryT", bound=BaseModel)


def _default_render(messages: list[Artifact[Any]]) -> str:
    lines = []
    for a in messages:
        role = getattr(a.data, "role", None)
        text = getattr(a.data, "text", None)
        lines.append(
            f"{role}: {text}" if role is not None and text is not None else str(a.data)
        )
    return "\n".join(lines)


def _default_fallback(history: str) -> str:
    return f"(offline memory) {history[:140]}"


class WindowSummarizer(Produce[SummaryT], Generic[MsgT, SummaryT]):
    """Condenses the recent window of `message_type` artifacts into a summary
    artifact every `every` messages (§27).

    Idempotent by construction: the summary id is derived from the message
    count, so re-running the same generation never produces a duplicate.
    """

    def __init__(
        self,
        message_type: type[MsgT],
        artifact_type: type[SummaryT],
        *,
        summarize: Callable[[Context, str], Awaitable[str | None]],
        build: Callable[[int, str], SummaryT],
        window: int = 8,
        every: int = 4,
        render: Callable[[list[Artifact[MsgT]]], str] = _default_render,
        fallback: Callable[[str], str] = _default_fallback,
        order_key: Callable[[Artifact[MsgT]], Any] = lambda a: a.created_at,
        id_of: Callable[[int], str] = lambda round_no: f"summary:{round_no}",
    ):
        super().__init__(artifact_type=artifact_type)
        self.message_type = message_type
        self.summarize = summarize
        self.build = build
        self.window = window
        self.every = every
        self.render = render
        self.fallback = fallback
        self.order_key = order_key
        self.id_of = id_of

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        messages = context.list_artifacts(self.message_type)
        count = len(messages)
        if count == 0 or count % self.every != 0:
            return None
        round_no = count // self.every
        summary_id = self.id_of(round_no)
        if context.get(summary_id) is not None:
            return None  # this round's summary already exists (§42)
        recent = sorted(messages, key=self.order_key)[-self.window :]
        history = self.render(recent)
        text = await self.summarize(context, history)
        if text is None:
            text = self.fallback(history)
        self.effects.create(self.build(round_no, text), id=summary_id)
        return None


class WindowPruner(Produce[MsgT], Generic[MsgT]):
    """Deletes `message_type` artifacts older than `keep` (ordered by
    `order_key`, default `created_at`). Standalone-useful — pair it with
    `WindowSummarizer` for full sliding-window memory, or use it alone to
    just bound how many messages a context keeps.
    """

    def __init__(
        self,
        message_type: type[MsgT],
        *,
        keep: int = 8,
        order_key: Callable[[Artifact[MsgT]], Any] = lambda a: a.created_at,
    ):
        super().__init__(artifact_type=message_type)
        self.message_type = message_type
        self.keep = keep
        self.order_key = order_key

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        messages = sorted(context.list_artifacts(self.message_type), key=self.order_key)
        # `max(0, ...)`: a plain negative slice bound wraps from the end in
        # Python (`messages[:-1]` means "all but the last"), which would prune
        # the wrong messages while the window hasn't filled up yet.
        old = messages[: max(0, len(messages) - self.keep)]
        if not old:
            return None
        for message in old:
            self.effects.delete(message.id)
        return None


def llm_summarizer(
    system: str,
    *,
    attempts: int = 2,
    temperature: float | None = None,
    max_tokens: int | None = None,
    on_error: OnStructuredError | None = None,
) -> Callable[[Context, str], Awaitable[str | None]]:
    """Builds a `WindowSummarizer(summarize=...)` callback from a system
    prompt, via `llm_reply` — the common case, no custom schema class needed.
    """

    async def _summarize(context: Context, history: str) -> str | None:
        return await llm_reply(
            context,
            system=system,
            user=history,
            attempts=attempts,
            temperature=temperature,
            max_tokens=max_tokens,
            on_error=on_error,
        )

    return _summarize


__all__ = ["WindowSummarizer", "WindowPruner", "llm_summarizer"]
