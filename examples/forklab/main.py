"""forklab main — CLI entry for the branch & merge demo (§39-§40).

The orchestration lives in `pipeline.py`; this file only parses arguments and
prints. The model is optional (§68): with `LLM_PROVIDER` set in `.env` the run
auto-switches to model mode (several calls across the flow); without it the
honest deterministic fallback runs offline (§59).

    uv run python -m examples.forklab.main            # offline mode (no .env)
    uv run python -m examples.forklab.main --mermaid  # also the merged provenance graph
    uv run python -m examples.forklab.main --conflict # an explicit MergeConflict (§40)
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from ctxloom import Context
from ctxloom.providers import openai_llm, openrouter_llm
from ctxloom.viz import context_to_mermaid

from .pipeline import result_data, run


def build_llm() -> Any | None:
    """Explicit provider for this demo: OpenRouter (default) or a local
    OpenAI-compatible endpoint; `None` when no key is configured → offline."""
    import os

    if os.getenv("OPENROUTER_API_KEY"):
        return openrouter_llm(max_tokens=2048)
    if os.getenv("OPENAI_BASE_URL"):
        return openai_llm(
            base_url=os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL"),
            max_tokens=2048,
        )
    return None


def _summary(merged: Context) -> str:
    data = result_data(merged)
    budget = merged.get("budget:1")
    budget_tokens = budget.data.tokens if budget is not None else None
    llm_state = (
        "model" if merged.resources.llm is not None else "deterministic (offline)"
    )
    lines = [
        "fork-lab · merge outcome",
        f"  llm mode:          {llm_state}",
        f"  merged version:    v{data['version']}",
        f"  evidences:         {sum(data['splits'].values())} (branch split: {data['splits'] or 'none'})",
        f"  budget artifact:   {budget_tokens} tokens",
    ]
    lines.append("  answer text:")
    if not data["answer"]:
        lines.append("    (no answer)")
    else:
        lines += [f"    {line}" for line in data["answer"].splitlines()]
    lines.append(
        "  sources: " + (", ".join(data["sources"]) if data["sources"] else "—")
    )
    lines.append(f"  provenance links: {len(merged.relations())}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m examples.forklab.main")
    parser.add_argument(
        "--question",
        default="Which design recovers the most thermal energy?",
    )
    parser.add_argument(
        "--topic",
        default="thermal energy recovery in HVAC design",
        help="domain context that every model prompt carries (§68)",
    )
    parser.add_argument("--mermaid", action="store_true")
    parser.add_argument("--conflict", action="store_true")
    args = parser.parse_args()

    merged = run(
        question=args.question,
        topic=args.topic,
        conflict=args.conflict,
        llm=build_llm(),
    )
    print(_summary(merged))
    if args.mermaid:
        print("\n" + context_to_mermaid(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
