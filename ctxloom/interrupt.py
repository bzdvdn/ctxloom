from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .artifacts import Artifact
from .patches import Patch


class PendingQuestion(BaseModel):
    """Artifact awaiting a human response (HITL, constitution §60).

    Created by an agent (or directly) to block a step until user input.
    A human answer is an ordinary patch (`Context.resume`), after which agents
    subscribed to `PendingQuestion(answered=True)` continue working.
    """

    question: str
    kind: str = "general"
    notes: dict[str, Any] = Field(default_factory=dict)
    answered: bool = False
    resolution: str | None = None
    resolved_at: datetime | None = None


class InterruptPatch(Patch):
    """Patch for HITL: base Patch operations + human-answer semantics (§60).

    Produce functions cannot mutate the context (`Context.resume` is unavailable
    to them), so the answer to a question is returned as an ordinary patch.
    """

    def answer(
        self, question: Artifact[PendingQuestion], resolution: str
    ) -> InterruptPatch:
        """Mark the `PendingQuestion` as answered and continue the flow."""
        self.update_fields(
            question,
            answered=True,
            resolution=resolution,
            resolved_at=datetime.now(UTC),
        )
        return self
