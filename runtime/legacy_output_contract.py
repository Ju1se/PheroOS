from __future__ import annotations


LEGACY_RAW_DATA_MARKER_FALLBACK_SOURCE = "legacy_raw_data_marker_fallback"
LEGACY_RAW_DATA_MARKERS = (
    "gvkey",
    "datadate",
    "indfmt",
    "datafmt",
    "popsrc",
    "consol",
    "sale=",
    "cogs=",
    "oancf=",
)


def legacy_raw_data_marker_fallback_source() -> str:
    return LEGACY_RAW_DATA_MARKER_FALLBACK_SOURCE


def legacy_raw_data_markers() -> list[str]:
    return list(LEGACY_RAW_DATA_MARKERS)
