from __future__ import annotations

from typing import Any


LEGACY_QUORUM_FORCE_FALLBACK_KEYS = (
    "force_insufficient_data_when_formal_valuation_blocked",
)
LEGACY_SAFE_FALLBACK_LABEL_MARKERS = ("insufficient",)
LEGACY_CANDIDATE_REGISTRY_MISSING_POLICY_REASON = (
    "no capability-declared candidates and no legacy investment fallback matched"
)


def legacy_quorum_force_fallback_value(data: dict[str, Any]) -> Any:
    for key in LEGACY_QUORUM_FORCE_FALLBACK_KEYS:
        if key in data:
            return data.get(key)
    return None


def legacy_quorum_policy_keys() -> set[str]:
    return set(LEGACY_QUORUM_FORCE_FALLBACK_KEYS)


def legacy_candidate_safe_fallback_value(data: dict[str, Any], label: str) -> Any:
    if "safe_fallback" in data:
        return data.get("safe_fallback")
    return legacy_candidate_label_implies_safe_fallback(label)


def legacy_candidate_label_implies_safe_fallback(label: str) -> bool:
    normalized = str(label or "").lower()
    return any(marker in normalized for marker in LEGACY_SAFE_FALLBACK_LABEL_MARKERS)


def legacy_candidate_registry_missing_policy_reason() -> str:
    return LEGACY_CANDIDATE_REGISTRY_MISSING_POLICY_REASON
