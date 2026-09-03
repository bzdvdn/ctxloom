"""Shared network-retry helper for HTTP-based LLM providers.

Every `complete()` implementation in this package hits the same class of
transient failures (429 rate limits, 5xx, connection resets/timeouts) and,
before this module, retried none of them — a single blip failed the call
outright. Not in `contracts.py`: the core stays free of the httpx dependency
(see that module's docstring); this lives in the `providers` package instead
and is imported by the concrete implementations that need it.

Scoped to `complete()` only, deliberately not `stream()`: a streaming call
can fail after already yielding chunks to the caller, and retrying by
restarting the request would silently duplicate what was already streamed.
`complete()` fails atomically (nothing to un-yield), so it's safe to retry
in full.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

#: HTTP statuses worth retrying: rate limit + server-side errors. Anything
#: else (400/401/403/404, ...) is a request/auth problem retrying won't fix.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


async def with_retry(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> T:
    """Retries `call` on transient HTTP failures with exponential backoff.

    Retries `httpx.TransportError` (connection reset, timeout, DNS...) and
    `httpx.HTTPStatusError` whose status is in `RETRYABLE_STATUS`; any other
    exception — including a non-retryable status — propagates on the first
    attempt. `attempts=1` disables retrying entirely.
    """
    for attempt in range(attempts):
        try:
            return await call()
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code not in RETRYABLE_STATUS
                or attempt + 1 >= attempts
            ):
                raise
        except httpx.TransportError:
            if attempt + 1 >= attempts:
                raise
        await asyncio.sleep(base_delay * (2**attempt))
    raise AssertionError("unreachable: loop always returns or raises")


__all__ = ["RETRYABLE_STATUS", "with_retry"]
