# -*- coding: utf-8 -*-
"""
retry.py — Exponential backoff + circuit breaker.

Usage:
    @with_retry(max_attempts=3, base_delay=1.0)
    def call_garena():
        ...

Circuit breaker is per-region and shared across threads.
"""

import functools
import threading
import time
from typing import Callable, TypeVar

from src.core.config import config
from src.core.logger import get_logger

log = get_logger(__name__)

F = TypeVar("F", bound=Callable)

# ── Circuit Breaker ───────────────────────────────────────────────────────────


class CircuitBreaker:
    """
    Simple per-key half-open circuit breaker.
    States: CLOSED → OPEN (after N failures) → HALF_OPEN (after reset_seconds)
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, threshold: int, reset_seconds: int) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._lock = threading.Lock()
        # key → (state, failure_count, opened_at)
        self._circuits: dict[str, tuple[str, int, float]] = {}

    def _get(self, key: str) -> tuple[str, int, float]:
        return self._circuits.get(key, (self.CLOSED, 0, 0.0))

    def is_open(self, key: str) -> bool:
        with self._lock:
            state, count, opened_at = self._get(key)
            if state == self.OPEN:
                if time.monotonic() - opened_at >= self._reset_seconds:
                    self._circuits[key] = (self.HALF_OPEN, count, opened_at)
                    return False
                return True
            return False

    def record_success(self, key: str) -> None:
        with self._lock:
            self._circuits[key] = (self.CLOSED, 0, 0.0)

    def record_failure(self, key: str) -> None:
        with self._lock:
            state, count, opened_at = self._get(key)
            count += 1
            if count >= self._threshold:
                self._circuits[key] = (self.OPEN, count, time.monotonic())
                log.warning(
                    "Circuit breaker OPENED for key='%s' after %d failures", key, count
                )
            else:
                self._circuits[key] = (state, count, opened_at)

    def state(self, key: str) -> str:
        with self._lock:
            return self._get(key)[0]


# Shared circuit breaker instance (per-region key)
circuit_breaker = CircuitBreaker(
    threshold=config.circuit_breaker_threshold,
    reset_seconds=config.circuit_breaker_reset_seconds,
)


# ── Retry decorator ───────────────────────────────────────────────────────────


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is OPEN for a given key."""


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    circuit_key: str = "default",
) -> Callable[[F], F]:
    """
    Decorator factory.  Wraps a callable with:
      - exponential backoff retries
      - circuit breaker check (raises CircuitOpenError immediately when open)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if circuit_breaker.is_open(circuit_key):
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN for '{circuit_key}'. "
                    f"Retry after {config.circuit_breaker_reset_seconds}s."
                )

            last_exc: Exception = RuntimeError("Unknown error")
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    circuit_breaker.record_success(circuit_key)
                    return result
                except CircuitOpenError:
                    raise
                except Exception as exc:
                    last_exc = exc
                    circuit_breaker.record_failure(circuit_key)
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        log.warning(
                            "Attempt %d/%d failed for '%s': %s — retrying in %.1fs",
                            attempt,
                            max_attempts,
                            circuit_key,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator
