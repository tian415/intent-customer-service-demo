from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Category, Group, User
from app.schemas import PredictionInput
from app.security import current_user, db_session, user_data
from app.services.admin import category_data
from app.services.faq import search_faq
from app.services.tickets import predict_intent

router = APIRouter(tags=['分类与知识'])


@router.get('/catalog')
def catalog(user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {
        'categories': [category_data(c) for c in db.scalars(select(Category).where(Category.active.is_(True)).order_by(Category.id))],
        'groups': [{'id': g.id, 'name': g.name} for g in db.scalars(select(Group).order_by(Group.id))] if user.role != 'user' else [],
        'agents': [user_data(u) for u in db.scalars(select(User).where(User.role == 'agent', User.active.is_(True)).order_by(User.id))] if user.role != 'user' else [],
    }


@router.get('/faq/search')
def faq(q: str = Query(min_length=1, max_length=1000), _user: User = Depends(current_user), db: Session = Depends(db_session)):
    return search_faq(db, q)


@router.post('/intent/predict')
def prediction(payload: PredictionInput, request: Request, _user: User = Depends(current_user), db: Session = Depends(db_session)):
    return predict_intent(db, payload.text, request.app.state.model_path, expected_sha256=request.app.state.expected_model_sha256, mapping_path=request.app.state.label_map_path)
