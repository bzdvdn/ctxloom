"""repair services — estimate building from the catalog (deterministic, §67)."""

from __future__ import annotations

import re

from ..models import Estimate, EstimateLine, PlanStep
from .catalog import Catalog, CatalogItem

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


__all__ = [
    "_conversion_factor",
    "_parse_quantity",
    "build_estimate",
    "qa_budget_warning",
]
