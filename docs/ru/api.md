# Справочник API

Символы верхнего уровня, экспортируемые `ctxloom` (см. `ctxloom/__init__.py`).
Формат по группам: имя — роль в одну строку. Детали — в док-строках модулей.

## Context и состояние

| Символ | Роль |
| --- | --- |
| `Context` | версионируемое рабочее состояние; ресурсы; запросы; `latest(Model)`; announce; diff/rollback |
| `View` | результат типа-запроса (`context.view(...)`) |
| `RuntimeResources` | провайдеры + источники + произвольные ресурсы приложения |
| `Commit`, `Read`, `Write` | учёт версий и записанные операции провенанса |

## Артефакты и изменения

| Символ | Роль |
| --- | --- |
| `Artifact` | пара `(id, data)`; `data` — модель pydantic |
| `Patch` | скомпилированный набор изменений рантайма (транспорт); produces пишут `self.effects`, `Patch` собирает рантайм |
| `ctxloom.operations` (`Create`/`Update`/`Delete`/`Link`/`Unlink`/`Relation`) | скомпилированные операции, которые несёт патч (§12) |
| `Create`, `Update`, `Delete`, `Link`, `Unlink`, `Relation` | записи операций, из которых строятся патчи |

## Агенты и produce

| Символ | Роль |
| --- | --- |
| `Agent` | тонкий контейнер: `name`, `consumes`, `produces`, `concurrency_limit` |
| `create_agent` | конструктор-фабрика агента — без подкласса для обычных контейнеров |
| `Consume` / `consume` | декларативная (или декоратор) завязка реакции; `Consume.by_field` для скоуп-событий |
| `Produce` / `produce` | производитель: пишет `self.effects` (или слот `effects` в функции-декораторе) → `None`; возврат модели/Patch тоже компилируется |
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

## Чат-слой (ctxloom.chat + ctxloom.web)

| Символ | Роль |
| --- | --- |
| `ChatAssistant` | сессии + цикл хода + история в одном handle (`stream`/`invoke`/`history`); хуки: `agents`, `user_message`, `reply`, `session_state` |
| `ChatEvent` | один транспорт-нейтральный фрейм (`session`/`status`/`message`) |
| `run_message(runtime, text, *, user_message, reply)` | строительный блок хода: создать вход → стримить статусы → терминальный ответ |
| `default_session_state(ctx, user_message)` | универсальный читатель истории (любой артефакт с `.text`) |
| `create_chat_router(assistant)` | FastAPI `APIRouter` канонического SSE-контракта (`/api/chat/stream`, `/api/runs/{id}`) — нужен extra `web` |
| `ctxloom.web.sse(event, data)` | один SSE-фрейм |

## Визуализация (ctxloom.viz + python -m ctxloom)

| Символ | Роль |
| --- | --- |
| `blueprint(agents)` | статическая карта consumes/produces как Mermaid `flowchart` |
| `context_to_mermaid(context)` | живой граф провенанса контекста (артефакты + связи) |
| `trace_to_mermaid(trace)` | один запуск как Mermaid `sequenceDiagram` |
| `python -m ctxloom graph\|context\|trace` | CLI, печатающий диаграммы в stdout |
| `trace_provenance_to_mermaid(trace)` | граф доказательств запуска (записанные артефакты + рёбра `patch.link`) |

## Replay (ctxloom.replay, §55)

| Символ | Роль |
| --- | --- |
| `ReplayLLM(recording, mode="record"\|"replay", inner=…)` | записывает каждый LLM-вызов в JSONL или воспроизводит их точно; `ReplayMiss` при расхождении |
| `ReplayMiss` | воспроизводимый вызов не совпал с записью |
| `replay_context(store, session_id, version=None)` | восстанавливает состояние сохранённой сессии на коммите |
| `replay_summary(context)` | компактная сводка состояния для CLI `replay` |

## Ветвление (ctxloom.context + ctxloom.branching, §39-§40)

| Символ | Роль |
| --- | --- |
| `Context.branch(name="")` | форкает изолированную копию; фиксирует снимок базы для трёхстороннего слияния |
| `Context.merge(other, message=…)` | атомарное трёхстороннее слияние; `MergeConflict` при разошедшихся артефактах |
| `MergeConflict` | бросается, когда обе стороны изменили артефакт по-разному после форка |
| `BranchStore(KVBackend)` | хранит ветки как `branch:<session>:<name>` поверх KV-бэкенда |
| `python -m ctxloom branch …` | CLI: `list` / `save` / `merge` |

