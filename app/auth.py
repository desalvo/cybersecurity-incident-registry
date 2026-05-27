import hashlib
from flask_login import LoginManager
from .models import db
from werkzeug.security import generate_password_hash, check_password_hash
login_manager=LoginManager()
def norm(p):
    if p is None: p=''
    return hashlib.sha256(p.encode('utf-8')).hexdigest()
def hash_password(p): return generate_password_hash(norm(p), method='pbkdf2:sha256:600000')
def verify_password(h,p):
    if not h: return False
    try: return check_password_hash(h, norm(p))
    except ValueError: return False
@login_manager.user_loader
def load_user(uid):
    from .models import User
    return db.session.get(User, int(uid))
