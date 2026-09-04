"""Concurrent-writer regression test for `SQLiteKVBackend` (§0.4.0 changelog).

Before 0.4.0, every KV operation reconnected to the database and had no
`busy_timeout`, so concurrent writers raced straight into
`sqlite3.OperationalError: database is locked`. The fix — WAL mode plus a
5s `busy_timeout` — is only meaningful across independent connections (a
single backend instance already serializes itself with an `asyncio.Lock`),
so this test opens several separate `SQLiteKVBackend`s against the same
file, the way independent processes or independent `Context`s sharing one
session store would.
"""

from __future__ import annotations

import asyncio

from ctxloom.checkpoints import SQLiteKVBackend


async def _write_many(backend: SQLiteKVBackend, prefix: str, count: int) -> None:
    for i in range(count):
        await backend.set(f"{prefix}:{i}", {"value": i})


def test_concurrent_writers_do_not_raise_database_locked(tmp_path):
    db_path = str(tmp_path / "shared.sqlite3")
    backends = [SQLiteKVBackend(db_path) for _ in range(8)]

    async def _run() -> None:
        await asyncio.gather(
            *(
                _write_many(backend, f"writer{i}", 25)
                for i, backend in enumerate(backends)
            )
        )
        for backend in backends:
            await backend.aclose()

    asyncio.run(_run())  # would raise sqlite3.OperationalError pre-fix

    verifier = SQLiteKVBackend(db_path)

    async def _verify() -> list[str]:
        keys = await verifier.keys()
        await verifier.aclose()
        return keys

    keys = asyncio.run(_verify())
    assert len(keys) == 8 * 25
    for i in range(8):
        assert f"writer{i}:24" in keys


def test_concurrent_read_write_same_key_is_serialized_not_corrupted(tmp_path):
    db_path = str(tmp_path / "hot_key.sqlite3")
    writer = SQLiteKVBackend(db_path)
    reader = SQLiteKVBackend(db_path)

    async def _writes() -> None:
        for i in range(50):
            await writer.set("hot", {"value": i})

    async def _reads() -> list[dict | None]:
        results = []
        for _ in range(50):
            results.append(await reader.get("hot"))
        return results

    async def _run() -> list[dict | None]:
        _, reads = await asyncio.gather(_writes(), _reads())
        await writer.aclose()
        await reader.aclose()
        return reads

    reads = asyncio.run(_run())
    # every read is either None (before the first write lands) or a value
    # this writer actually wrote — never a torn/partial write.
    for r in reads:
        assert r is None or (isinstance(r, dict) and 0 <= r["value"] < 50)
