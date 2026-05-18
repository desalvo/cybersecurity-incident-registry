"""Security helpers for production deployments.

The module is intentionally dependency-free so the application can enforce a
minimum security baseline without adding a heavy form framework.  It provides:

* strict checks for production secrets;
* per-session CSRF tokens for unsafe HTTP methods;
* automatic CSRF field injection in rendered HTML forms;
* common browser security headers.
"""
import os
import re
import secrets
from flask import abort, current_app, request, session

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WEAK_SECRET_VALUES = {"", "dev-change-me", "change-me", "changeme", "secret", "admin", "password"}
WEAK_ADMIN_PASSWORDS = {"", "admin", "adminpass", "password", "changeme", "change-me"}

_POST_FORM_RE = re.compile(r"(<form\b(?=[^>]*\bmethod\s*=\s*['\"]?post['\"]?)[^>]*>)", re.IGNORECASE)


def truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sì"}


def production_mode():
    return truthy(os.getenv("CIR_PRODUCTION", "0")) or os.getenv("FLASK_ENV", "").lower() == "production"


def validate_production_configuration(app):
    """Fail fast when a production deployment uses unsafe defaults."""
    if not production_mode():
        return
    secret = (app.config.get("SECRET_KEY") or "").strip()
    admin_password = (os.getenv("ADMIN_INITIAL_PASSWORD") or "").strip()
    database_url = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    errors = []
    if secret.lower() in WEAK_SECRET_VALUES or len(secret) < 32:
        errors.append("SECRET_KEY must be a random value of at least 32 characters")
    if admin_password.lower() in WEAK_ADMIN_PASSWORDS or len(admin_password) < 12:
        errors.append("ADMIN_INITIAL_PASSWORD must be changed and be at least 12 characters")
    if "sqlite" in database_url.lower():
        errors.append("DATABASE_URL must point to PostgreSQL in production")
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


def current_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_field():
    return f'<input type="hidden" name="_csrf_token" value="{current_csrf_token()}">'


def validate_csrf():
    if request.method not in UNSAFE_METHODS:
        return None
    if request.endpoint and (request.endpoint.startswith("static") or request.endpoint == "main.healthz"):
        return None
    expected = session.get("_csrf_token")
    supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not secrets.compare_digest(str(expected), str(supplied)):
        current_app.logger.warning("CSRF validation failed for %s %s", request.method, request.path)
        abort(400, description="Richiesta non valida o scaduta: token CSRF assente o non corretto.")
    return None


def inject_csrf_fields(response):
    if response.status_code != 200:
        return response
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return response
    try:
        body = response.get_data(as_text=True)
    except Exception:
        return response
    if "<form" not in body.lower():
        return response
    field = csrf_field()
    body = _POST_FORM_RE.sub(lambda match: match.group(1) + field, body)
    response.set_data(body)
    response.calculate_content_length()
    return response


def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if request.is_secure or truthy(os.getenv("CIR_FORCE_HSTS", "0")):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def init_security(app):
    app.config.setdefault("MAX_CONTENT_LENGTH", int(os.getenv("MAX_CONTENT_LENGTH", str(25 * 1024 * 1024))))
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", os.getenv("SESSION_COOKIE_SAMESITE", "Lax"))
    app.config.setdefault("REMEMBER_COOKIE_HTTPONLY", True)
    app.config.setdefault("REMEMBER_COOKIE_SAMESITE", os.getenv("REMEMBER_COOKIE_SAMESITE", "Lax"))
    if truthy(os.getenv("SESSION_COOKIE_SECURE", "0")) or production_mode():
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["REMEMBER_COOKIE_SECURE"] = True
    validate_production_configuration(app)
    app.jinja_env.globals["csrf_token"] = current_csrf_token
    app.jinja_env.globals["csrf_field"] = csrf_field
    app.before_request(validate_csrf)
    app.after_request(inject_csrf_fields)
    app.after_request(add_security_headers)
