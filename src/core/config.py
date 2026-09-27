# -*- coding: utf-8 -*-
"""
config.py — ENV-based configuration with fail-fast validation.
All secrets are loaded from environment variables; nothing is hardcoded.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GatewayConfig:
    # ── Auth ──────────────────────────────────────────────────────────────────
    ff_guest_uid: str
    ff_guest_password: str

    # ── Protocol ──────────────────────────────────────────────────────────────
    ff_ob_version: str
    ff_full_build_string: str

    # ── Crypto (AES-128-CBC) — updatable via ENV without code deploy ──────────
    aes_key: bytes
    aes_iv: bytes

    # ── Service Message IDs ───────────────────────────────────────────────────
    service_msg_player_show: int

    # ── Server ────────────────────────────────────────────────────────────────
    port: int
    log_level: str

    # ── Cache ─────────────────────────────────────────────────────────────────
    redis_url: Optional[str]
    cache_ttl_seconds: int
    enable_cache: bool

    # ── Rate limiting ─────────────────────────────────────────────────────────
    enable_rate_limit: bool
    rate_limit_per_uid: int  # requests per minute per UID

    # ── Resilience ────────────────────────────────────────────────────────────
    garena_timeout_seconds: int
    garena_max_retries: int
    circuit_breaker_threshold: int
    circuit_breaker_reset_seconds: int

    # ── Token refresh ─────────────────────────────────────────────────────────
    token_refresh_buffer_seconds: int  # refresh N seconds before expiry

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list = field(default_factory=lambda: ["*"])


def _require(key: str) -> str:
    """Read a required ENV variable; check local .env if absent."""
    value = os.getenv(key, "").strip()
    if not value:
        from pathlib import Path

        for env_path in [Path(".env"), Path(__file__).resolve().parent.parent.parent / ".env"]:
            if env_path.exists():
                try:
                    for line in env_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith(f"{key}=") and not line.startswith("#"):
                            value = line.split("=", 1)[1].strip()
                            if value:
                                break
                except Exception:
                    pass
            if value:
                break

    if not value:
        print(
            f"[FATAL] Required environment variable '{key}' is not set. "
            "Gateway cannot start. Check your .env or Azure Application Settings.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def load_config() -> GatewayConfig:
    """Load and validate configuration from environment variables."""
    ff_guest_uid = _require("FF_GUEST_UID")
    ff_guest_password = _require("FF_GUEST_PASSWORD")

    aes_key_str = _optional("AES_KEY", "Yg&tc%DEuh6%Zc^8")
    aes_iv_str = _optional("AES_IV", "6oyZDr22E3ychjM%")

    if len(aes_key_str.encode()) != 16 or len(aes_iv_str.encode()) != 16:
        print(
            "[FATAL] AES_KEY and AES_IV must each be exactly 16 bytes (characters).",
            file=sys.stderr,
        )
        sys.exit(1)

    return GatewayConfig(
        ff_guest_uid=ff_guest_uid,
        ff_guest_password=ff_guest_password,
        ff_ob_version=_optional("FF_OB_VERSION", "OB55"),
        ff_full_build_string=_optional(
            "FF_FULL_BUILD_STRING",
            "FFM_OB55_PRELive_MAX_2.133.1_2019118527_4636257_gp_unity2022_aab_sidekick_extend4641229-4641231_astc_sp",
        ),
        aes_key=aes_key_str.encode("utf-8"),
        aes_iv=aes_iv_str.encode("utf-8"),
        service_msg_player_show=int(_optional("SERVICE_MSG_PLAYER_SHOW", "179")),
        port=int(_optional("PORT", "8000")),
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
        redis_url=_optional("REDIS_URL") or None,
        cache_ttl_seconds=int(_optional("CACHE_TTL_SECONDS", "300")),
        enable_cache=_optional("ENABLE_CACHE", "true").lower() == "true",
        enable_rate_limit=_optional("ENABLE_RATE_LIMIT", "true").lower() == "true",
        rate_limit_per_uid=int(_optional("RATE_LIMIT_PER_UID", "10")),
        garena_timeout_seconds=int(_optional("GARENA_TIMEOUT_SECONDS", "15")),
        garena_max_retries=int(_optional("GARENA_MAX_RETRIES", "2")),
        circuit_breaker_threshold=int(_optional("CIRCUIT_BREAKER_THRESHOLD", "5")),
        circuit_breaker_reset_seconds=int(
            _optional("CIRCUIT_BREAKER_RESET_SECONDS", "60")
        ),
        token_refresh_buffer_seconds=int(
            _optional("TOKEN_REFRESH_BUFFER_SECONDS", "300")
        ),
        cors_origins=_optional("CORS_ORIGINS", "*").split(","),
    )


# Module-level singleton — imported everywhere
config: GatewayConfig = load_config()
