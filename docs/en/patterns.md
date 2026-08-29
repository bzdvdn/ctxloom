# Patterns

Reusable patterns observed across the five examples. They are not abstract —
each is concretely instantiated in `examples/`.

## HITL: humans as first-class participants

A human is just another reaction to the context. The runtime represents a
question with `PendingQuestion`:

```python
class PendingQuestion(BaseModel):
    question: str
    kind: str = "general"          # e.g. "clarify", "approval"
    notes: dict[str, Any] = {}     # routing info ("which agent asked")
```

A `Produce` creates one with `InterruptPatch()`:

```python
return InterruptPatch().answer(question_artifact, "да")
```

`InterruptPatch` stops the run, records the question, and takes the answer back
in — the producing agent sees the answer as a new event (the corresponding
`PendingQuestion` artifact is updated). Web demos query
`context.pending_questions()` to know whether to render a "waiting" state.

Pattern: **activate stage → immediately ask** (the repair `ApprovalStage`
creates the approval `PendingQuestion` the moment it becomes eligible, without
waiting for a user message), then **react to the answer** on the next event.

## Tool agents: LLM + tools (blocking or HITL)

For "the model decides which tool to call" flows, use the built-in agents:

```python
from ctxloom import HITLLMAgent, Consume, Produce

class OpsAgent(HITLLMAgent):
    name = "ops"
    system = "You run Kubernetes/GitLab/Ansible tasks."
    tools = [...]        # FunctionTool instances
    max_steps = 8
    max_asks = 2
    consumes = [Consume(Project)]
    produces = [Produce(Report)]
```

- `LLMAgent` — blocking loop: the LLM emits `tool_call`, the runtime runs the
  tool, the observation feeds the next step. No human in the loop.
- `HITLLMAgent` — same, plus the LLM can emit `ask`: a `PendingQuestion` is
  created, the loop pauses, and the human's answer returns as
  `Observation(source="user")`. Tool *execution* itself is also gated by
  `ToolUseHITL`, so risky commands wait for a human click before running.

The `devops` example is the canonical `HITLLMAgent` demo (LLM tool router +
approval for K8s/GitLab/Ansible mutations).

## Structured output: never parse raw JSON yourself

The runtime wraps a single LLM call into a `pydantic` schema with retries and
lenient JSON parsing:

```python
from ctxloom import structured_llm
from ctxloom.structured import StructuredLLM

# procedural variant:
body = await structured_llm(
    context, schema=AnswerBody,
    system="You assemble coherent answers.",
    user=f"Question: {question}\nFacts: {facts}",
)

# re-usable object variant:
_extractor = StructuredLLM(ProjectInfo, system="Extract repair facts; unknown = null")
facts = await _extractor.call(context, user=message_text)
```

Both return `None` on a missing model or a parse failure after retries — and the
caller is expected to handle `None` (see fallbacks).

`StructuredGenerateAgent` is the declarative wrapper: override
`build_prompt(inputs)`, optionally `fallback(inputs)`, declare `schema` — and
the reading/writing provenance is recorded for you.

## Fallbacks: honest degradation

Deterministic work stays deterministic; generative work degrades *honestly*:

1. If **no model is configured** — use the deterministic variant
   (canned options, fallback plans): demo mode without a key.
2. If a **model returns nothing usable** — do NOT substitute canned answers;
   report the failure openly: *"Не удалось подобрать варианты…"*.

The `repair` example implements both paths in `_make_design_options`:
`fallback_options` only when `context.resources.llm is None`, otherwise a
clear failure message.

## Cost/rollback model ("change → rebuild")

Long multi-stage conversations occasionally need to *go back*. The `repair`
example models this as: parse the change request → determine the earliest stage
affected → reset everything downstream deterministically:

```python
target = rollback_target(changed)      # "plan" | "estimate" | …
updates = _downstream_resets(target)   # clears design_options/plan/estimate
updates |= {"stage": target, "info": new_info, "handled_msg": ""}
```

Resetting `handled_msg` re-arms the stages so the rebuild actually runs. This
is the manual twin of `StatusMachine` — for those workflows where rollback is
part of the product, not a lifecycle.

## Budget and fairness

`Budget` caps a run:

```python
runtime = Runtime(ctx, agents=[...], budget=Budget(max_runs=200), max_concurrency=2)
```

- `max_runs`, `max_iterations`, `max_time_s`, tool-call caps — the runtime
  stops and reports `RunOutcome` (`completed` | `budget_exhausted` | …) with
  `RunStats`.
- `Agent.concurrency_limit` (LLM-bound agents default to a lower cap) + the
  runtime's global `max_concurrency` keep provider rate limits happy — the
  `medic-lab` demo runs a hypothesis laboratory with a LLM-limit of 2 inside a
  global cap of 6.

## Chat memory with sessions

State lives in the context, so *chat memory is just state*. Across requests:

```python
store = SessionStore(FileKVBackend("sessions"))
session = store.open(session_id, resources=resources)
# ...create UserMsg, astream, session.save()
```

`store.open` rehydrates the context from the last checkpoint; a background
agent (`@consume`/trigger) can trim history, update a `handled_msg` pointer, and
patch pending questions. The web demos ship this pattern verbatim.

## Status machines for long lifecycles

See [recipes](recipes.md). The rule of thumb for choosing between patterns:

| Situation | Approach |
| --- | --- |
| An artifact moves through phase states | `StatusMachine` + verify-produce |
| A workflow needs to roll *back* on user edits | stage guard + `_downstream_resets` |
| "Which of these did the model pick?" | `PickStage`-style parse + guard |

## Determinism as a habit

- Make eligibility a guard, not a lucky scheduling accident (`return None` early).
- Prefer stable ids (`answer:{qid}`, `ref:{sid}:{owner}`) → idempotent re-runs.
- Pure decision functions (`next_status`) are unit-testable without a runtime.
- Every LLM call has a structured schema, a retry budget, and a `None` path.