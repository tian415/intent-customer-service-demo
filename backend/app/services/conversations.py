"""Finite-state ecommerce support chats: orders, intent, FAQ/rules, human handoff."""
import re
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Category, Conversation, ConversationMessage, Order, User, now
from app.schemas import ConversationAction, ConversationMessageInput, TicketCreate
from app.services.faq import search_faq
from app.services.orders import ORDER_STATUS_LABELS, get_order, list_orders, order_data, recent_cases
from app.services.refund_language import (
    BACK_TO_ACCOUNT, CONDITION, GENERAL, HESITATION, OTHER_MOVEMENT, OUTSIDE_FUNDS, QUOTED, REPORTED, REVIEW, SHORT_CONFIRM, purchase_money_return, refund_topic,
    asks_about_submission_step, settlement_topic, timing_question,
)
from app.services.request_focus import effective_request
from app.services.refunds import INELIGIBLE_STATUSES, POLICY_HELP, REFUND_STAGES, asks_to_cancel_refund, refund_choice_needed, refund_for_order, refund_intent
from app.services.tickets import create_ticket, predict_intent

ORDER_HINT_TOKENS = (
    '订单', '物流', '快递', '发货', '签收', '退款', '退货', '取消订单', '改地址', '发票',
    'order', 'refund', 'shipping', 'delivery', 'track', 'cancel_order', 'change_order',
    'track_order', 'get_refund', 'payment', 'invoice',
)

STATUS_LABELS = {
    'active': '接待中',
    'waiting_order': '待选择订单',
    'handed_off': '已转人工',
    'closed': '已结束',
}

INTENT_LABEL_ZH = {
    'recover_password': '找回密码',
    'create_account': '注册账号',
    'delete_account': '注销账号',
    'edit_account': '修改账号资料',
    'registration_problems': '注册异常',
    'switch_account': '切换账号',
    'get_refund': '申请退款',
    'check_refund_policy': '退款政策咨询',
    'track_refund': '退款进度查询',
    'track_order': '查询物流',
    'cancel_order': '取消订单',
    'change_order': '修改订单',
    'place_order': '下单咨询',
    'delivery_options': '配送方式',
    'delivery_period': '送达时效',
    'change_shipping_address': '修改收货地址',
    'set_up_shipping_address': '设置收货地址',
    'check_invoice': '查询发票',
    'get_invoice': '开具发票',
    'payment_issue': '支付异常',
    'check_payment_methods': '支付方式',
    'complaint': '投诉建议',
    'contact_customer_service': '联系客服',
    'contact_human_agent': '转人工',
}

SOURCE_LABELS = {
    'rules': '关键词匹配',
    'model': '本地意图模型',
    'fallback': '待人工确认',
}



def _touch(conversation: Conversation) -> None:
    conversation.updated_at = now()


def _add_message(db: Session, conversation: Conversation, role: str, body: str) -> ConversationMessage:
    message = ConversationMessage(conversation_id=conversation.id, role=role, body=body)
    db.add(message)
    _touch(conversation)
    return message


def _intent_display(prediction: dict | None) -> str | None:
    if not prediction:
        return None
    label = prediction.get('predicted_label')
    category = prediction.get('category_name')
    if category:
        return category
    if label:
        return INTENT_LABEL_ZH.get(label, label)
    return None


def _stage(conversation: Conversation) -> str:
    if conversation.status == 'waiting_order':
        return 'await_order'
    if conversation.status == 'handed_off':
        return 'handed_off'
    if conversation.status == 'closed':
        return 'closed'
    if conversation.selected_order_id:
        return 'order_bound'
    return 'greeting'


def _quick_replies(conversation: Conversation, selected: Order | None) -> list[str]:
    if conversation.status in ('handed_off', 'closed'):
        return []
    if conversation.status == 'waiting_order':
        return ['转人工客服']
    # 动作类诉求已识别、待转人工时，把「转人工」放最前
    if conversation.next_action == 'answer' and _headphone_issue(conversation.current_request or '', selected):
        return ['已恢复声音', '仍然没声音', '转人工处理']
    request = conversation.current_request or ''
    if conversation.next_action == 'clarify' and refund_intent(request) == 'clarify_refund':
        return ['先了解退款时效', '我确认申请退款', '转人工处理']
    if (conversation.next_action == 'clarify' and re.search(r'退[款货费]', request)
            and not refund_choice_needed(request)):
        return ['查询退款进度', '了解退款条件', '我想申请退款']
    if conversation.next_action == 'handoff':
        return ['转人工处理']
    if conversation.next_action == 'clarify' and not conversation.current_request:
        return ['查询物流进度', '了解退款条件', '转人工客服']
    if conversation.current_request or conversation.selected_order_id:
        return ['转人工处理']
    return ['查询物流进度', '我想申请退款', '账号登录有问题', '转人工客服']


