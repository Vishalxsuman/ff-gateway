"""Pytest configuration and shared fixtures."""

import os
import sys

# Ensure src is importable from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set protocol/config vars before any src import triggers config.load_config().
os.environ.setdefault("FF_SESSION_JWT", "")
os.environ.setdefault("FF_TOKEN_PROVIDER_URL", "")
os.environ.setdefault("FF_TOKEN_PROVIDER_SECRET", "")
os.environ.setdefault("FF_TOKEN_UPDATE_KEY", "test-update-key")
os.environ.setdefault("FF_OB_VERSION", "OB55")
os.environ.setdefault("AES_KEY", "Yg&tc%DEuh6%Zc^8")
os.environ.setdefault("AES_IV", "6oyZDr22E3ychjM%")
os.environ.setdefault("ENABLE_CACHE", "false")
os.environ.setdefault("ENABLE_RATE_LIMIT", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
