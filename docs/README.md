# Documentation

`ctxloom` is a reactive, artifact-driven agent runtime. Start with the
concepts, then the recipes and patterns; the examples are the best real-world
reference.

## Languages

- **English** — [docs/en/](en/index.md)
- **Русский** — [docs/ru/](ru/index.md)

## English

| Page | What it covers |
| --- | --- |
| [index](en/index.md) | What ctxloom is, the mental model, quick start |
| [why-ctxloom](en/why-ctxloom.md) | the *design argument*: why effects, why no graph, why determinism, why versioned state |
| [concepts](en/concepts.md) | Context, Artifact, Patch, Agent, Produce, provenance, HITL, budget |
| [sources](en/sources.md) | Retrieval: FileSystem, Embedding, CSV, Web; SourceRef |
| [providers](en/providers.md) | LLMs, embedders, images, speech, video — 20+ vendors |
| [recipes](en/recipes.md) | `fan_out_sources`, `materialize_doc`, `StatusMachine` |
| [patterns](en/patterns.md) | HITL tool approvals, structured LLM, fallbacks, sessions |
| [observability](en/observability.md) | Traces, SQLite store, dashboard, Langfuse, Postgres |
| [viz](en/viz.md) | Mermaid rendering: blueprint, context, trace + `python -m ctxloom` CLI |
| [replay](en/replay.md) | Record & replay (§55): ReplayLLM, state replay, `replay` CLI |
| [branching](en/branching.md) | Fork & merge (§39-§40): `branch()`, three-way `merge()`, `BranchStore` |
| [effects](en/effects.md) | The produce contract & mental model (§24): `self.effects`, Patch = runtime transport |
| [eval](en/eval.md) | Multi-level evaluation (§56): evidence/claim/provenance/calc/answer metrics |
| [examples](en/examples.md) | knowledge, research, medic-lab, devops, repair |
| [port-matrix](en/port-matrix.md) | how canonical patterns (LangGraph/LangChain/CrewAI/…) map to our idioms + `examples/` |
| [release](en/release.md) | versioning, changelog, build/verify/publish |
| [api](en/api.md) | Public API reference (top-level symbols) |

## Русский

| Страница | О чём |
| --- | --- |
| [index](ru/index.md) | Что такое ctxloom, ментальная модель, быстрый старт |
| [why-ctxloom](ru/why-ctxloom.md) | *дизайн-аргумент*: почему effects, почему без графа, почему детерминизм, почему версионируемое состояние |
| [concepts](ru/concepts.md) | Context, Artifact, Patch, Agent, Produce, provenance, HITL, баджеты |
| [sources](ru/sources.md) | Получение данных: FileSystem, Embedding, CSV, Web; SourceRef |
| [providers](ru/providers.md) | LLM, эмбединги, изображения, речь, видео — 20+ вендоров |
| [recipes](ru/recipes.md) | `fan_out_sources`, `materialize_doc`, `StatusMachine` |
| [patterns](ru/patterns.md) | HITL-подтверждение инструментов, structured LLM, фолбэки, сессии |
| [observability](ru/observability.md) | Трейсы, SQLite-хранилище, дашборд, Langfuse, Postgres |
| [viz](ru/viz.md) | Рендер в Mermaid: blueprint, context, trace + CLI `python -m ctxloom` |
| [replay](ru/replay.md) | Запись и воспроизведение (§55): ReplayLLM, реплей состояния, CLI `replay` |
| [branching](ru/branching.md) | Форк и слияние (§39-§40): `branch()`, трёхсторонний `merge()`, `BranchStore` |
| [effects](ru/effects.md) | Контракт produce и ментальная модель (§24): `self.effects`, Patch = транспорт рантайма |
| [eval](ru/eval.md) | Многоуровневая оценка (§56): метрики evidence/claim/provenance/calc/answer |
| [examples](ru/examples.md) | knowledge, research, medic-lab, devops, repair |
| [port-matrix](ru/port-matrix.md) | как канонические паттерны (LangGraph/LangChain/CrewAI/…) мапятся на наши идиомы + `examples/` |
| [release](ru/release.md) | версионирование, чейджлог, сборка/проверка/публикация |
| [api](ru/api.md) | Справочник публичного API (символы верхнего уровня) |