def _apply_prediction(conversation: Conversation, prediction: dict) -> None:
    conversation.intent_category_id = prediction['category_id']
    conversation.prediction_source = prediction['source']
    conversation.prediction_model_version = prediction['model_version']
    conversation.prediction_label = prediction['predicted_label']
    conversation.prediction_mapping_version = prediction['mapping_version']
    conversation.prediction_integrity = prediction['integrity']
    conversation.prediction_score = prediction['score']
    conversation.needs_manual = prediction['needs_manual']


def conversation_data(db: Session, conversation: Conversation) -> dict:
    owner = db.get(User, conversation.user_id)
    messages = [
        {'id': m.id, 'role': m.role, 'body': m.body, 'created_at': m.created_at}
        for m in db.scalars(
            select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id).order_by(ConversationMessage.id)
        )
    ]
    selected = db.get(Order, conversation.selected_order_id) if conversation.selected_order_id else None
    prediction = _saved_prediction(db, conversation)
    current_request = conversation.current_request
    if _control_kind(current_request or '') == 'handoff' or (not current_request and not conversation.next_action):
        current_request = _legacy_request(messages)
    intent = refund_intent(current_request or '', prediction['predicted_label'] if not prediction['needs_manual'] else None)
    related = (refund_for_order(db, conversation.user_id, selected.id, open_only=intent == 'get_refund')
               if selected and intent in ('get_refund', 'track_refund') else None)
    return {
        'recent_cases': recent_cases(db, conversation.user_id),
        'service_intent': intent,
        'can_submit_refund': bool(selected and intent == 'get_refund' and not related and selected.status not in INELIGIBLE_STATUSES),
        'related_refund_id': related.id if related else None,
        'id': conversation.id,
        'status': conversation.status,
        'status_label': STATUS_LABELS.get(conversation.status, conversation.status),
        'stage': _stage(conversation),
        'selected_order_id': conversation.selected_order_id,
        'selected_order': order_data(selected) if selected else None,
        'ticket_id': conversation.ticket_id,
        'version': conversation.version,
        'current_request': current_request,
        'next_action': None if conversation.status in ('closed', 'handed_off') else conversation.next_action,
        'prediction_source': conversation.prediction_source,
        'prediction_source_label': SOURCE_LABELS.get(conversation.prediction_source or '', conversation.prediction_source),
        'prediction_model_version': conversation.prediction_model_version,
        'prediction_label': conversation.prediction_label,
        'prediction_label_display': _intent_display(prediction),
        'prediction_mapping_version': conversation.prediction_mapping_version,
        'prediction_integrity': conversation.prediction_integrity,
        'prediction_score': conversation.prediction_score,
        'needs_manual': conversation.needs_manual,
        'quick_replies': _quick_replies(conversation, selected),
        'created_at': conversation.created_at,
        'updated_at': conversation.updated_at,
        'messages': messages,
        'orders': list_orders(db, owner) if owner else [],
    }


def load_conversation(db: Session, user: User, identity: int, version: int | None = None) -> Conversation:
    if user.role != 'user':
        raise HTTPException(403, '只有普通用户可以使用智能客服会话')
    conversation = db.scalar(select(Conversation).where(Conversation.id == identity, Conversation.user_id == user.id))
    if not conversation:
        raise HTTPException(404, '会话不存在或无访问权限')
    if version is not None and conversation.version != version:
        raise HTTPException(409, '会话已被更新，请刷新后重试')
    return conversation


def _orders_summary(orders: list[dict]) -> str:
    if not orders:
        return '暂时没有查到您的订单。您可以直接说明问题，或点「转人工」。'
    return '查询物流或办理退款时，可以从订单卡片中选择对应的一笔。'


