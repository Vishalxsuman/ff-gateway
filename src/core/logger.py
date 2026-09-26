# -*- coding: utf-8 -*-
"""
logger.py — Structured JSON logger for the FF Gateway.

Every log record includes: timestamp, level, request_id (when set),
uid, region, latency_ms, and status — making logs trivially queryable
in Azure Monitor / Application Insights.
"""

import json
import logging
import sys
import time
import threading
from contextvars import ContextVar
from typing import Optional

from src.core.config import config

# Per-request context propagated via contextvars (thread + async-safe)
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_uid_var: ContextVar[str] = ContextVar("uid", default="-")
_region_var: ContextVar[str] = ContextVar("region", default="-")
_start_time_var: ContextVar[Optional[float]] = ContextVar("start_time", default=None)


def set_request_context(
    request_id: str = "-",
    uid: str = "-",
    region: str = "-",
) -> None:
    _request_id_var.set(request_id)
    _uid_var.set(uid)
    _region_var.set(region)
    _start_time_var.set(time.monotonic())


def get_latency_ms() -> Optional[float]:
    start = _start_time_var.get()
    if start is None:
        return None
    return round((time.monotonic() - start) * 1000, 2)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": "ff-gateway",
            "request_id": _request_id_var.get(),
            "uid": _uid_var.get(),
            "region": _region_var.get(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        latency = get_latency_ms()
        if latency is not None:
            log_record["latency_ms"] = latency
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level, logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
