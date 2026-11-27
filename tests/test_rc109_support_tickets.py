"""RC109: Support Tickets multitenancy, lifecycle, attachments and feature gate."""
import io
from pathlib import Path

import pytest


@pytest.fixture
def support_app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'tickets.db'))
    for key in ('UPLOAD_DIR', 'LOGO_DIR', 'SSO_LOGO_DIR', 'FORM_TEMPLATE_DIR',
                'BACKUP_DIR', 'AI_CHATBOT_DOC_DIR', 'SSL_DIR', 'SUPPORT_TICKETS_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv('SECRET_KEY', 'SUPPORT-TICKETS-TEST-SECRET-' * 3)
    monkeypatch.setenv('ADMIN_INITIAL_PASSWORD', 'TestAdminSupport123!')
    monkeypatch.setenv('CIR_DISABLE_BACKGROUND_SCHEDULERS', '1')
    monkeypatch.setenv('CIR_DISABLE_CSRF', '1')
    monkeypatch.delenv('CIR_PRODUCTION', raising=False)
    from app import create_app
    from app.models import db, Setting, Tenant, User, UserTenantRole
    app = create_app()
    app.config.update(TESTING=True)
    with app.app_context():
        t1 = Tenant.query.filter_by(name='default').one()
        t2 = Tenant(name='Support Test Another Tenant')
        t3 = Tenant(name='Support Test Secret Tenant')
        db.session.add_all([t2, t3]); db.session.flush()
        ids = {'a':t1.id, 'b':t2.id, 'c':t3.id}
        ids['super'] = User.query.filter_by(username='admin',auth_provider='local').one().id
        for name, memberships in {
            'reader': [(t1.id, 'reader'), (t2.id, 'reader')],
            'other': [(t1.id, 'reader')],
            'ta': [(t1.id, 'admin')],
            'tb': [(t2.id, 'admin')],
            'tc': [(t3.id, 'admin')],
        }.items():
            uid = User(username='support-'+name, name=name.upper(),
                       email=name+'@example.org', role='disabled',
                       tenant_id=memberships[0][0],default_tenant_id=memberships[0][0],auth_provider='local')
            db.session.add(uid); db.session.flush()
            ids[name]=uid.id
            for tid,role in memberships:
                db.session.add(UserTenantRole(user_id=uid.id,tenant_id=tid,role=role))
        db.session.commit()
        app.config['SUPPORT_TEST_IDS'] = ids
        db.session.merge(Setting(key='plugin_support_tickets_enabled',value='1'))
        db.session.commit()
    from app.plugins.support_tickets import routes
    app.config['SUPPORT_NOTIFY_ORIGINAL'] = routes._notify
    monkeypatch.setattr(routes, '_notify', lambda *a, **kw: None)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def as_user(app, who, tenant='a'):
    client = app.test_client()
    ids = app.config['SUPPORT_TEST_IDS']
    with client.session_transaction() as session:
        session['_user_id'] = str(ids[who])
        session['_fresh'] = True
        session['active_tenant_id'] = ids[tenant]
        session['active_tenant_scope_enabled'] = True
    return client


def new_ticket(client, app, target='a', level='tenant_admin', **kw):
    from app.plugins.support_tickets.models import SupportTicketCategory
    with app.app_context():
        category = SupportTicketCategory.query.filter_by(slug='workflow').one().id
    return client.post('/support/new', data={'tenant_id':app.config['SUPPORT_TEST_IDS'][target],
        'assignee_level':level, 'priority':'high', 'category_id':category,
        'subject': 'Document workflow missing', 'body':'## Help\nWe need **support**.\n\n```html\n<script>alert(1)</script>\n```',
        **kw}, follow_redirects=False)


def test_feature_flag_defaults_disabled_and_superadmin_controls(support_app):
    from app.models import db, Setting
    from app.plugins.support_tickets.models import SupportTicketCategory
    r = as_user(support_app, 'reader')
    with support_app.app_context():
        assert SupportTicketCategory.query.count() >= 5
        db.session.get(Setting, 'plugin_support_tickets_enabled').value = '0'; db.session.commit()
    assert r.get('/support/').status_code == 404
    assert r.get('/support/admin').status_code == 403
    root = as_user(support_app, 'super')
    assert root.get('/support/admin').status_code == 200
    assert root.post('/support/admin',data={'action':'toggle','enabled':'1'}).status_code == 302
    assert r.get('/support/').status_code == 200
    assert r.get('/support/new').status_code == 200


def test_create_cross_accessible_tenant_and_invisible_to_unrelated_users(support_app):
    reader = as_user(support_app, 'reader')
    result = new_ticket(reader, support_app, target='b')
    assert result.status_code == 302
    from app.plugins.support_tickets.models import SupportTicket
    with support_app.app_context():
        row = SupportTicket.query.one()
        assert row.status=='submitted' and row.tenant_id==support_app.config['SUPPORT_TEST_IDS']['b']
        assert row.priority=='high' and row.status_reason == ''
        row_id = row.id
    assert reader.get(f'/support/tickets/{row_id}').status_code == 200
    assert as_user(support_app, 'other').get(f'/support/tickets/{row_id}').status_code == 404
    assert as_user(support_app, 'ta').get(f'/support/tickets/{row_id}').status_code == 404
    assert as_user(support_app, 'tb', 'b').get(f'/support/tickets/{row_id}').status_code == 200
    assert as_user(support_app, 'super').get(f'/support/tickets/{row_id}').status_code == 200
    assert new_ticket(as_user(support_app, 'other'), support_app, target='c').status_code == 403


def test_manage_reply_close_reopen_and_escalation_permissions(support_app):
    owner = as_user(support_app,'reader')
    assert new_ticket(owner, support_app).status_code==302
    from app.plugins.support_tickets.models import SupportTicket
    with support_app.app_context():
        t = SupportTicket.query.one().id
    unauth = as_user(support_app,'other')
    assert unauth.post(f'/support/tickets/{t}/status', data={'status':'rejected'}).status_code == 404
    assert owner.post(f'/support/tickets/{t}/status', data={'status':'rejected'}).status_code == 403
    assert as_user(support_app,'tb', 'b').post(f'/support/tickets/{t}/status',data={'status':'assigned'}).status_code == 404
    manager = as_user(support_app,'ta')
    assert manager.post(f'/support/tickets/{t}/status', data={'status':'in_progress','reason':'Verifica necessaria'}).status_code == 302
    assert manager.post(f'/support/tickets/{t}/escalate').status_code == 302
    with support_app.app_context():
        row = SupportTicket.query.one()
        assert row.status=='in_progress' and row.status_reason=='Verifica necessaria'
        assert row.escalated and row.assignee_level == 'super_admin'
    assert manager.post(f'/support/tickets/{t}/reply',data={'body':'Verificato con il livello superiore'}).status_code == 302
    assert owner.post(f'/support/tickets/{t}/status',data={'status':'closed'}).status_code == 302
    assert manager.post(f'/support/tickets/{t}/reply',data={'body':'test'}).status_code == 409
    assert owner.post(f'/support/tickets/{t}/status',data={'status':'submitted'}).status_code == 302
    assert owner.post(f'/support/tickets/{t}/reply',data={'body':'Riaperto, grazie'}).status_code == 302


def test_direct_to_superadmins_not_visible_to_tenant_admins(support_app):
    owner=as_user(support_app, 'reader')
    assert new_ticket(owner,support_app,level='super_admin').status_code==302
    from app.plugins.support_tickets.models import SupportTicket
    with support_app.app_context():
        ticket=SupportTicket.query.one().id
    assert as_user(support_app, 'ta').get(f'/support/tickets/{ticket}').status_code==404
    assert as_user(support_app, 'super').get(f'/support/tickets/{ticket}').status_code==200


def test_attachments_private_download_and_safe_markdown(support_app):
    client=as_user(support_app,'reader')
    response = new_ticket(client, support_app, attachments=(io.BytesIO(b'hello sensitive'), 'proof.txt'))
    assert response.status_code==302
    from app.plugins.support_tickets.models import SupportTicketAttachment, SupportTicket
    with support_app.app_context():
        attachment = SupportTicketAttachment.query.one()
        tid = attachment.message.ticket_id
        aid = attachment.id
        assert attachment.sha256 and attachment.byte_count==15
    body=client.get(f'/support/tickets/{tid}').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in body
    assert '&lt;script&gt;' in body
    download=client.get(f'/support/attachments/{aid}')
    assert download.status_code==200 and download.data==b'hello sensitive'
    assert 'attachment' in download.headers['Content-Disposition']
    assert as_user(support_app,'other').get(f'/support/attachments/{aid}').status_code==404
    assert as_user(support_app,'ta').get(f'/support/attachments/{aid}').status_code==200
    assert client.post(f'/support/tickets/{tid}/reply',data={'body':'reply','attachments':(io.BytesIO(b'x'), 'malware.html')}).status_code==302
    with support_app.app_context():
        assert SupportTicketAttachment.query.count()==1


def test_search_composes_filters_and_superadmin_deletes_with_double_confirmation(support_app):
    client=as_user(support_app,'reader')
    assert new_ticket(client,support_app).status_code==302
    from app.plugins.support_tickets.models import SupportTicket
    with support_app.app_context():
        tid=SupportTicket.query.one().id
    assert b'SUP-000001' in client.get('/support/?priority=high&status=submitted&q=workflow').data
    assert b'SUP-000001' not in client.get('/support/?priority=low&status=submitted').data
    assert client.post(f'/support/tickets/{tid}/delete', data={'confirm_reference':f'SUP-{tid:06d}'}).status_code==403
    superadmin=as_user(support_app,'super')
    assert superadmin.post(f'/support/tickets/{tid}/delete',data={'confirm_reference':'wrong'}).status_code==400
    assert superadmin.post(f'/support/tickets/{tid}/delete',data={'confirm_reference':f'SUP-{tid:06d}'}).status_code==302
    with support_app.app_context():
        assert SupportTicket.query.count()==0


def test_add_category_is_exclusive_to_superadmin(support_app):
    client=as_user(support_app,'super')
    resp=client.post('/support/admin',data={'action':'add_category','slug':'integrazioni','label_it':'Integrazioni','label_en':'Integrations'})
    assert resp.status_code==302
    from app.plugins.support_tickets.models import SupportTicketCategory
    with support_app.app_context():
        assert SupportTicketCategory.query.filter_by(slug='integrazioni').count()==1
    assert as_user(support_app,'ta').post('/support/admin',data={'action':'add_category','slug':'abc','label_it':'ABC'}).status_code==403


def test_csrf_enforced_for_ticket_writes(support_app, monkeypatch):
    monkeypatch.setenv('CIR_DISABLE_CSRF', '0')
    client = as_user(support_app, 'reader')
    assert client.post('/support/new', data={'subject':'Test'}).status_code == 400
    # New forms must carry the existing CIR anti-CSRF token.
    import re
    html = client.get('/support/new').get_data(as_text=True)
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match, 'Support Tickets form omitted its CSRF token'
    from app.plugins.support_tickets.models import SupportTicketCategory
    with support_app.app_context():
        category=SupportTicketCategory.query.filter_by(slug='workflow').one().id
    good = client.post('/support/new', data={'_csrf_token':match.group(1),
        'tenant_id':support_app.config['SUPPORT_TEST_IDS']['a'],
        'assignee_level':'tenant_admin', 'priority':'low', 'category_id':category,
        'subject':'Need assistance', 'body':'Please advise'}, follow_redirects=False)
    assert good.status_code == 302


def test_tenant_email_html_and_no_message_body_leak(support_app, monkeypatch):
    from app.plugins.support_tickets.mail import ticket_email_html
    from app.plugins.support_tickets.models import SupportTicket
    from app.models import db, Setting, User
    from app.plugins.support_tickets import routes
    assert new_ticket(as_user(support_app, 'reader'), support_app).status_code == 302
    with support_app.app_context():
        ticket = SupportTicket.query.one()
        rendered = ticket_email_html(ticket, 'Nuova risposta', 'https://cir.example.org/support/tickets/1', 'Aperto', 'Alta')
        assert 'href="https://cir.example.org/support/tickets/1"' in rendered
        assert 'Need **support**' not in rendered
        assert 'Support Tickets' in rendered
        tid=ticket.tenant_id
        for key,value in {'smtp_host':'mail.example.org','smtp_port':'587', 'smtp_use_tls':'0',
                          'smtp_use_ssl':'0','smtp_auth_enabled':'0','smtp_default_sender':'cir@example.org',
                          'application_external_url':'https://cir.example.org'}.items():
            db.session.merge(Setting(key=key if key=='application_external_url' else f'tenant:{tid}:{key}',value=value))
        db.session.commit()
        sent=[]
        class FakeSMTP:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def send_message(self,email):sent.append(email)
            def starttls(self):pass
            def login(self,*args):pass
        monkeypatch.setattr(routes.smtplib,'SMTP',FakeSMTP)
        monkeypatch.setattr(routes,'validate_outbound_host',lambda hostname,**kwargs:hostname)
        from flask_login import login_user
        with support_app.test_request_context('/'):
            login_user(db.session.get(User,support_app.config['SUPPORT_TEST_IDS']['reader']))
            support_app.config['SUPPORT_NOTIFY_ORIGINAL'](ticket, 'created')
        assert len(sent)==1
        assert sent[0]['To']=='ta@example.org'
        assert sent[0]['From']=='cir@example.org'
        assert 'https://cir.example.org/support/tickets/' in sent[0].get_body(preferencelist=('html',)).get_content()
        with support_app.test_request_context('/'):
            login_user(db.session.get(User,support_app.config['SUPPORT_TEST_IDS']['ta']))
            support_app.config['SUPPORT_NOTIFY_ORIGINAL'](ticket,'reply')
        assert any(email['To']=='reader@example.org' for email in sent)


def test_full_export_includes_support_history_and_private_files(support_app):
    from app.routes import _export_tables_payload, _full_export_persistent_file_manifest
    from app.plugins.support_tickets.models import SupportTicket
    from app.models import db
    client=as_user(support_app,'reader')
    assert new_ticket(client,support_app,attachments=(io.BytesIO(b'confidential'), 'log.txt')).status_code==302
    with support_app.app_context():
        exported=_export_tables_payload()
        assert len(exported['support_tickets'])==1
        assert len(exported['support_ticket_messages'])==1
        assert len(exported['support_ticket_attachments'])==1
        assert exported['support_ticket_categories']
        manifest=_full_export_persistent_file_manifest()
        assert len(manifest['support_tickets'])==1
        attachment=exported['support_ticket_attachments'][0]
        assert manifest['support_tickets'][0]['relative_path']==attachment['stored_filename']


def test_full_backup_archive_contains_support_rows_and_binary_attachments(support_app):
    import tarfile,json
    from app.routes import build_full_export_archive_for_backup
    client=as_user(support_app,'reader')
    assert new_ticket(client,support_app,attachments=(io.BytesIO(b'ticket backup bytes'), 'trace.txt')).status_code==302
    with support_app.app_context():
        archive_name=build_full_export_archive_for_backup(prefix='support-test')
    with tarfile.open(archive_name,'r:gz') as archive:
        export=json.load(archive.extractfile('export.json'))
        assert len(export['tables']['support_tickets'])==1
        assert len(export['tables']['support_ticket_messages'])==1
        assert len(export['tables']['support_ticket_attachments'])==1
        name=export['tables']['support_ticket_attachments'][0]['stored_filename']
        assert archive.extractfile(f'files/persistent/support_tickets/{name}').read()==b'ticket backup bytes'


def test_tenant_export_excludes_private_direct_superadmin_conversation(support_app):
    assert new_ticket(as_user(support_app,'reader'),support_app,level='super_admin').status_code==302
    assert new_ticket(as_user(support_app,'reader'),support_app,level='tenant_admin').status_code==302
    from app.models import db,User
    from flask_login import login_user
    from app.routes import _export_tables_payload
    with support_app.test_request_context('/'):
        ids=support_app.config['SUPPORT_TEST_IDS']
        login_user(db.session.get(User,ids['ta']))
        rows=_export_tables_payload(ids['a'])
        assert len(rows['support_tickets'])==1
        assert rows['support_tickets'][0]['assignee_level']=='tenant_admin'
        assert len(rows['support_ticket_messages'])==1


def test_priority_category_editing_respects_owner_and_manager_permissions(support_app):
    assert new_ticket(as_user(support_app,'reader'),support_app).status_code == 302
    from app.plugins.support_tickets.models import SupportTicket,SupportTicketCategory
    with support_app.app_context():
        tid=SupportTicket.query.one().id
        category=SupportTicketCategory.query.filter_by(slug='incidenti').one().id
    path=f'/support/tickets/{tid}/details'
    payload={'priority':'urgent','category_id':category}
    assert as_user(support_app,'other').post(path,data=payload).status_code==404
    assert as_user(support_app,'tb','b').post(path,data=payload).status_code==404
    assert as_user(support_app,'reader').post(path,data=payload).status_code==302
    with support_app.app_context():
        ticket=SupportTicket.query.one()
        assert ticket.priority=='urgent' and ticket.category_id==category
    assert as_user(support_app,'ta').post(f'/support/tickets/{tid}/status',data={'status':'in_progress'}).status_code==302
    assert as_user(support_app,'reader').post(path,data=payload).status_code==403
    assert as_user(support_app,'ta').post(path,data={'priority':'medium','category_id':category}).status_code==302
    assert as_user(support_app,'super').post(path,data={'priority':'low','category_id':category,'assignee_level':'super_admin'}).status_code==302
    with support_app.app_context():
        assert SupportTicket.query.one().assignee_level=='super_admin'


def test_global_full_export_import_restores_support_ticket_and_file(support_app):
    """Exercise CIR's destructive full restore, not just export JSON serialization."""
    assert new_ticket(as_user(support_app,'reader'), support_app,
                      attachments=(io.BytesIO(b'from a full restore'), 'proof.txt')).status_code==302
    client=as_user(support_app, 'super')
    exported=client.get('/export/full')
    assert exported.status_code==200
    archive=exported.data
    from app.plugins.support_tickets.models import SupportTicket,SupportTicketAttachment
    with support_app.app_context():
        original_id=SupportTicket.query.one().id
    assert client.post(f'/support/tickets/{original_id}/delete',
        data={'confirm_reference':f'SUP-{original_id:06d}'}).status_code==302
    with support_app.app_context():
        assert SupportTicket.query.count()==0
    imported=client.post('/import/full',
        data={'file':(io.BytesIO(archive),'full-backup.tar.gz')},
        content_type='multipart/form-data',follow_redirects=False)
    assert imported.status_code==302, imported.get_data(as_text=True)[:500]
    with support_app.app_context():
        assert SupportTicket.query.count()==1
        assert SupportTicketAttachment.query.count()==1
        attachment=SupportTicketAttachment.query.one()
        assert (Path(support_app.config['SUPPORT_TICKETS_DIR'])/attachment.stored_filename).read_bytes()==b'from a full restore'


def test_tenant_scoped_restore_remaps_support_ids_and_preserves_private_l2_ticket(support_app):
    owner=as_user(support_app,'reader')
    assert new_ticket(owner,support_app,target='a',level='super_admin',
                      attachments=(io.BytesIO(b'private-l2'), 'private.txt')).status_code==302
    assert new_ticket(owner,support_app,target='a',level='tenant_admin',
                      attachments=(io.BytesIO(b'public-l1'), 'public.txt')).status_code==302
    from app.plugins.support_tickets.models import SupportTicket,SupportTicketAttachment
    from app.models import db
    manager=as_user(support_app,'ta')
    raw=manager.get('/export/full')
    assert raw.status_code==200
    import json,tarfile
    with tarfile.open(fileobj=io.BytesIO(raw.data),mode='r:gz') as archive:
        manifest=json.load(archive.extractfile('export.json'))
        assert manifest['scope']=='tenant'
        assert len(manifest['tables']['support_tickets'])==1
        assert len(manifest['tables']['support_ticket_attachments'])==1
        assert len(manifest['files']['persistent_files']['support_tickets'])==1
    with support_app.app_context():
        old_l2=SupportTicket.query.filter_by(assignee_level='super_admin').one().id
    restored=manager.post('/import/full',data={'file':(io.BytesIO(raw.data),'tenant-export.tar.gz')},
                          content_type='multipart/form-data',follow_redirects=False)
    assert restored.status_code==302,restored.get_data(as_text=True)[:300]
    with support_app.app_context():
        assert SupportTicket.query.filter_by(assignee_level='super_admin').one().id==old_l2
        assert SupportTicket.query.filter_by(assignee_level='tenant_admin').count()==1
        attachments=SupportTicketAttachment.query.all()
        assert sorted((Path(support_app.config['SUPPORT_TICKETS_DIR'])/f.stored_filename).read_bytes() for f in attachments)==[b'private-l2',b'public-l1']
