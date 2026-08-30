# Контракт produce и ментальная модель (§24)

Один абзац, который стоит держать в голове, читая любой пример или пиша
produce:

> **Produce описывает, что должно измениться, записывая `self.effects`; рантайm
> компилирует эти эффекты в один атомарный патч и коммитит его. Вам почти
> никогда не нужно собирать `Patch` самому — это транспорт рантайма.**

```python
async def produce(self, context, inputs, event=None) -> None:
    if <guard>:                     # право на запуск — решение состояния
        return None
    # эффекты: «дифф, выраженный как намерение»
    evidence = self.effects.create(Evidence(...), id="evidence:q1")
    answer = self.effects.create(Answer(...), id="answer:q1")
    evidence.link("extracted_from", doc)     # doc: Artifact
    answer.link("supported_by", evidence)    # evidence: хэндл эффекта
    self.effects.update(turn, status="answered")
    self.effects.ask("Утвердить смету?", kind="approval")   # HITL (§60)
    return None
```

## Три слоя

| Слой | Что это | Кто пишет |
| --- | --- | --- |
| **Produce** | реакция: guard → LLM/расчёт → `self.effects.*` → `None` | приложение (вы) |
| **Effects** | заявленный набор изменений (creates/updates/links/questions) на ход | вы, через `self.effects` |
| **Patch** | *скомпилированные* операции, которые рантайm применяет одним коммитом | рантайm (и легаси/продвинутые сборки) |

Ничего не применяется, пока produce не завершится — **атомарность структурная**
(§41), никакого rollback. События, валидация по `produces`, трейс
reads/writes/relations — всё строится из тех же скомпилированных операций.

## Почему `self.effects` «амбиентен»

`self.effects` живёт в слоте, скоуженном на прогон: рантайm ставит его перед
каждым исполнением и снимает после (contextvar) — безопасно при параллельных
produce и **невидимо** для вас: вы его не создаёте, не называете, не передаёте.
Хэндлы собираются поперёк стейтментов (`evidence` создан выше, связан ниже) —
поэтому вызовы читаются «про артефакты», а не «про id».

## Где `Patch` ещё появляется

- **`Agent.run`** — люк для кастомных (не-Produce) агентов, собирающих набор
  изменений вручную; рантайm сшивает их после эффектов.
- **Рецепты** (`fan_out_sources`, `materialize_doc`) и `StatusMachine` пишут в
  слот; tool-цикл (`ToolUse`/`ToolUseHITL`) и HITL (`effects.ask`) — тоже
  эффекты.
- **Тесты и продвинутые сборки** могут строить `Patch`; в обычных produce он
  не нужен.

## Правило

```text
guard → решить → описать (self.effects) → return None
```

Если внутри produce хочется написать `Patch()` — остановитесь и используйте
`self.effects`; компилирует рантайm.