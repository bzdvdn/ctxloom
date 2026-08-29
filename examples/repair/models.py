"""Repair assistant models: project, design, plan, estimate (§4, §17)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UserMsg(BaseModel):
    text: str
    session_id: str = ""


class ChatReply(BaseModel):
    """Assistant reply to the user (question, alternatives, plan, estimate)."""

    text: str
    query_id: str = ""
    kind: str = "text"  # text | approval
    images: list[str] = []


class ProjectInfo(BaseModel):
    """Project facts extracted from the chat; every field is optional (extra=forbid).

    Geometry is computed deterministically from area/length/width/ceiling_height.
    """

    model_config = ConfigDict(extra="forbid")

    room_type: str | None = None
    area: float | None = None
    ceiling_height: float | None = None
    length: float | None = None
    width: float | None = None
    budget: float | None = None
    style: str | None = None
    wall_color: str | None = None
    ceiling_color: str | None = None
    floor_material: str | None = None
    floor_area: float | None = None
    walls_area: float | None = None
    ceiling_area: float | None = None
    perimeter: float | None = None


class DesignOption(BaseModel):
    """Design option; fields are optional — local/raw models may leave some
    unset, and such an option still does not break the whole list."""

    name: str = ""
    palette: dict[str, str] = {}
    description: str = ""
    preview: str = ""


class DesignOptions(BaseModel):
    options: list[DesignOption]


class AssistantReply(BaseModel):
    text: str


class PlanStep(BaseModel):
    name: str
    description: str
    materials: list[str] = []


class RepairPlan(BaseModel):
    steps: list[PlanStep] = []


class EstimateLine(BaseModel):
    name: str
    quantity: float | None = None
    unit: str = ""
    unit_price: float | None = None
    total: float | None = None


class Estimate(BaseModel):
    lines: list[EstimateLine] = []
    subtotal: float | None = None
    total: float | None = None
    warnings: list[str] = []


class Project(BaseModel):
    """Final state of the conversation — an artifact whose `stage` drives routing."""

    stage: str = "collect"
    info: ProjectInfo = ProjectInfo()
    design_options: list[DesignOption] = []
    design_choice: str = ""
    palette: dict[str, str] = {}
    plan: list[PlanStep] = []
    estimate: Estimate | None = None
    approved: bool = False
    handled_msg: str = ""
