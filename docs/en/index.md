# ctxloom

**Reactive, artifact-driven agent runtime.**

`ctxloom` builds agents as reactive, stateful processes that transform
**versioned, typed, provenance-aware artifacts** inside an **evolving context**.
There is no execution graph: agents react to changes in state, and the runtime
derives what can run next from those changes.

```text
CREATE / UPDATE / PATCH
       │
       ▼
CONTEXT ───────► ARTIFACTS ─────► AGENTS REACT ──► PATCH ──► CONTEXT'
```

You describe *what data exists*, *what artifacts exist*, and *what agents can do
with them*. The runtime does the plumbing.

## The mental model

| Traditional agent | ctxloom |
| --- | --- |
| A program follows a graph / plan | Agents **react** to state changes |
| Messages are strings | **Typed artifacts** (`Claim`, `Evidence`, `Answer`, …) |
| Orchestration is explicit | Orchestration **falls out of the state** |
| Retries/rollback are manual | Context is **versioned** (git-like commits, diff, rollback) |
| "Who produced this?" is lost | **Provenance** links every derived artifact to its inputs |

## Why artifacts instead of messages?

Messages are opaque; artifacts are inspectable. An `Evidence` object knows its
text, its source, and its score. Because every artifact carries provenance, the
runtime can answer *"why did the agent say that?"* by walking the links
`Answer —supported_by→ Claim —derived_from→ Evidence —extracted_from→ Doc`.

## Why versioned context?

Every run is a commit. That gives you:

- **Diff** — exactly what changed between two turns.
- **Rollback** — undo a bad step and re-run from a clean state.
- **Deterministic replays** — the same history reproduces the same result.
- **Inspectability** — a full, queryable history of everything that happened.

## Requires

- Python 3.12+ (`.venv` is managed by `uv`).
- `pydantic` for artifact models; FastAPI/uvicorn only for the web demos.

## Quick start

```python
from pydantic import BaseModel

from ctxloom import (
    Agent,
    Budget,
    Consume,
    Context,
    Patch,
    Produce,
    Runtime,
    RuntimeResources,
)


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


class Echo(Produce[Answer]):
    artifact_type = Answer

    async def produce(self, context, inputs, event=None):
        question = next(a for a in inputs if isinstance(a.data, Question))
        self.effects.create(Answer(text=f"echo: {question.data.text}"))
        return None


class EchoAgent(Agent):
    name = "echo"
    consumes = [Consume(Question)]
    produces = [Echo()]


ctx = Context(resources=RuntimeResources())
runtime = Runtime(ctx, agents=[EchoAgent()], budget=Budget(max_runs=10))
ctx.create(Question(text="hello"))   # agents that consume it react automatically
runtime.run()
print(ctx.list_artifacts(Answer)[0].data.text)  # "echo: hello"
```

That is the whole loop: **create an artifact → agents react → a patch is applied
→ the context version advances**. Everything else in this documentation builds
on that loop.

## Where to go next

- [Concepts](concepts.md) — Context, Artifact, Patch, Agent, Produce.
- [Sources](sources.md) — where agents get information from.
- [Recipes](recipes.md) — ready-made search fan-out, ref materialization,
  lifecycle state machines.
- [Examples](examples.md) — five working applications you can run.