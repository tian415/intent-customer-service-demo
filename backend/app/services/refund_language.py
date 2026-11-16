"""Speech-act checks for Chinese refund requests; mentioning an action is not consent."""
import re

REFUND = re.compile(r'退款|退费|退钱|退货|退掉|申请退|钱.{0,5}退|款.{0,5}退|(?:给我|要|想|能不能|要不要|该不该)退|退不退|退还是不退')
# Mask quoted commands before looking for an instruction from the customer.
QUOTED = re.compile(r'“[^”]*(?:”|$)|「[^」]*(?:」|$)|『[^』]*(?:』|$)|‘[^’]*(?:’|$)|"[^"]*(?:"|$)')
CONDITION = re.compile(r'如果|假[如设使]|要是|倘若|万一|比如|比方|如若|打个比方|设想|假定|的话')
REPORTED = re.compile(r'建议|推荐|听说|听人说|被告知|让我|叫我|劝我|告诉我|提示|显示|写着|写的是|发来|转发|提到|原话|转述|说[：:]|(?:他|她|人家|卖家|商家|客服|同事|朋友|对方|店员|页面|系统|别人|家人|老[板公婆]|同学).{0,6}(?:说|讲|让|叫|教|提议|问)')
HESITATION = re.compile(
    r'犹豫|纠结|拿不[准定]|没(?:有)?(?:想好|想清楚|决定|确定|拿定)|不确定|不一定|说不准|'
    r'(?:再|先|还[在要]?|容我|让我)(?:考虑|想想|想一想|想一下|琢磨|商量|比较|看看(?=[吧啊呢，,。！？?\s]|$)|缓缓|缓一缓)|'
    r'要不要|退不退|不着急办|不急着办|再决定|先等等|缓一缓|等我.{0,8}(?:决定|确认)|'
    r'还(?:得|想|要|在)(?:再)?(?:想想|考虑|想一想|商量)|在考虑|说不好|没拿定主意|未必|等一等|尚未决定|还没说要|不代表.{0,5}要|暂不决定|还在想|未决定|考虑(?:一下|中|要不要)'
)
TIMESPAN = re.compile(r'多久|多长时间|多少(?:个)?(?:工作日|天|小时)|几(?:个)?(?:工作日|天|小时|星期|礼拜|钟头)|何时|什么时候|啥时候|啥时|时间|时效|多[久长]|当天|当[日天]|隔天|次日|几时|几号|哪天|多会儿|快不快|慢不慢|(?:[一两二三四五六七八九十半0-9]+)(?:个)?(?:工作日|天|小时|月|周|星期|礼拜|钟头)|今天|明天')
ELIGIBILITY_WINDOW = re.compile(r'(?:多久|多少天|几天|多长时间).{0,9}(?:还能|可以|允许|以内|之内|内能|内可|能申请|能退)|(?:签收|收货).{0,8}(?:期限|时限)|退货期限')
PAYMENT_RETURN = re.compile(r'(?:回|退|返|打)(?:回|到|入|进|至){1,2}(?:原(?:支付|付款)|微信|支付宝|余额|银行|卡[里上])')
MONEY = re.compile(
    r'钱(?!包)|货款|款项|价款|金额|银子|(?:[零一二两三四五六七八九十百千万\d]+)(?:块|元)|'
    r'(?:刷(?:卡)?|付(?:款)?|支付|扣(?:掉|走)?|花|掏)(?:过|出去|掉|了)?的?(?:那|这)?'
    r'(?:一?笔|[零一二两三四五六七八九十百千万\d]+(?:来|多)?)'
)
ACCOUNT_DESTINATION = r'(?:我(?:自己)?的?|原来的?|当时的?)?(?:微信|支付宝|银行卡|账户|余额|卡(?:上|里))'
BACK_TO_ACCOUNT = re.compile(r'(?:回|退回|返还)(?:到|进)?' + ACCOUNT_DESTINATION)
CASH_MOVEMENT = re.compile(
    r'回来|回去|回卡|原路|(?:退|返|打|还|回)(?:回|还|到|给|入|至|进|手上|手里|手头)|到[账帐]|'
    r'(?:拿|要|收|领|找)回|(?:见|看)(?:得?着|到)?(?:点|个)?影|(?:没|不见)(?:个|点)?影|'
    r'(?:回|进|落)到?(?:我)?(?:账[上户]|卡[上里]|余额|钱包)|' + BACK_TO_ACCOUNT.pattern
)
# A new subject in the same breath can be a parcel, a promotion or a payment
# to someone else. These do not establish a return of purchase funds.
OUTSIDE_FUNDS = re.compile(r'优惠券|积分|返现|工资|薪水|报销|转账|转给|借给|借的|借出|充值|(?:充|存)(?:进|到|入)|红包')
OTHER_MOVEMENT = re.compile(r'包裹|快递|物流|货物|寄回|送回|钱包.{0,4}(?:丢|落)|' + OUTSIDE_FUNDS.pattern)
FILED = re.compile(
    r'(?:售后|申请|资料|材料|单子).{0,4}(?:交上去|递交了|提交了|提交过|递上去|受理了)|'
    r'(?:退[款货费]|申请).{0,5}(?:审过了|批了|审核通过|受理了)|(?:申请|提交|递交|办)(?:了|过).{0,4}(?:售后|退[款货费])|'
    r'(?:昨天|前天|已经|之前|上次|刚刚).{0,6}(?:申请|提交|递交)(?!的条件)|(?:查[看询]?|催).{0,4}退款进度'
)
SETTLEMENT = re.compile(r'到[账帐卡]|退回|返还|拿到钱|收到钱|拿回钱|到银行|打进|退进|钱.{0,10}(?:回来|能到)|原路|打回|到手|' + PAYMENT_RETURN.pattern)
REVIEW = re.compile(r'审核|审批|审完|审好|批完|批下来|批准|通过|审(?:一[个笔张]|这[个笔张]|那[个笔张])?(?:退款|退货)?申请')
PAST = re.compile(r'(?:已经|早就|之前|上次|那笔|昨天|前天|刚刚|刚才).{0,8}(?:申请|提交|办|退)|(?:提交|申请|审核)(?:过|了)|(?:已经|都)(?:办完|审完)|已经.{0,6}审|退款进度|催.{0,4}退款|还没.{0,5}(?:到账|退回)')
GENERAL = re.compile(r'一般|通常|正常(?:情况)?|大多数|平均|最快|最慢|最迟|申请后|提交后|通过后|审核后|之后|办完后|退的话|还没(?:办|申请|提交)')


