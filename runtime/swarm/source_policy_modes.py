from __future__ import annotations

from typing import Any


CANONICAL_WRDS_ONLY_SOURCE_MODE = "WRDS_ONLY"
WRDS_ONLY_SOURCE_MODES = {CANONICAL_WRDS_ONLY_SOURCE_MODE, "WRDS-FIRST", "WRDS_FIRST"}


def canonical_wrds_only_source_mode() -> str:
    return CANONICAL_WRDS_ONLY_SOURCE_MODE


def source_mode_is_wrds_only(value: Any) -> bool:
    return str(value or "").strip().upper() in WRDS_ONLY_SOURCE_MODES
