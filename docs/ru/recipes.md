# Рецепты

`ctxloom.recipes` — переиспользуемые строительные блоки, кодифицирующие паттерны,
которые повторяются во всех демо. Импорт `ctxloom.recipes` не тянет лишних
зависимостей — всё построено на ядре.

## `find` / `find_all` — поиск типизированных артефактов в `inputs`

Если агент объявляет больше одного типа в `consumes`, produce получает плоский
`list[Artifact[Any]]`; выбрать «тот самый Question» или «все Evidence» —
почти в каждом produce одна и та же строка
`next((a for a in inputs if isinstance(a.data, X)), None)`. `find`/`find_all` —
типизированная замена в одну строку:

```python
from ctxloom.recipes import find, find_all

question = find(inputs, Question)          # Artifact[Question] | None
evidence = find_all(inputs, Evidence)       # list[Artifact[Evidence]]
```

## `fan_out_sources` — реактивный поиск

```python
from ctxloom.recipes import fan_out_sources

refs = await fan_out_sources(
    context,
    query=question,
    owner_id=query_id,           # скоуп рефов на владеющий ход
    limit=5,
    query_id=query_id,           # owner-ключ для провенанса
    on_start=lambda source: context.announce(
        f"Searching {source}…", kind="status"
    ),
    on_count=lambda source, n: context.announce(
        f"{source}: {n} hits", kind="status"
    ),
)
```

Что делает:

1. Рассылает запрос **по всем настроенным источникам** из
   `context.resources.sources`.
2. Ранжирует объединённые `SourceRef` по скорам (сначала лучшие).
3. Создаёт **идемпотентные, скоупированные на владельца рефы** (эффект `Create`):
   `id=f"ref:{ref.stable_id()}:{owner_id}"`.

Идемпотентность важна: поиск выполняется один раз за ход (свой маркер), но может
*повториться* при ретраях — те же id пересоздаются без дублей. `on_start` /
`on_count` дают прогресс-аннонсы поверх SSE.

## `materialize_doc` — ленивое разрешение ссылок

```python
from ctxloom.recipes import materialize_doc

async def doc_from_ref(context, ref_artifact, content) -> TypedDoc:
    # постройте доменный документ из полученного содержимого
    return TypedDoc(query_id=ref_artifact.data.query_id, path=..., text=content)

doc = await materialize_doc(
    context,
    ref_artifact,
    doc_from_ref,
    relation="resolved_from",    # по умолчанию: materialized_from
)
```

Источники возвращают *ссылки*, а не содержимое, поэтому документы достаются
**лениво, только когда нужны** — правило в демо research: «разрешить страницу
только после того, как модель оценила её релевантной». Отсутствие источника или
сбой разрешения дают `None` (честный no-op), а не падение, и сбой виден в трейсе.

Созданный документ связывается назад:
`TypedDoc ──resolved_from──► SourceRef`, так что обход провенанса
`Answer → Claim → Evidence → Doc → SourceRef` остаётся полным.

## `StatusMachine` — детерминированные жизненные циклы

Машины состояний — паттерн для «артефакта, который проходит состояния»
(исследовательский ход: `researching → answerable → answered`). Вместо ручного
графа переходов `StatusMachine` — **чистая функция текущего состояния**:

```python
from ctxloom import Artifact, Context
from ctxloom.recipes import StatusMachine


class EvaluateTurn(StatusMachine[ResearchTurn]):
    artifact_type = ResearchTurn                       # что продвигается
    terminal = frozenset({"answered", "insufficient"}) # где останавливается
    query_id_field = "query_id"                        # owner-ключ (по умолчанию)
    status_field = "status"                            # поле статуса (по умолчанию)

    def next_status(self, context: Context, key: str) -> str | None:
        """Чистая функция: какой статус жизненный цикл заслуживает сейчас."""
        if any(a.data.query_id == key for a in context.list_artifacts(Answer)):
            return "answered"
        return None

    def on_transition(self, context, key, old_status, new_status) -> None:
        context.announce(f"Research status: {old} → {new}",
                         kind="status", query_id=key)
```

Механика (всё унаследовано от `produce`):

- Будет разбужен любым событием; событие сопоставляется с жизненным циклом через
  `owner_key` (читает `query_id_field` данных артефакта с фолбэком на его `id`).
- Берёт первый подходящий артефакт `artifact_type`; `terminal`-статусы
  останавливают машину.
- `next_status` решает новый статус; `None` или отсутствие изменения ⇒ ничего не
  происходит.
- Непосредственно перед применением вызывается `on_transition` — ваш хук для
  прогресс-аннонсов.
- Переход — это эффект: `self.effects.update(target, **{status_field: new})`.

Логику *проверки* кладите в отдельный `produce`, реагирующий на смену статуса, —
машина и верификатор разделены, детерминированы и тестируются по отдельности.
`EvaluateTurn` в примерах knowledge/research — канонический образец этого
рецепта.

## `WindowSummarizer` / `WindowPruner` — ограниченная память диалога (§27, §37)

Долгоживущая память чата — это просто состояние: артефакты-сообщения
накапливаются, а два обычных `Produce` держат окно ограниченным — саммарайзер
сжимает недавнее окно каждые N сообщений, прунер удаляет то, что вышло за
границы. Рецепт владеет размером окна, периодичностью и идемпотентностью;
домен владеет тем, *как* суммировать и *как выглядит* артефакт саммари:

