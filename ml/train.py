"""Configurable local engineering baseline; no automatic data or research choices."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import warnings

from ml.dataset import read_dataset, read_source, validate_partition
from ml.intent import FORMAT, load_model, normalize_text
from ml.jsonio import loads
from ml.training_config import resolve_config


def train(train_path: Path, source_path: Path, output: Path,
          threshold: float = 0.6, margin: float = 0.15, *, config: dict | None = None) -> dict:
    settings = resolve_config(config)
    if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
        raise ValueError('threshold/margin 必须位于 [0,1]')
    manifest_path = output.with_suffix(output.suffix + '.manifest.json')
    if output.exists() or manifest_path.exists():
        raise ValueError('输出已存在；请指定新路径，避免覆盖模型或清单')
    import sklearn
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    texts, labels, metadata = read_dataset(train_path)
    validate_partition(metadata, settings['data_partition'])
    source = read_source(source_path)
    if len(set(labels)) < 2:
        raise ValueError('训练至少需要两个类别')
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=tuple(settings['ngram_range']),
                                 preprocessor=normalize_text, lowercase=False,
                                 max_features=settings['max_features'])
    matrix = vectorizer.fit_transform(texts)
    classifier = LogisticRegression(C=settings['C'], max_iter=settings['max_iter'], random_state=settings['random_state'])
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        classifier.fit(matrix, labels)
    model = {'format': FORMAT, 'labels': classifier.classes_.tolist(),
             'ngram_range': settings['ngram_range'],
             'vocabulary': {key: int(value) for key, value in vectorizer.vocabulary_.items()},
             'idf': vectorizer.idf_.tolist(), 'coef': classifier.coef_.tolist(),
             'intercept': classifier.intercept_.tolist(), 'threshold': threshold, 'margin': margin,
             'metadata': {'purpose': 'engineering_only_not_research_conclusion',
                          'created_at': datetime.now(timezone.utc).isoformat(),
                          'python': platform.python_version(), 'sklearn': sklearn.__version__,
                          'training': metadata, 'source': source,
                          'parameters': {'analyzer': 'char', **settings}}}
    raw = (json.dumps(model, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    manifest = {'format': 'ticket-model-manifest-v1', 'model_sha256': hashlib.sha256(raw).hexdigest(),
                'training_sha256': metadata['sha256'], 'source_record_sha256': source['record_sha256'],
                'parameters': model['metadata']['parameters'], 'purpose': model['metadata']['purpose']}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    created = []
    try:
        for path, content in [(output, raw), (manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))]:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
        load_model(output)
    except (OSError, ValueError):
        for path in created:
            path.unlink()
        raise
    return model['metadata']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, help='显式工程配置JSON，不自动选择算法或数据分区')
    parser.add_argument('--threshold', type=float, default=0.6)
    parser.add_argument('--margin', type=float, default=0.15)
    args = parser.parse_args()
    try:
        config = loads(args.config.read_text(encoding='utf-8')) if args.config else None
        metadata = train(args.train, args.source, args.output, args.threshold, args.margin, config=config)
        print(json.dumps({'purpose': metadata['purpose'], 'samples': metadata['training']['samples'],
                          'parameters': metadata['parameters'], 'model_sha256': load_model(args.output)['artifact_sha256']}, ensure_ascii=False))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f'训练失败：{exc}\n')


if __name__ == '__main__':
    main()
