"""Strict request boundaries; clients cannot assign protected ticket fields."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class Login(Input):
    portal: Literal['shop', 'staff'] | None = None
    username: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=1, max_length=128)
    model_config = ConfigDict(str_strip_whitespace=False, extra='forbid')


class UserUpdate(Input):
    model_config = ConfigDict(str_strip_whitespace=False, extra='forbid')

    @field_validator('display_name')
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('显示姓名不能为空')
        return value.strip()

    display_name: str = Field(min_length=1, max_length=80)
    role: Literal['user', 'agent', 'admin']
    active: bool = True
    group_id: int | None = Field(default=None, gt=0)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class UserCreate(UserUpdate):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=128)


class GroupInput(Input):
    name: str = Field(min_length=1, max_length=80)


class CategoryInput(GroupInput):
    keywords: str = Field(default='', max_length=1000)
    active: bool = True
    group_id: int | None = Field(default=None, gt=0)


class FAQInput(Input):
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=10000)
    keywords: str = Field(default='', max_length=1000)
    category_id: int | None = Field(default=None, gt=0)
    active: bool = True


class TicketCreate(Input):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=10000)


class Action(Input):
    version: int = Field(gt=0)
    action: Literal['accept', 'resolve', 'close', 'reopen', 'follow_up', 'transfer', 'classify']
    refund_decision: Literal['approved', 'declined'] | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    reason: str = Field(default='', max_length=1000)


class MessageInput(Input):
    version: int = Field(gt=0)
    body: str = Field(min_length=1, max_length=10000)
    internal: bool = False


class PredictionInput(Input):
    text: str = Field(min_length=1, max_length=10130)


class ConversationStart(Input):
    force_new: bool = False


class ConversationMessageInput(Input):
    version: int = Field(gt=0)
    body: str = Field(min_length=1, max_length=10000)


class ConversationAction(Input):
    version: int = Field(gt=0)
    action: Literal['select_order', 'handoff', 'close', 'submit_refund']
    reason: str = Field(default='', max_length=1000)
    order_id: int | None = Field(default=None, gt=0)
