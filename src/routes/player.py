# -*- coding: utf-8 -*-
"""
player.py — /player/<uid> endpoint.

Features:
  - UID + region validation
  - Per-UID rate limiting (in-memory, sliding window)
  - Cache lookup before hitting Garena
  - Structured error responses
"""

import time
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque

from flask import Blueprint, jsonify, request

from src.core.cache import cache_get, cache_set
from src.core.config import config
from src.core.logger import get_logger, set_request_context
from src.ff import client
from src.ff.regions import SUPPORTED_REGION_CODES, is_supported
from src.utils.retry import CircuitOpenError

log = get_logger(__name__)
player_bp = Blueprint("player", __name__)

# ── Per-UID rate limiter (sliding window, in-memory) ─────────────────────────

_rate_windows: dict[str, Deque[float]] = defaultdict(lambda: deque())
_rate_lock = threading.Lock()
_WINDOW_SECONDS = 60.0


def _is_rate_limited(uid: str, region: str) -> bool:
    if not config.enable_rate_limit:
        return False
    key = f"{region}:{uid}"
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _rate_lock:
        window = _rate_windows[key]
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= config.rate_limit_per_uid:
            return True
        window.append(now)
        return False


# ── Route ─────────────────────────────────────────────────────────────────────


@player_bp.route("/player/<string:uid>")
@player_bp.route("/player")
@player_bp.route("/info")
@player_bp.route("/api/v1/player")
def get_player(uid: str = None):
    if not uid:
        uid = request.args.get("uid", "").strip()

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    region = request.args.get("region", "IND").strip().upper()

    set_request_context(request_id=request_id, uid=uid, region=region)

    # ── Validate UID ──────────────────────────────────────────────────────────
    if not uid.isdigit() or not (5 <= len(uid) <= 16):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Invalid UID format. Must be 5–16 digits.",
                    "request_id": request_id,
                }
            ),
            400,
        )

    # ── Validate region (fall back to IND silently) ───────────────────────────
    if not is_supported(region):
        log.warning("Unsupported region '%s' — defaulting to IND", region)
        region = "IND"

    # ── Rate limit ────────────────────────────────────────────────────────────
    if _is_rate_limited(uid, region):
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Rate limit exceeded. Max {config.rate_limit_per_uid} requests/minute per UID.",
                    "request_id": request_id,
                }
            ),
            429,
        )

    # ── Cache lookup ──────────────────────────────────────────────────────────
    cached_data = cache_get(region, uid)
    if cached_data is not None:
        log.info("Cache HIT uid=%s region=%s", uid, region)
        return jsonify(
            {
                "success": True,
                "cached": True,
                "fetched_at": cached_data.get("_fetched_at"),
                "request_id": request_id,
                **cached_data,
            }
        )

    # ── Live Garena fetch ─────────────────────────────────────────────────────
    try:
        data = client.fetch_player(int(uid), region)
    except CircuitOpenError as exc:
        log.error("Circuit breaker open for region %s: %s", region, exc)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Garena API temporarily unavailable (circuit breaker open). Try again in 60s.",
                    "region": region,
                    "request_id": request_id,
                }
            ),
            503,
        )
    except RuntimeError as exc:
        log.error("Garena fetch failed: %s", exc)
        return (
            jsonify(
                {
                    "success": False,
                    "error": str(exc),
                    "region": region,
                    "request_id": request_id,
                }
            ),
            502,
        )
    except Exception as exc:
        log.exception("Unexpected error fetching player uid=%s", uid)
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Internal gateway error",
                    "request_id": request_id,
                }
            ),
            500,
        )

    fetched_at = datetime.now(timezone.utc).isoformat()
    data["_fetched_at"] = fetched_at
    cache_set(region, uid, data)

    return jsonify(
        {
            "success": True,
            "cached": False,
            "fetched_at": fetched_at,
            "request_id": request_id,
            **data,
        }
    )
