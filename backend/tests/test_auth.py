from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuthSession, User
from app.security import hash_password, verify_password
from conftest import TEST_PASSWORD, login


def test_password_is_salted_and_verifiable():
    first = hash_password('a-long-test-password')
    second = hash_password('a-long-test-password')
    assert first != second
    assert 'a-long-test-password' not in first
    assert verify_password('a-long-test-password', first)
    assert not verify_password('wrong', first)


def test_auth_csrf_cookie_and_logout(client, app):
    assert client.get('/api/tickets').status_code == 401
    response = client.post('/api/auth/login', json={'username': 'customer', 'password': 'wrong'})
    assert response.status_code == 401
    login(client)
    assert client.get('/api/auth/me').json()['user']['role'] == 'user'
    with Session(app.state.engine) as db:
        token = db.scalar(select(AuthSession)).id
        assert token != client.cookies.get('ticket_session')
        assert TEST_PASSWORD not in db.get(User, 1).password_hash
    saved = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/auth/logout', json={}).status_code == 403
    client.headers['X-CSRF-Token'] = saved
    assert client.post('/api/auth/logout', json={}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_foreign_origin_and_missing_header_rejected(client):
    assert client.post('/api/auth/login', headers={'Origin': 'https://evil.example'}, json={'username': 'customer', 'password': TEST_PASSWORD}).status_code == 403
    client.headers.pop('X-Requested-With')
    assert client.post('/api/auth/login', json={'username': 'customer', 'password': TEST_PASSWORD}).status_code == 403


def test_admin_boundary_and_last_admin(client):
    login(client)
    assert client.get('/api/admin/users').status_code == 403
    login(client, 'admin')
    payload = {'display_name': '管理员', 'role': 'user', 'active': True, 'group_id': None}
    assert client.put('/api/admin/users/6', json=payload).status_code == 409
    payload = {'username': 'newuser', 'password': TEST_PASSWORD, 'display_name': '新用户', 'role': 'user', 'active': True, 'group_id': None}
    created = client.post('/api/admin/users', json=payload)
    assert created.status_code == 201
    assert 'password_hash' not in created.json()
    assert client.post('/api/admin/users', json=payload).status_code == 409


def test_login_throttle_and_expired_session(client, app):
    for _ in range(10):
        assert client.post('/api/auth/login', json={'username': 'customer', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'customer', 'password': TEST_PASSWORD}).status_code == 429
    login(client, 'other')
    with Session(app.state.engine) as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == 2))
        session.expires_at = 0
        db.commit()
    assert client.get('/api/auth/me').status_code == 401


def test_password_whitespace_is_not_silently_changed(client):
    login(client, 'admin')
    password = '  whitespace password  '
    response = client.post('/api/admin/users', json={'username': 'spaces', 'display_name': '密码边界', 'role': 'user', 'password': password})
    assert response.status_code == 201
    assert client.post('/api/auth/login', json={'username': 'spaces', 'password': password.strip()}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'spaces', 'password': password}).status_code == 200


def test_invalid_origin_and_host_rejected(client):
    assert client.post('/api/auth/login', headers={'Origin': 'http://[bad'}, json={'username': 'customer', 'password': TEST_PASSWORD}).status_code == 403
    assert client.get('/api/health', headers={'Host': 'untrusted.example'}).status_code == 400


def test_wrong_portal_never_issues_session(client, app):
    for username, wrong, right in [('admin', 'shop', 'staff'), ('agent', 'shop', 'staff'), ('customer', 'staff', 'shop')]:
        credentials = {'username': username, 'password': TEST_PASSWORD}
        denied = client.post('/api/auth/login', json={**credentials, 'portal': wrong})
        assert denied.status_code == 403
        assert 'set-cookie' not in denied.headers
        assert client.get('/api/auth/me').status_code == 401
        with Session(app.state.engine) as db:
            assert db.scalar(select(AuthSession)) is None
        accepted = client.post('/api/auth/login', json={**credentials, 'portal': right})
        assert accepted.status_code == 200
        client.headers['X-CSRF-Token'] = accepted.json()['csrf_token']
        assert client.post('/api/auth/logout').status_code == 200
