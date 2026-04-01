"""Transient-failure retry helper for the three wire-bound LLM providers.

Retries cover two failure modes that the upstream genuinely means as
"please try again": a network-level `httpx.TransportError` (DNS, refused
connection, read timeout, etc.) and an HTTP status the spec uses to
signal back-pressure (429) or server overload (5xx). Other 4xx
responses are *never* retried — those are the caller's bug, and
retrying would hide it.

Only the **unary** (non-streaming) request paths use this helper.
Streaming responses cannot be safely resumed mid-stream once the
upstream has started emitting tokens, so `generate_stream` is left
unretried — the SSE client retries the request if the connection
drops, which is the standard OpenAI-compatible pattern.

Backoff is exponential (0.5s, 1s, 2s, ...) with a small cap of three
attempts total. The cap matters more than the curve — generation
latency is already in seconds, so a longer retry budget would just
stack onto user-visible wait time.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

__all__ = [
    "BASE_BACKOFF_SECONDS",
    "MAX_ATTEMPTS",
    "RETRY_STATUSES",
    "execute_with_retry",
]

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.5


def execute_with_retry(
    operation: Callable[[], httpx.Response],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    base_backoff: float = BASE_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Run `operation`, retrying transient failures.

    Returns the final `httpx.Response` (success or last-attempt failure).
    Callers still call `raise_for_status()` themselves so the eventual
    error surfaces with the upstream's body intact.

    Raises the last `httpx.TransportError` if every attempt failed at
    the network layer.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            response = operation()
        except httpx.TransportError:
            if attempt >= max_attempts:
                raise
            sleep(base_backoff * (2 ** (attempt - 1)))
            continue

        if response.status_code in RETRY_STATUSES and attempt < max_attempts:
            # Free the failed response's connection before retrying so the
            # client pool doesn't leak a slot on each attempt.
            response.close()
            sleep(base_backoff * (2 ** (attempt - 1)))
            continue

        return response
