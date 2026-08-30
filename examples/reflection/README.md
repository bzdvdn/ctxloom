# reflection

**Port of the "Reflection" agent** (LangGraph): generate → critique → regenerate.

The flow is pure runtime: a `Draft` artifact is created, a `Critic` produce
scores it (structured LLM, `ReviewBody`), and a `Rewrite` produce improves the
draft with the feedback — deterministically capped (`MAX_ROUNDS`) and stopped
early by an `accepted` status (`ACCEPT_AT`). Working memory is **artifacts**,
not a chat buffer.

```bash
uv run python -m examples.reflection.main [--topic "..."]
```

Without a model (`llm_from_env()` → None) the loop still runs deterministically
(offline fallbacks, §59): the draft is echoed, the critic scores it `0.4`, so
the loop iterates to the `MAX_ROUNDS` cap and finalizes.

Demonstrates: `self.effects` authoring (create + update across the loop),
deterministic guards as eligibility, structured LLM + honest `None` fallbacks,
artifact-state-driven termination (§69).
