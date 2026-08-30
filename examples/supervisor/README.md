# supervisor

**Port of the router + specialist + human approval** pattern (CrewAI roles,
AutoGen two-agent approval, LangGraph HITL gate).

A `Request` is routed (structured LLM `RouteBody`, deterministic keyword
fallback) to a specialist produce; the specialist returns a `SpecialistReport`;
then a supervisor produce asks the human to **approve** (`effects.ask`) and
records the answer with `effects.resume` (§60). "да" → the report is the final
reply; otherwise an honest "please refine" reply.

```bash
uv run python -m examples.supervisor.main
```

Run(`run()`) simulates the human answer so the CLI and tests complete
deterministically; a real web/chat app would stream the pending question and
let the user answer.

Demonstrates: `effects.ask`/`effects.resume` HITL, role-based produces, routing
as structured output.
