"""The recipes (reactive patterns) behave as documented when used directly."""

import asyncio
from pathlib import Path

from ctxloom import Agent, Consume, Context, Patch, Produce, Runtime, RuntimeResources
from ctxloom.artifacts import Artifact
from ctxloom.recipes import StatusMachine, fan_out_sources, materialize_doc
from ctxloom.sources import FileSystemSource, SourceRef
from pydantic import BaseModel


class Job(BaseModel):
    query_id: str
    status: str = "pending"
    text: str = ""


class Doc(BaseModel):
    query_id: str
    path: str
    content: str


def build_pages(tmp_path) -> FileSystemSource:
    pages = Path(tmp_path) / "pages"
    pages.mkdir()
    (pages / "a.md").write_text(
        "vitamin D supplementation prevents colds.", encoding="utf-8"
    )
    (pages / "b.md").write_text("unrelated content about cars.", encoding="utf-8")
    return FileSystemSource(str(pages), source_id="papers")


def test_fan_out_sources_builds_owner_tagged_refs(tmp_path):
    ctx = Context(resources=RuntimeResources(sources={"papers": build_pages(tmp_path)}))
    patch, refs = asyncio.run(
        fan_out_sources(
            ctx, "vitamin D nutritional supplementation", owner_id="job1", limit=2
        )
    )
    assert refs
    assert all(r.metadata.get("owner_id") == "job1" for r in refs)
    assert all(r.query_id == "job1" for r in refs)
    # stable ids scoped to the owner (Create.id, not artifact_id — set on apply)
    ids = {op.id for op in patch.operations if op.id}
    assert ids and all(i.startswith("ref:") for i in ids)


def test_materialize_doc_builds_doc_with_provenance(tmp_path):
    ctx = Context(resources=RuntimeResources(sources={"papers": build_pages(tmp_path)}))
    refs = asyncio.run(fan_out_sources(ctx, "prevents colds", owner_id="q1", limit=1))[
        1
    ]
    assert refs

    def factory(_ctx: Context, _ref: Artifact[SourceRef], content: str) -> Doc:
        return Doc(query_id=_ref.data.query_id, path=_ref.data.locator, content=content)

    patch = asyncio.run(
        materialize_doc(ctx, Artifact(data=refs[0]), factory, relation="resolved_from")
    )
    assert patch is not None
    creates = [op for op in patch.operations if op.__class__.__name__ == "Create"]
    assert creates and creates[0].data.query_id == "q1"
    assert any(
        op.relation == "resolved_from"
        for op in patch.operations
        if hasattr(op, "relation")
    )


class Fill(Produce[Job]):
    artifact_type = Job

    async def produce(self, context, inputs, event=None):
        target = context.get(event.artifact_id)
        if target is None:
            return None
        return Patch().update_fields(target, text="filled")


class Survey(StatusMachine[Job]):
    artifact_type = Job
    terminal = frozenset({"done"})

    def next_status(self, context, key):
        jobs = [j for j in context.list_artifacts(Job) if j.data.query_id == key]
        return "done" if jobs and any(j.data.text for j in jobs) else None


class Engine(Agent):
    consumes = [Consume(Job)]
    produces = [Fill(), Survey()]


def test_status_machine_advances_lifecycle():
    ctx = Context()
    runtime = Runtime(ctx, agents=[Engine()])
    ctx.create(Job(query_id="q1", status="pending"))
    asyncio.run(runtime.arun())
    job = ctx.list_artifacts(Job)[0]
    assert job.data.status == "done"


# --------------------------------------------------------------------------- #
# recipes.text — deterministic keyword scoring (§67)
# --------------------------------------------------------------------------- #


def test_keyword_score_english_ignores_stopwords():
    from ctxloom.recipes import EN_STOPWORDS, keyword_score

    text = "How to set up authentication and handle sessions securely"
    assert keyword_score(text, "set up authentication") == 1.0
    assert keyword_score(text, "authentication sessions", stopwords=EN_STOPWORDS) >= 0.5
    assert keyword_score("unrelated page", "authentication") == 0.0
    assert keyword_score(text, "") == 0.0  # empty query → no score


def test_keyword_score_russian_stems_match_inflections():
    from ctxloom.recipes import keyword_score

    # «аутентификацию» and «аутентификация» share the stem «аутентификац»
    score = keyword_score("Установка аутентификации", "аутентификацию", use_stems=True)
    assert score == 1.0
    plain = keyword_score("Установка аутентификации", "аутентификацию", use_stems=False)
    assert plain == 0.0  # without stems the inflections do not match


def test_stem_words_splits_cyrillic_and_latin():
    from ctxloom.recipes import stem_words

    stems = stem_words("Ремонт комнаты и kitchen")
    assert "ремонт" in stems
    assert "комнат" in stems
    assert "kitchen" in stems


# --------------------------------------------------------------------------- #
# recipes.rollback — change → rebuild (§22/§24)
# --------------------------------------------------------------------------- #

_FIELD_STAGES = {
    "room": "collect",
    "style": "design_choice",
    "area": "plan",
    "budget": "estimate",
}
_STAGE_ORDER = ("collect", "design_choice", "plan", "estimate")


class _Proj(BaseModel):
    room: str | None = None
    style: str | None = None
    area: float | None = None
    budget: float | None = None


def test_changed_fields_ignores_unknown_none():
    from ctxloom.recipes import changed_fields

    old = _Proj(room="kitchen", budget=100)
    new = _Proj(room="bathroom", budget=None)  # budget unknown → not a change
    assert changed_fields(old, new) == {"room"}


def test_earliest_stage_routes_to_the_first_affected():
    from ctxloom.recipes import earliest_stage

    assert (
        earliest_stage({"style"}, field_stages=_FIELD_STAGES, order=_STAGE_ORDER)
        == "design_choice"
    )
    assert (
        earliest_stage(
            {"area", "budget"}, field_stages=_FIELD_STAGES, order=_STAGE_ORDER
        )
        == "plan"
    )
    assert earliest_stage(set(), field_stages=_FIELD_STAGES, order=_STAGE_ORDER) is None


def test_downstream_fields_reset_inclusive_suffix():
    from ctxloom.recipes import downstream_fields

    resets = downstream_fields("plan", field_stages=_FIELD_STAGES, order=_STAGE_ORDER)
    assert resets == frozenset(
        {"area", "budget"}
    )  # plan + estimate stay, upstream is kept
