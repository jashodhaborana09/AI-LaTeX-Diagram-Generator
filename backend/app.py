"""Production Flask API for the AI-Powered LaTeX Diagram Generator."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, Response, current_app, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.utils import secure_filename

try:
    from compiler import compile_tikz, CompileError
    from granite import generate_tikz, repair_tikz
except ImportError:  # pragma: no cover - supports package imports.
    from .compiler import compile_tikz, CompileError
    from .granite import generate_tikz, repair_tikz


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_MAX_PROMPT_LENGTH = 3000
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60
UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER", BASE_DIR / "uploads"))
GENERATED_FOLDER = Path(os.getenv("GENERATED_FOLDER", BASE_DIR / "data" / "generated"))
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
SERVICE_NAME = "AI LaTeX Diagram Generator"
MODEL_NAME = "IBM Granite 4 H Small"
VERSION = "1.0.0"
FRONTEND_ORIGINS = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)
GENERATED_ASSET_DIRS = {
    "pdf": "pdf",
    "images": "images",
    "latex": "latex",
}
BEGIN_TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}(?:\s*\[[^\]]*\])?")
END_TIKZ = r"\end{tikzpicture}"
MARKDOWN_FENCE_RE = re.compile(r"^\s*```(?:latex|tex|tikz)?\s*$", re.IGNORECASE | re.MULTILINE)
DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}", re.IGNORECASE)
USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\}", re.IGNORECASE)
EMPTY_NODE_RE = re.compile(r"\\node(?:\s*\[[^\]]*\])?(?:\s*\([^)]*\))?(?:\s+at\s*\([^)]*\))?\s*\{\s*\}\s*;?")
NODE_NAME_RE = re.compile(r"\\node\b[^;]*?\(([^()\s]+)\)")
COORDINATE_RE = re.compile(r"\(([^()]*,[^()]*)\)")
COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
MAX_COMPILE_ATTEMPTS = 3
FLOWCHART_STYLE_REPLACEMENTS = {
    "rounded rectangle": ("rectangle", "rounded corners"),
    "startstop": ("rectangle", "rounded corners", "fill=green!20"),
    "process": ("rectangle", "fill=blue!20"),
    "decision": ("diamond", "aspect=2", "fill=yellow!20"),
}
UNSUPPORTED_TIKZ_KEYS = {
    "rounded rectangle",
    "startstop",
    "process",
    "decision",
    "terminator",
    "io",
    "input",
    "output",
    "data",
    "database",
    "document",
    "manual input",
    "manual operation",
    "preparation",
    "subroutine",
    "connector",
    "off page connector",
}
SUPPORTED_BARE_TIKZ_KEYS = {
    "rectangle",
    "circle",
    "ellipse",
    "diamond",
    "coordinate",
    "draw",
    "fill",
    "text",
    "node",
    "line",
    "path",
    "edge",
    "solid",
    "dashed",
    "densely dashed",
    "loosely dashed",
    "dotted",
    "densely dotted",
    "loosely dotted",
    "thick",
    "very thick",
    "ultra thick",
    "semithick",
    "thin",
    "very thin",
    "ultra thin",
    "help lines",
    "rounded corners",
    "sharp corners",
    "smooth",
    "cycle",
    "above",
    "below",
    "left",
    "right",
    "centered",
    "sloped",
    "midway",
    "near start",
    "near end",
    "auto",
    "swap",
    "bend left",
    "bend right",
    "->",
    "<-",
    "<->",
    "-",
    "|-|",
    "-|",
    "|-",
    "stealth",
    "latex",
}
SUPPORTED_TIKZ_COMMANDS = {
    "begin",
    "end",
    "node",
    "draw",
    "path",
    "coordinate",
    "matrix",
    "foreach",
    "definecolor",
    "tikzset",

    # text formatting
    "textbf",
    "textit",
    "texttt",

    # font declarations
    "ttfamily",
    "rmfamily",
    "sffamily",
    "bfseries",
    "itshape",
    "scshape",
    "mdseries",

    # font sizes
    "tiny",
    "scriptsize",
    "footnotesize",
    "small",
    "normalsize",
    "large",
    "Large",
    "LARGE",
    "huge",
    "Huge",
}
DISALLOWED_TIKZ_COMMANDS = {
    "documentclass",
    "usepackage",
    "usetikzlibrary",
    "beginpgfgraphicnamed",
    "includegraphics",
    "input",
    "include",
}

logger = logging.getLogger(__name__)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings loaded from environment variables."""

    max_prompt_length: int
    max_upload_size: int
    request_timeout: int
    log_level: str


