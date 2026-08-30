# adaptive

**Port of the hybrid scheduler idea (§26, §24)**: not every scheduling decision
needs an LLM — filter hard rules deterministically, rank with a metric, and
only fall back to an LLM on a *tie*.

The runtime accepts `scheduler=`:

```python
runtime = Runtime(
    ctx,
    agents=[...],
    scheduler=uncertainty_policy(
        rules=[not_b_for_x],        # prune candidates before ranking
        metric=support_split,       # rank: ordering only (never drops)
        llm_tie_break=0.05,         # LLM on near-tie, rarely; skipped offline
    ),
)
```

Two competing artists can summarize a `Task`; the policy decides the outcome:

- hard rule prunes capability 'b' for tag 'x' (so it never reaches ranking);
- the metric ranks 'b' first when the text mentions money;
- an HITL approval (§60) is pinned to the front and never loses to ranking;
- with a model and a tie, one structured call orders the top pair.

```bash
uv run python -m examples.adaptive.main             # "money" → picked: b
uv run python -m examples.adaptive.main --tag x     # rule prunes b entirely
```

Demonstrates: `Agent.capabilities` (§25), `Scheduler` filter/rank/LLM stages,
no-starvation fallback, HITL pin.
