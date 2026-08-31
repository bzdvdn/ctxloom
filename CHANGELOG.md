# Changelog

All notable changes to **ctxloom** are documented here as releases are cut.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/) with `rc` marks for pre-releases.

## [0.1.0-rc1] — 2026-08-31

First release candidate — the framework is ready for early adoption in
real projects. Everything runs offline (deterministic fallbacks) or with an
LLM via `.env`.

### Added — core

- **Effects authoring (§24)**: `Produce` writes `self.effects.create/update/
  link/ask/resume` and returns `None`; the runtime compiles the effect set into
  one atomic `Patch` (commit, events, validation, trace). `Patch` is the
  runtime's transport; `Operation` types moved to `ctxloom.operations`.
- **HITL (§60)**: `effects.ask(...)` → `PendingQuestion`, answered with
  `effects.resume(...)`; `InterruptPatch` removed.
- **Recipes `ctxloom.recipes`**: `fan_out_sources`, `materialize_doc`,
  `StatusMachine`, `keyword_score`/`stem_words` (EN/RU), change→rebuild
  rollback helpers.
- **Branching & merge (§39-§40)**: `Context.branch()`, three-way `merge()`
  with explicit `MergeConflict`, `BranchStore` over KV, CLI.
- **Replay (§55)**: `ReplayLLM` record/replay, deterministic state replay.
- **Evaluation harness (§56)**: `ctxloom.eval` — multi-level metrics over the
  final state.
- **Adaptive scheduling (§26, §24)**: `Runtime(scheduler=…)` —
  filter (rules) → deterministic rank → LLM tie-break (app-owned system
  prompt) → optional top-k; HITL-resume is always pinned; `Agent.capabilities`.
- **Structured I/O**: `structured_llm`, `StructuredLLM`, `llm_reply`,
  `PromptTemplate`/`MessagesPrompt`, typed `Message` roles + factories.
- **Auto-derived `artifact_type`** from `Produce[Foo]`.
- **Observability (§54)**: SQLite trace store, dashboard with sequence and
  evidence-graph (Mermaid), Langfuse/Postgres sinks.
- **Viz & CLI**: `blueprint`/`context_to_mermaid`/`trace_to_mermaid` and
  `python -m ctxloom {graph,context,trace,replay,branch}`.
- **Providers**: OpenAI-compatible chat/embedder + Anthropic, Gemini, Mistral,
  OpenRouter, Groq, xAI, DeepSeek, Azure, and more; image/speech/video; fakes.
- **`ctxloom` console script** (`uv add` → `ctxloom graph …`).

### Added — examples (in-repo, not shipped)

`knowledge` · `research` · `medic-lab` · `devops` · `repair` (Russian by
design, with plan/estimate UI + CSV export) · `forklab` (branch/merge) ·
`llm_ladder` (learning path) · canonical-pattern ports: `reflection`,
`map_reduce`, `supervisor`, `summarize`, `time_travel`, `adaptive`.

### Changed

- `Produce` no longer returns `Patch`; effects are the authoring surface.
- `Agent.execute` runs produces; the runtime compiles the effects slot.
- `MergeConflict`, `ReplayLLM`, `ctxloom.eval`, scheduler — new core surface.

### Removed

- `InterruptPatch`, `Patch.merge_existing_patch`, `Patch.to_dict`, `examples/plan`.

### Notes

- Requires Python ≥ 3.11; only `pydantic>=2.13` is mandatory at runtime.
- `uv build` ships only the `ctxloom` package (examples/tests stay in-repo).