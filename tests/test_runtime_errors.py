"""Runtime error handling: agent exceptions must surface through astream()."""

import asyncio

from ctxloom import Agent, Consume, Context, Patch, Produce, Runtime
from pydantic import BaseModel


class Trigger(BaseModel):
    pass


class Explode(Produce[Trigger]):
    artifact_type = Trigger

    async def produce(self, context, inputs, event=None) -> Patch | None:
        raise RuntimeError("boom inside the agent")


class ExplodeAgent(Agent):
    name = "explode"
    consumes = [Consume(Trigger)]
    produces = [Explode()]


def test_astream_propagates_agent_error():
    ctx = Context()
    runtime = Runtime(ctx, agents=[ExplodeAgent()])
    ctx.create(Trigger())

    async def collect():
        return [ev async for ev in runtime.astream()]

    try:
        asyncio.run(collect())
    except RuntimeError as exc:
        assert "boom inside the agent" in str(exc)
    else:
        raise AssertionError("expected the agent's RuntimeError to propagate")


def test_arun_propagates_agent_error():
    ctx = Context()
    runtime = Runtime(ctx, agents=[ExplodeAgent()])
    ctx.create(Trigger())
    try:
        asyncio.run(runtime.arun())
    except RuntimeError as exc:
        assert "boom inside the agent" in str(exc)
    else:
        raise AssertionError("expected the agent's RuntimeError to propagate")
