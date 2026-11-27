"""RC100: color bubbles, tenant isolation and strong encrypted aggregate exports."""
import csv
import io
import json
import re
from datetime import timedelta
from xml.etree import ElementTree as ET

import pytest

from app.statistics_visuals import (
    bubble_limit, incident_aggregates, export_bytes, encrypt_export, decrypt_export,
)


def test_aggregation_deduplicates_categories_per_incident_and_orders_counts():
    class Label:
        def __init__(self, value): self.value=value
    class Incident:
        def __init__(self, tenant_id, categories):
            self.tenant_id=tenant_id
            self.categories=[Label(c) for c in categories]
    rows=[Incident(1,['SPAM','SPAM','PHISHING']),Incident(2,['SPAM']),Incident(1,[])]
    names={1:'A',2:'B'}
    assert incident_aggregates(rows,names,'tenant')==[
        {'tenant':'A','category':'','tenant_id':1,'label':'A','count':2},
        {'tenant':'B','category':'','tenant_id':2,'label':'B','count':1},
    ]
    assert incident_aggregates(rows,names,'category')[0]['count']==2
    assert {r['label']:r['count'] for r in incident_aggregates(rows,names,'tenant_category')}=={
        'A · SPAM':1,'A · PHISHING':1,'B · SPAM':1}
    assert bubble_limit('30')==30
    assert bubble_limit('100')==100
    for candidate in ('0','101','abc'):
        with pytest.raises(ValueError):bubble_limit(candidate)


def test_json_xml_csv_have_same_counts_and_csv_formula_injection_protection():
    payload={'schema_version':1,'generated_at':'2026-11-26T10:00', 'scope':'per_tenant',
             'mode':'tenant_category','start':'','end':'','total_incidents':4,
             'rows':[{'tenant_id':1,'tenant':'=Evil','category':'@SPAM', 'count':4}]}
    j,_=export_bytes(payload,'json')
    x,_=export_bytes(payload,'xml')
    c,_=export_bytes(payload,'csv')
    assert json.loads(j)['rows'][0]['count']==4
    assert ET.fromstring(x).find('rows/row/count').text=='4'
    record=next(csv.DictReader(io.StringIO(c.decode('utf-8-sig'))))
    assert record['Tenant']=="'=Evil" and record['Categoria']=="'@SPAM"
    with pytest.raises(ValueError):export_bytes(payload,'xlsx')


def test_authenticated_encrypted_export_roundtrip_and_tamper_detection():
    from cryptography.exceptions import InvalidTag
    content=b'<statistics>confidential aggregated counts</statistics>'
    encoded=encrypt_export(content,'HighEntropyPassword2026!')
    assert content not in encoded
    assert decrypt_export(encoded,'HighEntropyPassword2026!')==content
    with pytest.raises(InvalidTag):decrypt_export(encoded,'IncorrectPassword123!')
    altered=json.loads(encoded);altered['ciphertext']='A'+altered['ciphertext'][1:]
    with pytest.raises(InvalidTag):decrypt_export(json.dumps(altered).encode(), 'HighEntropyPassword2026!')
    with pytest.raises(ValueError):encrypt_export(content,'short')


def _configure(monkeypatch,tmp_path):
    from tests.test_rc87_statistics_scope import _configure as original
    original(monkeypatch,tmp_path)


def _login(client,user,password):
    from tests.test_rc87_statistics_scope import _login as original
    original(client,user,password)


