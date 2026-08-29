# Рецепты

`ctxloom.recipes` — переиспользуемые строительные блоки, кодифицирующие паттерны,
которые повторяются во всех демо. Импорт `ctxloom.recipes` не тянет лишних
зависимостей — всё построено на ядре.

## `fan_out_sources` — реактивный поиск

```python
from ctxloom.recipes import fan_out_sources

patch, refs = await fan_out_sources(
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
3. Строит патч **идемпотентных, скоупированных на владельца рефов**:
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

patch = await materialize_doc(
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
- Итоговый патч — `update_fields(target, **{status_field: new})`.

Логику *проверки* кладите в отдельный `produce`, реагирующий на смену статуса, —
машина и верификатор разделены, детерминированы и тестируются по отдельности.
`EvaluateTurn` в примерах knowledge/research — канонический образец этого
рецепта.