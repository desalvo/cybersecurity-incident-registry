#!/usr/bin/env python3
"""Standard-library packaging fallback with the release exclusion policy."""
from pathlib import Path
import fnmatch
import shutil
import sys

EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                 '.pytest_tmp', 'backups', 'generated', 'htmlcov'}
EXCLUDED_DOCUMENT_PATHS = {
    'docs/CIR_UI_Screenshots.pdf',
    'docs/presentation/CIR_Operational_Training_IT.pptx',
    'docs/presentation/CIR_Operational_Training_Visual.pptx',
    'docs/presentation/CIR_Operational_Training_Visual.pdf',
    'docs/presentation/CIR_Operational_Training_Visual_EN.pptx',
    'docs/presentation/CIR_Operational_Training_Visual_EN.pdf',
}
EXCLUDED_FILES = {'.env', 'SCA_PIP_AUDIT.json', '.coverage', 'coverage.xml'}
EXCLUDED_PATTERNS = ('*.py[co]', '*.log', '*.key', '*.crt')


def copy_release_tree(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target == source or source in target.parents:
        raise ValueError('The staging directory must be outside the source tree.')

    def excluded(directory, names):
        relative = Path(directory).relative_to(source)
        if relative in {Path('instance'), Path('app/uploads')}:
            return names
        result = []
        for name in names:
            path = Path(directory) / name
            if (relative / name).as_posix() in EXCLUDED_DOCUMENT_PATHS or name in EXCLUDED_DIRS or name in EXCLUDED_FILES or any(fnmatch.fnmatchcase(name, p) for p in EXCLUDED_PATTERNS):
                result.append(name)
            elif path.is_symlink():
                raise ValueError(f'Symlinks are not supported in release sources: {relative / name}')
        return result

    shutil.copytree(source, target, ignore=excluded, dirs_exist_ok=True, copy_function=shutil.copy2)


if __name__ == '__main__':
    copy_release_tree(sys.argv[1], sys.argv[2])
