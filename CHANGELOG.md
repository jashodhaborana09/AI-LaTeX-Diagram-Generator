# Changelog

## Version 1.0.0

Initial production-ready public release of AI-LaTeX Diagram Generator.

### Features

- Natural-language TikZ diagram generation with IBM Granite on watsonx.ai.
- Diagram refinement from existing TikZ plus user instructions.
- Reference image upload support for PNG, JPG, and JPEG files.
- Generated LaTeX, PDF, and PNG artifact routes.

### Backend

- Flask API with structured JSON responses.
- Prompt and upload validation.
- TikZ cleanup and validation before compilation.
- Centralized error handling for production-safe client responses.
- Structured logging, request timing, rate limiting, and security headers.

### Frontend

- Completed browser interface for prompt entry, upload, preview, refinement, and exports.
- Static HTML, CSS, and JavaScript frontend served separately from the Flask API.

### Docker

- Gunicorn production startup.
- Render-compatible `PORT` binding.
- Configurable workers and request timeout.
- LaTeX and Poppler dependencies included for PDF and PNG generation.

### Deployment

- GitHub Actions CI for syntax checks, tests, Docker build, and container health verification.
- Docker Compose configuration for local production-style runs.
- Nginx reverse proxy configuration for frontend serving and API proxying.
- Health endpoint for platform readiness checks.

### Release Checklist

- GitHub Actions CI passes on push and pull request.
- Docker image builds successfully.
- Container starts and `/health` returns HTTP 200.
- Docker Compose configuration validates.
- README, architecture docs, API reference, roadmap, security policy, and contribution guide are present.
- MIT license is included.

### Deployment Checklist

- Required IBM watsonx.ai environment variables are configured.
- `VALIDATE_ENV_ON_START=true` is enabled for production.
- Runtime platform provides or maps `PORT`.
- `/health` is configured as the readiness endpoint.
- Logs are collected from stdout and stderr.
- Persistent storage is configured when generated artifacts must survive container replacement.

### Known Limitations

- Image uploads are stored locally and are not connected to persistent cloud storage.
- Rate limiting uses in-memory storage unless `RATELIMIT_STORAGE_URI` is configured.
- LaTeX compilation depends on the installed TeX packages included in the runtime image.
- IBM watsonx.ai credentials and project access are required for live diagram generation.
