"""Replaceable local intent inference, with conservative rule/manual fallback."""
from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import unicodedata
from typing import Any
from ml.jsonio import loads

FORMAT = "ticket-tfidf-logreg-v1"
MAX_MODEL_BYTES = 64_000_000


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def features(text: str, ngram_range: tuple[int, int] = (1, 3)) -> Counter[str]:
    text = normalize_text(text)
    return Counter(text[i:i + n] for n in range(ngram_range[0], ngram_range[1] + 1) for i in range(len(text) - n + 1))


def load_model(path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    """Read numeric JSON only. Callers must configure a trusted local path."""
    with path.open('rb') as stream:
        raw = stream.read(MAX_MODEL_BYTES + 1)
    if len(raw) > MAX_MODEL_BYTES:
        raise ValueError("模型过大")
    digest = hashlib.sha256(raw).hexdigest()
    integrity = 'unverified'
    if expected_sha256 is not None:
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256) or digest != expected_sha256:
            raise ValueError('模型完整性摘要与固定配置不一致')
        integrity = 'pinned'
    manifest_path = path.with_suffix(path.suffix + '.manifest.json')
    if manifest_path.exists():
        manifest = loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or manifest.get('model_sha256') != digest:
            raise ValueError('模型完整性摘要与产物清单不一致')
        if integrity != 'pinned':
            integrity = 'manifest'
    model = loads(raw.decode('utf-8'))
    if not isinstance(model, dict) or model.get("format") != FORMAT:
        raise ValueError("模型格式不支持")
    if 'metadata' in model:
        metadata = model['metadata']
        if not isinstance(metadata, dict) or ('training' in metadata and not isinstance(metadata['training'], dict)):
            raise ValueError('模型元信息 metadata 必须是对象')
    labels, vocab = model.get("labels"), model.get("vocabulary")
    if (not isinstance(labels, list) or len(labels) < 2
            or not all(isinstance(x, str) and x.strip() for x in labels)
            or len(set(labels)) != len(labels)
            or not isinstance(vocab, dict) or not vocab
            or not all(isinstance(k, str) and 1 <= len(k) <= 3 for k in vocab)
            or any(type(v) is not int for v in vocab.values())
            or sorted(vocab.values()) != list(range(len(vocab)))):
        raise ValueError("标签或词表无效")
    ngrams = model.get('ngram_range', [1, 3])
    if not isinstance(ngrams, list) or len(ngrams) != 2 or not all(type(n) is int for n in ngrams) or not 1 <= ngrams[0] <= ngrams[1] <= 3:
        raise ValueError('模型特征范围无效')
    if not all(ngrams[0] <= len(key) <= ngrams[1] for key in vocab):
        raise ValueError('词表与模型特征范围不一致')
    model['ngram_range'] = ngrams
    size = len(vocab)
    rows = 1 if len(labels) == 2 else len(labels)
    def numeric(values: Any, length: int) -> bool:
        return (isinstance(values, list) and len(values) == length
                and all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 1e12 for v in values))
    if (not numeric(model.get("idf"), size) or any(v <= 0 for v in model["idf"])
            or not numeric(model.get("intercept"), rows)
            or not isinstance(model.get("coef"), list) or len(model["coef"]) != rows
            or not all(numeric(row, size) for row in model["coef"])):
        raise ValueError("模型数值维度无效")
    for field in ("threshold", "margin"):
        value = model.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("模型阈值无效")
    model['artifact_sha256'] = digest
    model['integrity'] = integrity
    return model


def model_scores(text: str, model: dict[str, Any]) -> list[float]:
    counts = features(text, tuple(model.get('ngram_range', [1, 3])))
    vector = {model["vocabulary"][key]: count * model["idf"][model["vocabulary"][key]]
              for key, count in counts.items() if key in model["vocabulary"]}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    norm = norm or 1.0
    logits = [bias + sum(row[index] * value / norm for index, value in vector.items())
              for row, bias in zip(model["coef"], model["intercept"], strict=True)]
    if len(model["labels"]) == 2:
        z = logits[0]
        p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
        return [1 - p, p]
    exp = [math.exp(value - max(logits)) for value in logits]
    return [value / sum(exp) for value in exp]


