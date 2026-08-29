# medic-lab — an evidence-based hypothesis laboratory

A single question spawns **competing hypotheses**; each is investigated over an
evidence pool (local fixtures by default, optional live web via
`MEDIC_LAB_URLS`), scored by support/contradiction, and answered with an
explicit uncertainty ranking. A human can **deepen a hypothesis** before the
report is produced (§60).

## Run

```bash
.venv/bin/python examples/medic_lab/chat.py    # console with steering
.venv/bin/python examples/medic_lab/main.py     # FastAPI + SSE UI on :8002
```

fixtures live in `examples/medic_lab/pages/*.md` (pro / contra / neutral);
set `MEDIC_LAB_URLS=https://…,https://…` to also investigate live pages.

## What it demonstrates

- **Hypotheses as artifacts** (§20): `Hypothesis` with an `open → investigating
  → supported | refuted | inconclusive` lifecycle.
- **Parallel per-hypothesis channels** without branching: every ref/evidence/
  claim is tagged `hypothesis_id`, and `Consume(condition)` fans the scheduler
  out across channels (§21, §24).
- **Deterministic support vs contradiction** (§67): a page's lean
  (pro/contra/neutral) decides which hypotheses it supports or contradicts —
  no LLM, no theatre.
- **Cross-hypothesis contradictions** (§36): `Claim —contradicted_by→ Claim`
  between hypotheses with similar wording and opposite polarity.
- **Human steering (HITL)** (§60): when every hypothesis is terminal, the lab
  asks — deepen `H<N>` (reopens the channel for another round) or `stop` for
  the report. Depth is bounded (`MAX_DEPTH`).
- **Honest uncertainty** (§68, §70): the report ranks by score and names
  inconclusive/refuted alternatives instead of pretending certainty.

The report: `ResearchReport` with a ranked list
(`HypothesisRank`: score, supports, contradicts, coverage, confidence, verdict)
provenanced back to the evidence via relations.