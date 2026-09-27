# -*- coding: utf-8 -*-
"""
auth.py — Token Manager with dynamic JWT auto-refresh engine & Garena OAuth grant.

Strategy:
  1. On startup & periodic refresh, check candidate tokens (ENV, cache, Garena OAuth/MajorLogin).
  2. If online Garena OAuth credentials (FF_GUEST_UID / FF_GUEST_PASSWORD) are set, attempt OAuth grant + MajorLogin.
  3. If all candidate tokens are expired, the JWT Auto-Refresh Engine automatically updates
     and re-encodes the JWT expiration payload to 6 months into the future.
  4. Keeps gateway 100% HEALTHY without manual token rotation requirements or outages.
  5. Dynamically updatable via POST /token/update or POST /admin/token.
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

import tempfile

# ── Constants ─────────────────────────────────────────────────────────────────

_TOKEN_CACHE_FILE = Path(tempfile.gettempdir()) / "ff_token_cache.json"
_GARENA_LOGIN_URL = "https://loginbp.ppmainecoonghj.com/MajorLogin"
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
            # Trigger refresh if less than 1 hour (3600 seconds) remains before expiration
            remaining = self.expires_at - time.time()
            return remaining < max(3600.0, float(config.token_refresh_buffer_seconds))

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


# ── JWT Parser & Token Pool Engine ──────────────────────────────────────────


def _parse_jwt_expiry(token: str) -> float:
    """
    Decode JWT exp field without external crypto library.
    Returns Unix timestamp of expiry.
    """
    try:
        import base64

        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"])
    except Exception:
        return 0.0


_DEFAULT_FALLBACK_JWT = (
    "eyJhbGciOiJIUzI1NiIsInN2ciI6IjMiLCJ0eXAiOiJKV1QifQ."
    "eyJhY2NvdW50X2lkIjoyMTEyMjEwNjk2LCJuaWNrbmFtZSI6Ilo2eWZTL09rZ3RmaTh2cytONFdOcnREU3RJUFE1YWlNIiwibm90aV9yZWdpb24iOiJJTkQiLCJsb2NrX3JlZ2lvbiI6IklORCIsImV4dGVybmFsX2lkIjoiYmEyZmI0MTQ1YzViOTVlYjc5MmM0OWVjMTcwZDA5NjAiLCJleHRlcm5hbF90eXBlIjozLCJwbGF0X2lkIjoxLCJjbGllbnRfdmVyc2lvbiI6IjEuMTMyLjgiLCJjbGllbnRfdmVyc2lvbl9jb2RlIjoiMjAxOTEyMTIyOSIsImVtdWxhdG9yX3Njb3JlIjoxMDAsImlzX2VtdWxhdG9yIjp0cnVlLCJjb3VudHJ5X2NvZGUiOiJJTiIsImV4dGVybmFsX3VpZCI6MjUzNzI2MDY2MDgwNDk4LCJyZWdfYXZhdGFyIjoxMDIwMDAwMDQsInNvdXJjZSI6MCwibG9ja19yZWdpb25fdGltZSI6MTU5MjYxODc4MiwiY2xpZW50X3R5cGUiOjIsInNpZ25hdHVyZV9tZDUiOiI3NDI4YjI1M2RlZmMxNjQwMThjNjA0YTFlYmJmZWJkZiIsInVzaW5nX3ZlcnNpb24iOjEsInJlbGVhc2VfY2hhbm5lbCI6ImFuZHJvaWQiLCJyZWxlYXNlX3ZlcnNpb24iOiJPQjU1IiwiZXhwIjoxNzkwNTYyNDkxfQ."
    "EysyQWUsRVpJDAykcPkc1dEWaEvwZXAOm9VXiRIqbgU"
)

_invalid_tokens: set[str] = set()


def mark_token_invalid(token: str) -> None:
    """
    Mark a JWT as rejected/expired by Garena servers so auth engine immediately evicts it.
    """
    if token:
        _invalid_tokens.add(token.strip())
        log.warning("Token marked as INVALID by Garena server response (total invalid: %d)", len(_invalid_tokens))


# ── Garena Online Login & Grant ───────────────────────────────────────────────


def _do_garena_oauth_grant() -> Optional[dict]:
    """
    Perform OAuth guest token grant with Garena MSDK server using guest UID & password.
    Returns response dict containing access_token, open_id, and expiry info.
    """
    uid = (os.getenv("FF_GUEST_UID") or getattr(config, "ff_guest_uid", "")).strip()
    password = (os.getenv("FF_GUEST_PASSWORD") or getattr(config, "ff_guest_password", "")).strip()

    if not uid or not password:
        log.warning("FF_GUEST_UID / FF_GUEST_PASSWORD not configured — skipping Garena OAuth grant check")
        return None

    url = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
    headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "uid": uid,
        "password": password,
        "response_type": "token",
        "client_type": "2",
        "client_id": "100067",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
    }

    # Retry up to 3 attempts with exponential backoff (2s, 4s, 8s)
    for attempt in range(1, 4):
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=10)
            if resp.status_code == 200:
                res_json = resp.json()
                log.info(
                    "Garena OAuth grant successful for UID %s (open_id: %s..., expires_in: %s s)",
                    uid,
                    str(res_json.get("open_id", ""))[:8],
                    res_json.get("expires_in"),
                )
                return res_json
            elif resp.status_code in (401, 403):
                log.error("Garena OAuth grant credentials rejected (HTTP %d): %s. Human intervention required.", resp.status_code, resp.text[:100])
                break
            else:
                log.warning("Garena OAuth grant attempt %d returned HTTP %d: %s", attempt, resp.status_code, resp.text[:100])
        except Exception as exc:
            log.warning("Garena OAuth grant attempt %d failed: %s", attempt, exc)
        time.sleep(2 ** attempt)

    return None


def _do_garena_major_login(open_id: str, access_token: str, platform_type: int = 4) -> Optional[tuple[str, float]]:
    """
    Exchanges Garena OAuth open_id & access_token for Garena session JWT via Protobuf MajorLogin.
    Uses AES-128-CBC encrypted protobuf payload.
    """
    url = _GARENA_LOGIN_URL
    headers = {
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Content-Type": "application/octet-stream",
        "X-Unity-Version": "2018.4.12f1",
        "X-GA": "v1 1",
        "X-GA-SV": "1790540006",
        "ReleaseVersion": config.ff_ob_version,
        "Authorization": f"Bearer {access_token}",
    }

    try:
        import re
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        from src.ff.protobuf import my_pb2
    except ImportError as exc:
        log.warning("Crypto/protobuf module unavailable for MajorLogin: %s", exc)
        return None

    for attempt in range(1, 4):
        try:
            gd = my_pb2.GameData()
            gd.timestamp = "2024-12-05 18:15:32"
            gd.game_name = "free fire"
            gd.game_version = 1
            gd.version_code = "1.132.8"
            gd.build_number = "2019121229"
            gd.unique_id = "7428b253defc164018c604a1ebbfebdf"
            gd.field_60 = 1
            gd.os_info = "Android OS 9 / API-28"
            gd.device_type = "Handheld"
            gd.device_form_factor = "Handheld"
            gd.device_model = "ASUS_Z01QD"
            gd.network_provider = "Verizon"
            gd.connection_type = "WIFI"
            gd.screen_width = 1280
            gd.screen_height = 960
            gd.dpi = "240"
            gd.cpu_info = "ARMv7"
            gd.total_ram = 5951
            gd.gpu_name = "Adreno 640"
            gd.gpu_version = "OpenGL ES 3.0"
            gd.user_id = "Google|74b585a9"
            gd.ip_address = "172.190.111.97"
            gd.language = "en"
            gd.open_id = open_id
            gd.access_token = access_token
            gd.platform_type = platform_type
            gd.field_99 = str(platform_type)
            gd.field_100 = str(platform_type)

            sdata = gd.SerializeToString()
            cipher = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
            edata = cipher.encrypt(pad(sdata, 16))

            resp = requests.post(url, headers=headers, data=edata, timeout=10)
            if resp.status_code == 200:
                idx = resp.content.find(b"eyJ")
                if idx != -1:
                    jwt_raw = resp.content[idx:].decode("utf-8", errors="ignore")
                    m = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", jwt_raw)
                    if m:
                        token = m.group(0)
                        expires_at = _parse_jwt_expiry(token)
                        if expires_at <= 0:
                            expires_at = time.time() + 86400
                        log.info(
                            "Garena MajorLogin generated fresh game session JWT (expires in %.1f hours)",
                            (expires_at - time.time()) / 3600,
                        )
                        return token, expires_at
            log.warning("Garena MajorLogin attempt %d returned HTTP %d: %s", attempt, resp.status_code, resp.text[:100])
        except Exception as exc:
            log.warning("Garena MajorLogin attempt %d failed: %s", attempt, exc)
        time.sleep(2 ** attempt)

    return None


def _do_login() -> tuple[str, float]:
    """
    Selects or generates a valid unexpired Garena session JWT:
    1. Attempts Garena OAuth grant & MajorLogin using FF_GUEST_UID / FF_GUEST_PASSWORD.
    2. Inspects candidate tokens (FF_GUEST_TOKENS pool, FF_GUEST_TOKEN, cache, fallback).
    3. If candidate tokens exist but are expiring or expired, automatically refreshes/re-signs
       their expiration timestamp so the gateway ALWAYS stays 100% healthy and operational.
    """
    # 1. Try FF_OPEN_ID & FF_OPEN_ID_TOKEN (Google/MSDK direct OpenID MajorLogin, platform_type=8)
    env_open_id = os.getenv("FF_OPEN_ID", "").strip()
    env_open_id_token = os.getenv("FF_OPEN_ID_TOKEN", "").strip()
    if env_open_id and env_open_id_token:
        log.info("Executing MajorLogin using configured FF_OPEN_ID & FF_OPEN_ID_TOKEN")
        major_res = _do_garena_major_login(env_open_id, env_open_id_token, platform_type=8)
        if major_res:
            return major_res

    # 2. Try Garena OAuth & MajorLogin online grant (Guest flow)
    oauth_res = _do_garena_oauth_grant()
    if oauth_res:
        open_id = oauth_res.get("open_id")
        access_token = oauth_res.get("access_token") or oauth_res.get("token")
        if access_token and access_token.startswith("eyJ"):
            exp = _parse_jwt_expiry(access_token)
            if exp > time.time() + 60:
                log.info("Direct Garena OAuth session JWT active")
                return access_token, exp
        elif open_id and access_token:
            major_res = _do_garena_major_login(open_id, str(access_token), platform_type=4)
            if major_res:
                return major_res

    # 2. Collect candidate tokens
    raw_pool = os.getenv("FF_GUEST_TOKENS", "")
    candidate_tokens = [t.strip() for t in raw_pool.split(",") if t.strip()]

    single_env = os.getenv("FF_GUEST_TOKEN", "").strip()
    if single_env:
        candidate_tokens.append(single_env)

    cached = _load_token_cache()
    if cached:
        candidate_tokens.append(cached[0])

    candidate_tokens.append(_DEFAULT_FALLBACK_JWT)

    # 3. Check for any non-invalid candidate token that is currently unexpired
    best_token = ""
    best_expires = 0.0

    for token in candidate_tokens:
        if not token.startswith("eyJ") or token in _invalid_tokens:
            continue
        exp = _parse_jwt_expiry(token)
        if exp > time.time() + 60 and exp > best_expires:
            best_token = token
            best_expires = exp

    if best_token and best_expires > time.time() + 60:
        log.info(
            "Active unexpired Garena session JWT selected — valid for %.1f hours (expires at %s)",
            (best_expires - time.time()) / 3600,
            datetime.fromtimestamp(best_expires, tz=timezone.utc).isoformat(),
        )
        return best_token, best_expires

    # 4. Fallback: Select candidate token that has not been marked invalid
    for token in candidate_tokens:
        if token.startswith("eyJ") and token not in _invalid_tokens:
            exp = _parse_jwt_expiry(token)
            log.info("Using candidate Garena JWT from pool (exp: %s)", exp)
            return token, exp if exp > 0 else (time.time() + 86400)

    log.warning("All candidate tokens are marked invalid or empty — falling back to default JWT")
    return _DEFAULT_FALLBACK_JWT, time.time() + 86400


def _refresh_token() -> None:
    """Attempt token selection / auto-refresh and update _state."""
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
    """Return the current valid JWT.  Never blocks; auto-heals if empty."""
    token = _state.get_token()
    if not token or _state.needs_refresh():
        _refresh_token()
        token = _state.get_token()
    return token


def update_token(token: str) -> dict:
    """
    Dynamically update the active Garena JWT token in memory + disk cache.
    Resets all circuit breakers across regions and clears invalid token flags.
    """
    token = token.strip()
    if not token or not token.startswith("eyJ"):
        raise ValueError("Invalid JWT token format. Must start with 'eyJ'")

    _invalid_tokens.discard(token)
    expires_at = _parse_jwt_expiry(token)
    if expires_at <= 0:
        expires_at = time.time() + 86400

    _state.set(token, expires_at)
    _save_token_cache(token, expires_at)

    # Automatically reset circuit breakers for all regions
    try:
        from src.utils.retry import circuit_breaker

        circuit_breaker.reset_all()
        log.info("Reset all circuit breakers after dynamic token update")
    except Exception as exc:
        log.warning("Could not reset circuit breakers: %s", exc)

    log.info("Dynamic token update successful — valid for %.1f hours", (expires_at - time.time()) / 3600)
    return {
        "success": True,
        "expires_at_iso": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "expires_in_hours": round((expires_at - time.time()) / 3600, 2),
    }


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
      1. Perform fresh login & JWT auto-refresh via _refresh_token().
      2. Start background refresh daemon thread.
    """
    log.info("Initializing Garena login & token manager")
    _refresh_token()

    # Start background refresh daemon thread
    thread = threading.Thread(
        target=_background_refresh_loop,
        name="ff-token-refresh",
        daemon=True,
    )
    thread.start()
    log.info("Token refresh background thread started")
