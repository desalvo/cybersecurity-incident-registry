"""RC95: profile Gravatar controls and explicitly anonymized teaching asset."""
import hashlib
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from werkzeug.datastructures import MultiDict

from test_global_ui_mode import csrf, login, ui_app  # noqa: F401 - reuse real HTTP fixture


def test_avatar_default_uses_https_normalized_email_and_missing_email_falls_back(ui_app):
    from app.ui_settings import global_gravatar_enabled, gravatar_url_for_user
    from app.models import User
    with ui_app.app_context():
        assert global_gravatar_enabled() is True
        user = User(username='gravatar-user', name='Test', email='  Person@Example.org  ', role='reader')
        url = gravatar_url_for_user(user)
        expected = hashlib.md5('person@example.org'.encode()).hexdigest()
        assert url == f'https://secure.gravatar.com/avatar/{expected}?s=80&d=404&r=g'
        user.email = ''
        assert gravatar_url_for_user(user) is None


def test_profile_avatar_is_optional_and_controlled_globally(ui_app):
    from app.models import AuditLog, Setting, User, db
    from app.ui_settings import GLOBAL_GRAVATAR_KEY, global_gravatar_enabled
    client = login(ui_app)
    with ui_app.app_context():
        admin = User.query.filter_by(username='admin').first()
        admin.email = '  Admin.User@Example.com  '
        db.session.commit()
    digest = hashlib.md5(b'admin.user@example.com').hexdigest()
    image_url = f'https://secure.gravatar.com/avatar/{digest}?s=80&amp;d=404&amp;r=g'
    page = client.get('/')
    assert image_url in page.get_data(as_text=True)
    assert "referrerpolicy=\"no-referrer\"" in page.get_data(as_text=True)
    assert 'https://secure.gravatar.com' in page.headers['Content-Security-Policy']
    settings = client.get('/admin/interface')
    assert 'name="gravatar_enabled"' in settings.get_data(as_text=True)
    token = csrf(settings)
    response = client.post('/admin/interface', data={'mode':'modern','gravatar_enabled':'0','_csrf_token':token})
    assert response.status_code == 303
    with ui_app.app_context():
        assert global_gravatar_enabled() is False
        assert db.session.get(Setting,GLOBAL_GRAVATAR_KEY).value == '0'
        assert AuditLog.query.filter_by(operation_type='admin:global_gravatar_update').count() == 1
    assert 'secure.gravatar.com/avatar/' not in client.get('/').get_data(as_text=True)
    response = client.post('/admin/interface',data={'mode':'modern','gravatar_enabled':'1','_csrf_token':csrf(client.get('/admin/interface'))})
    assert response.status_code == 303
    with ui_app.app_context():
        assert global_gravatar_enabled() is True
    assert image_url in client.get('/').get_data(as_text=True)
    # Global switch must affect classic topbar as well.
    client.post('/admin/interface',data={'mode':'classic','gravatar_enabled':'1','_csrf_token':csrf(client.get('/admin/interface'))})
    assert 'class="classic-gravatar"' in client.get('/').get_data(as_text=True)


def test_invalid_avatar_value_rejected_and_tenant_user_cannot_edit(ui_app):
    client = login(ui_app)
    for entries in [[('gravatar_enabled','false')],[('gravatar_enabled','1'),('gravatar_enabled','0')]]:
        form = MultiDict([('mode','modern'),('_csrf_token',csrf(client.get('/admin/interface')))] + entries)
        assert client.post('/admin/interface',data=form).status_code == 400
    low = login(ui_app,'ui-reader')
    assert low.post('/admin/interface',data={'mode':'modern','gravatar_enabled':'0','_csrf_token':csrf(low.get('/'))}).status_code == 403


def test_anonymized_asset_is_pinned_and_builder_explains_provenance():
    root=Path(__file__).resolve().parents[1]
    png=root/'docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png'
    data=png.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='17898ab5874ae15ded91a0c8f2d022402eac9f6c5d212bd72b24dd213965a9ce'
    builder=(root/'scripts/build_training_visual_rc64.js').read_text()
    assert 'USER_DOC_PREVIEW' in builder
    assert 'Modello di notifica anonimizzato approvato' in builder
    assert 'generatedPdfPreview.path' in builder  # current-run original is retained for evidence


def test_approved_image_is_linked_on_both_document_preview_slides():
    root=Path(__file__).resolve().parents[1]
    deck=root/'docs/presentation/CIR_Operational_Training_Visual.pptx'
    if not deck.is_file():
        import pytest
        pytest.skip('Editorial PPTX not installed in this checkout')
    digest='17898ab5874ae15ded91a0c8f2d022402eac9f6c5d212bd72b24dd213965a9ce'
    with ZipFile(deck) as archive:
        for n in (68,115):
            rels=ET.fromstring(archive.read(f'ppt/slides/_rels/slide{n}.xml.rels'))
            targets=[r.attrib.get('Target','') for r in rels]
            assert any(hashlib.sha256(archive.read('ppt/' + t.removeprefix('../'))).hexdigest()==digest
                       for t in targets if t.startswith('../media/')), n
