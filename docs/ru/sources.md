# Источники (Sources)

**Source** — это способность получать информацию. Векторный поиск — одна из
стратегий; прямой API, ключевые слова/SQL, CSV и файловая система — такие же
первоклассные, и **эмбеддинги не обязательны**. Источники живут в
`Context.resources.sources`.

```python
from ctxloom import Context, RuntimeResources
from ctxloom.sources import CSVSource, EmbeddingSource, FileSystemSource, WebSource

ctx = Context(
    resources=RuntimeResources(
        sources={
            "docs": FileSystemSource("./docs", embedder=embedder),  # опционально
            "catalog": CSVSource("data/price.csv", key="sku", columns=...),
            "web": WebSource(...),
        }
    )
)
```

## SourceRef

Общий результат *любого* поиска — `SourceRef`: ранжированный, скоупированный
указатель:

```python
class SourceRef(BaseModel):
    source_id: str      # какой источник его произвёл
    payload: str        # маленький превью/тестовый фрагмент
    uid: str            # стабильный uid документа внутри источника
    score: float | None # ранг/оценка совпадения, если источник скорирует
    query: str | None   # запрос, который его нашёл
    metadata: dict      # owner_id-скоуп, дополнительный контекст
```

`SourceRef.stable_id()` позволяет строить детерминированные id артефактов
(`ref:{stable_id}:{owner_id}` в `fan_out_sources`), так что повторные поиски
идемпотентны.

## Четыре встроенных источника

| Источник | Назначение | Примечания |
| --- | --- | --- |
| `FileSystemSource` | поиск по ключевым словам (и, опционально, эмбединг) по локальным файлам | `embedder` опционален; скорирует совпадения |
| `EmbeddingSource` | векторный поиск по подготовленному корпусу | нужен `EmbeddingProvider` |
| `CSVSource` | запрос к каталогу/таблице, возвращает структурированные строки | детерминированно, без эмбеддингов |
| `WebSource` | живой веб: поиск + **ленивое** разрешение страниц | тянет *обещанные* документы по требованию |

## Ленивая материализация

`WebSource` (и удалённые источники вообще) возвращают *ссылки*, а не содержимое.
Разрешение документа — явное и ленивое: демо research тянет только те страницы,
которые решило использовать, и связывает полученный документ с референсом:

```text
SourceRef --materialized_from--> TypedDoc
```

Рецепт [`materialize_doc`](recipes.md) кодирует ровно этот поток.

## Типовые стадии поиска в демо

```text
query ──► fan_out_sources ──► SourceRefs (ранжированные, скоуп на владельца)
                                   │
                                   ▼  (выбор релевантных + ленивое разрешение для web)
                              TypedDoc / строки
                                   │
                                   ▼
                            Evidence (извлечённое, со скоупом)
```

## Пример: CSVSource для детерминированных чисел

Цены каталога никогда не идут через LLM. CSV-источник возвращает точные строки;
стадия оценки в примере `repair` умножает количества на цены из каталога
детерминированно:

```python
catalog = CSVSource("data/price.csv", key="name")
rows = await catalog.asearch("штукатурка", limit=20)
```

Можно указывать `CSVSource` на любую структурированную таблицу и искать по
ключевым словам, получая нужные строки для вычислений.