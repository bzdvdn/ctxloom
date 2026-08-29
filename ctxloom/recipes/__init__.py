"""Off-the-shelf building blocks for agents — reactive patterns (§46).

These are not core primitives (Context/Artifact/Patch/Produce stay minimal, the
constitution's primitives-first rule). Instead they are ready-made patterns that
keep reappearing across agent codebases and the bundled examples:

- `fan_out_sources` — query all configured sources, emit ranked, idempotent
  `SourceRef`s tagged with an owner (§8, §24, §42) — see `recipes.search`;
- `materialize_doc` — lazily resolve a `SourceRef` into a document with a
  provenance edge (Reference → Artifact, §6, §34) — see `recipes.resolve`;
- `StatusMachine` — a `Produce` that deterministically advances an artifact's
  `status` lifecycle driven by a pure `next_status(context, key)` (§67, §69) —
  see `recipes.status`.

Deterministic where it can be, LLM-free by design; expose the domain hook.
Extend by adding a module here (the package stays import-surface-flat).
"""

from __future__ import annotations

from .resolve import materialize_doc
from .search import fan_out_sources
from .status import StatusMachine

__all__ = [
    "StatusMachine",
    "fan_out_sources",
    "materialize_doc",
]
