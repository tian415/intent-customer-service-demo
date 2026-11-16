"""DEMO-only synthetic cases verify engineering contracts, not model quality."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

# Tests run from backend; package deliberately remains at repository root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.dataset import read_dataset, read_source
from ml.intent import load_model, model_scores, normalize_text, predict

CATEGORIES = [{"id": 1, "name": "退款", "keywords": "退款,退钱"},
              {"id": 2, "name": "账户", "keywords": "密码，登录"}]


def test_rules_normalization_and_manual_boundary() -> None:
    assert normalize_text(" ＡBC\t中文\n ") == "abc 中文"
    result = predict("我需要退款", CATEGORIES)
    assert result["category_id"] == 1 and result["source"] == "rules"
    assert result["needs_manual"] is False
    assert "不是概率" in result["reason"]
    for text in ("", " \n", "查一下天气", "退款后无法登录"):
        assert predict(text, CATEGORIES)["needs_manual"] is True
    assert predict("退款", [{**CATEGORIES[0], "active": False}])["needs_manual"]
    assert predict("退款", [])["category_id"] is None


@pytest.mark.parametrize("payload", [None, "not-json", "[]", '{"format":"unknown"}'])
def test_model_unavailable_falls_back_to_rules(tmp_path: Path, payload: str | None) -> None:
    path = tmp_path / "model.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    result = predict("退款", CATEGORIES, path)
    assert result["category_id"] == 1 and result["source"] == "rules"
    assert "模型不可用" in result["reason"]


def _model() -> dict:
    return {"format": "ticket-tfidf-logreg-v1", "labels": ["退款", "账户"],
            "vocabulary": {"退": 0}, "idf": [1.0], "coef": [[-3.0]],
            "intercept": [0.0], "threshold": 0.6, "margin": 0.15}


def test_safe_json_model_and_unknown_features(tmp_path: Path) -> None:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(_model()), encoding="utf-8")
    result = predict("退", CATEGORIES, path)
    assert result["source"] == "model" and result["category_id"] == 1
    assert predict("从未见过", CATEGORIES, path)["needs_manual"]
    assert predict("退款", [CATEGORIES[0]], path)["source"] == "rules"
    broken = _model()
    broken["coef"] = [[float("nan")]]
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert predict("退款", CATEGORIES, path)["source"] == "rules"
    broken["coef"] = [[1, 2]]
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError):
        load_model(path)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"name": "DEMO synthetic engineering fixture",
        "url": "local:pytest-generated", "license": "project synthetic fixture",
        "version": "test-v1", "approved_by": "test fixture only",
        "usage_approved": True, "privacy_reviewed": True}), encoding="utf-8")
    return source


def _dataset(path: Path, rows: list[tuple[str, str]]) -> Path:
    path.write_text("\n".join(json.dumps({"text": text, "label": label}, ensure_ascii=False)
                              for text, label in rows), encoding="utf-8")
    return path


def test_dataset_empty_duplicate_and_source_rejected(tmp_path: Path) -> None:
    for rows in ([], [("", "a")], [("ＡＢＣ", "a"), ("abc", "b")]):
        with pytest.raises(ValueError):
            read_dataset(_dataset(tmp_path / "invalid.jsonl", rows))
    source = _source(tmp_path)
    document = json.loads(source.read_text())
    document["usage_approved"] = False
    source.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="人工批准"):
        read_source(source)
    csv = tmp_path / "valid.csv"
    csv.write_text("text,label\n退款测试,refund\n", encoding="utf-8-sig")
    assert read_dataset(csv)[1] == ["refund"]


@pytest.mark.parametrize("class_count", [2, 3])
def test_export_matches_sklearn_and_evaluation_leakage(tmp_path: Path, class_count: int) -> None:
    pytest.importorskip("sklearn")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from ml.train import train
    from ml.evaluate import evaluate

    rows = [("退款申请", "退款"), ("退钱处理", "退款"), ("退款问题", "退款"),
            ("登录密码", "账户"), ("账户登录", "账户"), ("重置密码", "账户")]
    if class_count == 3:
        rows += [("快递运输", "物流"), ("查询快递", "物流"), ("包裹运输", "物流")]
    data = _dataset(tmp_path / "train.jsonl", rows)
    source, output = _source(tmp_path), tmp_path / "model.json"
    train(data, source, output, threshold=0.0, margin=0.0)
    model = load_model(output)
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3),
                                 preprocessor=normalize_text, lowercase=False, max_features=10000)
    texts, labels, _ = read_dataset(data)
    matrix = vectorizer.fit_transform(texts)
    classifier = LogisticRegression(max_iter=1000, random_state=0).fit(matrix, labels)
    for text in ("退款测试", "用户密码", "ABC 中文\n　快递"):
        expected = classifier.predict_proba(vectorizer.transform([text]))[0]
        assert model_scores(text, model) == pytest.approx(expected.tolist(), abs=1e-12)
    with pytest.raises(ValueError, match="泄漏"):
        evaluate(data, source, output, tmp_path / "leak.json")
    test = _dataset(tmp_path / "test.jsonl", [("申请退款服务", "退款"), ("忘记登录密码", "账户")])
    report = evaluate(test, source, output, tmp_path / "report.json")
    assert 0 <= report["accuracy"] <= 1 and 0 <= report["macro_f1"] <= 1
    assert report["test"]["samples"] == 2
    assert report["purpose"] == "engineering_only_not_research_conclusion"
    with pytest.raises(ValueError, match="输出已存在"):
        train(data, source, output)
    unseen = _dataset(tmp_path / "unseen.jsonl", [("没有这个标签", "new")])
    with pytest.raises(ValueError, match="未见标签"):
        evaluate(unseen, source, output, tmp_path / "unseen-report.json")


def test_predict_cli_without_sklearn(tmp_path: Path) -> None:
    categories = tmp_path / "categories.json"
    categories.write_text(json.dumps(CATEGORIES), encoding="utf-8")
    # -S disables site-packages; rules must remain standard-library only.
    run = subprocess.run([sys.executable, "-S", "-m", "ml.predict", "--text", "我要退款",
                          "--categories", str(categories)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["category_id"] == 1
