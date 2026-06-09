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
from .env_utils import get_admin_initial_password
from flask import abort, current_app, request, session, g

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE_NAME = "cir_csrf_token"
WEAK_SECRET_VALUES = {"", "dev-change-me", "change-me", "changeme", "secret", "admin", "password"}
WEAK_ADMIN_PASSWORDS = {"", "admin", "adminpass", "password", "changeme", "change-me"}

_POST_FORM_RE = re.compile(r"(<form\b(?=[^>]*\bmethod\s*=\s*['\"]?post['\"]?)[^>]*>)", re.IGNORECASE)


def truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "si", "sì"}


def production_mode():
    return truthy(os.getenv("CIR_PRODUCTION", "0")) or os.getenv("FLASK_ENV", "").lower() == "production"


def csrf_disabled():
    """Return True when CSRF validation is explicitly disabled for local/test use.

    The bypass is intentionally ignored in production mode: production deployments
    must keep CSRF validation active even if the environment variable is set.
    """
    return truthy(os.getenv("CIR_DISABLE_CSRF", "0")) and not production_mode()


def validate_production_configuration(app):
    """Fail fast when a production deployment uses unsafe defaults."""
    if not production_mode():
        return
    secret = (app.config.get("SECRET_KEY") or "").strip()
    admin_password = (get_admin_initial_password() or "").strip()
    database_url = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    errors = []
    if secret.lower() in WEAK_SECRET_VALUES or len(secret) < 32:
        errors.append("SECRET_KEY must be a random value of at least 32 characters")
    if admin_password.lower() in WEAK_ADMIN_PASSWORDS or len(admin_password) < 12:
        errors.append("ADMIN_INITIAL_PASSWORD must be changed and be at least 12 characters")
    if "sqlite" in database_url.lower():
        errors.append("DATABASE_URL must point to PostgreSQL in production")
    if truthy(os.getenv("CIR_DISABLE_CSRF", "0")):
        errors.append("CIR_DISABLE_CSRF cannot be enabled in production")
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


def current_csrf_token():
    if csrf_disabled():
        return ""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    # Keep the value available for after_request even on pages, such as login,
    # that do not extend the base template.  A dedicated CSRF cookie provides a
    # double-submit fallback for plain-HTTP Docker Compose deployments where the
    # session cookie can be lost because of an accidental Secure-cookie setting
    # or a browser/proxy mismatch.  The form token still has to match a value
    # issued by this application.
    g.csrf_token_value = token
    return token


def csrf_field():
    token = current_csrf_token()
    if not token:
        return ""
    return f'<input type="hidden" name="_csrf_token" value="{token}">'


def ensure_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


def block_disallowed_http_methods():
    """Reject HTTP methods that must be disabled for web security compliance."""
    if request.method in {"TRACE", "TRACK"}:
        current_app.logger.warning("Blocked disallowed HTTP method %s on %s", request.method, request.path)
        try:
            from .models import db, AuditLog
            db.session.add(AuditLog(operation_type="security:method_blocked", username="anonymous", actor_type="anonymous", details=f"{request.method} {request.path}"[:1000]))
            db.session.commit()
        except Exception:
            db.session.rollback()
        abort(405, description="Metodo HTTP non consentito.")
    return None


def validate_csrf():
    if csrf_disabled():
        return None
    if request.method not in UNSAFE_METHODS:
        return None
    if request.endpoint and (request.endpoint.startswith("static") or request.endpoint == "main.healthz"):
        return None
    expected = session.get("_csrf_token")
    cookie_expected = request.cookies.get(CSRF_COOKIE_NAME)
    supplied = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken") or request.headers.get("X-CSRF-Token")
    valid = False
    if supplied and expected and secrets.compare_digest(str(expected), str(supplied)):
        valid = True
    elif supplied and cookie_expected and secrets.compare_digest(str(cookie_expected), str(supplied)):
        valid = True
    if not valid:
        current_app.logger.warning("CSRF validation failed for %s %s", request.method, request.path)
        try:
            from .models import db, AuditLog
            db.session.add(AuditLog(operation_type="security:csrf_failure", username="anonymous", actor_type="anonymous", details=f"{request.method} {request.path}"[:1000]))
            db.session.commit()
        except Exception:
            db.session.rollback()
        abort(400, description="Richiesta non valida o scaduta: token CSRF assente o non corretto.")
    return None


