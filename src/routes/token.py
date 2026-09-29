"""Readiness and protected update routes for authorized session tokens."""

import hmac
import os

from flask import Blueprint, jsonify, request

from src.ff import auth

token_bp = Blueprint("token", __name__)


@token_bp.route("/token/status")
@token_bp.route("/admin/token/status")
def get_token_status():
    snapshot = auth.health_info()
    token = auth.get_token()
    return jsonify({
        "success": True,
        "status": auth.health_status(),
        "has_token": bool(token),
        "expires_in_seconds": snapshot["expires_in_seconds"],
        "details": snapshot,
    })


@token_bp.route("/token/update", methods=["POST"])
@token_bp.route("/admin/token", methods=["POST"])
def update_token():
    update_key = os.getenv("FF_TOKEN_UPDATE_KEY", "").strip()
    provided_key = request.headers.get("X-FF-Token-Update-Key", "").strip()
    if not update_key or not provided_key or not hmac.compare_digest(update_key, provided_key):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or data.get("jwt") or "").strip()
    if not token:
        return jsonify({"success": False, "error": "Missing token"}), 400

    try:
        return jsonify(auth.update_token(token)), 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400