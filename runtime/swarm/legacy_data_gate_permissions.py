from __future__ import annotations


LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS = {
    "decision:formal_valuation": "formal_valuation_allowed",
    "decision:report_publication": "report_publication_allowed",
}

LEGACY_FORMAL_VALUATION_CONCLUSION_TARGET = "decision:formal_valuation"
LEGACY_PUBLICATION_CONCLUSION_TARGET = "decision:report_publication"
LEGACY_PUBLICATION_ACTION_TARGET_TAILS = frozenset(
    {
        "publish_report",
        "report_publication",
        "publication",
        "final_report",
    }
)


def legacy_top_level_conclusion_permission_keys() -> dict[str, str]:
    return dict(LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS)


def legacy_publication_allowed_field() -> str:
    return LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS[LEGACY_PUBLICATION_CONCLUSION_TARGET]


def legacy_formal_valuation_allowed_field() -> str:
    return LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS[LEGACY_FORMAL_VALUATION_CONCLUSION_TARGET]


def legacy_publication_conclusion_target() -> str:
    return LEGACY_PUBLICATION_CONCLUSION_TARGET


def legacy_formal_valuation_conclusion_target() -> str:
    return LEGACY_FORMAL_VALUATION_CONCLUSION_TARGET


def legacy_publication_action_conclusion_target(action_tail: object) -> str:
    if legacy_publication_action_target_tail(action_tail):
        return legacy_publication_conclusion_target()
    return ""


def legacy_publication_action_target_tail(value: object) -> bool:
    tail = "_".join(str(value or "").strip().lower().replace("-", "_").split())
    return tail in LEGACY_PUBLICATION_ACTION_TARGET_TAILS
