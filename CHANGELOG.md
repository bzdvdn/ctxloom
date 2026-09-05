# Changelog

All notable changes to **ctxloom** are documented here as releases are cut.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/) with `rc` marks for pre-releases.

## [Unreleased]

### Added

- **`ctxloom.testing`**: a scenario-based behavioral testing harness for agent
  pipelines. `ScenarioLab`/`Scenario` (`ctxloom scenario` CLI) seed artifacts
  into a fresh `Context`, run a `Runtime` to completion, and return a
  `ScenarioResult` with chained assertions (`.artifacts(...)`, `.tools`,
  `.path`, `.llm`, `.errors`). `Scenario` (`lab.scenario()`) supports
  multi-turn conversations on one shared `Context`, for flows that need
  several rounds to reach the state under test.
- Tool fault injection (`lab.fail(tool_name, error, times=None)`) and
  generic resource fault injection (`lab.fail_resource(name, error,
  method=None, times=None)`) — the latter fails the LLM, the embedder, a
  named source, or any `resources.set(...)` value via a duck-typed
  reflection proxy (`ctxloom/testing/mock.py`) that correctly handles sync,
  async, and async-generator methods.
- Record/replay LLM wrapping (`ctxloom/testing/record.py`, reusing
  `ReplayLLM`) and a `@scenario` registry (`ctxloom/testing/registry.py`)
  for discovering and running scenarios via `ctxloom scenario <module>...`.
- Assertion sugar: `ArtifactAssertions.equals/.contains/.field_in`,
  `PathAssertions.any_of/.times`, `ToolAssertions.called_any`.
- Worked examples: `examples/repair/scenarios/`, `examples/knowledge/scenarios/`.

## [0.4.0] — 2026-09-04

Work since 0.4.0-rc1 — internal cleanup, dedupe, and an async-native
checkpoint/session/branch layer. First stable (non-rc) release.

### Breaking

- `Produce(Model, factory=fn)` is deprecated (`DeprecationWarning` on
  construction): it predates `@produce`, only supports `(context, inputs[,
  event]) -> Model | list | Patch | None`, and cannot see the effects slot.
  Still works for existing code; the canonical styles going forward are the
  `Produce` subclass and the `@produce` function.
- Sessions, branches and checkpoints are now **async**: `Session.save`/
  `.delete`, `SessionStore.{save_session,load_session,has_session,
  list_sessions,delete_session,open}`, `BranchStore.{save_branch,load_branch,
  list_branches,delete_branch}`, `Context.{save_checkpoint,load_checkpoint,
  to_kv,from_kv}`, and `replay_context` are all `async def` — call them with
  `await`. `KVBackend`/`CheckpointBackend` and every implementation
  (`File*`, `SQLite*`, `PostgreSQLKVBackend`) follow the same interface
  change; a new `aclose()` releases held connections.

### Added

- **Async checkpoint backends**: `FileKVBackend`/`FileBackend` offload
  blocking file I/O via `asyncio.to_thread`; `SQLiteKVBackend`/
  `SQLiteBackend` share one persistent connection (WAL + `busy_timeout=5000`)
  serialized by an `asyncio.Lock` instead of reconnecting on every call;
  `PostgreSQLKVBackend` moves to psycopg's native `AsyncConnection`. Fixes
  the connection-per-operation overhead and the missing lock-wait timeout
  that could raise `sqlite3.OperationalError: database is locked` under
  concurrent writers.
- `ctxloom/cli/` package: `graph`/`context`/`trace`/`replay`/`branch` are now
  one module each (`add_parser()` + handler) instead of living in a single
  334-line `__main__.py`, which is now a thin entry point.
- `_openai_compat_llm()`/`_openai_compat_embedder()`/
  `_openai_compat_speech()`/`_openai_compat_transcriber()` factory builders
  (`providers/chat.py`, `providers/speech.py`) — the one implementation
  behind every OpenAI-compatible vendor. New vendor coverage verified
  against each vendor's docs: `openrouter_embedder`, `openrouter_speech`,
  `groq_transcriber`, `together_embedder`, `fireworks_embedder`,
  `qwen_embedder`, `nvidia_embedder`. `mistral_llm`/`mistral_embedder` now
  use the same factory instead of hand-rolled env/auth resolution — all 13
  OpenAI-compatible vendors are consistent.
