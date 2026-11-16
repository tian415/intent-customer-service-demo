"""Explicit local field/label conversion; preserves source files and partitions."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from ml.dataset import read_records, read_source, sha256, validate_records
from ml.jsonio import loads


def prepare(input_path: Path, source_path: Path, output_path: Path, labels_path: Path, *,
            text_field: str = 'text', label_field: str = 'label', mapping_path: Path | None = None,
            partition_field: str | None = None, partition: str | None = None,
            group_field: str | None = None, format: str = 'records') -> dict:
    inputs = [input_path, source_path, labels_path] + ([mapping_path] if mapping_path else [])
    manifest_path = output_path.with_suffix(output_path.suffix + '.manifest.json')
    if any(output_path.resolve() == p.resolve() or manifest_path.resolve() == p.resolve() for p in inputs):
        raise ValueError('输出不能覆盖原始输入或配置文件')
    if output_path.exists() or manifest_path.exists():
        raise ValueError('输出或清单已存在，须选择新路径')
    source = read_source(source_path)
    labels = loads(labels_path.read_text(encoding='utf-8'))
    if (not isinstance(labels, list) or not labels or not all(isinstance(x, str) and x.strip() == x and x and x != '__manual__' for x in labels)
            or len(set(labels)) != len(labels)):
        raise ValueError('允许标签必须是显式、非空、无重复的字符串数组')
    mapping = loads(mapping_path.read_text(encoding='utf-8')) if mapping_path else None
    if mapping is not None and (not isinstance(mapping, dict) or not all(isinstance(k, str) and k and isinstance(v, str) and v in labels for k, v in mapping.items())):
        raise ValueError('标签映射必须显式覆盖源标签，目标须属于允许标签')
    if format == 'clinc':
        document = loads(input_path.read_text(encoding='utf-8'))
        if not partition or partition_field or not isinstance(document, dict) or partition not in document:
            raise ValueError('CLINC 格式须显式选择已有 partition 键，不自动合并或划分')
        pairs = document[partition]
        if not isinstance(pairs, list) or not all(isinstance(p, list) and len(p) == 2 for p in pairs):
            raise ValueError('CLINC 分区必须为 [text,label] 数组')
        records = [{text_field: pair[0], label_field: pair[1]} for pair in pairs]
    elif format == 'records':
        if bool(partition_field) != bool(partition):
            raise ValueError('partition_field 与 partition 必须一起显式提供')
        records = read_records(input_path)
    else:
        raise ValueError('未知源文件格式')
    result = []
    for number, row in enumerate(records, 1):
        if partition_field:
            if partition_field not in row:
                raise ValueError(f'第 {number} 行缺少原有分区字段')
            if row[partition_field] != partition:
                continue
        text, label = row.get(text_field), row.get(label_field)
        if not isinstance(text, str) or not isinstance(label, str):
            raise ValueError(f'第 {number} 行指定文本/标签字段不是字符串')
        if mapping is not None:
            if label not in mapping:
                raise ValueError(f'第 {number} 行源标签没有显式映射')
            label = mapping[label]
        if label not in labels:
            raise ValueError(f'第 {number} 行标签不在允许清单；不自动改标签或丢弃记录')
        item = {'text': text, 'label': label}
        if group_field:
            group = row.get(group_field)
            if isinstance(group, bool) or not isinstance(group, (str, int)) or not str(group).strip():
                raise ValueError(f'第 {number} 行缺少有效分组标识')
            item['group_id'] = str(group)
        item['source_row'] = number
        if partition:
            item['source_partition'] = partition
        result.append(item)
    _, target_labels, metadata = validate_records(result)
    report = {'format': 'ticket-dataset-v1', 'purpose': 'engineering_preparation_not_research_approval',
              'input_sha256': sha256(input_path), 'source': source,
              'labels_sha256': sha256(labels_path), 'mapping_sha256': sha256(mapping_path) if mapping_path else None,
              'source_format': format, 'text_field': text_field, 'label_field': label_field,
              'group_field': group_field, 'partition_field': partition_field, 'partition': partition,
              'input_records': len(records), 'automatic_split': False,
              **metadata, 'label_counts': dict(sorted(Counter(target_labels).items()))}
    encoded = ''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in result)
    import hashlib
    report['output_sha256'] = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with output_path.open('x', encoding='utf-8') as stream:
            created.append(output_path)
            stream.write(encoded)
        with manifest_path.open('x', encoding='utf-8') as stream:
            created.append(manifest_path)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except OSError:
        for path in created:
            path.unlink()
        raise
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'source', 'output', 'labels'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--text-field', default='text')
    parser.add_argument('--label-field', default='label')
    parser.add_argument('--mapping', type=Path)
    parser.add_argument('--partition-field')
    parser.add_argument('--partition')
    parser.add_argument('--group-field')
    parser.add_argument('--format', choices=['records', 'clinc'], default='records')
    args = parser.parse_args()
    try:
        report = prepare(args.input, args.source, args.output, args.labels, text_field=args.text_field,
                         label_field=args.label_field, mapping_path=args.mapping, partition_field=args.partition_field,
                         partition=args.partition, group_field=args.group_field, format=args.format)
        print(json.dumps({key: report[key] for key in ('samples', 'label_counts', 'input_sha256', 'output_sha256', 'automatic_split')}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'准备失败：{exc}\n')


if __name__ == '__main__':
    main()
