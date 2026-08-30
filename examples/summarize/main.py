"""summarize — conversation memory as artifacts (§27, §37).

Long-running chat memory is just state: `Msg` artifacts accumulate and a
`Summarizer` produce condenses the recent `context.view` into a `Summary`
artifact every N messages; a `Pruner` produce keeps the window bounded by
deleting the oldest messages. No chat buffer — the same artifacts feed the
prompt builder and the summarizer.

    uv run python -m examples.summarize.main
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from ctxloom import (
    Agent,
    Artifact,
    Consume,
    Context,
    Event,
    Produce,
    Runtime,
    RuntimeResources,
    structured_llm,
)
from ctxloom.prompts import PromptTemplate
from ctxloom.providers import LLMProvider, llm_from_env
from pydantic import BaseModel

WINDOW = 4  # messages kept working
SUMMARY_EVERY = 2


class Msg(BaseModel):
    role: str  # user | assistant
    text: str


class Summary(BaseModel):
    round: int
    text: str


class _Text(BaseModel):
    text: str


_SUMMARY = PromptTemplate(
    """You condense the recent conversation into a short memory note.
{history}"""
)


def _history_of(context: Context, limit: int = WINDOW) -> str:
    view = context.view((Msg,), limit=limit)
    ordered = sorted(view.artifacts, key=lambda a: a.created_at)
    return "\n".join(f"{a.data.role}: {a.data.text}" for a in ordered[-limit:])


class Summarize(Produce[Summary]):
    artifact_type = Summary

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        messages = context.list_artifacts(Msg)
        if len(messages) < 2:
            return None
        count = len(messages)
        if count % SUMMARY_EVERY != 0:
            return None
        round_no = count // SUMMARY_EVERY
        if context.get(f"summary:{round_no}") is not None:
            return None
        history = _history_of(context)
        body = await structured_llm(
            context,
            schema=_Text,
            system=_SUMMARY.render(history=history),
            user=history,
        )
        text = body.text if body is not None else f"(offline memory) {history[:140]}"
        self.effects.create(
            Summary(round=round_no, text=text), id=f"summary:{round_no}"
        )
        return None


class Prune(Produce[Msg]):
    artifact_type = Msg

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[Any]],
        event: Event | None = None,
    ) -> None:
        messages = sorted(context.list_artifacts(Msg), key=lambda m: m.created_at)
        old = messages[: len(messages) - WINDOW]
        if not old:
            return None
        for message in old:
            self.effects.delete(message.id)
        return None


class Flow(Agent):
    name = "summarize"
    consumes = [Consume(Msg)]
    produces = [Summarize(), Prune()]


def run(
    *,
    seed: list[str] | None = None,
    llm: LLMProvider | None = None,
) -> Context:
    ctx = Context(resources=RuntimeResources(llm=llm))
    if seed is not None:
        for i, text in enumerate(seed):
            ctx.create(Msg(role="user" if i % 2 == 0 else "assistant", text=text))
    asyncio.run(Runtime(ctx, agents=[Flow()]).arun())
    return ctx


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m examples.summarize.main")
    args = parser.parse_args()

    seed = [
        "We need to finish the room by Friday.",
        "I'll take demolition and rough works in week one.",
        "Budget is 300k; how much is left for materials?",
        "The estimate came to 310k, trim the decor.",
    ]
    ctx = run(seed=seed, llm=llm_from_env())
    summaries = sorted(ctx.list_artifacts(Summary), key=lambda s: s.data.round)
    print("summarize · memory as artifacts (window=4, summary every 2 msgs)")
    for s in summaries:
        print(f"  round {s.data.round}: {s.data.text[:120]}")
    print(f"  messages kept in context: {len(ctx.list_artifacts(Msg))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
