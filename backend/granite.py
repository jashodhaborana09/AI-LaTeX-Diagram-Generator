"""IBM watsonx.ai Granite integration for TikZ generation."""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

DEFAULT_GRANITE_MODEL_ID = "ibm/granite-4-h-small"
DEFAULT_MAX_RETRIES = 3
RETRY_STATUS_CODES = [408, 409, 425, 429, 500, 502, 503, 504]
PROMPT_RULES = """Rules:
- Output only TikZ code.
- Return only TikZ code.
- Do not include explanations.
- Do not use Markdown fences.
- Do not use \\documentclass.
- Do not use \\begin{document}.
- Return only a single tikzpicture environment.
- Use valid TikZ syntax.
- Use positioning library syntax only when required.
- Prefer standard shapes: rectangle, rounded rectangle, circle, diamond, ellipse.
- Prefer clean spacing.
- Avoid unsupported packages.
- Avoid unnecessary decorations.
- Avoid experimental TikZ libraries.
- Keep diagrams centered.
- Keep node names simple.
- Avoid overlapping nodes.
"""
DIAGRAM_TEMPLATES = {
    "flowchart": r"""\begin{tikzpicture}[node distance=1.8cm]
\node[draw, rounded corners] (start) {Start};
\node[draw, rectangle, below of=start] (process) {Process};
\node[draw, diamond, below of=process] (decision) {Decision};
\draw[->] (start) -- (process);
\draw[->] (process) -- (decision);
\end{tikzpicture}""",
    "sequence diagram": r"""\begin{tikzpicture}
\node (user) at (0,0) {User};
\node (api) at (3,0) {API};
\node (service) at (6,0) {Service};
\draw[dashed] (user) -- (0,-4);
\draw[dashed] (api) -- (3,-4);
\draw[dashed] (service) -- (6,-4);
\draw[->] (0,-1) -- node[above] {request} (3,-1);
\draw[->] (3,-2) -- node[above] {process} (6,-2);
\end{tikzpicture}""",
    "network diagram": r"""\begin{tikzpicture}
\node[draw, circle] (client) at (0,0) {Client};
\node[draw, circle] (router) at (3,0) {Router};
\node[draw, circle] (server) at (6,0) {Server};
\draw[->] (client) -- (router);
\draw[->] (router) -- (server);
\end{tikzpicture}""",
    "architecture diagram": r"""\begin{tikzpicture}
\node[draw, rounded corners] (frontend) at (0,0) {Frontend};
\node[draw, rounded corners] (api) at (3,0) {API};
\node[draw, rounded corners] (model) at (6,0) {Model};
\draw[->] (frontend) -- (api);
\draw[->] (api) -- (model);
\end{tikzpicture}""",
    "uml": r"""\begin{tikzpicture}
\node[draw, rectangle] (classa) at (0,0) {Class A};
\node[draw, rectangle] (classb) at (4,0) {Class B};
\draw[->] (classa) -- (classb);
\end{tikzpicture}""",
    "mind map": r"""\begin{tikzpicture}
\node[draw, circle] (center) at (0,0) {Topic};
\node[draw, ellipse] (idea1) at (-3,1.5) {Idea 1};
\node[draw, ellipse] (idea2) at (3,1.5) {Idea 2};
\draw (center) -- (idea1);
\draw (center) -- (idea2);
\end{tikzpicture}""",
    "tree": r"""\begin{tikzpicture}
\node[draw, circle] (root) at (0,0) {Root};
\node[draw, circle] (left) at (-2,-2) {Left};
\node[draw, circle] (right) at (2,-2) {Right};
\draw[->] (root) -- (left);
\draw[->] (root) -- (right);
\end{tikzpicture}""",
    "pipeline": r"""\begin{tikzpicture}
\node[draw, rounded corners] (input) at (0,0) {Input};
\node[draw, rectangle] (step) at (3,0) {Step};
\node[draw, rounded corners] (output) at (6,0) {Output};
\draw[->] (input) -- (step);
\draw[->] (step) -- (output);
\end{tikzpicture}""",
    "state machine": r"""\begin{tikzpicture}
\node[draw, circle] (idle) at (0,0) {Idle};
\node[draw, circle] (active) at (3,0) {Active};
\node[draw, circle] (done) at (6,0) {Done};
\draw[->] (idle) -- node[above] {start} (active);
\draw[->] (active) -- node[above] {finish} (done);
\end{tikzpicture}""",
}


class GraniteError(RuntimeError):
    """Base exception for Granite integration errors."""


class GraniteConfigurationError(GraniteError):
    """Raised when required Watsonx configuration is missing or invalid."""


