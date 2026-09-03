from pathlib import Path

ROOT = Path(__file__).parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_dockerfile_uses_multistage_runtime_and_isolated_venv():
    dockerfile = text('Dockerfile')
    assert 'FROM python:3.12.14-slim-trixie AS python-deps' in dockerfile
    assert 'FROM python:3.12.14-slim-trixie AS runtime' in dockerfile
    assert 'python -m venv /opt/cir-venv' in dockerfile
    assert 'COPY --from=python-deps /opt/cir-venv /opt/cir-venv' in dockerfile
    assert 'PATH=/opt/cir-venv/bin:$PATH' in dockerfile


def test_runtime_removes_python_packaging_tooling_and_embedded_pip_sbom_source():
    dockerfile = text('Dockerfile')
    assert 'pip uninstall -y pip setuptools wheel' in dockerfile
    assert '/usr/local/lib/python3.12/site-packages/pip' in dockerfile
    assert '/usr/local/lib/python3.12/site-packages/setuptools' in dockerfile
    assert '/usr/local/lib/python3.12/site-packages/wheel' in dockerfile


def test_runtime_keeps_headless_conversion_without_gui_recommendations():
    dockerfile = text('Dockerfile')
    assert 'libreoffice-writer-nogui' in dockerfile
    assert '--no-install-recommends' in dockerfile
    assert 'libreoffice-writer \\' not in dockerfile


def test_docker_context_excludes_historical_scan_inputs_and_tests():
    dockerignore = text('.dockerignore')
    for required in ('SBOM_*.cdx.json', 'SECURITY_AUDIT_*.md', 'tests/', 'pytest.ini', 'requirements-dev.txt'):
        assert required in dockerignore