## Оценка (ctxloom.eval, §56)

| Символ | Роль |
| --- | --- |
| `run_suite(cases, metrics)` / `run_case(case, metrics)` | выполнить кейсы и скорить итоговые контексты |
| `EvalCase` / `EvalResult` / `EvalReport` / `Metric` | структуры кейс/скор/отчёт (`overall()`, `render()`, `to_dict()`) |
| `core_metrics` | четыре не генеративные метрики (answer/provenance/evidence/claim) |
| `answer_coverage()` · `calculation_correctness(values=…)` · `source_coverage()` | фабрики с грёд-трусом (skip при отсутствии `expected`) |

## Структурный вывод

| Символ | Роль |
| --- | --- |
| `structured_llm(context, schema, *, system, user, attempts=…)` | один структурный вызов; `None` при честном сбое |
| `StructuredLLM(schema, *, system=…, attempts=…)` | переиспользуемый экземпляр; `.call(context, user)` |
| `llm_reply(context, *, system, user, attempts=…)` | обычный (неструктурный) вызов → `str` или `None` (под капотом схема с одним полем) |
| `parse_structured` | допускающий JSON→модель парсер, используемый внутри |

## Промпты (ctxloom.prompts, §68)

| Символ | Роль |
| --- | --- |
| `PromptTemplate(template, *, defaults=…)` | строгий рендер `{var}`: объявленные `variables`, `KeyError` при нехватке, поля атрибутов модели (`{question.text}`), литералы `{{`/`}}` |
| `MessagesPrompt([(role, template), …])` | рендерит чат-последовательность в `list[Message]` |

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
| `Message`, `Role` | одно сообщение чата; `role` — закрытый `Literal` + фабрики `Message.system/user/assistant/tool` |
| `LLMRequest` | одна генерация: `messages` + `temperature`/`max_tokens` — `None` = дефолт провайдера (вызов перекрывает провайдера, провайдер `None` = поле не отправляется) |
| `*_from_env(**overrides)` | подключение из `.env`; возвращает `None`, если не настроено |
| `FakeLLM`, `FakeEmbedder` | детерминированные заглушки для тестов/демо |

## Рецепты (ctxloom.recipes)

| Символ | Роль |
| --- | --- |
| `fan_out_sources(context, query, owner_id, …)` | идемпотентный поиск fan-out → рефы + патч |
| `materialize_doc(context, ref_artifact, doc_factory, relation=…)` | ленивый реф → документ с провенансом |
| `StatusMachine` | детерминированный жизненный цикл артефакта (`next_status`, `terminal`, `on_transition`, `query_id_field`/`status_field`) |

## Хелперы текста и отката (ctxloom.recipes)

| Символ | Роль |
| --- | --- |
| `keyword_score(text, query, *, stopwords=EN_STOPWORDS, use_stems=False)` | детерминированный скоринг покрытия запроса (EN/RU) |
| `stem_words(text)` / `stem(word)` | стемминг русско-английских токенов без эмбеддингов |
| `EN_STOPWORDS` | набор английских стоп-слов по умолчанию |
| `changed_fields(old, new, *, ignore=())` | какие поля реально изменились (новый `None` — не изменение) |
| `earliest_stage(changed, *, field_stages, order)` | первая затронутая изменение стадия (change → rebuild) |
| `downstream_fields(target, *, field_stages, order)` | поля, которые сбрасывать при пересборке со стадии |

## Сессии, чекпоинты, трейсинг

| Символ | Роль |
| --- | --- |
| `Session`, `SessionStore` | долгоживущая память чата между запросами |
| `KVBackend`, `FileKVBackend`, `SQLiteKVBackend`, `PostgreSQLKVBackend` | key/value чекпоинты под сессии (`pg` extra для Postgres) — синхронные по дизайну (частые мелкие записи; async-вариант — возможный шаг позже) |
| `CheckpointBackend`, `FileBackend`, `SQLiteBackend` | чекпоинты всего контекста |
| `Tracer`, `CompositeTracer`, `AgentSpan`, `RunTrace`, `LLMCall`, `TraceStore` | примитивы трейсинга (async-приёмники: `export`/`query`/`get`) |
| `LangfuseTracer`, `PostgresStore` | внешние приёмники трейсов — Postgres поддерживает async чтение+запись; дашборд (`create_trace_router`) принимает любой `TraceReader` |
| `create_trace_router(store)` (`ctxloom.tracing.web`) | FastAPI-роутер дашборда |