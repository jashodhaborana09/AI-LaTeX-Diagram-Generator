# GitHub Release Checklist

Use this checklist before publishing version `1.0.0`.

## Code

- [ ] `python -m py_compile backend/app.py backend/compiler.py backend/granite.py backend/image_processor.py backend/prompt_template.py backend/tikz_generator.py scripts/validate_env.py gunicorn.conf.py`
- [ ] `python -m pytest`
- [ ] No debug prints are present.
- [ ] No secrets are committed.
- [ ] No backend API route or response contract changed unexpectedly.

## Docker

- [ ] `docker build -t ai-latex-diagram-generator:1.0.0 .`
- [ ] Container starts successfully.
- [ ] `/health` returns HTTP `200`.
- [ ] Docker Compose config validates.
- [ ] Docker Compose stack starts with backend and Nginx.

## Documentation

- [ ] README badges render.
- [ ] README links resolve.
- [ ] `SYSTEM_ARCHITECTURE.md` diagrams render on GitHub.
- [ ] `API_REFERENCE.md` examples match current API responses.
- [ ] `CHANGELOG.md` includes version `1.0.0` release notes.
- [ ] `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `ROADMAP.md`, and `CODE_OF_CONDUCT.md` are present.

## GitHub

- [ ] GitHub Actions workflow passes.
- [ ] Bug report and feature request templates are available.
- [ ] Pull request template is available.
- [ ] Release tag is created as `v1.0.0`.
- [ ] Release notes include feature, deployment, and known limitation summaries.
