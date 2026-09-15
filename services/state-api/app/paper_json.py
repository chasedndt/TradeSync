"""JSON helpers shared by the paper risk modules: jsonb in, jsonb out."""

from __future__ import annotations

import json
from typing import Any


def decode(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def serial(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, allow_nan=False)