def model_choice(text: str, model: dict[str, Any]) -> tuple[str | None, float]:
    if not any(key in model["vocabulary"] for key in features(text, tuple(model.get('ngram_range', [1, 3])))):
        return None, 0.0
    scores = model_scores(text, model)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    best, runner_up = (scores[order[0]], scores[order[1]])
    if best < model["threshold"] or best - runner_up <= model["margin"]:
        return None, best
    return model["labels"][order[0]], best


def _result(category: dict | None, score: float, source: str, reason: str, model_version: str | None = None, *, predicted_label: str | None = None, mapping_version: str | None = None, integrity: str = 'not_applicable') -> dict:
    return {"category_id": category["id"] if category else None,
            "category_name": category["name"] if category else None,
            "score": round(score, 6), "source": source,
            "needs_manual": category is None, "reason": reason, "model_version": model_version, "predicted_label": predicted_label,
            "mapping_version": mapping_version, "integrity": integrity}


def _rules(text: str, categories: list[dict], prefix: str = "") -> dict:
    matches = []
    for category in categories:
        keywords = {normalize_text(k) for k in re.split(r"[,，]", category.get("keywords", ""))}
        hits = [word for word in keywords if word and word in text]
        if hits:
            matches.append((category, hits))
    # Multiple category hits are ambiguous regardless of keyword count.
    if len(matches) == 1:
        category, hits = matches[0]
        score = min(1.0, sum(len(word) for word in hits) / max(1, len(text)))
        return _result(category, score, "rules", prefix + "唯一类别关键词命中；规则分数不是概率")
    reason = "多个类别关键词命中，需人工分类" if matches else "未命中类别关键词，需人工分类"
    return _result(None, 0.0, "fallback", prefix + reason)


def resolve_mapping(model: dict, categories: list[dict], path: Path | None) -> tuple[dict, str | None]:
    if path is None:
        names = [c['name'] for c in categories]
        if set(model['labels']) != set(names) or len(names) != len(set(names)):
            raise ValueError('模型标签与当前类别不匹配，需要明确映射')
        return {c['name']: c for c in categories}, None
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError('映射文件过大')
    document = loads(raw.decode('utf-8'))
    if (not isinstance(document, dict) or document.get('approved') is not True
            or not isinstance(document.get('approved_by'), str) or not document['approved_by'].strip()
            or document.get('model_sha256') != model['artifact_sha256']):
        raise ValueError('映射须明确确认并匹配实际模型版本')
    labels = document.get('labels')
    if not isinstance(labels, dict) or set(labels) != set(model['labels']):
        raise ValueError('映射须显式覆盖每个模型标签，未知类别不自动猜测')
    by_id = {c['id']: c for c in categories}
    mapping = {}
    for label, identity in labels.items():
        if identity is not None and (type(identity) is not int or identity not in by_id):
            raise ValueError('映射目标类别不存在或已停用')
        mapping[label] = by_id[identity] if identity is not None else None
    return mapping, hashlib.sha256(raw).hexdigest()


def predict(text: str, categories: list[dict], model_path: Path | None = None, *,
            expected_sha256: str | None = None, mapping_path: Path | None = None) -> dict:
    normalized = normalize_text(text)
    categories = [c for c in categories if c.get('active', True)]
    if not normalized:
        return _result(None, 0.0, 'fallback', '文本为空，需人工分类')
    if model_path is not None:
        try:
            model = load_model(model_path, expected_sha256=expected_sha256)
            mapping, mapping_version = resolve_mapping(model, categories, mapping_path)
            label, score = model_choice(normalized, model)
            trace = {'mapping_version': mapping_version, 'integrity': model['integrity']}
            if label is None:
                return _result(None, score, 'fallback', '模型证据不足或类别接近，需人工分类', model['artifact_sha256'], **trace)
            category = mapping[label]
            reason = '本地模型预测；分数未经真实业务校准' if category else '模型标签被明确映射为人工处理'
            return _result(category, score, 'model', reason, model['artifact_sha256'], predicted_label=label, **trace)
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return _rules(normalized, categories, '模型不可用（含文件、完整性或映射校验失败），已回退规则；')
    return _rules(normalized, categories)
