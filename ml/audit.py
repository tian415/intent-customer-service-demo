"""Read-only data checks. Similarity candidates are not formal evaluation criteria."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
from itertools import combinations, chain, product
import json
from pathlib import Path

from ml.dataset import read_records, sha256, text_hash, validate_records


def audit(splits: dict[str, Path], *, similarity_threshold: float = 0.9, max_comparisons: int = 10000,
          text_field: str = 'text', label_field: str = 'label') -> dict:
    if not splits or not 0 <= similarity_threshold <= 1 or max_comparisons < 0:
        raise ValueError('需提供命名文件；相似阈值在[0,1]，比较上限不能为负')
    summary, all_rows, by_split = {}, [], {}
    exact, groups = defaultdict(list), defaultdict(list)
    for name, path in splits.items():
        if not name.strip():
            raise ValueError('分区名称不能为空')
        records = [{**row, 'text': row.get(text_field), 'label': row.get(label_field)} for row in read_records(path)]
        texts, labels, _ = validate_records(records, allow_duplicates=True)
        summary[name] = {'sha256': sha256(path), 'samples': len(texts), 'label_counts': dict(sorted(Counter(labels).items())),
                         'min_text_chars': min(map(len, texts)), 'max_text_chars': max(map(len, texts))}
        by_split[name] = []
        for number, (text, label, raw) in enumerate(zip(texts, labels, records, strict=True), 1):
            ref = {'split': name, 'row': number, 'label': label}
            exact[text_hash(text)].append(ref)
            if 'group_id' in raw:
                digest = hashlib.sha256(raw['group_id'].encode('utf-8')).hexdigest()
                groups[digest].append(ref)
            all_rows.append((text, ref))
            by_split[name].append((text, ref))
    duplicate_groups = [items for items in exact.values() if len(items) > 1]
    group_overlaps = [items for items in groups.values() if len({r['split'] for r in items}) > 1]
    near_count, cross_near_count, compared, long_skipped, near_examples = 0, 0, 0, 0, []
    total_pairs = len(all_rows) * (len(all_rows) - 1) // 2
    split_pairs = list(combinations(by_split.values(), 2))
    cross_total = sum(len(a) * len(b) for a, b in split_pairs)
    cross_compared, cross_long_skipped = 0, 0
    # Spend bounded work on cross-file leakage before within-file similarity.
    cross_pairs = chain.from_iterable(product(a, b) for a, b in split_pairs)
    within_pairs = chain.from_iterable(combinations(rows, 2) for rows in by_split.values())
    for (first, ref_a), (second, ref_b) in chain(cross_pairs, within_pairs):
        if compared >= max_comparisons:
            break
        compared += 1
        is_cross = ref_a['split'] != ref_b['split']
        cross_compared += int(is_cross)
        if first == second:
            continue
        if max(len(first), len(second)) > 1000:
            long_skipped += 1
            cross_long_skipped += int(is_cross)
            continue
        # Safe upper bound avoids costly matching of very different lengths.
        if 2 * min(len(first), len(second)) / (len(first) + len(second)) < similarity_threshold:
            continue
        # ratio can depend on argument order; either direction is a review candidate.
        score = max(SequenceMatcher(None, first, second, autojunk=False).ratio(),
                    SequenceMatcher(None, second, first, autojunk=False).ratio())
        if score >= similarity_threshold:
            near_count += 1
            cross_near_count += int(is_cross)
            if len(near_examples) < 20:
                near_examples.append({'first': ref_a, 'second': ref_b, 'similarity': round(score, 6)})
    return {'purpose': 'engineering_data_risk_report_not_research_result', 'splits': summary,
            'text_field': text_field, 'label_field': label_field,
            'exact_duplicate_groups': len(duplicate_groups),
            'cross_split_exact_groups': sum(len({r['split'] for r in rows}) > 1 for rows in duplicate_groups),
            'label_conflict_groups': sum(len({r['label'] for r in rows}) > 1 for rows in duplicate_groups),
            'cross_split_group_groups': len(group_overlaps), 'exact_examples': duplicate_groups[:20], 'group_examples': group_overlaps[:20],
            'near_duplicate_pairs': near_count, 'cross_split_near_duplicate_pairs': cross_near_count, 'near_examples': near_examples,
            'similarity_method': 'max of both directional normalized Unicode SequenceMatcher ratios; candidate heuristic only',
            'similarity_threshold': similarity_threshold, 'total_possible_pairs': total_pairs,
            'compared_pairs': compared, 'max_comparisons': max_comparisons, 'long_text_pairs_skipped': long_skipped,
            'near_complete': compared == total_pairs and long_skipped == 0,
            'cross_split_total_pairs': cross_total, 'cross_split_compared_pairs': cross_compared,
            'cross_split_near_complete': cross_compared == cross_total and cross_long_skipped == 0,
            'limitations': '不自动去重/改标签/重划分；仅检查提供的文件与group_id。近似候选不证明语义重复；未比较、翻译与上下文泄漏仍须人工核查；报告不包含原文。'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', action='append', required=True, help='显式名称=本地文件，可重复提供；不自动划分')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--similarity-threshold', type=float, default=0.9)
    parser.add_argument('--max-comparisons', type=int, default=10000)
    parser.add_argument('--text-field', default='text')
    parser.add_argument('--label-field', default='label')
    args = parser.parse_args()
    try:
        splits = {}
        for item in args.split:
            name, separator, path = item.partition('=')
            if not separator or name in splits:
                raise ValueError('分区须为不重复的 名称=路径')
            splits[name] = Path(path)
        if any(args.output.resolve() == p.resolve() for p in splits.values()):
            raise ValueError('报告不能覆盖原始输入')
        report = audit(splits, similarity_threshold=args.similarity_threshold, max_comparisons=args.max_comparisons,
                       text_field=args.text_field, label_field=args.label_field)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        print(json.dumps({key: report[key] for key in ('exact_duplicate_groups', 'cross_split_exact_groups', 'near_duplicate_pairs', 'near_complete')}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'核查失败：{exc}\n')


if __name__ == '__main__':
    main()
