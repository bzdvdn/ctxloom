"""repair services — the price catalog (`price.csv`), lexical search (§67)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ctxloom.recipes import keyword_score


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
        candidate = []
        for item in self._items:
            score = keyword_score(item.name, query, use_stems=True)
            if score > 0:
                candidate.append((score, item))
        # ties (equal lexical score) prefer the cheaper item — the catalog names
        # often collide (many "Розетка …"), and the expensive industrial variant
        # must not win over a household socket on the same stem (§67)
        candidate.sort(key=lambda pair: (-pair[0], pair[1].price))
        return [item for _, item in candidate[:top_k]]

    def find(self, query: str, *, min_score: float = 0.3) -> CatalogItem | None:
        best: CatalogItem | None = None
        best_score = min_score
        for item in self._items:
            score = keyword_score(item.name, query, use_stems=True)
            if score < best_score - 1e-9:
                continue
            if (
                best is None
                or score > best_score
                or (abs(score - best_score) <= 1e-9 and item.price < best.price)
            ):
                best, best_score = item, score
        return best


__all__ = ["Catalog", "CatalogItem"]
