import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.models import AuthSession, LoginAttempt, User
from app.schemas import Login
from app.security import COOKIE, SESSION_SECONDS, current_user, db_session, token_hash, user_data, verify_password

router = APIRouter(prefix='/auth', tags=['认证'])


@router.post('/login')
def login(payload: Login, request: Request, response: Response, db: Session = Depends(db_session)):
    now = int(time.time())
    key = token_hash(payload.username.lower())
    attempt = db.get(LoginAttempt, key)
    if attempt and attempt.until_at > now and attempt.count >= 10:
        raise HTTPException(429, '登录尝试过多，请在 5 分钟后重试')
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    valid = verify_password(payload.password, user.password_hash if user else request.app.state.dummy_hash)
    if not valid or not user or not user.active:
        if not attempt:
            attempt = LoginAttempt(key=key, count=0, until_at=now + 300)
            db.add(attempt)
        if attempt.until_at <= now:
            attempt.count, attempt.until_at = 0, now + 300
        attempt.count += 1
        db.commit()
        raise HTTPException(401, '账号或密码不正确，或账号已停用')
    if payload.portal == 'shop' and user.role != 'user':
        raise HTTPException(403, '这是顾客入口。客服或管理员请使用员工入口登录。')
    if payload.portal == 'staff' and user.role not in ('agent', 'admin'):
        raise HTTPException(403, '这是员工入口。顾客请使用顾客入口登录。')
    if attempt:
        db.delete(attempt)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    previous = request.cookies.get(COOKIE)
    if previous:
        db.execute(delete(AuthSession).where(AuthSession.id == token_hash(previous)))
    token = secrets.token_urlsafe(32)
    session = AuthSession(id=token_hash(token), user_id=user.id, csrf_token=secrets.token_urlsafe(32), expires_at=now + SESSION_SECONDS)
    db.add(session)
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', secure=False, max_age=SESSION_SECONDS, path='/api')
    return {'user': user_data(user), 'csrf_token': session.csrf_token}


@router.get('/me')
def me(request: Request, user: User = Depends(current_user)):
    return {'user': user_data(user), 'csrf_token': request.state.auth_session.csrf_token}


@router.post('/logout')
def logout(request: Request, response: Response, _user: User = Depends(current_user), db: Session = Depends(db_session)):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie(COOKIE, path='/api', httponly=True, samesite='strict')
    return {'ok': True}
