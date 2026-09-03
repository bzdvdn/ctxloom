# Evaluation harness (§56)

Because state is structured, evaluation is **multi-level** — not just
`answer == expected`:

> Evidence quality · Claim verification · Confidence calibration ·
> Provenance grounding · Calculation correctness · Answer coverage ·
> Source coverage

`ctxloom.eval` is the deterministic, LLM-free harness that scores a run's final
**state**. Each metric is a pure function over the resulting `Context` (+
optional ground truth), so truthfulness is measured where it lives — the
artifact graph — not the smoothness of the text.

## Running a suite

```python
from ctxloom import EvalCase, run_suite, core_metrics, calculation_correctness

cases = [
    EvalCase(
        name="calc-question",
        run=_run_knowledge_calc,               # executes the pipeline → Context
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

## Metrics

Artifact classes are matched **by name** (`Answer`, `Evidence`, …), so the
harness needs no domain imports — the domain stays out of the framework.

| Metric | What it answers | Built-in |
| --- | --- | --- |
| `answer_present` | did the run produce an answer at all? | plain fn |
| `provenance_grounded` | is every answer backed by an existing `supported_by` (§34)? | plain fn |
| `evidence_quality(threshold=0.5)` | share of evidence scoring at/above the bar | plain fn |
| `claim_verification(valid=("verified",))` | share of claims that passed verification (§35) | plain fn |
| `confidence_calibration()` | Brier score of `Claim.confidence` against actual correctness (§56) | factory (needs `expected.claim_correctness`) |
| `answer_coverage()` | coverage of the expected answer text by the answer | factory (needs `expected.answer`) |
| `calculation_correctness(values=…)` | share of calculations matching ground truth (§67) | factory |
| `source_coverage()` | share of the answer's sources matched by markers | factory (needs `expected.sources`) |

`core_metrics` bundles the four non-generative ones. A metric that lacks ground
truth returns `None` and is reported as **skipped** (`EvalResult.skipped`), never
as a silent zero.

## Types

- `Metric` — one measured 0..1 score with a reporting `weight`.
- `EvalCase` — name + a `run() -> Context` + optional `expected` ground truth.
- `EvalResult` (per case) / `EvalReport` (suite) — `overall()` (weighted mean),
  `to_dict()`, `render()`.

## Where to look

The end-to-end tests in `tests/test_eval.py` evaluate the `knowledge`
calculation question offline (no LLM) and assert a fully grounded, computed
report — the same shape you can point at any example pipeline.