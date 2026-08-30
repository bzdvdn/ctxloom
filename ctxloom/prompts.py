"""ctxloom.prompts — minimal, strict prompt templating (§68).

`PromptTemplate` renders a `{var}`-style template with *declared* variables:
at construction time the placeholders are parsed, at render time a missing
variable is a `KeyError` (never a silent `format` leak), and `{{`/`}}` stay
literal braces. Domain model attributes are supported, so a template can take
a whole artifact: `"Research {question.text} in {topic}"` and be rendered with
`template.render(question=…, topic=…)`.

`MessagesPrompt` is the same idea for a chat sequence of `(role, template)`
rows — it renders to `list[Message]` ready for an LLM request.

This is deliberately small and dependency-free: it sits between the app's
"domain strings" and `structured_llm`/`LLMAgent.system`, without claiming to be
a general prompting framework.
"""

from __future__ import annotations

import re
import string
from collections.abc import Mapping, Sequence
from typing import Any, cast

from .providers import Message, Role

_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*\Z")

_formatter = string.Formatter()


def _root_fields(template: str) -> frozenset[str]:
    """The top-level variable names referenced by the template."""
    roots: set[str] = set()
    for _, field_name, _, _ in _formatter.parse(template):
        if field_name is None or field_name == "":
            continue
        if _FIELD.match(field_name):
            roots.add(field_name.split(".")[0])
    return frozenset(roots)


class PromptTemplate:
    """A strict `{var}` template over the values passed to `render`."""

    def __init__(
        self,
        template: str,
        *,
        defaults: Mapping[str, Any] | None = None,
    ):
        if not isinstance(template, str) or not template.strip():
            raise ValueError("prompt template must be a non-empty string")
        self._template = template
        self._defaults = dict(defaults or {})
        self.variables = _root_fields(template)

    @property
    def template(self) -> str:
        return self._template

    def render(self, **values: Any) -> str:
        """Fills the placeholders; a missing declared variable is a `KeyError`."""
        merged = {**self._defaults, **values}
        missing = self.variables - merged.keys()
        if missing:
            raise KeyError(f"missing prompt variables: {', '.join(sorted(missing))}")
        try:
            return self._template.format(**merged)
        except (AttributeError, IndexError, KeyError) as exc:
            raise ValueError(
                f"failed to render prompt (template {self._template!r}): {exc}"
            ) from exc

    def __repr__(self) -> str:
        return f"PromptTemplate(variables={sorted(self.variables)})"


class MessagesPrompt:
    """A chat prompt: an ordered set of `(role, template)` rows.

    Renders to `list[Message]`; every row sees the same variables and a missing
    variable anywhere is a `KeyError`.
    """

    def __init__(self, messages: Sequence[tuple[str, str]]):
        if not messages:
            raise ValueError(
                "MessagesPrompt requires at least one (role, template) row"
            )
        self._rows: list[tuple[Role, PromptTemplate]] = []
        for role, template in messages:
            if role not in ("system", "user", "assistant", "tool"):
                raise ValueError(f"unknown message role in MessagesPrompt: {role!r}")
            self._rows.append((cast(Role, role), PromptTemplate(template)))
        variables: set[str] = set()
        for _, row in self._rows:
            variables |= set(row.variables)
        self.variables = frozenset(variables)

    def render(self, **values: Any) -> list[Message]:
        return [
            Message(role=role, content=template.render(**values))
            for role, template in self._rows
        ]

    def __repr__(self) -> str:
        return f"MessagesPrompt(roles={[r for r, _ in self._rows]})"


__all__ = ["MessagesPrompt", "PromptTemplate"]
