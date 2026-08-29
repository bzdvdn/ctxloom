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


def make_session(tmp_path, session_id="alice", backend_kind="file"):
    from ctxloom.resources import RuntimeResources

    if backend_kind == "file":
        backend = FileKVBackend(str(tmp_path / "sessions"))
    else:
        backend = SQLiteKVBackend(str(tmp_path / "sessions.db"))
    store = SessionStore(backend)
    session = store.open(session_id, resources=RuntimeResources())
    runtime = Runtime(session.context, agents=[SimpleAnswerer()], session=session)
    return session, runtime, store


def test_session_save_load_roundtrip(tmp_path):
    session, runtime, store = make_session(tmp_path)

    assert session.loaded is False
    session.context.create(Question(text="казах"))
    asyncio.run(runtime.arun())

    assert session.context.version == 1
    assert session.context.head_id is not None

    # load again, like on a process restart
    session2 = store.open("alice")
    assert session2.loaded is True
    assert session2.context.version == 1
    assert session2.context.head_id == session.context.head_id
    answers = session2.context.list_artifacts(Answer)
    assert len(answers) == 1
    assert answers[0].data.text == "КАЗАХ"


def test_session_auto_persist_after_commit(tmp_path):
    session, runtime, store = make_session(tmp_path)

    session.context.create(Question(text="hi"))
    asyncio.run(runtime.arun_once())

    # data is saved automatically after the commit
    restored = store.load_session("alice")
    assert restored is not None
    assert len(restored.list_artifacts(Answer)) == 1


def test_sessions_are_isolated(tmp_path):
    session_a, runtime_a, store = make_session(tmp_path, "alice")
    session_b, runtime_b, store = make_session(tmp_path, "bob")

    session_a.context.create(Question(text="a"))
    asyncio.run(runtime_a.arun())

    session_b.context.create(Question(text="b"))
    asyncio.run(runtime_b.arun())

    loaded_a = store.load_session("alice")
    loaded_b = store.load_session("bob")
    assert len(loaded_a.list_artifacts(Answer)) == 1
    assert len(loaded_b.list_artifacts(Answer)) == 1
    assert loaded_a.list_artifacts(Answer)[0].data.text == "A"
    assert loaded_b.list_artifacts(Answer)[0].data.text == "B"


def test_sqlite_kv_roundtrip(tmp_path):
    session, runtime, store = make_session(tmp_path, "carol", backend_kind="sqlite")

    session.context.create(Question(text="sqlite"))
    asyncio.run(runtime.arun())

    assert set(store.list_sessions()) == {"carol"}
    restored = store.load_session("carol")
    assert restored.list_artifacts(Answer)[0].data.text == "SQLITE"


def test_followup_reuses_context(tmp_path):
    """Continuing a conversation in the same session does not restart from scratch."""

    session, runtime, store = make_session(tmp_path)

    session.context.create(Question(text="first"))
    asyncio.run(runtime.arun())
    first_version = session.context.version

    session.context.create(Question(text="second"))
    asyncio.run(runtime.arun())
    second_version = session.context.version

    assert second_version > first_version
    assert len(session.context.list_artifacts(Answer)) == 2
    assert len(session.context.history()) == second_version


def test_delete_session(tmp_path):
    session, runtime, store = make_session(tmp_path)
    session.context.create(Question(text="x"))
    asyncio.run(runtime.arun())

    assert store.has_session("alice")
    session.delete()
    assert not store.has_session("alice")
    assert store.list_sessions() == []
