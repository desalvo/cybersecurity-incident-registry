from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_hardening_verifier_passes_packaged_manifests():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'verify_security_gate_context.py')], text=True, capture_output=True)
    assert r.returncode == 0, r.stderr
    assert 'PASS' in r.stdout


def test_github_workflow_runs_required_gates_and_release_rules():
    workflow = (ROOT / '.github' / 'workflows' / 'ci-release.yml').read_text(encoding='utf-8')
    for needle in (
        'branches:',
        '- main',
        "tags:",
        "- '**'",
        'python -m pytest -q',
        './scripts/run_postgres_tests.sh',
        './scripts/run_sca.sh',
        'scripts/verify_release_candidate.py',
        'scripts/verify_security_gate_context.py',
        'linux/amd64,linux/arm64',
        'ci-${GITHUB_SHA}',
        'final_tag=latest',
        'final_tag="$GITHUB_REF_NAME"',
        'run_trivy_production_gate.sh',
        'imagetools create',
        'DOCKERHUB_USERNAME',
        'DOCKERHUB_TOKEN',
    ):
        assert needle in workflow


def test_new_risk_acceptance_is_scoped_and_time_bounded():
    p = json.loads((ROOT / 'TRIVY_RISK_ACCEPTANCE_R8.json').read_text(encoding='utf-8'))
    assert p['valid_until'] == '2026-10-20'
    accepted = p['accepted_residual_vulnerabilities']
    util = {'CVE-2026-76642','CVE-2026-78408','CVE-2026-78409','CVE-2026-78410'}
    for cve in util:
        assert 'util-linux' in accepted[cve]['packages']
        assert accepted[cve]['review_before'] == '2026-10-20'
    assert accepted['CVE-2026-16742']['packages'] == ['libsystemd0','libudev1']
