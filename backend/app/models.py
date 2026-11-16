"""Persistence models. Schema changes live in numbered SQL migrations."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = 'groups'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'))
    created_at: Mapped[str] = mapped_column(default=now)


class AuthSession(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    csrf_token: Mapped[str]
    expires_at: Mapped[int]


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int]
    until_at: Mapped[int]


class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    keywords: Mapped[str] = mapped_column(default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'))


class FAQ(Base):
    __tablename__ = 'faqs'
    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str]
    answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(default='')
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id'))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id'))
    group_id: Mapped[int | None] = mapped_column(ForeignKey('groups.id'))
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'))
    status: Mapped[str]
    refund_stage: Mapped[str | None]
    version: Mapped[int] = mapped_column(Integer, default=1)
    prediction_source: Mapped[str]
    prediction_model_version: Mapped[str | None]
    prediction_label: Mapped[str | None]
    prediction_mapping_version: Mapped[str | None]
    prediction_integrity: Mapped[str | None]
    prediction_score: Mapped[float] = mapped_column(Float, default=0.0)
    needs_manual: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    __mapper_args__ = {'version_id_col': version}


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(default=now)


class TicketEvent(Base):
    __tablename__ = 'ticket_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str]
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=now)


class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    order_no: Mapped[str] = mapped_column(unique=True)
    product_name: Mapped[str]
    status: Mapped[str]
    amount_cents: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str]
    selected_order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey('tickets.id'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_request: Mapped[str | None] = mapped_column(Text)
    intent_category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id'))
    next_action: Mapped[str | None]
    prediction_source: Mapped[str | None]
    prediction_model_version: Mapped[str | None]
    prediction_label: Mapped[str | None]
    prediction_mapping_version: Mapped[str | None]
    prediction_integrity: Mapped[str | None]
    prediction_score: Mapped[float] = mapped_column(Float, default=0.0)
    needs_manual: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    __mapper_args__ = {'version_id_col': version}


class ConversationMessage(Base):
    __tablename__ = 'conversation_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversations.id'))
    role: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=now)