class GraniteAuthenticationError(GraniteError):
    """Raised when Watsonx rejects the configured credentials."""


class GraniteGenerationError(GraniteError):
    """Raised when TikZ generation fails after retries."""


@dataclass(frozen=True)
class WatsonxSettings:
    """Validated IBM watsonx.ai connection and generation settings."""

    api_key: str
    project_id: str
    url: str
    model_id: str = DEFAULT_GRANITE_MODEL_ID
    max_retries: int = DEFAULT_MAX_RETRIES


def generate_tikz(prompt: str) -> str:
    """Generate TikZ code from a natural-language diagram prompt."""
    clean_prompt = _validate_prompt(prompt)
    logger.info("Cleaned prompt: %s", clean_prompt)
    settings = _load_settings()
    model = _build_model(settings)
    watsonx_prompt = _build_tikz_prompt(clean_prompt)
    return _generate_text_with_retries(model, settings, watsonx_prompt, "generation")


def refine_tikz(existing_tikz: str, instruction: str) -> str:
    """Refine existing TikZ code using a natural-language edit instruction."""
    clean_tikz = _validate_tikz(existing_tikz)
    clean_instruction = _validate_prompt(instruction)
    settings = _load_settings()
    model = _build_model(settings)
    watsonx_prompt = _build_refinement_prompt(clean_tikz, clean_instruction)
    return _generate_text_with_retries(model, settings, watsonx_prompt, "refinement")


def repair_tikz(tikz_code: str, compiler_error: str, user_prompt: str = "") -> str:
    """Ask Granite to repair TikZ after validation or LaTeX compilation fails."""
    clean_tikz = _validate_tikz(tikz_code)
    clean_error = compiler_error.strip() or "Compilation failed."
    clean_prompt = user_prompt.strip()
    settings = _load_settings()
    model = _build_model(settings)
    watsonx_prompt = _build_repair_prompt(clean_tikz, clean_error, clean_prompt)
    return _generate_text_with_retries(model, settings, watsonx_prompt, "repair")


def _generate_text_with_retries(
    model: Any,
    settings: WatsonxSettings,
    watsonx_prompt: str,
    operation: str,
) -> str:
    """Call Watsonx with retries and return clean TikZ code."""

    last_error: Exception | None = None
    for attempt in range(1, settings.max_retries + 1):
        try:
            logger.info(
                "Running TikZ %s with Watsonx model %s, attempt %s/%s",
                operation,
                settings.model_id,
                attempt,
                settings.max_retries,
            )
            response = model.generate_text(prompt=watsonx_prompt)
            logger.info("Model response: %s", response)
            logger.info("Granite response received for TikZ %s.", operation)
            tikz_code = _extract_tikz(response)
            if not tikz_code:
                raise GraniteGenerationError(f"Watsonx returned an empty TikZ {operation} response.")
            return tikz_code
        except GraniteAuthenticationError:
            raise
        except Exception as error:
            if _is_authentication_error(error):
                raise GraniteAuthenticationError(
                    "IBM watsonx.ai authentication failed. Check IBM_API_KEY, IBM_PROJECT_ID, and IBM_URL."
                ) from error

            last_error = error
            if attempt >= settings.max_retries or not _is_retryable_error(error):
                break

            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "Watsonx TikZ %s failed on attempt %s/%s; retrying in %.2fs: %s",
                operation,
                attempt,
                settings.max_retries,
                delay,
                _error_message(error),
            )
            time.sleep(delay)

    details = f": {_error_message(last_error)}" if last_error else ""
    raise GraniteGenerationError(f"Failed to complete TikZ {operation} with IBM Granite{details}.") from last_error


def _load_settings() -> WatsonxSettings:
    """Load and validate watsonx.ai settings from environment variables."""
    _load_dotenv(ENV_FILE)

    api_key = _required_env("IBM_API_KEY")
    project_id = _required_env("IBM_PROJECT_ID")
    url = _required_env("IBM_URL")
    model_id = (
        os.getenv("MODEL_ID", "").strip()
        or os.getenv("IBM_GRANITE_MODEL_ID", "").strip()
        or DEFAULT_GRANITE_MODEL_ID
    )
    max_retries = _positive_int_env("IBM_WATSONX_MAX_RETRIES", DEFAULT_MAX_RETRIES)
    return WatsonxSettings(
        api_key=api_key,
        project_id=project_id,
        url=url,
        model_id=model_id,
        max_retries=max_retries,
    )


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs from a dotenv file if it exists."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _required_env(name: str) -> str:
    """Return a required environment variable or raise a configuration error."""
    value = os.getenv(name, "").strip()
    placeholder_values = {
        "YOUR_API_KEY",
        "YOUR_PROJECT_ID",
        "YOUR_WATSONX_URL",
    }

    if not value or value in placeholder_values:
        raise GraniteConfigurationError(
            f"{name} must be set in .env or the process environment before calling generate_tikz()."
        )

    return value


