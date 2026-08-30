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
        scored = sorted(
            (
                (keyword_score(item.name, query, use_stems=True), item)
                for item in self._items
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [item for score, item in scored if score > 0][:top_k]

    def find(self, query: str) -> CatalogItem | None:
        best, best_score = None, 0.3
        for item in self._items:
            score = keyword_score(item.name, query, use_stems=True)
            if score > best_score:
                best, best_score = item, score
        return best


__all__ = ["Catalog", "CatalogItem"]
