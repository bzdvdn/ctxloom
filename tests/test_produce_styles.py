import asyncio

from ctxloom import (
    Agent,
    Consume,
    Context,
    Patch,
    Produce,
    Runtime,
    produce,
)
from pydantic import BaseModel


class Input(BaseModel):
    text: str


class Marker(BaseModel):
    value: str


# --- Style 1: subclass of Produce (logic next to the type) ---


class MarkerProduce(Produce):
    artifact_type = Marker

    async def produce(self, context, inputs, event=None):
        artifact = context.get(event.artifact_id) if event is not None else None
        if artifact is None or not isinstance(artifact.data, Input):
            return None
        return Patch().create(Marker(value=artifact.data.text.upper()))


class SubclassAgent(Agent):
    consumes = [Consume(Input)]
    produces = [MarkerProduce()]


def test_produce_subclass_style():
    ctx = Context()
    runtime = Runtime(ctx, agents=[SubclassAgent()])
    ctx.create(Input(text="hi"))
    asyncio.run(runtime.arun())

    markers = ctx.list_artifacts(Marker)
    assert len(markers) == 1
    assert markers[0].data.value == "HI"


# --- Style 2: the @produce decorator (compact factory) ---


@produce(Marker)
async def decorator_factory(context, inputs, event):
    artifact = context.get(event.artifact_id) if event is not None else None
    if artifact is None or not isinstance(artifact.data, Input):
        return None
    return Marker(value=artifact.data.text.capitalize())


class DecoratorAgent(Agent):
    consumes = [Consume(Input)]
    produces = [decorator_factory]


def test_produce_decorator_style():
    ctx = Context()
    runtime = Runtime(ctx, agents=[DecoratorAgent()])
    ctx.create(Input(text="привет"))
    asyncio.run(runtime.arun())

    markers = ctx.list_artifacts(Marker)
    assert len(markers) == 1
    assert markers[0].data.value == "Привет"


# --- Two-argument factory stays compatible ---


def plain_factory(context, inputs):
    if not inputs:
        return None
    return Marker(value=inputs[0].data.text + "!")


class PlainAgent(Agent):
    consumes = [Consume(Input)]
    produces = [Produce(Marker, factory=plain_factory)]


def test_plain_two_arg_factory_still_works():
    ctx = Context()
    runtime = Runtime(ctx, agents=[PlainAgent()])
    ctx.create(Input(text="ok"))
    asyncio.run(runtime.arun())
    assert ctx.list_artifacts(Marker)[0].data.value == "ok!"


# --- The event reaches produce ---

received = {}


class RecordProduce(Produce):
    artifact_type = Marker

    async def produce(self, context, inputs, event=None):
        received["id"] = event.artifact_id if event is not None else None
        return Patch().create(Marker(value="recorded"))


class RecordAgent(Agent):
    consumes = [Consume(Input)]
    produces = [RecordProduce()]


def test_event_reaches_produce():
    ctx = Context()
    runtime = Runtime(ctx, agents=[RecordAgent()])
    artifact = ctx.create(Input(text="x"))
    asyncio.run(runtime.arun())

    assert received["id"] == artifact.id
    assert len(ctx.list_artifacts(Marker)) == 1
