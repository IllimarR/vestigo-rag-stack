"""Tests for the shared retry helper used by the wire-bound LLM providers.

Covers four cases: success after one transient 503, the 4xx-is-never-retried
rule, exhaustion after `MAX_ATTEMPTS` transient failures, and recovery from
an `httpx.TransportError`. Sleeps are captured (not actually slept on) so
the test suite stays fast.
"""

from __future__ import annotations

import httpx
import pytest

from services.llm.application import _retry
from services.llm.application._retry import (
    MAX_ATTEMPTS,
    RETRY_STATUSES,
    execute_with_retry,
)


class _Recorder:
    """Stand-in for `time.sleep` that records call durations."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def test_retry_returns_first_success_without_sleeping() -> None:
    sleeper = _Recorder()
    responses = iter([httpx.Response(200, text="ok")])

    result = execute_with_retry(lambda: next(responses), sleep=sleeper)

    assert result.status_code == 200
    assert sleeper.calls == []


def test_retry_recovers_after_transient_5xx() -> None:
    sleeper = _Recorder()
    responses = iter(
        [
            httpx.Response(503, text="retry me"),
            httpx.Response(200, text="ok"),
        ]
    )

    result = execute_with_retry(lambda: next(responses), sleep=sleeper)

    assert result.status_code == 200
    # Backed off once — second attempt succeeded.
    assert len(sleeper.calls) == 1


def test_retry_does_not_retry_4xx_client_errors() -> None:
    sleeper = _Recorder()
    call_count = 0

    def operation() -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, text="bad request")

    result = execute_with_retry(operation, sleep=sleeper)

    assert result.status_code == 400
    assert call_count == 1
    assert sleeper.calls == []


def test_retry_gives_up_after_max_attempts() -> None:
    sleeper = _Recorder()
    call_count = 0

    def operation() -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(502, text="bad gateway")

    result = execute_with_retry(operation, sleep=sleeper)

    assert result.status_code == 502
    assert call_count == MAX_ATTEMPTS
    # `MAX_ATTEMPTS - 1` backoffs between the attempts.
    assert len(sleeper.calls) == MAX_ATTEMPTS - 1


def test_retry_handles_transport_error_then_recovers() -> None:
    sleeper = _Recorder()
    attempt = {"n": 0}

    def operation() -> httpx.Response:
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, text="ok")

    result = execute_with_retry(operation, sleep=sleeper)

    assert result.status_code == 200
    assert attempt["n"] == 2
    assert len(sleeper.calls) == 1


def test_retry_reraises_transport_error_after_max_attempts() -> None:
    sleeper = _Recorder()

    def operation() -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(httpx.ConnectError):
        execute_with_retry(operation, sleep=sleeper)
    # Slept between attempts 1→2 and 2→3, then gave up.
    assert len(sleeper.calls) == MAX_ATTEMPTS - 1


def test_retry_backoff_is_exponential() -> None:
    sleeper = _Recorder()
    responses = iter(
        [
            httpx.Response(500, text="boom"),
            httpx.Response(500, text="boom"),
            httpx.Response(200, text="ok"),
        ]
    )

    execute_with_retry(
        lambda: next(responses),
        sleep=sleeper,
        base_backoff=0.5,
    )

    # 0.5 * 2**0, 0.5 * 2**1
    assert sleeper.calls == [0.5, 1.0]


def test_retry_statuses_cover_429_and_5xx_subset() -> None:
    # Document the explicit policy: only the back-pressure / overload
    # statuses are retried. Other 4xx must propagate.
    assert 429 in RETRY_STATUSES
    assert 500 in RETRY_STATUSES
    assert 503 in RETRY_STATUSES
    assert 504 in RETRY_STATUSES
    assert 400 not in RETRY_STATUSES
    assert 401 not in RETRY_STATUSES
    assert 404 not in RETRY_STATUSES


def test_module_exports_consistent() -> None:
    # Smoke-test that the public surface hasn't quietly grown — keeps the
    # retry contract small and reviewable.
    assert _retry.__all__ == [
        "BASE_BACKOFF_SECONDS",
        "MAX_ATTEMPTS",
        "RETRY_STATUSES",
        "execute_with_retry",
    ]
