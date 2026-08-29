"""knowledge search — fan-out, text and spreadsheet materialization."""

from __future__ import annotations

from ctxloom import Artifact, Context, Event, Patch, Produce
from ctxloom.recipes import fan_out_sources, materialize_doc
from ctxloom.sources import SourceRef

from ..models import ResearchTurn, SearchDone, Spreadsheet, TypedDoc
from .common import SCOUT_LIMIT


class ScoutSources(Produce[SourceRef]):
    """Fan-out over all configured sources, with idempotency (§24, §42)."""

    artifact_type = SourceRef

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[ResearchTurn]],
        event: Event | None = None,
    ) -> Patch | None:
        turn_artifact = context.get(event.artifact_id) if event is not None else None
        if turn_artifact is None or not isinstance(turn_artifact.data, ResearchTurn):
            return None
        turn = turn_artifact.data
        # Idempotency (§42): once searched, don't restart the cascade.
        if any(
            s.data.query_id == turn.query_id for s in context.list_artifacts(SearchDone)
        ):
            return None
        patch = Patch()
        fan_patch, _ = await fan_out_sources(
            context,
            turn.text,
            owner_id=turn.query_id,
            limit=SCOUT_LIMIT,
            on_start=lambda sid: context.announce(
                f"Searching for information in source «{sid}»...",
                kind="status",
                source=sid,
            ),
            on_count=lambda sid, n: context.announce(
                f"Found {n} matches in «{sid}»",
                kind="status",
                count=n,
                source=sid,
            ),
        )
        patch.merge(fan_patch)
        patch.create(SearchDone(query_id=turn.query_id), id=f"scouted:{turn.query_id}")
        return patch


class ResolveRef(Produce[TypedDoc]):
    """Lazy materialization of a text ref (§6); text documents only."""

    artifact_type = TypedDoc

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[SourceRef]],
        event: Event | None = None,
    ) -> Patch | None:
        ref_artifact = context.get(event.artifact_id) if event is not None else None
        if ref_artifact is None or not isinstance(ref_artifact.data, SourceRef):
            return None
        ref = ref_artifact.data
        if ref.metadata.get("structured"):
            return None  # not our branch: spreadsheets go to ResolveTable
        context.announce(
            f"Reading document «{ref.locator}» from {ref.source_id}...",
            kind="status",
            source=ref.source_id,
            path=ref.locator,
        )

        def doc_factory(
            _context: Context, _ref_art: Artifact[SourceRef], content: str
        ) -> TypedDoc:
            data = _ref_art.data
            return TypedDoc(
                source_id=data.source_id,
                path=data.locator,
                content=content,
                query_id=data.query_id,
                score=data.score or 0.0,
            )

        # provenance (§34): TypedDoc —resolved_from→ SourceRef
        return await materialize_doc(
            context, ref_artifact, doc_factory, relation="resolved_from"
        )


class ResolveTable(Produce[Spreadsheet]):
    """Spreadsheet: structured data stays structured, not text (§29)."""

    artifact_type = Spreadsheet

    async def produce(
        self,
        context: Context,
        inputs: list[Artifact[SourceRef]],
        event: Event | None = None,
    ) -> Patch | None:
        ref_artifact = context.get(event.artifact_id) if event is not None else None
        if ref_artifact is None or not isinstance(ref_artifact.data, SourceRef):
            return None
        ref = ref_artifact.data
        if not ref.metadata.get("structured"):
            return None  # not our branch: text documents go to ResolveRef
        source = context.resources.get_source(ref.source_id)
        if source is None:
            return None
        context.announce(
            f"Reading spreadsheet «{ref.locator}» from {ref.source_id}...",
            kind="status",
            source=ref.source_id,
            path=ref.locator,
        )
        try:
            payload = await source.resolve(ref)
        except Exception:
            return None
        columns = list(payload.get("columns", []))
        rows = [list(r) for r in payload.get("rows", [])]
        sheet_id = f"sheet:{ref.stable_id()}"
        return (
            Patch()
            .create(
                Spreadsheet(
                    source_id=ref.source_id,
                    path=ref.locator,
                    columns=columns,
                    rows=rows,
                    query_id=ref.query_id,
                ),
                id=sheet_id,
            )
            .link(sheet_id, "materialized_from", ref_artifact.id)
        )
