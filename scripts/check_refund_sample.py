"""Audit the pinned SEA Data Lab public sample locally. Never emit source messages."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.refunds import refund_intent

SOURCE_SHA256 = '6c69e06644a371d14af1b9abb3ebbc77fc71bd58da26401f4ddca86c8bbc5017'
# Provisional review from the customer message only. These six entries refer
# to an earlier request. The source groups them together with new applications.
EXISTING_REQUESTS = {
    'sea_ecom_00000078', 'sea_ecom_00000254', 'sea_ecom_00000265',
    'sea_ecom_00000337', 'sea_ecom_00000889', 'sea_ecom_00000984',
}


def audit(raw: bytes) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError('样本版本不符，请核对来源和 SHA-256')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    chinese = [row for row in rows if row['language'] == 'zh']
    counts = Counter(row['intent'] for row in chinese)
    observed = {}
    other_signals = 0
    for row in chinese:
        predicted = refund_intent(row['customer_message'])
        if row['intent'] == 'return_policy':
            expected = 'check_refund_policy'
        elif row['intent'] == 'refund_request':
            expected = 'track_refund' if row['id'] in EXISTING_REQUESTS else 'get_refund'
        else:
            other_signals += int(predicted is not None)
            continue
        results = observed.setdefault(expected, Counter())
        results[predicted or 'unmatched'] += 1
    return {'sha256':digest, 'total':len(rows), 'zh':len(chinese), 'source_counts':counts,
            'provisional_by_expected':observed, 'refund_signals_in_other_source_labels':other_signals}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', help='原版 data.jsonl 路径，或 - 表示标准输入')
    arg = parser.parse_args()
    raw = sys.stdin.buffer.read() if arg.sample == '-' else Path(arg.sample).read_bytes()
    print(json.dumps(audit(raw), ensure_ascii=False, indent=2))
