"""Strict JSON boundaries: duplicate keys and non-finite constants are ambiguous."""
from __future__ import annotations

import json
from typing import Any


def loads(text: str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('JSON 含重复键，拒绝静默覆盖')
            result[key] = value
        return result

    def reject_constant(_value: str):
        raise ValueError('JSON 含非有限数值')

    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
