# Concepts

The full design rationale lives in
[CONSTITUTION.md](../../CONSTITUTION.md). This page is the operative overview:
the six building blocks and how they interact.

## 1. Context

`Context` is the versioned working state. Like git, it keeps a history of
commits, each commit being the result of applying one or more **patches**.

```python
from ctxloom import Context, RuntimeResources
from ctxloom.sources import FileSystemSource

ctx = Context(
    resources=RuntimeResources(
        sources={"docs": FileSystemSource("./docs")},
    )
)
```

Key capabilities:

| Capability | Purpose |
| --- | --- |
| `create / update / delete` | encode intent (delegated per-run to agents) |
| `list_artifacts(Model)` | query the current state by artifact type |
| `view((M1, M2), condition=…)` | query a type join for decisions/chat memory |
| `related(artifact_id, relation)` | walk the provenance graph |
| `announce(message, kind=…)` | emit a progress/status event to the UI |
| `diff / rollback / merge` | inspect or unwind history; merge forks |

`Context.resources` carries what is *not* state: providers (the LLM, an
embedder), sources, and arbitrary app resources (a price catalog, an image
directory). Agents read them; they never persist them.

## 2. Artifact

An `Artifact` is the pair `(id, data, created_at, …)` where `data` is a
`pydantic` model. Artifacts are **first-class objects**, not string blobs.

```python
class Evidence(BaseModel):
    query_id: str
    source: str
    text: str
    score: float
```

Rules of thumb:

- Every artifact has a stable `id`. Prefer stable ids over random ones
  (`answer:{query_id}`, `ref:{stable_id}:{owner}`) — idempotency and
  provenance linking become trivial.
- `query_id` is the conventional owner key when many artifacts belong to one
  workflow turn (a question, a research turn). Recipes and examples rely on it.
- Artifacts are immutable as *data*; change is expressed through patches that
  create new versions.

## 3. Patch

`Patch` is the only language agents use to express a change:

```python
patch = Patch()
patch.create(Answer(query_id=qid, text=text), id="answer:q1")
patch.link("answer:q1", "supported_by", evidence_id)
patch.update_fields(some_artifact, status="answered")
patch.delete(old_artifact)
return patch
```

Operations:

| Op | Signature / meaning |
| --- | --- |
| `create` | add an artifact (optionally with a chosen `id`) |
| `update` / `update_fields` | record an edit on an artifact |
| `delete` | remove an artifact |
| `link` | connect `id → rel → other_id` (provenance) |
| `unlink` | remove a relation |

`Patch.merge_existing_patch(a, b)` composes several changes into one patch —
the demos return e.g. *update the project* + *create a reply* in a single patch.

`InterruptPatch` is the special HITL patch: it creates a `PendingQuestion`,
stops the run, and records an answer when execution resumes (see
[patterns](patterns.md)).

## 4. Agent

An `Agent` is a **thin container**: it declares what it reacts to and what it
can produce. The logic lives in `Produce` classes.

```python
class RepairFlow(Agent):
    name = "repair_flow"
    consumes = [Consume(UserMsg), Consume(Project)]
    produces = [
        CollectStage(), PickStage(), PlanStage(),
        EstimateStage(), ApprovalStage(), AssistantStage(),
        Produce(ChatReply), Produce(PendingQuestion),
    ]
```

- `consumes` — artifact types that wake this agent.
- `produces` — `Produce` instances that may run when the agent is awake.
- The runtime wakes agents on events, respecting budget and concurrency.

## 5. Produce

`Produce[M]` is where the work happens. It is a **stateless function** from the
current context (plus the triggering event) to a patch.

```python
class EstimateStage(Produce[Project]):
    artifact_type = Project

    async def produce(self, context, inputs, event=None) -> Patch | None:
        ...
        return Patch().update_fields(project_art, {"stage": "estimate"})
```

Convention: **determinism first** (§67). Whether a stage is eligible is decided
by a guard — `if project.stage != "estimate": return None`. Whether it should
change is a pure function of state. LLM use is reserved for genuinely
generative tasks and is always wrapped with a structured schema and a fallback.

A `Produce` can also take dependencies it needs to run before it via the
`depends_on`/`inject` mechanism — see the [API reference](api.md).

## 6. Provenance

Every derived artifact links to what produced it. The runtime records
**reads and writes** automatically; your code adds domain relations via
`patch.link`:

```text
Answer ──supported_by──► Claim ──derived_from──► Evidence ──extracted_from──► Doc
```

Why this matters:

- **Explainability** — "show your sources" is a query over relations, not LLM
  memory.
- **Scoring** — an answer's strength is the conjunction of its claims'
  confidence and their evidence support.
- **Deterministic auditing** — every run trace includes the reads/writes of each
  agent span.

## Supporting pieces

- **`Budget` / `RunOutcome` / `RunStats`** — limit runs, iterations, and time;
  on budget decline the runtime stops and reports the reason.
- **`Event` / `EventType`** — the wire format of "something changed"; agents are
  woken by artifacts' create/update events, and the announce mechanism emits
  `status` events on the way to the UI.
- **`Trigger`** — secondary enter conditions for a produce (e.g. a periodic or
  timer-based wake), independent of the artifact consums.
- **`Session` / `SessionStore`** — durable, per-chat working memory across
  requests, backed by a KV checkpoint (file or SQLite).