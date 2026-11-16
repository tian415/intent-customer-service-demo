"""Phase 5: local orders + finite-state support conversations."""
from app.models import Order
from sqlalchemy.orm import Session
from tests.conftest import login


def _add_orders(app, user_id=1):
    with Session(app.state.engine) as db:
        db.add_all([
            Order(user_id=user_id, order_no='T-1001', product_name='测试耳机', status='shipped', amount_cents=9900, created_at='2026-11-03T00:00:00+00:00', updated_at='2026-11-03T00:00:00+00:00'),
            Order(user_id=user_id, order_no='T-1002', product_name='测试键盘', status='delivered', amount_cents=19900, created_at='2026-11-03T00:00:00+00:00', updated_at='2026-11-03T00:00:00+00:00'),
            Order(user_id=2, order_no='T-OTHER', product_name='别人的订单', status='paid', amount_cents=100, created_at='2026-11-03T00:00:00+00:00', updated_at='2026-11-03T00:00:00+00:00'),
        ])
        db.commit()


def test_orders_are_scoped_to_owner(client, app):
    _add_orders(app)
    login(client, 'customer')
    mine = client.get('/api/orders')
    assert mine.status_code == 200
    numbers = {item['order_no'] for item in mine.json()}
    assert numbers == {'T-1001', 'T-1002'}
    assert client.get('/api/orders/3').status_code == 404
    login(client, 'agent')
    assert client.get('/api/orders').status_code == 403


def test_conversation_pulls_orders_selects_and_handoff(client, app):
    _add_orders(app)
    login(client, 'customer')
    created = client.post('/api/conversations')
    assert created.status_code == 201, created.text
    body = created.json()
    assert body['status'] == 'active'
    assert body['status_label'] == '接待中'
    assert body['stage'] == 'greeting'
    assert body['quick_replies']
    assert {o['order_no'] for o in body['orders']} == {'T-1001', 'T-1002'}
    assert any('订单卡片' in m['body'] or '暂时没有查到' in m['body'] for m in body['messages'] if m['role'] == 'system')
    assert any(m['role'] == 'assistant' and '售后助手' in m['body'] for m in body['messages'])
    version = body['version']

    asked = client.post(f"/api/conversations/{body['id']}/messages", json={'version': version, 'body': '我想查一下订单物流进度'})
    assert asked.status_code == 200, asked.text
    asked_body = asked.json()
    assert asked_body['status'] == 'waiting_order'
    assert asked_body['status_label'] == '待选择订单'
    assert asked_body['stage'] == 'await_order'
    assert any('订单卡片' in m['body'] or '点' in m['body'] for m in asked_body['messages'] if m['role'] == 'assistant')
    assert '我先选一笔订单' not in asked_body['quick_replies']
    version = asked_body['version']
    before_count = len(asked_body['messages'])
    spam = client.post(
        f"/api/conversations/{body['id']}/messages",
        json={'version': version, 'body': '我先选一笔订单'},
    )
    assert spam.status_code == 200, spam.text
    assert len(spam.json()['messages']) == before_count
    version = spam.json()['version']

    selected = client.post(
        f"/api/conversations/{body['id']}/actions",
        json={'version': version, 'action': 'select_order', 'order_id': asked_body['orders'][0]['id']},
    )
    assert selected.status_code == 200, selected.text
    selected_body = selected.json()
    assert selected_body['selected_order']['order_no'] in {'T-1001', 'T-1002'}
    assert selected_body['status'] == 'active'
    assert selected_body['stage'] == 'order_bound'
    assert any(
        m['role'] == 'assistant' and (
            '已识别' in m['body'] or '订单' in m['body'] or '人工' in m['body'] or '物流' in m['body']
        )
        for m in selected_body['messages']
    )
    version = selected_body['version']

    conflict = client.post(f"/api/conversations/{body['id']}/messages", json={'version': 1, 'body': '过期版本'})
    assert conflict.status_code == 409

    handoff = client.post(f"/api/conversations/{body['id']}/actions", json={'version': version, 'action': 'handoff'})
    assert handoff.status_code == 200, handoff.text
    result = handoff.json()
    assert result['status'] == 'handed_off'
    assert result['status_label'] == '已转人工'
    assert result['ticket_id']
    assert result['quick_replies'] == []
    ticket = client.get(f"/api/tickets/{result['ticket_id']}")
    assert ticket.status_code == 200
    payload = ticket.json()
    assert '智能客服多轮会话' in payload['description']
    assert payload['order_id'] == selected_body['selected_order']['id']
    assert payload['order_no'] == selected_body['selected_order']['order_no']
    orders = client.get('/api/orders')
    assert orders.status_code == 200
    linked = next(item for item in orders.json() if item['id'] == payload['order_id'])
    assert any(item['id'] == payload['id'] for item in linked['aftersales'])
    assert client.post(f"/api/conversations/{body['id']}/messages", json={'version': result['version'], 'body': '再问一次'}).status_code == 409


