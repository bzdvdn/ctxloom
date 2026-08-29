"""Research demo agents — thin containers, example-local (§48)."""

from ctxloom import Agent, Consume, Produce
from ctxloom.sources import SourceRef

from .models import (
    Answer,
    Claim,
    Evidence,
    ResearchTurn,
    SearchDone,
    TypedDoc,
    UserQuery,
)
from .produce import (
    BuildAnswer,
    EvaluateTurn,
    ExtractEvidence,
    ResolveRef,
    Router,
    VerifyClaims,
    WebScout,
)


class RouterAgent(Agent):
    name = "router"
    consumes = [Consume(UserQuery)]
    produces = [Router()]


class WebScoutAgent(Agent):
    name = "web_scout"
    consumes = [Consume(ResearchTurn)]
    produces = [WebScout(), Produce(SearchDone)]


class ResolverAgent(Agent):
    """Lazy materialization of a URL ref into a page document."""

    name = "resolver"
    consumes = [Consume(SourceRef)]
    produces = [ResolveRef()]


class EvidenceBuilder(Agent):
    """Extracts key facts from a fetched page."""

    name = "evidence_builder"
    consumes = [Consume(TypedDoc)]
    produces = [ExtractEvidence()]


class VerifierAgent(Agent):
    """Turns facts into claims with confidence against the source page."""

    name = "verifier"
    consumes = [Consume(Evidence)]
    produces = [VerifyClaims()]


class EvaluatorAgent(Agent):
    """Deterministic turn lifecycle: research → answerable | insufficient (§24)."""

    name = "evaluator"
    consumes = [
        Consume(ResearchTurn),
        Consume(SourceRef),
        Consume(TypedDoc),
        Consume(Evidence),
        Consume(Claim),
        Consume(SearchDone),
        Consume(Answer),
    ]
    produces = [EvaluateTurn()]
    priority = 100


class AnswerBuilder(Agent):
    """Assembles the answer when the turn is answerable."""

    name = "answer_builder"
    consumes = [Consume.by_field(ResearchTurn, "status", "answerable")]
    produces = [BuildAnswer()]


def research_agents() -> list[Agent]:
    """The full research agent set, in running order."""
    return [
        RouterAgent(),
        WebScoutAgent(),
        ResolverAgent(),
        EvidenceBuilder(),
        VerifierAgent(),
        EvaluatorAgent(),
        AnswerBuilder(),
    ]
