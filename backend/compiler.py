"""Compile TikZ code into LaTeX, PDF, and PNG preview files."""

from __future__ import annotations

import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "generated"
DEFAULT_TIMEOUT_SECONDS = 45
logger = logging.getLogger(__name__)


class CompileError(RuntimeError):
    """Raised when LaTeX compilation or preview generation fails."""

    def __init__(self, message: str, log_path: Path | None = None, details: str = "") -> None:
        super().__init__(message)
        self.log_path = log_path
        self.details = details


@dataclass(frozen=True)
class CompileResult:
    """Filesystem paths produced by a successful TikZ compilation."""

    job_id: str
    tex_path: Path
    pdf_path: Path
    png_path: Path
    log_path: Path
    work_dir: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id,
            "tex_path": str(self.tex_path),
            "pdf_path": str(self.pdf_path),
            "png_path": str(self.png_path),
            "log_path": str(self.log_path),
            "work_dir": str(self.work_dir),
        }


def compile_tikz(
    tikz_code: str,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    job_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, str]:
    """Compile TikZ code and return generated file paths."""
    clean_tikz = validate_tikz_code(tikz_code)
    safe_job_id = sanitize_job_id(job_id or f"diagram_{uuid.uuid4().hex}")
    paths = create_output_paths(output_dir, safe_job_id)

    tex_document = build_latex_document(clean_tikz)
    write_text_file(paths["tex_path"], tex_document)

    logger.info("PDF compilation started.")
    compile_pdf(paths["work_dir"], paths["tex_path"], paths["pdf_path"], timeout_seconds)
    if not paths["pdf_path"].exists():
        raise CompileError(
            "pdflatex finished without producing a PDF.",
            log_path=paths["log_path"],
            details=read_log_tail(paths["log_path"]),
        )
    logger.info("PDF compilation completed.")

    logger.info("PNG generation started.")
    generate_png_preview(paths["pdf_path"], paths["png_path"], timeout_seconds)
    if not paths["png_path"].exists():
        raise CompileError("PNG preview generation finished without producing an image.")
    logger.info("PNG generation completed.")

    result = CompileResult(
        job_id=safe_job_id,
        tex_path=paths["tex_path"],
        pdf_path=paths["pdf_path"],
        png_path=paths["png_path"],
        log_path=paths["log_path"],
        work_dir=paths["work_dir"],
    )
    return result.to_dict()


def validate_tikz_code(tikz_code: str) -> str:
    """Validate and normalize TikZ code."""
    if not isinstance(tikz_code, str):
        raise TypeError("tikz_code must be a string.")

    clean_tikz = tikz_code.strip()
    if not clean_tikz:
        raise ValueError("tikz_code must not be empty.")

    if "\\begin{tikzpicture}" not in clean_tikz or "\\end{tikzpicture}" not in clean_tikz:
        raise ValueError("tikz_code must contain a complete tikzpicture environment.")

    return clean_tikz