def load_app_settings() -> AppSettings:
    """Load production configuration with safe defaults."""
    return AppSettings(
        max_prompt_length=positive_int_env("MAX_PROMPT_LENGTH", DEFAULT_MAX_PROMPT_LENGTH),
        max_upload_size=positive_int_env("MAX_UPLOAD_SIZE", DEFAULT_MAX_UPLOAD_SIZE_BYTES),
        request_timeout=positive_int_env("REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )


class ApiError(RuntimeError):
    """Application-level error that should be returned as JSON."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class TikzValidationError(ValueError):
    """Raised when generated TikZ cannot be safely compiled."""


def create_app() -> Flask:
    """Create and configure the Flask application."""
    settings = load_app_settings()
    configure_logging(settings.log_level)

    app = Flask(__name__)
    app.config.update(
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=settings.max_upload_size,
        MAX_PROMPT_LENGTH=settings.max_prompt_length,
        MAX_UPLOAD_SIZE=settings.max_upload_size,
        REQUEST_TIMEOUT=settings.request_timeout,
        UPLOAD_FOLDER=str(UPLOAD_FOLDER),
        GENERATED_FOLDER=str(GENERATED_FOLDER),
    )
    

    configure_security(app)
   CORS(
    app,
    origins=[
        "https://ai-la-te-x-diagram-generator.vercel.app"
    ],
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
    limiter.init_app(app)
    ensure_directories(app)
    register_request_hooks(app)
    register_routes(app)
    register_error_handlers(app)

    return app


def configure_logging(level_name: str) -> None:
    """Configure process logging for local and production runtimes."""
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.setLevel(level)


def configure_security(app: Flask) -> None:
    """Attach production security headers without interfering with CORS."""
    Talisman(
        app,
        content_security_policy=None,
        force_https=False,
        frame_options="DENY",
        referrer_policy="strict-origin-when-cross-origin",
    )


def register_request_hooks(app: Flask) -> None:
    """Register request timing and response hardening hooks."""

    @app.before_request
    def start_request_timer() -> None:
        g.request_started_at = time.perf_counter()
        logger.info("API request received: %s %s", request.method, request.path)

    @app.after_request
    def finalize_response(response: Response) -> Response:
        response.headers.pop("X-Powered-By", None)
        response.headers.pop("Server", None)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        logger.info(
            "Response sent: %s %s -> %s",
            request.method,
            request.path,
            response.status_code,
        )

        start_time = getattr(g, "request_started_at", None)
        if start_time is not None:
            duration = time.perf_counter() - start_time
            logger.info("Request completed in %.2f seconds", duration)

        return response


def ensure_directories(app: Flask) -> None:
    """Create configured storage directories if they do not exist."""
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    generated_root = Path(app.config["GENERATED_FOLDER"])
    generated_root.mkdir(parents=True, exist_ok=True)
    for directory in GENERATED_ASSET_DIRS.values():
        (generated_root / directory).mkdir(parents=True, exist_ok=True)


def register_routes(app: Flask) -> None:
    """Register API endpoints."""

    @app.get("/health")
    def health() -> tuple[Response, int]:
        return jsonify(
            {
                "status": "healthy",
                "service": SERVICE_NAME,
                "model": MODEL_NAME,
                "version": VERSION,
            }
        ), 200

    @app.post("/generate")
    @limiter.limit("10 per minute")
    def generate() -> tuple[Response, int]:
        payload = get_json_payload()
        prompt = require_string(
            payload,
            "prompt",
            max_length=app.config["MAX_PROMPT_LENGTH"],
        )

        logger.info("Prompt length: %s characters", len(prompt))
        logger.info("Original prompt: %s", payload.get("prompt"))
        logger.info("Cleaned prompt: %s", prompt)
        logger.info("Granite request started.")
        try:
            raw_tikz = generate_tikz(prompt)
        except Exception as error:
            logger.exception("TikZ generation failed: %s", error)
            return jsonify(
                {
                    "success": False,
                    "error": "Generation failed.",
                    "tikz": "",
                    "details": "Generation failed",
                    "message": "Generation failed",
                }
            ), 200
        logger.info("Granite response received.")
        return compile_tikz_response(raw_tikz, Path(app.config["GENERATED_FOLDER"]), source_prompt=prompt)

    @app.post("/refine")
    def refine() -> tuple[Response, int]:
        payload = get_json_payload()
        instruction = require_string(
            payload,
            "instruction",
            max_length=app.config["MAX_PROMPT_LENGTH"],
        )
        current_tikz = require_string(payload, "tikz", fallback_field_name="current_tikz")

        prompt = build_refinement_prompt(instruction, current_tikz)
        logger.info("Prompt length: %s characters", len(instruction))
        logger.info("Original prompt: %s", payload.get("instruction"))
        logger.info("Cleaned prompt: %s", instruction)
        logger.info("Granite request started.")
        try:
            raw_tikz = generate_tikz(prompt)
        except Exception as error:
            logger.exception("TikZ refinement failed: %s", error)
            return jsonify(
                {
                    "success": False,
                    "error": "Generation failed.",
                    "tikz": current_tikz,
                    "details": "Generation failed",
                    "message": "Refinement failed",
                }
            ), 200
        logger.info("Granite response received.")
        return compile_tikz_response(raw_tikz, Path(app.config["GENERATED_FOLDER"]), source_prompt=instruction)

    @app.post("/upload")
    @limiter.limit("20 per minute")
    def upload() -> tuple[Response, int]:
        logger.info("Image upload received.")
        if "file" not in request.files:
            raise ApiError("Upload an image using the multipart field name 'file'.", 400)

        uploaded_file = request.files["file"]
        if not uploaded_file or not uploaded_file.filename:
            raise ApiError("Uploaded file must have a filename.", 400)

        extension = get_allowed_extension(uploaded_file.filename)
        upload_size = get_upload_size(uploaded_file)
        if upload_size == 0:
            raise ApiError("Uploaded file must not be empty.", 400)
        if upload_size > app.config["MAX_UPLOAD_SIZE"]:
            raise ApiError("Uploaded file exceeds the configured size limit.", 413)

        filename = unique_filename(uploaded_file.filename, extension)
        destination = Path(app.config["UPLOAD_FOLDER"]) / filename
        uploaded_file.save(destination)

        logger.info("Image upload stored: %s (%s bytes)", filename, upload_size)
        return jsonify(
            {
                "success": True,
                "filename": filename,
                "message": "Upload successful",
            }
        ), 200

    @app.get("/generated/<asset_type>/<path:filename>")
    def generated_file(asset_type: str, filename: str) -> Response:
        if asset_type not in GENERATED_ASSET_DIRS:
            raise ApiError("Generated asset type is invalid.", 404)

        safe_filename = secure_filename(filename)
        if safe_filename != filename or not safe_filename:
            raise ApiError("Generated filename is invalid.", 400)

        generated_dir = Path(app.config["GENERATED_FOLDER"]) / GENERATED_ASSET_DIRS[asset_type]
        file_path = generated_dir / safe_filename
        if not file_path.is_file():
            raise ApiError("Generated file was not found.", 404)

        return send_from_directory(generated_dir, safe_filename)


def register_error_handlers(app: Flask) -> None:
    """Return consistent JSON errors for expected and unexpected failures."""

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError) -> tuple[Response, int]:
        logger.exception("API error: %s", error)
        return error_response(str(error), error.status_code)

    @app.errorhandler(400)
    def handle_bad_request(error: HTTPException) -> tuple[Response, int]:
        logger.exception("Bad request: %s", error)
        return error_response("Invalid request.", 400)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_upload(_error: RequestEntityTooLarge) -> tuple[Response, int]:
        logger.exception("Request body exceeded the configured size limit.")
        return error_response("Uploaded file exceeds the configured size limit.", 413)

    @app.errorhandler(404)
    def handle_not_found(_error: HTTPException) -> tuple[Response, int]:
        logger.exception("Endpoint not found: %s %s", request.method, request.path)
        return error_response("Endpoint not found.", 404)

    @app.errorhandler(405)
    def handle_method_not_allowed(_error: HTTPException) -> tuple[Response, int]:
        logger.exception("Method not allowed: %s %s", request.method, request.path)
        return error_response("Method not allowed.", 405)

    @app.errorhandler(415)
    def handle_unsupported_media_type(error: HTTPException) -> tuple[Response, int]:
        logger.exception("Unsupported media type: %s", error)
        return error_response("Unsupported media type.", 415)

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error: RateLimitExceeded) -> tuple[Response, int]:
        logger.exception("Rate limit exceeded: %s", error)
        return error_response("Rate limit exceeded. Please try again later.", 429)

    @app.errorhandler(429)
    def handle_too_many_requests(error: HTTPException) -> tuple[Response, int]:
        logger.exception("Too many requests: %s", error)
        return error_response("Rate limit exceeded. Please try again later.", 429)

    @app.errorhandler(500)
    def handle_internal_server_error(error: HTTPException) -> tuple[Response, int]:
        logger.exception("Internal server error: %s", error)
        return error_response("An unexpected server error occurred.", 500)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        logger.exception("HTTP error: %s", error)
        status_code = normalize_status_code(error.code)
        return error_response(http_error_message(status_code), status_code)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> tuple[Response, int]:
        logger.exception("Unhandled API error: %s", error)
        return error_response("An unexpected server error occurred.", 500)


def get_json_payload() -> dict[str, Any]:
    """Return the JSON request payload or raise a 400 API error."""
    if not request.is_json:
        raise ApiError("Request body must be JSON.", 415)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("Request body must be a JSON object.", 400)

    return payload


def require_string(
    payload: dict[str, Any],
    field_name: str,
    fallback_field_name: str | None = None,
    max_length: int | None = None,
) -> str:
    """Return a required non-empty string field from a JSON payload."""
    value = payload.get(field_name)
    if (not isinstance(value, str) or not value.strip()) and fallback_field_name:
        value = payload.get(fallback_field_name)

    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"'{field_name}' is required and must be a non-empty string.", 400)

    cleaned = value.strip()
    if max_length is not None and len(cleaned) > max_length:
        raise ApiError(f"'{field_name}' must be {max_length} characters or fewer.", 400)

    return cleaned


def build_refinement_prompt(instruction: str, current_tikz: str) -> str:
    """Combine refinement context into a single prompt for Granite."""
    return f"""Refine the following TikZ diagram according to the instruction.

Instruction:
{instruction}

Current TikZ:
{current_tikz}

Return only the updated TikZ code."""


def compile_tikz_response(raw_tikz: str, generated_dir: Path, source_prompt: str = "") -> tuple[Response, int]:
    """Clean, validate, compile, and format the API response for generated TikZ."""
    tikz = ""
    last_compile_error: CompileError | None = None

    try:
        for attempt in range(1, MAX_COMPILE_ATTEMPTS + 1):
            logger.info("Compilation retry count: %s", attempt - 1)
            tikz = clean_tikz(raw_tikz if attempt == 1 else tikz)
            logger.info("TikZ cleaned.")

            validate_tikz(tikz)
            logger.info("TikZ validated.")

            try:
                compile_start = time.perf_counter()
                compile_result = compile_tikz(
                    tikz,
                    output_dir=generated_dir,
                    timeout_seconds=current_request_timeout(),
                )
                compile_duration = time.perf_counter() - compile_start
                logger.info("Compile time: %.2f seconds", compile_duration)
                logger.info("Compilation success on attempt %s.", attempt)
                break
            except CompileError as error:
                last_compile_error = error
                compile_duration = time.perf_counter() - compile_start
                logger.exception("Compilation failed on attempt %s after %.2f seconds.", attempt, compile_duration)
                logger.info("Compilation failure details: %s", error.details or str(error))
                if attempt >= MAX_COMPILE_ATTEMPTS:
                    logger.info("Compilation failed after %s attempts.", attempt)
                    raise

                repaired_tikz = repair_tikz(
                    tikz,
                    error.details or str(error),
                    source_prompt,
                )
                logger.info("Repaired response: %s", repaired_tikz)
                tikz = repaired_tikz
    except TikzValidationError as error:
        logger.exception("TikZ validation failed: %s", error)
        return jsonify(
            {
                "success": False,
                "error": "TikZ validation failed.",
                "tikz": tikz,
                "details": str(error),
                "message": "Generation failed",
            }
        ), 200
    except CompileError as exc:
        logger.exception("Compilation failed")

        return jsonify({
            "success": False,
            "message": "Generation failed",
            "error": str(exc),
            "details": exc.details or (last_compile_error.details if last_compile_error else ""),
        }), 500
    except Exception as error:
        logger.exception("Compilation failed unexpectedly: %s", error)
        return jsonify(
            {
                "success": False,
                "error": "Compilation failed.",
                "tikz": tikz,
                "details": "Compilation failed",
                "message": "Generation failed",
            }
        ), 200

    artifact_urls = build_artifact_urls(compile_result)
    return jsonify(
        {
            "success": True,
            "tikz": tikz,
            "pdf": artifact_urls["pdf"],
            "png": artifact_urls["png"],
            "tex": artifact_urls["tex"],
            "job_id": compile_result["job_id"],
            "message": "Generation successful",
        }
    ), 200


def build_artifact_urls(compile_result: dict[str, str]) -> dict[str, str]:
    """Convert compiler filesystem paths into browser-safe generated file URLs."""
    return {
        "pdf": f"/generated/pdf/{Path(compile_result['pdf_path']).name}",
        "png": f"/generated/images/{Path(compile_result['png_path']).name}",
        "tex": f"/generated/latex/{Path(compile_result['tex_path']).name}",
    }


def clean_tikz(tikz: str) -> str:
    """Normalize Granite output into one compilable tikzpicture environment."""
    if not isinstance(tikz, str):
        raise TikzValidationError("TikZ output must be a string.")

    cleaned = remove_markdown_fences(tikz)
    cleaned = remove_latex_document_wrappers(cleaned)
    cleaned = extract_tikzpicture(cleaned)
    cleaned = remove_duplicate_tikz_environments(cleaned)
    cleaned = repair_option_lists(cleaned)
    cleaned = fix_duplicated_semicolons(cleaned)
    cleaned = remove_empty_nodes(cleaned)
    cleaned = ensure_draw_path_semicolons(cleaned)
    cleaned = close_obvious_missing_braces(cleaned)
    cleaned = remove_extra_blank_lines(cleaned)
    return cleaned.strip()


def validate_tikz(tikz: str) -> None:
    """Validate the normalized TikZ before passing it to pdflatex."""
    if not isinstance(tikz, str):
        raise TikzValidationError("TikZ code must be a string.")

    if "```" in tikz:
        raise TikzValidationError("Markdown code fences remain in the TikZ output.")
    if r"\documentclass" in tikz or r"\begin{document}" in tikz or r"\usepackage" in tikz:
        raise TikzValidationError("TikZ output must not contain LaTeX document wrappers or packages.")

    begin_matches = list(BEGIN_TIKZ_RE.finditer(tikz))
    end_count = tikz.count(END_TIKZ)
    if not begin_matches or end_count == 0:
        raise TikzValidationError("TikZ code must contain a complete tikzpicture environment.")
    if len(begin_matches) != 1:
        raise TikzValidationError("TikZ code must contain exactly one \\begin{tikzpicture}.")
    if end_count != 1:
        raise TikzValidationError("TikZ code must contain exactly one \\end{tikzpicture}.")
    if tikz.find(r"\begin{tikzpicture}") > tikz.find(END_TIKZ):
        raise TikzValidationError("\\end{tikzpicture} appears before \\begin{tikzpicture}.")

    validate_balanced_braces(tikz)
    validate_balanced_delimiter(tikz, "[", "]", "bracket")
    validate_balanced_delimiter(tikz, "(", ")", "parenthesis")
    validate_supported_commands(tikz)
    validate_duplicate_node_names(tikz)
    validate_empty_nodes(tikz)
    validate_coordinates(tikz)
    validate_node_commands(tikz)
    validate_draw_path_commands(tikz)


def remove_markdown_fences(text: str) -> str:
    """Remove markdown code fences and language labels from model output."""
    without_line_fences = MARKDOWN_FENCE_RE.sub("", text)
    return without_line_fences.replace("```latex", "").replace("```tex", "").replace("```tikz", "").replace("```", "")


def remove_latex_document_wrappers(text: str) -> str:
    """Remove full-document LaTeX wrappers from model output."""
    cleaned = DOCUMENTCLASS_RE.sub("", text)
    cleaned = USEPACKAGE_RE.sub("", cleaned)
    cleaned = cleaned.replace(r"\begin{document}", "")
    cleaned = cleaned.replace(r"\end{document}", "")
    return cleaned


def extract_tikzpicture(text: str) -> str:
    """Keep only one tikzpicture environment and discard surrounding prose."""
    begin_match = BEGIN_TIKZ_RE.search(text)
    if not begin_match:
        return remove_extra_blank_lines(text)

    end_index = text.find(END_TIKZ, begin_match.end())
    if end_index == -1:
        return remove_extra_blank_lines(text[begin_match.start() :])

    begin_line = begin_match.group(0).strip()
    body = text[begin_match.end() : end_index]
    body = BEGIN_TIKZ_RE.sub("", body)
    body = body.replace(END_TIKZ, "")
    body = remove_extra_blank_lines(body)
    return "\n".join([begin_line, body.strip(), END_TIKZ])


def remove_duplicate_tikz_environments(tikz: str) -> str:
    """Keep a single tikzpicture wrapper when the model duplicates markers."""
    begin_match = BEGIN_TIKZ_RE.search(tikz)
    if not begin_match:
        return tikz

    begin_line = begin_match.group(0).strip()
    body = tikz[begin_match.end() :]
    body = BEGIN_TIKZ_RE.sub("", body)
    body = body.replace(END_TIKZ, "")
    return "\n".join([begin_line, body.strip(), END_TIKZ])


def fix_duplicated_semicolons(tikz: str) -> str:
    """Collapse accidental duplicated TikZ semicolons."""
    return re.sub(r";\s*;+", ";", tikz)


def remove_empty_nodes(tikz: str) -> str:
    """Remove nodes with empty labels."""
    return EMPTY_NODE_RE.sub("", tikz)


def ensure_draw_path_semicolons(tikz: str) -> str:
    """Append semicolons before the next command when obvious."""
    command_re = re.compile(r"\\(?:draw|path|coordinate)\b")
    boundary_re = re.compile(r"\\(?:node|draw|path|coordinate)\b|\\end\{tikzpicture\}")
    pieces: list[str] = []
    cursor = 0

    for match in command_re.finditer(tikz):
        start = match.start()
        if start < cursor:
            continue

        boundary = boundary_re.search(tikz, match.end())
        end = boundary.start() if boundary else len(tikz)
        segment = tikz[start:end]
        pieces.append(tikz[cursor:start])
        trailing_whitespace = segment[len(segment.rstrip()) :]
        command_text = segment.rstrip()
        if ";" not in segment:
            command_text = f"{command_text};"
        pieces.append(f"{command_text}{trailing_whitespace}")
        cursor = end

    pieces.append(tikz[cursor:])
    return "".join(pieces)


def close_obvious_missing_braces(tikz: str) -> str:
    """Close a small number of missing braces before the tikzpicture ends."""
    depth = delimiter_depth(tikz, "{", "}")
    if depth <= 0 or depth > 2 or END_TIKZ not in tikz:
        return tikz

    return tikz.replace(END_TIKZ, f"{'}' * depth}\n{END_TIKZ}", 1)


def repair_option_lists(tikz: str) -> str:
    """Repair TikZ option lists by replacing common invalid Granite aliases."""
    pieces: list[str] = []
    index = 0

    while index < len(tikz):
        if tikz[index] != "[":
            pieces.append(tikz[index])
            index += 1
            continue

        close_index = find_matching_bracket(tikz, index)
        if close_index == -1:
            pieces.append(tikz[index])
            index += 1
            continue

        options = tikz[index + 1 : close_index]
        pieces.append("[")
        pieces.append(repair_options(options))
        pieces.append("]")
        index = close_index + 1

    return "".join(pieces)


def find_matching_bracket(text: str, open_index: int) -> int:
    """Find the matching closing bracket while respecting nested delimiters."""
    bracket_depth = 0
    brace_depth = 0
    paren_depth = 0

    for index in range(open_index, len(text)):
        character = text[index]
        if character == "{" and bracket_depth > 0:
            brace_depth += 1
        elif character == "}" and bracket_depth > 0 and brace_depth > 0:
            brace_depth -= 1
        elif character == "(" and bracket_depth > 0:
            paren_depth += 1
        elif character == ")" and bracket_depth > 0 and paren_depth > 0:
            paren_depth -= 1
        elif character == "[" and brace_depth == 0 and paren_depth == 0:
            bracket_depth += 1
        elif character == "]" and brace_depth == 0 and paren_depth == 0:
            bracket_depth -= 1
            if bracket_depth == 0:
                return index

    return -1


def repair_options(options: str) -> str:
    """Repair or remove unsupported top-level TikZ option keys."""
    repaired: list[str] = []

    for option in split_top_level_options(options):
        normalized = option.strip()
        if not normalized:
            continue

        replacement = repair_option(normalized)
        if replacement:
            for item in replacement:
                if item not in repaired:
                    repaired.append(item)

    return ", ".join(repaired)


def split_top_level_options(options: str) -> list[str]:
    """Split a TikZ option list on commas outside braces, brackets, and parentheses."""
    parts: list[str] = []
    start = 0
    brace_depth = 0
    bracket_depth = 0
    paren_depth = 0

    for index, character in enumerate(options):
        if character == "{":
            brace_depth += 1
        elif character == "}" and brace_depth > 0:
            brace_depth -= 1
        elif character == "[":
            bracket_depth += 1
        elif character == "]" and bracket_depth > 0:
            bracket_depth -= 1
        elif character == "(":
            paren_depth += 1
        elif character == ")" and paren_depth > 0:
            paren_depth -= 1
        elif character == "," and brace_depth == 0 and bracket_depth == 0 and paren_depth == 0:
            parts.append(options[start:index])
            start = index + 1

    parts.append(options[start:])
    return parts


def repair_option(option: str) -> tuple[str, ...]:
    """Return repaired TikZ options, or an empty tuple when an option is unsafe."""
    option_key = option.split("=", 1)[0].strip()
    option_key_lower = option_key.lower()
    option_lower = option.lower()

    if "/.style" in option_lower or "/.default" in option_lower:
        style_name = option.split("/", 1)[0].strip().lower()
        if style_name in UNSUPPORTED_TIKZ_KEYS:
            return ()
        return (option,)

    if option_lower in FLOWCHART_STYLE_REPLACEMENTS:
        return FLOWCHART_STYLE_REPLACEMENTS[option_lower]

    if option_key_lower == "shape" and "=" in option:
        shape_value = option.split("=", 1)[1].strip().lower()
        if shape_value in FLOWCHART_STYLE_REPLACEMENTS:
            return FLOWCHART_STYLE_REPLACEMENTS[shape_value]
        if shape_value in UNSUPPORTED_TIKZ_KEYS:
            return ()

    if option_key_lower in UNSUPPORTED_TIKZ_KEYS:
        return ()

    if "=" not in option and option_lower not in SUPPORTED_BARE_TIKZ_KEYS:
        return ()

    return (option,)


def remove_extra_blank_lines(text: str) -> str:
    """Trim trailing whitespace and collapse repeated blank lines."""
    normalized_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    compact_lines: list[str] = []
    previous_blank = False

    for line in normalized_lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        compact_lines.append(line)
        previous_blank = is_blank

    return "\n".join(compact_lines).strip()


def validate_balanced_braces(tikz: str) -> None:
    """Ensure curly braces are balanced outside escaped brace literals."""
    depth = 0
    for index, character in enumerate(tikz):
        if character == "{" and not is_escaped(tikz, index):
            depth += 1
        elif character == "}" and not is_escaped(tikz, index):
            depth -= 1
            if depth < 0:
                raise TikzValidationError("TikZ code has an unmatched closing brace.")

    if depth != 0:
        raise TikzValidationError("TikZ code has unmatched opening braces.")


def validate_balanced_delimiter(tikz: str, open_char: str, close_char: str, label: str) -> None:
    """Ensure a delimiter pair is balanced."""
    depth = delimiter_depth(tikz, open_char, close_char)
    if depth < 0:
        raise TikzValidationError(f"TikZ code has an unmatched closing {label}.")
    if depth > 0:
        raise TikzValidationError(f"TikZ code has unmatched opening {label}s.")


def delimiter_depth(text: str, open_char: str, close_char: str) -> int:
    """Return delimiter depth, or -1 when a closing delimiter appears first."""
    depth = 0
    for index, character in enumerate(text):
        if character == open_char and not is_escaped(text, index):
            depth += 1
        elif character == close_char and not is_escaped(text, index):
            depth -= 1
            if depth < 0:
                return -1
    return depth


def is_escaped(text: str, index: int) -> bool:
    """Return True when a character is preceded by an odd number of backslashes."""
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def validate_supported_commands(tikz: str) -> None:
    """Reject unsupported LaTeX commands inside generated TikZ."""
    for command in COMMAND_RE.findall(tikz):
        if command in DISALLOWED_TIKZ_COMMANDS:
            raise TikzValidationError(f"Unsupported command: \\{command}.")
        if command not in SUPPORTED_TIKZ_COMMANDS and not command.startswith("tikz"):
            raise TikzValidationError(f"Unsupported command: \\{command}.")


def validate_duplicate_node_names(tikz: str) -> None:
    """Ensure TikZ node identifiers are unique."""
    node_names = NODE_NAME_RE.findall(tikz)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in node_names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)

    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise TikzValidationError(f"Duplicate node names: {duplicate_list}.")


def validate_empty_nodes(tikz: str) -> None:
    """Reject empty node labels after repair."""
    if EMPTY_NODE_RE.search(tikz):
        raise TikzValidationError("TikZ code contains empty nodes.")


def validate_coordinates(tikz: str) -> None:
    """Validate simple numeric coordinate pairs."""
    for match in COORDINATE_RE.finditer(tikz):
        coordinate = match.group(1)
        parts = [part.strip() for part in coordinate.split(",", 1)]
        if len(parts) != 2:
            raise TikzValidationError(f"Invalid coordinate: ({coordinate}).")
        if not all(is_valid_coordinate_value(part) for part in parts):
            raise TikzValidationError(f"Invalid coordinate: ({coordinate}).")


def is_valid_coordinate_value(value: str) -> bool:
    """Return True for numeric TikZ coordinate values with optional units."""
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:cm|mm|pt|in)?", value))


def validate_node_commands(tikz: str) -> None:
    """Ensure each node command is terminated and has balanced local delimiters."""
    for match in re.finditer(r"\\node\b", tikz):
        end_index = find_command_semicolon(tikz, match.start())
        if end_index == -1:
            raise TikzValidationError("A \\node command is missing a terminating semicolon.")

        command = tikz[match.start() : end_index + 1]
        if "{" not in command or "}" not in command:
            raise TikzValidationError("A \\node command must include node text inside braces.")
        if not delimiters_are_balanced(command):
            raise TikzValidationError("A \\node command has unbalanced delimiters.")


def validate_draw_path_commands(tikz: str) -> None:
    """Ensure draw, path, and coordinate commands are terminated."""
    for command_name in ("draw", "path", "coordinate"):
        for match in re.finditer(rf"\\{command_name}\b", tikz):
            if find_command_semicolon(tikz, match.start()) == -1:
                raise TikzValidationError(f"A \\{command_name} command is missing a terminating semicolon.")


def find_command_semicolon(text: str, start_index: int) -> int:
    """Find the command-ending semicolon outside braces, brackets, and parentheses."""
    brace_depth = 0
    bracket_depth = 0
    paren_depth = 0

    for index in range(start_index, len(text)):
        character = text[index]
        if character == "{" and not is_escaped(text, index):
            brace_depth += 1
        elif character == "}" and not is_escaped(text, index) and brace_depth > 0:
            brace_depth -= 1
        elif character == "[":
            bracket_depth += 1
        elif character == "]" and bracket_depth > 0:
            bracket_depth -= 1
        elif character == "(":
            paren_depth += 1
        elif character == ")" and paren_depth > 0:
            paren_depth -= 1
        elif character == ";" and brace_depth == 0 and bracket_depth == 0 and paren_depth == 0:
            return index

    return -1


def delimiters_are_balanced(text: str) -> bool:
    """Return True when common TikZ command delimiters are balanced."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack: list[str] = []

    for index, character in enumerate(text):
        if character in pairs and not is_escaped(text, index):
            stack.append(pairs[character])
        elif character in pairs.values() and not is_escaped(text, index):
            if not stack or stack.pop() != character:
                return False

    return not stack


def get_allowed_extension(filename: str) -> str:
    """Validate and return the uploaded image extension without a leading dot."""
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise ApiError(f"Unsupported image type. Allowed extensions: {allowed}.", 415)

    return extension


def get_upload_size(uploaded_file: FileStorage) -> int:
    """Return upload size in bytes without consuming the stream."""
    stream = uploaded_file.stream
    current_position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current_position)
    return size


def unique_filename(original_filename: str, extension: str) -> str:
    """Create a safe unique filename while preserving the image extension."""
    stem = Path(secure_filename(original_filename)).stem or "upload"
    return f"{stem}-{uuid4().hex}.{extension}"


def current_request_timeout() -> int:
    """Return configured timeout for the active Flask app."""
    return int(current_app_config("REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT_SECONDS))


def current_app_config(key: str, default: Any) -> Any:
    """Read a Flask config value when an app context exists."""
    try:
        return current_app.config[key]
    except RuntimeError:
        return default


def error_response(message: str, status_code: int) -> tuple[Response, int]:
    """Build a JSON error response using the allowed API status codes."""
    normalized_status = normalize_status_code(status_code)
    return jsonify({"success": False, "error": message}), normalized_status


def normalize_status_code(status_code: int | None) -> int:
    """Limit API errors to the documented status code set."""
    if status_code in {400, 404, 405, 413, 415, 429, 500}:
        return status_code
    return 500


def http_error_message(status_code: int) -> str:
    """Return safe client-facing messages for supported HTTP errors."""
    messages = {
        400: "Invalid request.",
        404: "Endpoint not found.",
        405: "Method not allowed.",
        413: "Uploaded file exceeds the configured size limit.",
        415: "Unsupported media type.",
        429: "Rate limit exceeded. Please try again later.",
        500: "An unexpected server error occurred.",
    }
    return messages.get(status_code, messages[500])


def positive_int_env(name: str, default: int) -> int:
    """Read a positive integer environment variable."""
    value = os.getenv(name, "").strip()
    if not value:
        return default

    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer.") from error

    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer.")

    return parsed


app = create_app()

if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    app.run(
        host=host,
        port=port,
        debug=debug,
    )
    
