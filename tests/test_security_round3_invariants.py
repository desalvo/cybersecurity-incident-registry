from pathlib import Path


ROUTES = (Path(__file__).parents[1] / 'app' / 'routes.py').read_text(encoding='utf-8')


def test_tenant_backup_job_passes_scope_to_archive_builder():
    assert "build_backup_archive(categories, scope_tenant_id=getattr(job, 'tenant_id', None))" in ROUTES
    assert "Incident.tenant_id == int(scope_tenant_id)" in ROUTES
    assert "_export_tables_payload(scope_tenant_id)" in ROUTES
    assert "_export_relations_payload(scope_tenant_id)" in ROUTES


def test_tenant_exports_do_not_include_global_authentication_secrets():
    assert "return q.filter(Setting.key.like(prefix))" in ROUTES
    assert "return q.filter(User.id == -1)" in ROUTES
    assert "return q.filter(MfaTotpToken.id == -1)" in ROUTES


def test_backup_s3_credentials_and_endpoint_are_hardened():
    assert "job.s3_secret_key = encrypt_backup_secret(secret)" in ROUTES
    assert "aws_secret_access_key=decrypt_backup_secret(job.s3_secret_key) or None" in ROUTES
    assert "validate_outbound_http_url(endpoint_url, purpose='endpoint S3 backup')" in ROUTES


def test_new_logo_uploads_do_not_accept_svg():
    sso_start = ROUTES.index('def save_sso_logo_upload')
    sso_end = ROUTES.index('def delete_sso_logo_asset', sso_start)
    assert "'.svg'" not in ROUTES[sso_start:sso_end]
