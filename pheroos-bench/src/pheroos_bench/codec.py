from __future__ import annotations

import json
from typing import Any


def encode(value: Any) -> bytes:
    """Encode every arm's wire object with the frozen experiment codec."""

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def byte_count(value: Any) -> int:
    return len(encode(value))

