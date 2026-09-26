# -*- coding: utf-8 -*-
"""version.py — /version endpoint."""

import os
import subprocess
from datetime import date

from flask import Blueprint, jsonify

from src.core.config import config

version_bp = Blueprint("version", __name__)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
    except Exception:
        return os.getenv("GIT_COMMIT", "unknown")


@version_bp.route("/version")
def version():
    return jsonify(
        {
            "service": "ff-gateway",
            "version": "1.0.0",
            "ob_version": config.ff_ob_version,
            "build_date": str(date.today()),
            "git_commit": _git_commit(),
            "python_version": os.sys.version.split()[0],
        }
    )
