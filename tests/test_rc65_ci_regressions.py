"""Offline regression checks for the RC65 PR CI failures.

The real Flask end-to-end coverage remains in test_tenant_defaults_integration.py,
test_tenant_defaults_rc18.py, and the same-commit Chromium capture gate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import uuid
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


def _pure_archive_validator(monkeypatch):
    # Load only the standalone, no-write validation logic; the full project
    # tests separately run it against actual SQLAlchemy/export fixtures.
    package = types.ModuleType('app')
    package.__path__ = [str(ROOT / 'app')]
    defaults = types.ModuleType('app.tenant_defaults')
    defaults._LOCAL_CATEGORY_MARKER = '__cir_existing_tenant_category'
    defaults._LOCAL_NOTIFICATION_MARKERS = {
        'notification_type': '__cir_existing_tenant_notification_type',
        'notification_template': '__cir_existing_tenant_notification_template',
    }
    defaults._validate_data = lambda kind, data: None
    monkeypatch.setitem(sys.modules, 'app', package)
    monkeypatch.setitem(sys.modules, 'app.tenant_defaults', defaults)
    spec = importlib.util.spec_from_file_location('app.tenant_defaults_archive', ROOT / 'app/tenant_defaults_archive.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_defaults_archive_tables


def _adopted_label_archive(kind='data_type', source_kind=None):
    sid, rid = str(uuid.uuid4()), 1
    name = 'SPAM - mail data'
    source_kind = kind if source_kind is None else source_kind
    label_data = {'kind': kind, 'value': name, 'description': 'Owned by tenant'}
    return {
        'tenants': [{'id': 1, 'name': 'Tenants Default', 'is_system_defaults': True},
                    {'id': 2, 'name': 'Laboratory', 'is_system_defaults': False}],
        'config_labels': [{'id': 10, 'tenant_id': 1, 'kind': source_kind, 'value': name},
                          {'id': 11, 'tenant_id': 2, 'kind': kind, 'value': name}],
        'tenant_default_sources': [{'id': sid, 'source_type': 'config_label',
                                    'source_id': 10, 'active': True,
                                    'snapshot_json': json.dumps({'kind': source_kind, 'value': name})}],
        'tenant_default_replicas': [{'id': rid, 'source_id': sid, 'tenant_id': 2,
                                     'local_type': 'config_label', 'local_id': 11,
                                     'snapshot_json': json.dumps({**label_data,
                                        '__cir_existing_tenant_category': True})}],
    }


@pytest.mark.parametrize('kind', ['category', 'data_type'])
def test_adopted_existing_labels_pass_archive_validation(monkeypatch, kind):
    validate = _pure_archive_validator(monkeypatch)
    assert validate(_adopted_label_archive(kind)) is True


@pytest.mark.parametrize('change', ['forbidden_kind', 'mismatched_kind', 'mismatched_name', 'foreign_tenant', 'fake_marker'])
def test_archive_still_rejects_forged_existing_label_provenance(monkeypatch, change):
    validate = _pure_archive_validator(monkeypatch)
    tables = _adopted_label_archive()
    if change == 'forbidden_kind':
        tables = _adopted_label_archive('severity')
    elif change == 'mismatched_kind':
        tables = _adopted_label_archive('data_type', 'category')
    elif change == 'mismatched_name':
        tables['config_labels'][1]['value'] = 'different local label'
    elif change == 'foreign_tenant':
        tables['tenant_default_replicas'][0]['tenant_id'] = 1
    else:
        snapshot = json.loads(tables['tenant_default_replicas'][0]['snapshot_json'])
        snapshot['__cir_existing_tenant_category'] = 'true'
        tables['tenant_default_replicas'][0]['snapshot_json'] = json.dumps(snapshot)
    with pytest.raises(ValueError, match='Archivio Tenants Default non valido'):
        validate(tables)


def test_frozen_training_presentation_notes_and_receipt():
    folder = ROOT / 'docs/presentation'
    slides = json.loads((folder / 'content_it.json').read_text())['slides']
    deck = folder / 'CIR_Operational_Training_IT.pptx'
    if not deck.is_file():
        pytest.skip('RC102: frozen deck removed; live CI release tests validate presentation receipts')
    receipt = json.loads((folder / 'presentation-receipt.json').read_text())
    assert hashlib.sha256(deck.read_bytes()).hexdigest() == receipt['sha256']
    with ZipFile(deck) as archive:
        assert archive.testzip() is None
        current_source = receipt.get('content_sha256') == hashlib.sha256(
            (folder / 'content_it.json').read_bytes()).hexdigest()
        if not current_source:
            assert not receipt.get('real_screenshots')
        for index, slide in enumerate(slides, 1):
            root = ET.fromstring(archive.read(f'ppt/notesSlides/notesSlide{index}.xml'))
            text = ' '.join((node.text or '') for node in root.findall('.//a:t', NS))
            if current_source:
                assert ' '.join(slide['notes'].split()) in ' '.join(text.split()), index
            else:
                assert len(text.strip()) > 40, index


def test_browser_capture_operates_visible_alfresco_control():
    source = (ROOT / 'scripts/capture_ui_screenshots.py').read_text(encoding='utf8')
    assert "documents.locator('select#document-storage-mode')" in source
    assert "storage.select_option('both')" in source
    assert "expect(storage).to_have_value('both')" in source
    assert "get_by_text(\"Alfresco\").first" not in source
