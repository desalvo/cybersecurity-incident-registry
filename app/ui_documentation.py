"""Links to verified CI screenshots bundled with this immutable application."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from flask import current_app, url_for

from .version import APP_RELEASE_VERSION, APP_RELEASE_BUILD


@lru_cache(maxsize=8)
def _installed_screenshots(static_folder, manifest_mtime, version, build):
    directory = Path(static_folder) / 'help/ui-runtime'
    try:
        data = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if (data.get('source_kind') != 'real-application-browser'
                or data.get('data_provenance') != 'isolated-synthetic-fixture'
                or data.get('functional_version') != version
                or str(data.get('build')) != build
                or not re.fullmatch(r'[a-f0-9]{40}(?:[a-f0-9]{24})?', data.get('source_commit', ''))):
            return {}
        result = {}
        for row in data.get('screenshots', []):
            sid = row.get('id', '')
            filename = row.get('file', '')
            if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid)
                    or filename not in (sid + '.png', sid + '.jpg')):
                return {}
            path = directory / filename
            if (path.is_symlink() or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != row.get('sha256')):
                return {}
            result[sid] = filename
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def documentation_screenshot(screenshot_id):
    folder = current_app.static_folder
    manifest = Path(folder) / 'help/ui-runtime/manifest.json'
    try:
        stamp = manifest.stat().st_mtime_ns
    except OSError:
        return None
    filename = _installed_screenshots(folder, stamp, APP_RELEASE_VERSION, APP_RELEASE_BUILD).get(screenshot_id)
    return url_for('static', filename='help/ui-runtime/' + filename) if filename else None