```python
from ctxloom.recipes import WindowPruner, WindowSummarizer, llm_summarizer


class Summary(BaseModel):
    round: int
    text: str


def build_summary(round_no: int, text: str) -> Summary:
    return Summary(round=round_no, text=text)


class Flow(Agent):
    name = "chat"
    consumes = [Consume(Msg)]
    produces = [
        WindowSummarizer(
            Msg, Summary,
            summarize=llm_summarizer("Сожми недавний диалог в короткую заметку-память."),
            build=build_summary,
            window=8,   # сколько сообщений идёт в один саммари
            every=4,    # новый саммари каждые N сообщений
        ),
        WindowPruner(Msg, keep=8),  # полезен и сам по себе, без саммарайзера
    ]
```

- `summarize(context, history) -> str | None` — ваш колбэк (или
  `llm_summarizer(system=...)` — тонкая обёртка над `llm_reply`); `None`
  запускает `fallback` рецепта (по умолчанию — обрезанная строка истории,
  никогда не падение).
- `build(round_no, text) -> Summary` — форму артефакта саммари определяете вы;
  рецепт никогда не угадывает имена полей.
- Id саммари выводится из количества сообщений (`summary:{round}` по
  умолчанию), поэтому повторный прогон того же поколения никогда не
  дублирует саммари.
- `render`/`order_key`/`id_of` переопределяемы, если дефолты (рендер по
  role/text, сортировка по `created_at`) не подходят вашему артефакту.

Полное рабочее демо — в `examples/summarize/main.py`.

## `keyword_score` / `stem_words` — детерминированный скоринг текста (§67)

Там, где эмбеддинги опциональны, покрытие по ключевым словам — нейтральный
фолбэк (английский чат `knowledge` и каталог `repair` используют именно его):

```python
from ctxloom.recipes import EN_STOPWORDS, keyword_score, stem_words

keyword_score("How to set up authentication", "authentication")          # 1.0
keyword_score("Установка аутентификации", "аутентификацию", use_stems=True)  # 1.0
stem_words("Ремонт комнаты и kitchen")  # {"ремонт", "комнат", "kitchen"}
```

- Английские стоп-слова убираются с обеих сторон по умолчанию (`EN_STOPWORDS`).
- `use_stems=True` включает небольшой русский стеммер окончаний, поэтому
  «аутентификацию» совпадает с «аутентификация» без модели.

## Skills — инструкции, подгружаемые по ситуации (§67)

**Skill** — тот же формат, что у Claude Skills: markdown-файл с
фронтматтером `name`/`description` и телом процедурных инструкций. Это не
`Source` — `Source` извлекается, чтобы ответить фактами; skill загружается,
чтобы изменить *как именно* делается LLM-вызов текущего хода (правило,
формат), когда его описание совпадает с ситуацией:

```python
from ctxloom.recipes import load_skills, match_skills

# --- один раз, при старте ---
skills = load_skills("skills/")   # каждый *.md-файл, разобранный по фронтматтеру

# --- на каждом ходу, только там, где применимо ---
situation = "reporting an answer backed by a number computed from structured storage"
for skill in match_skills(skills, situation):
    prompt += f"\n\nInstruction ({skill.name}): {skill.body}"
```

Файл skill:

```markdown
---
name: cost-reporting
description: How to report a number computed from structured storage. Use when the answer is backed by a deterministic calculation.
---
State the exact computed value explicitly, and say plainly it was computed,
not estimated — name the source and column it came from.
```

- `situation` — короткое описание происходящего, **написанное кодом**, не
  обязательно сырой вопрос пользователя: вызывающий код характеризует момент,
  так же как `description` самого skill характеризует, когда его применять.
  Это сохраняет триггер реактивным (§8): skill срабатывает из-за того, какое
  состояние существует (например, артефакт `Calculation`), а не потому что
  код разбирает формулировку пользователя.
- Сопоставление — `keyword_score` (детерминированно, без эмбеддингов) по
  `name + description`; возвращаются только совпадения не ниже `threshold`
  (по умолчанию `0.34`), не больше `limit` (по умолчанию `1`) — skill должен
  быть точным триггером, а не фолбэком, срабатывающим на каждом ходу.
- Это намеренно **не** новый core-примитив (§61): `body` подобранного skill —
  обычная строка, которую вы добавляете в промпт `structured_llm`/
  `llm_reply`. Skill `cost-reporting` из демо `knowledge`
  (`examples/knowledge/skills/`) — канонический пример — см. его
  [README](../../examples/knowledge/README.md#skills--instructions-loaded-by-the-situation-not-the-graph)
  (на английском).

## `changed_fields` / `earliest_stage` / `downstream_fields` — «изменить → пересобрать»

Длинные многоэтапные потоки иногда должны *откатываться*: пользователь правит
факт, пайплайн пересобирается с самой ранней затронутой стадии и очищает всё
ниже по потоку. Хелперы общие; ваш — это карта `field_stages` и порядок стадий
(одобрение в `repair` — канонический пример):

```python
from ctxloom.recipes import changed_fields, downstream_fields, earliest_stage

field_stages = {"room": "collect", "style": "design_choice",
                "area": "plan", "budget": "estimate"}
order = ("collect", "design_choice", "plan", "estimate")

changed = changed_fields(old_info, new_info)          # {"style", "budget"}
target = earliest_stage(changed, field_stages=field_stages, order=order)
reset = downstream_fields(target, field_stages=field_stages, order=order)
```

`changed_fields` игнорирует поля, которые в новом состоянии остались `None`
(модель не знала); `earliest_stage` возвращает `None`, если ничего не изменилось;
`downstream_fields` включает саму цель (всё на этой стадии и позже сбрасывается,
выше по потоку — сохраняется).