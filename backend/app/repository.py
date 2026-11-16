"""Shared read scopes. Apply before lookup, count, search and pagination."""
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from app.models import Category, Conversation, ConversationMessage, FAQ, Message, Order, Ticket, TicketEvent, User
from app.services.orders import order_data


def visible_tickets(user: User):
    if user.role == 'admin':
        return select(Ticket)
    if user.role == 'user':
        return select(Ticket).where(Ticket.owner_id == user.id)
    queue = and_(Ticket.status == 'pending', Ticket.assignee_id.is_(None), or_(Ticket.group_id.is_(None), Ticket.group_id == user.group_id) if user.group_id else Ticket.group_id.is_(None))
    group_assigned = and_(Ticket.status == 'assigned', Ticket.group_id == user.group_id) if user.group_id else False
    return select(Ticket).where(or_(Ticket.assignee_id == user.id, queue, group_assigned))


def ticket_data(db: Session, ticket: Ticket, user: User, detail: bool = False) -> dict:
    result = {key: getattr(ticket, key) for key in ('id','title','description','status','owner_id','assignee_id','category_id','group_id','order_id','refund_stage','version','created_at','updated_at','prediction_source','prediction_model_version','prediction_label','prediction_mapping_version','prediction_integrity','prediction_score','needs_manual')}
    owner = db.get(User, ticket.owner_id)
    agent = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    category = db.get(Category, ticket.category_id) if ticket.category_id else None
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    result.update(
        owner_name=owner.display_name,
        assignee_name=agent.display_name if agent else None,
        category_name=category.name if category else None,
        order_no=order.order_no if order else None,
        product_name=order.product_name if order else None,
    )
    latest = db.scalar(select(Message).where(Message.ticket_id == ticket.id, Message.internal.is_(False))
                       .order_by(Message.id.desc()).limit(1))
    result['needs_staff_reply'] = bool(latest and latest.author_id == ticket.owner_id
                                      and ticket.status not in ('resolved', 'closed'))
    result['latest_public_reply'] = ({'body': latest.body, 'created_at': latest.created_at,
                                     'from_customer': latest.author_id == ticket.owner_id} if latest else None)
    if detail:
        result['order'] = order_data(order) if order else None
        if user.role in ('agent', 'admin'):
            result['customer_statements'] = list(db.scalars(
                select(ConversationMessage.body).join(Conversation).where(
                    Conversation.ticket_id == ticket.id, Conversation.user_id == ticket.owner_id,
                    ConversationMessage.role == 'user',
                ).order_by(ConversationMessage.id)
            ))
        messages = select(Message).where(Message.ticket_id == ticket.id).order_by(Message.id)
        if user.role == 'user':
            messages = messages.where(Message.internal.is_(False))
        result['messages'] = [{'id': m.id, 'author_id': m.author_id, 'author_name': db.get(User, m.author_id).display_name, 'body': m.body, 'internal': m.internal, 'created_at': m.created_at} for m in db.scalars(messages)]
        events = select(TicketEvent).where(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id)
        # Internal notes and staff reasoning do not leak through the audit trail either.
        if user.role == 'user':
            events = events.where(TicketEvent.kind.not_in(('internal_note', 'classification')))
        result['events'] = [{'id': e.id, 'actor_name': db.get(User, e.actor_id).display_name, 'kind': e.kind, 'detail': e.detail, 'created_at': e.created_at} for e in db.scalars(events)]
    return result


def faq_data(item: FAQ) -> dict:
    return {k: getattr(item, k) for k in ('id', 'question', 'answer', 'keywords', 'category_id', 'active')}
