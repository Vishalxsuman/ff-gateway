# -*- coding: utf-8 -*-
"""
regions.py — All Garena regional endpoint mappings in one place.

To add a new region or update a URL, change only this file.
The OB version header is injected from config, NOT hardcoded here.
"""

from typing import NamedTuple


class RegionConfig(NamedTuple):
    code: str
    name: str
    gateway_host: str
    player_show_path: str = "/GetPlayerPersonalShow"

    @property
    def player_show_url(self) -> str:
        return f"{self.gateway_host}{self.player_show_path}"


# ── Region definitions ────────────────────────────────────────────────────────
# Source: reverse-engineered from FF game client (OB55, verified)
# Update gateway_host when Garena rotates cluster addresses.

REGIONS: dict[str, RegionConfig] = {
    "IND": RegionConfig(
        code="IND",
        name="India",
        gateway_host="https://client.ind.freefiremobile.com",
    ),
    "BD": RegionConfig(
        code="BD",
        name="Bangladesh",
        gateway_host="https://client.ind.freefiremobile.com",
    ),
    "PK": RegionConfig(
        code="PK",
        name="Pakistan",
        gateway_host="https://client.ind.freefiremobile.com",
    ),
    "ME": RegionConfig(
        code="ME",
        name="Middle East",
        gateway_host="https://client.ind.freefiremobile.com",
    ),
    "EG": RegionConfig(
        code="EG",
        name="Egypt",
        gateway_host="https://client.ind.freefiremobile.com",
    ),
    "TH": RegionConfig(
        code="TH",
        name="Thailand",
        gateway_host="https://clientbp.th.freefiremobile.com",
    ),
    "VN": RegionConfig(
        code="VN",
        name="Vietnam",
        gateway_host="https://client.vn.freefiremobile.com",
    ),
    "ID": RegionConfig(
        code="ID",
        name="Indonesia",
        gateway_host="https://client.id.freefiremobile.com",
    ),
    "BR": RegionConfig(
        code="BR",
        name="Brazil",
        gateway_host="https://client.us.freefiremobile.com",
    ),
    "SAC": RegionConfig(
        code="SAC",
        name="South America",
        gateway_host="https://clientbp.us.freefiremobile.com",
    ),
    "SG": RegionConfig(
        code="SG",
        name="Singapore / SEA",
        gateway_host="https://clientbp.ggpolarbear.com",
    ),
}

DEFAULT_REGION = "IND"
SUPPORTED_REGION_CODES: list[str] = sorted(REGIONS.keys())


def get_region(code: str) -> RegionConfig:
    """Return RegionConfig for the given code, falling back to IND."""
    return REGIONS.get(code.upper(), REGIONS[DEFAULT_REGION])


def is_supported(code: str) -> bool:
    return code.upper() in REGIONS
