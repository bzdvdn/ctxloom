"""forklab agents — thin containers: one per fork-strategy, one for the merge."""

from __future__ import annotations

from ctxloom import Agent, Consume

from .models import Review, Strategy
from .produce import BreadthInvestigate, DepthInvestigate, Evaluate


class StrategyAgent(Agent):
    """Runs in a *single* branch: spawn the Strategy first, this reacts."""

    name = "strategy"
    consumes = [Consume(Strategy)]
    produces = [DepthInvestigate(), BreadthInvestigate()]


class EvaluatorAgent(Agent):
    """Runs on the merged context and produces the final Answer."""

    name = "evaluator"
    consumes = [Consume(Review)]
    produces = [Evaluate()]
