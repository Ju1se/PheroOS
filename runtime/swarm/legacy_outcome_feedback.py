from __future__ import annotations


LEGACY_OUTCOME_FEEDBACK_EXCLUDED_FIELDS = (
    "formal_decision",
    "committee_decision",
)


def legacy_outcome_feedback_excluded_fields() -> list[str]:
    return list(LEGACY_OUTCOME_FEEDBACK_EXCLUDED_FIELDS)