def start_conversation(db: Session, user: User, *, force_new: bool = False) -> Conversation:
    if user.role != 'user':
        raise HTTPException(403, '只有普通用户可以开启智能客服会话')
    latest = db.scalar(select(Conversation).where(Conversation.user_id == user.id)
                       .order_by(Conversation.id.desc()).limit(1))
    if not force_new and latest and latest.status in ('active', 'waiting_order'):
        return latest
    # Retire superseded chats too, including leftovers created before this upgrade.
    for previous in db.scalars(select(Conversation).where(
        Conversation.user_id == user.id, Conversation.status.in_(('active', 'waiting_order')),
    )):
        previous.status = 'closed'
        _touch(previous)
    conversation = Conversation(user_id=user.id, status='active', needs_manual=True)
    db.add(conversation)
    db.flush()
    orders = list_orders(db, user)
    welcome = '我是售后助手。你可以查询订单、了解退款规则，或提交退款申请。'
    _add_message(db, conversation, 'assistant', welcome)
    _add_message(db, conversation, 'system', _orders_summary(orders))
    db.flush()
    return conversation


# Match a standalone command, so a complaint mentioning a human agent stays an issue.
HUMAN_AGENT = r'(?:(?:转(?:接)?|找|联系|接通|叫)个?)?人工(?:客服|处理|服务)?'
HANDOFF_REQUEST = re.compile(r'(?:请问|麻烦|请)?(?:可以|能不能|能否)?(?:帮我|给我|我想要?|我要)?' + HUMAN_AGENT + r'(?:吗|吧|一下)?')
HANDOFF_DECLINE = re.compile(r'(?:我)?(?:先)?(?:不用|不要|不需要|不想|别)' + HUMAN_AGENT + r'(?:了)?')
ACKNOWLEDGEMENTS = {'好', '好的', '明白了', '谢谢', '谢谢你', '知道了', '嗯', '对', '是的'}
ACK_ONLY = re.compile(r'^(?:好的?|明白了|知道了|谢谢(?:你|您)?|嗯|对|是的)(?:[，,。！!？?\s]*(?:好的?|谢谢(?:你|您)?|明白了|知道了|嗯|对|是的))*$')
PICK_COMMAND = '我先选一笔订单'


def _control_kind(text: str) -> Literal['handoff', 'decline', 'ack', 'pick'] | None:
    short = text.strip(' 。！!？?，,')
    if HANDOFF_REQUEST.fullmatch(short) or re.fullmatch(
        r'(?:请|麻烦|直接)?(?:可以|能不能|能否)?(?:帮我|给我|我想要?|我要)?' + HUMAN_AGENT + r'(?:吗|吧|一下)?',
        short,
    ):
        return 'handoff'
    if HANDOFF_DECLINE.fullmatch(short):
        return 'decline'
    if short in ACKNOWLEDGEMENTS or ACK_ONLY.fullmatch(short):
        return 'ack'
    if short == PICK_COMMAND:
        return 'pick'
    return None


def _legacy_request(messages: list[dict]) -> str | None:
    return next((effective_request(m['body']) for m in reversed(messages)
                 if m['role'] == 'user' and not _control_kind(m['body'])), None)


def _saved_prediction(db: Session, chat: Conversation) -> dict:
    category = db.get(Category, chat.intent_category_id) if chat.intent_category_id else None
    return {
        'category_id': chat.intent_category_id, 'category_name': category.name if category else None,
        'predicted_label': chat.prediction_label, 'source': chat.prediction_source,
        'model_version': chat.prediction_model_version, 'mapping_version': chat.prediction_mapping_version,
        'integrity': chat.prediction_integrity, 'score': chat.prediction_score,
        'needs_manual': chat.intent_category_id is None, 'reason': '沿用本轮顾客诉求的识别结果',
    }


def _headphone_issue(text: str, order: Order | None = None) -> bool:
    headphone = bool(re.search(r'耳机|耳塞|耳麦|耳朵[里上](?:戴|塞|挂)?[着的]?[那这]?(?:一?对|两[只颗个])', text)
                     or (order is not None and '耳机' in order.product_name))
    return bool(headphone and re.search(
        r'没声|没有声音|无声|不出声|听不[到见]|没声音|没动静|没反应|'
        r'(?:另?一[只边侧个]|左[耳边]|右[耳边]).{0,4}(?:哑|不响|静音)|'
        r'(?:只有?|就)(?:左|右|一)(?:边|侧|只|个|耳).{0,4}(?:响|有声|能听)', text,
    ))


