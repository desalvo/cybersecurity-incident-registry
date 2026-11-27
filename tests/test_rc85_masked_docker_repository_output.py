"""RC85: keep documentation publication independent of secret-filtered job outputs.

The Docker Hub account name can be present in DOCKERHUB_USERNAME (a GitHub
Actions secret). GitHub may therefore suppress a job output containing the
same account name, even though the image repository is public. These tests
exercise the actual publisher shell prefix without contacting GitHub/Docker.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/ci-release.yml'
DEFAULT = 'desalvo/cybersecurity-incident-registry'
DIGEST = 'sha256:' + 'e' * 64


def publisher_step():
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding='utf-8'))['jobs']
    steps = jobs['production-digest-publication']['steps']
    step, = (s for s in steps if s.get('id') == 'publish')
    return jobs, step


def test_job_exposes_digest_but_not_secret_filtered_repository():
    jobs, step = publisher_step()
    assert jobs['docker-release']['outputs'] == {
        'digest': '${{ steps.published.outputs.digest }}',
    }
    assert 'repository' not in jobs['docker-release']['outputs']
    assert step['env']['PUBLISHED_DIGEST'] == '${{ needs.docker-release.outputs.digest }}'
    assert step['env']['DOCKER_RELEASE_RESULT'] == '${{ needs.docker-release.result }}'
    assert step['env']['CONFIGURED_REPOSITORY'] == '${{ vars.CIR_DOCKER_REPOSITORY }}'
    assert 'PUBLISHED_REPOSITORY' not in step['env']
    assert 'needs.docker-release.outputs.repository' not in step['run']

    docker_resolve = next(s for s in jobs['docker-release']['steps'] if s.get('id') == 'image')
    assert docker_resolve['env']['CONFIGURED_REPOSITORY'] == step['env']['CONFIGURED_REPOSITORY']
    expression = 'repository="${CONFIGURED_REPOSITORY:-${DEFAULT_DOCKER_REPOSITORY}}"'
    assert expression in docker_resolve['run']
    assert expression in step['run']
    assert 'Promoted Docker release did not expose a verified digest' in step['run']
    assert 'Skipped Docker release unexpectedly reported a digest' in step['run']
    assert 'Unexpected Docker release result:' in step['run']


def run_publisher_prefix(tmp_path, *, result='success', digest=DIGEST, configured=''):
    _, step = publisher_step()
    # Execute the very same shell prefix that precedes the git/PR operations.
    # That makes the test independent of GitHub credentials and network access.
    script = step['run'].split('git config user.name', 1)[0]
    work = tmp_path / 'repo'
    (work / 'scripts').mkdir(parents=True)
    (work / 'k8s').mkdir()
    shutil.copyfile(ROOT / 'scripts/record_production_digest.py',
                    work / 'scripts/record_production_digest.py')
    shutil.copyfile(ROOT / 'k8s/kustomization.yaml', work / 'k8s/kustomization.yaml')
    (work / 'scripts/verify_production_release.sh').write_text(
        '#!/bin/bash\nset -euo pipefail\n'
        'test -s PRODUCTION_IMAGE_DIGEST\n'
        'printf verified > verification-called\n', encoding='utf-8'
    )
    env = dict(os.environ, DEFAULT_DOCKER_REPOSITORY=DEFAULT,
               CONFIGURED_REPOSITORY=configured, PUBLISHED_DIGEST=digest,
               DOCKER_RELEASE_RESULT=result)
    completed = subprocess.run(['bash', '-c', script], cwd=work, env=env,
                               capture_output=True, text=True, check=False)
    return completed, work


@pytest.mark.parametrize(('configured', 'expected_repository'), [
    ('', DEFAULT),
    ('sample-team/alternative-cir', 'sample-team/alternative-cir'),
])
def test_docker_success_records_immutable_digest_from_same_repository_resolution(
    tmp_path, configured, expected_repository,
):
    completed, work = run_publisher_prefix(tmp_path, configured=configured)
    assert completed.returncode == 0, completed.stderr
    assert (work / 'PRODUCTION_IMAGE_DIGEST').read_text().strip() == (
        expected_repository + '@' + DIGEST
    )
    assert f'newName: {expected_repository}' in (work / 'k8s/kustomization.yaml').read_text()
    assert f'digest: {DIGEST}' in (work / 'k8s/kustomization.yaml').read_text()
    assert (work / 'verification-called').read_text() == 'verified'


def test_docker_success_without_promoted_digest_fails_closed(tmp_path):
    completed, work = run_publisher_prefix(tmp_path, digest='')
    assert completed.returncode != 0
    assert 'did not expose a verified digest' in completed.stderr
    assert not (work / 'PRODUCTION_IMAGE_DIGEST').exists()
    assert not (work / 'verification-called').exists()


def test_docker_skipped_does_not_rewrite_production_metadata(tmp_path):
    completed, work = run_publisher_prefix(tmp_path, result='skipped', digest='')
    assert completed.returncode == 0, completed.stderr
    assert not (work / 'PRODUCTION_IMAGE_DIGEST').exists()
    assert not (work / 'verification-called').exists()


@pytest.mark.parametrize(('result', 'digest', 'error'), [
    ('skipped', DIGEST, 'unexpectedly reported a digest'),
    ('failure', '', 'Unexpected Docker release result'),
    ('cancelled', '', 'Unexpected Docker release result'),
    ('success', 'sha256:bad', 'invalid OCI digest'),
])
def test_inconsistent_or_invalid_release_state_fails_closed(tmp_path, result, digest, error):
    completed, work = run_publisher_prefix(tmp_path, result=result, digest=digest)
    assert completed.returncode != 0
    assert error in completed.stderr
    assert not (work / 'verification-called').exists()
