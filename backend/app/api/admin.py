from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Category, FAQ, Group, Ticket, TicketEvent, User
from app.schemas import CategoryInput, FAQInput, GroupInput, UserCreate, UserUpdate
from app.security import administrator, db_session, user_data
from app.repository import faq_data
from app.services.admin import category_data, require_reference, save_user

router = APIRouter(prefix='/admin', tags=['管理'], dependencies=[Depends(administrator)])


@router.get('/users')
def users(db: Session = Depends(db_session)):
    return [user_data(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post('/users', status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(db_session)):
    user = save_user(db, payload)
    db.commit()
    return user_data(user)


@router.put('/users/{identity}')
def update_user(identity: int, payload: UserUpdate, db: Session = Depends(db_session)):
    user = require_reference(db, User, identity)
    save_user(db, payload, user)
    db.commit()
    return user_data(user)


@router.get('/groups')
def groups(db: Session = Depends(db_session)):
    return [{'id': g.id, 'name': g.name} for g in db.scalars(select(Group).order_by(Group.id))]


@router.post('/groups', status_code=201)
def create_group(payload: GroupInput, db: Session = Depends(db_session)):
    item = Group(**payload.model_dump())
    db.add(item)
    db.commit()
    return {'id': item.id, 'name': item.name}


@router.put('/groups/{identity}')
def update_group(identity: int, payload: GroupInput, db: Session = Depends(db_session)):
    item = require_reference(db, Group, identity)
    item.name = payload.name
    db.commit()
    return {'id': item.id, 'name': item.name}


@router.get('/categories')
def categories(db: Session = Depends(db_session)):
    return [category_data(c) for c in db.scalars(select(Category).order_by(Category.id))]


@router.post('/categories', status_code=201)
def create_category(payload: CategoryInput, db: Session = Depends(db_session)):
    require_reference(db, Group, payload.group_id)
    item = Category(**payload.model_dump())
    db.add(item)
    db.commit()
    return category_data(item)


@router.put('/categories/{identity}')
def update_category(identity: int, payload: CategoryInput, db: Session = Depends(db_session)):
    require_reference(db, Group, payload.group_id)
    item = require_reference(db, Category, identity)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return category_data(item)


@router.get('/faqs')
def faqs(db: Session = Depends(db_session)):
    return [faq_data(f) for f in db.scalars(select(FAQ).order_by(FAQ.id))]


def save_faq(db: Session, payload: FAQInput, item: FAQ | None = None):
    require_reference(db, Category, payload.category_id)
    if item is None:
        item = FAQ()
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    return faq_data(item)


@router.post('/faqs', status_code=201)
def create_faq(payload: FAQInput, db: Session = Depends(db_session)):
    return save_faq(db, payload)


@router.put('/faqs/{identity}')
def update_faq(identity: int, payload: FAQInput, db: Session = Depends(db_session)):
    return save_faq(db, payload, require_reference(db, FAQ, identity))


@router.delete('/faqs/{identity}')
def delete_faq(identity: int, db: Session = Depends(db_session)):
    db.delete(require_reference(db, FAQ, identity))
    db.commit()
    return {'ok': True}


@router.get('/stats')
def statistics(db: Session = Depends(db_session)):
    def counts(column):
        return [{'name': name, 'count': count} for name, count in db.execute(select(column, func.count()).select_from(Ticket).group_by(column))]
    categories = db.execute(select(Category.name, func.count(Ticket.id)).select_from(Ticket).outerjoin(Category, Ticket.category_id == Category.id).group_by(Category.name))
    return {
        'total': db.scalar(select(func.count()).select_from(Ticket)),
        'by_status': counts(Ticket.status),
        'by_source': counts(Ticket.prediction_source),
        'by_category': [{'name': name or '待分类', 'count': count} for name, count in categories],
        'corrections': db.scalar(select(func.count()).select_from(TicketEvent).where(TicketEvent.kind == 'classification')),
        'unassigned': db.scalar(select(func.count()).select_from(Ticket).where(Ticket.assignee_id.is_(None), Ticket.status == 'pending')),
    }
