"""Exceptions for `ctxloom.testing`."""

from __future__ import annotations


class ScenarioError(Exception):
    """Misuse of the scenario harness itself (not a failed assertion) — e.g.
    `lab.fail_resource("no_such_name", ...)` naming a resource that doesn't
    exist on this scenario's `RuntimeResources`.
    """


class ScenarioSkip(Exception):
    """A scenario opts out of running (e.g. no API key, no recorded fixture).

    Raise this from inside a `@scenario`-decorated function — the `ctxloom
    scenario` CLI reports it as `SKIP` (with this exception's message),
    distinct from a failed assertion or a crash.
    """


class AssertionFailure(AssertionError):
    """A scenario assertion did not hold.

    Subclasses `AssertionError` so pytest's assertion introspection/output
    still applies to it like any other failed `assert`.
    """
