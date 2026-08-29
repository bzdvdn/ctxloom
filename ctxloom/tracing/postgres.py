# mypy: ignore-errors
"""PostgreSQL trace sink: pushes `RunTrace` to external PG.

Requires the ``pg`` extra (psycopg): imported lazily, so the `tracing` package
works without it. The schema mirrors the SQLite sink: `runs`/`spans` tables
(reads/writes/llm_calls — jsonb).
"""

from __future__ import annotations

import time

from .models import RunTrace


class PostgresStore:
    """Pushes traces to Postgres (`TraceSink`). Requires external driver."""

    def __init__(self, dsn: str):
        import psycopg  # type: ignore[import-not-found]

        self._conn = psycopg.connect(dsn)
        self._create_schema()

    def _create_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
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
            cur.execute(
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
                    llm_calls JSONB NOT NULL DEFAULT '[]'
                )
                """
            )
        self._conn.commit()

    def export(self, trace: RunTrace) -> None:
        import psycopg
        import psycopg.types.json

        started = trace.started_at.timestamp() if trace.started_at else time.time()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO runs (id, session_id, started_at, duration_ms, outcome) "
                "VALUES (%s, %s, to_timestamp(%s), %s, %s)",
                (trace.id, trace.session_id, started, trace.duration_ms, trace.outcome),
            )
            for span in trace.spans:
                cur.execute(
                    "INSERT INTO spans (run_id, agent, event_type, latency_ms, error, "
                    "reads, writes, llm_calls) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
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
                            [c.model_dump(mode="json") for c in span.llm_calls]
                        ),
                    ),
                )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
