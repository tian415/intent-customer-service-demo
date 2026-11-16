from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.models import Message, Ticket, User
from app.repository import ticket_data, visible_tickets
from app.schemas import Action, MessageInput, TicketCreate
from app.security import current_user, db_session
from app.services.tickets import add_message, apply_action, create_ticket, load_ticket

router = APIRouter(prefix='/tickets', tags=['工单'])


@router.get('')
def list_tickets(q: str = Query(default='', max_length=120), status: str = Query(default='', pattern=r'^(|pending|assigned|processing|resolved|closed)$'), scope: str = Query(default='all', pattern=r'^(all|mine|queue|todo|waiting|done)$'), page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(db_session)):
    statement = visible_tickets(user)
    if q.strip():
        statement = statement.where(or_(Ticket.title.contains(q.strip(), autoescape=True), Ticket.description.contains(q.strip(), autoescape=True)))
    if status:
        statement = statement.where(Ticket.status == status)
    if scope == 'mine' and user.role != 'user':
        statement = statement.where(Ticket.assignee_id == user.id)
    elif scope == 'queue':
        statement = statement.where(Ticket.status.in_(('pending', 'assigned')))
        if user.role == 'agent':
            statement = statement.where(or_(Ticket.assignee_id.is_(None), Ticket.assignee_id == user.id))
    elif scope in ('todo', 'waiting', 'done'):
        if user.role == 'agent':
            statement = statement.where(Ticket.assignee_id == user.id)
        statuses = {'todo': ('assigned', 'processing'), 'waiting': ('resolved',), 'done': ('closed',)}
        statement = statement.where(Ticket.status.in_(statuses[scope]))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    if scope == 'todo':
        last_author = select(Message.author_id).where(Message.ticket_id == Ticket.id, Message.internal.is_(False)).order_by(Message.id.desc()).limit(1).scalar_subquery()
        statement = statement.order_by((last_author == Ticket.owner_id).desc(), Ticket.updated_at.asc(), Ticket.id.asc())
    else:
        statement = statement.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size))
    return {'items': [ticket_data(db, t, user) for t in rows], 'total': total, 'page': page, 'page_size': page_size}


@router.post('', status_code=201)
def new_ticket(payload: TicketCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    ticket = create_ticket(db, user, payload, request.app.state.model_path, expected_sha256=request.app.state.expected_model_sha256, mapping_path=request.app.state.label_map_path)
    db.commit()
    return ticket_data(db, ticket, user, True)


@router.get('/{identity}')
def detail(identity: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return ticket_data(db, load_ticket(db, user, identity), user, True)


@router.post('/{identity}/actions')
def action(identity: int, payload: Action, user: User = Depends(current_user), db: Session = Depends(db_session)):
    ticket = load_ticket(db, user, identity, payload.version)
    apply_action(db, ticket, user, payload)
    db.commit()
    return ticket_data(db, ticket, user, True)


@router.post('/{identity}/messages')
def message(identity: int, payload: MessageInput, user: User = Depends(current_user), db: Session = Depends(db_session)):
    ticket = load_ticket(db, user, identity, payload.version)
    add_message(db, ticket, user, payload)
    db.commit()
    return ticket_data(db, ticket, user, True)
