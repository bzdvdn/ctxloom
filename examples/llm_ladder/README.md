# llm-ladder

The LLM workflow, from the simplest turn to state-changing patches — three
self-contained levels that grow the artifact/patch vocabulary step by step.

Every level runs **offline** (no `.env`) with an honest deterministic fallback,
or with a real model once `LLM_PROVIDER` is set (see `.env.example`).

```bash
uv run python -m examples.llm_ladder.level1   # one call → one create effect
uv run python -m examples.llm_ladder.level2   # two calls → linked patch (+ provenance)
uv run python -m examples.llm_ladder.level3   # lifecycle → StatusMachine updates (+ links)
```

## Level 1 — the simplest turn

```text
Question ──structured_llm(AnswerBody)──▶ self.effects.create(Answer, id="answer:{qid}")
```

One question in, one `Answer` out. Things every level shares:

- a **guard** returns `None` when the work is already done (idempotency, §42);
- one **`structured_llm`** call with a schema — parsing stays in code, the model
  only reasons (§67);
- the produce returns a **single `Patch`** — here just one `create`;
- with no model, `structured_llm` returns `None` and a fallback answers honestly
  (offline mode, §59).

## Level 2 — a linked patch

```text
Question + Doc ──► create Evidence ──extracted_from──▶ Doc
               ──► create Answer   ──supported_by──▶  Evidence
```

Two LLM calls (word the evidence, synthesize the answer) and *two* artifacts and
*two* provenance edges in **one returned patch** (§34). Planned artifacts are
linked by *handles*, not ids (§38):

```python
evidence = self.effects.create(Evidence(...), id="evidence:q1")
answer = self.effects.create(Answer(...), id="answer:q1")
evidence.link("extracted_from", doc)     # doc: Artifact
answer.link("supported_by", evidence)    # evidence: effect handle
return None
```

## Level 3 — lifecycle and state-changing patches

```text
Question ──► Turn(status=new)
Turn      ──► Claim (LLM) ──for_turn──▶ Turn
Claim     ──► StatusMachine: Turn(status=answered)     ← an update patch (§69)
answered  ──► Answer (LLM) ──supported_by──▶ Claim
```

A `StatusMachine` moves the turn's `status` — its transitions are `update_fields`
patches with a pure `next_status`, guarded by `terminal` (§69). Working memory is
**artifacts**, not a chat buffer; each produce stays one concern, one guard, one
effect-set.

## Learning path

| Level | Patch vocabulary | Teachings |
| --- | --- | --- |
| 1 | `create` | guard, schema, `structured_llm`, honest `None` |
| 2 | 2 creates + 2 links (one atomic effect set) | provenance is first-class (§34), composition |
| 3 | lifecycle `update_fields` + `create` + `link` | state transitions as patches, §69 |

See the bilingual tutorial: `docs/en/tutorial.md`, `docs/ru/tutorial.md`.