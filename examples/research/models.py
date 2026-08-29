"""Research demo models.

Each example in this repo owns its artifact models (§4) — nothing is shared
between knowledge / devops / repair / research, so demos stay independent.
"""

from pydantic import BaseModel


class UserQuery(BaseModel):
    text: str
    session_id: str = ""


class ResearchTurn(BaseModel):
    """Marker «this question needs web research», with a lifecycle."""

    query_id: str
    text: str
    status: str = "researching"  # researching → answerable → answered | insufficient


class SearchDone(BaseModel):
    """Deterministic marker «source fan-out finished» (§42 idempotency)."""

    query_id: str


class TypedDoc(BaseModel):
    """Materialized page (url as `path`), provenance via relations."""

    source_id: str
    path: str
    content: str
    query_id: str = ""
    score: float = 0.0


class Evidence(BaseModel):
    """Key fact with provenance (`source` = url), §18."""

    query_id: str
    text: str
    source: str
    score: float = 0.0


class Claim(BaseModel):
    """Verifiable claim with confidence (§35); the model is not the truth (§68)."""

    query_id: str
    text: str
    confidence: float = 0.0
    status: str = "unverified"  # unverified | verified | weak


class AnswerBody(BaseModel):
    """Internal structured-LLM schema for a piece of the answer."""

    text: str


class Answer(BaseModel):
    """Final answer with URL sources (§17)."""

    query_id: str
    text: str
    sources: list[str] = []