- Retry/backoff (`providers/_retry.py`, `with_retry()`): 429/5xx and
  transport errors now retry with exponential backoff on every network call
  across the package (chat, embeddings, image generation + its URL-fetch
  fallback, TTS, transcription, all four video providers). 4xx is never
  retried; streaming calls are not retried (can't replay already-yielded
  chunks).
- `Runtime(isolate_errors=True, on_agent_error=...)`: one agent's exception
  can skip that agent's patch instead of aborting the whole `arun()`/
  `astream()` — default stays fail-loud. Isolated errors get a traced
  `AgentSpan(error=...)` and count toward `RunStats.errors`.
- `on_error(reason, exc)` hook on `structured_llm`/`llm_reply`/
  `StructuredLLM`, called right before the honest `None` fallback — lets
  callers distinguish "offline" from "the provider is down" without
  changing the `None`-returning contract.
- `effects.upsert(data, id=...)` and `effects.create_once(data, id=...)` —
  explicit names for create-or-refresh and the "already done" idempotency
  guard every `produce` used to hand-roll. `effects.ask(...)` gained an
  optional `id=`.
- `RuntimeResources.aclose()` (duck-typed, closes `llm`/`embedder` if they
  support it) — fixes a real leak where `ChatAssistant` with a callable
  `resources=` built a fresh provider + HTTP client every turn and never
  closed the previous one.
- `providers.from_env(**overrides)`: the `OPENROUTER_API_KEY` → else
  `OPENAI_BASE_URL` → else `None` selection every example hand-rolled as a
  local `build_llm()`.
- `recipes.find(inputs, Model)`/`recipes.find_all(inputs, Model)` — pick the
  typed artifact(s) out of a produce's `inputs` without repeating
  `next(... isinstance ...)`; adopted across the `llm_ladder` examples.
- `recipes.WindowSummarizer`/`recipes.WindowPruner`/`recipes.llm_summarizer` —
  bounded conversation memory (periodic summarization + pruning) as two
  parametrized `Produce`s, generalized from `examples/summarize/main.py`
  (which now uses them instead of its own hand-rolled Summarize/Prune pair).
- `docs/{en,ru}/comparison.md` — ctxloom vs LangGraph/CrewAI, feature by
  feature, and an explicit "where ctxloom is not the right choice" section.
- `docs/{en,ru}/api.md`: a **Stability** section spelling out the pre-1.0
  SemVer contract — public API is `ctxloom.__all__` (and each submodule's own
  `__all__`), everything importable-but-unexported (e.g.
  `ctxloom.relations.RelationGraph`, `ctxloom.commit_log.CommitLog`) carries
  no compatibility guarantee, and breaking changes are always called out in
  `CHANGELOG.md` even pre-1.0.
- `tests/test_cli.py`: the `ctxloom/cli/` package (extracted this release)
  shipped with 0% test coverage — now covered end to end (parser wiring,
  `graph`/`context`/`replay`/`branch`/`trace`, happy paths and the shared
  "store not found" error path).
- `tests/test_checkpoints_concurrency.py`: a concurrent-writer regression
  test for `SQLiteKVBackend`, the scenario the WAL/`busy_timeout` fix above
  targets.

### Changed

- `Context` split: `RelationGraph` (`ctxloom/relations.py`) and `CommitLog`
  (`ctxloom/commit_log.py`) extracted out of the 754-line `Context` god
  object — same public API and behavior, verified against the full suite
  and forklab's branch/merge/conflict path byte-for-byte.
- `SessionStore`/`BranchStore` no longer hand-roll their own
  `to_dict()`/`from_dict()` round-trip over a `KVBackend` — both delegate to
  `Context.to_kv`/`from_kv`.
- `tool_use.py`: `ToolUse`/`ToolUseHITL` extracted a shared `_ToolLoopBase`,
  removing a byte-for-byte duplicated `_run_tool` and init boilerplate.
