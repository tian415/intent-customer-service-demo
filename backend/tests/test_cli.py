from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.cli import seed_demo
from app.database import make_engine, migrate
from app.models import FAQ, Ticket, User
from app.security import verify_password


def test_demo_seed_is_explicit_idempotent_and_has_no_fake_ticket_results(tmp_path):
    engine = make_engine(tmp_path / 'demo.sqlite3')
    migrate(engine)
    with Session(engine) as db:
        first = seed_demo(db)
        assert len(first) == 4
        assert len(set(password for _, password in first)) == 4
        for username, password in first:
            user = db.scalar(select(User).where(User.username == username))
            assert user.display_name.startswith('DEMO')
            assert verify_password(password, user.password_hash)
        assert db.scalar(select(func.count()).select_from(Ticket)) == 0
        assert all(f.question.startswith('DEMO') for f in db.scalars(select(FAQ)))
        assert seed_demo(db) == []
        assert db.scalar(select(func.count()).select_from(User)) == 4
    engine.dispose()
