"""Regression contract for cumulative archive directory and Git metadata."""
import importlib.util
from pathlib import Path
import tarfile


def _load_packager():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'package_cumulative.py'
    spec = importlib.util.spec_from_file_location('cir_package_cumulative', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cumulative_archive_uses_canonical_root_and_excludes_git(tmp_path):
    mod = _load_packager()
    src = tmp_path / 'cir-rc100-source'
    (src / '.git' / 'refs' / 'heads').mkdir(parents=True)
    (src / '.git' / 'refs' / 'heads' / 'master').write_text('not-for-distribution')
    (src / '.github').mkdir()
    (src / '.github' / 'ci.yml').write_text('keep')
    (src / 'docs').mkdir()
    (src / 'docs' / 'file.txt').write_text('CIR')
    (src / 'VERSION').write_text('0.10.0-1')
    archive = tmp_path / 'fixed.tar.zst'
    mod.make_archive(src, archive, 'zstd', 3)
    with tarfile.open(fileobj=__import__('subprocess').Popen(['zstd','-dc',str(archive)],stdout=__import__('subprocess').PIPE).stdout, mode='r|') as tf:
        names = [member.name.rstrip('/') for member in tf]
    assert names[0] == mod.CANONICAL_ROOT
    assert all(n == mod.CANONICAL_ROOT or n.startswith(mod.CANONICAL_ROOT + '/') for n in names)
    assert not any('.git' in Path(n).parts for n in names)
    assert mod.CANONICAL_ROOT + '/.github/ci.yml' in names
