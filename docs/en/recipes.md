# Recipes

`ctxloom.recipes` contains reusable building blocks that encode patterns which
recur in every demo. Importing `ctxloom.recipes` does not pull in additional
dependencies — everything is built on the core.

## `fan_out_sources` — reactive search

```python
from ctxloom.recipes import fan_out_sources

patch, refs = await fan_out_sources(
    context,
    query=question,
    owner_id=query_id,           # scope refs to the owning turn
    limit=5,
    query_id=query_id,           # owner key for provenance
    on_start=lambda source: context.announce(
        f"Searching {source}…", kind="status"
    ),
    on_count=lambda source, n: context.announce(
        f"{source}: {n} hits", kind="status"
    ),
)
```

What it does:

1. Fans out to **every configured source** in `context.resources.sources`.
2. Ranks the combined `SourceRef`s by score (highest first).
3. Builds a patch of **idempotent, owner-scoped refs** —
   `id=f"ref:{ref.stable_id()}:{owner_id}"`.

Idempotency matters: the caller runs a search once per turn (guarded by its own
marker) but may *re-run* on retries; the same ids are re-created, never
duplicated. `on_start` / `on_count` give you progress announces over SSE.

## `materialize_doc` — lazy reference resolution

```python
from ctxloom.recipes import materialize_doc

async def doc_from_ref(context, ref_artifact, content) -> TypedDoc:
    # build your domain document from the fetched content
    return TypedDoc(query_id=ref_artifact.data.query_id, path=..., text=content)

patch = await materialize_doc(
    context,
    ref_artifact,
    doc_from_ref,
    relation="resolved_from",    # default: materialized_from
)
```

Because sources return *references*, not payloads, documents are fetched
**lazily, only when needed** — the rule in the research demo is "resolve a page
only after the model ranks it relevant". A missing source or a resolve failure
yields `None` (an honest no-op), never a crash, and the failure is surfaced in
the run trace.

The produced document is linked back:
`TypedDoc ──resolved_from──► SourceRef` (§34), so the provenance walk
`Answer → Claim → Evidence → Doc → SourceRef` stays complete.

## `StatusMachine` — deterministic lifecycles

Status machines are the pattern for "an artifact that moves through states"
(a research turn: `researching → answerable → answered`). Instead of a manual
transition graph, a `StatusMachine` is a **pure function of current state**:

```python
from ctxloom import Artifact, Context
from ctxloom.recipes import StatusMachine


class EvaluateTurn(StatusMachine[ResearchTurn]):
    artifact_type = ResearchTurn                 # what it advances
    terminal = frozenset({"answered", "insufficient"})  # where it stops
    query_id_field = "query_id"                  # owner key field (default)
    status_field = "status"                      # status field (default)

    def next_status(self, context: Context, key: str) -> str | None:
        """Pure function: which status the lifecycle deserves now."""
        if any(a.data.query_id == key for a in context.list_artifacts(Answer)):
            return "answered"
        return None

    def on_transition(self, context, key, old_status, new_status) -> None:
        context.announce(f"Research status: {old → new}",
                         kind="status", query_id=key)
```

Mechanics (all inherited from `produce`):

- Woken by any event; the event maps to a lifecycle via `owner_key` (reads
  `query_id_field` of the artifact data, falling back to its `id`).
- Picks the first matching `artifact_type` artifact; `terminal` statuses stop
  the machine.
- `next_status` decides the new status; `None` or unchanged ⇒ nothing happens.
- Right before applying the change, `on_transition` is called — your hook for
  progress announces.
- The final patch is `update_fields(target, **{status_field: new})`.

Put your *verify* logic into another `produce` that react on status changes —
the machine and the verifier are separate, deterministic, and unit-testable.
The knowledge/research demos' `EvaluateTurn` are the canonical instance of
this recipe.