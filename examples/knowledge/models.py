from pydantic import BaseModel


class UserQuery(BaseModel):
    text: str
    session_id: str = ""


class ChatReply(BaseModel):
    """Planner's direct reply (greeting / direct), no research."""

    query_id: str
    text: str
    kind: str = "direct"  # greeting | direct


class ResearchTurn(BaseModel):
    """Marker «the question needs a search» with a lifecycle.

    status: researching → answerable → answered | insufficient (§69).
    """

    query_id: str
    text: str
    status: str = "researching"


class SearchDone(BaseModel):
    """Deterministic marker «source search complete» for a turn."""

    query_id: str


class TypedDoc(BaseModel):
    source_id: str
    path: str
    content: str
    query_id: str = ""
    score: float = 0.0


class Evidence(BaseModel):
    """Key fact with provenance (source:locator), §18."""

    query_id: str
    text: str
    source: str
    score: float = 0.0


class Claim(BaseModel):
    """A verifiable claim with confidence (§19, §35).

    Built from Evidence and checked against the source document: `status`
    reflects the strength of the confirmation (verified / weak / unverified),
    `conflict` — whether a contradicting claim was found in another source (§36).
    """

    query_id: str
    text: str
    confidence: float = 0.0
    status: str = "unverified"  # unverified | verified | weak
    conflict: bool = False


class Spreadsheet(BaseModel):
    """Structured spreadsheet data (§29): keep the table, not the text.

    columns/rows — schema and values. The agent can compute over them
    (without hallucinating) using deterministic aggregation (§67).
    """

    source_id: str
    path: str
    columns: list[str]
    rows: list[list[str]]
    query_id: str = ""


class Calculation(BaseModel):
    """Computation result with provenance (§33, §67): operation + derived_from."""

    query_id: str
    description: str
    value: float | int | str
    column: str = ""
    rows: int = 0


class AnswerBody(BaseModel):
    """Internal structured-LLM schema for a reply chunk."""

    text: str


class Answer(BaseModel):
    """Final answer assembled from patches, with a list of sources (§17)."""

    query_id: str
    text: str
    sources: list[str] = []