def purchase_money_return(text: str) -> bool:
    """Require both a money reference and a return direction in the same local context."""
    previous = ''
    for clause in re.split(r'[，,。；;！？!?\n]', text):
        if CASH_MOVEMENT.search(clause) and not OTHER_MOVEMENT.search(clause):
            if MONEY.search(clause) or (MONEY.search(previous) and not OTHER_MOVEMENT.search(previous)):
                return True
        previous = clause
    return False


def settlement_topic(text: str) -> bool:
    return bool(SETTLEMENT.search(text) or purchase_money_return(text))


def asks_about_submission_step(text: str) -> bool:
    """A question about operating a form, including an unfinished or cancelled draft."""
    control = re.search(r'按钮|入口|表单|页面|界面|弹窗|哪一?步|哪一?个键|'
                        r'点(?:击|进|开|过|了|下|确认|最后)|按(?:下|哪|了|确认)|'
                        r'填(?:写|好|过|到|完|了)|写(?:好|完|了|原因)|打开|关掉|退出来|返回|取消', text)
    submission = re.search(r'提交|递交|交上|交了|交出去|交给|送出|发出去|受理|建单|生效|'
                           r'发起|生成|交上去|正式申请|自动申请|申请成功|办上|办了|客服.{0,4}(?:收到|看到|看见)', text)
    question = re.search(r'算|才会|是不|会不会|有没有|要不要|还[要用需]|哪|怎么|什么|啥|'
                         r'意味|[吗么呢？?]|怕.{0,8}(?:误|已经|自动)', text)
    meaning = re.search(r'(?:什么|啥)意思|意味着什么|有什么用|干[啥嘛]的', text)
    return bool(control and question and (submission or meaning))


# Accept a complete directive, not a verb anywhere inside a description or a question.
OBJECT = r'(?:退(?:款|费|钱|货|掉)|把钱退回(?:来)?)'
ORDER = r'(?:(?:这|那)(?:一)?(?:笔|张|个|单)(?:订单|货款|钱)?|这个商品|订单)'
# An item, an order and its payment can all be the object of the verb 退.
# A command must name that object and express a personal decision or ask for action.
GOODS = r'(?:商品|东西|货品|货|物品|杯子|保温杯|耳机|衣服|鞋子)'
REFERENCE = r'(?:这|那)(?:一)?(?:笔|张|单|个|件|款|只|双|套|台)'
ORDER_OBJECT = rf'(?:{REFERENCE}(?:订单|单子|单|{GOODS})?|订单|{GOODS})'
RETURN_OBJECT = rf'(?:{ORDER_OBJECT}(?:的)?(?:钱|货款|款项)|{ORDER_OBJECT}|货款|钱)'
RETURN_VERB = r'退(?:回(?:来)?|掉|给我)?'
ITEM_RETURN = re.compile(rf'(?:把{RETURN_OBJECT}退|{RETURN_OBJECT}(?:我(?:自己)?(?:决定|想|要))退)')
ITEM_DIRECTIVE = re.compile(
    rf'(?:(?:麻烦|请)?(?:你|您)?(?:帮我|给我|替我)?把{RETURN_OBJECT}{RETURN_VERB}'
    rf'|{ORDER_OBJECT}我(?:自己)?(?:决定(?:要)?|确定(?:要)?|想|要){RETURN_VERB}'
    rf'|我(?:决定(?:要)?|确定(?:要)?|想|要)退(?:掉)?{ORDER_OBJECT})'
    r'(?:了|一下)?(?:吧|谢谢)?'
)
DECLINES_ITEM = re.compile(rf'(?:我)?{ORDER_OBJECT}(?:我)?(?:决定|确定|还是)?'
                           r'(?:不用|不准备|不打算|不想|不)(?:再)?(?:留着?|要)(?:了)?')
