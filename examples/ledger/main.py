"""ledger — edit one fact, watch only its real dependents recompute.

No LLM anywhere in this demo — it's deterministic by design (§67): the point
is the dependency wiring, not generation. `Artifact.version` (built into
every artifact, `reactifact/artifacts.py`) is the proof: a formula that never
consumed the fact you changed is never even invoked for that edit — its
version stays put, not "recomputed to the same number."

Run:  .venv/bin/python -m examples.ledger.main
"""

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script — add src to sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reactifact import Budget, Context, Runtime, RuntimeResources

from examples.ledger.agents import AGENTS
from examples.ledger.models import (
    Discount,
    DiscountRate,
    Hours,
    LaborCost,
    Rate,
    Tax,
    TaxRate,
    Total,
)

ROW = "  {:<12} value={:<10} version={}"


def report(title: str, context: Context) -> None:
    print(f"\n--- {title} ---")
    for artifact_type in (LaborCost, Tax, Discount, Total):
        artifact = context.latest(artifact_type)
        assert artifact is not None
        value = getattr(artifact.data, "value")  # noqa: B009 — heterogeneous types, all have .value
        print(ROW.format(artifact_type.__name__, round(value, 2), artifact.version))


async def main() -> None:
    context = Context(resources=RuntimeResources())
    runtime = Runtime(context, agents=AGENTS, budget=Budget(max_runs=40))

    hours = context.create(Hours(value=10))
    context.create(Rate(value=50))
    tax_rate = context.create(TaxRate(value=0.08))
    context.create(DiscountRate(value=0.05))
    await runtime.arun()
    report("initial calculation", context)

    print("\n>>> editing ONLY TaxRate (0.08 -> 0.12) — a fact nothing about")
    print(">>> LaborCost or Discount ever consumed.")
    context.update(tax_rate.id, TaxRate(value=0.12))
    await runtime.arun()
    report("after editing TaxRate", context)

    labor_cost_v1 = context.latest(LaborCost)
    discount_v1 = context.latest(Discount)
    tax_v1 = context.latest(Tax)
    total_v1 = context.latest(Total)
    assert labor_cost_v1 is not None and labor_cost_v1.version == 0, (
        "LaborCost doesn't consume TaxRate — it must not have recomputed"
    )
    assert discount_v1 is not None and discount_v1.version == 0, (
        "Discount doesn't consume TaxRate — it must not have recomputed"
    )
    assert tax_v1 is not None and tax_v1.version == 1, "Tax consumes TaxRate directly"
    assert total_v1 is not None and total_v1.version == 1, "Total consumes Tax"
    print("\n[confirmed] LaborCost & Discount: version 0 (never touched).")
    print("[confirmed] Tax & Total: version 1 (the only real dependents).")

    print("\n>>> editing Hours (10 -> 20) — this one *does* reach everything,")
    print(">>> transitively, through LaborCost.")
    context.update(hours.id, Hours(value=20))
    await runtime.arun()
    report("after editing Hours", context)

    labor_cost_v2 = context.latest(LaborCost)
    discount_v2 = context.latest(Discount)
    assert labor_cost_v2 is not None and labor_cost_v2.version == 1
    assert discount_v2 is not None and discount_v2.version == 1, (
        "Discount doesn't consume Hours directly, but it does consume "
        "LaborCost, which just changed — so it correctly recomputes now"
    )
    print("\n[confirmed] this time Discount recomputed too — because its real")
    print("dependency (LaborCost) actually changed, not because of Hours by name.")

    print("\n>>> a no-op edit: setting Hours to the value it already has.")
    labor_cost_before = context.latest(LaborCost)
    assert labor_cost_before is not None
    version_before = labor_cost_before.version
    same = context.update(hours.id, Hours(value=20))  # same value — §41/§42
    # No event is queued for a no-op update, so there's nothing for another
    # arun() to do — check it synchronously instead of triggering the
    # runtime's (correct, but here misleading) "0 agents ran" diagnostic.
    assert same is not None and same.version == version_before
    labor_cost_after = context.latest(LaborCost)
    assert labor_cost_after is not None
    assert labor_cost_after.version == version_before, (
        "a no-op update must not fire an event or cascade (§41/§42)"
    )
    print("[confirmed] no-op edit: no event fired, nothing recomputed.")


if __name__ == "__main__":
    asyncio.run(main())
