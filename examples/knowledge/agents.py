"""Demo-assistant agents — thin containers (§46, §48).

Logic lives in the Produce classes (`examples/assistant_produce.py`);
here we only declare the consumes/produces contracts.
"""

from ctxloom import Agent, Consume, Produce
from ctxloom.sources import SourceRef

from .models import (
    Answer,
    Calculation,
    Claim,
    Evidence,
    ResearchTurn,
    SearchDone,
    Spreadsheet,
    TypedDoc,
    UserQuery,
)
from .produce import (
    BuildAnswer,
    CalculateAggregate,
    EvaluateTurn,
    ExtractEvidence,
    PlannerReply,
    PlannerTurn,
    ResolveRef,
    ResolveTable,
    ScoutSources,
    VerifyClaims,
)


class Planner(Agent):
    """Router: greeting/direct → ChatReply, research → ResearchTurn."""

    name = "planner"
    consumes = [Consume(UserQuery)]
    produces = [PlannerReply(), PlannerTurn()]


class SearchScout(Agent):
    """Fan-out over sources: refs → SourceRef + search-complete marker."""

    name = "search_scout"
    consumes = [Consume(ResearchTurn)]
    produces = [ScoutSources(), Produce(SearchDone)]


class ResolverAgent(Agent):
    """Lazy materialization of a text link into a typed document."""

    name = "resolver"
    consumes = [Consume(SourceRef)]
    produces = [ResolveRef()]


class TableResolver(Agent):
    """Lazy materialization of a structured ref into a spreadsheet (§29)."""

    name = "table_resolver"
    consumes = [Consume(SourceRef)]
    produces = [ResolveTable()]


class EvidenceBuilder(Agent):
    """Extracts key facts from a document."""

    name = "evidence_builder"
    consumes = [Consume(TypedDoc)]
    produces = [ExtractEvidence()]


class VerifierAgent(Agent):
    """Verifies facts: builds claims with confidence and finds contradictions."""

    name = "verifier"
    consumes = [Consume(Evidence)]
    produces = [VerifyClaims()]


class CalculatorAgent(Agent):
    """Computes over the spreadsheet if the question asks for an aggregate (§29, §67)."""

    name = "calculator"
    consumes = [Consume(Spreadsheet)]
    produces = [CalculateAggregate()]


class ProgressEvaluator(Agent):
    """Deterministic turn overseer: moves statuses forward (§24, §69).

    Consumes research lifecycle events: search, documents, evidence, claims,
    calculations, the final answer — recomputes the needed status on each one.
    """

    name = "progress_evaluator"
    consumes = [
        Consume(ResearchTurn),
        Consume(SourceRef),
        Consume(TypedDoc),
        Consume(Evidence),
        Consume(Claim),
        Consume(Spreadsheet),
        Consume(Calculation),
        Consume(SearchDone),
        Consume(Answer),
    ]
    produces = [EvaluateTurn()]
    priority = 100


class AnswerBuilder(Agent):
    """Assembles the answer once the turn becomes answerable (§17)."""

    name = "answer_builder"
    consumes = [Consume.by_field(ResearchTurn, "status", "answerable")]
    produces = [BuildAnswer()]