PAY_BACK = re.compile(r'(?:麻烦|请)?(?:你|您)?(?:把钱)?退(?:回)?给我(?:吧|一下|了)?')
REQUEST = re.compile(
    r'(?:那就|那|那还是|还是|那我|我这边|我本人|我|就|是|确定|确认|决定|麻烦你|麻烦|劳驾|请|现在|直接|正式|马上|先|要|想|就按|帮我把|替我把|帮我|给我|替我|把|为我|办理|办|走|申请|提交|一下|一个|一笔|'
    + ORDER + r')*+' + OBJECT
    + r'(?:退货退款|退款|申请|流程|手续|吧|了|一下|谢谢|给我|给我吧|就行|' + ORDER + r')*+'
)
COMMIT = re.compile(r'(?:^|但(?:是)?|不过)(?:那)?(?:我(?:自己|本人)?)(?:现在)?(?:决定|确定|确认|坚持|确实要|就是要)|^(?:那就|确定要|确认办理|决定了|想好了)')
SHORT_CONFIRM = re.compile(r'(?:那就|确定|确认|现在就|我决定|请直接|那还是)(?:给我|帮我)?(?:办理|办|申请|提交)(?:吧|了|一下)?[。！!]?')


def directly_requests_refund(text: str) -> bool:
    """A following doubt revokes an instruction. Only a new personal decision lifts a prior caveat."""
    masked = QUOTED.sub('【引述】', text)
    parts = re.split(r'[，,。；;！!？?\n]|(?=但是|不过)', masked)
    qualified = False
    authorized = False
    clauses = [p.strip() for p in parts if p.strip()]
    for index, clause in enumerate(clauses):
        if CONDITION.search(clause) or HESITATION.search(clause) or REPORTED.search(clause) or '【引述】' in clause:
            qualified, authorized = True, False
            continue
        commitment = COMMIT.search(clause)
        if commitment:
            qualified = False
            clause = clause[commitment.start():].removeprefix('但是').removeprefix('不过').removeprefix('但')
        if authorized and not re.fullmatch(r'(?:麻烦|请|谢谢|多谢|帮我|给我|替我|办|办理|处理|一下|了|吧|您|你|尽快|就行)+', clause):
            # A new unrecognised qualification must not inherit an earlier directive.
            authorized = False
        if not qualified and (ITEM_DIRECTIVE.fullmatch(clause) or
                              (index and DECLINES_ITEM.fullmatch(clauses[index - 1]) and PAY_BACK.fullmatch(clause))):
            authorized = True
            continue
        if not qualified and REQUEST.fullmatch(clause):
            # Bare topic names and genuine questions do not start a transaction.
            bare_instruction = re.fullmatch(r'(?:申请|办理|提交)' + OBJECT, clause)
            explains_return = index > 0 and re.search(
                r'不合适|不合身|不想(?:留|保留|要)|坏了|漏水|损坏|有问题|发错|买错', clauses[index - 1],
            )
            authorized = not re.fullmatch(OBJECT, clause) and (not bare_instruction or index == 0 or bool(explains_return))
    return authorized and not text.rstrip().endswith(('?', '？', '吗', '么'))


def timing_question(text: str) -> bool:
    if not TIMESPAN.search(text):
        return False
    # “多久能退” can introduce either a return deadline or a payout duration.
    # An explicit limit governs eligibility; a money destination governs payout.
    if ELIGIBILITY_WINDOW.search(text) and (
        not (purchase_money_return(text) or PAYMENT_RETURN.search(text))
        or re.search(r'以内|之内|内还|内可|内能|期限|时限|过期|最晚.{0,6}(?:申请|提交)', text)
    ):
        return False
    # A date describing a reported event does not itself ask for a deadline.
    if not re.search(r'多[久长少]|几|何时|哪天|啥时|什么时候|时效|时间|多会儿|快不快|慢不慢|[?？吗么]|能否|能不能|会不会|来得及|要等|得等', text):
        return False
    return bool(settlement_topic(text) or REVIEW.search(text) or re.search(
        r'处理|办理|办好|办完|时效|等多久|等几天|退款|退费|退钱', text,
    ))


def refund_topic(text: str) -> bool:
    if purchase_money_return(text):
        return True
    if OTHER_MOVEMENT.search(text):
        return bool(re.search(r'退款|退费|退钱|退货|申请退|要不要退', text))
    return bool(REFUND.search(text) or ITEM_RETURN.search(text) or PAYMENT_RETURN.search(text)
                or (DECLINES_ITEM.search(text) and PAY_BACK.search(text)) or '原路退回' in text)
