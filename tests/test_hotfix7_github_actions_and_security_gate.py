from pathlib import Path
import json
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_hardening_verifier_passes_packaged_manifests():
    r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'verify_security_gate_context.py')], text=True, capture_output=True)
    assert r.returncode == 0, r.stderr
    assert 'PASS' in r.stdout



def test_github_workflow_yaml_is_valid():
    workflow_path = ROOT / '.github' / 'workflows' / 'ci-release.yml'
    parsed = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
    assert isinstance(parsed, dict)
    assert 'jobs' in parsed


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
        'UPLOAD_DIR: ${{ runner.temp }}/cir-pytest/uploads',
        'LOGO_DIR: ${{ runner.temp }}/cir-pytest/logos',
        'SSO_LOGO_DIR: ${{ runner.temp }}/cir-pytest/sso-logos',
        'FORM_TEMPLATE_DIR: ${{ runner.temp }}/cir-pytest/form-templates',
        'BACKUP_DIR: ${{ runner.temp }}/cir-pytest/backups',
        'AI_CHATBOT_DOC_DIR: ${{ runner.temp }}/cir-pytest/ai-chatbot-docs',
        'SSL_DIR: ${{ runner.temp }}/cir-pytest/ssl',
        'actions/checkout@v7',
        'actions/setup-python@v7',
    ):
        assert needle in workflow

    assert 'actions/checkout@v6' not in workflow
    assert 'actions/setup-python@v6' not in workflow

    postgres_step = workflow.split('- name: Run real PostgreSQL test suite', 1)[1].split('- name: Verify release candidate', 1)[0]
    for needle in (
        'UPLOAD_DIR: ${{ runner.temp }}/cir-postgres-tests/uploads',
        'BACKUP_DIR: ${{ runner.temp }}/cir-postgres-tests/backups',
        'AI_CHATBOT_DOC_DIR: ${{ runner.temp }}/cir-postgres-tests/ai-chatbot-docs',
        'SSL_DIR: ${{ runner.temp }}/cir-postgres-tests/ssl',
    ):
        assert needle in postgres_step


def test_new_risk_acceptance_is_scoped_and_time_bounded():
    p = json.loads((ROOT / 'TRIVY_RISK_ACCEPTANCE_R8.json').read_text(encoding='utf-8'))
    assert p['valid_until'] == '2026-10-20'
    accepted = p['accepted_residual_vulnerabilities']
    util = {'CVE-2026-76642','CVE-2026-78408','CVE-2026-78409','CVE-2026-78410'}
    for cve in util:
        assert 'util-linux' in accepted[cve]['packages']
        assert accepted[cve]['review_before'] == '2026-10-20'
    assert accepted['CVE-2026-16742']['packages'] == ['libsystemd0','libudev1']
