"""llm-ladder — the LLM workflow from simple to complex patches (§67, §68).

Three runnable levels, each self-contained, each teaching one step more of the
artifact/patch vocabulary:

    level1 — one structured LLM call → a simple `self.effects.create(Answer)`;
    level2 — two LLM calls → a linked patch (Evidence + Answer + provenance);
    level3 — lifecycle: Turn → Claim → StatusMachine update → Answer (+ links).

Run offline (no `.env`) or with a model — see `README.md`.
"""

from __future__ import annotations

__all__: list[str] = []
