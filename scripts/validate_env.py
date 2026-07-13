"""Validate production environment variables before starting the container."""

from __future__ import annotations

import logging
import os
import sys


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
REQUIRED_WHEN_ENABLED = ("IBM_API_KEY", "IBM_PROJECT_ID", "IBM_URL")
POSITIVE_INTEGER_VARS = (
    "PORT",
    "WORKERS",
    "MAX_PROMPT_LENGTH",
    "MAX_UPLOAD_SIZE",
    "REQUEST_TIMEOUT",
    "IBM_WATSONX_MAX_RETRIES",
    "GUNICORN_GRACEFUL_TIMEOUT",
    "GUNICORN_KEEPALIVE",
)
PLACEHOLDER_VALUES = {
    "YOUR_API_KEY",
    "YOUR_PROJECT_ID",
    "YOUR_WATSONX_URL",
    "your_api_key",
    "your_project_id",
}


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Validate environment variables when startup validation is enabled."""
    enabled = os.getenv("VALIDATE_ENV_ON_START", "false").lower() == "true"
    errors: list[str] = []

    if enabled:
        errors.extend(validate_required_vars())
    else:
        logger.info("Startup environment validation is disabled.")

    errors.extend(validate_positive_ints())

    model_id = os.getenv("MODEL_ID", "").strip() or os.getenv("IBM_GRANITE_MODEL_ID", "").strip()
    if model_id == "":
        logger.info("MODEL_ID is unset; default IBM Granite model will be used.")

    if errors:
        for error in errors:
            logger.error(error)
        return 1

    logger.info("Environment validation passed.")
    return 0


def validate_required_vars() -> list[str]:
    """Validate required runtime secrets and service configuration."""
    errors: list[str] = []
    for name in REQUIRED_WHEN_ENABLED:
        value = os.getenv(name, "").strip()
        if not value or value in PLACEHOLDER_VALUES:
            errors.append(f"{name} must be set for production startup.")
    return errors


def validate_positive_ints() -> list[str]:
    """Validate optional positive integer environment variables."""
    errors: list[str] = []
    for name in POSITIVE_INTEGER_VARS:
        value = os.getenv(name, "").strip()
        if not value:
            continue
        try:
            parsed = int(value)
        except ValueError:
            errors.append(f"{name} must be a positive integer.")
            continue
        if parsed < 1:
            errors.append(f"{name} must be a positive integer.")
    return errors


if __name__ == "__main__":
    sys.exit(main())
