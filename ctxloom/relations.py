"""ctxloom.relations — the provenance/link graph (§15).

Extracted out of `Context`: `RelationGraph` owns only the
`(source, relation, target) → Relation` mapping and the query/mutation
operations over it. It has no knowledge of artifacts, commits, or merge —
`Context` still resolves "does this artifact exist" itself (`related()`
needs the artifact store, so that method stays on `Context`, as a thin
wrapper that filters `RelationGraph.relations()` against `self._artifacts`).
"""

from __future__ import annotations

from typing import Any

from .patches import Relation

RelationKey = tuple[str, str, str]


class RelationGraph:
    """The live link graph: create/remove/query edges (§15)."""

    __slots__ = ("_edges",)

    def __init__(self) -> None:
        self._edges: dict[RelationKey, Relation] = {}

    def link(self, source_id: str, relation: str, target_id: str) -> Relation:
        """Establishes a link `source_id —relation→ target_id` (idempotently, §42)."""
        rel = Relation(source_id=source_id, relation=relation, target_id=target_id)
        self._edges[(rel.source_id, rel.relation, rel.target_id)] = rel
        return rel

    def unlink(
        self,
        source_id: str,
        relation: str | None = None,
        target_id: str | None = None,
    ) -> int:
        """Removes edges; `relation`/`target_id` = None mean "any"."""
        removed = 0
        for key in [k for k in self._edges if k[0] == source_id]:
            if relation is not None and key[1] != relation:
                continue
            if target_id is not None and key[2] != target_id:
                continue
            del self._edges[key]
            removed += 1
        return removed

    def relations(
        self,
        source_id: str | None = None,
        relation: str | None = None,
        target_id: str | None = None,
    ) -> list[Relation]:
        """All edges, optionally filtered by any component."""
        result: list[Relation] = []
        for rel in self._edges.values():
            if source_id is not None and rel.source_id != source_id:
                continue
            if relation is not None and rel.relation != relation:
                continue
            if target_id is not None and rel.target_id != target_id:
                continue
            result.append(rel)
        return result

    def __contains__(self, key: RelationKey) -> bool:
        return key in self._edges

    def __len__(self) -> int:
        return len(self._edges)

    def values(self) -> list[Relation]:
        return list(self._edges.values())

    def items(self) -> list[tuple[RelationKey, Relation]]:
        return list(self._edges.items())

    def copy(self) -> RelationGraph:
        clone = RelationGraph()
        clone._edges = dict(self._edges)
        return clone

    def to_dict(self) -> list[dict[str, Any]]:
        return [rel.to_dict() for rel in self._edges.values()]

    @classmethod
    def from_dict(cls, items: list[dict[str, Any]]) -> RelationGraph:
        graph = cls()
        for d in items:
            rel = Relation.from_dict(d)
            graph._edges[(rel.source_id, rel.relation, rel.target_id)] = rel
        return graph

    @classmethod
    def from_mapping(cls, mapping: dict[RelationKey, Relation]) -> RelationGraph:
        graph = cls()
        graph._edges = dict(mapping)
        return graph


__all__ = ["RelationGraph", "RelationKey"]
