# -*- coding: utf-8 -*-
"""
cache.py — Two-tier cache: in-memory LRU + optional Redis.

Cache key format: player:{region}:{uid}
TTL is governed by CACHE_TTL_SECONDS env var (default 300 s / 5 min).
Redis is used when REDIS_URL is set; otherwise falls back silently to
in-memory only.
"""

import json
import time
import threading
from collections import OrderedDict
from typing import Any, Optional

from src.core.config import config
from src.core.logger import get_logger

log = get_logger(__name__)

# ── In-memory LRU ────────────────────────────────────────────────────────────

_LRU_MAX_SIZE = 512


class _LRUCache:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = _LRU_MAX_SIZE) -> None:
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._store:
                return None
            value, expires_at = self._store[key]
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            expires_at = time.monotonic() + ttl
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expires_at)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._store)


# ── Redis client (optional) ───────────────────────────────────────────────────

_redis_client: Any = None


def _init_redis() -> Optional[Any]:
    if not config.redis_url:
        return None
    try:
        import redis  # type: ignore[import]

        client = redis.from_url(config.redis_url, socket_timeout=2, decode_responses=True)
        client.ping()
        log.info("Redis cache connected", extra={})
        return client
    except Exception as exc:
        log.warning(
            "Redis unavailable — falling back to in-memory only. Error: %s", exc
        )
        return None


# ── Public cache layer ────────────────────────────────────────────────────────

_lru = _LRUCache()


def _init() -> None:
    global _redis_client
    _redis_client = _init_redis()


def _make_key(region: str, uid: str) -> str:
    return f"player:{region.upper()}:{uid}"


def cache_get(region: str, uid: str) -> Optional[dict]:
    if not config.enable_cache:
        return None

    key = _make_key(region, uid)

    # L1: in-memory
    result = _lru.get(key)
    if result is not None:
        return result

    # L2: Redis
    if _redis_client:
        try:
            raw = _redis_client.get(key)
            if raw:
                value = json.loads(raw)
                _lru.set(key, value, config.cache_ttl_seconds)
                return value
        except Exception as exc:
            log.warning("Redis get failed: %s", exc)

    return None


def cache_set(region: str, uid: str, data: dict) -> None:
    if not config.enable_cache:
        return

    key = _make_key(region, uid)
    _lru.set(key, data, config.cache_ttl_seconds)

    if _redis_client:
        try:
            _redis_client.setex(key, config.cache_ttl_seconds, json.dumps(data))
        except Exception as exc:
            log.warning("Redis set failed: %s", exc)


def cache_delete(region: str, uid: str) -> None:
    key = _make_key(region, uid)
    _lru.delete(key)
    if _redis_client:
        try:
            _redis_client.delete(key)
        except Exception as exc:
            log.warning("Redis delete failed: %s", exc)


def cache_stats() -> dict:
    return {
        "backend": "redis+lru" if _redis_client else "lru",
        "lru_size": _lru.size(),
        "ttl_seconds": config.cache_ttl_seconds,
        "enabled": config.enable_cache,
    }
