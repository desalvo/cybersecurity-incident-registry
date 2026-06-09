FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    UPLOAD_DIR=/data/uploads \
    LOGO_DIR=/data/logo \
    FORM_TEMPLATE_DIR=/data/form_templates \
    SSO_LOGO_DIR=/data/sso_logos \
    BACKUP_DIR=/data/backups \
    AI_CHATBOT_DOC_DIR=/data/ai_chatbot_docs \
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
        gosu \
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
    chmod 0755 /app/docker-entrypoint.sh; \
    groupadd --gid 10001 appuser; \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser; \
    mkdir -p /data/uploads /data/logo /data/form_templates /data/sso_logos /data/ssl /data/backups /data/ai_chatbot_docs; \
    chown -R appuser:appuser /app /data

USER root
EXPOSE 8000 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["/app/docker-entrypoint.sh"]
