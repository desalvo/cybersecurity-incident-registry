"""Regression tests for offline Debian evidence collection."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dpkg_query_format_is_escaped_for_posix_shell():
    workflow = (ROOT / ".github/workflows/ci-security-fast.yml").read_text()
    assert r'dpkg-query -W -f="\${Package}\t\${Version}\t\${Status}\n"' in workflow
    assert "test -s /evidence/debian-installed.tsv" in workflow
    assert "test -s /evidence/debian-policy.txt" in workflow
    assert "test -s /evidence/debian-priority-packages.txt" in workflow


def test_missing_debian_evidence_is_not_reported_as_complete(tmp_path):
    spec = importlib.util.spec_from_file_location("summary", ROOT / "scripts/summarize_security_diagnostic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.summarize(tmp_path)
    assert result["debian_evidence_complete"] is False
    for name in ("debian-installed.tsv", "debian-policy.txt", "debian-priority-packages.txt", "debian-apt-update.log"):
        (tmp_path / name).write_text("sample evidence\n")
    assert module.summarize(tmp_path)["debian_evidence_complete"] is True
