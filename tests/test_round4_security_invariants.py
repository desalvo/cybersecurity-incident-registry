import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'app' / 'routes.py').read_text(encoding='utf-8')


def test_incident_clone_is_post_only():
    tree = ast.parse(ROUTES)
    clone = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'clone')
    route = next(d for d in clone.decorator_list if isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'route')
    methods = next(ast.literal_eval(k.value) for k in route.keywords if k.arg == 'methods')
    assert methods == ['POST']


def test_external_protocols_use_outbound_policy():
    assert "validate_outbound_ldap_uri(uri, purpose='LDAP login')" in ROUTES
    assert "validate_outbound_host(host, purpose='SMTP')" in ROUTES


def test_sensitive_external_errors_are_not_flushed_to_ui():
    forbidden = [
        "Login SSO fallito: {exc}",
        "Errore invio mail di prova: {exc}",
        "Errore invio notifica: {exc}",
        "Errore upload Alfresco: {exc}",
        "Errore download Alfresco: {exc}",
    ]
    for marker in forbidden:
        assert marker not in ROUTES
