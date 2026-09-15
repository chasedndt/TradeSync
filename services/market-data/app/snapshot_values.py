"""Reading values out of a snapshot payload.

Shared by the feature extractor and the one-hour return derivation, which both
read nested snapshot fields and accept only finite numbers.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


def value_at(payload: Mapping[str, Any], *parts: str) -> Any:
    value: Any = payload
    for part in parts:
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None
