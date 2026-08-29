# Концепции

Полное обоснование дизайна — в [CONSTITUTION.md](../../CONSTITUTION.md). Эта
страница — рабочий обзор шести строительных блоков и их взаимодействия.

## 1. Context

`Context` — версионируемое рабочее состояние. Как git, он хранит историю
коммитов, где каждый коммит — результат применения одного или нескольких
**патчей**.

```python
from ctxloom import Context, RuntimeResources
from ctxloom.sources import FileSystemSource

ctx = Context(
    resources=RuntimeResources(
        sources={"docs": FileSystemSource("./docs")},
    )
)
```

Ключевые возможности:

| Возможность | Назначение |
| --- | --- |
| `create / update / delete` | кодирование намерения (в runtime запускается посредством агентов) |
| `list_artifacts(Model)` | запрос текущего состояния по типу артефакта |
| `view((M1, M2), condition=…)` | запрос по нескольким типам для решений и памяти чата |
| `related(artifact_id, relation)` | проход по графу провенанса |
| `announce(message, kind=…)` | событие прогресса/статуса для UI |
| `diff / rollback / merge` | просмотр или откат истории; слияние веток |

`Context.resources` несёт то, что *не является состоянием*: провайдеры (LLM,
эмбеддер), источники и произвольные ресурсы приложения (каталог цен, папка
изображений). Агенты их читают, но никогда не сохраняют.

## 2. Artifact

`Artifact` — пара `(id, data, created_at, …)`, где `data` — модель `pydantic`.
Артефакты — **полноценные объекты**, а не строковые блобы.

```python
class Evidence(BaseModel):
    query_id: str
    source: str
    text: str
    score: float
```

Правила:

- У каждого артефакта стабильный `id`. Предпочитайте стабильные id случайным
  (`answer:{query_id}`, `ref:{stable_id}:{owner}`) — идемпотентность и связывание
  провенанса становятся тривиальными.
- `query_id` — соглашение об «owner-ключе», когда к одному ходу работы (вопросу,
  исследовательскому повороту) относится много артефактов. На нём построены
  рецепты и примеры.
- Артефакты иммутабельны как *данные*; изменения выражаются патчами, которые
  создают новые версии.

## 3. Patch

`Patch` — единственный язык, которым агенты выражают изменение:

```python
patch = Patch()
patch.create(Answer(query_id=qid, text=text), id="answer:q1")
patch.link("answer:q1", "supported_by", evidence_id)
patch.update_fields(some_artifact, status="answered")
patch.delete(old_artifact)
return patch
```

Операции:

| Операция | Смысл |
| --- | --- |
| `create` | добавить артефакт (опционально с выбранным `id`) |
| `update` / `update_fields` | зафиксировать правку артефакта |
| `delete` | удалить артефакт |
| `link` | соединить `id → rel → other_id` (провенанс) |
| `unlink` | убрать связь |

`Patch.merge_existing_patch(a, b)` объединяет несколько изменений в один патч —
в примерах возвращается, например, *обновить проект* + *создать ответ* единым
патчем.

`InterruptPatch` — специальный HITL-патч: создаёт `PendingQuestion`, останавливает
запуск и фиксирует ответ при возобновлении (см. [patterns](patterns.md)).

## 4. Agent

`Agent` — **тонкий контейнер**: он объявляет, на что реагирует и что может
производить. Логика живёт в классах `Produce`.

```python
class RepairFlow(Agent):
    name = "repair_flow"
    consumes = [Consume(UserMsg), Consume(Project)]
    produces = [
        CollectStage(), PickStage(), PlanStage(),
        EstimateStage(), ApprovalStage(), AssistantStage(),
        Produce(ChatReply), Produce(PendingQuestion),
    ]
```

- `consumes` — типы артефактов, которые будят агента.
- `produces` — экземпляры `Produce`, которые могут выполниться, когда агент
  проснулся.
- Runtime будит агентов по событиям, соблюдая бюджет и параллельность.

## 5. Produce

`Produce[M]` — место, где происходит работа. Это **функция без состояния** от
текущего контекста (плюс триггерное событие) к патчу.

```python
class EstimateStage(Produce[Project]):
    artifact_type = Project

    async def produce(self, context, inputs, event=None) -> Patch | None:
        ...
        return Patch().update_fields(project_art, {"stage": "estimate"})
```

Соглашение: **сначала детерминизм**. Право на запуск определяется гардом —
`if project.stage != "estimate": return None`. Должна ли стадия измениться —
чистая функция состояния. LLM применяется только к действительно генеративным
задачам и всегда обёрнут структурной схемой и фолбэком.

`Produce` может также объявлять зависимости (запускаться после других
производителей) через механизм `depends_on`/`inject` — см. [справочник API](api.md).

## 6. Провенанс

Каждый производный артефакт ссылается на то, что его произвело. Runtime
записывает **чтения и записи** автоматически; ваш код добавляет доменные связи
через `patch.link`:

```text
Answer ──supported_by──► Claim ──derived_from──► Evidence ──extracted_from──► Doc
```

Зачем это нужно:

- **Объяснимость** — «покажи источники» — это запрос по связям, а не память LLM.
- **Оценка** — сила ответа = соединение уверенности утверждений и поддержки
  доказательствами.
- **Детерминированный аудит** — каждый трейс содержит чтения/записи каждого
  спана агента.

## Сопутствующие куски

- **`Budget` / `RunOutcome` / `RunStats`** — лимиты на запуски, итерации и время;
  при исчерпании бюджета runtime останавливается и сообщает причину.
- **`Event` / `EventType`** — формат «что-то изменилось»; агентов будят события
  создания/обновления артефактов, а announce порождает `status`-события на пути
  к UI.
- **`Trigger`** — вторичное условие входа для produce (периодический или таймерый
  запуск), независимое от потребляемых артефактов.
- **`Session` / `SessionStore`** — долговременная рабочая память чата между
  запросами, поверх KV-чекпойнта (файл или SQLite).