# Паттерны

Переиспользуемые паттерны, встречающиеся во всех пяти примерах. Они не
абстрактны — каждый конкретно воплощён в `examples/`.

## HITL: человек как полноправный участник

Человек — просто ещё одна реакция на контекст. Runtime представляет вопрос
артефактом `PendingQuestion`:

```python
class PendingQuestion(BaseModel):
    question: str
    kind: str = "general"          # например "clarify", "approval"
    notes: dict[str, Any] = {}     # маршрутизация ("какой агент спросил")
```

`Produce` создаёт его с помощью `InterruptPatch()`:

```python
return InterruptPatch().answer(question_artifact, "да")
```

`InterruptPatch` останавливает запуск, фиксирует вопрос и забирает ответ обратно:
производящий агент видит ответ как новое событие (артефакт `PendingQuestion`
обновляется). Web-демо запрашивают `context.pending_questions()`, чтобы понять,
показывать ли состояние «ожидание».

Паттерн: **активировалась стадия → сразу спросить** (repair `ApprovalStage`
создаёт вопрос об одобрении в момент, когда становится активной, не дожидаясь
нового сообщения), затем **реагировать на ответ** следующим событием.

## Инструментальные агенты: LLM + инструменты (блокирующий или HITL)

Для потоков «модель решает, какой инструмент вызвать» используйте встроенных
агентов:

```python
from ctxloom import HITLLMAgent, Consume, Produce

class OpsAgent(HITLLMAgent):
    name = "ops"
    system = "You run Kubernetes/GitLab/Ansible tasks."
    tools = [...]        # экземпляры FunctionTool
    max_steps = 8
    max_asks = 2
    consumes = [Consume(Project)]
    produces = [Produce(Report)]
```

- `LLMAgent` — блокирующий цикл: LLM отдаёт `tool_call`, runtime выполняет
  инструмент, наблюдение идёт в следующий шаг. Человека в цикле нет.
- `HITLLMAgent` — то же плюс модель может выдать `ask`: создаётся
  `PendingQuestion`, цикл останавливается, ответ человека возвращается как
  `Observation(source="user")`. Само *исполнение* инструмента также
  контролируется `ToolUseHITL`, поэтому рискованные команды ждут нажатия человека.

Пример `devops` — каноническая демонстрация `HITLLMAgent` (LLM-роутер инструментов +
одобрение мутаций K8s/GitLab/Ansible).

## Структурный вывод: никогда не парсите сырой JSON сами

Runtime оборачивает один вызов LLM в схему `pydantic` с ретраями и терпимым
парсингом JSON:

```python
from ctxloom import structured_llm
from ctxloom.structured import StructuredLLM

# процедурный вариант:
body = await structured_llm(
    context, schema=AnswerBody,
    system="You assemble coherent answers.",
    user=f"Question: {question}\nFacts: {facts}",
)

# переиспользуемый объектный вариант:
_extractor = StructuredLLM(ProjectInfo, system="Extract repair facts; unknown = null")
facts = await _extractor.call(context, user=message_text)
```

Оба возвращают `None` при отсутствии модели или провале парсинга после ретраев —
и вызывающий обязан обработать `None` (см. фолбэки).

`StructuredGenerateAgent` — декларативная обёртка: переопределите
`build_prompt(inputs)`, опционально `fallback(inputs)`, объявите `schema` — чтение
и запись провенанса запишутся за вас.

## Фолбэки: честная деградация

Детерминированная работа остаётся детерминированной; генеративная деградирует
*честно*:

1. Если **модель не настроена** — используйте детерминированный вариант
   (заготовленные варианты, фолбэк-планы): демо-режим без ключа.
2. Если **модель вернула ничего полезного** — НЕ подменяйте канонные ответы;
   сообщите о сбое открыто: *«Не удалось подобрать варианты…»*.

Пример `repair` реализует оба пути в `_make_design_options`: `fallback_options`
только когда `context.resources.llm is None`, иначе — явное сообщение о сбое.

## Модель изменений и отката («изменить → пересобрать»)

Длинные многоэтапные диалоги иногда должны *откатываться*. Пример `repair`
моделирует это так: разобрать запрос на изменение → определить самую раннюю
затронутую стадию → детерминированно сбросить всё ниже по потоку:

```python
target = rollback_target(changed)      # "plan" | "estimate" | …
updates = _downstream_resets(target)   # чистит design_options/plan/estimate
updates |= {"stage": target, "info": new_info, "handled_msg": ""}
```

Сброс `handled_msg` переустанавливает стадии, чтобы пересборка реально
запустилась. Это ручной близнец `StatusMachine` — для потоков, где откат — часть
продукта, а не жизненного цикла.

## Бюджет и справедливость

`Budget` ограничивает запуск:

```python
runtime = Runtime(ctx, agents=[...], budget=Budget(max_runs=200), max_concurrency=2)
```

- `max_runs`, `max_iterations`, `max_time_s`, лимиты вызовов инструментов — runtime
  останавливается и сообщает `RunOutcome` (`completed` | `budget_exhausted` | …)
  вместе с `RunStats`.
- `Agent.concurrency_limit` (у LLM-агентов по умолчанию ниже) + глобальный
  `max_concurrency` runtime держат лимиты провайдеров: демо `medic-lab` — лаборатория
  гипотез с лимитом LLM = 2 внутри глобального лимита 6.

## Память чата через сессии

Состояние живёт в контексте, поэтому *память чата — это просто состояние*. Между
запросами:

```python
store = SessionStore(FileKVBackend("sessions"))
session = store.open(session_id, resources=resources)
# ...создать UserMsg, astream, session.save()
```

`store.open` восстанавливает контекст из последнего чекпоинта; фоновый агент
(`@consume`/триггер) может ужимать историю, обновлять указатель `handled_msg` и
закрывать зависшие вопросы. Web-демо несут этот паттерн дословно.

## Машины состояний для длинных жизненных циклов

См. [recipes](recipes.md). Правило выбора паттерна:

| Ситуация | Подход |
| --- | --- |
| Артефакт проходит фазовые состояния | `StatusMachine` + верификатор-produce |
| Потоку нужно *откатываться* на правках пользователя | гард стадии + `_downstream_resets` |
| «Который из этих выбрала модель?» | парсинг как в `PickStage` + гард |

## Детерминизм как привычка

- Право на запуск — гард, а не удачный порядок планировщика (`return None` рано).
- Предпочитайте стабильные id (`answer:{qid}`, `ref:{sid}:{owner}`) →
  идемпотентные повторы.
- Чистые функции решений (`next_status`) тестируются без runtime.
- У каждого LLM-вызова — структурная схема, бюджет ретраев и путь `None`.