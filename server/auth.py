import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException, Request
from .database import connect


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'{salt}${digest}'


def verify(password, encoded):
    salt, digest = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return hmac.compare_digest(actual, digest)


def current_user(request: Request):
    token = request.cookies.get('knowpage_session', '')
    with connect() as db:
        row = db.execute('SELECT u.id,u.name,u.role FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?', (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(401, '请先登录')
    return dict(row)


def admin(user):
    if user['role'] != 'admin':
        raise HTTPException(403, '此操作需要管理员权限')
