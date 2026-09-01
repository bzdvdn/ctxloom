# ctxloom

**Stop drawing the graph. Build agents as reactions to versioned, provable artifacts.**

[![CI](https://github.com/bzdvdn/ctxloom/actions/workflows/ci.yml/badge.svg)](https://github.com/bzdvdn/ctxloom/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/bzdvdn/ctxloom)
[![PyPI version](https://img.shields.io/pypi/v/ctxloom)](https://pypi.org/project/ctxloom/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Most agent frameworks make you **draw the graph**: connect nodes, wire memory,
declare control flow. But a knowledge question — *"why did infra costs jump in
Q2?"* — needs Confluence + GitLab + CSV + calculations + verification, and the
*next* question needs a different path. There is no universal graph to draw.

ctxloom flips the model. You describe **what artifacts exist and what agents can
do with them**; the runtime derives what runs next from **state changes**. Agents
react to events — there is no graph, no node pipeline.

```python
from pydantic import BaseModel

from ctxloom import Budget, Consume, Context, Runtime, RuntimeResources, create_agent, produce
from ctxloom.sources import FileSystemSource


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


@produce(Answer)
async def echo(context, inputs, event, effects):
    question = next((a for a in inputs if isinstance(a.data, Question)), None)
    if question is None:
        return None
    effects.create(Answer(text=f"echo: {question.data.text}"))


echo_agent = create_agent("echo", consumes=[Consume(Question)], produces=[echo])

ctx = Context(resources=RuntimeResources(sources={"docs": FileSystemSource("./docs")}))
runtime = Runtime(ctx, agents=[echo_agent], budget=Budget(max_runs=10))
ctx.create(Question(text="hello"))  # agents that consume it react automatically
runtime.run()

print(ctx.latest(Answer).data.text)  # "echo: hello"
```

## How it works

```text
ARTIFACT CREATED / UPDATED
       │
       ▼
     AGENTS REACT ──self.effects──► Effects ──compile──► Patch
       ▲                                                      │
       └──────────────────────────────────────────────────────┘
                                                        Context v+1
```

A produce writes what should change (`self.effects.create/update/link/ask`) and
returns `None`; the runtime compiles the effect set into one **atomic** `Patch`
and moves the context to the next version. The `event` that wakes an agent is
*derived* from that same change — the causal chain can never drift from the
actual state.

## What makes it different

| Traditional agent (LangGraph / CrewAI / LangChain) | ctxloom |
| --- | --- |
| A program follows a graph / plan | Agents **react** to state changes |
| Messages are strings | **Typed, versioned artifacts** (`Claim`, `Evidence`, `Answer`) |
| Orchestration is explicit wiring | Orchestration **falls out of the state** |
| A unit of work *returns* a change | An agent **writes effects**; the runtime compiles them |
| Retries/rollback are manual | Context is **git-like versioned** (diff, rollback, branch, merge) |
| "Who produced this?" is lost | **Provenance** links every derived artifact to its inputs |
| The model guesses the numbers | **Calculations are calculated** — the LLM is a reasoning component, not the source of truth |

Reactive. Deterministic. Accountable.

## Core primitives

- **Context** — versioned working state, git-like commits, `diff`/`rollback`/`merge`.
- **Artifact** — a first-class typed object (`Claim`, `Evidence`, `Answer`), not a string blob.
- **Effects** — an agent states its change via `self.effects.create/update/link/ask`; the runtime compiles it.
- **Patch** — the compiled, validated change-set applied as one atomic commit.
- **Agent** — a thin container declaring `consumes`/`produces`; logic lives in a `Produce`.
- **Source** — retrieval is a capability: vector search is *one* strategy; direct API, keyword, SQL, filesystem are equally first-class.
- **Provenance** — every derived artifact links to what produced it
  (`Answer —supported_by→ Claim —derived_from→ Evidence —extracted_from→ Doc`).
- **HITL** — humans as `effects.ask(...)` → `PendingQuestion`, answered via `effects.resume(...)` like any agent.

## In the box

- **Deterministic by design** — calculations over structured data, honest `None`
  fallbacks instead of hallucinated answers; the model reasons, never "knows".
- **Observability** — every run traces agent spans, reads/writes, LLM calls,
  tokens: SQLite store + web dashboard, exportable to Langfuse/Postgres (async sinks).
- **Budgets & replanning** — cap by runs/time/iterations/tool-calls, replan on decline.
- **Branching & replay** — `context.branch()`, three-way `merge()`, deterministic
  `ReplayLLM`, all for audit and safe alternative states.
- **Sessions** — `SessionStore` over `FileKVBackend`/`SQLiteKVBackend`
  (and `PostgreSQLKVBackend`) for durable chat memory.
- **Web layer** — `ChatAssistant` + `create_chat_router` mount a canonical SSE
  chat on *your* FastAPI app; errors degrade to a logged fallback, never a 500.
- **Recipes** — `fan_out_sources`, `materialize_doc`, `StatusMachine`, change→rebuild
  rollback helpers — pure, LLM-free.
- **Viz & CLI** — Mermaid `blueprint`/`context_to_mermaid`/`trace_to_mermaid`;
  `ctxloom` with `graph`/`context`/`trace`/`replay`/`branch`.

## Run a demo

Offline-capable, no API keys required (deterministic fallbacks):

```bash
uv run python ./examples/llm_ladder/level1.py  # the simplest LLM turn (offline too)
uv run python ./examples/repair/web.py         # room renovation: plan, estimate, CSV export
uv run python ./examples/devops/web.py         # HITL ops assistant + trace dashboard
```

Classic-pattern ports run as one-liners too:
`python -m examples.{reflection,map_reduce,supervisor,summarize,time_travel,adaptive}.main`.

## Examples (in-repo, not shipped)

- `knowledge` — multi-source chat: search → evidence → claim verification → answer, with CSV calculation.
- `research` — goes to the web (`WebSource`): lazy page fetch → evidence → verified claims → answer with URL provenance.
- `medic-lab` — hypothesis laboratory: competing hypotheses scored, HITL steering, honest report.
- `devops` — HITL tool agents + LLM tool router + trace dashboard.
- `repair` — budget-aware replanning (chat/data in Russian by design).
- `forklab` — deterministic branch & merge: two strategies on their own forks, three-way merge.
- `llm_ladder` — the workflow from one LLM call to state-changing patches (3 levels).
- `adaptive` — hybrid scheduler: rule filters + deterministic rank + LLM tie-break + `rank_limit`.
- `{reflection,map_reduce,supervisor,summarize,time_travel}` — canonical ports (see [port-matrix](docs/en/port-matrix.md)).

## Documentation

- [English](docs/en/index.md) · [Русский](docs/ru/index.md) — concepts, sources,
  providers, recipes, patterns, observability, eval, branching, replay, viz/CLI, API.
- [Why ctxloom](docs/en/why-ctxloom.md) — the *design argument*: why effects, why no graph, why determinism.
- [Tutorial · llm-ladder](docs/en/index.md#llm-ladder) — learn the workflow.
- [CONSTITUTION.md](CONSTITUTION.md) — the full design rationale and invariants.

## Development

```bash
uv sync --extra dev --extra web
.venv/bin/python -m pytest
.venv/bin/mypy
.venv/bin/ruff check
```

## License

MIT — see [LICENSE](LICENSE).
