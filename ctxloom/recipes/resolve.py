"""recipes — lazy reference materialization (§6, §34).

Effects-based: resolves a ref into a document and writes the create + the
provenance link into the current produce's `effects` slot. Returns the produced
document (or None on a failure), so the caller can react to the outcome.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from ..artifacts import Artifact
from ..context import Context
from ..sources import SourceRef
from .search import _active_effects


async def materialize_doc(
    context: Context,
    ref_artifact: Artifact[SourceRef],
    doc_factory: Callable[[Context, Artifact[SourceRef], str], BaseModel],
    *,
    relation: str = "materialized_from",
) -> BaseModel | None:
    """Resolves a ref into a document (lazily, §6) with provenance (§34).

    `doc_factory(context, ref_artifact, content)` builds the domain document;
    the produced document is created with a stable id and linked
    `relation → SourceRef` (default `materialized_from`, pass `resolved_from`
    to match the demos) in the current effect slot. Returns None on a missing
    source / resolve failure — the failure is a None, not a crash.
    """
    effects = _active_effects(context)
    ref = ref_artifact.data
    source = context.resources.get_source(ref.source_id)
    if source is None:
        return None
    try:
        content = await source.resolve(ref)
    except Exception:
        return None
    doc = doc_factory(context, ref_artifact, content)
    doc_id = f"resolved:{ref_artifact.id}"
    handle = effects.create(doc, id=doc_id)
    handle.link(relation, ref_artifact)
    return doc


__all__ = ["materialize_doc"]
