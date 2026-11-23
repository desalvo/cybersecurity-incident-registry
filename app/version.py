"""Application identity from the immutable source/image metadata files."""
from pathlib import Path

from release_metadata import read_runtime_metadata

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_metadata = read_runtime_metadata(_PROJECT_ROOT)
DEFAULT_RELEASE_VERSION = _metadata.version
DEFAULT_RELEASE_BUILD = _metadata.build
APP_RELEASE_VERSION = DEFAULT_RELEASE_VERSION
APP_RELEASE_BUILD = DEFAULT_RELEASE_BUILD
