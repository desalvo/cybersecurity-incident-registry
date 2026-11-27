#!/usr/bin/env python3
"""Validate same-commit browser evidence before publishing current UI manuals.

Standard-library only: the validation and artifact installation steps do not
need the application or a browser and never download files or execute manifests.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from release_metadata import read_release_metadata

REQUIRED_SCREENSHOTS = frozenset({
    'login-desktop', 'login-mobile', 'registry-desktop', 'registry-closed-state', 'registry-mobile',
    'registry-mobile-menu', 'incident-desktop', 'incident-mobile',
    'spam-incident-desktop', 'spam-incident-config-labels', 'spam-workflow-steps',
    'workflow-steps-focused', 'statistics-desktop', 'assistant-panel-closeup',
    'tenant-setup-wizard-desktop', 'tenant-setup-wizard-panel', 'tenant-wizard-next-step',
    'pdf-mapping-configuration', 'pdf-generated-preview', 'notification-preview', 'alfresco-settings-desktop',
    'alfresco-incident-documents',
    'assistant-desktop', 'assistant-mobile', 'interface-settings-desktop',
    'classic-registry-desktop', 'admin-modules-desktop', 'admin-sso-desktop',
    'documentation-user-desktop', 'documentation-user-mobile',
    'documentation-admin-desktop', 'documentation-admin-mobile',
    'support-ticket-new-tenant-admin', 'support-ticket-submitted-tenant-admin',
})
# These dedicated browser regions are narrower than the browser viewport.
# Only specifically approved regions may claim element-capture provenance.
ELEMENT_CAPTURE_SELECTORS = {
    'spam-incident-config-labels': '#incident-main .dnd-layout',
    'workflow-steps-focused': '#incident-workflow .workflow-steps-ordered',
    'statistics-desktop': '.stats-card:first-child',
    'assistant-panel-closeup': '#cir-albot-panel',
    'tenant-setup-wizard-desktop': '.setup-wizard-shell',
    'tenant-setup-wizard-panel': '.setup-wizard-panel',
    'tenant-wizard-next-step': '.setup-wizard-shell',
}
DOCUMENTATION_CAPTURE_ROUTES = {
    'tenant-setup-wizard-desktop': '/admin/setup-wizard',
    'tenant-setup-wizard-panel': '/admin/setup-wizard',
    'tenant-wizard-next-step': '/admin/setup-wizard',
    'documentation-user-desktop': '/aiuto',
    'documentation-user-mobile': '/aiuto',
    'documentation-admin-desktop': '/aiuto/amministrazione',
    'documentation-admin-mobile': '/aiuto/amministrazione',
    'support-ticket-new-tenant-admin': '/support/new',
}
# Only online help landing pages are required to show the *whole first fold*.
# Wizard captures are authenticated element crops with their own strict bounds,
# selector and route checks. Do not classify them as online manual covers.
ONLINE_DOCUMENTATION_COVERS = frozenset({
    'documentation-user-desktop', 'documentation-user-mobile',
    'documentation-admin-desktop', 'documentation-admin-mobile',
})
DOCUMENTATION_CAPTURE_CHECKS = frozenset({
    'documentation_covers_show_current_identity_and_local_platform_logos',
    'documentation_mobile_first_fold_has_no_horizontal_overflow',
})
REQUIRED_MANUALS = frozenset({
    'documentazione_utente.pdf', 'documentazione_amministrativa.pdf',
    'user_documentation_en.pdf', 'administrator_documentation_en.pdf',
    'ADMIN_ALFRESCO.pdf', 'CIR_UI_Screenshots.pdf', 'CIR_Incident_Laboratory_IT.pdf',
    'brochure_cybersecurity_incident_registry.pdf',
    'brochure_cybersecurity_incident_registry_en.pdf',
})


class EvidenceError(ValueError):
    """Evidence is incomplete, stale or not safe to install."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_artifact_path(directory: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise EvidenceError('Invalid artifact path')
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or ':' in relative:
        raise EvidenceError('Artifact path escapes its directory')
    target = directory / Path(*path.parts)
    component = directory
    for part in path.parts:
        component = component / part
        if component.is_symlink():
            raise EvidenceError('Symlink artifacts are not allowed')
    if not target.is_file() or not target.resolve().is_relative_to(directory.resolve()):
        raise EvidenceError('Artifact is missing or outside its directory')
    return target


