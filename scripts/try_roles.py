"""Run the three-role hands-on demo on loopback, with a private, reusable demo database."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.cli import seed_demo
from app.database import make_engine, migrate
from app.main import create_app


def local_ui(database: Path, dist: Path) -> FastAPI:
    app = create_app(database)
    app.mount('/assets', StaticFiles(directory=dist / 'assets'))

    @app.get('/{page:path}', include_in_schema=False)
    def frontend(page: str) -> FileResponse:
        if page.startswith('api/'):
            raise HTTPException(404)
        return FileResponse(dist / 'index.html')

    return app


def prepare(directory: Path) -> None:
    if directory.exists():
        if not all((directory / f).is_file() for f in ('demo.sqlite3', 'accounts.json')):
            raise RuntimeError('体验目录不完整，已保留原文件。')
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix='prepare-roles-') as temp:
        stage = Path(temp) / 'session'
        stage.mkdir(mode=0o700)
        engine = make_engine(stage / 'demo.sqlite3')
        try:
            migrate(engine)
            with Session(engine) as db:
                accounts = dict(seed_demo(db))
            with os.fdopen(os.open(stage / 'accounts.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
                           'w', encoding='utf-8') as f:
                json.dump(accounts, f, indent=2)
        finally:
            engine.dispose()
        stage.rename(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='打开三个独立登录的 Chrome 窗口')
    parser.add_argument('--port', type=int, default=8765, help='本机体验端口，默认 8765')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口应在 1 至 65535 之间')
    directory = ROOT / '.cache' / 'hands-on'
    origin = f'http://127.0.0.1:{args.port}'
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', args.port))
        listener.listen(128)
        prepare(directory)
        dist = ROOT / 'frontend' / 'dist'
        subprocess.run(['npm', 'run', 'build'], cwd=ROOT / 'frontend', check=True)
        app = local_ui(directory / 'demo.sqlite3', dist)
        print(f'体验入口 {origin}，本机演示账号见 {directory / "accounts.json"}', flush=True)
        windows = None
        if args.open:
            windows = subprocess.Popen(['node', 'e2e/open-roles.mjs', origin, str(directory / 'accounts.json')],
                                       cwd=ROOT / 'frontend')
        try:
            uvicorn.Server(uvicorn.Config(app, access_log=False)).run(sockets=[listener])
        finally:
            if windows and windows.poll() is None:
                windows.terminate()
                windows.wait(timeout=10)


if __name__ == '__main__':
    main()
