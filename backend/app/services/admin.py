from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Category, Group, Ticket, User
from app.schemas import UserCreate, UserUpdate
from app.security import hash_password, invalidate_sessions


def require_reference(db: Session, model, identity: int | None, active: bool = False):
    if identity is None:
        return None
    item = db.get(model, identity)
    if item is None or (active and not item.active):
        raise HTTPException(422, '选择的记录不存在或已停用')
    return item


def save_user(db: Session, payload: UserCreate | UserUpdate, existing: User | None = None) -> User:
    require_reference(db, Group, payload.group_id)
    if payload.role != 'agent' and payload.group_id is not None:
        raise HTTPException(422, '只有客服账号可以加入客服组')
    if existing:
        if existing.role == 'user' and payload.role != 'user':
            count = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.owner_id == existing.id, Ticket.status != 'closed'))
            if count:
                raise HTTPException(409, '该用户仍有未关闭工单，请先完成工单再更改角色')
        if existing.role == 'admin' and existing.active and (payload.role != 'admin' or not payload.active):
            count = db.scalar(select(func.count()).select_from(User).where(User.role == 'admin', User.active.is_(True)))
            if count <= 1:
                raise HTTPException(409, '必须保留至少一个有效管理员')
        if existing.role == 'agent' and (payload.role != 'agent' or not payload.active or payload.group_id != existing.group_id):
            count = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.assignee_id == existing.id, Ticket.status != 'closed'))
            if count:
                raise HTTPException(409, '该客服仍有未关闭工单，请先转派后再变更账号或分组')
        if payload.role != existing.role or payload.active != existing.active or payload.password or payload.group_id != existing.group_id:
            invalidate_sessions(db, existing.id)
        user = existing
    else:
        user = User(username=payload.username.lower(), password_hash='')
        db.add(user)
    for key in ('display_name', 'role', 'active', 'group_id'):
        setattr(user, key, getattr(payload, key))
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.flush()
    return user


def category_data(category: Category) -> dict:
    return {k: getattr(category, k) for k in ('id', 'name', 'keywords', 'active', 'group_id')}
