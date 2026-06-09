from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_target_aliases import legacy_canonical_target_alias


TARGET_RUN = "run"
TARGET_DATA_GATE = "gate:data_gate"
TARGET_DATA_SOURCE_POLICY = "constraint:data_source_policy"


CANONICAL_TARGET_ALIASES = {
    "data_gate": "gate:data_gate",
    "data gate": "gate:data_gate",
    "gate_data_gate": "gate:data_gate",
    "gate.data_gate": "gate:data_gate",
    "data_source_policy": "constraint:data_source_policy",
    "source_mode": "constraint:data_source_policy",
}


def canonical_target(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return TARGET_RUN
    lowered = normalize_target_text(text)
    if lowered in CANONICAL_TARGET_ALIASES:
        return CANONICAL_TARGET_ALIASES[lowered]
    legacy_alias = legacy_canonical_target_alias(lowered)
    if legacy_alias:
        return legacy_alias
    if lowered.startswith((
        "tool:",
        "agent:",
        "metric:",
        "constraint:",
        "decision:",
        "candidate:",
        "gate:",
        "artifact:",
        "issue:",
        "gap:",
        "code:",
        "compliance:",
        "research:",
    )):
        return lowered
    if lowered.startswith("data_issue:"):
        return f"issue:{lowered}"
    if lowered.startswith("evidence_gap:"):
        return f"gap:{lowered}"
    return lowered


def normalize_target_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return " ".join(text.replace("-", "_").split())


def target_kind(value: Any) -> str:
    target = canonical_target(value)
    if ":" not in target:
        return "run"
    return target.split(":", 1)[0]


def candidate_target(label: Any) -> str:
    return canonical_target(str(label or "").strip().lower())


def target_matches(value: Any, *expected: str) -> bool:
    actual = canonical_target(value)
    return any(actual == canonical_target(item) for item in expected)
