"""Off-the-shelf building blocks for agents — reactive patterns and helpers.

These are not core primitives (Context/Artifact/Patch/Produce stay minimal, the
constitution's primitives-first rule). Instead they are ready-made patterns that
keep reappearing across agent codebases and the bundled examples:

- `fan_out_sources` — query all configured sources, emit ranked, idempotent
  `SourceRef`s tagged with an owner (§8, §24, §42) — see `recipes.search`;
- `materialize_doc` — lazily resolve a `SourceRef` into a document with a
  provenance edge (Reference → Artifact, §6, §34) — see `recipes.resolve`;
- `StatusMachine` — a `Produce` that deterministically advances an artifact's
  `status` lifecycle driven by a pure `next_status(context, key)` (§67, §69) —
  see `recipes.status`;
- `keyword_score` / `stem_words` — deterministic text scoring without
  embedders (English and Russian) — see `recipes.text`;
- `changed_fields` / `earliest_stage` / `downstream_fields` — the
  "change → rebuild" model for multi-stage flows — see `recipes.rollback`;
- `Skill` / `load_skills` / `match_skills` — keyword-triggered instruction
  snippets (Claude-Skills-shaped: name/description frontmatter + body) loaded
  into a prompt when their description matches the situation — see
  `recipes.skills`.

Deterministic where it can be, LLM-free by design; expose the domain hook.
Extend by adding a module here (the package stays import-surface-flat).
"""

from __future__ import annotations

from .resolve import materialize_doc
from .rollback import changed_fields, downstream_fields, earliest_stage
from .search import fan_out_sources
from .skills import Skill, load_skills, match_skills
from .status import StatusMachine
from .text import EN_STOPWORDS, keyword_score, stem, stem_words

__all__ = [
    "EN_STOPWORDS",
    "Skill",
    "StatusMachine",
    "changed_fields",
    "downstream_fields",
    "earliest_stage",
    "fan_out_sources",
    "keyword_score",
    "load_skills",
    "match_skills",
    "materialize_doc",
    "stem",
    "stem_words",
]
