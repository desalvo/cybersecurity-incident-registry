"""Dynamic AGID secure-development compliance checks.

The tests exercise the Flask application with a real test client and a
throw-away SQLite database.  They are intentionally focused on controls
required by the AGID secure-coding guidelines: server-side validation,
CSRF/session hardening, disabled TRACE/TRACK, least-privilege access,
auditability, upload validation and SSRF protections for configurable AI
endpoints.
"""
from __future__ import annotations

import io

import pytest


@pytest.fixture()
def isolated_app(monkeypatch, tmp_path):
    base = tmp_path
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(base / "agid.db"))
    monkeypatch.setenv("UPLOAD_DIR", str(base / "uploads"))
    monkeypatch.setenv("LOGO_DIR", str(base / "logos"))
    monkeypatch.setenv("SSO_LOGO_DIR", str(base / "sso"))
    monkeypatch.setenv("FORM_TEMPLATE_DIR", str(base / "forms"))
    monkeypatch.setenv("BACKUP_DIR", str(base / "backups"))
    monkeypatch.setenv("AI_CHATBOT_DOC_DIR", str(base / "ai_docs"))
    monkeypatch.setenv("SECRET_KEY", "T" * 64)
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "AdminPassword123!")
    monkeypatch.delenv("CIR_PRODUCTION", raising=False)
    monkeypatch.delenv("CIR_AI_ALLOW_CUSTOM_ENDPOINTS", raising=False)
    monkeypatch.delenv("CIR_AI_ALLOW_PRIVATE_ENDPOINTS", raising=False)

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture()
def client(isolated_app):
    return isolated_app.test_client()


def _csrf_from_session(client) -> str:
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def _login_as_admin(client):
    client.get("/login")
    token = _csrf_from_session(client)
    return client.post(
        "/login",
        data={"username": "admin", "password": "AdminPassword123!", "_csrf_token": token},
        follow_redirects=False,
    )


def test_agid_security_headers_and_cookie_flags(client):
    response = client.get("/login", base_url="https://localhost")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "script-src 'self' 'nonce-" in response.headers["Content-Security-Policy"]
    assert "base-uri 'self'" in response.headers["Content-Security-Policy"]
    set_cookie = response.headers.get("Set-Cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie


def test_agid_trace_track_are_rejected_before_routes(client):
    assert client.open("/login", method="TRACE").status_code == 405
    assert client.open("/login", method="TRACK").status_code == 405


def test_agid_csrf_is_required_for_unsafe_methods(client):
    client.get("/login")
    response = client.post("/login", data={"username": "admin", "password": "AdminPassword123!"})
    assert response.status_code == 400


def test_agid_login_error_does_not_enumerate_users_and_records_audit(client, isolated_app):
    client.get("/login")
    token = _csrf_from_session(client)
    response = client.post(
        "/login",
        data={"username": "missing-user", "password": "wrong", "_csrf_token": token},
    )
    assert response.status_code == 200
    assert "Credenziali non valide" in response.get_data(as_text=True)
    assert "missing-user" not in response.get_data(as_text=True)

    with isolated_app.app_context():
        from app.models import AuditLog

        assert AuditLog.query.filter_by(operation_type="security:login_failure").count() >= 1


def test_agid_access_control_denies_admin_area_to_anonymous_user(client):
    response = client.get("/admin/users", follow_redirects=False)
    assert response.status_code in {302, 401}
    if response.status_code == 302:
        assert "/login" in response.headers.get("Location", "")


def test_agid_admin_login_uses_server_side_lockout_model(client, isolated_app):
    login_response = _login_as_admin(client)
    assert login_response.status_code in {302, 200}

    with isolated_app.app_context():
        from app.models import LoginFailure, User

        assert LoginFailure.__table__.c.rate_key.unique
        assert User.query.filter_by(username="admin", auth_provider="local").first() is not None


def test_agid_output_escaping_on_user_supplied_incident_name(client):
    assert _login_as_admin(client).status_code in {302, 200}
    client.get("/incident/new")
    token = _csrf_from_session(client)
    payload = {
        "name": "<script>alert(1)</script>",
        "reference": "ref-xss",
        "severity": "media",
        "status": "aperto",
        "start_date": "2026-05-22",
        "start_time": "10:00",
        "description": "<img src=x onerror=alert(1)>",
        "_csrf_token": token,
    }
    response = client.post("/incident/new", data=payload, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body or "ref-xss" in body


def test_agid_upload_validation_rejects_unsafe_chatbot_upload(client):
    assert _login_as_admin(client).status_code in {302, 200}
    client.get("/ai-chatbot/admin/documents")
    token = _csrf_from_session(client)
    response = client.post(
        "/ai-chatbot/admin/documents",
        data={
            "title": "bad upload",
            "_csrf_token": token,
            "document": (io.BytesIO(b"#!/bin/sh\necho owned\n"), "payload.sh"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Estensione file non consentita" in body or "non consentita" in body


def test_agid_ai_endpoint_validation_blocks_private_networks(monkeypatch):
    from app.plugins.ai_chatbot.security import validate_ai_endpoint

    monkeypatch.setenv("CIR_AI_ALLOW_CUSTOM_ENDPOINTS", "1")
    monkeypatch.delenv("CIR_AI_ALLOW_PRIVATE_ENDPOINTS", raising=False)
    with pytest.raises(ValueError):
        validate_ai_endpoint("http://127.0.0.1:8080/api", "chatgpt")

    monkeypatch.setattr(
        "app.plugins.ai_chatbot.security.socket.getaddrinfo",
        lambda hostname, port: [(None, None, None, None, ("104.18.33.45", 0))],
    )
    assert validate_ai_endpoint("https://api.openai.com/v1/chat/completions", "chatgpt")
