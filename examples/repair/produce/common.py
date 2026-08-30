"""repair produce — shared helpers for the staged pipeline (§71).

Deterministic utilities used across the stages: project/message lookups,
reply construction, fact extraction, palette/preview text, and the rollback
("change — rebuild") model shared with stages.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ctxloom import Patch, structured_llm
from ctxloom.artifacts import Artifact
from ctxloom.context import Context
from ctxloom.recipes import (
    changed_fields,
    downstream_fields,
    stem_words,
)

from ..models import ChatReply, DesignOption, Project, ProjectInfo, UserMsg
from ..services.geometry import ensure_geometry, geometry_text

logger = logging.getLogger(__name__)

_PICK_NUMBER = re.compile(r"^\s*(\d+)\s*$")
_APPROVE_RE = re.compile(r"^(да|подтвержд|согласен|ок|yes)\b", re.IGNORECASE)
# A cost/budget complaint — rebuild cheaper from the "plan" stage, not the estimate.
_BUDGET_COMPLAINT = re.compile(
    r"бюджет|дорог|вышел за бюджет|превыш|уложи|дешевле|много|дорого",
    re.IGNORECASE,
)

_IMAGE_RENDER_TIMEOUT = 60.0
_IMAGE_RENDER_RETRIES = 3
_IMAGE_RETRY_DELAY = 2.0


def _latest_user_msg(context: Context) -> Artifact[UserMsg] | None:
    messages = context.list_artifacts(UserMsg)
    return max((m for m in messages), key=lambda m: m.created_at, default=None)


def _project_artifact(context: Context) -> Artifact[Project] | None:
    projects = context.list_artifacts(Project)
    return projects[0] if projects else None


def _update_project(project_art: Artifact[Project], updates: dict[str, Any]) -> Patch:
    return Patch().update_fields(project_art, **updates)


def _reply(
    context: Context,
    msg_id: str,
    text: str,
    kind: str = "text",
    images: list[str] | None = None,
) -> Patch:
    return Patch().create(
        ChatReply(query_id=msg_id, text=text, kind=kind, images=images or []),
        id=f"reply:{msg_id}",
    )


async def _extract_info(
    context: Context, text: str, current: ProjectInfo
) -> ProjectInfo:
    context.announce("Анализирую детали проекта…", kind="status")
    result = await structured_llm(
        context,
        schema=ProjectInfo,
        user=(
            "Извлеки факты о ремонте. Не домысливай: неизвестные поля = null.\n"
            f"Сообщение: {text}"
        ),
    )
    if result is None:
        return current
    updates = {k: v for k, v in result.model_dump().items() if v is not None}
    return current.model_copy(update=updates)


def _list_preferences(info: ProjectInfo) -> str:
    """User preferences pulled from the facts (version/palette) for the design constructor."""
    items = [
        ("стиль", info.style),
        ("цвет стен", info.wall_color),
        ("цвет потолка", info.ceiling_color),
        ("пол", info.floor_material),
    ]
    return ", ".join(f"{label}: {value}" for label, value in items if value)


def _palette_text(project: Project) -> str:
    parts = []
    if project.design_choice:
        parts.append(f"вариант: {project.design_choice}")
    if project.palette:
        parts.append(", ".join(f"{k}: {v}" for k, v in project.palette.items() if v))
    if project.info.style:
        parts.append(f"стиль: {project.info.style}")
    return "; ".join(parts) if parts else "свободный выбор"


def _parse_pick(text: str, options: list[DesignOption]) -> DesignOption | None:
    match = _PICK_NUMBER.match(text.strip())
    if match and 1 <= int(match.group(1)) <= len(options):
        return options[int(match.group(1)) - 1]
    targets = stem_words(text)
    for option in options:
        if stem_words(option.name) & targets:
            return option
    return None


def _assistant_context(project: Project) -> str:
    """A brief project summary for the post-approval assistant."""
    parts = [
        f"Комната: {project.info.room_type}, {project.info.area} м²"
        if project.info.area
        else f"Комната: {project.info.room_type}",
        f"бюджет {project.info.budget} ₽" if project.info.budget else "",
        f"вариант: {project.design_choice}" if project.design_choice else "",
    ]
    head = "; ".join(p for p in parts if p)
    lines = "\n".join(f"- {s.name}: {s.description}" for s in project.plan)
    total = project.estimate.total if project.estimate is not None else None
    tail = f"Итог: {total} ₽." if total else ""
    return f"{head}.\nПлан:\n{lines}\n{tail}"


def _conversation_text(context: Context, current_msg_id: str, limit: int = 10) -> str:
    """Conversation history up to the current message — chat memory (§27).

    Retrieved via `context.view`: type (UserMsg|ChatReply), excluding the current
    message, the last `limit` records. Formatting — tailored to the prompt.
    """
    view = context.view(
        (UserMsg, ChatReply),
        condition=lambda a: a.id != current_msg_id,
    )
    ordered = sorted(view.artifacts, key=lambda a: a.created_at)
    recent = ordered[-limit:]
    if not recent:
        return ""
    lines = [
        f"user: {a.data.text}"
        if isinstance(a.data, UserMsg)
        else f"assistant: {a.data.text}"
        for a in recent
    ]
    return "Разговор:\n" + "\n".join(lines)


def _approval_text(project: Project) -> str:
    info = project.info
    steps = "\n".join(f"- {s.name}: {s.description}" for s in project.plan)
    est_lines = project.estimate.lines if project.estimate is not None else []
    lines = "\n".join(
        f"- {line.name}: {line.quantity} {line.unit} × {line.unit_price} ₽ = {line.total} ₽"
        for line in est_lines
    )
    total = project.estimate.total if project.estimate is not None else 0
    return (
        f"Комната: {info.room_type}, {info.area} м², бюджет {info.budget} ₽.\n"
        f"План:\n{steps}\nСмета:\n{lines}\nИтого: {total} ₽\n\nУтвердить (да) или изменить?"
    )


#: Reset mapping built on the generic change → rebuild recipe (recipes.rollback).
_RESET_STAGE_FIELDS: dict[str, str] = {
    "design_options": "design_choice",
    "design_choice": "design_choice",
    "palette": "design_choice",
    "plan": "plan",
    "estimate": "estimate",
}
_RESET_EMPTY: dict[str, Any] = {
    "design_options": [],
    "design_choice": "",
    "palette": {},
    "plan": [],
    "estimate": None,
}
_RESET_STAGE_ORDER = ("collect", "design_choice", "plan", "estimate")


def _downstream_resets(target: str) -> dict[str, Any]:
    """What to reset when rolling back to `target` (the change model from services)."""
    fields = downstream_fields(
        target, field_stages=_RESET_STAGE_FIELDS, order=_RESET_STAGE_ORDER
    )
    return {field: _RESET_EMPTY[field] for field in fields}


__all__ = [
    "_APPROVE_RE",
    "_BUDGET_COMPLAINT",
    "_IMAGE_RENDER_TIMEOUT",
    "_IMAGE_RENDER_RETRIES",
    "_IMAGE_RETRY_DELAY",
    "_approval_text",
    "_assistant_context",
    "_conversation_text",
    "_downstream_resets",
    "_extract_info",
    "_latest_user_msg",
    "_list_preferences",
    "_palette_text",
    "_parse_pick",
    "_project_artifact",
    "_reply",
    "_update_project",
    "changed_fields",
    "ensure_geometry",
    "geometry_text",
    "logger",
]
