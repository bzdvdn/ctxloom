# API reference

Top-level symbols exported by `ctxloom` (see `ctxloom/__init__.py`). The format
for each group: name — one-line role. Details live in the doc-strings of the
modules.

## Context & state

| Symbol | Role |
| --- | --- |
| `Context` | versioned working state; resources; queries; `latest(Model)`; announce; diff/rollback |
| `View` | result of a typed join query (`context.view(...)`) |
| `RuntimeResources` | providers + sources + arbitrary app resources |
| `Commit`, `Read`, `Write` | version bookkeeping and recorded provenance ops |

## Artifacts & changes

| Symbol | Role |
| --- | --- |
| `Artifact` | the `(id, data)` pair; `data` is a pydantic model |
| `Patch` | the runtime's compiled change-set (transport); produces write `self.effects`, `Patch` is assembled by the runtime |
| `ctxloom.operations` (`Create`/`Update`/`Delete`/`Link`/`Unlink`/`Relation`) | the compiled operations a patch carries (§12) |
| `Create`, `Update`, `Delete`, `Link`, `Unlink`, `Relation` | op records from which patches are built |

## Agents & produces

| Symbol | Role |
| --- | --- |
| `Agent` | thin container: `name`, `consumes`, `produces`, `concurrency_limit` |
| `create_agent` | constructor-style Agent builder — no subclassing needed for plain containers |
| `Consume` / `consume` | declarative (or decorator) reaction declaration; `Consume.by_field` for scoped events |
| `Produce` / `produce` | the work unit: writes `self.effects` (or `effects` slot in a decorated function) → `None`; model/Patch return is compiled too |
| `Trigger` | secondary (non-artifact) enter condition for a produce |
| `StructuredGenerateAgent` | declarative LLM→schema→artifact agent (`schema`, `build_prompt`, `fallback`) |
| `LLMAgent` | blocking LLM+tools loop (`system`, `tools`, `max_steps`) |
| `HITLLMAgent` | LLM+tools loop that can pause for human answers (`max_asks`, resume reporting) |
| `ToolUse`, `ToolUseHITL` | the tool-loop produce; HITL variant waits for approval on execution |
| `Tool`, `FunctionTool`, `tool`, `ToolOutput` | tool abstraction and registration |
| `ToolAnswer`, `Observation` | tool results and model observations (loop protocol) |

## Runtime

| Symbol | Role |
| --- | --- |
| `Runtime` | wakes agents on events; `run` / `arun` / `astream`; budget & concurrency |
| `Budget`, `RunOutcome`, `RunStats` | run limits and the final outcome/stats |
| `Event`, `EventType` | the wire format of "something changed" |
| `EventHub`, `ProgressEvent` | progress/announce channel consumed by web UIs |

## Chat layer (ctxloom.chat + ctxloom.web)

| Symbol | Role |
| --- | --- |
| `ChatAssistant` | sessions + turn loop + history in one handle (`stream`/`invoke`/`history`); hooks: `agents`, `user_message`, `reply`, `session_state` |
| `ChatEvent` | one transport-neutral frame (`session`/`status`/`message`) |
| `run_message(runtime, text, *, user_message, reply)` | the turn building block: create input → stream statuses → terminal reply |
| `default_session_state(ctx, user_message)` | generic history reader (any artifact with `.text`) |
| `create_chat_router(assistant)` | FastAPI `APIRouter` for the canonical SSE contract (`/api/chat/stream`, `/api/runs/{id}`) — needs the `web` extra |
| `ctxloom.web.sse(event, data)` | one SSE frame |

## Visualization (ctxloom.viz + python -m ctxloom)

| Symbol | Role |
| --- | --- |
| `blueprint(agents)` | static map of consumes/produces as Mermaid `flowchart` |
| `context_to_mermaid(context)` | live provenance graph of a context (artifacts + relations) |
| `trace_to_mermaid(trace)` | one run as a Mermaid `sequenceDiagram` |
| `python -m ctxloom graph\|context\|trace` | CLI printing the diagrams to stdout |
| `trace_provenance_to_mermaid(trace)` | a run's evidence graph (written artifacts + `patch.link` edges) |

## Replay (ctxloom.replay, §55)

| Symbol | Role |
| --- | --- |
| `ReplayLLM(recording, mode="record"\|"replay", inner=…)` | records every LLM call to JSONL, or replays them exactly; `ReplayMiss` on divergence |
| `ReplayMiss` | a replaying call did not match the recording |
| `replay_context(store, session_id, version=None)` | reconstructs a saved session's state at a commit |
| `replay_summary(context)` | compact state summary for the `replay` CLI |

## Branching (ctxloom.context + ctxloom.branching, §39-§40)

| Symbol | Role |
| --- | --- |
| `Context.branch(name="")` | forks an isolated copy; records the base snapshot for three-way merge |
| `Context.merge(other, message=…)` | atomic three-way merge; `MergeConflict` on diverged artifacts |
| `MergeConflict` | raised when both sides changed an artifact differently since the fork |
| `BranchStore(KVBackend)` | persists branches as `branch:<session>:<name>` over a KV backend |
| `python -m ctxloom branch …` | CLI: `list` / `save` / `merge` |

