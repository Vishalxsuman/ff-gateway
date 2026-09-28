"""test_token.py — Token update endpoint unit tests."""

import time
import base64
import json


def test_token_update_success():
    from src.app import create_app

    app = create_app()
    client = app.test_client()

    payload = {"exp": int(time.time()) + 7200, "account_id": 8888}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_jwt = f"eyJhbGciOiJIUzI1NiJ9.{b64}.sig"

    res = client.post("/token/update", json={"token": fake_jwt, "skip_verify": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True


def test_token_update_missing():
    from src.app import create_app

    app = create_app()
    client = app.test_client()

    res = client.post("/token/update", json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
