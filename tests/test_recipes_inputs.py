"""find/find_all: locate typed artifacts inside a produce's `inputs` list."""

from ctxloom import Context, RuntimeResources
from ctxloom.recipes import find, find_all
from pydantic import BaseModel


class Question(BaseModel):
    text: str


class Evidence(BaseModel):
    text: str


def build_inputs():
    ctx = Context(resources=RuntimeResources())
    q = ctx.create(Question(text="why?"))
    e1 = ctx.create(Evidence(text="first"))
    e2 = ctx.create(Evidence(text="second"))
    return [q, e1, e2]


def test_find_returns_first_match_of_type():
    inputs = build_inputs()
    hit = find(inputs, Question)
    assert hit is not None
    assert hit.data.text == "why?"


def test_find_returns_none_when_absent():
    inputs = build_inputs()

    class Answer(BaseModel):
        text: str

    assert find(inputs, Answer) is None


def test_find_all_returns_every_match():
    inputs = build_inputs()
    hits = find_all(inputs, Evidence)
    assert [h.data.text for h in hits] == ["first", "second"]


def test_find_all_returns_empty_list_when_absent():
    inputs = build_inputs()

    class Answer(BaseModel):
        text: str

    assert find_all(inputs, Answer) == []
