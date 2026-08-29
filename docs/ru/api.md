# Справочник API

Символы верхнего уровня, экспортируемые `ctxloom` (см. `ctxloom/__init__.py`).
Формат по группам: имя — роль в одну строку. Детали — в док-строках модулей.

## Context и состояние

| Символ | Роль |
| --- | --- |
| `Context` | версионируемое рабочее состояние; ресурсы; запросы; announce; diff/rollback |
| `View` | результат типа-запроса (`context.view(...)`) |
| `RuntimeResources` | провайдеры + источники + произвольные ресурсы приложения |
| `Commit`, `Read`, `Write` | учёт версий и записанные операции провенанса |

## Артефакты и изменения

| Символ | Роль |
| --- | --- |
| `Artifact` | пара `(id, data)`; `data` — модель pydantic |
| `Patch` | единственный язык мутаций: `create/update/update_fields/delete/link/unlink` |
| `Create`, `Update`, `Delete`, `Link`, `Unlink`, `Relation` | записи операций, из которых строятся патчи |
| `InterruptPatch` | HITL-патч: создать `PendingQuestion`, возобновиться с ответом человека |

## Агенты и produce

| Символ | Роль |
| --- | --- |
| `Agent` | тонкий контейнер: `name`, `consumes`, `produces`, `concurrency_limit` |
| `Consume` / `consume` | декларативная (или декоратор) завязка реакции; `Consume.by_field` для скоуп-событий |
| `Produce` / `produce` | единица работы: контекст + событие → патч | None |
| `Trigger` | вторичное (не артефактное) условие входа produce |
| `StructuredGenerateAgent` | декларативный агент LLM→схема→артефакт (`schema`, `build_prompt`, `fallback`) |
| `LLMAgent` | блокирующий цикл LLM+инструменты (`system`, `tools`, `max_steps`) |
| `HITLLMAgent` | цикл LLM+инструменты с паузами на ответ человека (`max_asks`, отчёт о возобновлении) |
| `ToolUse`, `ToolUseHITL` | produce цикла инструментов; HITL-вариант ждёт одобрения перед исполнением |
| `Tool`, `FunctionTool`, `tool`, `ToolOutput` | абстракция и регистрация инструментов |
| `ToolAnswer`, `Observation` | результаты инструментов и наблюдения модели (протокол цикла) |

## Runtime

| Символ | Роль |
| --- | --- |
| `Runtime` | будит агентов по событиям; `run` / `arun` / `astream`; бюджет и параллельность |
| `Budget`, `RunOutcome`, `RunStats` | лимиты запуска и итог/статистика |
| `Event`, `EventType` | проводной формат «что-то изменилось» |
| `EventHub`, `ProgressEvent` | канал прогресса/announce, который потребляют web-UI |

## Структурный вывод

| Символ | Роль |
| --- | --- |
| `structured_llm(context, schema, *, system, user, attempts=…)` | один структурный вызов; `None` при честном сбое |
| `StructuredLLM(schema, *, system=…, attempts=…)` | переиспользуемый экземпляр; `.call(context, user)` |
| `parse_structured` | допускающий JSON→модель парсер, используемый внутри |

## Источники (ctxloom.sources)

| Символ | Роль |
| --- | --- |
| `Source` | ABC: `asearch(query, limit)` → list[SourceRef] |
| `SourceRef` | общий атомарный результат поиска (ранжирован, скоуп, стабильный id) |
| `FileSystemSource` | поиск по ключевым словам/эмбедингу по локальным файлам |
| `CSVSource` | детерминированный поиск по каталогу/таблице |
| `EmbeddingSource` | векторный поиск по подготовленному корпусу |
| `WebSource` | открытие ресурсов + ленивое разрешение удалённых документов |

## Провайдеры (ctxloom.providers)

| Символ | Роль |
| --- | --- |
| `LLMProvider`, `EmbeddingProvider` | два контракта, с которыми говорит ядро |
| `ImageProvider`, `SpeechProvider`, `TranscriberProvider`, `VideoProvider` | медиа-контракты |
| `OpenAICompatProvider`, `OpenAICompatEmbedder` + вендорные фабрики (`openai_llm`, `anthropic_llm`, `deepseek_llm`, `groq_llm`, `mistral_llm`, `openrouter_llm`, `gemini_llm`, `ollama_llm`, `azure_llm`, …) | 20+ чат/эмбеддинг-бэкендов |
| `*_from_env(**overrides)` | подключение из `.env`; возвращает `None`, если не настроено |
| `FakeLLM`, `FakeEmbedder` | детерминированные заглушки для тестов/демо |

## Рецепты (ctxloom.recipes)

| Символ | Роль |
| --- | --- |
| `fan_out_sources(context, query, owner_id, …)` | идемпотентный поиск fan-out → рефы + патч |
| `materialize_doc(context, ref_artifact, doc_factory, relation=…)` | ленивый реф → документ с провенансом |
| `StatusMachine` | детерминированный жизненный цикл артефакта (`next_status`, `terminal`, `on_transition`, `query_id_field`/`status_field`) |

## Сессии, чекпоинты, трейсинг

| Символ | Роль |
| --- | --- |
| `Session`, `SessionStore` | долгоживущая память чата между запросами |
| `KVBackend`, `FileKVBackend`, `SQLiteKVBackend` | key/value чекпоинты под сессии |
| `CheckpointBackend`, `FileBackend`, `SQLiteBackend` | чекпоинты всего контекста |
| `Tracer`, `CompositeTracer`, `AgentSpan`, `RunTrace`, `LLMCall`, `TraceStore` | примитивы трейсинга |
| `LangfuseTracer`, `PostgresStore` | внешние приёмники трейсов |
| `create_trace_router(store)` (`ctxloom.tracing.web`) | FastAPI-роутер дашборда |