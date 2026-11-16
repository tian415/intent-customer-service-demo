"""Build the current UI and run the local two-portal acceptance in a disposable store."""
from __future__ import annotations

import json
import argparse
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

from sqlalchemy.orm import Session
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.cli import seed_demo
from app.database import make_engine, migrate
from try_roles import local_ui


def check(run_dir: Path, suite: str = 'portals', case_set: str = 'first') -> int:
    dist = run_dir / 'dist'
    subprocess.run(['npm', 'run', 'build', '--', '--outDir', str(dist)],
                   cwd=ROOT / 'frontend', check=True)
    db_path = run_dir / 'demo.sqlite3'
    engine = make_engine(db_path)
    try:
        migrate(engine)
        with Session(engine) as db:
            credentials = dict(seed_demo(db))
    finally:
        engine.dispose()
    app = local_ui(db_path, dist)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError('隔离验收服务启动失败')
                time.sleep(0.05)
            evidence = ROOT / '.cache' / 'verification' / 'portals'
            evidence.mkdir(parents=True, exist_ok=True)
            output = tempfile.mkdtemp(dir=evidence, prefix='run-')
            print(f'本次浏览器验收记录目录 {output}', flush=True)
            result = subprocess.run(
                ['node', f'e2e/{suite}.mjs'], cwd=ROOT / 'frontend', timeout=180,
                input=json.dumps({'origin': origin, 'credentials': credentials, 'output': output, 'caseSet': case_set}),
                text=True,
            )
            return result.returncode
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['portals', 'service-followup', 'service-language', 'service-fresh', 'service-cycle'], default='portals')
    parser.add_argument('--case-set', choices=['first', 'final', 'speech', 'speech-final', 'history', 'r22-fresh',
                                               'r22-acceptance', 'r22-release', 'r22-colloquial',
                                               'r22-final', 'r24-audit', 'r25-submit', 'complete'], default='first')
    args = parser.parse_args()
    if args.case_set != 'first' and args.suite != 'service-fresh':
        parser.error('--case-set 仅适用于 service-fresh')

    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='portals-') as temporary:
        sys.exit(check(Path(temporary), args.suite, args.case_set))
