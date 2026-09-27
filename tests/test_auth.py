"""test_auth.py — Token manager unit tests."""

import base64
import json
import time

import pytest


def test_parse_jwt_expiry_valid():
    """parse_jwt_expiry should correctly extract exp from a real-looking JWT."""
    payload = {"exp": int(time.time()) + 3600, "account_id": 123}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_token = f"header.{b64}.signature"

    from src.ff.auth import _parse_jwt_expiry

    exp = _parse_jwt_expiry(fake_token)
    assert abs(exp - payload["exp"]) < 2


def test_parse_jwt_expiry_bad_token():
    """parse_jwt_expiry should return ~6 months for garbage tokens."""
    from src.ff.auth import _parse_jwt_expiry

    future = time.time() + 60 * 60 * 24 * 175  # slightly less than 6 months
    exp = _parse_jwt_expiry("garbage.token.value")
    assert exp > future


def test_auto_refresh_jwt_expired_token():
    """_auto_refresh_jwt should automatically update payload exp for an expired token."""
    from src.ff.auth import _auto_refresh_jwt, _parse_jwt_expiry

    past_exp = int(time.time()) - 3600  # expired 1 hour ago
    payload = {"account_id": 999, "exp": past_exp}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    expired_token = f"eyJhbGciOiJIUzI1NiJ9.{b64}.sig"

    refreshed_token, new_exp = _auto_refresh_jwt(expired_token)
    assert new_exp > time.time() + 86400  # valid in future
    parsed_exp = _parse_jwt_expiry(refreshed_token)
    assert parsed_exp > time.time() + 86400


def test_token_state_needs_refresh_when_empty():
    from src.ff.auth import _TokenState

    state = _TokenState()
    assert state.needs_refresh() is True


def test_token_state_healthy_after_set():
    from src.ff.auth import _TokenState

    state = _TokenState()
    state.set("mytoken", time.time() + 3600)
    assert state.health_status() == "healthy"
    assert state.needs_refresh() is False
    assert state.get_token() == "mytoken"


def test_token_state_degraded_after_3_failures():
    from src.ff.auth import _TokenState

    state = _TokenState()
    state.set("token", time.time() + 3600)
    state.record_failure()
    state.record_failure()
    assert state.health_status() == "healthy"
    state.record_failure()
    assert state.health_status() == "degraded"
    assert state.is_degraded is True


def test_token_state_recovers_after_set():
    from src.ff.auth import _TokenState

    state = _TokenState()
    state.record_failure()
    state.record_failure()
    state.record_failure()
    assert state.is_degraded is True
    state.set("fresh_token", time.time() + 7200)
    assert state.is_degraded is False
    assert state.consecutive_failures == 0
