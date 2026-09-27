# -*- coding: utf-8 -*-
"""
app.py — Flask application factory and entry point.

Cold-start-safe: all heavy initialization happens in create_app() so
gunicorn workers don't race each other on startup.
"""

import uuid

from flask import Flask, jsonify, request

from src.core import cache as cache_module
from src.core.config import config
from src.core.logger import setup_logging, get_logger
from src.ff import auth
from src.routes.health import health_bp
from src.routes.player import player_bp
from src.routes.token import token_bp
from src.routes.version import version_bp

log = get_logger(__name__)


def create_app() -> Flask:
    setup_logging()
    log.info("Initializing FF Gateway (OB version: %s)", config.ff_ob_version)

    # Initialize cache (connects to Redis if configured)
    cache_module._init()

    # Initialize token manager (loads/fetches JWT, starts refresh thread)
    auth.initialize()

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # ── CORS ──────────────────────────────────────────────────────────────────
    @app.after_request
    def add_cors(response):
        origins = ", ".join(config.cors_origins)
        response.headers["Access-Control-Allow-Origin"] = origins
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Request-ID"
        )
        return response

    # ── Request ID injection ──────────────────────────────────────────────────
    @app.before_request
    def inject_request_id():
        if "X-Request-ID" not in request.headers:
            request.environ["HTTP_X_REQUEST_ID"] = str(uuid.uuid4())[:8]

    # ── Blueprints ────────────────────────────────────────────────────────────
    app.register_blueprint(health_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(token_bp)
    app.register_blueprint(version_bp)

    # ── 404 / 405 handlers ───────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "status": 404}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed", "status": 405}), 405

    @app.errorhandler(500)
    def internal_error(e):
        log.exception("Unhandled 500 error")
        return jsonify({"error": "Internal server error", "status": 500}), 500

    log.info("FF Gateway ready on port %d", config.port)
    return app


# Gunicorn entry point: `gunicorn src.app:app`
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.port, debug=False)