def inject_csrf_fields(response):
    if csrf_disabled():
        return response
    if response.status_code != 200:
        return response
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return response
    try:
        body = response.get_data(as_text=True)
    except Exception:
        return response
    lower_body = body.lower()
    if "<form" in lower_body:
        field = csrf_field()
        body = _POST_FORM_RE.sub(lambda match: match.group(1) + field, body)
    nonce = getattr(g, "csp_nonce", "")
    if nonce:
        body = re.sub(r"<script(?![^>]*\bnonce=)", f"<script nonce=\"{nonce}\"", body, flags=re.IGNORECASE)
        body = re.sub(r"<style(?![^>]*\bnonce=)", f"<style nonce=\"{nonce}\"", body, flags=re.IGNORECASE)
    response.set_data(body)
    response.calculate_content_length()
    return response



def cookie_secure_enabled():
    """Return whether session/CSRF cookies must carry the Secure flag.

    The flag is controlled by ``SESSION_COOKIE_SECURE`` instead of being
    implied by ``CIR_PRODUCTION``.  This keeps CSRF usable on plain-HTTP
    Docker Compose deployments used on localhost or behind non-TLS test
    frontends: if cookies are marked Secure, browsers correctly refuse to
    send them over HTTP and the POST to /login loses the CSRF session.

    Production deployments served through HTTPS should explicitly set
    ``SESSION_COOKIE_SECURE=1``.
    """
    return truthy(os.getenv("SESSION_COOKIE_SECURE", "0"))


def _csrf_cookie_secure():
    return cookie_secure_enabled()


def add_csrf_cookie(response):
    if csrf_disabled():
        response.delete_cookie(CSRF_COOKIE_NAME, path="/")
        return response
    token = getattr(g, "csrf_token_value", None) or session.get("_csrf_token")
    if token:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            max_age=int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "1800")),
            secure=_csrf_cookie_secure(),
            httponly=True,
            samesite=os.getenv("SESSION_COOKIE_SAMESITE", "Lax") or "Lax",
            path="/",
        )
    return response

def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    nonce = getattr(g, "csp_nonce", "")
    default_csp = (
        f"default-src 'self'; img-src 'self' data:; style-src 'self' 'nonce-{nonce}'; "
        f"script-src 'self' 'nonce-{nonce}'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    )
    response.headers.setdefault("Content-Security-Policy", os.getenv("CONTENT_SECURITY_POLICY", default_csp))
    if request.is_secure or truthy(os.getenv("CIR_FORCE_HSTS", "0")):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def init_security(app):
    app.config.setdefault("MAX_CONTENT_LENGTH", int(os.getenv("MAX_CONTENT_LENGTH", str(25 * 1024 * 1024))))
    app.config["CIR_CSRF_DISABLED"] = csrf_disabled()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax") or "Lax"
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = os.getenv("REMEMBER_COOKIE_SAMESITE", "Lax") or "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "1800"))
    secure_cookies = cookie_secure_enabled()
    app.config["SESSION_COOKIE_SECURE"] = secure_cookies
    app.config["REMEMBER_COOKIE_SECURE"] = secure_cookies
    validate_production_configuration(app)
    app.jinja_env.globals["csrf_token"] = current_csrf_token
    app.jinja_env.globals["csrf_field"] = csrf_field
    app.before_request(ensure_csp_nonce)
    app.before_request(block_disallowed_http_methods)
    app.before_request(validate_csrf)
    # Flask runs after_request handlers in reverse registration order.
    # Register headers first and HTML/CSRF injection last so the response body is
    # finalized before the dedicated CSRF cookie is written.
    app.after_request(add_security_headers)
    app.after_request(add_csrf_cookie)
    app.after_request(inject_csrf_fields)
