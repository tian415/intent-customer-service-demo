"""Explicit three-file engineering run using existing tools; no split or model selection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from ml.audit import audit
from ml.dataset import read_dataset, read_records, read_source, sha256
from ml.evaluate import evaluate
from ml.jsonio import loads
from ml.prepare import prepare
from ml.train import train
from ml.training_config import resolve_config

ROOT = Path(__file__).resolve().parents[1]
PARTITIONS = ('train', 'validation', 'test')


def keys(value: dict, expected: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f'{name}字段必须完整且无未知项：{sorted(expected)}')


def pinned_file(value: dict, base: Path) -> tuple[Path, str]:
    keys(value, {'path', 'sha256'}, '文件配置')
    if not isinstance(value['path'], str) or not value['path'].strip() or not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256']):
        raise ValueError('文件须指定本地路径及64位小写SHA-256')
    path = (base / value['path']).resolve()
    if sha256(path) != value['sha256']:
        raise ValueError('文件摘要与显式配置不符')
    return path, value['sha256']


def write_report(path: Path, value: dict | list) -> None:
    import os
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run(config_path: Path) -> dict:
    config_path = config_path.resolve()
    raw_config = config_path.read_bytes()
    config = loads(raw_config.decode('utf-8'))
    keys(config, {'format', 'purpose', 'data', 'splits', 'model', 'leakage', 'output'}, '运行配置')
    if config['format'] != 'ticket-run-v1' or config['purpose'] != 'engineering_preparation':
        raise ValueError('此入口仅支持显式engineering_preparation，不构成正式实验批准')
    data, model, leakage = config['data'], config['model'], config['leakage']
    keys(data, {'version', 'source', 'text_field', 'label_field', 'group_field', 'partition_field', 'labels'}, '数据配置')
    keys(model, {'parameters', 'threshold', 'margin'}, '模型配置')
    keys(model['parameters'], {'ngram_range', 'max_features', 'C', 'max_iter', 'random_state'}, '模型参数')
    keys(leakage, {'similarity_threshold', 'max_comparisons'}, '泄漏检查配置')
    keys(config['splits'], set(PARTITIONS), '三分区配置')
    settings = resolve_config(model['parameters'])
    if settings['data_partition'] is not None:
        raise ValueError('原分区名称由各文件配置提供，不能在模型参数覆盖')
    for name in ('text_field', 'label_field'):
        if not isinstance(data[name], str) or not data[name].strip():
            raise ValueError('输入字段与目标标签字段必须明确')
    for name in ('group_field', 'partition_field'):
        if data[name] is not None and (not isinstance(data[name], str) or not data[name].strip()):
            raise ValueError('分组/原分区字段须为明确名称或null')
    fields = [data[k] for k in ('text_field', 'label_field', 'group_field', 'partition_field') if data[k] is not None]
    if len(set(fields)) != len(fields):
        raise ValueError('文本、标签、分组和原分区不能复用同一字段')
    for value in (model['threshold'], model['margin'], leakage['similarity_threshold']):
        if type(value) not in (int, float) or not 0 <= value <= 1:
            raise ValueError('阈值须为[0,1]有限数值')
    if type(leakage['max_comparisons']) is not int or leakage['max_comparisons'] < 0:
        raise ValueError('比较上限须为非负整数')
    if not isinstance(config['output'], str) or not config['output'].strip():
        raise ValueError('必须明确新输出目录')
    output = (config_path.parent / config['output']).resolve()
    if not any(output.is_relative_to(ROOT / parent) for parent in ('data/processed', '.cache')):
        raise ValueError('输出必须在项目被忽略的data/processed或.cache目录')
    if output.exists():
        raise ValueError('输出目录已存在，拒绝覆盖任何产物')
    source_path, source_sha = pinned_file(data['source'], config_path.parent)
    source = read_source(source_path)
    if not isinstance(data['version'], str) or not data['version'].strip() or source['version'] != data['version']:
        raise ValueError('数据版本与已固定来源记录不一致')
    inputs, expected, original_partitions = {}, {source_path: source_sha}, []
    for name in PARTITIONS:
        spec = config['splits'][name]
        keys(spec, {'path', 'sha256', 'partition'}, f'{name}配置')
        path, digest = pinned_file({k: spec[k] for k in ('path', 'sha256')}, config_path.parent)
        inputs[name] = path;expected[path] = digest
        partition = spec['partition']
        if data['partition_field'] is None and partition is not None:
            raise ValueError('没有原分区字段，不能猜测分区名称')
        if data['partition_field'] is not None and (not isinstance(partition, str) or not partition.strip()):
            raise ValueError('须显式指定每个文件的原分区名称')
        original_partitions.append(partition)
        for row in read_records(path):
            if 'group_id' in row and data['group_field'] != 'group_id':
                raise ValueError('输入含已知group_id，必须明确保留该字段，不能静默丢弃')
            if 'source_partition' in row and data['partition_field'] != 'source_partition':
                raise ValueError('输入含原分区标记，必须明确核对，不能静默丢弃')
            if data['partition_field'] is not None and row.get(data['partition_field']) != partition:
                raise ValueError('分区文件混合、漏标或与配置不符；此入口不自动筛选/划分')
    if len(set(inputs.values())) != 3:
        raise ValueError('须显式提供三个独立文件，不自动从一个文件划分')
    if data['partition_field'] is not None and len(set(original_partitions)) != 3:
        raise ValueError('训练/验证/测试不能复用同一声明分区')
    output.mkdir(parents=True, mode=0o700)
    write_report(output / 'configuration.json', config)
    labels = output / 'labels.json';write_report(labels, data['labels'])
    prepared = {}
    for name, path in inputs.items():
        prepared[name] = output / f'{name}.jsonl'
        prepare(path, source_path, prepared[name], labels, text_field=data['text_field'], label_field=data['label_field'],
                group_field=data['group_field'], partition_field=data['partition_field'], partition=config['splits'][name]['partition'])
    audit_report = audit(prepared, **leakage)
    blockers = []
    for key, reason in [('cross_split_exact_groups', '跨分区精确文本重复'), ('cross_split_group_groups', '跨分区已知分组交叉'),
                        ('cross_split_near_duplicate_pairs', '已识别跨分区近似重复候选')]:
        if audit_report[key]:blockers.append(reason)
    if not audit_report['cross_split_near_complete']:
        blockers.append('跨分区近似检查覆盖不足（上限或长文本跳过）')
    training_labels = set(read_dataset(prepared['train'])[1])
    if any(set(read_dataset(prepared[name])[1]) - training_labels for name in ('validation', 'test')):
        blockers.append('验证/测试含训练未见标签，需人工决定开放集方案')
    warnings = ['未知模板族/语义关联未获认证，不能声称消除所有数据泄漏']
    if data['group_field'] is None:warnings.append('未提供已知分组字段，未验证会话/源模板交叉')
    write_report(output / 'preflight.json', {'audit': audit_report, 'blockers': blockers, 'warnings': warnings})
    if blockers:
        raise ValueError('；'.join(blockers) + '；已保存preflight.json，未训练模型')
    train(prepared['train'], source_path, output / 'model.json', threshold=model['threshold'], margin=model['margin'],
          config={**settings, 'data_partition': config['splits']['train']['partition']})
    reports = {name: evaluate(prepared[name], source_path, output / 'model.json', output / f'{name}-metrics.json',
                              data_partition=config['splits'][name]['partition']) for name in ('validation', 'test')}
    for path, digest in expected.items():
        if sha256(path) != digest:
            raise ValueError('运行期间输入/来源改变，不生成完成记录；保留中间产物供核查')
    report = {'purpose': config['purpose'], 'config_sha256': hashlib.sha256(raw_config).hexdigest(),
              'data_version': data['version'], 'source_record_sha256': source_sha,
              'partitions': {name: {'path': str(path), 'sha256': expected[path], 'prepared_sha256': sha256(prepared[name])} for name, path in inputs.items()},
              'fit_partition': 'train_only', 'automatic_split': False, 'automatic_parameter_selection': False,
              'template_group_independence': 'not_certified', 'warnings': warnings, 'audit': audit_report,
              'validation': reports['validation'], 'test': reports['test']}
    write_report(output / 'completed.json', report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.config)
        print(json.dumps({'purpose': report['purpose'], 'data_version': report['data_version'],
                          'fit_partition': report['fit_partition'], 'template_group_independence': report['template_group_independence']}))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'运行拒绝或失败：{exc}\n')


if __name__ == '__main__':
    main()