def _read_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise EvidenceError('Manifest missing or too large')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError('Invalid manifest JSON') from exc
    if not isinstance(data, dict):
        raise EvidenceError('Manifest must be an object')
    return data


def _image_size(path: Path) -> tuple[int, int]:
    """Read PNG/JPEG dimensions with stdlib only (required by offline CI gates).

    A JPEG must have a Start Of Frame marker, matching its extension, and an
    End Of Image marker.  We do not trust extensions or checksum alone to claim
    an image was actually captured by the browser.
    """
    data = path.read_bytes()
    if path.suffix.lower() == '.png':
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
            raise EvidenceError('Invalid PNG header')
        return struct.unpack('>II', data[16:24])
    if path.suffix.lower() != '.jpg' or len(data) < 24 or data[:2] != b'\xff\xd8' or data[-2:] != b'\xff\xd9':
        raise EvidenceError('Invalid JPEG header or end marker')
    index, dimensions = 2, None
    sof_markers = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
    while index + 3 < len(data):
        if data[index] != 0xff:
            raise EvidenceError('Malformed JPEG segment')
        while index < len(data) and data[index] == 0xff:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in (0x01, *range(0xd0, 0xd9)):
            continue
        if marker == 0xda:  # Compressed image data begins after SOS.
            break
        if marker == 0xd9:
            break
        if index + 2 > len(data):
            raise EvidenceError('Malformed JPEG segment length')
        segment = struct.unpack('>H', data[index:index+2])[0]
        if segment < 2 or index + segment > len(data):
            raise EvidenceError('Invalid JPEG segment bounds')
        if marker in sof_markers:
            if segment < 8 or dimensions is not None:
                raise EvidenceError('Invalid JPEG frame header')
            height, width = struct.unpack('>HH', data[index+3:index+7])
            dimensions = (width, height)
        index += segment
    if dimensions is None:
        raise EvidenceError('JPEG has no valid frame dimensions')
    return dimensions


