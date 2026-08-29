# Observability

Every run records a trace. Traces are *observable by default*: the demo
dashboards work offline with no external services, and you can additionally ship
traces to Langfuse or Postgres.

## What a trace contains

A `RunTrace` is one run of the runtime (until `astream`/`run` ends):

- **Agent spans** (`AgentSpan`) — what each agent did: artifact reads and
  writes, and the key/value summary of the patch it produced.
- **LLM calls** (`LLMCall`) — prompts, responses (truncated), token usage,
  latency.
- **Timing and ordering** — the whole causal chain of a run, in order.

`RecordingLLM` wraps your provider for free, so **LLM call tracking needs no
code** — just wire it at resources time.

## Storing and viewing

### SQLite store + web dashboard (local, offline)

```python
from ctxloom.tracing import TraceStore

store = TraceStore("traces.db")   # SQLite sink; also serves runs back to the UI
```

The dashboard is a FastAPI router mounted on your app:

```python
from ctxloom.tracing.web import create_trace_router

app.include_router(create_trace_router(store), prefix="/traces")
```

It serves `traces.html` (list of runs, filterable) and `run.html` (spans, reads,
writes, LLM input/output, timing). The `devops` example mounts this router and
is the reference UI.

### Langfuse and Postgres as additional sinks

A trace can go to several places at once via `CompositeTracer`, passed to the
`Runtime`. `Tracer`s are thin: `on_turn_begin` → `on_span` → `on_turn_end`.

```python
from ctxloom import Runtime
from ctxloom.tracing import LangfuseTracer, PostgresStore, TraceStore

runtime = Runtime(
    ctx,
    agents=[...],
    tracer=[
        TraceStore("traces.db"),                        # local dashboard
        LangfuseTracer(public_key="...", private_key="...",
                       host="https://cloud.langfuse.com"),
        PostgresStore(dsn="postgresql://…"),            # pg extra required
    ],
)
```

Spans are delivered once per turn end (delivery-once semantics); the Langfuse
tracer maps read/write summaries into `input`/`output`, so the timeline is
readable in their UI. The SQLite `TraceStore` stays the source for the web
dashboard; Postgres mirrors the same `runs`/`spans` schema for external
tooling.

## Emission model

- Only **state-changing** agents emit spans (a pure read/verify produce emits
  nothing — less noise).
- One `Tracer` per `CompositeTracer`: hand the same composite to multiple sinks.
- `on_turn_end` is the single delivery point: a new `astream`/`arun` advances the
  run id (a re-run counts as a new run), and each turn's trace is finalized once.

## Progress events (UI reactivity)

For the animated "Думаю… / Составляю план… / Считаю смету…" lines, `Produce`s
call `context.announce(message, kind=..., **payload)`. Those become
`ProgressEvent`s on the `EventHub`, which the runtime yields to the SSE stream:

```python
async for event in runtime.astream():
    if event.kind == "status":
        yield sse("status", {"message": event.message})
```

`announce` is not a log — it is a *first-class UI channel* that the web demos
consume verbatim.