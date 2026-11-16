"""Disposable credentials only: rotation must preserve business and revoke old sessions."""
import json
import os
import secrets
import stat
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.cli import seed_demo
from app.main import create_app
from app.models import User, AuthSession, Ticket
from app.security import verify_password, hash_password


def test_demo_rotation_is_private_preserves_records_and_revokes_old_sessions(tmp_path,capsys):
    from app.cli import rotate_demo
    application=create_app(tmp_path/'demo.sqlite3')
    with TestClient(application,headers={'X-Requested-With':'ticket-ui'}) as client:
        with Session(application.state.engine) as db:
            old=dict(seed_demo(db))
            other_hash=hash_password(secrets.token_urlsafe(24))
            other=User(username='real_user',display_name='不参与演示轮换',password_hash=other_hash,role='user',active=True)
            db.add(other);db.flush();other_id=other.id
            db.add(AuthSession(id='unrelated-session',user_id=other_id,csrf_token='fixture',expires_at=9999999999));db.commit()
        response=client.post('/api/auth/login',json={'username':'demo_user','password':old['demo_user']})
        client.headers['X-CSRF-Token']=response.json()['csrf_token']
        ticket=client.post('/api/tickets',json={'title':'DEMO 密码','description':'保留历史工单'}).json()
        output=tmp_path/'private'/'credentials-demo.json'
        result=rotate_demo(application.state.engine,output)
        assert result['rotated_accounts']==4 and result['revoked_sessions']==1
        credentials=json.loads(output.read_text())['credentials']
        assert set(credentials)==set(old) and all(credentials[k]!=old[k] for k in old)
        if os.name=='posix':
            assert stat.S_IMODE(output.stat().st_mode)==0o600
            assert stat.S_IMODE(output.parent.stat().st_mode)==0o700
        assert client.get('/api/auth/me').status_code==401
        assert client.post('/api/auth/login',json={'username':'demo_user','password':old['demo_user']}).status_code==401
        client.cookies.clear()
        assert client.post('/api/auth/login',json={'username':'demo_user','password':credentials['demo_user']}).status_code==200
        with Session(application.state.engine) as db:
            stored=db.get(Ticket,ticket['id'])
            assert stored.description=='保留历史工单' and stored.status=='assigned'
            assert all(verify_password(credentials[u.username],u.password_hash) for u in db.scalars(select(User).where(User.username.in_(old))))
            assert db.get(User,other_id).password_hash==other_hash
            assert db.get(AuthSession,'unrelated-session') is not None
        captured=capsys.readouterr()
        assert not any(value in captured.out+captured.err for value in credentials.values())
        with pytest.raises(ValueError,match='存在'):
            rotate_demo(application.state.engine,output)


def test_demo_rotation_refuses_modified_identity_without_any_password_change(tmp_path):
    from app.cli import rotate_demo
    application=create_app(tmp_path/'demo.sqlite3')
    with TestClient(application):
        with Session(application.state.engine) as db:
            seed_demo(db)
            user=db.scalar(select(User).where(User.username=='demo_user'));user.display_name='普通真实用户';db.commit()
            before={u.id:u.password_hash for u in db.scalars(select(User))}
        output=tmp_path/'private'/'credentials.json'
        with pytest.raises(ValueError,match='DEMO|演示'):
            rotate_demo(application.state.engine,output)
        assert not output.exists()
        with Session(application.state.engine) as db:
            assert {u.id:u.password_hash for u in db.scalars(select(User))}==before


def test_directory_sync_failure_keeps_original_passwords_and_sessions(tmp_path,monkeypatch):
    import app.cli as cli
    application=create_app(tmp_path/'demo.sqlite3')
    with TestClient(application):
        with Session(application.state.engine) as db:
            seed_demo(db)
            before={u.id:u.password_hash for u in db.scalars(select(User))}
            db.add(AuthSession(id='old-valid-session',user_id=next(iter(before)),csrf_token='fixture',expires_at=9999999999));db.commit()
        original_fsync=os.fsync
        def fail_directory_sync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError('synthetic directory fsync failure')
            return original_fsync(descriptor)
        monkeypatch.setattr(cli.os,'fsync',fail_directory_sync)
        output=tmp_path/'new-private'/'nested'/'credentials.json'
        with pytest.raises(OSError,match='directory fsync failure'):
            cli.rotate_demo(application.state.engine,output)
        assert not output.exists()
        with Session(application.state.engine) as db:
            assert {u.id:u.password_hash for u in db.scalars(select(User))}==before
            assert db.get(AuthSession,'old-valid-session') is not None
