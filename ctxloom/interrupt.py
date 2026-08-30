from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PendingQuestion(BaseModel):
    """Artifact awaiting a human response (HITL, constitution §60).

    Created by an agent (or directly) to block a step until user input.
    A human answer is recorded via `self.effects.resume(question, answer)` (§60),
    after which agents subscribed to `PendingQuestion(answered=True)` continue.
    """

    question: str
    kind: str = "general"
    notes: dict[str, Any] = Field(default_factory=dict)
    answered: bool = False
    resolution: str | None = None
    resolved_at: datetime | None = None
