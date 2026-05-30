import hashlib
import os
from flask_login import LoginManager
from .models import db
from werkzeug.security import generate_password_hash, check_password_hash
login_manager=LoginManager()
def norm(p):
    if p is None: p=''
    return hashlib.sha256(p.encode('utf-8')).hexdigest()
def _password_hash_method():
    # Keep the production default strong, but allow the test suite to use a
    # lower-cost PBKDF2 setting. The override is intentionally limited to
    # pytest/runtime explicit configuration and is never enabled by default in
    # normal deployments.
    configured = os.getenv('CIR_PASSWORD_HASH_METHOD')
    if configured:
        return configured
    if os.getenv('PYTEST_CURRENT_TEST') or os.getenv('PYTEST_VERSION'):
        return 'pbkdf2:sha256:1000'
    return 'pbkdf2:sha256:600000'

def hash_password(p): return generate_password_hash(norm(p), method=_password_hash_method())
def verify_password(h,p):
    if not h: return False
    try: return check_password_hash(h, norm(p))
    except ValueError: return False
@login_manager.user_loader
def load_user(uid):
    from .models import User
    return db.session.get(User, int(uid))