def _positive_int_env(name: str, default: int) -> int:
    """Return a positive integer environment value with a default."""
    value = os.getenv(name, "").strip()
    if not value:
        return default

    try:
        parsed = int(value)
    except ValueError as error:
        raise GraniteConfigurationError(f"{name} must be a positive integer.") from error

    if parsed < 1:
        raise GraniteConfigurationError(f"{name} must be a positive integer.")

    return parsed


def _build_model(settings: WatsonxSettings) -> Any:
    """Create a Watsonx ModelInference client from validated settings."""
    try:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    except ImportError as error:
        raise GraniteConfigurationError(
            "Install the IBM watsonx.ai Python SDK with: pip install ibm-watsonx-ai"
        ) from error

    credentials = Credentials(
        api_key=settings.api_key,
        url=settings.url,
    )
    params = {
        GenParams.DECODING_METHOD: "greedy",
        GenParams.MAX_NEW_TOKENS: 1200,
        GenParams.MIN_NEW_TOKENS: 80,
        GenParams.REPETITION_PENALTY: 1.08,
        GenParams.STOP_SEQUENCES: ["```end", "</tikz>"],
    }

    try:
        return ModelInference(
            model_id=settings.model_id,
            credentials=credentials,
            project_id=settings.project_id,
            params=params,
            max_retries=settings.max_retries,
            retry_status_codes=RETRY_STATUS_CODES,
        )
    except TypeError as error:
        raise GraniteConfigurationError(
            "Installed ibm-watsonx-ai SDK does not support the expected ModelInference API."
        ) from error
    except Exception as error:
        if _is_authentication_error(error):
            raise GraniteAuthenticationError(
                "IBM watsonx.ai authentication failed. Check IBM_API_KEY, IBM_PROJECT_ID, and IBM_URL."
            ) from error
        if _is_model_configuration_error(error):
            raise GraniteConfigurationError(
                f"Unable to initialize IBM Granite model '{settings.model_id}'. "
                "Check MODEL_ID, IBM_PROJECT_ID, IBM_URL, and model access."
            ) from error
        raise GraniteConfigurationError(
            f"Unable to initialize IBM watsonx.ai ModelInference: {_error_message(error)}"
        ) from error


def _validate_prompt(prompt: str) -> str:
    """Validate and trim a natural-language prompt."""
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string.")

    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("prompt must not be empty.")

    return clean_prompt


def _validate_tikz(tikz_code: str) -> str:
    """Validate existing TikZ input before refinement or repair."""
    if not isinstance(tikz_code, str):
        raise ValueError("existing_tikz must be a string.")

    clean_tikz = tikz_code.strip()
    if not clean_tikz:
        raise ValueError("existing_tikz must not be empty.")

    if "\\begin{tikzpicture}" not in clean_tikz or "\\end{tikzpicture}" not in clean_tikz:
        raise ValueError("existing_tikz must contain a complete tikzpicture environment.")

    return clean_tikz


def _build_tikz_prompt(prompt: str) -> str:
    """Build the strict generation prompt sent to Granite."""
    diagram_type = _detect_diagram_type(prompt)
    template = DIAGRAM_TEMPLATES[diagram_type]
    return f"""You are an expert academic LaTeX and TikZ diagram author.

Create clean, compilable TikZ code for the requested {diagram_type}.

{PROMPT_RULES}

Use this small {diagram_type} template only as syntax and layout guidance:
{template}

Diagram request:
{prompt}
"""


def _build_refinement_prompt(existing_tikz: str, instruction: str) -> str:
    """Build the prompt used to refine an existing TikZ diagram."""
    return f"""You are an expert academic LaTeX and TikZ diagram editor.

Refine the existing TikZ code according to the user's instruction.

{PROMPT_RULES}
- Do not include explanations, comments about your changes, or surrounding prose.
- Preserve all existing node names and edge references unless the instruction cannot be completed otherwise.
- Preserve the overall diagram semantics unless the instruction explicitly changes them.
- Keep the result professional, publication-quality, readable, and compilable.
- Keep \\begin{{tikzpicture}} and \\end{{tikzpicture}}.
- Avoid overlapping labels, nodes, and arrows.

User refinement instruction:
{instruction}

Existing TikZ:
{existing_tikz}
"""


