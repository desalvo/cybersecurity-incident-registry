FROM python:3.12.14-slim-trixie AS python-deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .

# Build an isolated application virtualenv. Runtime packaging tools are removed
# after dependency installation because the service never installs packages at runtime.
RUN set -eux; \
    python -m venv /opt/cir-venv; \
    /opt/cir-venv/bin/python -m pip install --upgrade pip setuptools wheel; \
    /opt/cir-venv/bin/python -m pip install --only-binary=:all: -r requirements.txt; \
    /opt/cir-venv/bin/python -m pip check; \
    /opt/cir-venv/bin/python -m pip uninstall -y pip setuptools wheel; \
    rm -rf /root/.cache/pip /opt/cir-venv/lib/python*/site-packages/pip* /opt/cir-venv/lib/python*/site-packages/setuptools* /opt/cir-venv/lib/python*/site-packages/wheel*

FROM python:3.12.14-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/cir-venv/bin:$PATH \
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

# Debian 13 Trixie runtime dependencies only. LibreOffice uses the no-GUI
# variant for headless document conversion. --no-install-recommends prevents
# optional desktop/Java integrations from entering the service image.
RUN set -eux; \
    apt-get update; \
    apt-get upgrade -y; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        gosu \
        fonts-dejavu-core \
        libreoffice-writer-nogui; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*; \
    # pip/setuptools/wheel are build tooling, not runtime dependencies. The
    # official Python base embeds an SBOM under pip/_vendor which scanners can
    # otherwise mistake for installed vulnerable packages.
    rm -rf \
        /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
        /usr/local/lib/python3.12/site-packages/pip \
        /usr/local/lib/python3.12/site-packages/pip-* \
        /usr/local/lib/python3.12/site-packages/setuptools \
        /usr/local/lib/python3.12/site-packages/setuptools-* \
        /usr/local/lib/python3.12/site-packages/wheel \
        /usr/local/lib/python3.12/site-packages/wheel-*

COPY --from=python-deps /opt/cir-venv /opt/cir-venv
COPY . .

RUN set -eux; \
    chmod 0755 /app/docker-entrypoint.sh; \
    groupadd --gid 10001 appuser; \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser; \
    mkdir -p /data/uploads /data/logo /data/form_templates /data/sso_logos /data/ssl /data/backups /data/ai_chatbot_docs; \
    chown -R appuser:appuser /app /data /opt/cir-venv

USER root
EXPOSE 8000 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import http.client; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=4); c.request('GET','/healthz'); r=c.getresponse(); raise SystemExit(0 if 200 <= r.status < 400 else 1)"

CMD ["/app/docker-entrypoint.sh"]
