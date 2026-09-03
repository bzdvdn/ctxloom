import asyncio
import os
import tempfile

import pytest
from ctxloom.commit import Commit
from ctxloom.context import Context
from ctxloom.patches import Update
from pydantic import BaseModel


class Doc(BaseModel):
    title: str
    content: str


def test_checkpoint_roundtrip():
    asyncio.run(_test_checkpoint_roundtrip())


async def _test_checkpoint_roundtrip():
    ws = Context()
    doc = ws.create(Doc(title="Test", content="Hello"))
    # update the artifact
    ws.update(doc.id, Doc(title="Test", content="Updated"))
    ws.log_commit(
        Commit(
            author="test",
            message="test commit",
            operations=[Update(doc.id, Doc(title="Test", content="Updated"))],
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "checkpoint.json")
        await ws.save_checkpoint(path)

        # load into a new Context
        ws2 = await Context.load_checkpoint(path)

    # verify that the artifact was restored
    assert len(ws2.list_artifacts(Doc)) == 1
    restored_doc = ws2.list_artifacts(Doc)[0]
    assert restored_doc.id == doc.id
    assert restored_doc.data.content == "Updated"
    # check the history
    assert len(restored_doc.history) == 1
    assert restored_doc.history[0].content == "Hello"
    # check the commits
    commits = ws2.commit_log()
    assert len(commits) == 1
    assert commits[0].author == "test"
    assert len(commits[0].operations) == 1
    op = commits[0].operations[0]
    assert isinstance(op, Update)
    assert op.artifact_id == doc.id
    assert op.new_data.content == "Updated"


def test_postgres_kv_requires_dsn_and_lazy_driver():
    """The backend exists in the public API; psycopg is imported only at use.

    Run against a real Postgres with TEST_PG_DSN set:
      TEST_PG_DSN=postgresql://user:pass@localhost/ctxloom pytest tests/test_checkpoint.py
    """
    import os

    dsn = os.environ.get("TEST_PG_DSN")
    if not dsn:
        pytest.skip("TEST_PG_DSN not set — skipping Postgres KV integration")
    import psycopg  # noqa: F401  (ensure the extra is installed)

    asyncio.run(_test_postgres_kv_roundtrip(dsn))


async def _test_postgres_kv_roundtrip(dsn: str) -> None:
    from ctxloom import PostgreSQLKVBackend

    backend = PostgreSQLKVBackend(dsn)
    try:
        await backend.set("k1", {"hello": "world"})
        assert await backend.get("k1") == {"hello": "world"}
        assert await backend.keys() == ["k1"]
        await backend.delete("k1")
        assert await backend.get("k1") is None
    finally:
        await backend.aclose()


def test_require_extra_readable_error():
    """Missing extra dependency → a hint, not a bare ModuleNotFoundError."""
    from unittest import mock

    from ctxloom._extras import require_extra

    def _boom(name, *a, **kw):
        raise ModuleNotFoundError(f"No module named '{name}'", name=name)

    with mock.patch("ctxloom._extras.importlib.import_module", side_effect=_boom):
        try:
            require_extra("PostgreSQLKVBackend", "psycopg", "pg")
        except ImportError as exc:
            message = str(exc)
            assert 'pip install "ctxloom[pg]"' in message
            assert "PostgreSQLKVBackend requires" in message
        else:  # pragma: no cover
            raise AssertionError("expected ImportError with the install hint")
