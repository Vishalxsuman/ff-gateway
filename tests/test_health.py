"""test_health.py — Health endpoint unit tests."""

import time

import pytest

from src.app import create_app


@pytest.fixture()
def client(monkeypatch):
    # Stub auth so no real Garena call is made
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

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_json_structure(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "token_age_seconds" in data
    assert "token_expires_in_seconds" in data
    assert "last_refresh" in data
    assert "region_support" in data
    assert isinstance(data["region_support"], list)
    assert "IND" in data["region_support"]


def test_health_status_healthy(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert data["status"] == "healthy"


def test_health_uptime_positive(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert data["uptime_seconds"] >= 0
