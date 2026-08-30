from ctxloom.artifacts import Artifact
from ctxloom.patches import Create, Patch, Update
from pydantic import BaseModel


class Item(BaseModel):
    name: str
    qty: int


def test_merge_instance_appends_operations():
    base = Patch().create(Item(name="a", qty=1), id="a")
    other = Patch().update("a", Item(name="a", qty=2))
    base.merge(other)
    assert [type(op) for op in base.operations] == [Create, Update]
    assert base.operations[1].artifact_id == "a"


def test_merge_returns_self_for_chaining():
    patch = Patch()
    result = patch.merge(Patch().create(Item(name="b", qty=2)))
    assert result is patch
    assert len(patch.operations) == 1


def test_merge_skips_none():
    patch = Patch().delete("x")
    patch.merge(None)
    assert len(patch.operations) == 1


def test_update_fields_builds_full_update():
    item = Artifact(data=Item(name="a", qty=1))
    patch = Patch().update_fields(item, qty=2)
    op = patch.operations[0]
    assert isinstance(op, Update)
    assert op.artifact_id == item.id
    assert op.new_data.qty == 2
    assert op.new_data.name == "a"  # other fields preserved


def test_update_fields_returns_self_for_chaining():
    item = Artifact(data=Item(name="a", qty=1))
    patch = Patch()
    assert patch.update_fields(item, qty=2) is patch
