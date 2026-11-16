"""Disposable, private, non-research browser fixture. Never opens the user runtime DB."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy.orm import Session
import uvicorn
from app.cli import seed_demo
from app.database import make_engine, migrate
from app.main import create_app
from app.models import Category
from ml.train import train


def private_json(path: Path, value) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def prepare_fixture(directory: Path) -> dict:
    directory = directory.resolve()
    if not directory.is_relative_to(ROOT / '.cache') or directory.exists():
        raise ValueError('必须指定项目.cache内尚不存在的隔离目录，禁止覆盖任何现有数据库')
    directory.mkdir(parents=True, mode=0o700)
    rows = [('登录密码忘记了请求重置', 'credential_reset'), ('密码忘记后如何找回账号', 'credential_reset'),
            ('无法登录需要重置密码', 'credential_reset'), ('账号密码忘记无法进入', 'credential_reset'),
            ('希望申请退款退费', 'refund_request'), ('退费申请如何办理', 'refund_request'),
            ('订单退款咨询', 'refund_request'), ('请处理退款申请', 'refund_request'),
            ('软件闪退出现故障', 'client_crash'), ('产品打开后闪退报错', 'client_crash'),
            ('程序故障无法启动', 'client_crash'), ('应用报错崩溃', 'client_crash')]
    data = directory / 'engineering-training.jsonl'
    data.write_text(''.join(json.dumps({'text': text, 'label': label}, ensure_ascii=False) + '\n' for text, label in rows))
    source = directory / 'source.json'
    private_json(source, {'name': 'DEMO synthetic browser software fixture; never research data',
                         'url': 'local:scripts/serve_browser_fixture.py', 'license': 'project synthetic engineering fixture',
                         'version': 'phase3-v1', 'approved_by': 'user authorization for non-research engineering tests only',
                         'usage_approved': True, 'privacy_reviewed': True})
    model = directory / 'model.json'
    train(data, source, model, threshold=0.0, margin=0.0, config={'C': 1.0})
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    engine = make_engine(directory / 'fixture.sqlite3')
    migrate(engine)
    with Session(engine) as db:
        credentials = dict(seed_demo(db))
        categories = {c.name: c.id for c in db.query(Category)}
    engine.dispose()
    mapping = directory / 'label-map.json'
    private_json(mapping, {'model_sha256': digest, 'approved': True,
                           'approved_by': 'DEMO browser software fixture only; not a research approval',
                           'labels': {'credential_reset': categories['账号问题'], 'refund_request': categories['退款咨询'], 'client_crash': categories['产品故障']}})
    private_json(directory / 'credentials.json', credentials)
    info = {'purpose': 'DEMO engineering E2E, not research or real user records', 'model_sha256': digest,
            'mapping_sha256': hashlib.sha256(mapping.read_bytes()).hexdigest(), 'database': str(directory / 'fixture.sqlite3'),
            'model': str(model), 'mapping': str(mapping)}
    private_json(directory / 'run-info.json', info)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    info = prepare_fixture(args.directory)
    credentials = args.directory / 'credentials.json'
    print('隔离DEMO服务将监听127.0.0.1:8000；凭据私有且不打印，浏览器读取后立即移除。', flush=True)
    try:
        uvicorn.run(create_app(Path(info['database']), Path(info['model']), expected_model_sha256=info['model_sha256'], label_map_path=Path(info['mapping'])), host='127.0.0.1', port=8000)
    finally:
        credentials.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
