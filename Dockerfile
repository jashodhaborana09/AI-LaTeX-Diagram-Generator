FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    WORKERS=2 \
    LOG_LEVEL=INFO \
    MAX_PROMPT_LENGTH=3000 \
    MAX_UPLOAD_SIZE=10485760 \
    REQUEST_TIMEOUT=60 \
    VALIDATE_ENV_ON_START=true \
    GUNICORN_GRACEFUL_TIMEOUT=30 \
    GUNICORN_KEEPALIVE=5 \
    GUNICORN_WORKER_CLASS=sync

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-pictures \
    texlive-fonts-recommended \
    lmodern \
    poppler-utils \
    ghostscript \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --default-timeout=600 -r requirements.txt

COPY . .

RUN mkdir -p data/generated/images \
             data/generated/pdf \
             data/generated/latex \
             data/generated/work \
             data/uploads \
             data/processed \
             uploads \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl --fail "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["sh", "-c", "python scripts/validate_env.py && gunicorn --config gunicorn.conf.py backend.app:app"]
