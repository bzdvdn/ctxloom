import asyncio

import pytest
from ctxloom import Agent, Consume, Context, Patch, Produce, Runtime
from pydantic import BaseModel


class Input(BaseModel):
    text: str


class Output(BaseModel):
    text: str


# --- Imperative agent (as before, run is overridden) ---
class SimpleAgent(Agent):
    consumes = [Consume(Input)]
    produces = [Produce(Output)]

    async def run(self, event, context):
        data = context.get(event.artifact_id)
        if data is None:
            return None
        return Patch().create(Output(text=data.data.text.upper()))


def test_auto_triggers_from_consumes():
    ctx = Context()
    runtime = Runtime(ctx, agents=[SimpleAgent()])

    agent = runtime.agents[0]
    assert len(agent.triggers) == 2  # created and updated

    ctx.create(Input(text="hello"))
    asyncio.run(runtime.arun())

    outputs = ctx.list_artifacts(Output)
    assert len(outputs) == 1
    assert outputs[0].data.text == "HELLO"


# --- Declarative agent (automatic run based on Produce) ---
async def make_upper(context, inputs):
    if not inputs:
        return []
    return [Output(text=inputs[0].data.text.upper())]


def test_auto_run_with_produce_factory_is_deprecated_but_still_works():
    """Produce(..., factory=...) is deprecated (§ produce styles cleanup) —
    still functions for existing code, but warns and points at @produce."""
    with pytest.warns(DeprecationWarning, match="Produce.*factory.*deprecated"):
        produce_instance = Produce(Output, factory=make_upper)

    class AutoAgent(Agent):
        name = "auto_agent"
        consumes = [Consume(Input)]
        produces = [produce_instance]

    ctx = Context()
    runtime = Runtime(ctx, agents=[AutoAgent()])

    ctx.create(Input(text="hello"))
    asyncio.run(runtime.arun())

    outputs = ctx.list_artifacts(Output)
    assert len(outputs) == 1
    assert outputs[0].data.text == "HELLO"
