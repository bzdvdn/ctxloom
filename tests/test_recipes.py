"""The recipes (reactive patterns) behave as documented when used directly."""

import asyncio
from pathlib import Path

from ctxloom import Agent, Consume, Context, Produce, Runtime, RuntimeResources
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
    """fan_out_sources writes idempotent refs into the produce's effects slot."""

    class Scout(Produce[SourceRef]):
        artifact_type = SourceRef

        async def produce(self, context, inputs, event=None):
            await fan_out_sources(
                context,
                "vitamin D nutritional supplementation",
                owner_id="job1",
                limit=2,
            )
            self.effects.create(Job(query_id="job1", text="scouted"), id="marker:job1")
            return None

    class Engine(Agent):
        consumes = [Consume(Job)]
        produces = [Scout(), Produce(Job)]

    ctx = Context(resources=RuntimeResources(sources={"papers": build_pages(tmp_path)}))
    runtime = Runtime(ctx, agents=[Engine()])
    ctx.create(Job(query_id="job1", status="pending"))
    asyncio.run(runtime.arun())

    refs = ctx.list_artifacts(SourceRef)
    assert refs
    assert all(r.data.metadata.get("owner_id") == "job1" for r in refs)
    assert all(r.data.query_id == "job1" for r in refs)
    assert all(r.id.startswith("ref:") for r in refs)
    # the effects slot compiled and committed both the refs and the marker
    assert ctx.get("marker:job1") is not None


def test_materialize_doc_builds_doc_with_provenance(tmp_path):
    """materialize_doc creates the doc + link in effects (resolved_from, §34)."""

    class Scout(Produce[SourceRef]):
        artifact_type = SourceRef

        async def produce(self, context, inputs, event=None):
            await fan_out_sources(context, "prevents colds", owner_id="q1", limit=1)
            return None

    class Resolver(Produce[Doc]):
        artifact_type = Doc

        async def produce(self, context, inputs, event=None):
            ref_art = context.get(event.artifact_id) if event is not None else None
            if ref_art is None or not isinstance(ref_art.data, SourceRef):
                return None

            def factory(_ctx: Context, _ref: Artifact[SourceRef], content: str) -> Doc:
                return Doc(
                    query_id=_ref.data.query_id,
                    path=_ref.data.locator,
                    content=content,
                )

            await materialize_doc(context, ref_art, factory, relation="resolved_from")
            return None

    class Engine(Agent):
        consumes = [Consume(Job), Consume(SourceRef)]
        produces = [Scout(), Resolver()]

    ctx = Context(resources=RuntimeResources(sources={"papers": build_pages(tmp_path)}))
    runtime = Runtime(ctx, agents=[Engine()])
    ctx.create(Job(query_id="q1", status="pending"))
    asyncio.run(runtime.arun())

    docs = ctx.list_artifacts(Doc)
    assert docs
    doc = docs[0]
    assert doc.data.query_id == "q1"
    assert len(ctx.related(doc.id, relation="resolved_from")) == 1


class Fill(Produce[Job]):
    artifact_type = Job

    async def produce(self, context, inputs, event=None):
        target = context.get(event.artifact_id)
        if target is None:
            return None
        self.effects.update(target, text="filled")
        return None


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
