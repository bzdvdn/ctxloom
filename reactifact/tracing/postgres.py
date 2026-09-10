# mypy: ignore-errors
"""PostgreSQL trace sink: pushes `RunTrace` to PG and can serve it back.

Requires the ``pg`` extra (psycopg async): imported lazily, so the `tracing`
package works without it. Schema mirrors the SQLite sink: `runs`/`spans` tables
with reads/writes/relations/llm_calls as jsonb.

Both write (`export`) and read (`query`/`get`) are async — this is what lets the
web dashboard in `create_trace_router` read from Postgres directly.

Connections are short-lived (opened per operation via
`psycopg.AsyncConnection`), so the store is not bound to any event loop and can
be shared across requests.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from .models import AgentSpan, ArtifactRef, LLMCall, RelationRef, RunTrace


class PostgresStore:
    """Postgres trace sink with async write + read. Requires the `pg` extra."""

    def __init__(self, dsn: str):
        from .._extras import require_extra

        self._psycopg = require_extra("PostgresStore", "psycopg", "pg")
        self.dsn = dsn
        self._schema_ready = False

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        conn = await self._psycopg.AsyncConnection.connect(self.dsn)
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL DEFAULT '',
                        started_at TIMESTAMPTZ NOT NULL,
                        duration_ms REAL NOT NULL,
                        outcome TEXT NOT NULL
                    )
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spans (
                        id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL REFERENCES runs(id),
                        agent TEXT NOT NULL,
                        event_type TEXT NOT NULL DEFAULT '',
                        latency_ms REAL NOT NULL DEFAULT 0,
                        error TEXT,
                        reads JSONB NOT NULL DEFAULT '[]',
                        writes JSONB NOT NULL DEFAULT '[]',
                        relations JSONB NOT NULL DEFAULT '[]',
                        llm_calls JSONB NOT NULL DEFAULT '[]'
                    )
                    """
                )
                await cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id)",
                )
            await conn.commit()
        finally:
            await conn.close()
        self._schema_ready = True

    async def export(self, trace: RunTrace) -> None:

        import psycopg.types.json

        await self._ensure_schema()
        started = trace.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        conn = await self._psycopg.AsyncConnection.connect(self.dsn)
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO runs (id, session_id, started_at, duration_ms, outcome) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        trace.id,
                        trace.session_id,
                        started,
                        trace.duration_ms,
                        trace.outcome,
                    ),
                )
                for span in trace.spans:
                    await cur.execute(
                        "INSERT INTO spans (run_id, agent, event_type, latency_ms, error, "
                        "reads, writes, relations, llm_calls) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            trace.id,
                            span.agent,
                            span.event_type,
                            span.latency_ms,
                            span.error,
                            psycopg.types.json.Jsonb(
                                [r.model_dump(mode="json") for r in span.reads]
                            ),
                            psycopg.types.json.Jsonb(
                                [w.model_dump(mode="json") for w in span.writes]
                            ),
                            psycopg.types.json.Jsonb(
                                [r.model_dump(mode="json") for r in span.relations]
                            ),
                            psycopg.types.json.Jsonb(
                                [c.model_dump(mode="json") for c in span.llm_calls]
                            ),
                        ),
                    )
            await conn.commit()
        finally:
            await conn.close()

    async def query(
        self,
        *,
        session_id: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        await self._ensure_schema()
        where: list[str] = []
        args: list[Any] = []
        if session_id is not None:
            where.append("session_id = %s")
            args.append(session_id)
        if outcome is not None:
            where.append("outcome = %s")
            args.append(outcome)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        conn = await self._psycopg.AsyncConnection.connect(self.dsn)
        try:
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT COUNT(*) FROM runs{where_sql}", tuple(args))
                total = (await cur.fetchone())[0]
                await cur.execute(
                    f"SELECT id, session_id, started_at, duration_ms, outcome, "
                    f"(SELECT COUNT(*) FROM spans WHERE run_id = runs.id) AS spans_count "
                    f"FROM runs{where_sql} ORDER BY started_at DESC LIMIT %s OFFSET %s",
                    (*args, limit, offset),
                )
                rows = await cur.fetchall()
        finally:
            await conn.close()

        items = [
            {
                "id": r[0],
                "session_id": r[1],
                "started_at": r[2],
                "duration_ms": round(r[3], 1),
                "outcome": r[4],
                "spans": r[5],
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    async def get(self, trace_id: str) -> RunTrace | None:
        from datetime import UTC

        await self._ensure_schema()
        conn = await self._psycopg.AsyncConnection.connect(self.dsn)
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, session_id, started_at, duration_ms, outcome "
                    "FROM runs WHERE id = %s",
                    (trace_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                await cur.execute(
                    "SELECT agent, event_type, latency_ms, error, reads, writes, "
                    "relations, llm_calls FROM spans WHERE run_id = %s ORDER BY id",
                    (trace_id,),
                )
                span_rows = await cur.fetchall()
        finally:
            await conn.close()

        spans = [
            AgentSpan(
                agent=r[0],
                event_type=r[1],
                latency_ms=r[2],
                error=r[3],
                reads=[ArtifactRef(**d) for d in r[4]],
                writes=[ArtifactRef(**d) for d in r[5]],
                relations=[RelationRef(**d) for d in r[6]],
                llm_calls=[LLMCall(**d) for d in r[7]],
            )
            for r in span_rows
        ]
        started = row[2]
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return RunTrace(
            id=row[0],
            session_id=row[1],
            started_at=started,
            duration_ms=row[3],
            outcome=row[4],
            spans=spans,
        )
