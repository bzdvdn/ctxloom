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
