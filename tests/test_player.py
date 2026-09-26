"""test_player.py — Player endpoint integration tests (Garena mocked)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_GARENA_RAW = {
    "basic_info": {
        "account_id": 1036762440,
        "nickname": "TestPlayer",
        "level": 45,
        "exp": 123456,
        "liked": 100,
        "rank": 300,
        "ranking_points": 4200,
        "cs_rank": 200,
        "cs_ranking_points": 2100,
        "head_pic": 902000270,
        "banner_id": 901000257,
        "badge_cnt": 5,
        "badge_id": 1001000100,
        "create_at": 1580000000,
        "last_login_at": 1727000000,
        "has_elite_pass": True,
        "season_id": 53,
        "release_version": "OB55",
        "weapon_skin_shows": [907007001],
    },
    "social_info": {
        "gender": "GENDER_MALE",
        "language": "LANGUAGE_ENGLISH",
        "privacy": "PRIVACY_FRIENDS_ONLY",
        "social_highlight": "Esporizon Verified",
    },
    "credit_score_info": {"score": 100, "reason": 2, "start": 1725000000, "end": 1727600000},
    "clan_basic_info": {
        "clan_id": 3001234567,
        "clan_name": "EliteSquad",
        "clan_level": 5,
        "current_members": 30,
        "max_members": 50,
        "captain_id": 9876543210,
    },
}


@pytest.fixture()
def client(monkeypatch):
    import src.ff.auth as auth_module
    import src.core.cache as cache_module

    monkeypatch.setattr(auth_module, "initialize", lambda: None)
    monkeypatch.setattr(cache_module, "_init", lambda: None)
    monkeypatch.setattr(auth_module, "get_token", lambda: "stub_token")
    monkeypatch.setattr(
        auth_module,
        "health_info",
        lambda: {
            "age_seconds": 60.0,
            "expires_in_seconds": 86000.0,
            "last_refresh": "2026-09-26T10:00:00+00:00",
            "consecutive_failures": 0,
            "is_degraded": False,
        },
    )
    monkeypatch.setattr(auth_module, "health_status", lambda: "healthy")

    from src.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_player_missing_uid(client):
    """Route requires uid in path — missing uid hits 404."""
    resp = client.get("/player/")
    assert resp.status_code == 404


def test_player_invalid_uid(client):
    resp = client.get("/player/abc?region=IND")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "Invalid UID" in data["error"]


def test_player_uid_too_short(client):
    resp = client.get("/player/123?region=IND")
    assert resp.status_code == 400


def test_player_live_fetch_success(client):
    """Mock fetch_player and verify response shape."""
    from src.ff import client as ff_client

    mock_data = ff_client._format_response(SAMPLE_GARENA_RAW, "1036762440", "IND")

    with patch("src.routes.player.client.fetch_player", return_value=mock_data):
        resp = client.get("/player/1036762440?region=IND")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["cached"] is False
    assert "basic_info" in data
    assert data["basic_info"]["nickname"] == "TestPlayer"
    assert data["basic_info"]["level"] == 45


def test_player_cache_hit(client, monkeypatch):
    """If cache returns data, Garena is never called."""
    from src.ff import client as ff_client

    cached = ff_client._format_response(SAMPLE_GARENA_RAW, "1036762440", "IND")
    cached["_fetched_at"] = "2026-09-26T10:00:00+00:00"

    monkeypatch.setattr("src.routes.player.cache_get", lambda r, u: cached)

    with patch("src.routes.player.client.fetch_player") as mock_fetch:
        resp = client.get("/player/1036762440?region=IND")
        mock_fetch.assert_not_called()

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cached"] is True


def test_player_garena_502(client):
    """Garena RuntimeError should return 502."""
    with patch(
        "src.routes.player.client.fetch_player",
        side_effect=RuntimeError("Garena HTTP 503: Service Unavailable"),
    ):
        resp = client.get("/player/1036762440?region=IND")

    assert resp.status_code == 502
    data = resp.get_json()
    assert data["success"] is False


def test_player_circuit_open_503(client):
    """CircuitOpenError should return 503."""
    from src.utils.retry import CircuitOpenError

    with patch(
        "src.routes.player.client.fetch_player",
        side_effect=CircuitOpenError("Circuit is OPEN"),
    ):
        resp = client.get("/player/1036762440?region=IND")

    assert resp.status_code == 503
    data = resp.get_json()
    assert data["success"] is False


def test_format_response_structure():
    """Unit test for _format_response without HTTP layer."""
    from src.ff.client import _format_response

    result = _format_response(SAMPLE_GARENA_RAW, "1036762440", "IND")

    assert result["uid"] == "1036762440"
    assert result["region"] == "IND"
    assert result["basic_info"]["nickname"] == "TestPlayer"
    assert result["basic_info"]["level"] == 45
    assert result["credit_score_info"]["score"] == 100
    assert result["credit_score_info"]["status"] == "PERFECT"
    assert result["credit_score_info"]["is_tournament_eligible"] is True
    assert result["clan_info"]["clan_name"] == "EliteSquad"
    assert result["social_info"]["gender"] == "MALE"
    assert len(result["weapon_skins"]) == 1
