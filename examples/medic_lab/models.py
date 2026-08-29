"""medic-lab models — evidence-based hypothesis laboratory.

A question spawns competing hypotheses; each is investigated over evidence
sources (local fixtures by default, optional live web), scored by
support/contradiction, and answered with an explicit uncertainty ranking.
"""

from pydantic import BaseModel


class Question(BaseModel):
    text: str
    session_id: str = ""
    depth: int = 0
    #: hypothesis_id → clarifying sub-questions the model proposed for a deepen round.
    deepen_queries: dict[str, list[str]] = {}


class Hypothesis(BaseModel):
    """Candidate answer; status drives the investigation channel."""

    question_id: str
    statement: str
    status: str = "open"  # open → investigating → supported | refuted | inconclusive
    score: float = 0.0
    supports: int = 0
    contradicts: int = 0
    coverage: int = 0
    confidence: float = 0.0


class Evidence(BaseModel):
    """Fact supporting/contradicting hypotheses (§18), tagged per hypothesis."""

    question_id: str
    hypothesis_id: str
    text: str
    source: str
    score: float = 0.0


class Claim(BaseModel):
    """Verifiable statement with confidence (§35); not the truth itself (§68)."""

    question_id: str
    hypothesis_id: str
    text: str
    confidence: float = 0.0
    status: str = "unverified"


class HypothesisRank(BaseModel):
    hypothesis_id: str
    statement: str
    score: float
    supports: int
    contradicts: int
    coverage: int
    confidence: float
    verdict: str


class TypedDoc(BaseModel):
    """Materialized page for one hypothesis channel (lazy, §6)."""

    question_id: str
    hypothesis_id: str
    round: int = 0
    source_id: str
    path: str
    content: str
    score: float = 0.0


class SearchDone(BaseModel):
    """Idempotency marker: «this hypothesis channel is searched» (§42)."""

    hypothesis_id: str
    round: int = 0
    question_id: str = ""


class ResearchReport(BaseModel):
    question_id: str
    answer: str
    uncertainty: str
    ranking: list[HypothesisRank] = []
