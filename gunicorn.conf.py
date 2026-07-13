"""Production Gunicorn configuration for the Flask backend."""

from __future__ import annotations

import multiprocessing
import os


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer setting from the environment."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = _positive_int("WORKERS", max(2, multiprocessing.cpu_count() * 2 + 1))
timeout = _positive_int("REQUEST_TIMEOUT", 60)
graceful_timeout = _positive_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _positive_int("GUNICORN_KEEPALIVE", 5)
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
worker_tmp_dir = os.getenv("GUNICORN_WORKER_TMP_DIR", "/tmp")
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "INFO").lower()
capture_output = True
enable_stdio_inheritance = True
preload_app = os.getenv("GUNICORN_PRELOAD_APP", "false").lower() == "true"
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")
access_log_format = (
    '{"remote":"%(h)s","request":"%(r)s","status":%(s)s,'
    '"bytes":%(b)s,"referer":"%(f)s","user_agent":"%(a)s",'
    '"duration_us":%(D)s}'
)
