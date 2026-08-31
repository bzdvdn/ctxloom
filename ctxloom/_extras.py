"""ctxloom._extras — readable errors for optional dependencies.

Core must stay dependency-free; extra-gated features lazily import their
driver. Instead of a bare `ModuleNotFoundError`, `require_extra` explains what
it needs and how to install it:

    from ctxloom._extras import require_extra
    psycopg = require_extra("PostgreSQLKVBackend", "psycopg", "pg")

    # -> ImportError:
    # ctxloom.PostgreSQLKVBackend requires the 'pg' extra (psycopg).
    # Install it with `pip install "ctxloom[pg]"` or `uv sync --extra pg`.
"""

from __future__ import annotations

import importlib
from typing import Any


def require_extra(feature: str, module: str, extra: str) -> Any:
    """Imports `module`, or raises a readable error with the install hint."""
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        missing = exc.name or module
        if not (missing == module or missing.startswith(module + ".")):
            raise  # not our dependency — re-raise the original error
        raise ImportError(
            f"ctxloom.{feature} requires the {extra!r} extra ({module}). "
            f'Install it with `pip install "ctxloom[{extra}]"` '
            f"or `uv sync --extra {extra}`."
        ) from None


__all__ = ["require_extra"]
