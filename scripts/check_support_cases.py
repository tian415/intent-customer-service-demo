"""Replay engineering probes against an isolated rules-only API, not research evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.cli import seed_demo
from app.main import create_app


def check(cases_path: Path, output: Path) -> bool:
    raw = cases_path.read_bytes()
    spec = json.loads(raw)
    results = []
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='support-probes-') as directory:
        app = create_app(Path(directory) / 'probe.sqlite3')
        with TestClient(app, headers={'X-Requested-With': 'ticket-ui'}) as client:
            with Session(app.state.engine) as db:
                credentials = dict(seed_demo(db))
            login = client.post('/api/auth/login', json={
                'username': 'demo_user', 'password': credentials['demo_user'], 'portal': 'shop',
            })
            login.raise_for_status()
            client.headers['X-CSRF-Token'] = login.json()['csrf_token']
            for case in spec['cases']:
                response = client.post('/api/conversations', json={'force_new': True})
                response.raise_for_status()
                chat = response.json()
                trace = []
                failures = []
                for step in case['steps']:
                    payload = {'body': step} if isinstance(step, str) else step
                    route = 'messages' if isinstance(step, str) else 'actions'
                    response = client.post(f"/api/conversations/{chat['id']}/{route}",
                                           json={**payload, 'version': chat['version']})
                    if response.status_code != 200:
                        failures.append(f'HTTP {response.status_code}: {response.json()}')
                        break
                    chat = response.json()
                    reply = next((m['body'] for m in reversed(chat['messages']) if m['role'] == 'assistant'), '')
                    trace.append({'input': step, 'request': chat['current_request'],
                                  'service_intent': chat['service_intent'], 'next_action': chat['next_action'],
                                  'can_submit_refund': chat['can_submit_refund'], 'reply': reply})
                reply = trace[-1]['reply'] if trace else ''
                for key, expected in case['expect'].items():
                    if key == 'reply_contains':
                        failures.extend(f'答复缺少 {text}' for text in expected if text not in reply)
                    elif key == 'reply_not_contains':
                        failures.extend(f'答复不应包含 {text}' for text in expected if text in reply)
                    elif chat.get(key) not in (expected if isinstance(expected, list) else [expected]):
                        failures.append(f'{key}: 期望 {expected!r}，实际 {chat.get(key)!r}')
                results.append({'id': case['id'], 'name': case['name'], 'passed': not failures,
                                'failures': failures, 'trace': trace})
            assert client.get('/api/tickets?scope=mine').json()['total'] == 0, '探针不应自动创建工单'
    passed = sum(item['passed'] for item in results)
    report: dict[str, Any] = {
        'kind': 'engineering_diagnostic_not_independent_evaluation',
        'cases_sha256': hashlib.sha256(raw).hexdigest(),
        'model': 'rules_only', 'total': len(results), 'passed': passed, 'results': results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'工程探针：{passed}/{len(results)}；非独立中文准确率。记录：{output}')
    for item in results:
        if not item['passed']:
            print(item['id'], item['name'], '; '.join(item['failures']))
    return passed == len(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=ROOT / 'backend/tests/fixtures/support_cases.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(0 if check(args.cases, args.output) else 1)
