"""Refund intent routing and the public state of a local review request."""
import re
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ticket
from app.services.refund_language import (
    CONDITION, FILED, GENERAL, HESITATION, OTHER_MOVEMENT, PAST, QUOTED, REPORTED, directly_requests_refund, purchase_money_return,
    asks_about_submission_step, refund_topic, timing_question,
)
from app.services.request_focus import effective_request

RefundIntent = Literal['check_refund_policy', 'get_refund', 'track_refund', 'refund_timing', 'clarify_refund', 'refund_submission_help']
REFUND_STAGES = {'requested': '等待客服审核', 'approved': '审核通过', 'declined': '未通过审核'}
INELIGIBLE_STATUSES = {'pending_payment', 'cancelled', 'refunded'}
POLICY_HELP = '本店接受本人已付款订单的退款申请。待付款、已取消或已退款的订单不能新申请。是否符合退款条件由客服根据原因审核。申请时请选本人订单，填写退款原因并确认提交。客服审核后会在「我的售后」留下处理意见；提交申请不会直接产生退款。'


def refund_choice_needed(text: str) -> bool:
    """Do not choose a refund for a customer weighing refund versus exchange."""
    return bool(re.search(r'退款|退货|退钱', text) and '换货' in text
                and re.search(r'还是|或者|或|哪个好|哪种|选哪个|还没想好|没想好', text))


def asks_to_cancel_refund(text: str) -> bool:
    """An existing application must be reviewed by staff, including when already approved."""
    if any(cue.search(text) for cue in (CONDITION, HESITATION, QUOTED, REPORTED)):
        return False
    return bool(re.search(
        r'(?:撤销|撤回|取消|撤掉).{0,12}(?:退款|退货|退费|售后)(?:申请|单)?'
        r'|(?:退款|退货|退费|售后)(?:申请|单).{0,8}(?:撤销|撤回|取消|撤掉)', text,
    ))


def refund_intent(text: str, label: str | None = None) -> RefundIntent | None:
    # An old open chat may still hold a full utterance from before request-focus tracking.
    focused = effective_request(text)
    if not focused or refund_choice_needed(focused) or asks_to_cancel_refund(focused):
        return None
    if focused != text:
        label = None
    text = focused
    subject_is_refund = refund_topic(text)
    if not subject_is_refund and OTHER_MOVEMENT.search(text):
        return None
    qualified = any(cue.search(text) for cue in (CONDITION, HESITATION, QUOTED, REPORTED))
    timing = subject_is_refund and timing_question(text)
    returning_money = purchase_money_return(text)
    if subject_is_refund and not timing and asks_about_submission_step(text):
        return 'refund_submission_help'
    if timing:
        if qualified:
            return 'refund_timing'
        if returning_money:
            return 'track_refund' if FILED.search(text) or '查询退款进度' in text else 'refund_timing'
        if PAST.search(text):
            return 'track_refund'
        if GENERAL.search(text) or not re.search(r'时候.{0,5}(?:能)?退回|那笔', text):
            return 'refund_timing'
    if subject_is_refund and directly_requests_refund(text):
        return 'get_refund'
    if returning_money and (FILED.search(text) or re.search(r'还没|一直没|迟迟|没.{0,2}影', text)):
        return 'track_refund'
    if subject_is_refund and HESITATION.search(text) and not re.search(
        r'规则|政策|条件|材料|怎么退|如何退|能不能退|可以退.{0,4}[吗么]', text,
    ):
        return 'clarify_refund'
    money_return = re.search(
        r'(?:钱|款项|款)(?:一直|怎么|到现在|还|都|也|迟迟)*(?:没|未)(?:有)?(?:回来|退回|返还|退到|到账)'
        r'|(?:上次|之前|前几天|昨天|那笔)(?:那笔|申请的|办的)?退(?:的|到|了|款|货)', text,
    )
    if not money_return and re.search(r'之前|已经|提交过|什么时候|啥时候|多久|几时', text):
        money_return = re.search(r'(?:钱|款).{0,12}(?:原路(?:返|退)|返还|返到)', text)
    subject = re.search(
        r'退款|退货|退费|退钱|退换|退掉|退.{0,3}款|钱.{0,6}退|退回来|申请退|'
        r'能.{0,4}退|可以退|可以.{0,6}申请?退|想退|我要退|给我退|退不退|上次退的|七天无理由', text,
    )
    if subject or money_return:
        progress = re.search(
            r'进度|到哪|到[账帐]|打到|到卡|卡上|退到|退了[没吗]|退回.{0,2}[没吗]|'
            r'审核结果|审核.{0,6}结果|结果出来|出来没|结果呢|'
            r'(?:什么时候|几天|何时).{0,7}(?:到[账帐]?|退回)|'
            r'(?:多久).{0,4}(?:到[账帐]|退回|能到)|'
            r'(?:上次|之前|申请过|已经申请).{0,16}(?:怎么[样了]|怎样了|到[账帐]|状态|结果)|'
            r'(?:申请的|那笔).{0,8}退款.{0,8}(?:怎么[样了]|怎样了|状态|结果)|'
            r'还没.{0,5}(退|到)|(?:已经|早就|昨天|之前|刚刚?)申请(?:过|了)?退|'
            r'申请(?:过|了)(?:.{0,3})?退|(?:退[货款]申请|申请退[货款]).{0,5}(?:提交过|已提交|通过了|被拒|驳回|审核中|失败)', text,
        )
        if (money_return or progress) and not (qualified and not PAST.search(text)):
            return 'track_refund'
        if re.search(
            r'规则|政策|条件|步骤|流程|一般|材料|需要什么|怎么退|如何退|怎么申请|如何申请|'
            r'期限|时限|几天.{0,8}退|多久.{0,8}退|多少天.{0,8}退|七天无理由|'
            r'能不能退|可[以否]退|支持.{0,10}退|可以.{0,8}退.{0,2}吗|'
            r'能.{0,4}退.{0,2}[吗么不]|还能退|能退吗', text,
        ):
            return 'check_refund_policy'
    if subject_is_refund and qualified:
        return 'clarify_refund'
    if label in ('check_refund_policy', 'track_refund'):
        return label
    # The optional English classifier can still assist English service requests.
    if label == 'get_refund' and not re.search(r'[\u3400-\u9fff]', text):
        return label
    return None


def refund_for_order(db: Session, owner_id: int, order_id: int, *, open_only: bool = False) -> Ticket | None:
    query = select(Ticket).where(Ticket.owner_id == owner_id, Ticket.order_id == order_id,
                                 Ticket.refund_stage.is_not(None))
    if open_only:
        query = query.where(Ticket.status != 'closed')
    return db.scalar(query.order_by(Ticket.id.desc()).limit(1))