def test_superuser_can_see_cross_tenant_bubbles_and_reader_cannot(monkeypatch,tmp_path):
    _configure(monkeypatch,tmp_path)
    from app import create_app
    from app.models import db,Tenant,Incident,User,ConfigLabel
    from app.auth import hash_password
    from app.timeutils import utcnow
    from app.routes import upsert_user_tenant_role
    app=create_app();app.config['TESTING']=True
    with app.app_context():
        tenant=Tenant.query.filter_by(name='default').one()
        other=Tenant(name='rc100-secondary')
        db.session.add(other);db.session.flush()
        spam_a=ConfigLabel.query.filter_by(tenant_id=tenant.id,kind='category',value='SPAM').first()
        if spam_a is None:
            spam_a=ConfigLabel(tenant_id=tenant.id,kind='category',value='SPAM')
            db.session.add(spam_a)
        spam_b=ConfigLabel(tenant_id=other.id,kind='category',value='SPAM')
        db.session.add(spam_b);db.session.flush()
        stamp=utcnow()-timedelta(hours=1)
        for tid,cat,name in [(tenant.id,spam_a,'A1'),(tenant.id,spam_a,'A2'),(other.id,spam_b,'B1')]:
            item=Incident(tenant_id=tid,name=name,reference=name,creator_name='Synthetic Test',
                          creator_email='fake@invalid.test',status='aperto')
            item.start_at=stamp;item.categories.append(cat);db.session.add(item)
        reader=User(username='rc100-reader',auth_provider='local',role='reader',
                    tenant_id=tenant.id,default_tenant_id=tenant.id,
                    password_hash=hash_password('ReaderPassword123!'))
        db.session.add(reader);db.session.flush()
        upsert_user_tenant_role(reader,tenant.id,'reader')
        db.session.commit()
    client=app.test_client();_login(client,'admin','AdminPassword123!')
    page=client.get('/reports/stats?bubble_mode=tenant_category&bubble_limit=30')
    assert page.status_code==200
    html=page.get_data(as_text=True)
    assert 'Panoramica a bolle' in html and 'rc100-secondary' in html
    assert 'cir-bubble-scene' in html and 'AES-256-GCM' in html
    payload=client.get('/reports/stats.aggregates.json?scope=all&mode=tenant_category').get_json()
    assert {r['label']:r['count'] for r in payload['rows'] if r['category']=='SPAM'}=={
        'default · SPAM':2,'rc100-secondary · SPAM':1}
    assert client.get('/reports/stats?bubble_limit=999').status_code==400
    for mode in ['tenant','category','tenant_category']:
        assert client.get('/reports/stats.aggregates.json?scope=all&mode='+mode).status_code==200
    assert ET.fromstring(client.get('/reports/stats.xml?scope=all').data).find('rows/row') is not None
    token=re.search(r'name="_csrf_token" value="([^"]+)"',html).group(1)
    post={'_csrf_token':token,'scope':'all','mode':'tenant_category',
          'format':'xml','encrypt':'1','password':'VerySecretForStatistics2026'}
    encrypted=client.post('/reports/stats.export',data=post)
    assert encrypted.status_code==200
    assert 'no-store' in encrypted.headers['Cache-Control']
    assert 'attachment' in encrypted.headers['Content-Disposition']
    decoded=decrypt_export(encrypted.data,post['password'])
    assert ET.fromstring(decoded).find('rows/row') is not None
    assert client.post('/reports/stats.export',data={**post,'password':'123'}).status_code==400
    assert client.post('/reports/stats.export',data={**post,'format':'txt'}).status_code==400
    reader_client=app.test_client();_login(reader_client,'rc100-reader','ReaderPassword123!')
    reader_page=reader_client.get('/reports/stats')
    assert reader_page.status_code==200 and 'cir-bubble-scene' not in reader_page.get_data(as_text=True)
    assert reader_client.get('/reports/stats.aggregates.json?scope=all').status_code==403
    assert reader_client.get('/reports/stats.xml?scope=per_tenant').status_code==403
    assert reader_client.get('/reports/stats.aggregates.json?scope=tenant').get_json()['total_incidents']==2
    reader_html=reader_page.get_data(as_text=True)
    reader_token=re.search(r'name="_csrf_token" value="([^"]+)"',reader_html).group(1)
    assert reader_client.post('/reports/stats.export',data={**post,'_csrf_token':reader_token}).status_code==403
    assert reader_client.post('/reports/stats.export',data={**post,'_csrf_token':reader_token,'scope':'tenant'}).status_code==200


def test_training_master_contains_synthetic_cross_tenant_bubble_sample():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    spec=json.loads((root/'docs/presentation/visual_rc64_spec.json').read_text())
    italian=next(x for x in spec if x['original']==24)
    assert 'bolle 3D' in ' '.join(italian['bullets'])
    assert 'dati sintetici' in italian['notes']
    builder=(root/'scripts/build_training_visual_rc64.js').read_text()
    assert "Tenant A\\nSPAM" in builder and 'b.r' in builder
    translated=json.loads((root/'docs/presentation/visual_rc98_english_slides.json').read_text())
    assert '3D bubble' in ' '.join(translated['slides']['32'])
