"""summarize — conversation memory as artifacts (§27, §37).

Long-running chat memory is just state: `Msg` artifacts accumulate and
`ctxloom.recipes.WindowSummarizer` condenses the recent window into a
`Summary` artifact every N messages; `WindowPruner` keeps the window bounded
by deleting the oldest messages. No chat buffer — the same artifacts feed the
prompt builder and the summarizer. The recipe owns the window/cadence/
idempotency bookkeeping; this demo only supplies the summarizer callback and
the `Summary` shape.

    uv run python -m examples.summarize.main
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ctxloom import Agent, Consume, Context, Runtime, RuntimeResources
from ctxloom.providers import LLMProvider
from ctxloom.recipes import WindowPruner, WindowSummarizer, llm_summarizer
from pydantic import BaseModel


def build_llm() -> LLMProvider | None:
    """Explicit provider for this demo: OpenRouter (default) or a local
    OpenAI-compatible endpoint; `None` when no key is configured -> offline."""
    import os

    from ctxloom.providers import openai_llm, openrouter_llm

    if os.getenv("OPENROUTER_API_KEY"):
        return openrouter_llm(max_tokens=2048)
    if os.getenv("OPENAI_BASE_URL"):
        return openai_llm(
            base_url=os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL"),
            max_tokens=2048,
        )
    return None


WINDOW = 4  # messages kept working
SUMMARY_EVERY = 2


class Msg(BaseModel):
    role: str  # user | assistant
    text: str


class Summary(BaseModel):
    round: int
    text: str


def _build_summary(round_no: int, text: str) -> Summary:
    return Summary(round=round_no, text=text)


_summarize = llm_summarizer(
    "You condense the recent conversation into a short memory note."
)


class Flow(Agent):
    name = "summarize"
    consumes = [Consume(Msg)]
    produces = [
        WindowSummarizer(
            Msg,
            Summary,
            summarize=_summarize,
            build=_build_summary,
            window=WINDOW,
            every=SUMMARY_EVERY,
        ),
        WindowPruner(Msg, keep=WINDOW),
    ]


async def _arun(
    *,
    seed: list[str] | None = None,
    llm: LLMProvider | None = None,
) -> Context:
    ctx = Context(resources=RuntimeResources(llm=llm))
    runtime = Runtime(ctx, agents=[Flow()])
    # One message, then one run — not a bulk seed followed by a single run —
    # so round 1's summary actually gets produced before round 2's messages
    # even exist (otherwise `Summarize` only ever sees the final message
    # count and round 1 is structurally unreachable).
    for i, text in enumerate(seed or []):
        ctx.create(Msg(role="user" if i % 2 == 0 else "assistant", text=text))
        await runtime.arun()
    return ctx


def run(
    *,
    seed: list[str] | None = None,
    llm: LLMProvider | None = None,
) -> Context:
    return asyncio.run(_arun(seed=seed, llm=llm))


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m examples.summarize.main")
    parser.parse_args()

    seed = [
        "We need to finish the room by Friday.",
        "I'll take demolition and rough works in week one.",
        "Budget is 300k; how much is left for materials?",
        "The estimate came to 310k, trim the decor.",
    ]
    ctx = run(seed=seed, llm=build_llm())
    summaries = sorted(ctx.list_artifacts(Summary), key=lambda s: s.data.round)
    print("summarize · memory as artifacts (window=4, summary every 2 msgs)")
    for s in summaries:
        print(f"  round {s.data.round}: {s.data.text[:200]}")
    print(f"  messages kept in context: {len(ctx.list_artifacts(Msg))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
