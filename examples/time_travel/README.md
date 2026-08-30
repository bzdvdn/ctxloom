# time_travel

**Port of "time travel" / check-pointed branching** (LangGraph checkpoints +
replay; git-like branch-run-merge): after a milestone commit the app forks the
context and runs two candidate experiments **in parallel** on their own
branches, merges them three-way, and deterministically picks the better
candidate — linking the decision back to both (§39-§40).

```bash
uv run python -m examples.time_travel.main
```

The same session can be replayed to the milestone with
`python -m ctxloom replay <sessions> --session … --version …` (§55).

Demonstrates: `Context.branch()`, parallel runtimes, explicit three-way
`merge()`, provenance kept across forks, deterministic ranking (§67).
