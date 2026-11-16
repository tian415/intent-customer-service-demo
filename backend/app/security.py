"""Local session authentication. Passwords and cookie tokens are never stored raw."""
import hashlib
import hmac
import secrets
import time
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.models import AuthSession, User

COOKIE = 'ticket_session'
SESSION_SECONDS = 8 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return f'scrypt$32768$8$3${salt}${key.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, n, r, p, salt, expected = encoded.split('$')
        if name != 'scrypt' or (n, r, p) != ('32768', '8', '3'):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def db_session(request: Request):
    with Session(request.app.state.engine, expire_on_commit=False) as db:
        # Serialize SQLite writes before reading invariants such as last admin or load.
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        yield db


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = request.cookies.get(COOKIE, '')
    session = db.get(AuthSession, token_hash(token)) if token else None
    user = db.get(User, session.user_id) if session else None
    if not session or session.expires_at <= int(time.time()) or not user or not user.active:
        raise HTTPException(401, '登录已失效，请重新登录')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf_token):
            raise HTTPException(403, '请求校验失败，请刷新后重试')
    request.state.auth_session = session
    return user


def administrator(user: User = Depends(current_user)) -> User:
    if user.role != 'admin':
        raise HTTPException(403, '需要管理员权限')
    return user


def invalidate_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def user_data(user: User) -> dict:
    return {key: getattr(user, key) for key in ('id', 'username', 'display_name', 'role', 'active', 'group_id')}
