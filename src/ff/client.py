# -*- coding: utf-8 -*-
"""
client.py — Garena API client.

Handles:
  - Protobuf serialization of the request
  - AES-128-CBC encryption
  - HTTP POST to the correct regional endpoint
  - Protobuf deserialization of the response
  - Structured JSON output to the caller
  - Retry + circuit breaker (delegated to retry.py)
"""

import binascii
import sys
import os
import time
from typing import Any

import requests
from google.protobuf.json_format import MessageToDict

from src.core.config import config
from src.core.logger import get_logger
from src.ff import auth
from src.ff.crypto import encrypt_payload, serialize_uid_request
from src.ff.regions import get_region
from src.utils.retry import with_retry, CircuitOpenError

# Ensure protobuf path
_proto_dir = os.path.join(os.path.dirname(__file__), "protobuf")
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from src.ff.protobuf import data_pb2  # noqa: E402

log = get_logger(__name__)

_CDN_ICON_BASE = "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG"


def _build_headers(token: str) -> dict[str, str]:
    return {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        "Authorization": f"Bearer {token}",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": config.ff_ob_version,
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "Keep-Alive",
    }


def _call_garena(uid: int, region: str) -> dict[str, Any]:
    """Single attempt to call Garena — no retry logic here (handled by decorator)."""
    token = auth.get_token()
    if not token:
        raise RuntimeError("No valid JWT token available. Gateway is not yet authenticated.")

    region_cfg = get_region(region)
    url = region_cfg.player_show_url

    # Serialize → encrypt
    hex_payload = serialize_uid_request(uid)
    encrypted_body = encrypt_payload(hex_payload)

    headers = _build_headers(token)

    log.info("POST %s uid=%d region=%s", url, uid, region)
    t0 = time.monotonic()

    resp = requests.post(
        url,
        headers=headers,
        data=encrypted_body,
        timeout=config.garena_timeout_seconds,
    )

    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    log.info(
        "Garena responded HTTP %d in %.1f ms (uid=%d region=%s)",
        resp.status_code,
        latency_ms,
        uid,
        region,
    )

    if resp.status_code != 200:
        error_text = resp.text.strip()[:200] or f"HTTP {resp.status_code}"
        if resp.status_code in (401, 403):
            auth.mark_token_invalid(token)
            log.warning("Garena Auth Token rejected (HTTP %d): %s. Token evicted from pool.", resp.status_code, error_text)
        raise RuntimeError(f"Garena HTTP {resp.status_code}: {error_text}")

    pb = data_pb2.AccountPersonalShowInfo()
    pb.ParseFromString(resp.content)
    return MessageToDict(pb, preserving_proto_field_name=True)


