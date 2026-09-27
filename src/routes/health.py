# -*- coding: utf-8 -*-
"""health.py — /health endpoint."""

import time

from flask import Blueprint, jsonify

from src.ff import auth
from src.ff.regions import SUPPORTED_REGION_CODES
from src.utils.retry import circuit_breaker

health_bp = Blueprint("health", __name__)

_START_TIME = time.time()


@health_bp.route("/health")
def health():
    auth_snap = auth.health_info()
    auth_status = auth.health_status()

    # Aggregate circuit breaker states
    cb_states = {
        f"garena:{r}": circuit_breaker.state(f"garena:{r}")
        for r in SUPPORTED_REGION_CODES
    }
    any_open = any(s == "OPEN" for s in cb_states.values())

    if auth_status == "unhealthy":
        overall = "unhealthy"
    elif auth_status == "degraded" or any_open:
        overall = "degraded"
    else:
        overall = "healthy"

    http_status = 200 if overall in ("healthy", "degraded") else 503

    payload = {
        "status": overall,
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "token_age_seconds": auth_snap["age_seconds"],
        "token_expires_in_seconds": auth_snap["expires_in_seconds"],
        "last_refresh": auth_snap["last_refresh"],
        "consecutive_token_failures": auth_snap["consecutive_failures"],
        "region_support": SUPPORTED_REGION_CODES,
        "circuit_breakers": cb_states,
    }
    return jsonify(payload), http_status


@health_bp.route("/token/update", methods=["POST"])
@health_bp.route("/admin/token", methods=["POST"])
def update_token_route():
    from flask import request
    data = request.get_json(silent=True) or {}
    token = data.get("token") or request.form.get("token") or ""

    if not token:
        return jsonify({"success": False, "error": "Missing 'token' in request body"}), 400

    try:
        res = auth.update_token(token)
        return jsonify(res), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Failed to update token: {exc}"}), 500