def load_evidence(manifest_path: Path, expected_commit: str | None = None, *, metadata_root: Path = ROOT) -> dict:
    """Return the validated manifest and local paths under ``_paths``."""
    manifest_path = Path(manifest_path).absolute()
    data = _read_json(manifest_path)
    if data.get('schema_version') != 1:
        raise EvidenceError('Unsupported screenshot schema')
    if data.get('source_kind') != 'real-application-browser':
        raise EvidenceError('Current UI manuals require real application screenshots')
    if data.get('data_provenance') != 'isolated-synthetic-fixture':
        raise EvidenceError('Screenshot data must be an isolated synthetic fixture')
    commit = data.get('source_commit')
    if not isinstance(commit, str) or not re.fullmatch(r'[a-f0-9]{40}(?:[a-f0-9]{24})?', commit):
        raise EvidenceError('Missing or invalid source commit')
    if expected_commit is not None and commit != expected_commit:
        raise EvidenceError('Screenshot commit differs from the source being built')
    metadata = read_release_metadata(metadata_root)
    if data.get('functional_version') != metadata.version or str(data.get('build')) != metadata.build:
        raise EvidenceError('Screenshot release metadata differs from this release')
    browser = data.get('browser')
    if not isinstance(browser, dict) or not all(browser.get(k) for k in ('name', 'version', 'playwright')):
        raise EvidenceError('Browser provenance is required')
    checks = data.get('checks')
    if not isinstance(checks, dict) or not checks or any(v is not True for v in checks.values()):
        raise EvidenceError('Screenshot checks did not all pass')
    if DOCUMENTATION_CAPTURE_CHECKS - checks.keys():
        raise EvidenceError('Required online documentation checks are missing')
    rows = data.get('screenshots')
    if not isinstance(rows, list) or not rows or len(rows) > 80:
        raise EvidenceError('Screenshot list missing or invalid')
    paths = {}
    files = set()
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError('Screenshot entry must be an object')
        sid = row.get('id')
        if not isinstance(sid, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid) or sid in paths:
            raise EvidenceError('Invalid or duplicate screenshot ID')
        path = safe_artifact_path(manifest_path.parent, row.get('file'))
        image_format = 'jpeg' if path.suffix.lower() == '.jpg' else 'png'
        if path.suffix.lower() not in ('.png', '.jpg') or path.stat().st_size > 40 * 1024 * 1024:
            raise EvidenceError('Expected a bounded PNG or JPEG image')
        if row.get('image_format', image_format) != image_format:
            raise EvidenceError('Screenshot format/extension mismatch: ' + sid)
        if image_format == 'jpeg' and 'jpeg_quality' in row and (type(row['jpeg_quality']) is not int or not 75 <= row['jpeg_quality'] <= 95):
            raise EvidenceError('Screenshot JPEG quality is outside the permitted range')
        if path in files:
            raise EvidenceError('Each screenshot must have its own file')
        files.add(path)
        if not isinstance(row.get('sha256'), str) or sha256(path) != row['sha256']:
            raise EvidenceError('Screenshot checksum mismatch: ' + sid)
        width, height = _image_size(path)
        viewport = row.get('viewport')
        if (not isinstance(viewport, dict)
                or type(viewport.get('width')) is not int or type(viewport.get('height')) is not int
                or not 300 <= viewport['width'] <= 4000 or not 400 <= viewport['height'] <= 4000):
            raise EvidenceError('Invalid screenshot viewport: ' + sid)
        area = row.get('capture_area')
        # Online manual covers must remain exact first-fold screenshots.
        # Preserve their specific diagnostic even when the capture-area
        # metadata itself has been corrupted.
        if sid in ONLINE_DOCUMENTATION_COVERS and (area != 'viewport' or height != viewport['height']):
            raise EvidenceError('Online documentation must show its real route and first viewport: ' + sid)
        if area == 'element':
            # Playwright's Locator.screenshot captures a DOM rectangle, NOT the
            # whole viewport. Validate its native pixel dimensions separately
            # instead of comparing its width to the viewport width.
            declared = row.get('element_size')
            if (row.get('element_selector') != ELEMENT_CAPTURE_SELECTORS.get(sid)
                    or sid not in ELEMENT_CAPTURE_SELECTORS):
                raise EvidenceError('Unapproved screenshot element selector: ' + sid)
            if (not isinstance(declared, dict)
                    or type(declared.get('width')) is not int
                    or type(declared.get('height')) is not int
                    or declared != {'width': width, 'height': height}
                    or not 200 <= width <= viewport['width']
                    or not 80 <= height <= 40000):
                raise EvidenceError('Element screenshot dimensions mismatch: ' + sid)
        elif area in ('viewport', 'full-page'):
            if (row.get('element_size') is not None or row.get('element_selector') is not None
                    or width != viewport['width']
                    or height < viewport['height'] or height > 40000
                    or (area == 'viewport' and height != viewport['height'])):
                raise EvidenceError('Screenshot dimensions do not match viewport: ' + sid)
        else:
            raise EvidenceError('Unsupported screenshot capture area: ' + sid)
        # The optional ROIs are obtained directly from the authenticated DOM
        # element used for this screenshot. Reject forged, clipped or colliding
        # card regions before they can be used in training slide 61.
        if row.get('step_card_rois') is not None:
            if sid != 'workflow-steps-focused':
                raise EvidenceError('Unexpected workflow step geometry for: ' + sid)
            try:
                from scripts.training_step_card_roi import step_card_regions
                step_card_regions(path, row)
            except (ValueError, OSError) as exc:
                raise EvidenceError('Invalid workflow step geometry: ' + sid) from exc
        expected_mode = 'classic' if sid.startswith('classic-') else 'modern'
        if row.get('ui_mode') != expected_mode:
            raise EvidenceError('Wrong UI mode: ' + sid)
        if row.get('authenticated') is not (not sid.startswith('login-')):
            raise EvidenceError('Wrong authentication state: ' + sid)
        route = row.get('route')
        if not isinstance(route, str) or not route.startswith('/') or route.startswith('//'):
            raise EvidenceError('Screenshot route must be local')
        if sid == 'support-ticket-submitted-tenant-admin' and not re.fullmatch(r'/support/tickets/[1-9][0-9]*', route):
            raise EvidenceError('Submitted ticket screenshot must show its real ticket route')
        if sid in DOCUMENTATION_CAPTURE_ROUTES:
            if (route != DOCUMENTATION_CAPTURE_ROUTES[sid]
                    or (sid in ONLINE_DOCUMENTATION_COVERS and
                        (row.get('capture_area') != 'viewport' or height != viewport['height']))):
                raise EvidenceError('Online documentation must show its real route and first viewport: ' + sid)
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ('caption_it', 'caption_en')):
            raise EvidenceError('Bilingual screenshot captions are required')
        paths[sid] = path
    missing = REQUIRED_SCREENSHOTS - paths.keys()
    if missing:
        raise EvidenceError('Missing required screenshots: ' + ', '.join(sorted(missing)))
    data['_paths'] = paths
    return data


