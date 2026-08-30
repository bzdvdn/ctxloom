# Replay (§55)

Replay answers the constitutive question — **"why did the agent produce this
answer?"** — concretely. Because commits are deterministic (§14), context state
is recoverable *without running agents*, and because every LLM call can be
recorded, a run can be *reproduced exactly*.

## Provider-level record & replay

`ReplayLLM` is a recording studio for the model calls. Two passes:

```python
from ctxloom import ReplayLLM

# pass 1 — record a real run
resources = RuntimeResources(
    llm=ReplayLLM("calls.jsonl", mode="record", inner=real_llm)
)
runtime.run()                          # appends every call to calls.jsonl

# pass 2 — reproduce the run without any network
resources = RuntimeResources(llm=ReplayLLM("calls.jsonl", mode="replay"))
runtime.run()                          # same artifacts, same answers
```

- **`mode="record"`** wraps a real provider and appends each
  `(request → response)` pair (model, temperature, response_format, messages →
  text, usage) as one JSONL line.
- **`mode="replay"`** answers *exactly* the recorded calls. A call that does
  not match the recording raises `ReplayMiss` — it must not be answered with a
  wrong result (§59). At the `structured_llm` layer the miss degrades to an
  honest `None` (the normal fallback path).

Because the deterministic paths (guards, calculations, routing) are unchanged,
a replayed run produces identical artifacts — and you can walk the reproduced
state (or render it with `context_to_mermaid`) to explain the answer.

## Deterministic state replay

A session checkpoint carries the full commit chain. Reconstruct the state at a
specific commit without agent execution:

```python
from ctxloom import replay_context, replay_summary
from ctxloom.checkpoints import SQLiteKVBackend
from ctxloom.session import SessionStore

store = SessionStore(SQLiteKVBackend("sessions.sqlite3"))
context = replay_context(store, session_id, version=7)   # state at commit 7
print(replay_summary(context))                            # counts, by type
```

## CLI

```bash
python -m ctxloom replay sessions.sqlite3 --session demo --diagram
```

Prints the replayed state summary (`version · artifacts · relations · pending
questions`, breakdown by artifact type) and, with `--diagram`, the provenance
graph as Mermaid. `--version` replays to a specific commit.