def test_handoff_requires_user_utterance(client, app):
    _add_orders(app)
    login(client, 'customer')
    created = client.post('/api/conversations').json()
    blocked = client.post(f"/api/conversations/{created['id']}/actions", json={'version': created['version'], 'action': 'handoff'})
    assert blocked.status_code == 422


def test_conversation_resumes_open_chat_unless_forced(client, app):
    _add_orders(app)
    login(client, 'customer')
    first = client.post('/api/conversations', json={}).json()
    again = client.post('/api/conversations', json={}).json()
    assert again['id'] == first['id']
    fresh = client.post('/api/conversations', json={'force_new': True}).json()
    assert fresh['id'] != first['id']


def test_handoff_copy_points_to_orders_hub(client, app):
    _add_orders(app)
    login(client, 'customer')
    created = client.post('/api/conversations', json={'force_new': True}).json()
    asked = client.post(
        f"/api/conversations/{created['id']}/messages",
        json={'version': created['version'], 'body': '退款'},
    ).json()
    selected = client.post(
        f"/api/conversations/{asked['id']}/actions",
        json={'version': asked['version'], 'action': 'select_order', 'order_id': asked['orders'][0]['id']},
    ).json()
    handoff = client.post(
        f"/api/conversations/{selected['id']}/actions",
        json={'version': selected['version'], 'action': 'handoff'},
    ).json()
    last = handoff['messages'][-1]['body']
    assert '订单与售后' in last
    assert '我的问题' not in last


def test_refund_intent_leads_to_handoff_next_step(client, app):
    _add_orders(app)
    login(client, 'customer')
    created = client.post('/api/conversations', json={'force_new': True}).json()
    order_id = created['orders'][0]['id']
    bound = client.post(
        f"/api/conversations/{created['id']}/actions",
        json={'version': created['version'], 'action': 'select_order', 'order_id': order_id},
    ).json()
    asked = client.post(
        f"/api/conversations/{bound['id']}/messages",
        json={'version': bound['version'], 'body': '我想退款'},
    ).json()
    last = asked['messages'][-1]['body']
    assert asked['service_intent'] == 'get_refund' and asked['can_submit_refund']
    assert '填写原因' in last and '审核' in last
    assert 'DEMO：如何咨询退款' not in last
    assert '演示知识' not in last
    assert asked['needs_manual'] is True
    assert asked['quick_replies'][0] == '转人工处理'


def _send(client, chat, body):
    response = client.post(f"/api/conversations/{chat['id']}/messages",
                           json={'version': chat['version'], 'body': body})
    assert response.status_code == 200, response.text
    return response.json()


