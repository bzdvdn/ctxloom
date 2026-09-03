"""with_retry (ctxloom.providers._retry): transient-failure retry/backoff."""

import asyncio

import httpx
import pytest
from ctxloom.providers._retry import RETRYABLE_STATUS, with_retry


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://example.test")
    response = httpx.Response(status, request=request)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return exc
    raise AssertionError("expected raise_for_status to raise")  # pragma: no cover


def test_succeeds_on_first_try_without_sleeping(monkeypatch):
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        return "ok"

    async def fail_if_called(*_a, **_kw):
        raise AssertionError("with_retry slept despite succeeding on the first try")

    monkeypatch.setattr(asyncio, "sleep", fail_if_called)
    result = asyncio.run(with_retry(call))
    assert result == "ok"
    assert calls == 1


def test_retries_transport_error_then_succeeds(monkeypatch):
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom")
        return "ok"

    async def no_sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    result = asyncio.run(with_retry(call))
    assert result == "ok"
    assert calls == 2


def test_retries_retryable_status_then_succeeds(monkeypatch):
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _status_error(429)
        return "ok"

    async def no_sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    result = asyncio.run(with_retry(call))
    assert result == "ok"
    assert calls == 2


def test_does_not_retry_non_retryable_status():
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        raise _status_error(401)

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        asyncio.run(with_retry(call))
    assert excinfo.value.response.status_code == 401
    assert calls == 1  # no retry attempted


def test_raises_after_exhausting_attempts(monkeypatch):
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("still down")

    async def no_sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(httpx.ConnectError):
        asyncio.run(with_retry(call, attempts=3))
    assert calls == 3


def test_attempts_one_disables_retry():
    calls = 0

    async def call():
        nonlocal calls
        calls += 1
        raise _status_error(500)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(with_retry(call, attempts=1))
    assert calls == 1


def test_retryable_status_set_is_rate_limit_and_server_errors():
    expected = {429, 500, 502, 503, 504}
    assert expected == RETRYABLE_STATUS
