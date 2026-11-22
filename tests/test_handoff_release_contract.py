"""A resume document is a mandatory part of every subsequent package."""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_handoff_is_present_and_describes_resume_and_validation_state():
    handoff = ROOT / 'docs' / 'HANDOFF.md'
    text = handoff.read_text(encoding='utf-8')
    assert (ROOT / 'VERSION').read_text().strip() in text
    for required in ('0.9.0-1', 'Tenants Default', 'RC16', 'pytest', 'PostgreSQL', '2026-10-20'):
        assert required in text
    assert len(text) > 1500
    assert {p.name for p in ROOT.glob('*.md')} == {'README.md', 'README_en.md'}


def test_packaging_and_offline_verifier_require_handoff(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'verify_release_candidate.py')],
                            cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    candidate = tmp_path / 'candidate'
    copied = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'copy_release_tree.py'),
                             str(ROOT), str(candidate)], text=True, capture_output=True)
    assert copied.returncode == 0, copied.stdout + copied.stderr
    (candidate / 'docs' / 'HANDOFF.md').unlink()
    for command in ([sys.executable, str(candidate / 'scripts' / 'verify_release_candidate.py')],
                    ['bash', str(candidate / 'scripts' / 'package_release.sh'), str(tmp_path / 'missing.zip')]):
        rejected = subprocess.run(command, cwd=candidate, text=True, capture_output=True)
        assert rejected.returncode != 0
        assert 'HANDOFF.md' in rejected.stdout + rejected.stderr
    assert not (tmp_path / 'missing.zip').exists()
