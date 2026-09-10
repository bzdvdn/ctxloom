"""Record/replay glue for `reactifact.testing` — reuses `reactifact.replay.ReplayLLM` directly.

No new recording mechanism: `ReplayLLM` already records/replays LLM calls to
a JSONL file (`reactifact/replay.py`). This module only decides *whether* to
wrap `context.resources.llm` with it, based on a scenario's `mode`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, get_args

from reactifact.providers import LLMProvider
from reactifact.replay import ReplayLLM

Mode = Literal["live", "record", "replay"]

MODE_ENV_VAR = "REACTIFACT_SCENARIO_MODE"


def wrap_llm(
    inner: LLMProvider | None, *, mode: Mode, recording_path: Path
) -> LLMProvider | None:
    """Returns `inner` unchanged in `"live"` mode, or a `ReplayLLM` wrapper otherwise."""
    if mode == "live" or inner is None:
        return inner
    return ReplayLLM(
        str(recording_path),
        mode=mode,
        inner=inner,
        model=str(getattr(inner, "model", "") or ""),
    )


def mode_from_env(default: Mode = "live") -> Mode:
    """Reads the scenario mode from `$REACTIFACT_SCENARIO_MODE` (set by `reactifact
    scenario --mode ...`), falling back to `default` when unset.

    Lets a scenario module stay agnostic of the CLI: build the `ScenarioLab`
    with `mode=mode_from_env()` and the same scenario runs live, records, or
    replays depending only on how it was invoked.
    """
    value = os.environ.get(MODE_ENV_VAR, default)
    if value not in get_args(Mode):
        raise ValueError(
            f"{MODE_ENV_VAR}={value!r} is not a valid mode "
            f"(expected one of {get_args(Mode)})"
        )
    return value  # type: ignore[return-value]
