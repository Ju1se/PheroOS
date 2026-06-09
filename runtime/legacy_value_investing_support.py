from __future__ import annotations


LEGACY_VALUE_INVESTING_CAPABILITY_ID = "value-investing-research"
LEGACY_DEFAULT_COMMITTEE_CAPABILITY_IDS = frozenset({"value-investing-research"})


def legacy_value_investing_capability_id() -> str:
    return LEGACY_VALUE_INVESTING_CAPABILITY_ID


def legacy_default_committee_capability_ids() -> set[str]:
    return set(LEGACY_DEFAULT_COMMITTEE_CAPABILITY_IDS)
