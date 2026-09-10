"""recipes — locating typed artifacts among a produce's `inputs`.

A produce whose agent declares more than one `Consume` type receives a flat
`list[Artifact[Any]]` merged across all of them; picking out "the one
Question" or "all the Evidence" is the same
`next((a for a in inputs if isinstance(a.data, X)), None)` boilerplate in
nearly every example. These two helpers replace it without hiding anything —
`find` is a typed `next(..., None)`, `find_all` is a typed filter.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from ..artifacts import Artifact

TData = TypeVar("TData", bound=BaseModel)


def find(inputs: list[Artifact[Any]], data_type: type[TData]) -> Artifact[TData] | None:
    """First input artifact whose `.data` is an instance of `data_type`, else `None`."""
    return next((a for a in inputs if isinstance(a.data, data_type)), None)


def find_all(
    inputs: list[Artifact[Any]], data_type: type[TData]
) -> list[Artifact[TData]]:
    """All input artifacts whose `.data` is an instance of `data_type`."""
    return [a for a in inputs if isinstance(a.data, data_type)]


__all__ = ["find", "find_all"]
