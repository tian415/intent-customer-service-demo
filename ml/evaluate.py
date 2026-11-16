"""Evaluate an explicitly separate local test file; no automatic split."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

from ml.dataset import read_dataset, read_source, validate_partition
from ml.intent import load_model, model_choice


def evaluate(test_path: Path, source_path: Path, model_path: Path, output: Path, *, data_partition: str | None = None) -> dict:
    import sklearn
    from sklearn.metrics import accuracy_score, classification_report, f1_score

    texts, labels, metadata = read_dataset(test_path)
    validate_partition(metadata, data_partition)
    source, model = read_source(source_path), load_model(model_path)
    training = model.get("metadata", {}).get("training", {})
    import re
    for key in ('text_hashes', 'group_hashes'):
        values = training.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{64}', v) for v in values):
            raise ValueError('模型训练元信息摘要格式无效')
    if not training.get("text_hashes"):
        raise ValueError("模型缺少训练文本摘要，不能检查泄漏")
    if set(metadata['group_hashes']) & set(training.get('group_hashes', [])):
        raise ValueError('检测到训练/测试分组或会话交叉；停止评估')
    if set(metadata["text_hashes"]) & set(training["text_hashes"]):
        raise ValueError("检测到训练/测试文本泄漏（规范化完全相同）；停止评估")
    if set(labels) - set(model["labels"]):
        raise ValueError("测试包含训练未见标签；需人工确定开放集评估方案")
    predictions = [model_choice(text, model)[0] or "__manual__" for text in texts]
    report = {"purpose": "engineering_only_not_research_conclusion",
              "created_at": datetime.now(timezone.utc).isoformat(),
              "model_sha256": model['artifact_sha256'], "model_metadata": model.get("metadata"),
              "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__},
              "test": metadata, "source": source,
              "accuracy": accuracy_score(labels, predictions),
              "macro_f1": f1_score(labels, predictions, labels=model["labels"], average="macro", zero_division=0),
              "manual_count": predictions.count("__manual__"),
              "classification_report": classification_report(labels, predictions,
                  labels=model["labels"], output_dict=True, zero_division=0),
              "limitations": "仅当前输入工程评估；精确摘要不能发现近似改写泄漏，人工需核查划分、来源与业务适用性；不构成研究结论"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("test", "source", "model", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument('--data-partition', help='输入含原分区标记时必须显式匹配')
    args = parser.parse_args()
    try:
        report = evaluate(args.test, args.source, args.model, args.output, data_partition=args.data_partition)
        print(json.dumps({key: report[key] for key in ("accuracy", "macro_f1", "manual_count", "purpose")}))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2, f"评估失败：{exc}\n")


if __name__ == "__main__":
    main()
