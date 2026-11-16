"""Run local inference against explicit current category JSON."""
import argparse
import json
from pathlib import Path

from ml.intent import predict
from ml.jsonio import loads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True)
    parser.add_argument("--categories", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--label-map', type=Path)
    args = parser.parse_args()
    try:
        categories = loads(args.categories.read_text(encoding="utf-8"))
        if (not isinstance(categories, list) or not all(isinstance(c, dict)
                and type(c.get("id")) is int and isinstance(c.get("name"), str)
                and isinstance(c.get("keywords", ""), str) for c in categories)):
            raise ValueError("类别文件必须为含 id/name/keywords 的数组")
        print(json.dumps(predict(args.text, categories, args.model, expected_sha256=args.expected_sha256, mapping_path=args.label_map), ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"推理失败：{exc}\n")


if __name__ == "__main__":
    main()
