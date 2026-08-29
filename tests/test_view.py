from ctxloom import Context
from pydantic import BaseModel


class Question(BaseModel):
    text: str


class Evidence(BaseModel):
    text: str
    score: float


class Claim(BaseModel):
    text: str


def build():
    ctx = Context()
    q = ctx.create(Question(text="почему выросли затраты?"))
    e1 = ctx.create(Evidence(text="gpu вырос на 43%", score=0.9))
    e2 = ctx.create(Evidence(text="деплой в мае", score=0.6))
    c = ctx.create(Claim(text="вырос gpu-инференс"))
    return ctx, {"q": q, "e1": e1, "e2": e2, "c": c}


def test_view_filters_by_type():
    ctx, arts = build()
    view = ctx.view(Evidence)
    assert [a.id for a in view.artifacts] == [arts["e1"].id, arts["e2"].id]


def test_view_filters_by_condition_and_limit():
    ctx, arts = build()
    view = ctx.view(Evidence, condition=lambda a: a.data.score > 0.7)
    assert [a.id for a in view.artifacts] == [arts["e1"].id]

    view2 = ctx.view(Evidence, condition=lambda a: a.data.score > 0.5, limit=1)
    assert [a.id for a in view2.artifacts] == [arts["e1"].id]


def test_view_tuple_of_types():
    ctx, arts = build()
    view = ctx.view((Evidence, Claim))
    assert len(view.artifacts) == 3


def test_view_all_when_no_type():
    ctx, _ = build()
    assert len(ctx.view().artifacts) == 4


def test_view_does_not_mutate_context():
    ctx, _ = build()
    ctx.view(Evidence)
    assert len(ctx.list_artifacts()) == 4


def test_view_render_and_tokens_estimate():
    ctx, _ = build()
    view = ctx.view((Question, Claim))
    text = view.render()
    assert "[Question]" in text
    assert "[Claim]" in text
    assert view.tokens_estimate >= 1
    # max_chars truncates
    short = view.render(max_chars=20)
    assert len(short) == 20
    assert view.tokens_estimate >= len(short) // 4
