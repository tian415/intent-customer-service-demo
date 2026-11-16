"""Ticket invariants, classification and explainable least-open-load routing."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models import Category, Message, Ticket, TicketEvent, User, now
from app.repository import visible_tickets
from app.schemas import Action, MessageInput, TicketCreate
from app.services.admin import category_data
from app.services.refunds import REFUND_STAGES, refund_for_order


def predict_intent(db: Session, text: str, model_path=None, *, expected_sha256=None, mapping_path=None) -> dict:
    from ml.intent import predict
    categories = [category_data(c) for c in db.scalars(select(Category).where(Category.active.is_(True)).order_by(Category.id))]
    return predict(text, categories, model_path=model_path, expected_sha256=expected_sha256, mapping_path=mapping_path)


def audit(db: Session, ticket: Ticket, actor: User, kind: str, detail: str) -> None:
    db.add(TicketEvent(ticket_id=ticket.id, actor_id=actor.id, kind=kind, detail=detail))


def load_ticket(db: Session, user: User, identity: int, version: int | None = None) -> Ticket:
    ticket = db.scalar(visible_tickets(user).where(Ticket.id == identity))
    if not ticket:
        raise HTTPException(404, '工单不存在或无访问权限')
    if version is not None and ticket.version != version:
        raise HTTPException(409, '工单已被更新，请刷新详情后重试')
    return ticket


def eligible_agent(db: Session, ticket: Ticket, identity: int) -> User:
    agent = db.get(User, identity)
    if not agent or not agent.active or agent.role != 'agent':
        raise HTTPException(422, '请选择有效客服账号')
    if ticket.group_id is not None and agent.group_id != ticket.group_id:
        raise HTTPException(422, '客服不属于该工单的客服组')
    return agent


def route(db: Session, ticket: Ticket, actor: User) -> None:
    ticket.assignee_id = None
    ticket.status = 'pending'
    if ticket.category_id is None or ticket.group_id is None:
        audit(db, ticket, actor, 'assignment', '无有效类别分组，进入待分配队列')
        return
    agents = list(db.scalars(select(User).where(User.role == 'agent', User.active.is_(True), User.group_id == ticket.group_id).order_by(User.id)))
    if not agents:
        audit(db, ticket, actor, 'assignment', '客服组无可用客服，进入待分配队列')
        return
    loads = dict(db.execute(select(Ticket.assignee_id, func.count()).where(Ticket.status.in_(('assigned','processing','resolved'))).group_by(Ticket.assignee_id)).all())
    agent = min(agents, key=lambda u: (loads.get(u.id, 0), u.id))
    ticket.assignee_id, ticket.status = agent.id, 'assigned'
    audit(db, ticket, actor, 'assignment', f'按客服组与未关闭工单数分配给 {agent.display_name}（同负载按账号编号）')


def create_ticket(
    db: Session,
    user: User,
    payload: TicketCreate,
    model_path=None,
    *,
    expected_sha256=None,
    mapping_path=None,
    order_id: int | None = None,
    conversation_prediction: dict | None = None,
    refund_request: bool = False,
) -> Ticket:
    if user.role != 'user':
        raise HTTPException(403, '请使用普通用户账号提交工单')
    prediction = conversation_prediction if conversation_prediction is not None else predict_intent(db, payload.title + '\n' + payload.description, model_path, expected_sha256=expected_sha256, mapping_path=mapping_path)
    category = db.get(Category, prediction['category_id']) if prediction['category_id'] and not prediction['needs_manual'] else None
    if category and not category.active:
        category = None
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        owner_id=user.id,
        category_id=category.id if category else None,
        group_id=category.group_id if category else None,
        order_id=order_id,
        refund_stage='requested' if refund_request else None,
        status='pending',
        prediction_source=prediction['source'],
        prediction_model_version=prediction['model_version'],
        prediction_label=prediction['predicted_label'],
        prediction_mapping_version=prediction['mapping_version'],
        prediction_integrity=prediction['integrity'],
        prediction_score=prediction['score'],
        needs_manual=category is None,
    )
    db.add(ticket)
    db.flush()
    audit(db, ticket, user, 'created', '用户提交工单')
    if prediction['predicted_label']:
        audit(db, ticket, user, 'prediction', f"原模型标签：{prediction['predicted_label']}；映射版本：{prediction['mapping_version'] or '同名直接对应'}；完整性：{prediction['integrity']}")
    version_note = f"；模型 SHA-256：{prediction['model_version']}" if prediction['model_version'] else ''
    audit(db, ticket, user, 'prediction', f"分类来源：{prediction['source']}；{prediction['reason']}{version_note}")
    route(db, ticket, user)
    db.flush()
    return ticket


def require_handler(ticket: Ticket, user: User) -> None:
    if user.role != 'admin' and (user.role != 'agent' or ticket.assignee_id != user.id):
        raise HTTPException(403, '只有承办客服或管理员可执行此操作')


def apply_action(db: Session, ticket: Ticket, user: User, payload: Action) -> Ticket:
    action, old_status = payload.action, ticket.status
    if action == 'accept':
        if user.role != 'agent':
            raise HTTPException(403, '只有客服可以接单')
        if ticket.status not in ('pending', 'assigned') or ticket.assignee_id not in (None, user.id):
            raise HTTPException(409, '工单已被接单或不在可接单状态')
        eligible_agent(db, ticket, user.id)
        ticket.assignee_id, ticket.status = user.id, 'processing'
    elif action == 'resolve':
        require_handler(ticket, user)
        if ticket.status != 'processing':
            raise HTTPException(409, '只能解决处理中的工单')
        if ticket.refund_stage is not None:
            if not payload.refund_decision or not payload.reason.strip():
                raise HTTPException(422, '请先填写退款审核结论和给顾客的说明')
            ticket.refund_stage = payload.refund_decision
            result = f'{REFUND_STAGES[ticket.refund_stage]}：{payload.reason.strip()}'
            audit(db, ticket, user, 'refund_review', REFUND_STAGES[ticket.refund_stage])
        else:
            if not payload.reason.strip():
                raise HTTPException(422, '请填写向顾客公开的处理结果')
            result = f'处理结果：{payload.reason.strip()}'
        db.add(Message(ticket_id=ticket.id, author_id=user.id, body=result, internal=False))
        ticket.status = 'resolved'
    elif action in ('close', 'reopen', 'follow_up'):
        if user.role != 'user' or ticket.owner_id != user.id:
            raise HTTPException(403, '只有工单提交者可以确认或重新打开')
        allowed = ('resolved',) if action == 'close' else ('resolved', 'closed')
        if ticket.status not in allowed:
            raise HTTPException(409, '当前状态不允许此操作')
        if action == 'follow_up' and not payload.reason.strip():
            raise HTTPException(422, '请说明仍需帮助的问题')
        if action == 'close':
            ticket.status = 'closed'
        else:
            if ticket.refund_stage is not None:
                current = refund_for_order(db, ticket.owner_id, ticket.order_id, open_only=True)
                if current and current.id != ticket.id:
                    raise HTTPException(409, f'此订单已有进行中的退款申请 #{current.id}')
                ticket.refund_stage = 'requested'
            assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
            if assignee and assignee.active and assignee.role == 'agent' and (ticket.group_id is None or assignee.group_id == ticket.group_id):
                ticket.status = 'assigned'
            else:
                ticket.assignee_id, ticket.status = None, 'pending'
                audit(db, ticket, user, 'assignment', '原客服不可用，重开后进入待分配队列')
            if action == 'follow_up':
                db.add(Message(ticket_id=ticket.id, author_id=user.id,
                               body=payload.reason.strip(), internal=False))
                audit(db, ticket, user, 'reply', '顾客补充问题，继续处理')
    elif action == 'transfer':
        require_handler(ticket, user)
        if ticket.status in ('resolved', 'closed'):
            raise HTTPException(409, '请先由用户重开后再转派')
        if not payload.assignee_id or not payload.reason:
            raise HTTPException(422, '转派需选择客服并填写原因')
        agent = eligible_agent(db, ticket, payload.assignee_id)
        if ticket.assignee_id == agent.id:
            raise HTTPException(409, '该客服已是当前承办人')
        ticket.assignee_id, ticket.status = agent.id, 'assigned'
        audit(db, ticket, user, 'assignment', f'人工转派给 {agent.display_name}：{payload.reason}')
    elif action == 'classify':
        if user.role not in ('agent', 'admin'):
            raise HTTPException(403, '需要工作人员权限')
        if ticket.assignee_id is not None:
            require_handler(ticket, user)
        if ticket.status in ('resolved', 'closed'):
            raise HTTPException(409, '请先由用户重开后再修改分类')
        category = db.get(Category, payload.category_id) if payload.category_id else None
        if not category or not category.active or not payload.reason:
            raise HTTPException(422, '请选择有效类别并填写纠错原因')
        previous = ticket.category_id
        ticket.category_id, ticket.group_id, ticket.needs_manual = category.id, category.group_id, False
        audit(db, ticket, user, 'classification', f'类别 {previous or "未分类"} → {category.id}（{category.name}）；原因：{payload.reason}')
        if ticket.status in ('pending', 'assigned'):
            route(db, ticket, user)
    ticket.updated_at = now()
    audit(db, ticket, user, 'status', f'{action}: {old_status} → {ticket.status}')
    db.flush()
    return ticket


def add_message(db: Session, ticket: Ticket, user: User, payload: MessageInput) -> Ticket:
    if ticket.status in ('resolved', 'closed'):
        raise HTTPException(409, '工单已解决或关闭，请先重开再回复')
    if user.role == 'user':
        if payload.internal:
            raise HTTPException(403, '普通用户不能添加内部备注')
    else:
        require_handler(ticket, user)
    db.add(Message(ticket_id=ticket.id, author_id=user.id, body=payload.body, internal=payload.internal))
    ticket.updated_at = now()
    audit(db, ticket, user, 'internal_note' if payload.internal else 'reply', '添加内部备注' if payload.internal else '添加公开回复')
    db.flush()
    return ticket
