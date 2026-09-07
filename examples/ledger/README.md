# ledger — edit one fact, only its real dependents recompute

A tiny cost model (hours × rate → labor cost → tax/discount → total) that
exists to make one point concretely, with numbers, not by assertion:
**dependencies here are declared on artifact types, not wired between
nodes that share one blob of state** — so editing one fact recomputes
exactly what actually consumed it, and nothing else, for free.

No LLM anywhere in this demo — deterministic by design (§67), so the
proof is unambiguous: `Artifact.version` (built into every artifact,
`ctxloom/artifacts.py`) increments only when something is genuinely
recomputed.

## Run

```bash
.venv/bin/python -m examples.ledger.main
```

```
--- initial calculation ---
  LaborCost    value=500.0      version=0
  Tax          value=40.0       version=0
  Discount     value=25.0       version=0
  Total        value=515.0      version=0

>>> editing ONLY TaxRate (0.08 -> 0.12) — a fact nothing about
>>> LaborCost or Discount ever consumed.

--- after editing TaxRate ---
  LaborCost    value=500.0      version=0   ← untouched
  Tax          value=60.0       version=1   ← recomputed
  Discount     value=25.0       version=0   ← untouched
  Total        value=535.0      version=1   ← recomputed (consumes Tax)
```

`LaborCost` and `Discount` don't consume `TaxRate` — they are never even
*invoked* for this edit, not invoked-and-decided-not-to-update. Editing
`Hours` instead correctly cascades through everything, because everything
really does depend on it transitively through `LaborCost` — the model
isn't "isolated," it's *precise*.

## Why this needs artifact-level dependencies, not node/state ones

In LangGraph, state is one shared `TypedDict` that flows through nodes
connected by edges; a node doesn't declare "I read field X" anywhere the
framework can see — it just receives the whole state object. So the
framework has no way to know that a `tax` node never touched `discount`'s
inputs; if you want "only recompute what changed" you're back to either:

- re-running the whole downstream path on any edit (coarse — you lose the
  precision this demo shows), or
- hand-rolling a dependency tracker yourself (dirty flags, a manual DAG,
  `Command(goto=...)` to selectively re-enter specific nodes) — which is
  exactly the bookkeeping `Consume`/`consumes` gives you for writing one
  small class per formula.

Here, `tax_agent.consumes = [Consume(LaborCost), Consume(TaxRate)]` *is*
the dependency declaration — the runtime derives "what needs to run" from
which artifact type an `ARTIFACT_UPDATED` event carries, matched against
every agent's own declared `consumes`. No router function anywhere
enumerates "if X changed, also rerun Y, Z" — that logic doesn't exist as a
separate thing to maintain; it's just wherever `Consume(X)` appears.

One honest caveat: convergence isn't always a single step. Editing `Hours`
made `Total` jump from version 0 to version 3, not straight to 1 — because
`Tax`/`Discount`'s updates land in separate passes as the fixpoint settles,
and `Total` reacts to each. Same phenomenon a spreadsheet's own multi-pass
recalculation engine has; it doesn't undermine the core claim (`LaborCost`/
`Discount` really do stay at version 0 when only `TaxRate` changes), but a
sharper reader will ask, so it's stated here rather than glossed over.

## See also

`examples/forklab` is the other half of "artifacts + their state, not nodes
with one state" story: two independent strategies explored on
`context.branch()`ed copies, then reconciled with a real three-way
`merge()` (explicit `MergeConflict` when both forks touch the same
artifact, no silent last-write-wins). That's not just "awkward" in
LangGraph — a checkpointer is linear time-travel through one thread's
history, not git-like divergent branching with a real merge; there's no
comparable primitive to point at.

## Structure

```
ledger/
├── models.py    # Hours, Rate, TaxRate, DiscountRate (facts) + LaborCost, Tax, Discount, Total (derived)
├── produce.py   # one produce per formula — the Consume(...) list IS the dependency graph
├── agents.py    # AGENTS list
└── main.py      # the demo: initial calc, edit TaxRate, edit Hours, edit nothing (no-op)
```
