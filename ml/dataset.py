"""Explicit-source, loss-aware local data reading; never downloads or splits data."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from ml.intent import normalize_text
from ml.jsonio import loads


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode('utf-8')).hexdigest()


def read_source(path: Path) -> dict:
    source = loads(path.read_text(encoding='utf-8'))
    if not isinstance(source, dict):
        raise ValueError('来源记录必须为 JSON 对象')
    for key in ('name', 'url', 'license', 'version', 'approved_by'):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise ValueError(f'来源记录缺少 {key}')
    if source.get('usage_approved') is not True or source.get('privacy_reviewed') is not True:
        raise ValueError('数据使用和隐私审查必须已获确认；工具不能代替人工批准')
    return {**source, 'record_sha256': sha256(path)}


def read_records(path: Path) -> list[dict]:
    """Read records without discarding fields or duplicate keys/columns."""
    if path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            try:
                headers = reader.fieldnames
            except csv.Error as exc:
                raise ValueError('CSV 表头格式错误') from exc
            if not headers or any(not name for name in headers) or len(set(headers)) != len(headers):
                raise ValueError('CSV 列名为空或重复')
            try:
                rows = list(reader)
            except csv.Error as exc:
                raise ValueError(f'CSV 行格式错误（第 {reader.line_num} 行）') from exc
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError('CSV 数据行的列值数量与表头不一致')
    elif path.suffix.lower() == '.jsonl':
        rows = []
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if line.strip():
                try:
                    rows.append(loads(line))
                except ValueError as exc:
                    raise ValueError(f'JSONL 第 {number} 行格式无效：{exc}') from exc
    else:
        raise ValueError('数据只支持 CSV 或 JSONL')
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError('数据集为空或记录不是对象')
    return rows


def validate_records(rows: list[dict], *, allow_duplicates: bool = False) -> tuple[list[str], list[str], dict]:
    texts, labels, hashes, group_hashes = [], [], set(), set()
    partitions = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row.get('text'), str) or not isinstance(row.get('label'), str):
            raise ValueError(f'第 {index} 行须有字符串 text/label')
        text, label = normalize_text(row['text']), row['label'].strip()
        if not text or not label or label == '__manual__':
            raise ValueError(f'第 {index} 行文本/标签为空或使用保留标签')
        digest = text_hash(text)
        if digest in hashes and not allow_duplicates:
            raise ValueError(f'第 {index} 行文本规范化后重复（含标签冲突）')
        hashes.add(digest)
        if 'group_id' in row:
            group = row['group_id']
            if not isinstance(group, str) or not group.strip():
                raise ValueError(f'第 {index} 行 group_id 必须是非空字符串')
            group_hashes.add(hashlib.sha256(group.encode('utf-8')).hexdigest())
        if 'source_partition' in row:
            partition = row['source_partition']
            if not isinstance(partition, str) or not partition.strip():
                raise ValueError(f'第 {index} 行原分区必须是非空字符串')
            partitions.append(partition)
        texts.append(text)
        labels.append(label)
    if not texts:
        raise ValueError('数据集为空')
    return texts, labels, {'samples': len(texts), 'labels': sorted(set(labels)),
                           'text_hashes': sorted(hashes), 'group_hashes': sorted(group_hashes),
                           'partitions': sorted(set(partitions)), 'partitioned_rows': len(partitions)}


def read_dataset(path: Path) -> tuple[list[str], list[str], dict]:
    texts, labels, metadata = validate_records(read_records(path))
    return texts, labels, {'sha256': sha256(path), **metadata}


def validate_partition(metadata: dict, expected: str | None) -> None:
    partitions = metadata.get('partitions', [])
    if partitions:
        if metadata['partitioned_rows'] != metadata['samples'] or len(partitions) != 1 or expected != partitions[0]:
            raise ValueError('数据带原分区标记，须显式指定匹配的单一分区；不混用或自动重划分')
    elif expected is not None:
        raise ValueError('输入没有原分区标记，无法核对指定分区')