def _format_response(raw: dict[str, Any], uid: str, region: str) -> dict[str, Any]:
    """Transform raw protobuf dict into the Esporizon-standard response schema."""
    basic = raw.get("basic_info", {})
    clan = raw.get("clan_basic_info", {})
    captain = raw.get("captain_basic_info", {})
    pet = raw.get("pet_info", {})
    social = raw.get("social_info", {})
    profile = raw.get("profile_info", {})
    credit = raw.get("credit_score_info", {})
    diamond = raw.get("diamond_cost_res", {})

    avatar_id = str(basic.get("head_pic", "902000270"))
    banner_id = str(basic.get("banner_id", "901000257"))

    credit_score = credit.get("score", 100)
    credit_reason = credit.get("reason", 2)

    _reason_map = {
        1: "Standard Weekly Credit Maintenance",
        2: "Clean Match Streak / Active Weekly Behavior Reward",
        3: "AFK / Early Exit Infraction Penalty",
        4: "Griefing / Negative Behavior Violation",
        5: "Tournament Fair-Play Verification Clearance",
    }

    credit_info = {
        "score": credit_score,
        "max_score": 100,
        "status": (
            "PERFECT" if credit_score == 100
            else "HEALTHY" if credit_score >= 90
            else "RESTRICTED" if credit_score >= 80
            else "PROBATION"
        ),
        "is_tournament_eligible": credit_score >= 90,
        "is_cs_rank_eligible": credit_score >= 80,
        "is_br_rank_eligible": credit_score >= 60,
        "reason_code": credit_reason,
        "reason_description": _reason_map.get(credit_reason, "Active Integrity Verification"),
        "cycle_start": credit.get("start"),
        "cycle_end": credit.get("end"),
    }

    basic_info = {
        "nickname": basic.get("nickname", "Unknown"),
        "level": basic.get("level", 1),
        "exp": basic.get("exp", 0),
        "likes": basic.get("liked", 0),
        "signature": social.get("social_highlight", ""),
        "avatar_id": avatar_id,
        "avatar_url": f"{_CDN_ICON_BASE}/{avatar_id}.png",
        "banner_id": banner_id,
        "banner_url": f"{_CDN_ICON_BASE}/{banner_id}.png",
        "badge_count": basic.get("badge_cnt", 0),
        "badge_id": basic.get("badge_id", 1001000100),
        "created_at": basic.get("create_at"),
        "last_login_at": basic.get("last_login_at"),
        "title": basic.get("title"),
        "season_id": basic.get("season_id", 53),
        "release_version": basic.get("release_version", config.ff_ob_version),
        "has_elite_pass": basic.get("has_elite_pass", False),
    }

    rank_info = {
        "br_rank": basic.get("rank", 0),
        "br_ranking_points": basic.get("ranking_points", 0),
        "br_max_rank": basic.get("max_rank", basic.get("rank", 0)),
        "show_br_rank": basic.get("show_br_rank", True),
        "cs_rank": basic.get("cs_rank", 0),
        "cs_ranking_points": basic.get("cs_ranking_points", 0),
        "cs_max_rank": basic.get("cs_max_rank", basic.get("cs_rank", 0)),
        "show_cs_rank": basic.get("show_cs_rank", True),
        "hippo_rank": basic.get("hippo_rank", 0),
        "hippo_ranking_points": basic.get("hippo_ranking_points", 0),
    }

    clan_info = (
        {
            "clan_id": str(clan.get("clan_id", "")),
            "clan_name": clan.get("clan_name", "None"),
            "clan_level": clan.get("clan_level", 0),
            "current_members": clan.get("current_members", 0),
            "max_members": clan.get("max_members", 50),
            "captain_id": str(clan.get("captain_id", "")),
        }
        if clan
        else None
    )

    captain_info = (
        {
            "account_id": str(captain.get("account_id", "")),
            "nickname": captain.get("nickname", ""),
            "level": captain.get("level", 1),
            "rank": captain.get("rank", 0),
            "ranking_points": captain.get("ranking_points", 0),
            "cs_rank": captain.get("cs_rank", 0),
            "avatar_url": f"{_CDN_ICON_BASE}/{captain.get('head_pic', 902000257)}.png",
        }
        if captain and captain.get("account_id")
        else None
    )

    pet_info = (
        {
            "pet_id": str(pet.get("pet_id", "")),
            "name": pet.get("pet_name", "Companion"),
            "level": pet.get("level", 1),
            "exp": pet.get("exp", 0),
            "skin_id": str(pet.get("skin_id", "")),
            "selected_skill_id": str(pet.get("selected_skill_id", "")),
            "is_selected": pet.get("is_selected", True),
        }
        if pet
        else None
    )

    social_info = {
        "gender": str(social.get("gender", "GENDER_UNKNOWN")).replace("GENDER_", ""),
        "language": str(social.get("language", "LANGUAGE_ENGLISH")).replace("LANGUAGE_", ""),
        "privacy": str(social.get("privacy", "PRIVACY_FRIENDS_ONLY")).replace("PRIVACY_", ""),
        "highlight": social.get("social_highlight", ""),
    }

    skills = [
        {
            "slot_index": s.get("slot_index", 0),
            "skill_id": str(s.get("skill_id", "")),
            "icon_url": f"{_CDN_ICON_BASE}/{s.get('skill_id', '')}.png",
        }
        for s in profile.get("skill_slots", [])
    ]

    weapons = [
        {
            "id": str(w),
            "icon_url": f"{_CDN_ICON_BASE}/{w}.png",
        }
        for w in basic.get("weapon_skin_shows", [])
    ]

    return {
        "uid": str(basic.get("account_id", uid)),
        "region": region,
        "basic_info": basic_info,
        "rank_info": rank_info,
        "clan_info": clan_info,
        "captain_info": captain_info,
        "pet_info": pet_info,
        "social_info": social_info,
        "credit_score_info": credit_info,
        "equipped_skills": skills,
        "weapon_skins": weapons,
        "diamond_cost": diamond.get("diamond_cost", 0),
    }


def fetch_player(uid: int, region: str) -> dict[str, Any]:
    """
    Public entry point.  Fetches player data with retry + circuit breaker.
    Raises RuntimeError or CircuitOpenError on unrecoverable failure.
    """
    circuit_key = f"garena:{region.upper()}"

    @with_retry(
        max_attempts=config.garena_max_retries + 1,
        base_delay=1.0,
        circuit_key=circuit_key,
    )
    def _retried_call() -> dict[str, Any]:
        return _call_garena(uid, region)

    raw = _retried_call()
    return _format_response(raw, str(uid), region.upper())
