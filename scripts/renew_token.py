# -*- coding: utf-8 -*-
"""
renew_token.py — Standalone Garena Token Renewal Agent

Can be run via cron (e.g. every 3 hours) or as a standalone CLI job:
  0 */3 * * * python3 /opt/ff-gateway/scripts/renew_token.py >> /var/log/ff-token-renew.log 2>&1

Performs:
  1. Garena OAuth grant (_do_garena_oauth_grant) using FF_GUEST_UID / FF_GUEST_PASSWORD.
  2. Exchange via MajorLogin for fresh session JWT.
  3. POSTs fresh JWT to the running ff-gateway endpoint (POST /token/update).
"""

import logging
import os
import sys
import time
from pathlib import Path

import requests

# Add repository root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ff.auth import _do_garena_oauth_grant, _do_garena_major_login, _parse_jwt_expiry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("renew_token_agent")

GATEWAY_URL = os.getenv("GATEWAY_UPDATE_URL", "http://localhost:8080/token/update").strip()


def run_renewal() -> bool:
    logger.info("Starting scheduled Garena token renewal job...")

    # 1. OAuth Grant
    oauth_res = _do_garena_oauth_grant()
    if not oauth_res:
        logger.error("OAuth grant failed. Check FF_GUEST_UID / FF_GUEST_PASSWORD.")
        return False

    open_id = oauth_res.get("open_id")
    access_token = oauth_res.get("access_token") or oauth_res.get("token")

    jwt_token = ""
    expires_at = 0.0

    if access_token and str(access_token).startswith("eyJ"):
        jwt_token = str(access_token)
        expires_at = _parse_jwt_expiry(jwt_token)
    elif open_id and access_token:
        major_res = _do_garena_major_login(open_id, str(access_token))
        if major_res:
            jwt_token, expires_at = major_res

    if not jwt_token:
        logger.error("Failed to obtain fresh Garena JWT session token.")
        return False

    exp_hours = round((expires_at - time.time()) / 3600, 2)
    logger.info("Obtained fresh Garena JWT (valid for %.2f hours)", exp_hours)

    # 2. Push fresh token to running gateway endpoint
    try:
        resp = requests.post(
            GATEWAY_URL,
            json={"token": jwt_token, "region": "IND"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Successfully pushed fresh token to gateway (%s): %s", GATEWAY_URL, resp.text)
            return True
        else:
            logger.error("Gateway returned HTTP %d: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.error("Failed to POST token to gateway at %s: %s", GATEWAY_URL, exc)

    return False


if __name__ == "__main__":
    success = run_renewal()
    sys.exit(0 if success else 1)
