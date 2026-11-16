from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models import User
from app.security import current_user, db_session
from app.services.orders import get_order_payload, list_orders

router = APIRouter(prefix='/orders', tags=['订单'])


@router.get('')
def orders(user: User = Depends(current_user), db: Session = Depends(db_session)):
    return list_orders(db, user)


@router.get('/{identity}')
def order_detail(identity: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return get_order_payload(db, user, identity)
