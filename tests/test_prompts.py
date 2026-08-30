"""Prompt templating (§68): strict variables, defaults, model attributes, chat rows."""

from ctxloom import MessagesPrompt, PromptTemplate
from ctxloom.providers import Message
from pydantic import BaseModel


class Doc(BaseModel):
    text: str


def test_render_fills_plain_variables():
    tpl = PromptTemplate("Answer {question} in {topic}.")
    assert tpl.render(question="why", topic="hvac") == "Answer why in hvac."
    assert tpl.variables == frozenset({"question", "topic"})


def test_missing_variable_raises_named_error():
    tpl = PromptTemplate("Use {topic} and {question}.")
    try:
        tpl.render(topic="x")
    except KeyError as exc:
        assert "question" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError for a missing variable")


def test_model_attribute_fields():
    doc = Doc(text="snippet")
    tpl = PromptTemplate("Research {doc.text} (topic: {topic})")
    assert tpl.render(doc=doc, topic="t") == "Research snippet (topic: t)"
    assert tpl.variables == frozenset({"doc", "topic"})  # top-level roots


def test_literal_braces_and_defaults():
    tpl = PromptTemplate("Literal {{brace}} and {topic}", defaults={"topic": "t"})
    assert tpl.render() == "Literal {brace} and t"
    assert tpl.render(topic="u") == "Literal {brace} and u"


def test_nonempty_requirement():
    try:
        PromptTemplate("   ")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for an empty template")


def test_messages_prompt_renders_role_row():
    tpl = MessagesPrompt(
        [
            ("system", "You analyze {topic}."),
            ("user", "Question: {question}"),
        ]
    )
    messages = tpl.render(topic="hvac", question="why")
    assert messages == [
        Message.system("You analyze hvac."),
        Message.user("Question: why"),
    ]
    assert tpl.variables == frozenset({"topic", "question"})


def test_messages_prompt_missing_anywhere_raises():
    tpl = MessagesPrompt([("system", "{topic}"), ("user", "{question}")])
    try:
        tpl.render(topic="t")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected KeyError when a row lacks a variable")


def test_message_factories_build_typed_roles():
    from ctxloom import Message

    assert Message.system("s") == Message(role="system", content="s")
    assert Message.user("u") == Message(role="user", content="u")
    assert Message.assistant("a") == Message(role="assistant", content="a")
    assert Message.tool("t") == Message(role="tool", content="t")


def test_message_rejects_unknown_role():
    from ctxloom import Message

    for bad in ("assistan", "human", ""):
        try:
            Message(role=bad, content="x")  # type: ignore[arg-type]
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"expected ValueError for role {bad!r}")


def test_messages_prompt_rejects_unknown_role_row():
    try:
        MessagesPrompt([("human", "hello")])
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for an unknown role row")
