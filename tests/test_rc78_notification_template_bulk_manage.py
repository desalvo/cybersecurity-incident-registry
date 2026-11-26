"""RC78: transaction-safe tenant-specific bulk notification template deletion.

Runs without Flask to cover the core authorization and selection logic; the
existing Flask integration suite exercises routing and published-default sync
when all application dependencies are installed in CI.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, String, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def _function_from_route(name):
    tree = ast.parse((ROOT / 'app/routes.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    return compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])),
                   'app/routes.py', 'exec')


class _Form:
    def __init__(self, ids):
        self.ids = ids
    def getlist(self, name):
        assert name == 'template_ids'
        return self.ids


@pytest.fixture
def route_backend():
    base = declarative_base()
    class Template(base):
        __tablename__ = 'templates'
        id = Column(Integer, primary_key=True)
        tenant_id = Column(Integer, nullable=False)
        kind = Column(String(40), nullable=False)
        name = Column(String(150), nullable=False)
        is_default = Column(Boolean, default=False)
        subject = Column(String, default='')
    engine = create_engine('sqlite:///:memory:')
    base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        Template(tenant_id=10, kind='user', name='Welcome', subject='Tenant override'),
        Template(tenant_id=10, kind='csirt', name='CSIRT'),
        Template(tenant_id=20, kind='user', name='Other tenant'),
    ])
    session.commit()
    context = SimpleNamespace(active=10, admin=True, selected=[], blocked=set(), status=[], restored=set())

    def fail(status, message=''):
        raise PermissionError(status, message)

    def local_query(kind=None):
        query = session.query(Template).filter(Template.tenant_id == context.active)
        if kind:
            query = query.filter(Template.kind == kind)
        return query

    def writable(identifier):
        row = local_query().filter(Template.id == identifier).first()
        if row is None:
            fail(404)
        return row

    def fake_commit():
        # A separate sync test checks the live Tenants Default hooks. Here
        # we model a shared replacement while leaving unrelated tenants intact.
        session.commit()
        for kind, name in context.restored:
            if local_query(kind).filter_by(name=name).first() is None:
                session.add(Template(tenant_id=context.active, kind=kind, name=name,
                                     subject='Shared after removal'))
        session.commit()

    env = {
        'can_admin': lambda: context.admin,
        'abort': fail,
        'ensure_default_notification_templates': lambda: None,
        'db': SimpleNamespace(session=SimpleNamespace(commit=fake_commit,
                                                     rollback=session.rollback, delete=session.delete)),
        'request': SimpleNamespace(method='POST', form=_Form([])),
        'redirect': lambda url: f'REDIRECT:{url}',
        'url_for': lambda name: name,
        'flash': lambda message, category=None: context.status.append((message, category)),
        'writable_notification_template_or_404': writable,
        '_shared_configuration_delete_blocked': lambda kind, row: row.id in context.blocked,
        'current_tenant_notification_template_query': local_query,
        'render_template': lambda *args, **kwargs: (args, kwargs),
        'current_tenant': lambda: SimpleNamespace(is_system_defaults=False),
        'notification_type_map': lambda enabled_only=False: {'user':'Utente', 'csirt':'CSIRT'},
        'audit_log': lambda key, details, actor_type: context.status.append((key, details)),
        'current_tenant_id': lambda: context.active,
        'NotificationTemplate': Template,
    }
    exec(_function_from_route('notification_templates_manage'), env)

    def call(ids, admin=True, active=10):
        context.admin = admin
        context.active = active
        env['request'].method = 'POST'
        env['request'].form = _Form(ids)
        return env['notification_templates_manage']()

    yield SimpleNamespace(call=call, context=context, session=session, Template=Template)
    session.close()
    engine.dispose()


def test_bulk_removes_only_selected_templates_and_leaves_other_tenants(route_backend):
    b = route_backend
    local = b.session.query(b.Template).filter_by(tenant_id=10).all()
    assert len(local) == 2
    assert b.call([str(row.id) for row in local]).startswith('REDIRECT:')
    assert b.session.query(b.Template).filter_by(tenant_id=10).count() == 0
    assert b.session.query(b.Template).filter_by(tenant_id=20).count() == 1


def test_local_override_restores_shared_template_after_delete(route_backend):
    b=route_backend
    local = b.session.query(b.Template).filter_by(tenant_id=10, kind='user').one()
    b.context.restored.add(('user', 'Welcome'))
    b.call([str(local.id)])
    restored = b.session.query(b.Template).filter_by(tenant_id=10, kind='user', name='Welcome').one()
    assert restored.id != local.id
    assert restored.subject == 'Shared after removal'
    assert any('ripristinati' in m for m, _ in b.context.status)


def test_non_admin_and_cross_tenant_ids_are_rejected_before_any_delete(route_backend):
    b = route_backend
    a = b.session.query(b.Template).filter_by(tenant_id=10, kind='user').one()
    foreign = b.session.query(b.Template).filter_by(tenant_id=20).one()
    with pytest.raises(PermissionError) as exc:
        b.call([str(a.id)], admin=False)
    assert exc.value.args[0] == 403
    with pytest.raises(PermissionError) as exc:
        b.call([str(a.id), str(foreign.id)])
    assert exc.value.args[0] == 404
    assert b.session.query(b.Template).filter_by(tenant_id=10).count() == 2


@pytest.mark.parametrize('ids', [['x'], ['0'], ['-1'], ['9'*100], ['1', '1', 'a'], ['1']*501])
def test_invalid_payload_is_rejected_before_delete(route_backend, ids):
    b = route_backend
    with pytest.raises(PermissionError) as exc:
        b.call(ids)
    assert exc.value.args[0] == 400
    assert b.session.query(b.Template).count() == 3


def test_empty_selection_keeps_everything(route_backend):
    b=route_backend
    assert b.call([]).startswith('REDIRECT:')
    assert b.session.query(b.Template).count() == 3
    assert b.context.status[-1][1] == 'warning'


def test_one_blocked_template_prevents_all_deletions(route_backend):
    b=route_backend
    rows=b.session.query(b.Template).filter_by(tenant_id=10).all()
    b.context.blocked.add(rows[-1].id)
    b.call([str(row.id) for row in rows])
    assert b.session.query(b.Template).filter_by(tenant_id=10).count() == 2


def test_navigation_and_page_match_route_contract():
    code=(ROOT/'app/routes.py').read_text()
    page=(ROOT/'app/templates/notification_templates_manage.html').read_text()
    assert "@bp.route('/notifiche/template/gestisci', methods=['GET', 'POST'])" in code
    assert 'name="template_ids"' in page and 'data-cir-notification-select-all' in page
    assert 'data-cir-confirm=' in page and 'Cancella selezionati' in page
    assert 'for entry in templates' in page
    for path in ('app/templates/ui/navigation.html', 'app/templates/base.html'):
        assert "main.notification_templates_manage" in (ROOT/path).read_text()
    assert "'main.notification_templates_manage'" in (ROOT/'app/tenant_defaults_views.py').read_text()


def test_menu_selection_js_is_progressive_and_checked_server_side():
    code=(ROOT/'app/static/ui/ui.js').read_text()
    assert 'data-cir-notification-select-all' in code
    assert 'data-cir-notification-select' in code
    assert 'request.form.getlist(\'template_ids\')' in (ROOT/'app/routes.py').read_text()
