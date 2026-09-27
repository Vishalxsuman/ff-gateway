# -*- coding: utf-8 -*-
"""
token.py — Token management route.

Allows updating the active Garena session JWT token via POST /token/update.
"""

from flask import Blueprint, jsonify, request

from src.core.logger import get_logger
from src.ff import auth

log = get_logger(__name__)

token_bp = Blueprint("token", __name__)


@token_bp.route("/token/update", methods=["POST", "OPTIONS"])
@token_bp.route("/admin/token", methods=["POST", "OPTIONS"])
def update_token():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or data.get("jwt") or data.get("access_token") or "").strip()

    if not token:
        return jsonify({"success": False, "error": "Missing token payload. Provide 'token' field in JSON."}), 400

    if not token.startswith("eyJ"):
        return jsonify({"success": False, "error": "Invalid JWT token format. Must start with 'eyJ'."}), 400

    try:
        res = auth.update_token(token)
        return jsonify(res), 200
    except Exception as exc:
        log.error("Failed to update token: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
