import asyncio
import os

import pytest
from ctxloom import (
    ChatAssistant,
    Consume,
    FileKVBackend,
    SessionStore,
    create_agent,
    produce,
)
from ctxloom.web import create_chat_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class Q(BaseModel):
    text: str
    session_id: str = ""


class A(BaseModel):
    text: str


async def make_answer(context, inputs, event, effects):
    effects.create(A(text="answer"))
    return None


ASSISTANT_PROD = produce(A)(make_answer)
ANSWER_AGENT = create_agent("a", consumes=[Consume(Q)], produces=[ASSISTANT_PROD])


def make_assistant(tmp_path: str) -> ChatAssistant:
    store = SessionStore(FileKVBackend(os.path.join(tmp_path, "sess")))

    def reply(ctx, msg_id):
        a = ctx.latest(A)
        return {"reply": a.data.text if a else "fallback", "waiting": False}

    return ChatAssistant(
        store=store,
        agents=[ANSWER_AGENT],
        user_message=Q,
        reply=reply,
        max_concurrency=1,
    )


def test_stream_events(tmp_path):
    assistant = make_assistant(str(tmp_path))

    async def run():
        events = [ev async for ev in assistant.stream("hi", session_id="s1")]
        return events

    events = asyncio.run(run())
    assert [e.kind for e in events] == ["session", "message"]
    assert events[1].payload["reply"] == "answer"


def test_history_roundtrip(tmp_path):
    assistant = make_assistant(str(tmp_path))
    _drain(assistant.stream("hi", session_id="s1"))
    history = assistant.history("s1")
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant"]
    assert history["messages"][0]["text"] == "hi"
    assert history["messages"][1]["text"] == "answer"


def test_history_empty_for_unknown_session(tmp_path):
    assistant = make_assistant(str(tmp_path))
    assert assistant.history("nope")["messages"] == []


def _drain(stream):
    async def _collect():
        return [ev async for ev in stream]

    return asyncio.run(_collect())


def test_web_router_contract(tmp_path):
    assistant = make_assistant(str(tmp_path))
    app = FastAPI()
    app.include_router(create_chat_router(assistant))
    client = TestClient(app)

    assert client.get("/api/health").json() == {"ok": True}

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "hi", "session_id": "s1"},
    ) as response:
        body = "".join(response.iter_text())

    assert "event: session" in body
    assert "event: message" in body
    assert '"reply": "answer"' in body

    runs = client.get("/api/runs/s1").json()
    assert any(m["role"] == "assistant" for m in runs["messages"])
    assert client.delete("/api/runs/s1").json() == {"ok": True}
    assert client.get("/api/runs/s1").json()["messages"] == []


def test_web_extra_error_is_readable(tmp_path, monkeypatch):
    """Missing fastapi → a readable install hint, not a bare ModuleNotFoundError."""
    import builtins
    import sys

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "fastapi" or name.startswith("fastapi."):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return real_import(name, *args, **kwargs)

    # Drop cached fastapi so importlib actually tries to import it again.
    for mod in [m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setattr(builtins, "__import__", blocked)
    from ctxloom import ChatAssistant, Consume, create_agent, produce

    class _Q(BaseModel):
        text: str
        session_id: str = ""

    async def _m(ctx, inputs, event, effects):
        return None

    agent = create_agent("a", consumes=[Consume(_Q)], produces=[produce(_Q)(_m)])
    with pytest.raises(ImportError, match=r"ctxloom\[web\]"):
        create_chat_router(
            ChatAssistant(
                store=None,
                agents=[agent],
                user_message=_Q,
                reply=lambda ctx, mid: {},
            )
        )


def test_runtime_crash_degrades_to_fallback_message(tmp_path, caplog):
    """A crashing produce must not escape as an exception from stream()."""

    from ctxloom import Agent, Produce

    class Boom(Produce[A]):
        async def produce(self, context, inputs, event=None):
            raise RuntimeError("boom inside the agent")

    class BoomAgent(Agent):
        name = "boom"
        consumes = [Consume(Q)]
        produces = [Boom()]

    store = SessionStore(FileKVBackend(os.path.join(str(tmp_path), "sess")))
    assistant = ChatAssistant(
        store=store,
        agents=[BoomAgent()],
        user_message=Q,
        reply=lambda ctx, mid: {"reply": "should not reach", "waiting": False},
        max_concurrency=1,
        fallback_reply="degraded",
    )

    events = _drain(assistant.stream("hi", session_id="s1"))

    kinds = [ev.kind for ev in events]
    assert kinds[-1] == "message"
    assert events[-1].payload["reply"] == "degraded"
    assert events[-1].payload.get("error") is True
    assert any("runtime crashed" in r.message for r in caplog.records)


def test_reply_hook_crash_degrades_to_fallback(tmp_path, caplog):
    """A crashing reply hook must degrade to the fallback, not a 500."""

    def boom_reply(ctx, mid):
        raise RuntimeError("reply hook exploded")

    store = SessionStore(FileKVBackend(os.path.join(str(tmp_path), "sess")))
    assistant = ChatAssistant(
        store=store,
        agents=[ANSWER_AGENT],
        user_message=Q,
        reply=boom_reply,
        max_concurrency=1,
        fallback_reply="degraded",
    )

    events = _drain(assistant.stream("hi", session_id="s2"))

    assert events[-1].kind == "message"
    assert events[-1].payload["reply"] == "degraded"
    assert events[-1].payload.get("error") is True


def test_session_open_crash_degrades_to_fallback(tmp_path, caplog):
    """A failing session open must degrade to a fallback message, not an exception."""

    class BoomStore:
        def open(self, session_id, resources=None):
            raise RuntimeError("backend down")

        def delete_session(self, session_id):
            pass

    assistant = ChatAssistant(
        store=BoomStore(),
        agents=[ANSWER_AGENT],
        user_message=Q,
        reply=lambda ctx, mid: {"reply": "never", "waiting": False},
        max_concurrency=1,
        fallback_reply="degraded",
    )

    events = _drain(assistant.stream("hi", session_id="s3"))

    assert events[-1].kind == "message"
    assert events[-1].payload["reply"] == "degraded"
