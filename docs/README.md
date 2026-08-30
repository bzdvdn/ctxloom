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
| [concepts](en/concepts.md) | Context, Artifact, Patch, Agent, Produce, provenance, HITL, budget |
| [sources](en/sources.md) | Retrieval: FileSystem, Embedding, CSV, Web; SourceRef |
| [providers](en/providers.md) | LLMs, embedders, images, speech, video — 20+ vendors |
| [recipes](en/recipes.md) | `fan_out_sources`, `materialize_doc`, `StatusMachine` |
| [patterns](en/patterns.md) | HITL tool approvals, structured LLM, fallbacks, sessions |
| [observability](en/observability.md) | Traces, SQLite store, dashboard, Langfuse, Postgres |
| [viz](en/viz.md) | Mermaid rendering: blueprint, context, trace + `python -m ctxloom` CLI |
| [replay](en/replay.md) | Record & replay (§55): ReplayLLM, state replay, `replay` CLI |
| [branching](en/branching.md) | Fork & merge (§39-§40): `branch()`, three-way `merge()`, `BranchStore` |
| [examples](en/examples.md) | knowledge, research, medic-lab, devops, repair |
| [api](en/api.md) | Public API reference (top-level symbols) |

## Русский

| Страница | О чём |
| --- | --- |
| [index](ru/index.md) | Что такое ctxloom, ментальная модель, быстрый старт |
| [concepts](ru/concepts.md) | Context, Artifact, Patch, Agent, Produce, provenance, HITL, баджеты |
| [sources](ru/sources.md) | Получение данных: FileSystem, Embedding, CSV, Web; SourceRef |
| [providers](ru/providers.md) | LLM, эмбединги, изображения, речь, видео — 20+ вендоров |
| [recipes](ru/recipes.md) | `fan_out_sources`, `materialize_doc`, `StatusMachine` |
| [patterns](ru/patterns.md) | HITL-подтверждение инструментов, structured LLM, фолбэки, сессии |
| [observability](ru/observability.md) | Трейсы, SQLite-хранилище, дашборд, Langfuse, Postgres |
| [viz](ru/viz.md) | Рендер в Mermaid: blueprint, context, trace + CLI `python -m ctxloom` |
| [replay](ru/replay.md) | Запись и воспроизведение (§55): ReplayLLM, реплей состояния, CLI `replay` |
| [branching](ru/branching.md) | Форк и слияние (§39-§40): `branch()`, трёхсторонний `merge()`, `BranchStore` |
| [examples](ru/examples.md) | knowledge, research, medic-lab, devops, repair |
| [api](ru/api.md) | Справочник публичного API (символы верхнего уровня) |