from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.models import User
from app.schemas import ConversationAction, ConversationMessageInput, ConversationStart
from app.security import current_user, db_session
from app.services.conversations import (
    add_user_message,
    apply_conversation_action,
    conversation_data,
    load_conversation,
    start_conversation,
)

router = APIRouter(prefix='/conversations', tags=['智能客服'])


@router.post('', status_code=201)
def create_conversation(
    payload: ConversationStart = ConversationStart(),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    conversation = start_conversation(db, user, force_new=payload.force_new)
    db.commit()
    return conversation_data(db, conversation)


@router.get('/{identity}')
def detail(identity: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return conversation_data(db, load_conversation(db, user, identity))


@router.post('/{identity}/messages')
def message(identity: int, payload: ConversationMessageInput, request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conversation = load_conversation(db, user, identity, payload.version)
    show_preview = add_user_message(
        db,
        conversation,
        user,
        payload,
        request.app.state.model_path,
        expected_sha256=request.app.state.expected_model_sha256,
        mapping_path=request.app.state.label_map_path,
    )
    db.commit()
    return {**conversation_data(db, conversation), 'show_handoff_preview': show_preview}


@router.post('/{identity}/actions')
def action(identity: int, payload: ConversationAction, request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conversation = load_conversation(db, user, identity, payload.version)
    apply_conversation_action(
        db,
        conversation,
        user,
        payload,
        request.app.state.model_path,
        expected_sha256=request.app.state.expected_model_sha256,
        mapping_path=request.app.state.label_map_path,
    )
    db.commit()
    return conversation_data(db, conversation)