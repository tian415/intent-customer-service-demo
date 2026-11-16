"""Administrative boundaries, knowledge fallback, and database-derived stats."""
from fastapi.testclient import TestClient
from conftest import TEST_PASSWORD, login


def test_admin_crud_references_duplicates_and_catalog(client):
    login(client, 'admin')
    group = client.post('/api/admin/groups', json={'name': '新客服组'})
    assert group.status_code == 201
    identity = group.json()['id']
    assert client.put(f'/api/admin/groups/{identity}', json={'name': '更名组'}).json()['name'] == '更名组'
    assert client.post('/api/admin/groups', json={'name': '更名组'}).status_code == 409
    category_data = {'name': '新类别', 'keywords': '新关键词', 'active': True, 'group_id': identity}
    category = client.post('/api/admin/categories', json=category_data)
    assert category.status_code == 201
    category_id = category.json()['id']
    assert client.put(f'/api/admin/categories/{category_id}', json={**category_data, 'name': '更新类别'}).status_code == 200
    assert client.post('/api/admin/categories', json={**category_data, 'group_id': 99999}).status_code == 422
    account_data = {'username': 'NEW_AGENT', 'display_name': '新客服', 'password': TEST_PASSWORD,
                    'role': 'agent', 'active': True, 'group_id': identity}
    account = client.post('/api/admin/users', json=account_data)
    assert account.status_code == 201 and account.json()['username'] == 'new_agent'
    assert 'password_hash' not in account.text and TEST_PASSWORD not in account.text
    assert client.post('/api/admin/users', json=account_data).status_code == 409
    assert client.post('/api/admin/users', json={**account_data, 'username': 'bad_reference', 'group_id': 9999}).status_code == 422
    assert client.post('/api/admin/users', json={**account_data, 'username': 'invalid_group', 'role': 'user'}).status_code == 422
    assert client.post('/api/admin/users', json={**account_data, 'username': 'short_pass', 'password': 'short'}).status_code == 422
    faq_data = {'question': '新问题', 'answer': '新答案', 'keywords': '新关键词', 'category_id': category_id, 'active': True}
    faq = client.post('/api/admin/faqs', json=faq_data)
    assert faq.status_code == 201
    faq_id = faq.json()['id']
    assert client.put(f'/api/admin/faqs/{faq_id}', json={**faq_data, 'answer': '更新答案'}).json()['answer'] == '更新答案'
    assert client.post('/api/admin/faqs', json={**faq_data, 'category_id': 99999}).status_code == 422
    assert client.delete(f'/api/admin/faqs/{faq_id}').json() == {'ok': True}
    assert faq_id not in [f['id'] for f in client.get('/api/admin/faqs').json()]
    login(client)
    catalog = client.get('/api/catalog').json()
    assert catalog['groups'] == [] and catalog['agents'] == []
    for endpoint in ('users', 'groups', 'categories', 'faqs', 'stats'):
        assert client.get(f'/api/admin/{endpoint}').status_code == 403


def test_last_active_admin_cannot_be_disabled_or_demoted(client):
    login(client, 'admin')
    for role, active in [('admin', False), ('user', True), ('agent', True)]:
        response = client.put('/api/admin/users/6', json={
            'display_name': '管理员', 'role': role, 'active': active, 'group_id': None})
        assert response.status_code == 409
    assert client.get('/api/auth/me').status_code == 200


def test_password_role_active_and_group_changes_revoke_target_session(client, app):
    login(client, 'admin')
    target = TestClient(app, headers={'X-Requested-With': 'ticket-ui'})
    try:
        cases = [
            ('other', 2, {'display_name': '其他用户', 'role': 'user', 'active': True, 'group_id': None, 'password': TEST_PASSWORD}),
            ('other', 2, {'display_name': '其他用户', 'role': 'agent', 'active': True, 'group_id': None}),
            ('billing', 5, {'display_name': '账务客服', 'role': 'agent', 'active': True, 'group_id': 1}),
            ('customer', 1, {'display_name': '测试用户', 'role': 'user', 'active': False, 'group_id': None}),
        ]
        for username, identity, payload in cases:
            login(target, username)
            assert client.put(f'/api/admin/users/{identity}', json=payload).status_code == 200
            assert target.get('/api/auth/me').status_code == 401
        assert client.get('/api/auth/me').status_code == 200
    finally:
        target.close()


