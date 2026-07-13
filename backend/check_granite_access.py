"""Check which IBM watsonx.ai Granite models are available."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
REQUIRED_ENV_VARS = ("IBM_API_KEY", "IBM_PROJECT_ID", "IBM_URL")
PLACEHOLDER_VALUES = {
    "YOUR_API_KEY",
    "YOUR_PROJECT_ID",
    "YOUR_WATSONX_URL",
    "your_real_api_key",
    "your_project_id",
}
logger = logging.getLogger(__name__)


class ConfigurationError(RuntimeError):
    """Raised when required watsonx.ai configuration is missing."""


@dataclass(frozen=True)
class WatsonxConfig:
    """Validated watsonx.ai credentials for the access-check script."""

    api_key: str
    project_id: str
    url: str


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ."""
    if not path.exists():
        raise ConfigurationError(f".env file not found at {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config() -> WatsonxConfig:
    """Load required IBM watsonx.ai configuration from the environment."""
    load_dotenv(ENV_FILE)

    missing = []
    values: dict[str, str] = {}
    for name in REQUIRED_ENV_VARS:
        value = os.getenv(name, "").strip()
        if not value or value in PLACEHOLDER_VALUES:
            missing.append(name)
        values[name] = value

    if missing:
        missing_list = ", ".join(missing)
        raise ConfigurationError(f"Missing required configuration in .env: {missing_list}")

    return WatsonxConfig(
        api_key=values["IBM_API_KEY"],
        project_id=values["IBM_PROJECT_ID"],
        url=values["IBM_URL"],
    )


def build_client(config: WatsonxConfig) -> Any:
    """Build an IBM watsonx.ai API client."""
    try:
        from ibm_watsonx_ai import APIClient, Credentials
    except ImportError as error:
        raise ConfigurationError(
            "Install the IBM watsonx.ai Python SDK with: pip install ibm-watsonx-ai"
        ) from error

    credentials = Credentials(api_key=config.api_key, url=config.url)
    return APIClient(credentials=credentials, project_id=config.project_id)


def infer_region(service_url: str) -> str:
    """Infer the IBM Cloud region from a watsonx.ai service URL."""
    parsed = urlparse(service_url if "://" in service_url else f"https://{service_url}")
    host = parsed.hostname or ""
    cloud_suffix = ".ml.cloud.ibm.com"

    if host.endswith(cloud_suffix):
        return host[: -len(cloud_suffix)] or "unknown"

    return host.split(".", 1)[0] if host else "unknown"


def get_foundation_models(client: Any) -> list[Any]:
    """Fetch all foundation model records available to the configured project."""
    response = client.foundation_models.get_model_specs(get_all=True, filters=None)
    return normalize_model_records(response)


def normalize_model_records(response: Any) -> list[Any]:
    """Normalize SDK model-list responses into a list."""
    if response is None:
        return []

    if hasattr(response, "to_dict"):
        try:
            records = response.to_dict("records")
        except TypeError:
            records = None
        if isinstance(records, list):
            return records

    if isinstance(response, dict):
        for key in ("resources", "models", "results"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        return [response]

    if isinstance(response, list):
        return response

    if not isinstance(response, (str, bytes)):
        try:
            return list(response)
        except TypeError:
            pass

    return []


def get_model_id(model: Any) -> str:
    """Extract a model identifier from a model record."""
    if isinstance(model, dict):
        for key in ("model_id", "id", "modelId"):
            value = model.get(key)
            if value:
                return str(value)
        return ""

    for attribute in ("model_id", "id", "modelId"):
        value = getattr(model, attribute, None)
        if value:
            return str(value)

    return ""


def is_ibm_granite_model(model: Any) -> bool:
    """Return True when a model record appears to be an IBM Granite model."""
    model_id = get_model_id(model).lower()
    return "granite" in model_id and "ibm" in model_id


def configure_logging() -> None:
    """Configure console logging for the Granite access check."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def log_model_summary(config: WatsonxConfig, models: list[Any]) -> None:
    """Log a concise summary of available Granite models."""
    logger.info("Current region: %s", infer_region(config.url))
    logger.info("Current project ID: %s", config.project_id)
    logger.info("Current service URL: %s", config.url)
    logger.info("Total number of models: %s", len(models))

    granite_models = [model for model in models if is_ibm_granite_model(model)]

    logger.info("IBM Granite models:")
    if not granite_models:
        logger.info("No Granite models are available for this account or region.")
        return

    for model in granite_models:
        logger.info("- %s", get_model_id(model))


def main() -> int:
    """Run the Granite access check and return a process exit code."""
    configure_logging()
    try:
        config = load_config()
        client = build_client(config)
        models = get_foundation_models(client)
        log_model_summary(config, models)
    except ConfigurationError as error:
        logger.exception("Configuration error: %s", error)
        return 1
    except Exception as error:
        logger.exception("Error while checking IBM watsonx.ai Granite access: %s", error)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
