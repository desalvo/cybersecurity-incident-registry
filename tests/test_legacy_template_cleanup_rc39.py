"""RC39 generalized cleanup regression: no hardcoded template names."""
import pytest
from flask import Flask
from app.models import db, FormTemplateConfig, FormFieldMapping, FormTemplateBinary, AuditLog, NotificationTemplate, Tenant
from app.legacy_template_cleanup import cleanup_unused_legacy_templates

@pytest.fixture
def session(tmp_path):
    app=Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',SQLALCHEMY_TRACK_MODIFICATIONS=False,FORM_TEMPLATE_DIR=str(tmp_path))
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield db.session, tmp_path
        db.session.remove()
        db.drop_all()

def add_model(s,name,mappings=2):
    s.add(FormTemplateConfig(template_name=name))
    for i in range(mappings):
        s.add(FormFieldMapping(template_name=name,template_field=f'field_{i}',db_field='description'))
    s.flush()

def test_unused_missing_pdf_deleted_with_mappings_and_audit(session):
    s,_=session
    add_model(s,'legacy_old_2025',3)
    result=cleanup_unused_legacy_templates(s)
    assert result['deleted'][0]['mappings']==3
    assert s.query(FormTemplateConfig).count()==0
    assert s.query(FormFieldMapping).count()==0
    assert s.query(AuditLog).filter_by(operation_type='legacy_template_cleanup').count()==1
    assert cleanup_unused_legacy_templates(s)['deleted']==[]

def test_rollback_restores_everything(session):
    s,_=session
    add_model(s,'legacy_old_2025',3)
    s.commit()
    cleanup_unused_legacy_templates(s)
    s.rollback()
    assert s.query(FormTemplateConfig).count()==1
    assert s.query(FormFieldMapping).count()==3
    assert s.query(AuditLog).count()==0

def test_existing_pdf_is_preserved(session):
    s,root=session
    add_model(s,'active_doc')
    (root/'active_doc.pdf').write_bytes(b'%PDF-1.4\n')
    assert cleanup_unused_legacy_templates(s)['deleted']==[]
    assert s.query(FormTemplateConfig).count()==1

def test_operational_notification_reference_prevents_deletion(session):
    s,_=session
    add_model(s,'active_doc')
    s.add(Tenant(id=1,name='default'))
    s.add(NotificationTemplate(tenant_id=1,kind='internal',name='alert',linked_form_template_name='active_doc'))
    s.flush()
    result=cleanup_unused_legacy_templates(s)
    assert not result['deleted']
    assert result['preserved'][0]['reason']=='notification_template.linked_form_template_name'

def test_setting_reference_prevents_deletion(session):
    from app.models import Setting
    s,_=session
    add_model(s,'active_doc')
    s.add(Setting(key='test_form_refs',value='{"document_template_name":"active_doc"}'))
    s.flush()
    assert not cleanup_unused_legacy_templates(s)['deleted']