def _order_one_liner(order: Order) -> str:
    label = ORDER_STATUS_LABELS.get(order.status, order.status)
    return f'{order.product_name}（{order.order_no}，{label}）'


def _timing_reply(db: Session, text: str) -> str:
    faq = search_faq(db, text)
    if faq['reliable'] and faq['items']:
        entry = faq['items'][0]
        question = entry['question']
        if (refund_topic(question) and timing_question(question)
                and bool(REVIEW.search(question)) == bool(REVIEW.search(text))
                and settlement_topic(question) == settlement_topic(text)):
            return entry['answer']

    review = '提交后由客服审核，目前没有可确认的固定审核时长。审核结果会显示在「订单与售后」。'
    settlement = '审核通过后才进入退款处理。这里没有银行到账记录，也无法给出确切的到账时间。'
    if REVIEW.search(text) and not settlement_topic(text):
        return review
    if settlement_topic(text) and not REVIEW.search(text):
        return settlement
    return review + settlement


def _reply(db: Session, chat: Conversation, text: str, prediction: dict) -> tuple[str, str]:
    label = prediction.get('predicted_label')
    intent = refund_intent(text, label if not prediction['needs_manual'] else None)
    policy = intent == 'check_refund_policy'
    track = label in ('track_order', 'delivery_period') or any(
        t in text for t in ('物流', '快递', '发货', '发出', '发出去', '运输', '在途', '路上',
                            '到哪', '签收', '送到', '送达', '收到', '包裹', '中转站', '揽收', '派件', '派送',
                            '配送', '运单', '快件', '分拨', '转运', '订单状态', '订单进度')
    ) or bool(re.search(r'(东西|包裹|货|这单|订单).{0,6}(在哪|哪里|哪儿|发出|发了|在途|路上|进度|状态)', text))
    action = label in ('get_refund', 'cancel_order', 'change_order', 'change_shipping_address',
                       'payment_issue', 'complaint', 'get_invoice') or any(
        t in text for t in ('申请退款', '退款', '退货', '退费', '取消订单', '改地址', '改址', '投诉', '发票')
    )
    login_sms_missing = (
        '短信' in text and re.search(r'登录|登陆|验证身份|登不进', text)
        and re.search(r'收不到|没收[到着]|没(?:有)?[来发]|没动静|不(?:过)?来|没(?:有)?到|等不到', text)
    )
    verification_code = re.search(r'(?:验证|登录|登陆|短信|校验|认证|动态)码', text)
    account_question = verification_code or login_sms_missing or any(term in text for term in ('密码', '登录', '账号'))
    if account_question and not re.search(
        r'物流|包裹|快递|退[货款钱]|订单状态', text,
    ):
        track = False
    # Shipping questions that mention "退款" only to exclude it should not become handoff.
    if track and re.search(r'不(?:谈|办|要|想)?退款|只(?:问|查).{0,6}(?:发货|物流|快递)', text):
        action = False
    order_related = bool(intent) or track or any(t in text.lower() for t in ORDER_HINT_TOKENS) or any(
        t in (label or '') for t in ('order', 'delivery', 'refund', 'invoice', 'shipping', 'payment')
    )
    order = db.get(Order, chat.selected_order_id) if chat.selected_order_id else None
    if intent == 'refund_submission_help':
        return 'answer', ('点「填写退款申请」只会打开表单。填好退款原因后，点「确认提交申请」并看到售后单号，才算提交成功。'
                          '确认前退出或取消不会建单。已提交的申请可在「订单与售后 → 我的全部售后」查看，由客服审核。')
    if intent == 'refund_timing':
        return 'answer', _timing_reply(db, text)
    if intent == 'clarify_refund':
        return 'clarify', '您是先了解退款，还是已经决定要申请？如果只想知道多久能办好，可以直接问审核或到账时间。'
    if not intent and OUTSIDE_FUNDS.search(text) and not re.search(
        r'快递|快件|包裹|运单|物流|订单状态|配送|签收|发货|到货|送达|送到|揽收', text,
    ):
        return 'clarify', '这里能核对本店订单的售后记录。如果是本店扣款异常，请补充订单和支付页面提示。如果是其他账户的收支，请在对应的支付或账户记录中核对。'
    if asks_to_cancel_refund(text):
        return 'handoff', '撤销已有的退款申请需要人工核对处理进度。可以在「订单与售后」打开原售后单联系承办客服，或点「人工」说明要撤销哪一笔。'
    if refund_choice_needed(text):
        return 'clarify', '您想申请退款，还是希望换货？请先确认一种诉求；退款可在这里提交申请，换货需要人工核实。'
    if not intent and re.search(r'(?:更换|补发|补寄|换)(?:一?[个件套只条块根对]|新的?)?'
                                r'(?:配件|零件|附件|盖子|杯盖|密封圈|耳塞|耳套|滤芯|电池|充电线)', text):
        return 'handoff', '配件能否单独更换或补寄，需要客服核对商品和配件情况。可以点「人工」把当前描述交给客服。'
    if not intent and re.search(r'退款|退费|退货', text) and not track:
        return 'clarify', '您是想了解退款条件、查已有申请的进度，还是要新申请退款？'
    if not policy and order_related and not order:
        available = db.scalar(select(Order.id).where(Order.user_id == chat.user_id).limit(1))
        if available is None:
            return 'handoff', '暂未查到您名下的订单。您可以补充情况，或点「人工」请客服核实。'
        if intent == 'track_refund' and timing_question(text):
            return 'ask_order', _timing_reply(db, text) + ' 要查您这一笔的审核进度，请选对应订单。'
        return 'ask_order', '请先点下方订单卡片选一笔，我再继续处理。您也可以补充或更正问题。'
    if policy:
        faq = search_faq(db, text)
        answer = (faq['items'][0]['answer'] if faq['reliable'] and faq['items']
                  and '退' in faq['items'][0]['question'] else POLICY_HELP)
        if re.search(r'几天|多久|期限|时限|多少天|第.{1,3}天|过期', text) and not re.search(r'天|日内|小时', answer):
            return 'answer', '当前规则没有写明具体退货期限。' + answer + ' 如需确认您的订单是否还在期限内，可点「人工」。'
        return 'answer', answer
    if order and intent == 'track_refund':
        ticket = refund_for_order(db, chat.user_id, order.id)
        timing_note = _timing_reply(db, text) if timing_question(text) else ''
        if ticket:
            return 'answer', f'{order.product_name}的退款申请 #{ticket.id}：{REFUND_STAGES[ticket.refund_stage]}。打开售后单可查看处理意见。{timing_note or "这里没有银行到账记录。"}'
        return 'answer', f'{_order_one_liner(order)}。未查到这笔订单的退款审核单，也没有可核实的到账记录。{timing_note}'
    if order and intent == 'get_refund':
        ticket = refund_for_order(db, chat.user_id, order.id, open_only=True)
        if ticket:
            return 'answer', f'这笔订单已有退款申请 #{ticket.id}，{REFUND_STAGES[ticket.refund_stage]}。可以打开原单查看或补充说明。'
        if order.status in INELIGIBLE_STATUSES:
            return 'answer', f'订单记录为「{ORDER_STATUS_LABELS[order.status]}」，当前不能新申请退款。如对状态有异议，可以联系人工核对。'
        return 'handoff', f'{order.product_name}可以提交退款申请。请核对订单并填写原因，提交后由售后客服审核。'
    if _headphone_issue(text, order):
        return 'answer', '先核对设备的左右声道平衡是否居中，再换一段音频试听。如果仍有一侧无声，可以带着排查记录交给客服。'
    if track and order and not policy:
        shipping = {'shipped': '这笔订单已发货。', 'delivered': '这笔订单已签收。'}.get(order.status)
        timing = '这里没有实时物流轨迹或预计送达时间，无法保证具体送达日期。' if re.search(
            r'多久|什么时候|几天|何时|明天|今天|后天|保证|送到|送达|收到', text,
        ) else ''
        if re.search(r'中转|卡在|不动|没动|没更新|不更新|停在|停了|没动静|轨迹|原因|怎么回事', text) and not timing:
            timing = '这里没有实时物流轨迹，无法核实停留原因。'
        return 'answer', f'订单{_order_one_liner(order)}。{shipping or "当前记录没有可核实的发货进度。"}{timing}如需进一步核实，可点「人工」。'
    if action and not policy:
        context = f'对应订单：{_order_one_liner(order)}。\n' if order else ''
        return 'handoff', f'已识别您的办理请求。{context}请点「人工」确认转接，由客服审核办理。'
    if account_question:
        password_reset = '密码' in text and bool(re.search(r'忘|想不起来|记不住|重设|重置|找回', text))
        if not password_reset:
            if verification_code or login_sms_missing:
                return 'handoff', '这里无法核实验证码的发送或失效原因。请点「人工」补充报错提示，不要发送密码或验证码。'
            if chat.next_action == 'clarify':
                return 'handoff', '目前的信息还不足以确认登录失败原因。请点「人工」补充页面报错，不要发送密码或验证码。'
            return 'clarify', '是忘记密码、收不到验证码，还是页面提示账号不可用？请补充一种情况，不要发送密码或验证码。'
    faq = search_faq(db, text)
    if faq['reliable'] and faq['items']:
        return 'answer', faq['items'][0]['answer'] + '\n需要继续办理时，可点「人工」。'
    if policy or prediction.get('category_id') or chat.next_action == 'clarify':
        return 'handoff', '目前没有可核实的知识答案，您可以点「人工」把问题交给客服。'
    return 'clarify', '您具体想查询什么，还是需要办理一项售后？可以补充一句，也可以点「人工」。'


