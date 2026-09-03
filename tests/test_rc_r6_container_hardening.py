from pathlib import Path

ROOT = Path(__file__).parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_runtime_image_uses_headless_libreoffice_and_no_curl_healthcheck():
    dockerfile = text('Dockerfile')
    assert 'libreoffice-writer-nogui' in dockerfile
    assert 'libreoffice-writer \\' not in dockerfile
    assert '\n        curl \\' not in dockerfile
    assert 'http.client.HTTPConnection' in dockerfile
    assert 'apt-get upgrade -y' in dockerfile


def test_historical_release_artifacts_are_not_copied_into_runtime_image():
    ignore = text('.dockerignore')
    for pattern in (
        'SBOM_*.cdx.json',
        'SECURITY_AUDIT_*.md',
        'RELEASE_NOTES_*.md',
        'MIGRATION_*.md',
        'tests/',
    ):
        assert pattern in ignore


def test_multiarch_security_build_is_fresh_by_default():
    script = text('scripts/build_multiarch_image.sh')
    assert 'CIR_DOCKER_PULL_BASE:-1' in script
    assert 'CIR_DOCKER_NO_CACHE:-1' in script
    assert 'BUILD_ARGS+=(--pull)' in script
    assert 'BUILD_ARGS+=(--no-cache)' in script
