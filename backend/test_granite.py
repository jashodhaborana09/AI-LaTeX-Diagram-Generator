"""Manual IBM watsonx.ai Granite connection test.

Run this file directly to verify that the project can authenticate with
watsonx.ai and receive TikZ output from the configured Granite model.
"""

from __future__ import annotations

import logging

from granite import (
    GraniteAuthenticationError,
    GraniteConfigurationError,
    GraniteGenerationError,
    generate_tikz,
)


logger = logging.getLogger(__name__)
TEST_PROMPT = "Draw a simple flowchart with Start → Process → End using TikZ."


def configure_logging() -> None:
    """Configure concise console logging for the manual connection test."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def test_connection() -> None:
    """Test IBM Granite connectivity by requesting a small TikZ flowchart."""
    configure_logging()

    logger.info("IBM Granite Connection Test")
    logger.info("Connecting to IBM watsonx.ai...")
    logger.info("Starting IBM Granite connection test.")

    try:
        response = generate_tikz(TEST_PROMPT)
    except GraniteConfigurationError as error:
        logger.exception("Granite configuration error: %s", error)
    except GraniteAuthenticationError as error:
        logger.exception("Granite authentication error: %s", error)
    except GraniteGenerationError as error:
        logger.exception("Granite generation error: %s", error)
    except Exception as error:
        logger.exception("Unexpected Granite connection test error: %s", error)
    else:
        logger.info("IBM Granite connection test completed successfully.")
        logger.info("Generated TikZ code: %s", response)


if __name__ == "__main__":
    test_connection()
