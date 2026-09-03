# Привязка к конституции: оценка (§56)

Состояние структурировано, поэтому оценка **многоуровневая** — не только
`answer == expected`:

> Качество доказательств · Проверка утверждений · Калибровка уверенности ·
> Корректность провенанса · Корректность вычислений · Покрытие ответа ·
> Покрытие источников

`ctxloom.eval` — детерминированный, без LLM харнесс, оценивающий итоговое
**состояние** прогона. Каждая метрика — чистая функция над итоговым `Context`
(+ опциональный грёд-трус), поэтому правдивость измеряется там, где она живёт —
в графе артефактов, — а не гладкость текста.

## Запуск сюита

```python
from ctxloom import EvalCase, run_suite, core_metrics, calculation_correctness

cases = [
    EvalCase(
        name="calc-question",
        run=_run_knowledge_calc,               # выполняет пайплайн → Context
        expected={"sources": ["costs:", "pricing:", "guide:"]},
    ),
]
report = run_suite(cases, metrics={
    **core_metrics,                          # answer/provenance/evidence/claim
    "calc": calculation_correctness(values=(5480, 3580)),
    "sources": source_coverage(),
})
print(report.render())
```

```
eval · multi-level report (§56)

[calc-question] overall 1.000
    answer_present            1.000
    provenance_grounded       1.000
    evidence_quality          1.000
    claim_verification        1.000
    calc                      1.000
    sources                   1.000

suite overall: 1.000
```

## Метрики

Классы артефактов сопоставляются **по имени** (`Answer`, `Evidence`, …),
поэтому харнессу не нужны доменные импорты — домен остаётся вне фреймворка.

| Метрика | На что отвечает | Встроенная |
| --- | --- | --- |
| `answer_present` | прогон вообще дал ответ? | функция |
| `provenance_grounded` | каждый ли ответ подкреплён существующей `supported_by` (§34)? | функция |
| `evidence_quality(threshold=0.5)` | доля доказательств с оценкой не ниже порога | функция |
| `claim_verification(valid=("verified",))` | доля утверждений, прошедших проверку (§35) | функция |
| `confidence_calibration()` | Brier-скор `Claim.confidence` против фактической правильности (§56) | фабрика (нужен `expected.claim_correctness`) |
| `answer_coverage()` | покрытие ожидаемого текста ответа фактическим | фабрика (нужен `expected.answer`) |
| `calculation_correctness(values=…)` | доля вычислений, совпавших с грёд-трусом (§67) | фабрика |
| `source_coverage()` | доля источников ответа, покрытых маркерами | фабрика (нужен `expected.sources`) |

`core_metrics` объединяет четыре не генеративные. Метрика без грёд-труса
возвращает `None` и попадает в **skipped** (`EvalResult.skipped`), а не в тихий
ноль.

## Типы

- `Metric` — один измеренный 0..1 скор с весами `weight`.
- `EvalCase` — имя + `run() -> Context` + опциональный `expected`.
- `EvalResult` (на кейс) / `EvalReport` (сюит) — `overall()` (взвешенное
  среднее), `to_dict()`, `render()`.

## Куда смотреть

End-to-end тесты в `tests/test_eval.py` оценивают калькуляционный вопрос demo
`knowledge` офлайн (без LLM) и проверяют полностью обоснованный отчёт — ту же
форму можно направить на любой пример.