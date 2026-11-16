"""Select the current request for routing while the conversation retains the verbatim text."""
import re

from app.services.refund_language import (
    CONDITION, HESITATION, QUOTED, REPORTED, REVIEW, directly_requests_refund, refund_topic, settlement_topic,
    timing_question,
)

CLAUSE_BREAK = re.compile(r'[，,。；;！!？?]|(?=而是|改为|改成|只是想|就是想|只想查|只想问)')
FOCUS = re.compile(r'^(?:但是?|不过)?(?:我)?(?:现在|这次)(?:问|查|只问)(?:的?是)?')
INQUIRY = re.compile(r'^(?:请|麻烦)?(?:我)?(?:现在|眼下|目前|这会儿)?(?:只是|就是|只|仅|其实|就|帮我|给我|想要?|要)(?:想|要)?(?:问|查|看|了解|知道)')
CANCEL_PREFIX = re.compile(
    r'^(?:请|麻烦)?(?:我(?:现在)?)?(?:并)?(?:先|暂时)?'
    r'(?:不是|不想|不用|不要|不需要|别(?=再|给|帮|替|办|退|查|问|提|说|申请|提交|操作|处理)|'
    r'不退|不查|不谈|算了|没(?:有)?(?:要求|说要|打算|要|想))'
)
REFUND_WITHDRAWAL = re.compile(
    r'(?:不想|不需要|不用|(?<!要)不要|没有要|没要求|没说要|没打算|别|先不|暂不)'
    r'(?:再|急着|给我|帮我|替我|办理|申请|提交|直接|操作|做|走|办)*退(?:款|钱|货|费)?'
    r'|(?:退款|退货|退费|退款申请)(?:就)?(?:先|暂时)?(?:不用|不要|不办|放一放|搁一搁)'
)
STOP_ACTION = re.compile(r'(?:(?:我|请|先|暂时|还是|现在|就|又|你|您|帮我|给我|替我)*'
                         r'(?:别|不要|不用|不必|先不|暂不)(?:再|急着|替我|帮我|给我)*'
                         r'(?:办(?:理)?|操作|提交|处理|申请)(?:了|吧|啊)?|算了)')


def effective_request(text: str) -> str:
    text = text.strip().replace('帐号', '账号')
    clauses = [part.strip() for part in CLAUSE_BREAK.split(text) if part.strip()]
    remaining: list[str] = []
    changed = False
    for part in clauses:
        pivot = re.match(r'^(?:而是|改为|改成)', part)
        if pivot:
            remaining.clear()
            part = part[pivot.end():]
            changed = True
        if REFUND_WITHDRAWAL.search(part) or STOP_ACTION.fullmatch(part):
            # Keep an earlier inquiry, but a withdrawal supersedes an earlier application.
            remaining = [p for p in remaining if not directly_requests_refund(p)]
            changed = True
            continue
        cancel = CANCEL_PREFIX.match(part)
        if cancel:
            changed = True
            remainder = part[cancel.end():].strip()
            if re.search(r'先看|只问|只想|改成|改为', remainder):
                remaining = [remainder]
            continue
        focus = FOCUS.match(part)
        if focus and remaining:
            remaining = [part[focus.end():]]
            changed = True
        elif INQUIRY.match(part) and remaining:
            # A follow-up like “只想问要几天” still needs its preceding topic.
            if re.search(r'退|订单|包裹|货|快递|物流|密码|账号|验证码|耳机', part):
                remaining = [part]
                changed = True
            else:
                remaining.append(part)
        else:
            remaining.append(re.sub(r'^(?:而?是)(?=要|想|查|忘|一直)', '', part) if changed else part)
    if changed:
        focused = '，'.join(remaining)
        if (refund_topic(text) and not refund_topic(focused) and timing_question(focused)
                and (settlement_topic(focused) or REVIEW.search(focused))
                and not re.search(r'发票|账号|贷款|支付失败|发货|配送|运费|快递|换货', focused)):
            return f'咨询退款时效，{focused}'
        if (directly_requests_refund(focused) and not directly_requests_refund(text)
                and any(cue.search(text) for cue in (QUOTED, CONDITION, HESITATION, REPORTED))):
            return text
        return focused
    return text
