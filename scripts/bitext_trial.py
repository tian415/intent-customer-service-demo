"""Bounded Bitext engineering trial; no download, research split or quality metrics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.cli import seed_demo
from app.main import create_app
from ml.audit import audit
from ml.dataset import read_records, read_source, sha256
from ml.intent import load_model, normalize_text, predict
from ml.prepare import prepare
from ml.train import train

SENSITIVE = {'email': r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', 'digit_run_7plus': r'\d{7,}'}


def write_json(path: Path, value) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def exercise_tickets(directory: Path, model: Path, digest: str, rows: list[dict]) -> dict:
    """Use existing app/service contracts on a separate private SQLite database."""
    application = create_app(directory / 'integration.sqlite3', model, expected_model_sha256=digest)
    with TestClient(application, headers={'X-Requested-With': 'ticket-ui'}) as client:
        with Session(application.state.engine) as db:
            credentials = dict(seed_demo(db))
        response = client.post('/api/auth/login', json={'username': 'demo_user', 'password': credentials['demo_user']})
        assert response.status_code == 200
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        catalog = client.get('/api/catalog').json()['categories']
        categories = {c['name']: c['id'] for c in catalog}
        mapping = directory / 'engineering-routing-map.json'
        labels = load_model(model)['labels']
        targets = {'recover_password': categories['账号问题'], 'get_refund': categories['退款咨询']}
        write_json(mapping, {'model_sha256': digest, 'approved': True,
                            'approved_by': 'Phase4A user authorization: isolated engineering probe only, not formal mapping approval',
                            'labels': {label: targets.get(label) for label in labels}})
        application.state.label_map_path = mapping
        def submit(text: str) -> dict:
            result = client.post('/api/tickets', json={'title': 'DEMO Bitext工程自检', 'description': text})
            assert result.status_code == 201, result.status_code
            return result.json()
        probes = {label: next(row['instruction'] for row in rows if row['intent'] == label)
                  for label in ('recover_password', 'get_refund', 'delivery_options')}
        account, refund, unmapped = (submit(probes[label]) for label in probes)
        assert account['prediction_label'] == 'recover_password' and account['category_name'] == '账号问题'
        assert refund['prediction_label'] == 'get_refund' and refund['category_name'] == '退款咨询'
        assert all(r['prediction_source'] == 'model' and r['assignee_id'] is not None for r in (account, refund))
        assert unmapped['prediction_source'] == 'model' and unmapped['needs_manual'] and unmapped['category_id'] is None
        assert unmapped['assignee_id'] is None and unmapped['status'] == 'pending'
        application.state.label_map_path = None
        mismatch = submit(probes['recover_password'])
        assert mismatch['prediction_source'] == 'fallback' and mismatch['needs_manual']
        application.state.label_map_path = mapping
        damaged = directory / 'damaged-model.json'
        value = json.loads(model.read_text(encoding='utf-8'));value['intercept'][0] += 1
        write_json(damaged, value)
        application.state.model_path = damaged
        english, chinese = submit(probes['recover_password']), submit('忘记登录密码')
        assert english['prediction_source'] == 'fallback' and english['needs_manual']
        assert chinese['prediction_source'] == 'rules' and chinese['category_name'] == '账号问题'
        assert chinese['assignee_id'] is not None and chinese['prediction_model_version'] is None
        preserved = client.get(f"/api/tickets/{account['id']}").json()
        assert preserved['prediction_model_version'] == digest and preserved['prediction_label'] == 'recover_password'
        login = client.post('/api/auth/login', json={'username': 'demo_admin', 'password': credentials['demo_admin']})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        response = client.post(f"/api/tickets/{account['id']}/actions",
                               json={'action': 'classify', 'version': preserved['version'], 'category_id': categories['退款咨询'],
                                     'reason': 'DEMO工程纠错，只验证保留原预测，不是正式标签判断'})
        assert response.status_code == 200
        corrected = response.json()
        assert corrected['category_name'] == '退款咨询' and corrected['assignee_id'] is not None
        assert corrected['prediction_label'] == 'recover_password' and corrected['prediction_model_version'] == digest
        assert corrected['prediction_mapping_version'] == preserved['prediction_mapping_version']
        assert any(event['kind'] == 'classification' for event in corrected['events'])
        keys = ('prediction_source', 'prediction_label', 'prediction_model_version', 'prediction_mapping_version',
                'category_name', 'needs_manual', 'status', 'assignee_id')
        return {name: {key: value[key] for key in keys} for name, value in
                [('account', account), ('refund', refund), ('unmapped', unmapped), ('mismatch', mismatch),
                 ('damaged_english', english), ('damaged_chinese', chinese), ('manual_correction', corrected)]}


def run_trial(raw: Path, source: Path, directory: Path, *, per_intent: int = 10, near_limit: int = 10000) -> dict:
    if directory.exists():
        raise ValueError('试运行目录已存在，拒绝覆盖任何产物')
    if not 2 <= per_intent <= 20 or not 0 <= near_limit <= 20000:
        raise ValueError('仅支持每意图2–20条及最多20000对的有界工程自检')
    original_sha = sha256(raw)
    provenance = read_source(source)
    if provenance.get('data_sha256', original_sha) != original_sha:
        raise ValueError('原始数据摘要与来源记录不符')
    rows = read_records(raw)
    required = {'flags', 'instruction', 'category', 'intent', 'response'}
    if not required.issubset(rows[0]) or any(not isinstance(row.get(k), str) or not row[k].strip() for row in rows for k in required):
        raise ValueError('Bitext原始字段缺失/空值，停止而非猜测字段')
    directory.mkdir(parents=True, mode=0o700)
    labels = sorted({row['intent'] for row in rows})
    for label in ('recover_password', 'get_refund', 'delivery_options'):
        if label not in labels:
            raise ValueError('缺少工程接入探针标签，不自行换用其他标签')
    labels_path = directory / 'observed-labels.json';write_json(labels_path, labels)
    full_audit = audit({'published': raw}, text_field='instruction', label_field='intent', max_comparisons=near_limit)
    write_json(directory / 'full-audit.json', full_audit)
    if full_audit['label_conflict_groups']:
        raise ValueError('原始输入有标签冲突，停止而非在工程子集中静默选边')
    try:
        prepare(raw, source, directory / 'full-import.jsonl', labels_path, text_field='instruction', label_field='intent')
        full_import = {'accepted': True}
    except ValueError as exc:
        if '重复' not in str(exc):
            raise
        full_import = {'accepted': False, 'reason': str(exc)}
    picked, counts, seen, selection, skipped_sensitive = [], Counter(), set(), [], 0
    for number, row in enumerate(rows, 1):
        if any(re.search(pattern, row['instruction'] + ' ' + row['response']) for pattern in SENSITIVE.values()):
            skipped_sensitive += 1
            continue
        key = normalize_text(row['instruction'])
        if counts[row['intent']] >= per_intent or key in seen:
            continue
        seen.add(key);picked.append(row);counts[row['intent']] += 1;selection.append(number)
    if any(counts[label] != per_intent for label in labels):
        raise ValueError('合规唯一输入不足，停止而非自动改样本规模')
    sample = directory / 'engineering-subset.csv'
    with sample.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(picked)
    prepared = directory / 'engineering-input.jsonl'
    manifest = prepare(sample, source, prepared, labels_path, text_field='instruction', label_field='intent')
    # Zero thresholds deliberately exercise transport/routing; never deploy as calibrated settings.
    model = directory / 'model.json'
    train(prepared, source, model, threshold=0.0, margin=0.0,
          config={'ngram_range': [1, 3], 'max_features': 10000, 'C': 1.0, 'max_iter': 1000, 'random_state': 0})
    loaded = load_model(model);digest = loaded['artifact_sha256']
    assert load_model(model, expected_sha256=digest)['integrity'] == 'pinned'
    assert set(loaded['labels']) == set(labels)
    categories = [{'id': i + 1, 'name': label, 'keywords': ''} for i, label in enumerate(labels)]
    prediction = predict(picked[0]['instruction'], categories, model, expected_sha256=digest)
    assert prediction['source'] == 'model' and prediction['predicted_label'] in labels
    integration = exercise_tickets(directory, model, digest, picked)
    category_labels = defaultdict(set)
    for row in rows:category_labels[row['category']].add(row['intent'])
    assert sha256(raw) == original_sha
    report = {'purpose': 'Phase4A_engineering_feasibility_not_research', 'input_sha256': original_sha,
              'source_record_sha256': provenance['record_sha256'], 'sample_count': len(picked), 'label_count': len(labels),
              'rows': len(rows), 'fields': list(rows[0]), 'label_counts': dict(sorted(Counter(r['intent'] for r in rows).items())),
              'category_intents': {k: sorted(v) for k, v in sorted(category_labels.items())},
              'full_import': full_import, 'full_audit': full_audit, 'selected_original_rows': selection,
              'selection': 'first unique normalized input per original intent in file order; exclude email/long-digit pattern rows; software probe only',
              'sensitive_pattern_rows': {field: {name: sum(bool(re.search(pattern, r[field])) for r in rows)
                                               for name, pattern in SENSITIVE.items()} for field in ('instruction', 'response')},
              'sample_scan_excluded_rows': skipped_sensitive,
              'privacy_limit': 'pattern screening is not a full privacy review; response is never a model feature or automatic business answer',
              'model_sha256': digest, 'model_bytes': model.stat().st_size, 'prepared_sha256': manifest['output_sha256'],
              'prediction_probe_label': prediction['predicted_label'], 'in_sample_probes': True,
              'threshold': 0.0, 'margin': 0.0, 'formal_split': None, 'holdout_evaluation': False,
              'raw_bytes_unchanged': True, 'integration': integration}
    write_json(directory / 'trial-report.json', report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if not args.output.resolve().is_relative_to(ROOT / 'data/processed'):
            raise ValueError('CLI输出必须位于被忽略的data/processed新目录')
        result = run_trial(args.raw, args.source, args.output)
        print(json.dumps({key: result[key] for key in ('purpose', 'rows', 'sample_count', 'label_count', 'model_sha256', 'raw_bytes_unchanged')}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'工程试运行失败：{exc}\n')


if __name__ == '__main__':
    main()
