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


def test_dockerfile_forces_entrypoint_executable_before_non_root_user() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    chmod_pos = dockerfile.find("chmod 0755 /app/docker-entrypoint.sh")
    user_pos = dockerfile.find("USER appuser")
    cmd_pos = dockerfile.find('CMD ["/app/docker-entrypoint.sh"]')
    assert chmod_pos != -1, "Dockerfile must chmod the entrypoint during image build"
    assert user_pos != -1 and chmod_pos < user_pos
    assert cmd_pos != -1 and user_pos < cmd_pos
