import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import create_app
from app.database import ROOT
from app.models import Category, FAQ, Group, User
from app.security import hash_password

TEST_PASSWORD = 'Test-only-password-2026'


def pytest_configure(config):
    # Keep temporary data inside this project regardless of the invocation cwd.
    if not config.option.basetemp:
        config.option.basetemp = str(ROOT / '.cache' / 'pytest')


@pytest.fixture(scope='session')
def password_hash():
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def app(tmp_path, password_hash):
    application = create_app(tmp_path / 'test.sqlite3')
    with TestClient(application):
        with Session(application.state.engine) as db:
            db.add_all([Group(id=1, name='技术组'), Group(id=2, name='账务组')])
            db.flush()
            db.add_all([
                User(id=1, username='customer', display_name='测试用户', password_hash=password_hash, role='user', active=True),
                User(id=2, username='other', display_name='其他用户', password_hash=password_hash, role='user', active=True),
                User(id=3, username='agent', display_name='客服一', password_hash=password_hash, role='agent', active=True, group_id=1),
                User(id=4, username='agent2', display_name='客服二', password_hash=password_hash, role='agent', active=True, group_id=1),
                User(id=5, username='billing', display_name='账务客服', password_hash=password_hash, role='agent', active=True, group_id=2),
                User(id=6, username='admin', display_name='管理员', password_hash=password_hash, role='admin', active=True),
            ])
            db.add(Category(id=1, name='账号问题', keywords='密码,登录', active=True, group_id=1))
            db.flush()
            db.add(FAQ(question='忘记密码怎么办', answer='测试知识库答案', keywords='密码', category_id=1, active=True))
            db.commit()
        yield application


@pytest.fixture
def client(app):
    # app fixture owns the lifespan; avoid reinitializing shared state.
    c = TestClient(app, headers={'X-Requested-With': 'ticket-ui'})
    yield c
    c.close()


def login(client, username='customer'):
    response = client.post('/api/auth/login', json={'username': username, 'password': TEST_PASSWORD})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return response.json()['user']
