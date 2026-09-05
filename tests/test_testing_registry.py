"""`ctxloom.testing.registry.collect()` — repeated calls in one process must
keep returning the same scenarios.

Regression: `collect()` used to clear `_REGISTRY` and then call a plain
`importlib.import_module(name)`, which is a no-op for a module already in
`sys.modules` — so a second `collect()` call for the same module(s) in one
process silently returned an empty list (the `@scenario` decorators never
re-ran against the freshly cleared registry). This matters most for a
scenarios *package* (e.g. `examples.repair.scenarios`), where the decorators
live in already-imported submodules, not the package's own `__init__.py`.
"""

from __future__ import annotations

from ctxloom.testing.registry import collect


def test_collect_is_idempotent_for_a_flat_module():
    first = collect(["examples.knowledge.scenarios"])
    second = collect(["examples.knowledge.scenarios"])
    assert len(first) == len(second) > 0
    assert {c.name for c in first} == {c.name for c in second}


def test_collect_is_idempotent_for_a_scenarios_package():
    # examples.repair.scenarios is a package whose @scenario functions live
    # in submodules (greeting.py, estimate.py, ...), not in __init__.py.
    first = collect(["examples.repair.scenarios"])
    second = collect(["examples.repair.scenarios"])
    third = collect(["examples.repair.scenarios"])
    assert len(first) == len(second) == len(third) > 0
    assert {c.name for c in first} == {c.name for c in third}


def test_collect_across_multiple_modules_stays_stable_on_repeat():
    modules = ["examples.repair.scenarios", "examples.knowledge.scenarios"]
    first = collect(modules)
    second = collect(modules)
    assert len(first) == len(second) > 0
