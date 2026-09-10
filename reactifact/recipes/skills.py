"""recipes.skills — deterministic, keyword-triggered instruction snippets (§67).

A "skill" here is the same shape popularized by Claude's Skills: a short
markdown file with a `name`/`description` frontmatter and a body of
procedural instructions. It differs from a `Source` in what it is *for* — a
`Source` is retrieved to answer a question with facts; a skill is loaded to
change *how* an LLM call for this turn is made (a rule to follow, a format to
use) once its description matches the situation at hand.

Matching is deterministic keyword overlap (`keyword_score`, §67) over
name+description — no embeddings, no new core primitive (§61): a matched
skill's `body` is just a string you prepend to a `structured_llm`/`llm_reply`
prompt. Composition over abstraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .text import keyword_score

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    """A named, described instruction snippet, loaded on demand (§67)."""

    name: str
    description: str
    body: str


def parse_skill(content: str, *, default_name: str = "") -> Skill:
    """Parses `---\\nname: ...\\ndescription: ...\\n---\\n<body>` into a `Skill`.

    Missing or malformed frontmatter is not an error: the whole content
    becomes the body, `name` falls back to `default_name` (typically the file
    stem) and `description` to `""` — a skill with no description simply
    never matches (`match_skills` needs it to score above `threshold`).
    """
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return Skill(name=default_name, description="", body=content.strip())
    header, body = match.groups()
    fields: dict[str, str] = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip().lower()] = value.strip()
    return Skill(
        name=fields.get("name", default_name),
        description=fields.get("description", ""),
        body=body.strip(),
    )


def load_skills(
    directory: str | Path, *, extensions: tuple[str, ...] = (".md",)
) -> list[Skill]:
    """Parses every skill file under `directory` (honest empty list if absent)."""
    root = Path(directory)
    if not root.exists():
        return []
    skills: list[Skill] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in extensions:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        skills.append(parse_skill(content, default_name=path.stem))
    return skills


def match_skills(
    skills: list[Skill],
    situation: str,
    *,
    threshold: float = 0.34,
    limit: int = 1,
) -> list[Skill]:
    """The subset of `skills` whose name+description covers `situation` (§67).

    `situation` is a short, code-written description of what is currently
    being done ("assembling an answer backed by a computed total"), not
    necessarily the user's raw question — the caller characterizes the
    moment, the same way a skill's own description characterizes when to use
    it. Ranked by `keyword_score`, highest first; only matches scoring at or
    above `threshold` are returned, capped at `limit` — a skill should be a
    precise trigger, not a grab-bag fallback that fires on every turn.
    """
    scored = [
        (keyword_score(f"{skill.name} {skill.description}", situation), skill)
        for skill in skills
    ]
    matched = sorted(
        (item for item in scored if item[0] >= threshold),
        key=lambda item: item[0],
        reverse=True,
    )
    return [skill for _, skill in matched[:limit]]


__all__ = ["Skill", "load_skills", "match_skills", "parse_skill"]
