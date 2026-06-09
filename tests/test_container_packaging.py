"""Container packaging regression tests."""
from __future__ import annotations

import os
import stat
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_docker_entrypoint_is_executable_in_source_tree() -> None:
    entrypoint = PROJECT_ROOT / "docker-entrypoint.sh"
    mode = entrypoint.stat().st_mode
    assert mode & stat.S_IXUSR, "docker-entrypoint.sh must be executable by owner"
    assert mode & stat.S_IXGRP, "docker-entrypoint.sh must be executable by group"
    assert mode & stat.S_IXOTH, "docker-entrypoint.sh must be executable by others"
    assert os.access(entrypoint, os.X_OK)


def test_dockerfile_prepares_named_volumes_before_dropping_privileges() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "gosu" in dockerfile, "Docker image must include gosu for root-to-appuser startup drop"
    assert "--uid 10001" in dockerfile and "--gid 10001" in dockerfile
    assert "USER root" in dockerfile, "Entrypoint must start as root so fresh named volumes can be chowned"
    assert 'CMD ["/app/docker-entrypoint.sh"]' in dockerfile


def test_entrypoint_chowns_persistent_dirs_and_reexecs_as_appuser() -> None:
    entrypoint = (PROJECT_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    for env_name in ("UPLOAD_DIR", "LOGO_DIR", "FORM_TEMPLATE_DIR", "SSO_LOGO_DIR", "SSL_DIR", "BACKUP_DIR", "AI_CHATBOT_DOC_DIR"):
        assert env_name in entrypoint
    assert 'chown -R "${APP_UID}:${APP_GID}"' in entrypoint
    assert "seed_persistent_assets" in entrypoint
    assert "CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE" in entrypoint
    assert 'exec gosu "${APP_USER}" "$0" --as-appuser' in entrypoint


def test_compose_defaults_to_published_image_and_has_build_override() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    override = (PROJECT_ROOT / "docker-compose.build.yml").read_text(encoding="utf-8")
    assert "desalvo/cybersecurity-incident-registry:latest" in compose
    assert "CIR_DISABLE_CSRF" in compose
    assert "APP_UID" in compose and "APP_GID" in compose
    assert "AI_CHATBOT_DOC_DIR" in compose
    assert "CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE" in compose
    assert "build:" in override and "dockerfile: Dockerfile" in override


def test_kubernetes_prepares_pvcs_for_non_root_container_and_exposes_csrf_flag() -> None:
    deployment = (PROJECT_ROOT / "k8s" / "deployment.yaml").read_text(encoding="utf-8")
    pvc = (PROJECT_ROOT / "k8s" / "pvc.yaml").read_text(encoding="utf-8")
    kustomization = (PROJECT_ROOT / "k8s" / "kustomization.yaml").read_text(encoding="utf-8")
    assert "prepare-persistent-volumes" in deployment
    assert "chown -R 10001:10001" in deployment
    assert "runAsUser: 10001" in deployment
    assert "fsGroup: 10001" in deployment
    assert "CIR_DISABLE_CSRF" in deployment
    assert "AI_CHATBOT_DOC_DIR" in deployment
    assert "cir-ai-chatbot-docs" in pvc
    assert "desalvo/cybersecurity-incident-registry:latest" in deployment
    assert "cir-logo" in pvc
    assert "newTag: latest" in kustomization
