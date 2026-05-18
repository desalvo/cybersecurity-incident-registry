FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    UPLOAD_DIR=/data/uploads \
    LOGO_DIR=/data/logo \
    FORM_TEMPLATE_DIR=/data/form_templates \
    SSL_DIR=/data/ssl \
    SSL_PORT=8443 \
    SSL_ENABLED=0 \
    PORT=8000 \
    WEB_CONCURRENCY=1

WORKDIR /app

# Debian 13 Trixie runtime dependencies only.
# The application uses binary Python wheels, so build-essential/libpq-dev are not required.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        libreoffice-writer \
        libreoffice-core; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN set -eux; \
    python -m pip install --upgrade pip setuptools wheel; \
    python -m pip install --only-binary=:all: -r requirements.txt; \
    rm -rf /root/.cache/pip

COPY . .

RUN set -eux; \
    mkdir -p /data/uploads /data/logo /data/form_templates /data/ssl; \
    useradd --create-home --shell /usr/sbin/nologin appuser; \
    chown -R appuser:appuser /app /data

USER appuser
EXPOSE 8000 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["/app/docker-entrypoint.sh"]
