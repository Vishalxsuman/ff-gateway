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
    """parse_jwt_expiry should return 0.0 for garbage tokens."""
    from src.ff.auth import _parse_jwt_expiry

    exp = _parse_jwt_expiry("garbage.token.value")
    assert exp == 0.0


def test_mark_token_invalid():
    """mark_token_invalid should flag rejected tokens and prevent selection in pool."""
    from src.ff.auth import mark_token_invalid, _invalid_tokens, _do_login

    bad_token = "eyJhbGciOiJIUzI1NiJ9.eyJhY2NvdW50X2lkIjo5OTksImV4cCI6MjA0ODU1MjYyM30.sig"
    mark_token_invalid(bad_token)
    assert bad_token in _invalid_tokens


def test_token_state_needs_refresh_when_empty():
    from src.ff.auth import _TokenState

    state = _TokenState()
    assert state.needs_refresh() is True


def test_token_state_healthy_after_set():
    from src.ff.auth import _TokenState

    state = _TokenState()
    state.set("mytoken", time.time() + 7200)
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