def _respond(db: Session, chat: Conversation, text: str, prediction: dict) -> None:
    if (chat.selected_order_id and refund_intent(text) == 'refund_timing' and purchase_money_return(text)
            and not any(cue.search(text) for cue in (GENERAL, CONDITION, HESITATION, QUOTED, REPORTED))
            and refund_for_order(db, chat.user_id, chat.selected_order_id)):
        text = f'查询退款进度，{text}'
        chat.current_request = text
    action, reply = _reply(db, chat, text, prediction)
    chat.next_action = action
    chat.status = 'waiting_order' if action == 'ask_order' else 'active'
    chat.needs_manual = action in ('handoff', 'clarify', 'ask_order')
    _add_message(db, chat, 'assistant', reply)


def _restore_request(db: Session, chat: Conversation, model_path, expected_sha256, mapping_path) -> None:
    # Recover open sessions created before request tracking, or where an older
    # version stored a standalone handoff command in place of the actual issue.
    if _control_kind(chat.current_request or '') != 'handoff' and (chat.current_request or chat.next_action):
        return
    chat.current_request = None
    rows = db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == chat.id, ConversationMessage.role == 'user',
    ).order_by(ConversationMessage.id.desc()))
    for row in rows:
        if not _control_kind(row.body):
            chat.current_request = effective_request(row.body)
            if not chat.current_request:
                break
            prediction = predict_intent(db, chat.current_request, model_path,
                                        expected_sha256=expected_sha256, mapping_path=mapping_path)
            _apply_prediction(chat, prediction)
            break