def validate_manuals(directory: Path, expected_commit: str, screenshot_manifest_sha256: str, *,
                     metadata_root: Path = ROOT, receipt_name: str = 'build-manifest.json',
                     require_presentation: bool = True, screenshot_evidence: dict | None = None,
                     installed: bool = False, runtime_external_training: bool = False) -> dict:
    directory = Path(directory).absolute()
    if runtime_external_training and not installed:
        raise EvidenceError('External training documents are allowed only in an installed Docker runtime')
    if Path(receipt_name).name != receipt_name:
        raise EvidenceError('Receipt filename must be a basename')
    receipt = _read_json(directory / receipt_name)
    if receipt.get('schema_version') != (2 if require_presentation else 1):
        raise EvidenceError('Documentation receipt schema does not cover the complete required batch')
    if receipt.get('source_commit') != expected_commit:
        raise EvidenceError('Manuals belong to a different source commit')
    metadata = read_release_metadata(metadata_root)
    if receipt.get('functional_version') != metadata.version or str(receipt.get('build')) != metadata.build:
        raise EvidenceError('Manual release metadata differs from this release')
    if receipt.get('screenshot_manifest_sha256') != screenshot_manifest_sha256:
        raise EvidenceError('Manuals were not built from these screenshots')
    if receipt.get('real_screenshots') is not True:
        raise EvidenceError('Manuals do not contain real screenshot evidence')
    files = receipt.get('files')
    if not isinstance(files, list):
        raise EvidenceError('Manual build receipt has no files')
    from scripts.presentation_evidence import (
        PRESENTATION_ARTIFACTS, PRESENTATION_FILE, PRESENTATION_RECEIPT,
        validate_presentation, validate_detached_presentation_receipt,
    )
    required = set(REQUIRED_MANUALS)
    if require_presentation:
        required.update(PRESENTATION_ARTIFACTS)
        if receipt.get('presentation_receipt_file') != PRESENTATION_RECEIPT:
            raise EvidenceError('Presentation receipt is not bound to the documentation batch')
        if screenshot_evidence is None:
            raise EvidenceError('Validated screenshot evidence is required for the complete documentation batch')
    # Only these two large, fully CI-validated artifacts live outside the
    # minimal Docker runtime. The receipt itself and every manual preview are
    # required inside the image and checked against the same-run manifest.
    external = frozenset({'CIR_UI_Screenshots.pdf', PRESENTATION_FILE}) if runtime_external_training else frozenset()
    external_hashes = {}
    paths = {}
    for item in files:
        if not isinstance(item, dict):
            raise EvidenceError('Invalid manual entry')
        name = item.get('file')
        if not isinstance(name, str) or PurePosixPath(name).name != name:
            raise EvidenceError('Manual filenames must be basenames')
        if name in paths:
            raise EvidenceError('Duplicate manual')
        if name not in required:
            raise EvidenceError('Unexpected documentation artifact')
        relative = 'presentation/' + name if installed and name in PRESENTATION_ARTIFACTS else name
        if name in external:
            absent_path = directory / relative
            if absent_path.exists() or absent_path.is_symlink():
                raise EvidenceError('Externally distributed document must not be copied into Docker: ' + name)
            if not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                raise EvidenceError('External document is missing its verified SHA-256 receipt: ' + name)
            external_hashes[name] = item['sha256']
            paths[name] = absent_path  # Preserve the required manifest census.
            continue
        try:
            path = safe_artifact_path(directory, relative)
        except EvidenceError as exc:
            raise EvidenceError(f'Documentation artifact {name}: {exc}') from exc
        limit = 150 * 1024 * 1024 if name == PRESENTATION_FILE else 80 * 1024 * 1024
        if path.stat().st_size > limit:
            raise EvidenceError('Documentation artifact exceeds size limit')
        if (name in REQUIRED_MANUALS and not path.read_bytes().startswith(b'%PDF-')) or sha256(path) != item.get('sha256'):
            raise EvidenceError('Manual format or checksum mismatch')
        paths[name] = path
    if required - paths.keys():
        raise EvidenceError('Required current manuals are missing')
    if runtime_external_training and set(external_hashes) != external:
        raise EvidenceError('Runtime external documentation receipt is incomplete')
    if require_presentation:
        if runtime_external_training:
            validate_detached_presentation_receipt(
                paths, expected_commit, screenshot_manifest_sha256,
                screenshot_evidence, metadata_root=metadata_root,
                deck_sha256=external_hashes[PRESENTATION_FILE],
            )
        else:
            validate_presentation(paths, expected_commit, screenshot_manifest_sha256,
                                  screenshot_evidence, metadata_root=metadata_root)
    receipt['_paths'] = paths
    return receipt


