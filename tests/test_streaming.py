import asyncio

from ctxloom import Agent, Consume, Context, Patch, ProgressEvent, Runtime
from ctxloom.streaming import EventHub
from pydantic import BaseModel


class UserMsg(BaseModel):
    text: str


class Done(BaseModel):
    text: str


class Announcer(Agent):
    consumes = [Consume(UserMsg)]

    async def run(self, event, context):
        context.announce("Думаю над вопросом...", kind="status", source="brain")
        context.announce("Найдено 3 соответствия", kind="status")
        return Patch().create(Done(text="ok"))


async def collect_events(runtime):
    return [ev async for ev in runtime.astream()]


def test_astream_yields_status_and_run_end():
    ctx = Context()
    runtime = Runtime(ctx, agents=[Announcer()])
    ctx.create(UserMsg(text="привет"))

    events = asyncio.run(collect_events(runtime))

    assert events[0].kind == "run_start"
    assert events[-1].kind == "run_end"
    statuses = [e for e in events if e.kind == "status"]
    assert [e.message for e in statuses] == [
        "Думаю над вопросом...",
        "Найдено 3 соответствия",
    ]
    assert statuses[0].data["source"] == "brain"
    assert events[-1].data["runs"] >= 1
    assert events[-1].data["outcome"] in {"completed", "budget_runs_exceeded"}


def test_announce_is_noop_without_subscribers():
    ctx = Context()
    ctx.announce("никто не слушает", kind="status")  # must not raise
    assert isinstance(ctx._hub, EventHub)


def test_eventhub_multiple_subscribers():
    hub = EventHub()
    q1 = hub.subscribe()
    q2 = hub.subscribe()

    hub.publish(ProgressEvent(kind="status", message="x"))
    ev1 = q1.get_nowait()
    ev2 = q2.get_nowait()
    assert ev1.message == ev2.message == "x"

    hub.unsubscribe(q1)
    hub.unsubscribe(q2)
    assert not hub.has_subscribers
    hub.publish(ProgressEvent(kind="status", message="y"))
    assert q2.empty()
