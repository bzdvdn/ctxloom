"""forklab models — branch & merge demonstration (§39-§40)."""

from __future__ import annotations

from pydantic import BaseModel


class Question(BaseModel):
    """A single question the two strategies investigate.

    The model must know the domain it works in (§68): `topic` carries the
    domain context (a product area, a research theme) for every prompt.
    """

    text: str
    topic: str = "thermal energy recovery in HVAC design"


class Strategy(BaseModel):
    """Which fork-strategy to run in the branch it was spawned in."""

    branch: str
    kind: str  # "depth" | "breadth"


class EvidenceBody(BaseModel):
    """Structured wording of a finding (the LLM owns the sentence, not the score)."""

    text: str


class Evidence(BaseModel):
    """A finding produced on one of the branches."""

    branch: str
    source: str
    text: str
    score: float


class Review(BaseModel):
    """Trigger to evaluate the merged state (created after the merge)."""

    base_on: str = "merged"


class AnswerBody(BaseModel):
    """Structured synthesis of the answer over merged evidence."""

    text: str


class Answer(BaseModel):
    """The final answer: sources are deterministic, the wording may be LLM-made."""

    text: str
    sources: list[str]


class Budget(BaseModel):
    """A shared artifact in the base — used to demonstrate an explicit merge
    conflict (§40): both forks change it, the merge must not choose silently."""

    tokens: int = 0
