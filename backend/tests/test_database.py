"""Real SQLite migration and restart checks; no runtime database is touched."""
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.database import MIGRATIONS, make_engine, migrate
from app.main import create_app
from app.models import User
from conftest import login


def test_migration_idempotence_preserves_existing_rows(tmp_path):
    engine = make_engine(tmp_path / 'migration.sqlite3')
    try:
        applied = migrate(engine)
        assert applied
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO groups(id,name) VALUES (123,'持久组')")
            before = connection.exec_driver_sql('SELECT name, checksum, applied_at FROM schema_migrations ORDER BY name').all()
        assert migrate(engine) == []
        with engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT name FROM groups WHERE id=123').scalar_one() == '持久组'
            assert connection.exec_driver_sql('SELECT name, checksum, applied_at FROM schema_migrations ORDER BY name').all() == before
    finally:
        engine.dispose()


def test_migration_changed_checksum_and_missing_version_fail_closed(tmp_path):
    directory = tmp_path / 'migrations'
    directory.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        (directory / path.name).write_bytes(path.read_bytes())
    engine = make_engine(tmp_path / 'checksum.sqlite3')
    try:
        applied = migrate(engine, directory)
        changed = directory / applied[0]
        original = changed.read_text()
        changed.write_text(original + '\n-- changed migration\n')
        with pytest.raises(RuntimeError, match='已应用迁移被修改'):
            migrate(engine, directory)
        changed.write_text(original)
        changed.unlink()
        with pytest.raises(RuntimeError, match='迁移版本高于当前代码'):
            migrate(engine, directory)
        with engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT count(*) FROM schema_migrations').scalar_one() == len(applied)
    finally:
        engine.dispose()


def test_failed_migration_rolls_back_partial_schema(tmp_path):
    directory = tmp_path / 'broken'
    directory.mkdir()
    (directory / '001_broken.sql').write_text('CREATE TABLE partial(id INTEGER); INVALID SQL;')
    engine = make_engine(tmp_path / 'rollback.sqlite3')
    try:
        with pytest.raises(OperationalError, match='syntax error'):
            migrate(engine, directory)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM sqlite_master WHERE name='partial'").scalar_one() == 0
    finally:
        engine.dispose()


def test_application_restart_preserves_accounts_tickets_and_history(tmp_path, password_hash):
    path = tmp_path / 'restart.sqlite3'
    initial = create_app(path)
    with TestClient(initial, headers={'X-Requested-With': 'ticket-ui'}) as first:
        with Session(initial.state.engine) as db:
            db.add(User(username='customer', display_name='重启用户', password_hash=password_hash, role='user', active=True))
            db.commit()
        login(first)
        response = first.post('/api/tickets', json={'title': '重启持久化', 'description': '没有类别时转人工'})
        assert response.status_code == 201
        ticket = response.json()
        reply = first.post(f"/api/tickets/{ticket['id']}/messages", json={
            'version': ticket['version'], 'body': '重启前公开回复'})
        assert reply.status_code == 200
        stored = reply.json()
    restarted = create_app(path)
    with TestClient(restarted, headers={'X-Requested-With': 'ticket-ui'}) as second:
        login(second)
        response = second.get(f"/api/tickets/{ticket['id']}")
        assert response.status_code == 200
        assert response.json() == stored
        assert second.get('/api/tickets').json()['total'] == 1
        assert migrate(restarted.state.engine) == []


def test_phase2_version_column_migration_preserves_an_existing_v1_ticket(tmp_path):
    original=tmp_path/'v1-migrations';original.mkdir()
    (original/'001_initial.sql').write_bytes((MIGRATIONS/'001_initial.sql').read_bytes())
    engine=make_engine(tmp_path/'upgrade.sqlite3')
    try:
        assert migrate(engine,original)==['001_initial.sql']
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'olduser','历史用户','not-a-login-hash','user','2026-01-01T00:00:00+00:00')")
            connection.exec_driver_sql("INSERT INTO tickets(id,title,description,owner_id,status,prediction_source,created_at,updated_at) VALUES(1,'历史工单','保留原文',1,'pending','rules','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')")
        assert migrate(engine)==[
            '002_prediction_model_version.sql',
            '003_prediction_label_trace.sql',
            '004_orders_conversations.sql',
            '005_ticket_order_id.sql',
            '006_conversation_request.sql',
            '007_refund_review.sql',
        ]
        with engine.connect() as connection:
            row=connection.exec_driver_sql('SELECT title,description,prediction_model_version,prediction_label,prediction_mapping_version,prediction_integrity,order_id FROM tickets WHERE id=1').one()
            assert tuple(row)==('历史工单','保留原文',None,None,None,None,None)
            assert connection.exec_driver_sql('SELECT COUNT(*) FROM orders').scalar()==0
            assert connection.exec_driver_sql('SELECT COUNT(*) FROM conversations').scalar()==0
        assert migrate(engine)==[]
    finally:
        engine.dispose()
