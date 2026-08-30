"""recipes.rollback — the "change → rebuild" model (§22, §24).

Long multi-stage flows sometimes have to *go back*: the user edits a fact, the
pipeline must rebuild from the earliest affected stage and reset every
downstream artifact. The three helpers here are the deterministic mechanism;
the workflow (stages, field→stage mapping) is the domain's own, passed in:

    field_stages = {"room": "collect", "area": "plan", "budget": "estimate"}
    order = ("collect", "design_choice", "plan", "estimate")

    changed = changed_fields(old_info, new_info)      # which fields moved
    target = earliest_stage(changed, field_stages=..., order=order)
    reset = downstream_fields(target, field_stages=..., order=order)  # what to clear

Nothing is guessed: the rebuild target is a pure function of what changed (§24).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel


def changed_fields(
    old: BaseModel,
    new: BaseModel,
    *,
    ignore: Collection[str] = (),
) -> set[str]:
    """Fields whose value differs in `new` (unknown/`None` = not changed).

    A field only counts when it was actually *set* in the new state — a `None`
    (the model did not know) is not a change.
    """
    old_dump = old.model_dump()
    new_dump = new.model_dump()
    ignored = set(ignore)
    return {
        key
        for key in old_dump
        if key not in ignored
        and new_dump.get(key) is not None
        and new_dump.get(key) != old_dump.get(key)
    }


def earliest_stage(
    changed: Collection[str],
    *,
    field_stages: Mapping[str, str],
    order: Sequence[str],
) -> str | None:
    """The earliest stage (by `order`) that any changed field belongs to.

    Returns None when nothing changed (the caller decides the no-op behavior).
    """
    for stage in order:
        affected = {
            field for field, maps_to in field_stages.items() if maps_to == stage
        }
        if affected & set(changed):
            return stage
    return None


def downstream_fields(
    target: str,
    *,
    field_stages: Mapping[str, str],
    order: Sequence[str],
) -> frozenset[str]:
    """All fields to reset when rebuilding from `target` (target stage inclusive).

    Everything produced at `target` or later belongs to the rebuild and must be
    cleared; upstream artifacts stay untouched.
    """
    if target not in order:
        return frozenset()
    index = order.index(target)
    rebuild_stages = set(order[index:])
    return frozenset(
        field for field, maps_to in field_stages.items() if maps_to in rebuild_stages
    )


__all__ = ["changed_fields", "downstream_fields", "earliest_stage"]
