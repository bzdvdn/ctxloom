# API reference

Top-level symbols exported by `ctxloom` (see `ctxloom/__init__.py`). The format
for each group: name — one-line role. Details live in the doc-strings of the
modules.

## Context & state

| Symbol | Role |
| --- | --- |
| `Context` | versioned working state; resources; queries; announce; diff/rollback |
| `View` | result of a typed join query (`context.view(...)`) |
| `RuntimeResources` | providers + sources + arbitrary app resources |
| `Commit`, `Read`, `Write` | version bookkeeping and recorded provenance ops |

## Artifacts & changes

| Symbol | Role |
| --- | --- |
| `Artifact` | the `(id, data)` pair; `data` is a pydantic model |
| `Patch` | the only mutation language: `create/update/update_fields/delete/link/unlink` |
| `Create`, `Update`, `Delete`, `Link`, `Unlink`, `Relation` | op records from which patches are built |
| `InterruptPatch` | HITL patch: create a `PendingQuestion`, resume with the human answer |

## Agents & produces

| Symbol | Role |
| --- | --- |
| `Agent` | thin container: `name`, `consumes`, `produces`, `concurrency_limit` |
| `Consume` / `consume` | declarative (or decorator) reaction declaration; `Consume.by_field` for scoped events |
| `Produce` / `produce` | the work unit: context + event → patch | None |
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

## Structured output

| Symbol | Role |
| --- | --- |
| `structured_llm(context, schema, *, system, user, attempts=…)` | one structured call; `None` on honest failure |
| `StructuredLLM(schema, *, system=…, attempts=…)` | reusable instance; `.call(context, user)` |
| `parse_structured` | lenient JSON→model parser used internally |

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
| `*_from_env(**overrides)` | `.env`-driven wiring that returns `None` when unconfigured |
| `FakeLLM`, `FakeEmbedder` | deterministic stand-ins for tests/demos |

## Recipes (ctxloom.recipes)

| Symbol | Role |
| --- | --- |
| `fan_out_sources(context, query, owner_id, …)` | idempotent fan-out search → refs + patch |
| `materialize_doc(context, ref_artifact, doc_factory, relation=…)` | lazy ref → document with provenance |
| `StatusMachine` | deterministic artifact lifecycle (`next_status`, `terminal`, `on_transition`, `query_id_field`/`status_field`) |

## Sessions, checkpoints, tracing

| Symbol | Role |
| --- | --- |
| `Session`, `SessionStore` | durable per-chat working memory across requests |
| `KVBackend`, `FileKVBackend`, `SQLiteKVBackend` | key/value checkpoints backing sessions |
| `CheckpointBackend`, `FileBackend`, `SQLiteBackend` | full-context checkpoints |
| `Tracer`, `CompositeTracer`, `AgentSpan`, `RunTrace`, `LLMCall`, `TraceStore` | tracing primitives |
| `LangfuseTracer`, `PostgresStore` | external trace sinks |
| `create_trace_router(store)` (`ctxloom.tracing.web`) | FastAPI dashboard router |