# Contributing

Thanks for helping improve AI-LaTeX Diagram Generator. This project is intended to stay production-ready, easy to run locally, and compatible with the existing public API.

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and fill in IBM watsonx.ai credentials for live generation.

## Local Checks

Run these before opening a pull request:

```bash
python -m py_compile backend/app.py backend/compiler.py backend/granite.py backend/image_processor.py backend/prompt_template.py backend/tikz_generator.py scripts/validate_env.py gunicorn.conf.py
python -m pytest
docker build -t ai-latex-diagram-generator:local .
```

## Contribution Guidelines

- Do not change existing API routes or response shapes without documenting a breaking change.
- Keep backend functions typed and small.
- Add or update tests for behavior changes.
- Keep generated artifacts, credentials, and local `.env` files out of commits.
- Prefer focused pull requests over broad rewrites.

## Pull Requests

Use the pull request template and include:

- What changed.
- Why it changed.
- How it was tested.
- Screenshots for visible frontend changes.
- Any deployment or environment variable impact.
