"""Deterministic repair-assistant logic (no LLM, §67).

Geometry, lexical matching against the price catalog, and estimate building — pure code.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from examples.textutil import stem_score

from .models import Estimate, EstimateLine, PlanStep, ProjectInfo

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

# --------------------------------------------------------------------------- #
# Fast-reply: answer short phrases without the LLM (as in REPAIR_AI_CHAT)
# --------------------------------------------------------------------------- #

_FAST_ABILITIES = (
    "что ты умеешь",
    "что умеешь",
    "что ты можешь",
    "что можешь",
    "чем можешь помочь",
    "чем можешь",
    "с чем можешь помочь",
    "какие возможности",
    "твои возможности",
    "как ты работаешь",
    "как работаешь",
    "расскажи о себе",
    "кто ты",
)
_FAST_THANKS = ("спасибо", "спасибки", "благодарю", "благодарен", "благодарна")
_FAST_FAREWELL = (
    "до свидания",
    "до встречи",
    "всего доброго",
    "всего хорошего",
    "пока",
    "прощай",
    "bye",
    "goodbye",
)
_FAST_GREETING = (
    "здравствуйте",
    "здравствуй",
    "добрый день",
    "добрый вечер",
    "доброе утро",
    "привет",
    "hello",
    "hi",
    "ку",
)
_FAST_SMALLTALK = (
    "как дела",
    "как у тебя дела",
    "как жизнь",
    "как настроение",
    "как сам",
    "как ты",
    "что нового",
    "как поживаешь",
)
#: Phrases stripped from the message to reveal the remainder (e.g.
#: «привет, сколько стоит плитка?» still reaches the pipeline).
_FAST_STRIP = (
    _FAST_ABILITIES
    + _FAST_THANKS
    + _FAST_FAREWELL
    + _FAST_GREETING
    + (
        "большое",
        "огромное",
        "очень",
    )
)

FAST_ABILITIES_TEXT = (
    "Что я умею:\n"
    "- спланировать ремонт комнаты по этапам;\n"
    "- подобрать материалы из каталога и цены;\n"
    "- рассчитать смету и уложиться в бюджет;\n"
    "- спросить у вас решения по дизайну.\n\n"
    "Например: «Спланируй ремонт ванной 5 м² бюджет 50 000»."
)
FAST_GREETING_TEXT = (
    "Здравствуйте! Я помогу спланировать ремонт, подобрать материалы "
    "и посчитать смету. Опишите комнату: тип, площадь и бюджет."
)
FAST_THANKS_TEXT = "Пожалуйста! Обращайтесь, если понадобится что-то ещё по ремонту."
FAST_FAREWELL_TEXT = "До свидания! Хорошего ремонта."


def fast_reply(text: str) -> str | None:
    """A canned reply for a routine message, or None — let the pipeline run.

    Abilities win immediately; thanks/farewell/greeting — only when no
    content remains after stripping the routine phrases («привет, сколько стоит
    плитка?» → None, it will reach the LLM).
    """
    norm = (" " + text.strip().lower() + " ").replace(",", " ").replace("?", "")
    if any(phrase in norm for phrase in _FAST_ABILITIES):
        return FAST_ABILITIES_TEXT

    rest = norm
    for phrase in _FAST_STRIP:
        rest = rest.replace(phrase, " ")
    rest = " ".join(rest.split())
    if rest and rest not in _FAST_SMALLTALK:
        return None

    if any(phrase in norm for phrase in _FAST_THANKS):
        return FAST_THANKS_TEXT
    if any(phrase in norm for phrase in _FAST_FAREWELL):
        return FAST_FAREWELL_TEXT
    if any(phrase in norm for phrase in _FAST_GREETING):
        return FAST_GREETING_TEXT
    return None


#: Pipeline stages in order.
STAGES: tuple[str, ...] = (
    "collect",
    "design_choice",
    "plan",
    "estimate",
    "final_approval",
    "assistant",
)

# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #


class Geometry:
    def wall_area(self, length: float, width: float, height: float) -> float:
        return round(2 * (length + width) * height, 2)

    def floor_area(self, length: float, width: float) -> float:
        return round(length * width, 2)

    def perimeter(self, length: float, width: float) -> float:
        return round(2 * (length + width), 2)


def ensure_geometry(info: ProjectInfo) -> ProjectInfo:
    """Fills in geometry from area/length/width/ceiling_height (square of the area)."""
    g = Geometry()
    data = info.model_dump(exclude_none=True)
    if data.get("area") is None:
        if data.get("length") is not None and data.get("width") is not None:
            data["area"] = round(data["length"] * data["width"], 2)
    else:
        length = data.get("length")
        width = data.get("width")
        if length is None and width is None:
            side = math.sqrt(data["area"])
            data["length"] = round(side, 2)
            data["width"] = round(side, 2)
    data.setdefault("ceiling_height", 2.7)
    length = float(data.get("length") or 0.0)
    width = float(data.get("width") or 0.0)
    height = float(data.get("ceiling_height") or 2.7)
    data["floor_area"] = g.floor_area(length, width) if length and width else None
    data["walls_area"] = (
        g.wall_area(length, width, height) if length and width else None
    )
    data["ceiling_area"] = data["floor_area"]
    data["perimeter"] = g.perimeter(length, width) if length and width else None
    return ProjectInfo.model_validate(data)


def geometry_text(info: ProjectInfo) -> str:
    length = (info.length or 1.0) if (info.length or 0) else 1.0
    width = (info.width or 1.0) if (info.width or 0) else 1.0
    height = info.ceiling_height or 2.7
    g = Geometry()
    return (
        f"Комната: {info.room_type}, площадь пола {info.floor_area or g.floor_area(length, width)} м², "
        f"периметр {info.perimeter or g.perimeter(length, width)} м, "
        f"площадь стен {info.walls_area or g.wall_area(length, width, height)} м², "
        f"высота потолков {height} м"
    )


# --------------------------------------------------------------------------- #
# Price catalog (price.csv) — lexical search without embedders
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CatalogItem:
    name: str
    price: float
    unit: str


class Catalog:
    def __init__(self, path: str | Path):
        self._items: list[CatalogItem] = []
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                name = row[0].strip()
                try:
                    price = float(row[1].replace(",", "."))
                except ValueError:
                    continue
                unit = row[2].strip() if len(row) > 2 else ""
                self._items.append(CatalogItem(name=name, price=price, unit=unit))

    def search(self, query: str, top_k: int = 5) -> list[CatalogItem]:
        scored = sorted(
            ((stem_score(item.name, query), item) for item in self._items),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [item for score, item in scored if score > 0][:top_k]

    def find(self, query: str) -> CatalogItem | None:
        best, best_score = None, 0.3
        for item in self._items:
            score = stem_score(item.name, query)
            if score > best_score:
                best, best_score = item, score
        return best


# --------------------------------------------------------------------------- #
# Estimate: quantity parsing, unit conversion, totals (deterministically)
# --------------------------------------------------------------------------- #

_QUANTITY = re.compile(
    r"[~≈]\s*(\d+(?:[.,]?\d+)?)\s*(м²|м2|[а-яё]{1,8})?", re.UNICODE | re.IGNORECASE
)
_KG_IN_NAME = re.compile(r"(\d+(?:[.,]?\d+)?)\s*кг", re.UNICODE | re.IGNORECASE)
_LITERS_IN_NAME = re.compile(
    r"(\d+(?:[.,]?\d+)?)\s*л(?:\.|\s|$)", re.UNICODE | re.IGNORECASE
)
_RUNNING_M_IN_NAME = re.compile(
    r"(\d+(?:[.,]?\d+)?)\s*м\.?\s*п", re.UNICODE | re.IGNORECASE
)
_SHEET_DIMS_IN_NAME = re.compile(
    r"(\d{3,4})\s*[×xх*]\s*(\d{3,4})", re.UNICODE | re.IGNORECASE
)
_M2_IN_NAME = re.compile(r"(\d+(?:[.,]?\d+)?)\s*м²", re.UNICODE | re.IGNORECASE)


def _parse_quantity(material: str) -> tuple[float | None, str, str]:
    """Returns (number, plan_unit, catalog_query) from a material string."""
    match = _QUANTITY.search(material)
    query = _QUANTITY.sub("", material).strip(" .,-")
    if not match:
        return None, "", query
    qty = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "").lower()
    return qty, unit, query


def _conversion_factor(item: CatalogItem, plan_unit: str) -> float:
    """How many catalog units the plan quantity expands to."""
    name = item.name.lower()
    if item.unit in ("₽/мешок", "₽/меш", "₽/упаковка"):
        if plan_unit in ("кг", "кг.", "килограмм"):
            kg = _KG_IN_NAME.search(name)
            if kg:
                return 1.0 / float(kg.group(1).replace(",", "."))
            return 1.0
        if plan_unit in ("м²", "м2"):
            liters = _LITERS_IN_NAME.search(name)
            if liters:
                return 1.0 / float(liters.group(1).replace(",", "."))
            return 1.0
        return 1.0
    if "лист" in item.unit:
        dims = _SHEET_DIMS_IN_NAME.search(name)
        if dims and plan_unit in ("м²", "м2"):
            sheet_m2 = (int(dims.group(1)) / 1000) * (int(dims.group(2)) / 1000)
            return 1.0 / sheet_m2 if sheet_m2 else 1.0
        return 1.0
    if item.unit in ("₽/пог.м", "₽/м"):
        if plan_unit in ("м²", "м2"):
            m2 = _M2_IN_NAME.search(name)
            if m2:
                return 1.0 / float(m2.group(1).replace(",", "."))
            return 0.5  # rough norm
        return 1.0
    return 1.0


def build_estimate(plan: list[PlanStep], catalog: Catalog) -> Estimate:
    """Prices only from the catalog: unknown material — skipped (§68: honesty)."""
    lines: list[EstimateLine] = []
    total = 0.0
    unpriced: list[str] = []
    for step in plan:
        for material in step.materials:
            qty, plan_unit, query = _parse_quantity(material)
            item = catalog.find(query)
            if item is None:
                unpriced.append(material)
                continue
            factor = 1.0 if qty is None else _conversion_factor(item, plan_unit)
            quantity = qty * factor if qty is not None else None
            line_total = (
                round(quantity * item.price, 2) if quantity is not None else None
            )
            lines.append(
                EstimateLine(
                    name=item.name,
                    quantity=quantity,
                    unit=item.unit,
                    unit_price=item.price,
                    total=line_total,
                )
            )
            if line_total is not None:
                total += line_total
    warnings: list[str] = []
    if unpriced:
        warnings.append(f"Не найдено в каталоге: {', '.join(unpriced[:3])}")
    if not lines:
        warnings.append("Не удалось оценить ни одной позиции")
    estimate = Estimate(lines=lines, subtotal=round(total, 2), total=round(total, 2))
    estimate.warnings = warnings
    return estimate


def qa_budget_warning(estimate: Estimate, budget: float | None) -> list[str]:
    if budget is None or estimate.total is None:
        return []
    if estimate.total > budget * 1.1:
        return [f"Смета ({estimate.total} ₽) превышает бюджет ({budget} ₽)"]
    return []


# --------------------------------------------------------------------------- #
# Change model / rollback (rollback table)
# --------------------------------------------------------------------------- #

_ROOM_FIELDS = {"room_type"}
_PALETTE_FIELDS = {"style", "wall_color", "ceiling_color", "floor_material"}
_GEOMETRY_FIELDS = {"area", "length", "width", "ceiling_height"}
_BUDGET_FIELDS = {"budget"}


def changed_fields(old: ProjectInfo, new: ProjectInfo) -> set[str]:
    old_dump = old.model_dump()
    new_dump = new.model_dump()
    return {
        key
        for key in old_dump
        if new_dump.get(key) is not None and new_dump.get(key) != old_dump.get(key)
    }


def rollback_target(changed: set[str]) -> str:
    """The strongest change determines the stage from which to rebuild."""
    if changed & _ROOM_FIELDS:
        return "collect"
    if changed & _PALETTE_FIELDS:
        return "design_choice"
    if changed & _GEOMETRY_FIELDS:
        return "plan"
    if changed & _BUDGET_FIELDS:
        return "estimate"
    return "estimate"  # no changes — stay at the final approval
