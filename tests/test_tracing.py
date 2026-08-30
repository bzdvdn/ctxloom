import asyncio

from ctxloom import (
    Agent,
    Consume,
    Context,
    Patch,
    Runtime,
    RuntimeResources,
    Tracer,
    TraceStore,
)
from ctxloom.providers import LLMProvider, LLMRequest, LLMResponse
from ctxloom.tracing import AgentSpan, ArtifactRef, LLMCall, RunTrace
from pydantic import BaseModel


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


class ReplyLLM(LLMProvider):
    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text='{"text":"привет"}',
            usage={"prompt_tokens": 12, "completion_tokens": 7},
        )

    async def stream(self, request):
        yield LLMResponse(text="")


class Greeter(Agent):
    consumes = [Consume(Question)]

    async def run(self, event, context):
        q = context.get(event.artifact_id)
        if q is None:
            return None
        return Patch().create(Answer(text="Привет!"))


class CountingQuestion(Question):
    """Counts model_dump calls to verify memoization."""

    dumps: int = 0

    def model_dump(self, *args, **kwargs):
        type(self).dumps += 1
        return super().model_dump(*args, **kwargs)


class Note(BaseModel):
    text: str


class Linker(Agent):
    """Writes two artifacts and a provenance edge via the patch."""

    consumes = [Consume(Question)]

    async def run(self, event, context):
        return (
            Patch()
            .create(Note(text="one"), id="note:1")
            .create(Note(text="two"), id="note:2")
            .link("note:1", "supported_by", "note:2")
        )


def test_trace_store_roundtrip(tmp_path):
    store = TraceStore(str(tmp_path / "traces.db"))
    trace = RunTrace(
        id="abc",
        session_id="s1",
        outcome="completed",
        spans=[
            AgentSpan(
                agent="greeter",
                event_type="artifact_created",
                reads=[
                    ArtifactRef(
                        artifact_id="q1",
                        version=0,
                        op_type="read",
                        data_type="Question",
                        data='{"text":"hi"}',
                    )
                ],
                writes=[
                    ArtifactRef(
                        artifact_id="a1",
                        version=0,
                        op_type="create",
                        data_type="Answer",
                        data='{"text":"Привет!"}',
                    )
                ],
                latency_ms=12.5,
            )
        ],
    )
    store.export(trace)

    assert store.get("abc") is not None
    assert store.get("nope") is None
    assert store.query()["total"] == 1
    assert store.query(session_id="other")["items"] == []
    assert store.query(session_id="s1")["items"][0]["id"] == "abc"
    assert store.query(outcome="completed")["total"] == 1
    assert store.query(outcome="failed")["items"] == []


def test_runtime_records_spans_and_trace(tmp_path):
    store = TraceStore(str(tmp_path / "traces.db"))
    ctx = Context(resources=RuntimeResources(llm=ReplyLLM()))
    tracer = Tracer(store=store)
    runtime = Runtime(ctx, agents=[Greeter()], tracer=tracer)
    ctx.create(Question(text="привет"))
    asyncio.run(runtime.arun())

    traces = store.query()["items"]
    assert len(traces) == 1
    trace = store.get(traces[0]["id"])
    assert trace is not None
    assert trace.outcome == "completed"
    # greeter span: read the question, created the answer
    greeter = next(s for s in trace.spans if s.agent == "Greeter")
    assert any(
        r.artifact_id == ctx.list_artifacts(Question)[0].id for r in greeter.reads
    )
    # writes carry artifact data
    assert any(w.op_type == "create" for w in greeter.writes)
    assert greeter.latency_ms >= 0
    answers = ctx.list_artifacts(Answer)
    assert any(w.artifact_id == answers[0].id for w in greeter.writes)
    created = next(w for w in greeter.writes if w.op_type == "create")
    assert created.data_type == "Answer"
    assert created.data is not None and "Привет" in created.data


def test_runtime_records_llm_calls(tmp_path):
    from ctxloom import structured_llm

    class AnswerBody(BaseModel):
        text: str

    class LlamAgent(Agent):
        consumes = [Consume(Question)]

        async def run(self, event, context):
            body = await structured_llm(context, schema=AnswerBody, user="привет")
            return Patch().create(Answer(text=body.text if body else ""))

    store = TraceStore(str(tmp_path / "llm.db"))
    ctx = Context(resources=RuntimeResources(llm=ReplyLLM()))
    runtime = Runtime(ctx, agents=[LlamAgent()], tracer=Tracer(store=store))
    ctx.create(Question(text="hi"))
    asyncio.run(runtime.arun())

    trace = store.get(store.query()["items"][0]["id"])
    assert trace is not None
    llam = next(s for s in trace.spans if s.agent == "LlamAgent")
    assert len(llam.llm_calls) == 1
    call = llam.llm_calls[0]
    assert call.agent == "LlamAgent"
    assert call.prompt_tokens == 12
    assert call.completion_tokens == 7
    assert call.latency_ms >= 0
    assert any("привет" in (m.get("content") or "") for m in call.messages)
    assert "привет" in call.response


