"""API invariants using isolated synthetic engineering records."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Category, Group, User
from conftest import login


def create(client, title='密码问题', description='忘记登录密码'):
    response = client.post('/api/tickets', json={'title': title, 'description': description})
    assert response.status_code == 201, response.text
    return response.json()


def action(client, ticket, verb, expected=200, **fields):
    response = client.post(f"/api/tickets/{ticket['id']}/actions", json={
        'version': ticket['version'], 'action': verb, **fields})
    assert response.status_code == expected, response.text
    return response.json()


def test_owner_scope_applies_before_search_count_pagination_and_detail(client):
    login(client)
    own = create(client, '共同标题 A')
    login(client, 'other')
    foreign = create(client, '共同标题 B')
    for scope in ('all', 'mine', 'queue'):
        result = client.get('/api/tickets', params={'q': '共同标题', 'scope': scope, 'page_size': 1}).json()
        assert result['total'] == 1
        assert [row['id'] for row in result['items']] == [foreign['id']]
    assert client.get(f"/api/tickets/{own['id']}").status_code == 404
    assert client.get('/api/tickets', params={'q': '共同标题 A'}).json()['total'] == 0
    assert client.get('/api/tickets', params={'status': 'invented'}).status_code == 422
    assert client.get('/api/tickets', params={'scope': 'unrestricted'}).status_code == 422
    assert client.get('/api/tickets', params={'page': 0}).status_code == 422


def test_internal_notes_and_classification_reason_do_not_leak(client):
    login(client)
    ticket = create(client)
    assert client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': '普通用户伪装内部', 'internal': True}).status_code == 403
    login(client, 'agent')
    note = client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': 'INTERNAL_SECRET_MARKER', 'internal': True})
    assert note.status_code == 200
    ticket = note.json()
    assert len(ticket['messages']) == 1 and ticket['messages'][0]['internal']
    ticket = action(client, ticket, 'classify', category_id=1, reason='CLASSIFICATION_SECRET_MARKER')
    assert any(event['kind'] == 'classification' for event in ticket['events'])
    reply = client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': '公开进展', 'internal': False})
    assert reply.status_code == 200
    login(client)
    public = client.get(f"/api/tickets/{ticket['id']}")
    assert 'INTERNAL_SECRET_MARKER' not in public.text
    assert 'CLASSIFICATION_SECRET_MARKER' not in public.text
    assert [message['body'] for message in public.json()['messages']] == ['公开进展']
    assert all(event['kind'] not in ('internal_note', 'classification') for event in public.json()['events'])


def test_role_status_guards_and_stale_message_do_not_change_state(client):
    login(client)
    ticket = create(client)
    for verb in ('accept', 'resolve', 'transfer', 'classify'):
        action(client, ticket, verb, expected=403, category_id=1, assignee_id=4, reason='尝试越权')
    for verb in ('close', 'reopen'):
        action(client, ticket, verb, expected=409)
    assert client.post('/api/tickets', json={'title': '越权', 'description': '测试', 'status': 'closed'}).status_code == 422
    login(client, 'agent')
    action(client, ticket, 'resolve', expected=409)
    processing = action(client, ticket, 'accept')
    action(client, ticket, 'accept', expected=409)
    stale = client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': '过期回复'})
    assert stale.status_code == 409
    assert client.get(f"/api/tickets/{ticket['id']}").json()['messages'] == []
    action(client, processing, 'resolve', expected=422)
    action(client, processing, 'close', expected=403)
    assert client.post('/api/tickets', json={'title': '错误角色', 'description': '客服提交'}).status_code == 403


def test_full_lifecycle_transfer_confirm_and_reopen(client):
    login(client)
    ticket = create(client)
    login(client, 'agent')
    ticket = action(client, ticket, 'accept')
    assert ticket['status'] == 'processing'
    action(client, ticket, 'transfer', expected=422, assignee_id=5, reason='跨组禁止')
    ticket = action(client, ticket, 'transfer', assignee_id=4, reason='同组协作')
    assert ticket['status'] == 'assigned' and ticket['assignee_id'] == 4
    action(client, ticket, 'resolve', expected=403)
    login(client, 'agent2')
    ticket = action(client, ticket, 'accept')
    ticket = action(client, ticket, 'resolve', reason='已恢复账号访问，请重新登录')
    assert ticket['status'] == 'resolved'
    action(client, ticket, 'transfer', expected=409, assignee_id=3, reason='已解决不可转派')
    assert client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': '已解决不可回复'}).status_code == 409
    login(client)
    ticket = action(client, ticket, 'reopen')
    assert ticket['status'] == 'assigned' and ticket['assignee_id'] == 4
    login(client, 'agent2')
    ticket = action(client, ticket, 'accept')
    ticket = action(client, ticket, 'resolve', reason='已恢复账号访问，请重新登录')
    login(client)
    ticket = action(client, ticket, 'close')
    assert ticket['status'] == 'closed'
    ticket = action(client, ticket, 'reopen')
    assert ticket['status'] == 'assigned' and ticket['assignee_id'] == 4


def test_cross_group_access_and_nonhandler_action(client):
    login(client)
    ticket = create(client)
    login(client, 'billing')
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404
    assert client.get('/api/tickets').json()['total'] == 0
    action(client, ticket, 'accept', expected=404)
    login(client, 'agent2')
    # Same group may view assigned queue but cannot act for another assignee.
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 200
    action(client, ticket, 'accept', expected=409)
    action(client, ticket, 'transfer', expected=403, assignee_id=4, reason='非承办人')
    assert client.post(f"/api/tickets/{ticket['id']}/messages", json={
        'version': ticket['version'], 'body': '非承办人回复'}).status_code == 403
    login(client, 'agent')
    ticket = action(client, ticket, 'accept')
    login(client, 'agent2')
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404


def test_least_load_manual_queue_and_processing_classification(client, app):
    login(client)
    first, second, third = create(client), create(client), create(client)
    assert [t['assignee_id'] for t in (first, second, third)] == [3, 4, 3]
    unknown = create(client, '未知业务', '咨询新业务')
    assert unknown['category_id'] is None and unknown['status'] == 'pending' and unknown['needs_manual']
    login(client, 'agent')
    action(client, unknown, 'classify', expected=422, category_id=1)
    unknown = action(client, unknown, 'classify', category_id=1, reason='人工识别账户问题')
    assert not unknown['needs_manual'] and unknown['category_id'] == 1
    assert any(e['kind'] == 'classification' and '人工识别' in e['detail'] for e in unknown['events'])
    first = action(client, first, 'accept')
    with Session(app.state.engine) as db:
        db.add(Category(id=2, name='账务问题', keywords='退款', active=True, group_id=2))
        db.commit()
    first = action(client, first, 'classify', category_id=2, reason='处理中发现账务问题')
    assert first['status'] == 'processing' and first['assignee_id'] == 3 and first['group_id'] == 2
    first = action(client, first, 'transfer', assignee_id=5, reason='转给账务组')
    assert first['assignee_id'] == 5 and first['status'] == 'assigned'


def test_category_group_with_no_available_agent_remains_queued(client, app):
    with Session(app.state.engine) as db:
        db.add(Group(id=3, name='无人组'))
        db.flush()
        db.add(Category(id=2, name='新业务', keywords='新业务', active=True, group_id=3))
        db.commit()
    login(client)
    ticket = create(client, '新业务问题', '新业务咨询')
    assert ticket['status'] == 'pending' and ticket['assignee_id'] is None and ticket['group_id'] == 3
    login(client, 'agent')
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 404
    login(client, 'admin')
    assert client.get(f"/api/tickets/{ticket['id']}").status_code == 200


def test_simultaneous_accept_commits_only_one_assignment(client, app):
    login(client)
    ticket = create(client, '人工分类请求', '无关键词业务')
    assert ticket['status'] == 'pending' and ticket['assignee_id'] is None
    first = TestClient(app, headers={'X-Requested-With': 'ticket-ui'})
    second = TestClient(app, headers={'X-Requested-With': 'ticket-ui'})
    try:
        login(first, 'agent')
        # Independent sessions for one agent retain read access after the win;
        # the losing request must report version conflict, not lose visibility.
        login(second, 'agent')
        barrier = Barrier(2)
        def accept(worker):
            barrier.wait(timeout=5)
            return worker.post(f"/api/tickets/{ticket['id']}/actions", json={
                'version': ticket['version'], 'action': 'accept'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(accept, (first, second)))
        assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
        winner = next(r.json() for r in responses if r.status_code == 200)
        login(client, 'admin')
        persisted = client.get(f"/api/tickets/{ticket['id']}").json()
        assert persisted['assignee_id'] == winner['assignee_id']
        assert persisted['version'] == ticket['version'] + 1
        assert len([e for e in persisted['events'] if e['kind'] == 'status' and e['detail'].startswith('accept:')]) == 1
    finally:
        first.close()
        second.close()


def test_reopen_unavailable_previous_assignee_returns_pending(client):
    login(client)
    ticket = create(client)
    login(client, 'agent')
    ticket = action(client, ticket, 'accept')
    ticket = action(client, ticket, 'resolve', reason='已恢复账号访问，请重新登录')
    login(client)
    ticket = action(client, ticket, 'close')
    login(client, 'admin')
    changed = client.put('/api/admin/users/3', json={
        'display_name': '客服一', 'role': 'agent', 'active': False, 'group_id': 1})
    assert changed.status_code == 200
    login(client)
    ticket = action(client, ticket, 'reopen')
    assert ticket['status'] == 'pending' and ticket['assignee_id'] is None


def test_follow_up_atomically_reopens_and_keeps_public_feedback(client):
    login(client)
    ticket = create(client)
    login(client, 'agent')
    ticket = action(client, ticket, 'accept')
    ticket = action(client, ticket, 'resolve', reason='请尝试重设密码')
    action(client, ticket, 'follow_up', expected=403, reason='不允许冒充顾客')
    login(client, 'other')
    action(client, ticket, 'follow_up', expected=404, reason='其他顾客不可写入')
    login(client)
    action(client, ticket, 'follow_up', expected=422, reason='   ')
    unchanged = client.get(f"/api/tickets/{ticket['id']}").json()
    assert unchanged['version'] == ticket['version'] and unchanged['status'] == 'resolved'
    result = action(client, ticket, 'follow_up', reason='按说明操作后，仍然提示验证码失效')
    assert result['id'] == ticket['id'] and result['status'] == 'assigned'
    assert result['version'] == ticket['version'] + 1
    assert result['messages'][-1]['body'] == '按说明操作后，仍然提示验证码失效'
    assert result['messages'][-1]['author_id'] == 1 and not result['messages'][-1]['internal']
    assert result['needs_staff_reply'] is True
    action(client, ticket, 'follow_up', expected=409, reason='重复发送')
    assert client.get('/api/tickets').json()['total'] == 1
    assert len(client.get(f"/api/tickets/{ticket['id']}").json()['messages']) == 2


def test_work_queue_excludes_other_handlers_and_prioritizes_customer_feedback(client):
    login(client)
    first, other, third = create(client), create(client), create(client)
    response = client.post(f"/api/tickets/{third['id']}/messages", json={
        'version': third['version'], 'body': '补充：仍无法登录'})
    third = response.json()
    login(client, 'agent')
    todo = client.get('/api/tickets?scope=todo').json()['items']
    assert [t['id'] for t in todo] == [third['id'], first['id']]
    assert other['id'] not in [t['id'] for t in client.get('/api/tickets?scope=queue').json()['items']]
    assert client.get(f"/api/tickets/{other['id']}").status_code == 200  # visibility is unchanged
    noted = client.post(f"/api/tickets/{third['id']}/messages", json={
        'version':third['version'], 'body':'SECRET_INTERNAL', 'internal':True}).json()
    assert noted['needs_staff_reply'] is True
    assert noted['latest_public_reply']['body'] == '补充：仍无法登录'
    answered = client.post(f"/api/tickets/{third['id']}/messages", json={
        'version':noted['version'], 'body':'已收到补充', 'internal':False}).json()
    assert answered['needs_staff_reply'] is False
    login(client)
    assert 'SECRET_INTERNAL' not in client.get('/api/tickets').text
