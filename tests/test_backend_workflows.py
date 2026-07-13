"""Automated tests for backend upload, generation, refinement, compile, and download flows."""

from __future__ import annotations

import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from backend import app as app_module
from backend import compiler, granite


SAMPLE_TIKZ = r"""
\begin{tikzpicture}
\node[draw] (database) at (0,0) {Database};
\node[draw] (api) at (3,0) {API};
\draw[->] (database) -- (api);
\end{tikzpicture}
""".strip()


class FakeGraniteModel:
    """Simple fake Watsonx model used to mock IBM Granite responses."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> dict[str, str]:
        self.prompts.append(prompt)
        return {"generated_text": self.response_text}


@pytest.fixture()
def client():
    return app_module.app.test_client()


def test_upload_accepts_supported_image(client):
    response = client.post(
        "/upload",
        data={
            "file": (
                BytesIO(b"\x89PNG\r\n\x1a\nsample-image-bytes"),
                "diagram.png",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["filename"].endswith(".png")
    assert payload["message"] == "Upload successful"


def test_generate_tikz_uses_mocked_granite_response(monkeypatch):
    fake_model = FakeGraniteModel(SAMPLE_TIKZ)
    settings = granite.WatsonxSettings(
        api_key="test-api-key",
        project_id="test-project-id",
        url="https://example.com",
        max_retries=1,
    )

    monkeypatch.setattr(granite, "_load_settings", lambda: settings)
    monkeypatch.setattr(granite, "_build_model", lambda _settings: fake_model)

    tikz_code = granite.generate_tikz("Create an API to database architecture diagram.")

    assert tikz_code == SAMPLE_TIKZ
    assert fake_model.prompts
    assert "Return only TikZ code" in fake_model.prompts[0]


def test_refine_tikz_sends_existing_code_and_instruction_to_mocked_granite(monkeypatch):
    refined_tikz = SAMPLE_TIKZ.replace("at (0,0)", "at (-2,0)")
    fake_model = FakeGraniteModel(refined_tikz)
    settings = granite.WatsonxSettings(
        api_key="test-api-key",
        project_id="test-project-id",
        url="https://example.com",
        max_retries=1,
    )

    monkeypatch.setattr(granite, "_load_settings", lambda: settings)
    monkeypatch.setattr(granite, "_build_model", lambda _settings: fake_model)

    tikz_code = granite.refine_tikz(SAMPLE_TIKZ, "Move database left")

    assert tikz_code == refined_tikz
    assert "(database)" in tikz_code
    assert "Move database left" in fake_model.prompts[0]
    assert SAMPLE_TIKZ in fake_model.prompts[0]
    assert "Preserve all existing node names" in fake_model.prompts[0]


def test_compile_tikz_writes_tex_pdf_and_png_with_mocked_tools(tmp_path, monkeypatch):
    def fake_which(command: str) -> str | None:
        if command in {"pdflatex", "pdftoppm"}:
            return command
        return None

    def fake_run_command(command: list[str], cwd: Path, timeout_seconds: int):
        if command[0] == "pdflatex":
            job_name = next(part for part in command if part.startswith("-jobname=")).split("=", 1)[1]
            (cwd / f"{job_name}.pdf").write_bytes(b"%PDF-1.4 fake pdf")
            (cwd / f"{job_name}.log").write_text("Compilation successful", encoding="utf-8")
        elif command[0] == "pdftoppm":
            png_path = Path(f"{command[-1]}.png")
            png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake png")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(compiler.shutil, "which", fake_which)
    monkeypatch.setattr(compiler, "run_command", fake_run_command)

    result = compiler.compile_tikz(
        SAMPLE_TIKZ,
        output_dir=tmp_path,
        job_id="compile_test",
    )

    assert Path(result["tex_path"]).exists()
    assert Path(result["pdf_path"]).exists()
    assert Path(result["png_path"]).exists()
    assert Path(result["tex_path"]).read_text(encoding="utf-8").startswith(
        r"\documentclass[tikz,border=8pt]{standalone}"
    )


def test_generate_returns_frontend_ready_artifact_urls(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "generate_tikz", lambda _prompt: SAMPLE_TIKZ)
    monkeypatch.setitem(app_module.app.config, "GENERATED_FOLDER", str(tmp_path))
    app_module.ensure_directories(app_module.app)

    def fake_compile_tikz(tikz: str, output_dir: str | Path, job_id=None, timeout_seconds: int = 45):
        output_root = Path(output_dir)
        job = "frontend_contract"
        pdf_path = output_root / "pdf" / f"{job}.pdf"
        png_path = output_root / "images" / f"{job}.png"
        tex_path = output_root / "latex" / f"{job}.tex"
        work_dir = output_root / "work" / job
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf")
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake png")
        tex_path.write_text(tikz, encoding="utf-8")
        return {
            "job_id": job,
            "tex_path": str(tex_path),
            "pdf_path": str(pdf_path),
            "png_path": str(png_path),
            "log_path": str(work_dir / f"{job}.log"),
            "work_dir": str(work_dir),
        }

    monkeypatch.setattr(app_module, "compile_tikz", fake_compile_tikz)

    response = client.post("/generate", json={"prompt": "Create a diagram"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {
        "success": True,
        "tikz": SAMPLE_TIKZ,
        "pdf": "/generated/pdf/frontend_contract.pdf",
        "png": "/generated/images/frontend_contract.png",
        "tex": "/generated/latex/frontend_contract.tex",
        "job_id": "frontend_contract",
        "message": "Generation successful",
    }


def test_refine_accepts_frontend_payload_shape(client, tmp_path, monkeypatch):
    refined_tikz = SAMPLE_TIKZ.replace("{API}", "{Refined API}")
    captured_prompt: dict[str, str] = {}

    monkeypatch.setitem(app_module.app.config, "GENERATED_FOLDER", str(tmp_path))
    app_module.ensure_directories(app_module.app)

    def fake_generate_tikz(prompt: str) -> str:
        captured_prompt["value"] = prompt
        return refined_tikz

    def fake_compile_tikz(tikz: str, output_dir: str | Path, job_id=None, timeout_seconds: int = 45):
        output_root = Path(output_dir)
        job = "refine_contract"
        pdf_path = output_root / "pdf" / f"{job}.pdf"
        png_path = output_root / "images" / f"{job}.png"
        tex_path = output_root / "latex" / f"{job}.tex"
        work_dir = output_root / "work" / job
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 fake pdf")
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfake png")
        tex_path.write_text(tikz, encoding="utf-8")
        return {
            "job_id": job,
            "tex_path": str(tex_path),
            "pdf_path": str(pdf_path),
            "png_path": str(png_path),
            "log_path": str(work_dir / f"{job}.log"),
            "work_dir": str(work_dir),
        }

    monkeypatch.setattr(app_module, "generate_tikz", fake_generate_tikz)
    monkeypatch.setattr(app_module, "compile_tikz", fake_compile_tikz)

    response = client.post(
        "/refine",
        json={
            "prompt": "Original diagram prompt",
            "tikz": SAMPLE_TIKZ,
            "instruction": "Rename API node",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["tikz"] == refined_tikz
    assert payload["png"] == "/generated/images/refine_contract.png"
    assert "Rename API node" in captured_prompt["value"]
    assert SAMPLE_TIKZ in captured_prompt["value"]


def test_generated_asset_routes_serve_pdf_png_and_tex(client, tmp_path, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "GENERATED_FOLDER", str(tmp_path))
    app_module.ensure_directories(app_module.app)

    (tmp_path / "pdf" / "download_test.pdf").write_bytes(b"%PDF-1.4 fake pdf")
    (tmp_path / "images" / "download_test.png").write_bytes(b"\x89PNG\r\n\x1a\nfake png")
    (tmp_path / "latex" / "download_test.tex").write_text(SAMPLE_TIKZ, encoding="utf-8")

    pdf_response = client.get("/generated/pdf/download_test.pdf")
    png_response = client.get("/generated/images/download_test.png")
    tex_response = client.get("/generated/latex/download_test.tex")

    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == "application/pdf"
    assert pdf_response.data == b"%PDF-1.4 fake pdf"

    assert png_response.status_code == 200
    assert png_response.mimetype == "image/png"
    assert png_response.data.startswith(b"\x89PNG")

    assert tex_response.status_code == 200
    assert tex_response.data.decode("utf-8").splitlines() == SAMPLE_TIKZ.splitlines()
