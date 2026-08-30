# ctxloom

**Reactive, artifact-driven agent runtime.**

`ctxloom` is a framework for building agents as reactive, stateful processes
that transform **versioned, typed, provenance-aware artifacts** inside an
**evolving context** — instead of describing execution as a graph.

```text
ARTIFACT CREATED / UPDATED
       │
       ▼
     AGENTS REACT ──self.effects──► Effects ──compile──► Patch
       ▲                                                      │
       └──────────────────────────────────────────────────────┘
                                                       Context v+1
```

You describe _what data exists, what artifacts exist, what agents can do with
them_. The runtime derives execution from state changes: a produce writes
`self.effects.create/update/link/ask` and returns `None`; the runtime compiles
the effect set into one **atomic** `Patch` and moves the context to the next
version. No explicit graphs, no node pipelines.

## Core primitives

- **Context** — versioned working state, git-like commits, `diff`/`rollback`/`merge`.
- **Artifact** — a first-class typed object (`Claim`, `Evidence`, `Answer`, …),
  not a string blob.
- **Effects** — the produce's authoring surface (`self.effects.create/update/link/ask`); the runtime compiles them into a `Patch`.
- **Patch** — the compiled, validated change-set the runtime applies as one atomic commit (§24).
- **Agent** — a thin container declaring `consumes`/`produces`; logic lives in `Produce`.
- **Source** — a retrieval capability. Vector search is _one_ strategy; direct API,
  keyword, SQL, and filesystem are equally first-class. Embeddings optional.
- **Provenance** — every derived artifact links back to what produced it
  (`Answer —supported_by→ Claim —derived_from→ Evidence —extracted_from→ Doc`).
- **HITL** — humans interact through `effects.ask(...)` → `PendingQuestion`, answered via `effects.resume(...)` like any agent (§60).

## Highlights

- Deterministic work stays deterministic (§67): calculations over structured data
  (`CSVSource` → `Spreadsheet` → `Calculation`) instead of hallucinated numbers.
- Claims carry `confidence` and explicit contradictions (§35–§36), so the model is
  a reasoning component, never the source of truth.
- Observability built in: every run traces agent spans, reads/writes, LLM calls,
  tokens — SQLite store + web dashboard, exportable to Langfuse/Postgres.
- Budget by runs/time/iterations/tool-calls with replanning on decline.

## Also in the box

- **Recipes (`ctxloom.recipes`)** — `fan_out_sources`, `materialize_doc`,
  `StatusMachine`, keyword scoring (EN/RU stems), and the change→rebuild
  rollback helpers — pure, LLM-free.
- **Branching & merge** (§39-§40) — `context.branch()`, three-way `merge()`
  with explicit `MergeConflict`, `BranchStore` over KV.
- **Replay** (§55) — `ReplayLLM` records every LLM call and replays a run
  deterministically; state replay via the CLI.
- **Evaluation harness** (§56) — `ctxloom.eval`: metrics over the final state
  (evidence/claim/provenance/calc/answer), weighted report.
- **Observability** — SQLite trace store + web dashboard (sequence and
  evidence-graph diagrams), Langfuse/Postgres sinks.
- **Viz & CLI** — Mermaid `blueprint`/`context_to_mermaid`/`trace_to_mermaid`;
  `python -m ctxloom` with `graph`/`context`/`trace`/`replay`/`branch`.
- **Sessions & checkpoints** — `SessionStore` over `FileKVBackend`/`SQLiteKVBackend`
  for durable chat memory across requests.

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
        self.effects.create(Answer(text=f"echo: {question.data.text}"))
        return None


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
[CONSTITUTION.md](CONSTITUTION.md); the `examples/` ship several full demos and a tutorial ladder.

## Examples (in-repo, not shipped)

- `examples/knowledge` — multi-source chat: search → evidence → claim verification → answer,
  with CSV calculation (CLI + FastAPI/SSE web).
- `examples/research` — research agent that _goes to the web_ (`WebSource`):
  lazy page fetch → evidence → verified claims → answer with URL provenance.
- `examples/medic-lab` — hypothesis laboratory: a question spawns competing
  hypotheses, each is investigated over an evidence pool, scored by
  support/contradiction, and ended with an HITL steering + honest report.
- `examples/devops` — ops assistant: HITL tool agents + LLM tool router + trace dashboard.
- `examples/repair` — budget-aware replanning demo (chat and data are in Russian by design).
- `examples/forklab` — deterministic branch & merge demo (§39-§40): two research
  strategies on their own forks, explicit three-way merge, evaluate on the merged state.
- `examples/llm_ladder` — the LLM workflow from simplest to state-changing patches
  (3 self-contained levels, offline fallbacks, model mode via `.env`).

## Run a demo

```bash
uv run python ./examples/llm_ladder/level1.py    # the simplest LLM turn (offline too)
uv run python ./examples/repair/web.py           # room renovation: plan, estimate, CSV export
uv run python ./examples/devops/web.py           # HITL ops assistant + trace dashboard
```

## Documentation

- [English docs](docs/en/index.md) — the produce contract & mental model,
  concepts, sources, providers, recipes, patterns, observability, eval,
  branching, replay, viz/CLI, examples, API reference.
- [Русская документация](docs/ru/index.md) — контракт produce и ментальная
  модель, концепции, источники, провайдеры, рецепты, паттерны, наблюдаемость,
  eval, ветвление, replay, viz/CLI, примеры, справочник API.
- [Tutorial · llm-ladder](docs/en/index.md#llm-ladder) — learn the workflow
  from a single LLM call to linked and lifecycle patches.

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
