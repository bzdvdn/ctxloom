"""`ctxloom.recipes.memory` — bounded conversation memory (§27, §37).

`WindowSummarizer` + `WindowPruner` replace the hand-rolled Summarize/Prune
pair that used to live only in `examples/summarize/main.py` — same behavior,
now parametrized instead of copy-pasted per app.
"""

from __future__ import annotations

import asyncio

from ctxloom import Agent, Consume, Context, Runtime, create_agent
from ctxloom.recipes import WindowPruner, WindowSummarizer
from pydantic import BaseModel


class Msg(BaseModel):
    role: str
    text: str


class Summary(BaseModel):
    round: int
    text: str


def _build(round_no: int, text: str) -> Summary:
    return Summary(round=round_no, text=text)


async def _offline_summarize(context: Context, history: str) -> str | None:
    return None  # forces the fallback path, deterministic and offline


def _flow(*, window: int = 4, every: int = 2, keep: int = 4) -> Agent:
    return create_agent(
        "memory",
        consumes=[Consume(Msg)],
        produces=[
            WindowSummarizer(
                Msg,
                Summary,
                summarize=_offline_summarize,
                build=_build,
                window=window,
                every=every,
            ),
            WindowPruner(Msg, keep=keep),
        ],
    )


def _run(messages: list[str]) -> Context:
    async def _arun() -> Context:
        ctx = Context()
        runtime = Runtime(ctx, agents=[_flow()])
        for i, text in enumerate(messages):
            ctx.create(Msg(role="user" if i % 2 == 0 else "assistant", text=text))
            await runtime.arun()
        return ctx

    return asyncio.run(_arun())


def test_summarizes_every_n_messages_with_stable_round_ids():
    ctx = _run([f"msg {i}" for i in range(4)])
    summaries = sorted(ctx.list_artifacts(Summary), key=lambda s: s.data.round)
    assert [s.data.round for s in summaries] == [1, 2]
    assert ctx.get("summary:1") is not None
    assert ctx.get("summary:2") is not None


def test_offline_summarizer_produces_honest_fallback_text():
    ctx = _run(["hello", "world"])
    summary = ctx.get("summary:1")
    assert summary is not None
    assert summary.data.text.startswith("(offline memory)")


def test_pruner_keeps_only_the_window():
    ctx = _run([f"msg {i}" for i in range(10)])
    assert len(ctx.list_artifacts(Msg)) == 4  # keep=4 in _flow()


def test_pruner_alone_bounds_messages_without_a_summarizer():
    async def _arun() -> Context:
        ctx = Context()
        agent = create_agent(
            "prune-only", consumes=[Consume(Msg)], produces=[WindowPruner(Msg, keep=2)]
        )
        runtime = Runtime(ctx, agents=[agent])
        for i in range(5):
            ctx.create(Msg(role="user", text=f"m{i}"))
            await runtime.arun()
        return ctx

    ctx = asyncio.run(_arun())
    assert len(ctx.list_artifacts(Msg)) == 2
    remaining = sorted(ctx.list_artifacts(Msg), key=lambda m: m.data.text)
    assert [m.data.text for m in remaining] == ["m3", "m4"]


def test_no_summary_before_the_first_round_completes():
    ctx = _run(["only one message"])
    assert ctx.list_artifacts(Summary) == []
