"""Local Python startup defaults for deterministic project test runs.

When the repository root is on ``sys.path`` (the normal case for
``python -m pytest`` from the project directory), this module is imported before
pytest plugin discovery.  It prevents unrelated globally installed pytest
plugins from affecting the application suite and keeps background schedulers off
in test processes.  Runtime application processes are unaffected.
"""
from __future__ import annotations

import os
import sys


def _looks_like_pytest_invocation() -> bool:
    argv = ' '.join(sys.argv).lower()
    return 'pytest' in argv or any(part.endswith('pytest') for part in sys.argv[:1])


if _looks_like_pytest_invocation():
    os.environ.setdefault('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    os.environ.setdefault('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    os.environ.setdefault('CIR_FORCE_PYTEST_PROCESS_EXIT', '1')
