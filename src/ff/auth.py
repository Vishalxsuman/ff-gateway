"""Authorized session-token lifecycle for the Free Fire gateway."""

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

from src.core.config import config
from src.core.logger import get_logger

log = get_logger(__name__)
_CHECK_INTERVAL_SECONDS = 60
_state_lock = threading.Lock()
_refresh_lock = threading.Lock()
_token = ""
_issued_at = 0.0
_expires_at = 0.0
_last_refresh: Optional[datetime] = None
_consecutive_failures = 0
_is_degraded = False
_invalid_tokens: set[str] = set()


def _parse_jwt_expiry(token: str) -> float:
    try:
        import base64

        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def mark_token_invalid(token: str) -> None:
    global _token, _expires_at
    clean = token.strip()
    if not clean:
        return
    _invalid_tokens.add(clean)
    with _state_lock:
        if _token == clean:
            _token = ""
            _expires_at = 0.0
    log.warning("Configured Garena session was rejected and evicted")


def _set_token(token: str) -> float:
    global _token, _issued_at, _expires_at, _last_refresh
    global _consecutive_failures, _is_degraded
    clean = token.strip().removeprefix("Bearer ").strip()
    expiry = _parse_jwt_expiry(clean)
    if not clean.startswith("eyJ") or expiry <= time.time() + 60:
        raise ValueError("Session token is malformed or expires within 60 seconds")
    with _state_lock:
        _token = clean
        _issued_at = time.time()
        _expires_at = expiry
        _last_refresh = datetime.now(timezone.utc)
        _consecutive_failures = 0
        _is_degraded = False
    return expiry


def _load_token() -> Optional[str]:
    configured = os.getenv("FF_SESSION_JWT", "").strip()
    if configured:
        return configured

    provider_url = os.getenv("FF_TOKEN_PROVIDER_URL", "").strip()
    provider_secret = os.getenv("FF_TOKEN_PROVIDER_SECRET", "").strip()
    if not provider_url or not provider_secret:
        return None

    if urlparse(provider_url).scheme != "https":
        log.error("FF_TOKEN_PROVIDER_URL must use HTTPS")
        return None

    try:
        response = requests.get(
            provider_url,
            headers={"Accept": "application/json", "Authorization": f"Bearer {provider_secret}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("token") or payload.get("jwt") or payload.get("session_token") or "").strip()
        return token or None
    except (requests.RequestException, ValueError, AttributeError) as exc:
        log.warning("Authorized session-token provider request failed: %s", exc)
        return None


def _refresh_token() -> bool:
    global _consecutive_failures, _is_degraded
    with _refresh_lock:
        try:
            candidate = _load_token()
            if not candidate or candidate in _invalid_tokens:
                raise RuntimeError("No valid authorized session token source is configured")
            _set_token(candidate)
            log.info("Authorized Free Fire session token loaded/refreshed")
            return True
        except Exception as exc:
            with _state_lock:
                _consecutive_failures += 1
                _is_degraded = _consecutive_failures >= 3
            log.warning("Authorized session-token refresh failed: %s", exc)
            return False


def get_token() -> str:
    with _state_lock:
        current = _token
        expires_at = _expires_at
    if not current or current in _invalid_tokens or expires_at <= time.time() + max(60, config.token_refresh_buffer_seconds):
        _refresh_token()
        with _state_lock:
            current = _token
    return current


def update_token(token: str) -> dict:
    expiry = _set_token(token)
    _invalid_tokens.discard(token.strip())
    try:
        from src.utils.retry import circuit_breaker

        circuit_breaker.reset_all()
    except Exception as exc:
        log.warning("Could not reset circuit breakers after token update: %s", exc)
    return {
        "success": True,
        "expires_at_iso": datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat(),
        "expires_in_hours": round((expiry - time.time()) / 3600, 2),
    }


def health_info() -> dict:
    with _state_lock:
        now = time.time()
        return {
            "age_seconds": round(now - _issued_at, 1) if _issued_at else 0,
            "expires_in_seconds": round(max(0, _expires_at - now), 1),
            "last_refresh": _last_refresh.isoformat() if _last_refresh else None,
            "consecutive_failures": _consecutive_failures,
            "is_degraded": _is_degraded,
        }


def health_status() -> str:
    with _state_lock:
        if _is_degraded:
            return "degraded"
        if not _token or _expires_at <= time.time():
            return "unhealthy"
        return "healthy"


def initialize() -> None:
    _refresh_token()

    def refresh_loop() -> None:
        while True:
            time.sleep(_CHECK_INTERVAL_SECONDS)
            with _state_lock:
                should_refresh = not _token or _expires_at <= time.time() + max(60, config.token_refresh_buffer_seconds)
            if should_refresh:
                _refresh_token()

    threading.Thread(target=refresh_loop, name="ff-token-refresh", daemon=True).start()