def add_user_message(db: Session, conversation: Conversation, user: User, payload: ConversationMessageInput, model_path=None, *, expected_sha256=None, mapping_path=None) -> bool:
    """Save the message and indicate whether this turn requests a transfer preview."""
    if conversation.status in ('handed_off', 'closed'):
        raise HTTPException(409, '会话已结束，请新开会话')
    text = payload.body.strip()
    # Legacy UI command, not a new utterance about the customer's issue.
    if text == PICK_COMMAND and conversation.status == 'waiting_order':
        return False
    control = _control_kind(text)
    if control == 'handoff':
        _restore_request(db, conversation, model_path, expected_sha256, mapping_path)
    _add_message(db, conversation, 'user', text)
    selected = db.get(Order, conversation.selected_order_id) if conversation.selected_order_id else None
    if _headphone_issue(conversation.current_request or '', selected) and conversation.next_action == 'answer':
        new_topic = refund_topic(text) or any(word in text for word in ('物流', '快递', '发货', '账号', '密码', '登录'))
        unsuccessful = not new_topic and bool(re.search(r'仍然|还是|依旧|还没|没有恢复|没恢复|没用|没解决|听不到|听不见', text))
        recovered = text in ('已恢复声音', '恢复了') or bool(re.fullmatch(
            r'(?:好了[，,]?)?(?:现在|已经)?(?:好了[，,]?)?(?:能听[到见]了|有声音了|恢复(?:声音)?了|好了)[。！!]*',
            text,
        ))
        if recovered and not unsuccessful:
            conversation.status = 'closed'
            _add_message(db, conversation, 'assistant', '已按你的反馈结束本次咨询。')
            db.flush()
            return False
        if unsuccessful or text == '仍无声':
            conversation.next_action = 'handoff'
            conversation.needs_manual = True
            _add_message(db, conversation, 'assistant', '已记录排查后仍然无声。可点「人工」把症状和排查反馈一起交给客服。')
            db.flush()
            return False
    if control:
        if control == 'handoff':
            tip = '请核对当前诉求并确认转接。' if conversation.current_request else '请先说一下需要客服处理的问题。'
        elif control == 'decline':
            tip = '好的，继续当前咨询。'
        elif control == 'pick':
            tip = '可从自己的订单中选择一笔，或直接说明问题。'
        elif conversation.next_action == 'clarify' and refund_topic(conversation.current_request or ''):
            tip = '您是要了解退款，还是决定现在申请？请告诉我您选哪一种。'
        else:
            tip = '好的。有其他情况可以继续补充。'
        _add_message(db, conversation, 'assistant', tip)
    else:
        request = effective_request(text)
        if not request:
            conversation.current_request = None
            _apply_prediction(conversation, predict_intent(db, ''))
            conversation.next_action = 'clarify'
            conversation.status = 'active'
            conversation.needs_manual = True
            _add_message(db, conversation, 'assistant', '好的，原诉求不再办理。请说一下现在希望解决的问题。')
            db.flush()
            return False
        previous = conversation.current_request or ''
        previous_intent = refund_intent(previous)
        other_topic = re.search(r'快递|物流|发货|送达|包裹|耳机|维修|密码|登录|验证码|换货', request)
        if (previous_intent == 'track_refund' and purchase_money_return(request) and timing_question(request)
                and not other_topic and not GENERAL.search(request) and not CONDITION.search(request)):
            request = f'查询退款进度，{request}'
        elif (refund_topic(previous) or previous_intent) and not refund_topic(request) and not other_topic and not OTHER_MOVEMENT.search(request):
            if previous_intent == 'clarify_refund' and SHORT_CONFIRM.fullmatch(request):
                request = '我确认申请退款'
            elif asks_about_submission_step(request) and not re.search(r'发票|地址|注销|收货|付款|下单', request):
                request = f'关于退款，{request}'
            elif HESITATION.search(request):
                request = f'关于退款，{request}'
            elif BACK_TO_ACCOUNT.search(request) and timing_question(f'到账，{request}'):
                context = '查询退款进度' if previous_intent == 'track_refund' else '咨询一般退款'
                request = f'{context}到账时效，{request}'
            elif (previous_intent == 'track_refund' and re.fullmatch(
                r'(?:那|请问|钱|款|到底|还没|已经)?到[账帐](?:了没|了吗|了么|没|没有)[？?。]?', request,
            )):
                request = f'查询退款进度，{request}'
            elif timing_question(request) or re.fullmatch(
                r'(?:那|请问|大概|通常|一般|到底|还|要|得|需要|等|会|是|什么时候|何时|多久|几天|啊|呀|呢|吗|了|[，,？?。！!\s])+', request,
            ) and re.search(r'多久|几天|何时|什么时候', request):
                context = '查询退款进度' if previous_intent == 'track_refund' else '咨询一般退款时效'
                request = f'{context}，{request}'
        prediction = predict_intent(db, request, model_path, expected_sha256=expected_sha256, mapping_path=mapping_path)
        if conversation.current_request and not refund_intent(request) and not HESITATION.search(text) and (
            (not prediction['category_id'] and request.startswith(('补充一下', '订单号是', '已经等了', '原因是', '补充：')))
            or (
                refund_intent(conversation.current_request) == 'get_refund'
                and refund_intent(request) is None
                and re.match(r'^(?:原因是|补充一下|补充：)', request)
            )
        ):
            request = conversation.current_request
            prediction = _saved_prediction(db, conversation)
        if any(token in request for token in ('账号', '密码', '登录', '验证码')) and not any(
            token in request for token in ('订单', '退款', '支付')
        ):
            conversation.selected_order_id = None
        conversation.current_request = request
        _apply_prediction(conversation, prediction)
        _respond(db, conversation, request, prediction)
    db.flush()
    return control == 'handoff' and bool(conversation.current_request)


