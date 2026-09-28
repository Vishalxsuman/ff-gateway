# -*- coding: utf-8 -*-
"""
token.py — Token management and JWT generation routes.

Endpoints:
  - GET /token/status : Token health, expiry, and state
  - POST /token/update : Dynamically upload and verify a new Garena session JWT
  - GET /access-jwt, POST /access-jwt : Generate Garena session JWT given access_token (and optional open_id)
  - GET /token, POST /token : Generate Garena session JWT given guest uid and password
"""

from flask import Blueprint, jsonify, request

from src.core.logger import get_logger
from src.ff import auth, client

log = get_logger(__name__)

token_bp = Blueprint("token", __name__)


@token_bp.route("/token/status", methods=["GET"])
@token_bp.route("/admin/token/status", methods=["GET"])
def get_token_status():
    snap = auth.health_info()
    token = auth.get_token()
    exp = auth._parse_jwt_expiry(token) if token else 0.0
    return jsonify({
        "success": True,
        "status": auth.health_status(),
        "has_token": bool(token),
        "expires_in_hours": round(snap.get("expires_in_seconds", 0) / 3600, 2),
        "expires_at_iso": auth.datetime.fromtimestamp(exp, tz=auth.timezone.utc).isoformat() if exp > 0 else None,
        "details": snap,
    })


@token_bp.route("/access-jwt", methods=["GET", "POST"])
def access_jwt():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        access_token = (data.get("access_token") or data.get("token") or "").strip()
        open_id = (data.get("open_id") or "").strip() or None
    else:
        access_token = (request.args.get("access_token") or request.args.get("token") or "").strip()
        open_id = (request.args.get("open_id") or "").strip() or None

    if not access_token:
        return jsonify({"message": "missing access_token"}), 400

    result, err = auth.generate_jwt_from_access_token(access_token, open_id)
    if err or not result:
        return jsonify({"message": err or "Failed to generate JWT"}), 400

    return jsonify(result), 200


@token_bp.route("/token", methods=["GET", "POST"])
def oauth_guest_token():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        uid = (data.get("uid") or "").strip() or None
        password = (data.get("password") or "").strip() or None
        access_token = (data.get("access_token") or "").strip() or None
        open_id = (data.get("open_id") or "").strip() or None
    else:
        uid = (request.args.get("uid") or "").strip() or None
        password = (request.args.get("password") or "").strip() or None
        access_token = (request.args.get("access_token") or "").strip() or None
        open_id = (request.args.get("open_id") or "").strip() or None

    if access_token:
        result, err = auth.generate_jwt_from_access_token(access_token, open_id)
    else:
        result, err = auth.generate_jwt_from_guest(uid, password)

    if err or not result:
        return jsonify({"message": err or "Failed to generate guest JWT"}), 400

    return jsonify(result), 200


@token_bp.route("/token/update", methods=["POST", "OPTIONS"])
@token_bp.route("/admin/token", methods=["POST", "OPTIONS"])
def update_token():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    token = (data.get("token") or data.get("jwt") or data.get("access_token") or "").strip()
    skip_verify = bool(data.get("skip_verify", False))

    if not token:
        return jsonify({"success": False, "error": "Missing token payload. Provide 'token' field in JSON."}), 400

    if not token.startswith("eyJ"):
        return jsonify({"success": False, "error": "Invalid JWT token format. Must start with 'eyJ'."}), 400

    # 1. Live Garena verification check
    if not skip_verify:
        is_valid, msg, _ = client.verify_token(token)
        if not is_valid:
            log.warning("Token verification failed during update: %s", msg)
            return jsonify({
                "success": False,
                "verified": False,
                "error": f"Garena Verification Failed: {msg}",
            }), 400

    # 2. If verified, save to global server state
    try:
        res = auth.update_token(token)
        res["verified"] = True
        res["message"] = "Token verified live against Garena servers and saved to global gateway state."
        return jsonify(res), 200
    except Exception as exc:
        log.error("Failed to update token: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500

