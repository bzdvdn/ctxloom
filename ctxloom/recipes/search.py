"""recipes — ready-made search fan-out (§8, §24, §42)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..context import Context
from ..patches import Patch
from ..sources import SourceRef


async def fan_out_sources(
    context: Context,
    query: str,
    owner_id: str,
    *,
    limit: int = 5,
    query_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
    on_start: Callable[[str], None] | None = None,
    on_count: Callable[[str, int], None] | None = None,
) -> tuple[Patch, list[SourceRef]]:
    """Fans out over every configured source and builds idempotent refs.

    Returns a patch with stable-id `SourceRef`s (scoped to `owner_id`, §42) and
    the ranked refs, so the caller can also add its own "search done" marker.
    A repeated fan-out for the same owner re-creates the same ids (create-or-
    refresh), which the caller guards with an idempotency marker. `on_start` /
    `on_count` receive each source's id and hit count for progress announces.
    """
    refs: list[SourceRef] = []
    for source in context.resources.sources.values():
        if on_start is not None:
            on_start(source.source_id)
        found = await source.asearch(query, limit=limit)
        if on_count is not None:
            on_count(source.source_id, len(found))
        refs.extend(found)
    refs.sort(key=lambda r: r.score or 0.0, reverse=True)

    patch = Patch()
    scoped_refs: list[SourceRef] = []
    for ref in refs[:limit]:
        scoped = ref.model_copy(
            update={
                "metadata": {
                    **ref.metadata,
                    "owner_id": owner_id,
                    **(extra_metadata or {}),
                },
                "query_id": query_id if query_id is not None else owner_id,
            }
        )
        scoped_refs.append(scoped)
        patch.create(scoped, id=f"ref:{ref.stable_id()}:{owner_id}")
    return patch, scoped_refs