- Examples: explicit `build_llm()` instead of `llm_from_env()`; manual
  `PendingQuestion` reconstruction replaced by `ctx.resume()`;
  `medic_lab`'s `Consume(condition=...)` replaced by
  `Consume.by_status(Hypothesis, "open")` for consistency with sibling
  examples.
- Docs (EN+RU) synced: `Runtime(isolate_errors, on_agent_error)`, `on_error`,
  `RuntimeResources.aclose()`, `effects.create_once`/`upsert`,
  `providers.from_env`, `retry_attempts`, the new vendor factories, the
  async session/branch/checkpoint API, and produce-style guidance.

### Fixed

- `llm_from_env()`/`embedder_from_env()` silently dropped
  `temperature`/`max_tokens`/`timeout`/`transport`/... overrides instead of
  forwarding them to the provider.
- `VideoProvider.poll()` no longer aborts a multi-minute job on a single
  transient `fetch()` failure — it waits for the next interval and returns
  an honest failed `VideoResult` only once the deadline passes.
- `session.save()`/`store.open()`/`assistant.history()`/
  `store.delete_session()` were being called synchronously from inside
  already-`async` chat/web request handlers (`chat.py`, `web.py`, the
  `medic_lab` example router) — silently blocking the event loop on every
  turn. Now real `await` calls against the async session API.
- `ctxloom/__init__.py`: 15 public names (eval + replay helpers) were
  importable but missing from `__all__`, so `from ctxloom import *` and
  doc/IDE tooling silently dropped them.
- Minor example bugs across `knowledge`, `map_reduce`, `medic_lab`, and
  `repair` produces: a stale re-query re-running the same filter twice
  instead of reusing an already-scoped list, a `Combine` produce that
  cross-joined chunks against summaries instead of a direct id lookup, a
  dead local re-alias, and a duplicated existence check in `repair`'s
  `CollectStage`.
- `SQLiteKVBackend`'s bootstrap (`journal_mode=WAL` + `busy_timeout` pragmas
  on first connect) could itself raise `sqlite3.OperationalError: database is
  locked` when several backends opened the same brand-new file at once —
  changing journal mode is an exclusive operation SQLite does not always
  retry through the busy handler. The one-time bootstrap now retries with
  backoff; the hot-path `execute()` was already correctly serialized.

## [0.4.0-rc1] — 2026-09-02

Minor release — provider-level generation defaults + explicit provider wiring.

### Breaking

- `LLMRequest.temperature` no longer defaults to `0.7` — a `None` now means
  "omit the field, let the provider apply its own default" instead of
  "use `0.7`". Same call shape, different generation behavior, no error
  raised. Pass `temperature=0.7` explicitly (per-call or on the provider) if
  your code relied on the old implicit default. See "Upgrading" in
  [docs/en/release.md](docs/en/release.md).

### Added

- **Provider-level `temperature` / `max_tokens`** — the defaults live on the
  provider instance (`openai_llm(..., temperature=0.7, max_tokens=2048)`), any
  per-call value overrides them, and a `None` at both levels omits the field so
  the API applies its own default. `LLMRequest.temperature` is now `float | None`
  (was a hard-coded `0.7`), ending the 0.7-vs-0.0 drift between call sites.
- Applied across the stack: `structured_llm` / `llm_reply` /
  `LLMAgent` / `HITLLMAgent` / `ToolUse` accept `temperature`/`max_tokens`
  (default `None` = provider default). `OpenAICompatProvider`, `AnthropicProvider`
  and `GeminiProvider` follow the same resolution order
  (call → provider → omit); Anthropic always sends `max_tokens` (API requires
  it, default `4096`).
- **Image provider defaults** — `OpenAICompatImageProvider` takes `n`/`size`/
  `quality` in the constructor; `generate(prompt, size=...)` overrides per call,
  unset fields are omitted.

### Changed

- **Explicit providers in examples** — demos no longer use `llm_from_env()`.
  Each defines a local `build_llm()` picking `openrouter_llm(...)` or
  `openai_llm(...)` explicitly (with `max_tokens=2048`) and returning `None`
  offline. `openai_llm`/`openrouter_llm` now tolerate `base_url`/`model` as
  `None` (defaults applied) and return `None` without a key, so demos stay
  offline-capable.

---

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