def _act(client, chat, action, **kwargs):
    response = client.post(f"/api/conversations/{chat['id']}/actions",
                           json={'version': chat['version'], 'action': action, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def _refund_category(app):
    from app.models import Category, FAQ
    with Session(app.state.engine) as db:
        db.add(Category(id=2, name='退款咨询', keywords='退款,退费', group_id=1))
        db.flush()
        db.add(FAQ(question='退款政策是什么', keywords='退款', answer='测试退款政策说明', category_id=2))
        db.get(Order, 1).status = 'refunding'
        db.commit()


def test_correction_handoff_uses_latest_request_and_preserves_originals(client, app):
    from app.models import Category
    _add_orders(app)
    _refund_category(app)
    login(client)
    chat = client.post('/api/conversations').json()
    lines = ['查物流', '快递没有到', '不是催单，我要退款', '谢谢']
    for line in lines:
        last_version = chat['version']
        chat = _send(client, chat, line)
        assert chat['version'] > last_version
    assert chat['next_action'] == 'ask_order' and chat['current_request'] == '我要退款'
    assert [m['body'] for m in chat['messages'] if m['role'] == 'user'] == lines
    with Session(app.state.engine) as db:
        # Re-running prediction after this edit would lose the original routing.
        db.get(Category, 2).keywords = '换货'
        db.commit()
    bound = _act(client, chat, 'select_order', order_id=1)
    assert bound['next_action'] == 'handoff'
    result = _act(client, bound, 'handoff')
    assert result['next_action'] is None
    assert client.post(f"/api/conversations/{chat['id']}/actions",
                       json={'version': bound['version'], 'action': 'handoff'}).status_code == 409
    tickets = client.get('/api/tickets?scope=mine').json()
    assert tickets['total'] == 1
    path = f"/api/tickets/{result['ticket_id']}"
    detail = client.get(path).json()
    assert (detail['title'], detail['category_id'], detail['order_id']) == ('我要退款', 2, 1)
    assert 'customer_statements' not in detail
    login(client, 'agent')
    assert client.get(path).json()['customer_statements'] == lines
    login(client, 'other')
    assert client.get(path).status_code == 404
    assert client.get('/api/tickets?scope=mine').json()['total'] == 0


def test_refunding_order_does_not_turn_shipping_or_policy_into_refund_request(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    chat = client.post('/api/conversations').json()
    policy = _send(client, chat, '退款政策是什么')
    assert policy['next_action'] == 'answer'
    assert '测试退款政策说明' in policy['messages'][-1]['body']
    chat = _act(client, policy, 'select_order', order_id=1)
    chat = _send(client, chat, '查物流')
    assert chat['next_action'] == 'answer' and '没有可核实' in chat['messages'][-1]['body']
    result = _act(client, chat, 'handoff')
    ticket = client.get(f"/api/tickets/{result['ticket_id']}").json()
    assert ticket['category_id'] is None and ticket['status'] == 'pending'
    assert ticket['order_no'] == 'T-1001'


def test_no_order_handoff_remains_findable_and_abandoned_chat_stays_closed(client):
    login(client)
    old = client.post('/api/conversations').json()
    new = client.post('/api/conversations', json={'force_new': True}).json()
    chat = _send(client, new, '查物流')
    assert chat['status'] == 'active' and chat['next_action'] == 'handoff' and not chat['orders']
    assert '没有' in chat['messages'][-1]['body'] or '未查到' in chat['messages'][-1]['body']
    result = _act(client, chat, 'handoff')
    assert client.get(f"/api/conversations/{old['id']}").json()['status'] == 'closed'
    assert client.post('/api/conversations').json()['id'] > new['id']
    found = client.get('/api/tickets?scope=mine').json()['items'][0]
    assert found['id'] == result['ticket_id'] and found['order_id'] is None


def test_topic_switch_and_withdrawal_leave_waiting_state(client, app):
    _add_orders(app)
    login(client)
    chat = _send(client, client.post('/api/conversations').json(), '查物流')
    assert chat['status'] == 'waiting_order'
    chat = _send(client, chat, '我不想查物流了，忘记密码怎么办')
    assert chat['next_action'] == 'answer' and chat['status'] == 'active'
    assert '测试知识库答案' in chat['messages'][-1]['body']
    chat = _send(client, chat, '我不要重设密码了')
    assert chat['current_request'] is None and chat['next_action'] == 'clarify'
    refused = client.post(f"/api/conversations/{chat['id']}/actions",
                          json={'version': chat['version'], 'action': 'handoff'})
    assert refused.status_code == 422
    chat = _send(client, chat, '我忘了登录密码')
    assert _act(client, chat, 'close')['status'] == 'closed'


def test_pre_migration_open_chat_recovers_request_on_order_selection(client, app):
    from app.models import Conversation
    _add_orders(app)
    login(client)
    chat = _send(client, client.post('/api/conversations').json(), '查物流')
    with Session(app.state.engine) as db:
        old = db.get(Conversation, chat['id'])
        old.current_request = old.next_action = old.intent_category_id = None
        db.commit()
    old = client.get(f"/api/conversations/{chat['id']}").json()
    assert old['current_request'] == '查物流'
    bound = _act(client, old, 'select_order', order_id=1)
    assert bound['current_request'] == '查物流' and bound['next_action'] == 'answer'


def test_transfer_controls_preserve_issue_and_require_confirmation(client, app):
    from app.models import Conversation
    _add_orders(app)
    login(client)
    start = client.post('/api/conversations').json()
    empty = _send(client, start, '请帮我转人工客服。')
    assert not empty['show_handoff_preview'] and empty['current_request'] is None
    chat = _send(client, empty, '忘记登录密码了')
    decline = _send(client, chat, '先不用转人工了')
    assert not decline['show_handoff_preview'] and decline['current_request'] == chat['current_request']
    # Older active sessions could have mistakenly stored the transfer command as the issue.
    with Session(app.state.engine) as db:
        old = db.get(Conversation, chat['id'])
        old.current_request = '帮我转人工'
        old.intent_category_id = None
        db.commit()
    restored = client.get(f"/api/conversations/{chat['id']}").json()
    assert restored['current_request'] == '忘记登录密码了'
    ask = _send(client, restored, '帮我转人工')
    assert ask['show_handoff_preview'] and ask['current_request'] == '忘记登录密码了'
    assert client.get('/api/tickets?scope=mine').json()['total'] == 0
    assert 'show_handoff_preview' not in client.get(f"/api/conversations/{chat['id']}").json()
    done = _act(client, ask, 'handoff')
    ticket = client.get(f"/api/tickets/{done['ticket_id']}").json()
    assert ticket['category_id'] == 1 and ticket['title'] == '忘记登录密码了'
    new = _send(client, client.post('/api/conversations').json(), '人工客服没有回复我')
    assert new['current_request'] == '人工客服没有回复我' and not new['show_handoff_preview']


def test_refund_review_owner_deduplication_and_visible_result(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    chat = _send(client, client.post('/api/conversations').json(), '这件商品能退吗')
    assert chat['service_intent'] == 'check_refund_policy' and not chat['selected_order_id']
    chat = _send(client, chat, '我想申请退款')
    chat = _act(client, chat, 'select_order', order_id=1)
    action_url = f"/api/conversations/{chat['id']}/actions"
    assert client.post(action_url, json={'version':chat['version'], 'action':'submit_refund'}).status_code == 422
    first = _act(client, chat, 'submit_refund', reason='插口损坏')
    original = first['ticket_id']
    path = f'/api/tickets/{original}'
    assert client.get(path).json()['refund_stage'] == 'requested'
    assert '插口损坏' in client.get(path).json()['description']
    chat = _send(client, client.post('/api/conversations').json(), '帮我退钱')
    chat = _act(client, chat, 'select_order', order_id=1)
    assert chat['related_refund_id'] == original and not chat['can_submit_refund']
    assert _act(client, chat, 'handoff')['ticket_id'] == original
    assert client.get('/api/tickets').json()['total'] == 1
    login(client, 'other')
    assert client.get(path).status_code == 404
    assert client.post('/api/conversations').json()['recent_cases'] == []
    login(client, 'agent')
    old = client.get(path).json()
    accepted = client.post(path+'/actions', json={'version':old['version'], 'action':'accept'}).json()
    reply = client.post(path+'/messages', json={'version':accepted['version'], 'body':'已登记，正在核查'}).json()
    assert reply['status'] == 'processing'
    assert client.post(path+'/actions', json={'version':reply['version'],'action':'resolve'}).status_code == 422
    result = client.post(path+'/actions', json={'version':reply['version'],'action':'resolve',
                         'refund_decision':'declined','reason':'请补充故障说明以便复核'}).json()
    assert result['status'] == 'resolved' and result['refund_stage'] == 'declined'
    login(client)
    assert '未通过审核' in client.get(path).json()['messages'][-1]['body']
    chat = _send(client, client.post('/api/conversations').json(), '钱什么时候能退回来')
    chat = _act(client, chat, 'select_order', order_id=1)
    assert chat['service_intent'] == 'track_refund' and '未通过审核' in chat['messages'][-1]['body']
    chat = _act(client, chat, 'select_order', order_id=2)
    assert chat['related_refund_id'] is None and '未查到' in chat['messages'][-1]['body']
    detail = client.get(path).json()
    assert detail['order']['order_no'] == 'T-1001'
    assert 'amount_display' in detail['order'] and 'status_label' in detail['order']
    continued = client.post(path+'/actions', json={'version':detail['version'], 'action':'follow_up',
                            'reason':'补充：插口无法接触，换线后也一样'}).json()
    assert continued['id'] == original and continued['refund_stage'] == 'requested'
    assert continued['status'] == 'assigned' and continued['needs_staff_reply']
    login(client, 'other')
    assert client.get(path).status_code == 404


def test_headphone_check_can_finish_or_escalate_with_symptom(client):
    login(client)
    for response in ('已恢复声音', '仍然没声音'):
        chat = _send(client, client.post('/api/conversations', json={'force_new':True}).json(), '耳机左侧没有声音')
        assert response in chat['quick_replies'] and '声道平衡' in chat['messages'][-1]['body']
        chat = _send(client, chat, response)
        if response == '已恢复声音':
            assert chat['status'] == 'closed' and not chat['ticket_id']
        else:
            handoff = _act(client, chat, 'handoff')
            ticket = client.get(f"/api/tickets/{handoff['ticket_id']}").json()
            assert ticket['title'] == '耳机左侧没有声音' and response in ticket['description']


def test_negated_or_ambiguous_refund_never_allows_submission(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    for line in ('别给我退款', '请不要给我退款', '暂时别退钱', '我并不想申请退款', '我想退货或者换货，哪个好'):
        chat = client.post('/api/conversations', json={'force_new': True}).json()
        chat = _act(client, chat, 'select_order', order_id=1)
        chat = _send(client, chat, '我要退款')
        assert chat['can_submit_refund']
        chat = _send(client, chat, line)
        assert not chat['can_submit_refund'] and chat['service_intent'] is None
        response = client.post(f"/api/conversations/{chat['id']}/actions", json={
            'version': chat['version'], 'action': 'submit_refund', 'reason': '不应创建'})
        assert response.status_code == 422
        assert client.get('/api/tickets').json()['total'] == 0


def test_refund_followup_keeps_context_but_explicit_shipping_focus_replaces_it(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    chat = _act(client, client.post('/api/conversations').json(), 'select_order', order_id=1)
    for line in ('查退款进度', '那什么时候能到账'):
        chat = _send(client, chat, line)
        assert chat['service_intent'] == 'track_refund' and '到账记录' in chat['messages'][-1]['body']
    chat = _send(client, chat, '这单在退款，但我现在问的是快递发货了吗')
    assert chat['service_intent'] is None and '当前记录没有可核实的发货进度' in chat['messages'][-1]['body']
    chat = _send(client, chat, '能保证明天送到吗')
    assert '无法保证具体送达日期' in chat['messages'][-1]['body']
    chat = _send(client, chat, '查退款进度')
    chat = _send(client, chat, '耳机维修需要多久')
    assert chat['service_intent'] is None and chat['current_request'] == '耳机维修需要多久'


def test_account_clarification_does_not_turn_verification_failure_into_password_reset(client, app):
    _add_orders(app)
    login(client)
    chat = _act(client, client.post('/api/conversations').json(), 'select_order', order_id=1)
    chat = _send(client, chat, '我的帐号进不去了')
    assert chat['selected_order_id'] is None and chat['next_action'] == 'clarify'
    chat = _send(client, chat, '不是忘记密码，是一直收不到验证码')
    assert chat['next_action'] == 'handoff'
    assert '重设' not in chat['messages'][-1]['body']
    ticket = _act(client, chat, 'handoff')
    detail = client.get(f"/api/tickets/{ticket['ticket_id']}").json()
    assert '验证码' in detail['title'] and '我的帐号进不去了' in detail['description']


def test_headphone_free_text_feedback_preserves_symptom_and_never_closes_on_failure(client):
    login(client)
    for line in ('照你说的试过了，还是听不到', '还没好，声音没有恢复'):
        chat = _send(client, client.post('/api/conversations', json={'force_new': True}).json(), '耳机左侧没声')
        chat = _send(client, chat, line)
        assert chat['next_action'] == 'handoff' and chat['status'] == 'active'
        result = _act(client, chat, 'handoff')
        detail = client.get(f"/api/tickets/{result['ticket_id']}").json()
        assert detail['title'] == '耳机左侧没声' and line in detail['description']
    chat = _send(client, client.post('/api/conversations', json={'force_new': True}).json(), '耳机左侧没声')
    chat = _send(client, chat, '好了，现在能听到了')
    assert chat['status'] == 'closed' and chat['ticket_id'] is None


def test_r19_self_built_coverage_phrases(client, app):
    """Phrases introduced by the self-built Chinese coverage set stay within product bounds."""
    _add_orders(app)
    _refund_category(app)
    login(client)

    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(), 'select_order', order_id=1)
    chat = _send(client, chat, '这单有没有发出去')
    assert chat['next_action'] == 'answer' and '发货' in chat['messages'][-1]['body']

    chat = _send(client, client.post('/api/conversations', json={'force_new': True}).json(), '七天无理由这里支持吗')
    assert chat['service_intent'] == 'check_refund_policy' and chat['next_action'] == 'answer'

    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(), 'select_order', order_id=1)
    chat = _send(client, chat, '请替我提交退款')
    assert chat['service_intent'] == 'get_refund' and chat['can_submit_refund']
    chat = _send(client, chat, '好的谢谢')
    assert chat['service_intent'] == 'get_refund' and chat['can_submit_refund']

    chat = _send(client, client.post('/api/conversations', json={'force_new': True}).json(), '我不是忘密码，验证码一直收不到')
    assert chat['next_action'] in ('clarify', 'handoff')
    assert '重设本系统账号密码' not in chat['messages'][-1]['body']

    chat = _send(client, client.post('/api/conversations', json={'force_new': True}).json(), '耳机左边没声音')
    chat = _send(client, chat, '算了先看物流')
    assert chat['current_request'] and '物流' in chat['current_request']


def test_current_request_scopes_refund_permission_to_its_own_clause(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    for text, expected, answer in (
        ('我没有要退货，刚才点错了，帮我查一下订单状态。', None, '订单'),
        ('我没要求退款，我就是想问包裹到哪儿了。', None, '订单'),
        ('钱还没回来，能看看上次那笔退到哪一步了吗？', 'track_refund', '退款审核单'),
        ('先别帮我退钱，我只是问问签收后几天还能退。', 'check_refund_policy', '期限'),
        ('我想退款，改为查物流', None, '订单'),
    ):
        chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                    'select_order', order_id=1)
        chat = _send(client, chat, '帮我办理退款')
        assert chat['can_submit_refund']
        chat = _send(client, chat, text)
        assert chat['service_intent'] == expected and answer in chat['messages'][-1]['body']
        assert not chat['can_submit_refund']
        assert client.post(f"/api/conversations/{chat['id']}/actions", json={
            'version': chat['version'], 'action': 'submit_refund', 'reason': '当前不是申请',
        }).status_code == 422
    assert client.get('/api/tickets').json()['total'] == 0


def test_refund_mentions_do_not_authorize_writes_or_refund_handoffs(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    for text in ('客服建议我申请退款，我还没决定。', '假设要办理退款，我想先考虑一下',
                 '他说：“请帮我退款。”', '我想退款，不过我还得想想', '朋友在群里转发了退款申请'):
        chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                    'select_order', order_id=1)
        chat = _send(client, chat, text)
        assert chat['next_action'] == 'clarify' and not chat['can_submit_refund'], text
        assert client.post(f"/api/conversations/{chat['id']}/actions", json={
            'version': chat['version'], 'action': 'submit_refund', 'reason': '只是在咨询',
        }).status_code == 422
        assert not client.get(f"/api/conversations/{chat['id']}").json()['can_submit_refund']
        ticket = _act(client, chat, 'handoff')
        assert client.get(f"/api/tickets/{ticket['ticket_id']}").json()['refund_stage'] is None


def test_refund_timing_distinguishes_general_policy_and_real_progress(client, app):
    _add_orders(app)
    _refund_category(app)
    login(client)
    chat = client.post('/api/conversations', json={'force_new': True}).json()
    for text, contains in (('如果我申请退款，大概几天能到账？', '确切的到账时间'),
                           ('退款申请一般审核多久', '固定审核时长')):
        chat = _send(client, chat, text)
        assert chat['service_intent'] == 'refund_timing' and chat['next_action'] == 'answer'
        assert contains in chat['messages'][-1]['body']
        assert '未查到' not in chat['messages'][-1]['body'] and not chat['can_submit_refund']
    chat = _act(client, chat, 'select_order', order_id=1)
    chat = _send(client, chat, '我昨天提交过退款，还需要多久能到账？')
    assert chat['service_intent'] == 'track_refund'
    assert '未查到' in chat['messages'][-1]['body'] and '确切的到账时间' in chat['messages'][-1]['body']
    with Session(app.state.engine) as db:
        from app.models import FAQ
        db.add(FAQ(question='退款审核要多久', answer='测试规则：审核窗口为两个工作日。',
                   keywords='退款审核', active=True))
        db.commit()
    chat = _send(client, chat, '退款审核要多久')
    assert chat['messages'][-1]['body'] == '测试规则：审核窗口为两个工作日。'


def test_hesitation_replaces_previous_application_until_explicit_decision(client, app):
    _add_orders(app)
    login(client)
    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                'select_order', order_id=1)
    chat = _send(client, chat, '我想办理退款')
    assert chat['can_submit_refund']
    for text in ('补充一下，我还要考虑', '好的'):
        chat = _send(client, chat, text)
        assert chat['next_action'] == 'clarify' and not chat['can_submit_refund']
    chat = _send(client, chat, '那就办吧')
    assert chat['can_submit_refund']
    chat = _send(client, chat, '客服建议退款，但我决定了，请现在给我办理退款')
    assert chat['can_submit_refund']


def test_payment_return_question_does_not_authorize_application(client, app):
    _add_orders(app)
    login(client)
    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                'select_order', order_id=1)
    chat = _send(client, chat, '请给我办理退款')
    assert chat['can_submit_refund']
    chat = _send(client, chat, '我刷的那笔钱啥时候回来')
    assert chat['service_intent'] == 'refund_timing' and not chat['can_submit_refund']
    assert '确切的到账时间' in chat['messages'][-1]['body'] and '未查到' not in chat['messages'][-1]['body']
    assert client.post(f"/api/conversations/{chat['id']}/actions", json={
        'version': chat['version'], 'action': 'submit_refund', 'reason': '我只是问时间',
    }).status_code == 422
    chat = _send(client, chat, '我发出去的红包多久退回来')
    assert chat['service_intent'] is None and '对应的支付或账户记录' in chat['messages'][-1]['body']
    chat = _send(client, chat, '我用红包买的包裹到哪儿了')
    assert '订单' in chat['messages'][-1]['body'] and '账户记录' not in chat['messages'][-1]['body']
    chat = _send(client, chat, '我这五十块多久能退到卡里')
    assert chat['service_intent'] == 'refund_timing' and chat['next_action'] == 'answer'
    chat = _send(client, chat, '收货以后多少天以内还能申请退货')
    assert chat['service_intent'] == 'check_refund_policy' and '期限' in chat['messages'][-1]['body']


def test_customer_decides_on_an_item_return_then_stops(client, app):
    _add_orders(app)
    login(client)
    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                'select_order', order_id=1)
    chat = _send(client, chat, '朋友劝我把这件商品退了，我还没想好')
    assert chat['service_intent'] == 'clarify_refund' and not chat['can_submit_refund']
    chat = _send(client, chat, '想好了，这件商品我决定退掉，帮我办理吧')
    assert chat['can_submit_refund']
    chat = _send(client, chat, '请把这笔订单的钱退给我，先别操作')
    assert not chat['can_submit_refund']
    assert client.post(f"/api/conversations/{chat['id']}/actions", json={
        'version': chat['version'], 'action': 'submit_refund', 'reason': '意愿已撤回',
    }).status_code == 422
    assert client.get('/api/tickets').json()['total'] == 0


def test_asking_about_refund_form_clears_previous_application_intent(client, app):
    _add_orders(app)
    login(client)
    chat = _act(client, client.post('/api/conversations', json={'force_new': True}).json(),
                'select_order', order_id=1)
    chat = _send(client, chat, '我想申请退款')
    assert chat['can_submit_refund']
    chat = _send(client, chat, '我把原因写完就算递交了么？')
    assert chat['service_intent'] == 'refund_submission_help'
    assert chat['next_action'] == 'answer' and not chat['can_submit_refund']
    assert '确认提交申请' in chat['messages'][-1]['body']
    assert client.post(f"/api/conversations/{chat['id']}/actions", json={
        'version': chat['version'], 'action': 'submit_refund', 'reason': '当前正在询问操作步骤',
    }).status_code == 422
    assert client.get('/api/tickets').json()['total'] == 0
    chat = _send(client, chat, '确认申请以后要多久才能到账？')
    assert '到账时间' in chat['messages'][-1]['body'] and not chat['can_submit_refund']
