"""Inspect a trusted numeric JSON artifact without sklearn or executable weights."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.intent import FORMAT, load_model, resolve_mapping
from ml.jsonio import loads


def inspect_model(path: Path, categories: list[dict], *, expected_sha256: str | None = None, mapping_path: Path | None = None) -> dict:
    if (not isinstance(categories, list) or not all(isinstance(c, dict) and isinstance(c.get('name'), str) and c['name'].strip() for c in categories)):
        raise ValueError('类别清单须为含非空 name 的对象数组')
    active_names = [c['name'] for c in categories if c.get('active', True)]
    if len(set(active_names)) != len(active_names):
        raise ValueError('有效类别名称重复')
    model = load_model(path, expected_sha256=expected_sha256)
    mapping_version = None
    compatibility_error = None
    try:
        if mapping_path is not None and not all(type(c.get('id')) is int for c in categories):
            raise ValueError('显式映射检查需要类别整数id')
        _, mapping_version = resolve_mapping(model, [c for c in categories if c.get('active', True)], mapping_path)
        compatible = True
    except (ValueError, OSError) as exc:
        compatible = False
        compatibility_error = str(exc)
    metadata = model.get('metadata', {})
    training = metadata.get('training', {})
    return {'format': FORMAT, 'model_version': model['artifact_sha256'],
            'compatible': compatible, 'mapping_version': mapping_version, 'integrity': model['integrity'],
            'compatibility_mode': 'explicit_mapping' if mapping_path else 'same_name',
            'compatibility_error': compatibility_error,
            'model_labels': model['labels'], 'active_categories': active_names,
            'missing_in_model': sorted(set(active_names) - set(model['labels'])),
            'extra_model_labels': sorted(set(model['labels']) - set(active_names)),
            'features': len(model['vocabulary']), 'threshold': model['threshold'], 'margin': model['margin'],
            'provenance': 'recorded' if training.get('sha256') and metadata.get('source') else 'missing',
            'purpose': 'engineering_compatibility_check_not_model_quality_or_research_approval'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--categories', type=Path, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--label-map', type=Path)
    args = parser.parse_args()
    try:
        report = inspect_model(args.model, loads(args.categories.read_text(encoding='utf-8')), expected_sha256=args.expected_sha256, mapping_path=args.label_map)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        if not report['compatible']:
            parser.exit(2)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'检查失败：{exc}\n')


if __name__ == '__main__':
    main()
