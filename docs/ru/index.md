# ctxloom

**Реактивный runtime для агентов на артефактах.**

`ctxloom` строит агентов как реактивные, сохраняемые процессы, которые
преобразуют **версионируемые, типизированные артефакты с провенансом** внутри
**эволюционирующего контекста**. Здесь нет графа исполнения: агенты реагируют на
изменения состояния, а runtime сам выводит, что может запуститься дальше.

```text
CREATE / UPDATE / PATCH
       │
       ▼
CONTEXT ───────► ARTIFACTS ─────► AGENTS REACT ──► PATCH ──► CONTEXT'
```

Вы описываете *какие данные существуют*, *какие артефакты есть* и *что агенты
могут с ними делать*. Остальное делает runtime.

## Ментальная модель

| Традиционный агент | ctxloom |
| --- | --- |
| Программа идёт по графу/плану | Агенты **реагируют на изменения состояния** |
| Сообщения — строки | **Типизированные артефакты** (`Claim`, `Evidence`, `Answer`, …) |
| Оркестрация явная | Оркестрация **выводится из состояния** |
| Ретраи/откаты вручную | Контекст **версионируется** (коммиты как в git, diff, rollback) |
| «Кто это произвёл?» теряется | **Провенанс** связывает каждый производный артефакт с его входами |

## Почему артефакты вместо сообщений?

Сообщения непрозрачны; артефакты инспектируемы. Объект `Evidence` знает свой
текст, источник и оценку. Благодаря провенансу runtime отвечает на вопрос
*«почему агент так сказал?»*, проходя по связям
`Answer —supported_by→ Claim —derived_from→ Evidence —extracted_from→ Doc`.

## Почему версионируемый контекст?

Каждый запуск — это коммит:

- **Diff** — что именно изменилось между двумя ходами.
- **Rollback** — отменить неудачный шаг и перезапустить с чистого состояния.
- **Детерминированные повторы** — та же история даёт тот же результат.
- **Инспектируемость** — полная, запрашиваемая история всего, что произошло.

## Требования

- Python 3.12+ (`.venv` управляется через `uv`).
- `pydantic` для моделей артефактов; FastAPI/uvicorn — только для web-примеров.

## Быстрый старт

```python
from pydantic import BaseModel

from ctxloom import (
    Agent,
    Budget,
    Consume,
    Context,
    Patch,
    Produce,
    Runtime,
    RuntimeResources,
)


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


class Echo(Produce[Answer]):
    artifact_type = Answer

    async def produce(self, context, inputs, event=None):
        question = next(a for a in inputs if isinstance(a.data, Question))
        self.effects.create(Answer(text=f"echo: {question.data.text}"))
        return None


class EchoAgent(Agent):
    name = "echo"
    consumes = [Consume(Question)]
    produces = [Echo()]


ctx = Context(resources=RuntimeResources())
runtime = Runtime(ctx, agents=[EchoAgent()], budget=Budget(max_runs=10))
ctx.create(Question(text="hello"))   # агенты, потребляющие это, реагируют сами
runtime.run()
print(ctx.list_artifacts(Answer)[0].data.text)  # "echo: hello"
```

Это весь цикл: **создан артефакт → агенты реагируют → применён патч → версия
контекста продвинулась**. Всё остальное в этой документации надстраивается над
этим циклом.

## Куда дальше

- [Concepts](concepts.md) — Context, Artifact, Patch, Agent, Produce.
- [Sources](sources.md) — откуда агенты берут информацию.
- [Recipes](recipes.md) — готовые search fan-out, материализация референсов,
  машины состояний жизненного цикла.
- [Examples](examples.md) — пять работающих приложений, которые можно запустить.