def apply_conversation_action(db: Session, conversation: Conversation, user: User, payload: ConversationAction, model_path=None, *, expected_sha256=None, mapping_path=None) -> Conversation:
    if conversation.status in ('handed_off', 'closed'):
        raise HTTPException(409, '会话已结束，无法继续操作')
    if payload.action == 'select_order':
        if payload.order_id is None:
            raise HTTPException(422, '请选择订单')
        order = get_order(db, user, payload.order_id)
        conversation.selected_order_id = order.id
        conversation.status = 'active'
        _add_message(db, conversation, 'system', f'已选择订单 {order.order_no}（{order.product_name}）。')
        _restore_request(db, conversation, model_path, expected_sha256, mapping_path)
        if conversation.current_request:
            _respond(db, conversation, conversation.current_request, _saved_prediction(db, conversation))
        else:
            _add_message(db, conversation, 'assistant', f'已选中订单：{_order_one_liner(order)}。请继续说明问题。')
    elif payload.action == 'close':
        conversation.status = 'closed'
        _add_message(db, conversation, 'assistant', '本会话已结束。如需继续，请点击「重新咨询」。')
    elif payload.action in ('handoff', 'submit_refund'):
        user_lines = [
            m.body for m in db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation.id,
                    ConversationMessage.role == 'user',
                ).order_by(ConversationMessage.id)
            )
        ]
        _restore_request(db, conversation, model_path, expected_sha256, mapping_path)
        if not conversation.current_request:
            raise HTTPException(422, '请先描述问题再转人工')
        order = db.get(Order, conversation.selected_order_id) if conversation.selected_order_id else None
        order_line = (
            f'关联订单：{order.order_no} {order.product_name}（{ORDER_STATUS_LABELS.get(order.status, order.status)}）'
            if order else '关联订单：未选择'
        )
        prediction = _saved_prediction(db, conversation)
        title = conversation.current_request[:120]
        transcript = '\n'.join(f'- {line}' for line in user_lines[-8:])
        description = (f'来自智能客服多轮会话 #{conversation.id}\n{order_line}\n'
                       f'当前诉求：{conversation.current_request}\n用户表述摘要：\n{transcript}')
        intent = refund_intent(conversation.current_request, prediction['predicted_label'] if not prediction['needs_manual'] else None)
        is_refund = bool(order and intent == 'get_refund')
        if payload.action == 'submit_refund' and not is_refund:
            raise HTTPException(422, '请先说明退款诉求并选择本人订单')
        ticket = refund_for_order(db, user.id, order.id, open_only=True) if is_refund else None
        if not ticket and is_refund and order.status in INELIGIBLE_STATUSES:
            if payload.action == 'submit_refund':
                raise HTTPException(422, '这笔订单当前不能申请退款')
            is_refund = False  # A general status dispute can still be escalated.
        if not ticket:
            if payload.action == 'submit_refund':
                if not payload.reason.strip():
                    raise HTTPException(422, '请填写退款原因')
                _add_message(db, conversation, 'user', payload.reason.strip())
                description = f'退款原因：{payload.reason.strip()}\n{description}'
            ticket = create_ticket(
                db, user, TicketCreate(title=title, description=description[:10000]),
                conversation_prediction=prediction, order_id=order.id if order else None,
                refund_request=is_refund,
            )
        conversation.ticket_id = ticket.id
        conversation.status = 'handed_off'
        _add_message(
            db,
            conversation,
            'assistant',
            f'已关联售后单 #{ticket.id}。可在顶部「订单与售后」查看进度；本对话转为只读。',
        )
    else:
        raise HTTPException(422, '不支持的操作')
    _touch(conversation)
    db.flush()
    return conversation
