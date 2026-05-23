# Manual AGID compliance runner image.
# Build from the project root:
#   docker build --no-cache -f compliance/agid/Dockerfile -t cir-agid-compliance .
# Run from the project root, saving evidence in the current package:
#   docker run --rm -v "$PWD/compliance/agid:/results" cir-agid-compliance
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AGID_PIP_AUDIT_TIMEOUT=300 \
    AGID_PIP_AUDIT_SOCKET_TIMEOUT=10 \
    VIRTUAL_ENV=/opt/agid-venv \
    PATH=/opt/agid-venv/bin:$PATH

WORKDIR /project

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash ca-certificates curl libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
RUN python -m venv /opt/agid-venv \
    && /opt/agid-venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/agid-venv/bin/python -m pip install -r requirements-dev.txt \
    && /opt/agid-venv/bin/python -m pip install 'bandit==1.7.10' 'pip-audit>=2.7,<3' \
    && /opt/agid-venv/bin/python -m bandit --version \
    && /opt/agid-venv/bin/python -m pip_audit --version

COPY . /project
RUN chmod +x /project/compliance/agid/run_container_agid_compliance.sh \
    /project/compliance/agid/run_docker_agid_compliance.sh \
    /project/compliance/agid/run_agid_compliance_docker.sh \
    /project/scripts/run_agid_compliance.sh || true

VOLUME ["/results"]
ENTRYPOINT ["/project/compliance/agid/run_container_agid_compliance.sh"]
