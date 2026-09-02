# Changelog

All notable changes to **ctxloom** are documented here as releases are cut.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/) with `rc` marks for pre-releases.

## [0.3.2-rc1] — 2026-09-02

Patch release on top of 0.3.1.

### Added

- **Cоnfigurable structured completions** — `structured_llm` / `llm_reply` /
  `StructuredLLM` now accept `temperature` and `max_tokens` (defaults stay
  `0.0` / `2048`, backward compatible) for non-zero-`temperature` models or
  longer generations.

---

## [0.3.1-rc1] — 2026-09-01

Patch release on top of 0.3.0.

### Fixed

- **Async tracing end-to-end** — `Tracer.on_turn_end`, sink `export`/`query`/`get`
  are now async. `TraceStore` (SQLite) bridges its core via `asyncio.to_thread`.
- **`PostgresStore` read support** — was write-only (`export`); now also `query`/`get`,
  and the schema grew the `relations` jsonb column to match SQLite. Uses
  `psycopg.AsyncConnection` per operation.
- **`create_trace_router` accepts any `TraceReader`** — the dashboard now works
  against `PostgresStore(dsn)` directly, not just SQLite.
- **`LangfuseTracer` is async** (`httpx.AsyncClient`); `RecordingLLM` unchanged.
- **CLI `ctxloom trace` awaits** the async store.
- Exported `RelationRef` from `ctxloom.tracing`.

### Changed

- Docs (`api.md`, `observability.md`, EN/RU) describe the async interface and the
  Postgres-backed dashboard.

---

## [0.3.0-rc1] — 2026-09-01

Third release candidate — "build your agent in minutes" surface: a ready
app-facing chat layer, a zero-subclass agent factory, and a furnished CLI.
The runtime itself is unchanged (still reactive/effect-driven); this release is
about the ergonomics around it.

### Added

- **Chat layer** — `ChatAssistant` (`ctxloom.chat`): session-persisted turns
  (`stream`/`invoke`/`history`) driven by hooks (`agents`, `user_message`,
  `reply`, `session_state`, `create_message`, `tracer`); transport-agnostic
  building blocks (`run_message`, `default_session_state`).
- **Web router** — `ctxloom.web.create_chat_router(assistant)` mounts the
  canonical SSE chat contract (`/api/chat/stream`, `/api/runs/{id}`, `health`,
  delete) on *your* FastAPI app. FastAPI is imported lazily with a readable
  `pip install "ctxloom[web]"` error when the extra is missing.
- **Error resilience** — the chat layer never leaks a 500: runtime crashes,
  failing reply hooks and session-open errors degrade to a fallback `message`
  (`error: true`) and are logged via the `ctxloom.chat` logger.
- **`create_agent`** — constructor-style agent factory: `Agent` is a thin
  container, no subclassing needed for the common case.
- **Function produces with effects** — `@produce(…)` functions may declare an
  `event`/`effects` parameter (recognized by name) and author the same slot as
  `self.effects`; return-based produces still work.
- **`Context.latest(type)`** — the most recent artifact of a type.
- **Zero-run diagnostic** — a run where no agent reacted prints a one-time hint
  (agents present / consumed types) instead of failing silently.
- **CLI friendliness** — `ctxloom` with no args prints a welcome + how-to,
  `ctxloom --version` reports the release.

### Refactored

- **Examples** — `knowledge`, `research`, `devops`, `repair` web layers rebuilt
  on `ctxloom.chat` + `create_chat_router` (~60% less code each; domain hooks
  only). medic-lab/forkLab stay custom by design.

---

## [0.2.0-rc1] — 2026-08-31

Second release candidate — the framework API is stable at the `0.2` surface,
now ready for wider adoption.

### Added

- **PostgreSQL session backend** — `PostgreSQLKVBackend` (behind the `pg`
  extra): sessions stored in the same Postgres as the application.
- **Readable optional-dependency errors** — `ctxloom._extras.require_extra`:
  missing `pg`/other extras now say
  `pip install "ctxloom[pg]"` / `uv sync --extra pg` instead of a bare
  `ModuleNotFoundError` (applies to the Postgres KV and trace sink).

### Internal

- **CI** — GitHub Actions: checks + wheel smoke (`ci.yml`) and release-on-tag
  (`release.yml`).
- **Release process** — `docs/en|ru/release.md` (versioning, changelog,
  build/verify/publish) and the `ctxloom` console script.

---

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