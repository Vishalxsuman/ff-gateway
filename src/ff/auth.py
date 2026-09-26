# -*- coding: utf-8 -*-
"""
auth.py — Token Manager with auto-refresh.

Strategy:
  1. On startup, load token from ENV (FF_GUEST_TOKEN if set) or token cache file.
  2. If none found, perform Garena guest login using FF_GUEST_UID / FF_GUEST_PASSWORD.
  3. Background thread checks expiry every minute and refreshes 5 min before expiry.
  4. If 3 consecutive refreshes fail, mark health as DEGRADED (visible in /health).
  5. Token is stored in memory + optional file for persistence across restarts.

NOTE: Garena guest tokens are ~6 months valid.  The auto-refresh logic handles
shorter-lived tokens should Garena reduce TTL.  Manual rotation is only needed
if you permanently lose guest account credentials.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from src.core.config import config
from src.core.logger import get_logger

log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TOKEN_CACHE_FILE = Path("/tmp/ff_token_cache.json")
_GARENA_LOGIN_URL = "https://loginbp.ggpolarbear.com/MajorLogin"
_CHECK_INTERVAL_SECONDS = 60  # how often the background thread checks expiry

# ── Token state ───────────────────────────────────────────────────────────────


class _TokenState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.token: str = ""
        self.issued_at: float = 0.0
        self.expires_at: float = 0.0
        self.last_refresh: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self.is_degraded: bool = False

    def set(self, token: str, expires_at: float) -> None:
        with self._lock:
            self.token = token
            self.issued_at = time.time()
            self.expires_at = expires_at
            self.last_refresh = datetime.now(timezone.utc)
            self.consecutive_failures = 0
            self.is_degraded = False

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 3:
                self.is_degraded = True
                log.error(
                    "Token refresh failed 3 consecutive times — gateway DEGRADED"
                )

    def get_token(self) -> str:
        with self._lock:
            return self.token

    def age_seconds(self) -> float:
        with self._lock:
            return time.time() - self.issued_at if self.issued_at else 0.0

    def expires_in_seconds(self) -> float:
        with self._lock:
            return max(0.0, self.expires_at - time.time())

    def needs_refresh(self) -> bool:
        with self._lock:
            if not self.token:
                return True
            return (self.expires_at - time.time()) < config.token_refresh_buffer_seconds

    def health_status(self) -> str:
        with self._lock:
            if self.is_degraded:
                return "degraded"
            if not self.token:
                return "unhealthy"
            return "healthy"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "age_seconds": round(time.time() - self.issued_at, 1) if self.issued_at else 0,
                "expires_in_seconds": round(max(0.0, self.expires_at - time.time()), 1),
                "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
                "consecutive_failures": self.consecutive_failures,
                "is_degraded": self.is_degraded,
            }


_state = _TokenState()

# ── Persistence ───────────────────────────────────────────────────────────────


def _save_token_cache(token: str, expires_at: float) -> None:
    try:
        _TOKEN_CACHE_FILE.write_text(
            json.dumps({"token": token, "expires_at": expires_at}),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("Could not write token cache: %s", exc)


def _load_token_cache() -> Optional[tuple[str, float]]:
    try:
        if not _TOKEN_CACHE_FILE.exists():
            return None
        data = json.loads(_TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
        token = data.get("token", "")
        expires_at = float(data.get("expires_at", 0))
        if token and expires_at > time.time() + 60:
            return token, expires_at
    except Exception as exc:
        log.warning("Could not load token cache: %s", exc)
    return None


# ── Garena login ──────────────────────────────────────────────────────────────


def _parse_jwt_expiry(token: str) -> float:
    """
    Decode JWT exp field without a crypto library (no verification needed —
    we trust our own token).  Returns Unix timestamp of expiry.
    Falls back to 6 months from now if parsing fails.
    """
    try:
        import base64

        payload_b64 = token.split(".")[1]
        # Fix padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"])
    except Exception:
        log.warning("Could not parse JWT expiry — defaulting to 6 months")
        return time.time() + 60 * 60 * 24 * 180  # 6 months


def _do_login() -> tuple[str, float]:
    """
    Authenticate with Garena's MajorLogin endpoint using guest credentials.

    Returns (jwt_token, expires_at_unix_timestamp).
    Raises RuntimeError on failure.
    """
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2018.4.11f1",
        "ReleaseVersion": config.ff_ob_version,
        "X-GA": "v1 1",
        "Connection": "Keep-Alive",
    }

    # Garena guest login payload
    payload = {
        "uid": config.ff_guest_uid,
        "password": config.ff_guest_password,
        "client_type": "2",
        "plat_id": "1",
    }

    response = requests.post(
        _GARENA_LOGIN_URL,
        headers=headers,
        data=payload,
        timeout=15,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Garena MajorLogin returned HTTP {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    token = data.get("token") or data.get("data", {}).get("token", "")
    if not token:
        # Some Garena responses nest the token differently
        token = data.get("access_token", "")

    if not token:
        raise RuntimeError(
            f"MajorLogin succeeded but no token found in response: {str(data)[:300]}"
        )

    expires_at = _parse_jwt_expiry(token)
    log.info(
        "Garena login succeeded — token valid for %.0f hours",
        (expires_at - time.time()) / 3600,
    )
    return token, expires_at


def _refresh_token() -> None:
    """Attempt login and update _state; record failure on exception."""
    log.info("Attempting Garena token refresh…")
    try:
        token, expires_at = _do_login()
        _state.set(token, expires_at)
        _save_token_cache(token, expires_at)
        log.info("Token refresh successful")
    except Exception as exc:
        _state.record_failure()
        log.error("Token refresh failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────


def get_token() -> str:
    """Return the current valid JWT.  Never blocks; returns empty string if unavailable."""
    return _state.get_token()


def health_info() -> dict:
    return _state.snapshot()


def health_status() -> str:
    return _state.health_status()


# ── Background refresh thread ─────────────────────────────────────────────────


def _background_refresh_loop() -> None:
    while True:
        time.sleep(_CHECK_INTERVAL_SECONDS)
        if _state.needs_refresh():
            _refresh_token()


def initialize() -> None:
    """
    Called once at startup:
      1. Try ENV-injected token (FF_GUEST_TOKEN).
      2. Try token cache file.
      3. Perform fresh login if neither is valid.
      4. Start background refresh thread.
    """
    # Option 1: static token in ENV (override — useful for short-term debugging)
    env_token = os.getenv("FF_GUEST_TOKEN", "").strip()
    if env_token:
        expires_at = _parse_jwt_expiry(env_token)
        if expires_at > time.time() + 60:
            _state.set(env_token, expires_at)
            log.info(
                "Using FF_GUEST_TOKEN from ENV (valid for %.0f hours)",
                (expires_at - time.time()) / 3600,
            )
        else:
            log.warning("FF_GUEST_TOKEN from ENV is expired — ignoring")

    # Option 2: cached token from previous run
    if not _state.get_token():
        cached = _load_token_cache()
        if cached:
            token, expires_at = cached
            _state.set(token, expires_at)
            log.info(
                "Loaded cached token (valid for %.0f hours)",
                (expires_at - time.time()) / 3600,
            )

    # Option 3: fresh login
    if not _state.get_token():
        log.info("No valid token found — performing fresh Garena login")
        _refresh_token()

    # Start background refresh daemon thread
    thread = threading.Thread(
        target=_background_refresh_loop,
        name="ff-token-refresh",
        daemon=True,
    )
    thread.start()
    log.info("Token refresh background thread started")
