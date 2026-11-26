"""RC87: statistics scope, export and multi-tenant privacy regression."""
from datetime import timedelta
import csv
import io
import json
import re


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'statistics.db'))
    for name, folder in [('UPLOAD_DIR', 'uploads'), ('LOGO_DIR', 'logos'),
                         ('SSO_LOGO_DIR', 'sso'), ('FORM_TEMPLATE_DIR', 'forms'),
                         ('BACKUP_DIR', 'backup'), ('AI_CHATBOT_DOC_DIR', 'ai_docs')]:
        monkeypatch.setenv(name, str(tmp_path / folder))
    monkeypatch.setenv('SECRET_KEY', 'R' * 64)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'AdminPassword123!')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)


def _login(client, username, password):
    page = client.get('/login')
    token = re.search(r'name="_csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    assert token is not None
    response = client.post('/login', data={
        '_csrf_token': token.group(1), 'username': username, 'password': password,
    }, follow_redirects=True)
    assert response.status_code == 200


def test_cross_tenant_statistics_scoped_to_super_admin_and_available_as_exports(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    from app import create_app
    from app.models import db, Tenant, Incident, User
    from app.auth import hash_password
    from app.timeutils import utcnow
    from app.routes import upsert_user_tenant_role

    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        default = Tenant.query.filter_by(name='default').one()
        other = Tenant(name='second-laboratory', description='Tenant di prova')
        db.session.add(other)
        db.session.flush()
        stamp = utcnow() - timedelta(hours=1)
        for tid, ref in [(default.id, 'STATS-TENANT-A'), (other.id, 'STATS-TENANT-B')]:
            incident = Incident(tenant_id=tid, name=ref, reference=ref,
                                creator_name='Training Fixture',
                                creator_email='example@invalid.test', status='aperto')
            incident.start_at = stamp
            db.session.add(incident)
        reader = User(username='stats-reader', auth_provider='local', role='reader',
                      tenant_id=default.id, default_tenant_id=default.id,
                      password_hash=hash_password('StatisticsReader123!'))
        db.session.add(reader)
        db.session.flush()
        upsert_user_tenant_role(reader, default.id, 'reader')
        db.session.commit()

    super_client = app.test_client()
    _login(super_client, 'admin', 'AdminPassword123!')

    default_stats = super_client.get('/reports/stats.json').get_json()
    assert default_stats['scope'] == 'tenant'
    assert default_stats['periods'][0]['count'] == 1
    assert default_stats['periods'][0]['tenant_breakdown'] == []

    global_response = super_client.get('/reports/stats.json?scope=all')
    assert global_response.status_code == 200
    assert global_response.headers['Cache-Control'].startswith('private, no-store')
    assert global_response.get_json()['periods'][0]['count'] == 2

    grouped = super_client.get('/reports/stats.json?scope=per_tenant')
    assert grouped.status_code == 200
    result = grouped.get_json()['periods'][0]
    assert result['count'] == 2
    assert {row['tenant']: row['count'] for row in result['tenant_breakdown']} == {
        'default': 1, 'second-laboratory': 1,
    }
    page = super_client.get('/reports/stats?scope=per_tenant')
    assert page.status_code == 200
    assert b'second-laboratory' in page.data
    assert b'Esporta CSV' in page.data and b'Esporta JSON' in page.data
    csv_response = super_client.get('/reports/stats.csv?scope=per_tenant')
    assert csv_response.status_code == 200
    records = list(csv.DictReader(io.StringIO(csv_response.get_data(as_text=True))))
    assert {r['Tenant'] for r in records} == {'default', 'second-laboratory'}
    assert all(r['Incidenti'] == '1' for r in records)
    pdf_response = super_client.get('/reports/stats.pdf?scope=per_tenant')
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b'%PDF-')
    assert super_client.get('/reports/stats.json?scope=bogus').status_code == 400

    reader_client = app.test_client()
    _login(reader_client, 'stats-reader', 'StatisticsReader123!')
    for endpoint in ['/reports/stats', '/reports/stats.pdf', '/reports/stats.json', '/reports/stats.csv']:
        assert reader_client.get(endpoint).status_code == 200
        for scope in ('all', 'per_tenant'):
            response = reader_client.get(endpoint + '?scope=' + scope)
            assert response.status_code == 403, (endpoint, scope, response.status_code)
    assert reader_client.get('/reports/stats.json').get_json()['periods'][0]['count'] == 1


def test_visual_training_stats_explains_scopes_and_connectors():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / 'docs/presentation/visual_rc64_spec.json').read_text(encoding='utf-8'))
    stats = next(row for row in source if row.get('original') == 24)
    text = ' '.join(stats['bullets']).lower()
    assert all(value in text for value in ['tenant', 'cross-tenant', 'super admin', 'global', 'csv', 'json', 'connettori'])
    assert 'dati sintetici' in stats['notes']
    builder = (root / 'scripts/build_training_visual_rc64.js').read_text(encoding='utf-8')
    assert "d.original===24" in builder
    assert 'CROSS-TENANT' in builder and 'PDF · CSV · JSON' in builder