def test_runtime_without_tracer_still_works():
    ctx = Context(resources=RuntimeResources(llm=ReplyLLM()))
    runtime = Runtime(ctx, agents=[Greeter()])
    ctx.create(Question(text="привет"))
    asyncio.run(runtime.arun())
    assert ctx.list_artifacts(Answer)


def test_composite_tracer_fans_out(tmp_path):
    store_a = TraceStore(str(tmp_path / "a.db"))
    store_b = TraceStore(str(tmp_path / "b.db"))
    ctx = Context(resources=RuntimeResources(llm=ReplyLLM()))
    runtime = Runtime(
        ctx,
        agents=[Greeter()],
        tracer=[Tracer(store=store_a), Tracer(store=store_b)],
    )
    ctx.create(Question(text="привет"))
    asyncio.run(runtime.arun())
    assert store_a.query()["total"] == 1
    assert store_b.query()["total"] == 1


def test_trace_store_migrates_old_schema(tmp_path):
    """Old DB without the llm_calls column — migrated without data loss."""
    import sqlite3

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE runs (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL DEFAULT '',
            started_at REAL NOT NULL, duration_ms REAL NOT NULL, outcome TEXT NOT NULL
        );
        CREATE TABLE spans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
            agent TEXT NOT NULL, event_type TEXT NOT NULL DEFAULT '', latency_ms REAL NOT NULL DEFAULT 0,
            error TEXT, reads TEXT NOT NULL DEFAULT '[]', writes TEXT NOT NULL DEFAULT '[]'
        );
        """
    )
    conn.execute("INSERT INTO runs VALUES ('old', 's', 0, 1, 'completed')")
    conn.commit()
    conn.close()

    store = TraceStore(path)  # migration adds llm_calls
    assert store.get("old") is not None  # the old trace is readable
    rows = store._conn.execute("PRAGMA table_info(spans)").fetchall()
    assert any(r[1] == "llm_calls" for r in rows)


def test_trace_memoizes_artifact_dump(tmp_path):
    """Two agents read one artifact — model_dump is called once (memo)."""
    CountingQuestion.dumps = 0

    class Greeter2(Agent):
        consumes = [Consume(CountingQuestion)]

        async def run(self, event, context):
            return Patch().create(Answer(text="hi"))

    store = TraceStore(str(tmp_path / "memo.db"))
    ctx = Context(resources=RuntimeResources(llm=ReplyLLM()))
    runtime = Runtime(ctx, agents=[Greeter2(), Greeter2()], tracer=Tracer(store=store))
    ctx.create(CountingQuestion(text="q"))
    asyncio.run(runtime.arun())

    assert CountingQuestion.dumps == 1


def test_trace_store_retention_prunes_oldest(tmp_path):
    store = TraceStore(str(tmp_path / "ret.db"), max_runs=2)
    for i in range(5):
        store.export(RunTrace(id=f"r{i}", session_id="s", outcome="completed"))

    items = store.query()["items"]
    ids = {item["id"] for item in items}
    assert ids == {"r3", "r4"}  # the last 2 remain
    assert store.get("r0") is None
    # spans of old traces are also removed
    rows = store._conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
    assert rows == 0  # r3/r4 have no spans (exported without spans)


class FakeClient:
    """Captures POST requests instead of real HTTP."""

    def __init__(self):
        self.requests: list[tuple[str, dict]] = []

    def post(self, url: str, json=None):
        self.requests.append((url, json or {}))


def test_langfuse_exports_trace_spans_and_llm():
    from ctxloom.tracing import LangfuseTracer

    client = FakeClient()
    langfuse = LangfuseTracer(
        public_key="pk",
        secret_key="sk",
        host="http://langfuse.local",
        client=client,
    )
    langfuse.on_turn_end(
        RunTrace(
            id="tr",
            session_id="s1",
            outcome="completed",
            spans=[
                AgentSpan(
                    agent="greeter",
                    event_type="artifact_created",
                    writes=[
                        ArtifactRef(
                            artifact_id="a1",
                            version=0,
                            op_type="create",
                            data_type="Answer",
                            data='{"t":"Привет!"}',
                        )
                    ],
                    llm_calls=[
                        LLMCall(
                            agent="greeter",
                            provider="fake",
                            model="m",
                            messages=[{"role": "user", "content": "hi"}],
                            response="ok",
                            prompt_tokens=3,
                            completion_tokens=2,
                        )
                    ],
                )
            ],
        )
    )

    paths = [url.rsplit("/", 1)[-1] for url, _ in client.requests]
    assert paths == ["traces", "observations", "observations"]  # trace + span + llm
    trace_payload = client.requests[0][1]
    assert trace_payload["id"] == "tr"
    assert trace_payload["sessionId"] == "s1"
    span_payload = client.requests[1][1]
    assert span_payload["type"] == "SPAN"
    assert span_payload["name"] == "greeter"
    assert "writes" in span_payload["metadata"]
    # meaningful input/output: what the agent received / produced (+ type counts)
    assert span_payload["input"]["read_summary"] == {}
    assert span_payload["output"]["write_summary"] == {"Answer": 1}
    assert span_payload["output"]["writes"][0]["artifact_id"] == "a1"
    llm_payload = client.requests[2][1]
    assert llm_payload["type"] == "GENERATION"
    assert llm_payload["usage"] == {"input": 3, "output": 2, "unit": "TOKENS"}
    assert llm_payload["model"] == "m"


def test_postgres_store_requires_pg_extra():
    """PostgresStore without psycopg installed fails honestly (pg extra)."""
    import importlib.util

    from ctxloom.tracing import PostgresStore

    if importlib.util.find_spec("psycopg") is None:
        try:
            PostgresStore("postgresql://x")
        except (ImportError, ModuleNotFoundError):
            pass
        else:
            raise AssertionError("expected ImportError without psycopg")


def _basic(user: str, password: str) -> str:
    import base64

    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_trace_router_basic_auth(tmp_path):
    from ctxloom.tracing.web import create_trace_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = TraceStore(str(tmp_path / "auth.db"))
    store.export(RunTrace(id="r1", session_id="s", outcome="completed"))
    app = FastAPI()
    app.include_router(create_trace_router(store, username="obs", password="secret"))
    client = TestClient(app)

    # without a header — 401
    assert client.get("/api/traces").status_code == 401
    assert client.get("/traces").status_code == 401
    # wrong password — 401
    assert (
        client.get(
            "/api/traces", headers={"Authorization": _basic("obs", "bad")}
        ).status_code
        == 401
    )
    # valid — 200 and data
    ok = client.get("/api/traces", headers={"Authorization": _basic("obs", "secret")})
    assert ok.status_code == 200
    assert ok.json()["total"] == 1


def test_trace_router_open_without_auth(tmp_path):
    from ctxloom.tracing.web import create_trace_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = TraceStore(str(tmp_path / "open.db"))
    app = FastAPI()
    app.include_router(create_trace_router(store))
    client = TestClient(app)
    assert client.get("/api/traces").status_code == 200


def test_trace_run_page_embeds_mermaid_diagram(tmp_path):
    from ctxloom.tracing.web import create_trace_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = TraceStore(str(tmp_path / "diag.db"))
    store.export(
        RunTrace(
            id="r1",
            outcome="completed",
            duration_ms=12.0,
            spans=[AgentSpan(agent="planner", event_type="ResearchTurn", writes=[])],
        )
    )
    app = FastAPI()
    app.include_router(create_trace_router(store))
    client = TestClient(app)
    html = client.get("/traces/r1").text
    assert "__MERMAID__" not in html  # the placeholder was replaced
    assert "__RUN_ID__" not in html
    assert "sequenceDiagram" in html
    assert "MERMAID_SRC" in html


def test_trace_run_page_embeds_provenance_graph(tmp_path):
    from ctxloom.tracing.models import RelationRef
    from ctxloom.tracing.web import create_trace_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = TraceStore(str(tmp_path / "evg.db"))
    store.export(
        RunTrace(
            id="r1",
            outcome="completed",
            duration_ms=12.0,
            spans=[
                AgentSpan(
                    agent="answerer",
                    event_type="Answer",
                    writes=[
                        {
                            "artifact_id": "a1",
                            "op_type": "create",
                            "data_type": "Answer",
                            "data": "{}",
                        },
                        {
                            "artifact_id": "c1",
                            "op_type": "create",
                            "data_type": "Claim",
                            "data": "{}",
                        },
                    ],
                    relations=[
                        RelationRef(
                            source_id="a1",
                            relation="supported_by",
                            target_id="c1",
                            source_type="Answer",
                            target_type="Claim",
                        )
                    ],
                )
            ],
        )
    )
    app = FastAPI()
    app.include_router(create_trace_router(store))
    client = TestClient(app)
    html = client.get("/traces/r1").text
    assert "__MERMAID_GRAPH__" not in html
    assert "Evidence graph" in html
    assert "MERMAID_GRAPH_SRC" in html
    assert "supported_by" in html  # the provenance edge was rendered server-side


def test_runtime_records_provenance_relations(tmp_path):
    store = TraceStore(str(tmp_path / "rels.db"))
    ctx = Context(resources=RuntimeResources())
    runtime = Runtime(ctx, agents=[Linker()], tracer=Tracer(store=store))
    ctx.create(Question(text="link me"))
    asyncio.run(runtime.arun())

    items = store.query()["items"]
    assert len(items) == 1
    loaded = store.get(items[0]["id"])
    assert loaded is not None
    assert loaded.spans and loaded.spans[0].writes
    relations = loaded.spans[0].relations
    assert len(relations) == 1
    edge = relations[0]
    assert edge.source_id == "note:1"
    assert edge.relation == "supported_by"
    assert edge.target_id == "note:2"
    assert edge.source_type == "Note"
    assert edge.target_type == "Note"
