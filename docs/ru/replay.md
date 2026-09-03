# Replay (§55)

Replay отвечает на конституционный вопрос — **«почему агент произвёл этот
ответ?»** — конкретно. Коммиты детерминированы (§14), поэтому состояние контекста
восстанавливается *без запуска агентов*, а каждый LLM-вызов можно записать —
и запуск *воспроизводится точно*.

## Запись и воспроизведение на уровне провайдера

`ReplayLLM` — студия записи вызовов модели. Два прохода:

```python
from ctxloom import ReplayLLM

# проход 1 — записать настоящий запуск
resources = RuntimeResources(
    llm=ReplayLLM("calls.jsonl", mode="record", inner=real_llm)
)
runtime.run()                          # дописывает каждый вызов в calls.jsonl

# проход 2 — воспроизвести без сети
resources = RuntimeResources(llm=ReplayLLM("calls.jsonl", mode="replay"))
runtime.run()                          # те же артефакты, те же ответы
```

- **`mode="record"`** оборачивает реальный провайдер и дописывает каждую пару
  `(request → response)` (model, temperature, response_format, messages →
  text, usage) одной JSONL-строкой.
- **`mode="replay"`** отвечает *точно* на записанные вызовы. Вызов, не
  совпадающий с записью, бросает `ReplayMiss` — нельзя отвечать неверным
  результатом (§59). На уровне `structured_llm` miss честно деградирует в `None`
  (обычный путь фолбэка).

Так как детерминированные пути (гарды, вычисления, маршрутизация) не меняются,
повторённый запуск даёт идентичные артефакты — и по воспроизведённому состоянию
можно пройтись (или отрисовать `context_to_mermaid`), чтобы объяснить ответ.

## Детерминированный реплей состояния

Чекпоинт сессии несёт полную цепочку коммитов. Восстанавливайте состояние на
конкретном коммите без исполнения агентов:

```python
from ctxloom import replay_context, replay_summary
from ctxloom.checkpoints import SQLiteKVBackend
from ctxloom.session import SessionStore

store = SessionStore(SQLiteKVBackend("sessions.sqlite3"))
context = await replay_context(store, session_id, version=7)   # состояние на коммите 7
print(replay_summary(context))                                  # счётчики, по типам
```

## CLI

```bash
python -m ctxloom replay sessions.sqlite3 --session demo --diagram
```

Печатает сводку воспроизведённого состояния (`version · artifacts · relations ·
pending questions`, разбивка по типам артефактов) и, с `--diagram`, граф
провенанса в Mermaid. `--version` отматывает на конкретный коммит.