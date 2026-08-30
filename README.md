# ctxloom

**Reactive, artifact-driven agent runtime.**

`ctxloom` is a framework for building agents as reactive, stateful processes
that transform **versioned, typed, provenance-aware artifacts** inside an
**evolving context** — instead of describing execution as a graph.

```text
AGENT
   │
   ▼
CONTEXT ──► PATCH ──► CONTEXT'
```

You describe _what data exists, what artifacts exist, what agents can do with
them_. The runtime derives execution from state changes: an artifact is created,
agents that consume it react, produce a patch, and the context moves to the next
version. No explicit graphs, no node pipelines.

## Core primitives

- **Context** — versioned working state, git-like commits, `diff`/`rollback`/`merge`.
- **Artifact** — a first-class typed object (`Claim`, `Evidence`, `Answer`, …),
  not a string blob.
- **Patch** — the only language agents use to change state (`create/update/delete/link`).
- **Agent** — a thin container declaring `consumes`/`produces`; logic lives in `Produce`.
- **Source** — a retrieval capability. Vector search is _one_ strategy; direct API,
  keyword, SQL, and filesystem are equally first-class. Embeddings optional.
- **Provenance** — every derived artifact links back to what produced it
  (`Answer —supported_by→ Claim —derived_from→ Evidence —extracted_from→ Doc`).
- **HITL** — humans interact through `PendingQuestion`/patch resumption like any agent.

## Highlights

- Deterministic work stays deterministic (§67): calculations over structured data
  (`CSVSource` → `Spreadsheet` → `Calculation`) instead of hallucinated numbers.
- Claims carry `confidence` and explicit contradictions (§35–§36), so the model is
  a reasoning component, never the source of truth.
- Observability built in: every run traces agent spans, reads/writes, LLM calls,
  tokens — SQLite store + web dashboard, exportable to Langfuse/Postgres.
- Budget by runs/time/iterations/tool-calls with replanning on decline.

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
from ctxloom.sources import FileSystemSource


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


class Echo(Produce[Answer]):
    artifact_type = Answer

    async def produce(self, context, inputs, event=None):
        question = next(a for a in inputs if isinstance(a.data, Question))
        return Patch().create(Answer(text=f"echo: {question.data.text}"))


class EchoAgent(Agent):
    name = "echo"
    consumes = [Consume(Question)]
    produces = [Echo()]


ctx = Context(resources=RuntimeResources(sources={"docs": FileSystemSource("./docs")}))
runtime = Runtime(ctx, agents=[EchoAgent()], budget=Budget(max_runs=10))
ctx.create(Question(text="hello"))  # agents that consume it react automatically
runtime.run()
```

You describe artifacts, what agents consume and produce — and the runtime derives
the execution from state changes. Full documentation lives in [docs/](docs/README.md)
in two languages (English & Русский); the design and invariants are in
[CONSTITUTION.md](CONSTITUTION.md); the `examples/` ship three full demos.

## Examples (in-repo, not shipped)

- `examples/knowledge` — multi-source chat: search → evidence → claim verification → answer,
  with CSV calculation (CLI + FastAPI/SSE web).
- `examples/research` — research agent that *goes to the web* (`WebSource`):
  lazy page fetch → evidence → verified claims → answer with URL provenance.
- `examples/medic-lab` — hypothesis laboratory: a question spawns competing
  hypotheses, each is investigated over an evidence pool, scored by
  support/contradiction, and ended with an HITL steering + honest report.
- `examples/devops` — ops assistant: HITL tool agents + LLM tool router + trace dashboard.
- `examples/repair` — budget-aware replanning demo (chat and data are in Russian by design).
- `examples/forklab` — deterministic branch & merge demo (§39-§40): two research
  strategies on their own forks, explicit three-way merge, evaluate on the merged state.

## Documentation

- [English docs](docs/en/index.md) — concepts, sources, providers, recipes,
  patterns, observability, examples, API reference.
- [Русская документация](docs/ru/index.md) — концепции, источники, провайдеры,
  рецепты, паттерны, наблюдаемость, примеры, справочник API.
- [CONSTITUTION.md](CONSTITUTION.md) — обоснование дизайна и инварианты.

## Development

```bash
uv sync --extra dev --extra web
.venv/bin/python -m pytest
.venv/bin/mypy
.venv/bin/ruff check
```

## License

MIT — see [LICENSE](LICENSE).

The full design rationale and invariants live in [CONSTITUTION.md](CONSTITUTION.md).