def test_open_ticket_blocks_agent_disable_demotion_and_group_change(client):
    login(client)
    assert client.post('/api/tickets', json={'title': '密码问题', 'description': '忘记密码'}).status_code == 201
    login(client, 'admin')
    for role, active, group in [('agent', False, 1), ('user', True, None), ('agent', True, 2)]:
        response = client.put('/api/admin/users/3', json={
            'display_name': '客服一', 'role': role, 'active': active, 'group_id': group})
        assert response.status_code == 409
    assert client.get('/api/admin/users').json()[2]['active'] is True


def test_faq_no_match_ambiguous_inactive_and_exact_question(client):
    login(client)
    empty = client.get('/api/faq/search', params={'q': '未知业务'}).json()
    assert empty['items'] == [] and empty['reliable'] is False and empty['fallback'] == 'manual_ticket'
    exact = client.get('/api/faq/search', params={'q': '忘记密码怎么办'}).json()
    assert exact['reliable'] and exact['items'][0]['score'] == 1.0 and exact['fallback'] is None
    login(client, 'admin')
    data = {'question': '另一个密码问题', 'answer': '另一个答案', 'keywords': '密码', 'active': True, 'category_id': 1}
    created = client.post('/api/admin/faqs', json=data).json()
    ambiguous = client.get('/api/faq/search', params={'q': '密码'}).json()
    assert len(ambiguous['items']) == 2 and ambiguous['reliable'] is False
    assert ambiguous['fallback'] == 'manual_ticket'
    assert client.put(f"/api/admin/faqs/{created['id']}", json={**data, 'active': False}).status_code == 200
    assert len(client.get('/api/faq/search', params={'q': '密码'}).json()['items']) == 1
    assert client.put('/api/admin/faqs/1', json={**data, 'active': False}).status_code == 200
    disabled = client.get('/api/faq/search', params={'q': '密码'}).json()
    assert disabled['items'] == [] and disabled['fallback'] == 'manual_ticket'


def test_stats_come_from_tickets_and_corrections(client):
    login(client, 'admin')
    baseline = client.get('/api/admin/stats').json()
    assert baseline['total'] == 0 and baseline['corrections'] == 0
    login(client)
    first = client.post('/api/tickets', json={'title': '密码问题', 'description': '登录失败'}).json()
    second = client.post('/api/tickets', json={'title': '未知业务', 'description': '没有关键词'}).json()
    login(client, 'admin')
    stats = client.get('/api/admin/stats').json()
    assert stats['total'] == 2 and stats['unassigned'] == 1
    assert {row['name']: row['count'] for row in stats['by_status']} == {'assigned': 1, 'pending': 1}
    assert {row['name']: row['count'] for row in stats['by_category']} == {'账号问题': 1, '待分类': 1}
    assert {row['name']: row['count'] for row in stats['by_source']} == {'rules': 1, 'fallback': 1}
    correction = client.post(f"/api/tickets/{second['id']}/actions", json={
        'version': second['version'], 'action': 'classify', 'category_id': 1, 'reason': '人工确认'})
    assert correction.status_code == 200
    stats = client.get('/api/admin/stats').json()
    assert stats['total'] == 2 and stats['corrections'] == 1 and stats['unassigned'] == 0
    assert {row['name']: row['count'] for row in stats['by_category']} == {'账号问题': 2}
    assert stats['by_status'] == [{'name': 'assigned', 'count': 2}]
    assert first['id'] != second['id']
