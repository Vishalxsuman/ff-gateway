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
    """mark_token_invalid should evict a rejected session from active state."""
    from src.ff.auth import mark_token_invalid, _invalid_tokens, update_token, get_token

    payload = {"exp": int(time.time()) + 3600}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    bad_token = f"eyJhbGciOiJIUzI1NiJ9.{encoded}.sig"
    update_token(bad_token)
    mark_token_invalid(bad_token)
    assert bad_token in _invalid_tokens
    assert get_token() == ""


def test_gateway_fails_closed_without_authorized_token_source(monkeypatch):
    from src.ff import auth

    monkeypatch.delenv("FF_SESSION_JWT", raising=False)
    monkeypatch.delenv("FF_TOKEN_PROVIDER_URL", raising=False)
    monkeypatch.delenv("FF_TOKEN_PROVIDER_SECRET", raising=False)
    monkeypatch.setattr(auth, "_token", "")
    monkeypatch.setattr(auth, "_expires_at", 0.0)

    assert auth.get_token() == ""
    assert auth.health_status() == "unhealthy"


def test_update_token_rejects_expired_token():
    from src.ff.auth import update_token

    payload = {"exp": int(time.time()) - 60}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(ValueError):
        update_token(f"eyJhbGciOiJIUzI1NiJ9.{encoded}.sig")
