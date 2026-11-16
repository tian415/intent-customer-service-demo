"""SQLite connections and transactional, checksum-verified migrations."""
import hashlib
import os
from pathlib import Path
from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / 'data' / 'runtime' / 'app.sqlite3'
DATABASE_URL = URL.create('sqlite', database=str(DATABASE_PATH))
MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations'


def make_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass  # Existing permissions are changed only with explicit local approval.
    else:
        os.close(descriptor)
    engine = create_engine(URL.create('sqlite', database=str(path)), connect_args={'check_same_thread': False, 'timeout': 10})

    @event.listens_for(engine, 'connect')
    def configure(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')
    return engine


def migrate(engine: Engine, directory: Path = MIGRATIONS) -> list[str]:
    """Immutable migration files; never create_all or silently recreate a database."""
    applied = []
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        try:
            connection.exec_driver_sql('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            existing = dict(connection.exec_driver_sql('SELECT name, checksum FROM schema_migrations').all())
            files = sorted(directory.glob('[0-9][0-9][0-9]_*.sql'))
            if set(existing) - {p.name for p in files}:
                raise RuntimeError('数据库迁移版本高于当前代码，停止启动')
            for path in files:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if path.name in existing:
                    if existing[path.name] != digest:
                        raise RuntimeError(f'已应用迁移被修改：{path.name}')
                    continue
                for statement in raw.decode('utf-8').split(';'):
                    if statement.strip():
                        connection.exec_driver_sql(statement)
                connection.exec_driver_sql('INSERT INTO schema_migrations(name, checksum) VALUES (?, ?)', (path.name, digest))
                applied.append(path.name)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return applied