## Evaluation (ctxloom.eval, §56)

| Symbol | Role |
| --- | --- |
| `run_suite(cases, metrics)` / `run_case(case, metrics)` | execute cases and score the final contexts |
| `EvalCase` / `EvalResult` / `EvalReport` / `Metric` | case/score/report structures (`overall()`, `render()`, `to_dict()`) |
| `core_metrics` | the four non-generative metrics (answer/provenance/evidence/claim) |
| `answer_coverage()` · `calculation_correctness(values=…)` · `source_coverage()` | ground-truth factories (skip when `expected` is missing) |

## Structured output

| Symbol | Role |
| --- | --- |
| `structured_llm(context, schema, *, system, user, attempts=…)` | one structured call; `None` on honest failure |
| `StructuredLLM(schema, *, system=…, attempts=…)` | reusable instance; `.call(context, user)` |
| `llm_reply(context, *, system, user, attempts=…)` | plain-text completion → `str` or `None` (single-text schema under the hood) |
| `parse_structured` | lenient JSON→model parser used internally |

## Prompts (ctxloom.prompts, §68)

| Symbol | Role |
| --- | --- |
| `PromptTemplate(template, *, defaults=…)` | strict `{var}` rendering: declared `variables`, `KeyError` on missing vars, model-attribute fields (`{question.text}`), `{{`/`}}` literals |
| `MessagesPrompt([(role, template), …])` | renders a chat sequence to `list[Message]` |

## Sources (ctxloom.sources)

| Symbol | Role |
| --- | --- |
| `Source` | ABC: `asearch(query, limit)` → list[SourceRef] |
| `SourceRef` | the shared atomic search result (ranked, scoped, stable id) |
| `FileSystemSource` | keyword/embedding search over local files |
| `CSVSource` | deterministic catalog/table search |
| `EmbeddingSource` | vector search over a prepared corpus |
| `WebSource` | discovery + lazy remote document resolution |

## Providers (ctxloom.providers)

| Symbol | Role |
| --- | --- |
| `LLMProvider`, `EmbeddingProvider` | the two contracts the core talks to |
| `ImageProvider`, `SpeechProvider`, `TranscriberProvider`, `VideoProvider` | media contracts |
| `OpenAICompatProvider`, `OpenAICompatEmbedder` + vendor factories (`openai_llm`, `anthropic_llm`, `deepseek_llm`, `groq_llm`, `mistral_llm`, `openrouter_llm`, `gemini_llm`, `ollama_llm`, `azure_llm`, …) | 20+ chat/embedder backends |
| `Message`, `Role` | one chat message; `role` is a closed `Literal` + `Message.system/user/assistant/tool` factories |
| `*_from_env(**overrides)` | `.env`-driven wiring that returns `None` when unconfigured |
| `FakeLLM`, `FakeEmbedder` | deterministic stand-ins for tests/demos |

## Recipes (ctxloom.recipes)

| Symbol | Role |
| --- | --- |
| `fan_out_sources(context, query, owner_id, …)` | idempotent fan-out search → refs + patch |
| `materialize_doc(context, ref_artifact, doc_factory, relation=…)` | lazy ref → document with provenance |
| `StatusMachine` | deterministic artifact lifecycle (`next_status`, `terminal`, `on_transition`, `query_id_field`/`status_field`) |

## Text & rollback helpers (ctxloom.recipes)

| Symbol | Role |
| --- | --- |
| `keyword_score(text, query, *, stopwords=EN_STOPWORDS, use_stems=False)` | deterministic query-coverage scoring (English / Russian) |
| `stem_words(text)` / `stem(word)` | Russian-English token stemming without embedders |
| `EN_STOPWORDS` | the default English stop-word set |
| `changed_fields(old, new, *, ignore=())` | which fields actually changed (new `None` = not a change) |
| `earliest_stage(changed, *, field_stages, order)` | the first stage a change affects (change → rebuild) |
| `downstream_fields(target, *, field_stages, order)` | fields to reset when rebuilding from a stage |

## Sessions, checkpoints, tracing

| Symbol | Role |
| --- | --- |
| `Session`, `SessionStore` | durable per-chat working memory across requests |
| `KVBackend`, `FileKVBackend`, `SQLiteKVBackend`, `PostgreSQLKVBackend` | key/value checkpoints backing sessions (`pg` extra for Postgres) — sync by design (small frequent writes; an async variant is a later option) |
| `CheckpointBackend`, `FileBackend`, `SQLiteBackend` | full-context checkpoints |
| `Tracer`, `CompositeTracer`, `AgentSpan`, `RunTrace`, `LLMCall`, `TraceStore` | tracing primitives |
| `LangfuseTracer`, `PostgresStore` | external trace sinks |
| `create_trace_router(store)` (`ctxloom.tracing.web`) | FastAPI dashboard router |