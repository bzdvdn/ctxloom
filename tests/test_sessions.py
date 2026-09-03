import asyncio

from ctxloom import (
    Agent,
    Consume,
    FileKVBackend,
    Patch,
    Runtime,
    SessionStore,
    SQLiteKVBackend,
)
from pydantic import BaseModel


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


class SimpleAnswerer(Agent):
    consumes = [Consume(Question)]
    produces = []

    async def run(self, event, context):
        q = context.get(event.artifact_id)
        if q is None:
            return None
        return Patch().create(Answer(text=q.data.text.upper()))


async def make_session(tmp_path, session_id="alice", backend_kind="file"):
    from ctxloom.resources import RuntimeResources

    if backend_kind == "file":
        backend = FileKVBackend(str(tmp_path / "sessions"))
    else:
        backend = SQLiteKVBackend(str(tmp_path / "sessions.db"))
    store = SessionStore(backend)
    session = await store.open(session_id, resources=RuntimeResources())
    runtime = Runtime(session.context, agents=[SimpleAnswerer()], session=session)
    return session, runtime, store


def test_session_save_load_roundtrip(tmp_path):
    asyncio.run(_test_session_save_load_roundtrip(tmp_path))


async def _test_session_save_load_roundtrip(tmp_path):
    session, runtime, store = await make_session(tmp_path)

    assert session.loaded is False
    session.context.create(Question(text="казах"))
    await runtime.arun()

    assert session.context.version == 1
    assert session.context.head_id is not None

    # load again, like on a process restart
    session2 = await store.open("alice")
    assert session2.loaded is True
    assert session2.context.version == 1
    assert session2.context.head_id == session.context.head_id
    answers = session2.context.list_artifacts(Answer)
    assert len(answers) == 1
    assert answers[0].data.text == "КАЗАХ"


def test_session_auto_persist_after_commit(tmp_path):
    asyncio.run(_test_session_auto_persist_after_commit(tmp_path))


async def _test_session_auto_persist_after_commit(tmp_path):
    session, runtime, store = await make_session(tmp_path)

    session.context.create(Question(text="hi"))
    await runtime.arun_once()

    # data is saved automatically after the commit
    restored = await store.load_session("alice")
    assert restored is not None
    assert len(restored.list_artifacts(Answer)) == 1


def test_sessions_are_isolated(tmp_path):
    asyncio.run(_test_sessions_are_isolated(tmp_path))


async def _test_sessions_are_isolated(tmp_path):
    session_a, runtime_a, store = await make_session(tmp_path, "alice")
    session_b, runtime_b, store = await make_session(tmp_path, "bob")

    session_a.context.create(Question(text="a"))
    await runtime_a.arun()

    session_b.context.create(Question(text="b"))
    await runtime_b.arun()

    loaded_a = await store.load_session("alice")
    loaded_b = await store.load_session("bob")
    assert len(loaded_a.list_artifacts(Answer)) == 1
    assert len(loaded_b.list_artifacts(Answer)) == 1
    assert loaded_a.list_artifacts(Answer)[0].data.text == "A"
    assert loaded_b.list_artifacts(Answer)[0].data.text == "B"


def test_sqlite_kv_roundtrip(tmp_path):
    asyncio.run(_test_sqlite_kv_roundtrip(tmp_path))


async def _test_sqlite_kv_roundtrip(tmp_path):
    session, runtime, store = await make_session(tmp_path, "carol", backend_kind="sqlite")

    session.context.create(Question(text="sqlite"))
    await runtime.arun()

    assert set(await store.list_sessions()) == {"carol"}
    restored = await store.load_session("carol")
    assert restored.list_artifacts(Answer)[0].data.text == "SQLITE"


def test_followup_reuses_context(tmp_path):
    asyncio.run(_test_followup_reuses_context(tmp_path))


async def _test_followup_reuses_context(tmp_path):
    """Continuing a conversation in the same session does not restart from scratch."""

    session, runtime, store = await make_session(tmp_path)

    session.context.create(Question(text="first"))
    await runtime.arun()
    first_version = session.context.version

    session.context.create(Question(text="second"))
    await runtime.arun()
    second_version = session.context.version

    assert second_version > first_version
    assert len(session.context.list_artifacts(Answer)) == 2
    assert len(session.context.history()) == second_version


def test_delete_session(tmp_path):
    asyncio.run(_test_delete_session(tmp_path))


async def _test_delete_session(tmp_path):
    session, runtime, store = await make_session(tmp_path)
    session.context.create(Question(text="x"))
    await runtime.arun()

    assert await store.has_session("alice")
    await session.delete()
    assert not await store.has_session("alice")
    assert await store.list_sessions() == []
