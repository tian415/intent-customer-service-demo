"""Bounded engineering configuration; these defaults are not a research decision."""
import math

DEFAULTS = {'ngram_range': [1, 3], 'max_features': 10000, 'C': 1.0,
            'max_iter': 1000, 'random_state': 0, 'data_partition': None}


def resolve_config(config: dict | None) -> dict:
    if config is not None and not isinstance(config, dict):
        raise ValueError('训练配置必须是对象')
    if set(config or {}) - set(DEFAULTS):
        raise ValueError('训练配置含不支持的字段，不自动选择算法')
    result = {**DEFAULTS, **(config or {})}
    ngrams = result['ngram_range']
    if not isinstance(ngrams, list) or len(ngrams) != 2 or not all(type(n) is int for n in ngrams) or not 1 <= ngrams[0] <= ngrams[1] <= 3:
        raise ValueError('ngram_range须在1到3之间且顺序有效')
    for key, lower, upper in [('max_features', 1, 50000), ('max_iter', 1, 10000), ('random_state', 0, 2**32 - 1)]:
        if type(result[key]) is not int or not lower <= result[key] <= upper:
            raise ValueError(f'{key}超出工程支持范围')
    if type(result['C']) not in (int, float) or not math.isfinite(result['C']) or not 0 < result['C'] <= 10000:
        raise ValueError('C必须为有限正数且不超过10000')
    partition = result['data_partition']
    if partition is not None and (not isinstance(partition, str) or not partition.strip()):
        raise ValueError('data_partition须为明确的已有分区名称')
    return result
