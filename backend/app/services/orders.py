"""Local mock commerce orders; never crawl external shops."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Order, Ticket, User


ORDER_STATUS_LABELS = {
    'pending_payment': '待付款',
    'paid': '已付款',
    'shipped': '已发货',
    'delivered': '已签收',
    'refunding': '退款中',
    'refunded': '已退款',
    'cancelled': '已取消',
}

TICKET_STATUS_LABELS = {
    'pending': '待分配',
    'assigned': '已分配',
    'processing': '处理中',
    'resolved': '待确认',
    'closed': '已关闭',
}


def order_data(order: Order, *, aftersales: list[dict] | None = None) -> dict:
    payload = {
        'id': order.id,
        'order_no': order.order_no,
        'product_name': order.product_name,
        'status': order.status,
        'status_label': ORDER_STATUS_LABELS.get(order.status, order.status),
        'amount_cents': order.amount_cents,
        'amount_display': f'¥{order.amount_cents / 100:.2f}',
        'created_at': order.created_at,
        'updated_at': order.updated_at,
    }
    if aftersales is not None:
        payload['aftersales'] = aftersales
    return payload


def _aftersales_for_order(db: Session, user: User, order_id: int) -> list[dict]:
    rows = db.scalars(
        select(Ticket).where(Ticket.owner_id == user.id, Ticket.order_id == order_id).order_by(Ticket.id.desc())
    )
    return [
        {
            'id': ticket.id,
            'title': ticket.title,
            'refund_stage': ticket.refund_stage,
            'status': ticket.status,
            'status_label': TICKET_STATUS_LABELS.get(ticket.status, ticket.status),
            'updated_at': ticket.updated_at,
        }
        for ticket in rows
    ]


def recent_cases(db: Session, owner_id: int) -> list[dict]:
    rows = db.execute(select(Ticket, Order.product_name).outerjoin(Order, Ticket.order_id == Order.id)
                      .where(Ticket.owner_id == owner_id, Ticket.status != 'closed')
                      .order_by(Ticket.updated_at.desc(), Ticket.id.desc()).limit(3))
    return [{'id': t.id, 'product': product or t.title, 'refund_stage': t.refund_stage,
             'status_label': TICKET_STATUS_LABELS[t.status]} for t, product in rows]


def list_orders(db: Session, user: User) -> list[dict]:
    if user.role != 'user':
        raise HTTPException(403, '只有普通用户可以查看自己的消费订单')
    rows = list(db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())))
    return [order_data(item, aftersales=_aftersales_for_order(db, user, item.id)) for item in rows]


def get_order(db: Session, user: User, identity: int) -> Order:
    if user.role != 'user':
        raise HTTPException(403, '只有普通用户可以查看自己的消费订单')
    order = db.scalar(select(Order).where(Order.id == identity, Order.user_id == user.id))
    if not order:
        raise HTTPException(404, '订单不存在或无访问权限')
    return order


def get_order_payload(db: Session, user: User, identity: int) -> dict:
    order = get_order(db, user, identity)
    return order_data(order, aftersales=_aftersales_for_order(db, user, order.id))
