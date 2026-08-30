"""repair services — the "change → rebuild" stage routing (§22/§24).

Built on the generic `recipes.rollback` helpers; the map below is the repair
workflow's own field→stage table.
"""

from __future__ import annotations

from ctxloom.recipes import earliest_stage

#: Which project field a change belongs to → the stage it invalidates.
_FIELD_STAGES: dict[str, str] = {
    "room_type": "collect",
    "style": "design_choice",
    "wall_color": "design_choice",
    "ceiling_color": "design_choice",
    "floor_material": "design_choice",
    "area": "plan",
    "length": "plan",
    "width": "plan",
    "ceiling_height": "plan",
    "budget": "estimate",
}
_STAGE_ORDER = ("collect", "design_choice", "plan", "estimate")


def rollback_target(changed: set[str]) -> str:
    """The strongest change determines the stage from which to rebuild."""
    return (
        earliest_stage(changed, field_stages=_FIELD_STAGES, order=_STAGE_ORDER)
        or "estimate"  # no changes — stay at the final approval
    )


__all__ = ["rollback_target"]
