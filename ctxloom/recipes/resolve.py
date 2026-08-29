"""recipes — lazy reference materialization (§6, §34)."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from ..artifacts import Artifact
from ..context import Context
from ..patches import Patch
from ..sources import SourceRef


async def materialize_doc(
    context: Context,
    ref_artifact: Artifact[SourceRef],
    doc_factory: Callable[[Context, Artifact[SourceRef], str], BaseModel],
    *,
    relation: str = "materialized_from",
) -> Patch | None:
    """Resolves a ref into a document (lazily, §6) with provenance (§34).

    `doc_factory(context, ref_artifact, content)` builds the domain document;
    the produced artifact is linked `relation → SourceRef` (default
    `materialized_from`, pass `resolved_from` to match the demos). Returns None
    on a missing source / resolve failure — the failure is a None, not a crash.
    """
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
    return Patch().create(doc, id=doc_id).link(doc_id, relation, ref_artifact.id)
