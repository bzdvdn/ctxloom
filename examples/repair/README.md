# repair — budget-aware replanning demo

A room-repair assistant: it gathers the project facts (room type, area, budget),
optionally asks you for design decisions, builds a plan and a material estimate
from the local price catalog, and — when you say the plan is over budget —
**replans** from the plan stage instead of just trimming the estimate.

> **Note:** the chat and its demo data (catalog, plan, palettes) are intentionally
> in **Russian**. The code and comments are in English; the runtime/prompting text
> stays Russian because the demo targets a Russian repair workflow. Example:
> `«сделай ремонт ванной»`.

## Run

```bash
.venv/bin/python examples/repair/chat.py     # console, no API keys needed
.venv/bin/python examples/repair/web.py      # FastAPI + SSE web UI on :8000
```

## Highlights demonstrated

- `Context`-driven state machine via `Project.stage` (collect → design → approval),
  no explicit graph.
- Human-in-the-loop: `PendingQuestion` for approvals and design picks; humans
  answer in natural language, not buttons.
- Deterministic estimate from `data/price.csv` (lexical match, no LLM, §67) with
  budget-aware replan: going over budget rebuilds the *plan*, not just the total.
- Honest fallbacks: without an LLM the demo still runs — canned replies,
  fallback design options, and clear "can't decide honestly" messages (§59, §68).

## Data

`data/price.csv` is a real-weight construction catalog (bricks, plywood,
drywall, blocks) in ₽; `data/materials.csv` is a small curated list for the
fast catalog demo. Both are Russian by design (see the note above).