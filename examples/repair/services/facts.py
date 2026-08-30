"""repair services — required facts, labels, and the pipeline stages."""

from __future__ import annotations

#: Fields required before the project can advance.
REQUIRED_FACTS: tuple[str, ...] = ("room_type", "area", "budget")

#: Human-readable project field names (for the «Уточните…» questions).
FACT_LABELS: dict[str, str] = {
    "room_type": "тип помещения",
    "area": "площадь",
    "budget": "бюджет",
    "ceiling_height": "высоту потолков",
    "length": "длину",
    "width": "ширину",
    "style": "стиль",
    "wall_color": "цвет стен",
    "ceiling_color": "цвет потолка",
    "floor_material": "пол",
}

#: Pipeline stages in order.
STAGES: tuple[str, ...] = (
    "collect",
    "design_choice",
    "plan",
    "estimate",
    "final_approval",
    "assistant",
)

__all__ = ["FACT_LABELS", "REQUIRED_FACTS", "STAGES"]
