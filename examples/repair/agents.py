"""Repair assistant agent — a container over the staged Produce (§71)."""

from ctxloom import Agent, Consume, PendingQuestion, Produce

from .models import ChatReply, Project, UserMsg
from .produce import (
    ApprovalStage,
    AssistantStage,
    CollectStage,
    EstimateStage,
    PickStage,
    PlanStage,
)


class RepairFlow(Agent):
    """Single dispatcher: reacts to messages and project changes.

    Each stage is its own Produce with a deterministic guard; routing follows
    `Project.stage` — the runtime builds links from the artifact state.
    """

    name = "repair_flow"
    consumes = [Consume(UserMsg), Consume(Project)]
    produces = [
        CollectStage(),
        PickStage(),
        PlanStage(),
        EstimateStage(),
        ApprovalStage(),
        AssistantStage(),
        Produce(ChatReply),
        Produce(PendingQuestion),
    ]
