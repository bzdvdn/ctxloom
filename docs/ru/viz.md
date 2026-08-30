# Визуализация и CLI

`ctxloom.viz` рендерит систему в **Mermaid**. Рисовать граф исполнения нечего —
runtime выводит исполнение из изменений состояния, — поэтому две честные
диаграммы: *статическая карта* и *живое состояние*:

| Функция | Что рисует |
| --- | --- |
| `blueprint(agents)` | статическая карта: типы артефактов = ноды, агенты = рёбра (`Consume` / `creates` / `lifecycle`) |
| `context_to_mermaid(context)` | живой граф провенанса: артефакты сгруппированы по типам, связи `patch.link` |
| `trace_to_mermaid(trace)` | один запуск как `sequenceDiagram`: спаны по времени, записи/чтения, LLM-вызовы |

Все три — чистые функции, возвращающие строку, без зависимостей: вставляйте вывод
в GitHub, Notion или [mermaid.live](https://mermaid.live).

## CLI

```bash
python -m ctxloom graph examples.knowledge.agents        # все агенты модуля
python -m ctxloom graph examples.knowledge.agents:Planner # один агент
python -m ctxloom context examples/knowledge/sessions/sessions.sqlite3
python -m ctxloom trace traces.db [run_id]
```

- `graph` инстансирует каждый подкласс `Agent`, определённый в модуле (или один
  через `module:Attr`), и печатает blueprint.
- `context` читает сохранённую сессию из KV-бэкенда (директория файлов или
  SQLite) и печатает её граф провенанса; `--session` выбирает сессию,
  `--limit` ограничивает число артефактов.
- `trace` читает запуск из базы `TraceStore` (по умолчанию — последний запуск).

## В дашборде

Страница запуска (`/traces/<run_id>`) рендерит диаграмму трассы вживую через
Mermaid, с кнопкой `copy` и исходником в раскрывающемся `<pre>`; если браузер
офлайн (нет Mermaid JS) — показывается текст исходника.