def _build_repair_prompt(existing_tikz: str, compiler_error: str, user_prompt: str) -> str:
    """Build the prompt used to repair TikZ after validation or compilation failure."""
    context = f"\nOriginal user request:\n{user_prompt}\n" if user_prompt else ""
    return f"""You are an expert LaTeX TikZ repair assistant.

Repair the TikZ so it compiles successfully. Preserve the diagram intent.

{PROMPT_RULES}
- Fix only syntax, structure, unsupported commands, invalid coordinates, and obvious layout errors.
- Keep the result as one complete tikzpicture environment.
{context}
Compiler or validation error:
{compiler_error}

Broken TikZ:
{existing_tikz}
"""


def _detect_diagram_type(prompt: str) -> str:
    """Infer a diagram template family from the user prompt."""
    normalized = prompt.lower()
    checks = (
        ("sequence diagram", ("sequence", "lifeline", "actor")),
        ("network diagram", ("network", "router", "switch", "server", "client")),
        ("architecture diagram", ("architecture", "service", "microservice", "api", "database")),
        ("uml", ("uml", "class diagram", "use case", "inheritance")),
        ("mind map", ("mind map", "mindmap", "brainstorm", "central topic")),
        ("tree", ("tree", "hierarchy", "binary tree", "root node")),
        ("pipeline", ("pipeline", "workflow", "stages", "etl")),
        ("state machine", ("state machine", "state diagram", "finite state", "transition")),
        ("flowchart", ("flowchart", "flow chart", "decision", "process")),
    )
    for diagram_type, keywords in checks:
        if any(keyword in normalized for keyword in keywords):
            return diagram_type
    return "flowchart"


def _extract_tikz(response: Any) -> str:
    """Extract TikZ text from common Watsonx response shapes."""
    if isinstance(response, str):
        return _clean_tikz(response)

    if isinstance(response, dict):
        for key in ("generated_text", "text", "output"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return _clean_tikz(value)

        results = response.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    for key in ("generated_text", "text", "output"):
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            return _clean_tikz(value)

    return _clean_tikz(str(response)) if response is not None else ""


def _clean_tikz(text: str) -> str:
    """Remove wrappers and keep the first complete tikzpicture block."""
    cleaned = text.strip()
    cleaned = cleaned.replace("\\documentclass", "% removed documentclass")
    cleaned = cleaned.replace("\\begin{document}", "")
    cleaned = cleaned.replace("\\end{document}", "")
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith(("latex", "tex", "tikz")):
            cleaned = cleaned.split("\n", 1)[1].strip() if "\n" in cleaned else ""

    begin_index = cleaned.find("\\begin{tikzpicture}")
    end_marker = "\\end{tikzpicture}"
    end_index = cleaned.find(end_marker)

    if begin_index != -1 and end_index != -1:
        end_index += len(end_marker)
        return cleaned[begin_index:end_index].strip()

    return cleaned


def _is_authentication_error(error: Exception) -> bool:
    """Return True when an exception looks like an authentication failure."""
    status_code = _get_status_code(error)
    if status_code in {401, 403}:
        return True

    message = str(error).lower()
    auth_terms = (
        "unauthorized",
        "forbidden",
        "invalid api key",
        "invalid token",
        "authentication",
        "not authorized",
    )
    return any(term in message for term in auth_terms)


def _is_retryable_error(error: Exception) -> bool:
    """Return True when an exception is likely transient."""
    status_code = _get_status_code(error)
    if status_code in RETRY_STATUS_CODES:
        return True

    message = str(error).lower()
    retryable_terms = (
        "timeout",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "connection",
        "service unavailable",
        "gateway",
    )
    return any(term in message for term in retryable_terms)


def _is_model_configuration_error(error: Exception) -> bool:
    """Return True when an exception suggests model or project misconfiguration."""
    status_code = _get_status_code(error)
    if status_code in {400, 404}:
        return True

    message = str(error).lower()
    configuration_terms = (
        "model",
        "project",
        "deployment",
        "not found",
        "invalid",
        "unsupported",
    )
    return any(term in message for term in configuration_terms)


def _get_status_code(error: Exception) -> int | None:
    """Extract an HTTP status code from common SDK exception shapes."""
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _error_message(error: Exception) -> str:
    """Return a readable error message for logging and exceptions."""
    message = str(error).strip()
    return message or error.__class__.__name__


def _retry_delay_seconds(attempt: int) -> float:
    """Calculate exponential backoff with jitter for Watsonx retries."""
    base_delay = min(2 ** (attempt - 1), 8)
    jitter = random.uniform(0.1, 0.6)
    return base_delay + jitter