def validate_installed_documentation(root: Path = ROOT, *, runtime_external_training: bool = False) -> dict:
    """Check a complete installed batch against this candidate's VERSION/BUILD.

    Packaging calls this after stamping BUILD. A receipt from a prior build is
    never silently reused merely because the source commit has not changed.
    """
    root = Path(root).absolute()
    installed_path = root / 'app/static/help/ui-runtime/manifest.json'
    original_path = root / 'docs/UI_SCREENSHOTS_SOURCE.json'
    installed = load_evidence(installed_path, metadata_root=root)
    commit = installed['source_commit']
    original = _read_json(original_path)
    # The original receipt is bound to artifact-relative image paths. The
    # installer only changes these paths; all other source facts stay equal.
    normalized = dict(original)
    rows = original.get('screenshots')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise EvidenceError('Original screenshot manifest has invalid entries')
    normalized['screenshots'] = [dict(row, file=str(row.get('id', '')) + Path(row.get('file', '')).suffix.lower()) for row in rows]
    if normalized != {key: value for key, value in installed.items() if key != '_paths'}:
        raise EvidenceError('Installed screenshots differ from their original artifact manifest')
    receipt = validate_manuals(root / 'docs', commit, sha256(original_path),
                               metadata_root=root, receipt_name='UI_SCREENSHOTS_BUILD.json',
                               screenshot_evidence=installed, installed=True,
                               runtime_external_training=runtime_external_training)
    if (receipt.get('source_manifest_file') != 'UI_SCREENSHOTS_SOURCE.json'
            or receipt.get('installed_manifest_sha256') != sha256(installed_path)):
        raise EvidenceError('Installed screenshot receipt checksum mismatch')
    return receipt
