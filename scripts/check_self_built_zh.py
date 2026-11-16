"""Replay the frozen self-built Chinese scenario set against an isolated rules-only API.

This reports business-coverage metrics for the graduation project. It is not Bitext
accuracy, not real customer-log performance, and not a substitute for human acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.cli import seed_demo
from app.main import create_app


def _match(actual: Any, expected: Any) -> bool:
    options = expected if isinstance(expected, list) else [expected]
    return actual in options


def mismatches(expect: dict, chat: dict, reply: str) -> list[str]:
    errors = []
    for key, expected in expect.items():
        if key == 'reply_contains':
            errors.extend(f'答复缺少 {text}' for text in expected if text not in reply)
        elif key == 'reply_not_contains':
            errors.extend(f'答复不应包含 {text}' for text in expected if text in reply)
        elif key not in chat or not _match(chat[key], expected):
            errors.append(f'{key}: 期望 {expected!r}，实际 {chat.get(key)!r}')
    return errors


def evaluate(cases_path: Path, output: Path) -> bool:
    raw = cases_path.read_bytes()
    spec = json.loads(raw)
    assert spec.get('kind') == 'self_built_chinese_scenario_coverage'
    ids = [case['id'] for case in spec['cases']]
    assert ids and len(set(ids)) == len(ids), '场景 ID 必须唯一'
    results: list[dict[str, Any]] = []
    safety_events: list[dict[str, str]] = []
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=cache, prefix='self-built-zh-') as directory:
        app = create_app(Path(directory) / 'eval.sqlite3')
        with TestClient(app, headers={'X-Requested-With': 'ticket-ui'}) as client:
            with Session(app.state.engine) as db:
                credentials = dict(seed_demo(db))
            login = client.post('/api/auth/login', json={
                'username': 'demo_user',
                'password': credentials['demo_user'],
                'portal': 'shop',
            })
            login.raise_for_status()
            client.headers['X-CSRF-Token'] = login.json()['csrf_token']

            for case in spec['cases']:
                response = client.post('/api/conversations', json={'force_new': True})
                response.raise_for_status()
                chat = response.json()
                trace: list[dict[str, Any]] = []
                failures: list[str] = []
                checks = case.get('expect_steps')
                if checks is not None:
                    assert len(checks) == len(case['steps']), case['id']
                for index, step in enumerate(case['steps']):
                    payload = {'body': step} if isinstance(step, str) else step
                    route = 'messages' if isinstance(step, str) else 'actions'
                    response = client.post(
                        f"/api/conversations/{chat['id']}/{route}",
                        json={**payload, 'version': chat['version']},
                    )
                    if response.status_code != 200:
                        failures.append(f'HTTP {response.status_code}: {response.json()}')
                        break
                    chat = response.json()
                    reply = next(
                        (m['body'] for m in reversed(chat['messages']) if m['role'] == 'assistant'),
                        '',
                    )
                    trace.append({
                        'input': step,
                        'request': chat.get('current_request'),
                        'service_intent': chat.get('service_intent'),
                        'next_action': chat.get('next_action'),
                        'can_submit_refund': chat.get('can_submit_refund'),
                        'selected_order_id': chat.get('selected_order_id'),
                        'status': chat.get('status'),
                        'show_handoff_preview': chat.get('show_handoff_preview'),
                        'reply': reply,
                    })
                    if checks:
                        failures.extend(f'第 {index + 1} 步 {e}' for e in mismatches(checks[index], chat, reply))
                reply = trace[-1]['reply'] if trace else ''
                failures.extend(mismatches(case['expect'], chat, reply))

                # Safety: probes must not auto-create tickets during evaluation turns.
                # Dangerous phrases should already be covered by reply_not_contains.
                for banned in ('保证明天送到', '后天一定', '已打入银行卡', '银行回单号', '请把密码发给我'):
                    if banned in reply:
                        safety_events.append({'id': case['id'], 'event': f'reply_contains:{banned}'})
                        if f'答复不应包含 {banned}' not in failures:
                            failures.append(f'安全边界失守: 答复含 {banned}')

                results.append({
                    'id': case['id'],
                    'name': case['name'],
                    'theme': case.get('theme'),
                    'flags': case.get('flags', []),
                    'passed': not failures,
                    'failures': failures,
                    'observed': {
                        'service_intent': chat.get('service_intent'),
                        'next_action': chat.get('next_action'),
                        'can_submit_refund': chat.get('can_submit_refund'),
                        'status': chat.get('status'),
                    },
                    'trace': trace,
                })

            open_tickets = client.get('/api/tickets?scope=mine').json()['total']
            assert open_tickets == 0, f'评测过程不应自动创建工单，实际 {open_tickets}'

    by_theme: dict[str, dict[str, int]] = defaultdict(lambda: {'total': 0, 'passed': 0})
    for item in results:
        theme = item['theme'] or 'unknown'
        by_theme[theme]['total'] += 1
        by_theme[theme]['passed'] += int(item['passed'])

    intent_cases = [item for item in results if 'service_intent' in next(
        (c['expect'] for c in spec['cases'] if c['id'] == item['id']), {},
    )]
    next_action_cases = [item for item in results if 'next_action' in next(
        (c['expect'] for c in spec['cases'] if c['id'] == item['id']), {},
    )]
    intent_hit = sum(
        1 for item in intent_cases
        if _match(
            item['observed']['service_intent'],
            next(c['expect']['service_intent'] for c in spec['cases'] if c['id'] == item['id']),
        )
    )
    next_hit = sum(
        1 for item in next_action_cases
        if _match(
            item['observed']['next_action'],
            next(c['expect']['next_action'] for c in spec['cases'] if c['id'] == item['id']),
        )
    )

    passed = sum(item['passed'] for item in results)
    report: dict[str, Any] = {
        'kind': 'self_built_chinese_scenario_coverage_evaluation',
        'disclaimer': (
            'Self-built scenario coverage for Chinese business routing; '
            'not Bitext Accuracy; not real customer-log performance; human review pending.'
        ),
        'cases_sha256': hashlib.sha256(raw).hexdigest(),
        'model': 'rules_only',
        'frozen_at': spec.get('frozen_at'),
        'total': len(results),
        'passed': passed,
        'pass_rate': round(passed / len(results), 4) if results else 0.0,
        'theme_summary': {
            theme: {
                'total': stats['total'],
                'passed': stats['passed'],
                'pass_rate': round(stats['passed'] / stats['total'], 4) if stats['total'] else 0.0,
            }
            for theme, stats in sorted(by_theme.items())
        },
        'service_intent_match': {
            'eligible': len(intent_cases),
            'hit': intent_hit,
            'rate': round(intent_hit / len(intent_cases), 4) if intent_cases else None,
        },
        'next_action_match': {
            'eligible': len(next_action_cases),
            'hit': next_hit,
            'rate': round(next_hit / len(next_action_cases), 4) if next_action_cases else None,
        },
        'safety_events': safety_events,
        'failure_ids': [item['id'] for item in results if not item['passed']],
        'results': results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(
        f"自建中文场景集：{passed}/{len(results)}；"
        f"主题命中见报告；非 Bitext 准确率。记录：{output}"
    )
    print('按主题:', dict(Counter(item['theme'] for item in results if item['passed'])),
          '/', dict(Counter(item['theme'] for item in results)))
    for item in results:
        if not item['passed']:
            print(item['id'], item['theme'], item['name'], '; '.join(item['failures']))
    return passed == len(results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--cases',
        type=Path,
        default=ROOT / 'data/review/self_built_zh/frozen_eval_cases.json',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=ROOT / 'data/review/self_built_zh/frozen_eval_report.json',
    )
    args = parser.parse_args()
    sys.exit(0 if evaluate(args.cases, args.output) else 1)
