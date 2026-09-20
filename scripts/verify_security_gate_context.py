#!/usr/bin/env python3
"""Verify the runtime-hardening assumptions required by CIR's temporary OS-CVE acceptance."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

def require(text: str, pattern: str, label: str, errors: list[str]) -> None:
    if not re.search(pattern, text, flags=re.MULTILINE):
        errors.append(label)

def main() -> int:
    errors: list[str] = []
    dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    entrypoint = (ROOT / 'docker-entrypoint.sh').read_text(encoding='utf-8')
    deployment = (ROOT / 'k8s' / 'deployment.yaml').read_text(encoding='utf-8')

    image_nonroot = bool(re.search(r'(?m)^USER\s+(?:appuser|10001)(?::10001)?\s*$', dockerfile))
    entrypoint_drops_root = ('exec gosu "${APP_USER}"' in entrypoint and 'CIR_RUN_AS_ROOT_ON_VOLUME_PERMISSION_FAILURE:-0' in entrypoint)
    if not (image_nonroot or entrypoint_drops_root):
        errors.append('Image must run non-root directly or drop root via the hardened entrypoint')
    require(deployment, r'runAsNonRoot:\s*true', 'Kubernetes deployment must set runAsNonRoot: true', errors)
    require(deployment, r'runAsUser:\s*10001', 'Kubernetes deployment must set runAsUser: 10001', errors)
    require(deployment, r'allowPrivilegeEscalation:\s*false', 'Kubernetes deployment must disable privilege escalation', errors)
    require(deployment, r'readOnlyRootFilesystem:\s*true', 'Kubernetes deployment must use a read-only root filesystem', errors)
    require(deployment, r'(?:drop:\s*\[\"ALL\"\]|drop:\s*\n\s*-\s*ALL)', 'Kubernetes deployment must drop all Linux capabilities', errors)
    require(deployment, r'(?s)seccompProfile:\s*\n\s*type:\s*RuntimeDefault', 'Kubernetes deployment must use RuntimeDefault seccomp', errors)

    if errors:
        print('Security gate context verification: FAIL', file=sys.stderr)
        for err in errors:
            print(f'- {err}', file=sys.stderr)
        return 1
    print('Security gate context verification: PASS')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