def create_output_paths(output_dir: str | Path, job_id: str) -> dict[str, Path]:
    """Create output directories and return canonical file paths."""
    root = Path(output_dir)
    tex_dir = root / "latex"
    pdf_dir = root / "pdf"
    image_dir = root / "images"
    work_dir = root / "work" / job_id

    for directory in (tex_dir, pdf_dir, image_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return {
        "tex_path": tex_dir / f"{job_id}.tex",
        "pdf_path": pdf_dir / f"{job_id}.pdf",
        "png_path": image_dir / f"{job_id}.png",
        "log_path": work_dir / f"{job_id}.log",
        "work_dir": work_dir,
    }


def build_latex_document(tikz_code: str) -> str:
    """Wrap TikZ code in a complete standalone LaTeX document."""
    return "\n".join(
        [
            r"\documentclass[tikz,border=8pt]{standalone}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{lmodern}",
            r"\usepackage{xcolor}",
            r"\usepackage{tikz}",
            r"\usetikzlibrary{arrows.meta,positioning,shapes.geometric,shapes.multipart,fit,calc,backgrounds}",
            r"\begin{document}",
            tikz_code,
            r"\end{document}",
            "",
        ]
    )


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text content to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def compile_pdf(work_dir: Path, tex_path: Path, pdf_path: Path, timeout_seconds: int) -> None:
    """Run pdflatex and copy generated artifacts into their public directories."""
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise CompileError("pdflatex was not found. Install a LaTeX distribution and add pdflatex to PATH.")

    if not tex_path.exists():
        raise CompileError(f"Expected LaTeX source was not found: {tex_path}")

    working_tex = work_dir / tex_path.name
    shutil.copy2(tex_path, working_tex)

    command = [
        pdflatex,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={working_tex.stem}",
        working_tex.name,
    ]
    completed = run_command(command, cwd=work_dir, timeout_seconds=timeout_seconds)
    log_path = work_dir / f"{working_tex.stem}.log"
    logger = logging.getLogger(__name__)
    if completed.returncode != 0:
        error_details = extract_latex_errors(
            log_path,
            completed.stdout,
            completed.stderr,
        )

        logger.error("LaTeX compilation failed:\n%s", error_details)

        raise CompileError(
            "pdflatex failed to compile the TikZ document.",
            log_path=log_path,
            details=error_details,
        )

    generated_pdf = work_dir / f"{working_tex.stem}.pdf"
    if generated_pdf.exists():
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated_pdf, pdf_path)


def generate_png_preview(pdf_path: Path, png_path: Path, timeout_seconds: int) -> None:
    """Generate a PNG preview from a compiled PDF."""
    png_path.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("pdftoppm"):
        prefix = png_path.with_suffix("")
        command = [
            shutil.which("pdftoppm") or "pdftoppm",
            "-png",
            "-singlefile",
            "-r",
            "180",
            str(pdf_path),
            str(prefix),
        ]
        completed = run_command(command, cwd=pdf_path.parent, timeout_seconds=timeout_seconds)
        if completed.returncode == 0 and png_path.exists():
            return
        raise CompileError(
            "pdftoppm failed to generate the PNG preview.",
            details=(completed.stderr or completed.stdout).strip(),
        )

    magick = shutil.which("magick")
    if magick:
        command = [
            magick,
            "-density",
            "180",
            str(pdf_path),
            "-quality",
            "95",
            str(png_path),
        ]
        completed = run_command(command, cwd=pdf_path.parent, timeout_seconds=timeout_seconds)
        if completed.returncode == 0 and png_path.exists():
            return
        raise CompileError(
            "ImageMagick failed to generate the PNG preview.",
            details=(completed.stderr or completed.stdout).strip(),
        )

    raise CompileError(
        "No PDF-to-PNG converter was found. Install pdftoppm or ImageMagick to generate previews."
    )


def run_command(
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with captured output."""
    return subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def extract_latex_errors(log_path: Path, stdout: str, stderr: str) -> str:
    """Extract useful LaTeX error details from logs and command output."""
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    lines = log_text.splitlines()
    error_lines: list[str] = []

    for index, line in enumerate(lines):
        if line.startswith("!") or "LaTeX Error" in line:
            start = max(0, index - 2)
            end = min(len(lines), index + 6)
            error_lines.extend(lines[start:end])
            break

    if not error_lines:
        combined_output = "\n".join(part for part in (stdout, stderr) if part.strip())
        error_lines = combined_output.splitlines()[-24:]

    return "\n".join(error_lines).strip()


def read_log_tail(log_path: Path, line_count: int = 40) -> str:
    """Read the last lines of a LaTeX log file."""
    if not log_path.exists():
        return ""

    return "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-line_count:])


def sanitize_job_id(job_id: str) -> str:
    """Create a filesystem-safe job identifier."""
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in job_id)
    safe = safe.strip("._-")
    if not safe:
        raise ValueError("job_id must contain at least one alphanumeric character.")
    return safe[:80]
