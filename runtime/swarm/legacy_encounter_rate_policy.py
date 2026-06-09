from __future__ import annotations


LEGACY_ENCOUNTER_RATE_RECOMMENDATION_SOURCE = "legacy_encounter_rate_policy"
LEGACY_ENCOUNTER_RATE_RECOMMENDATIONS = {
    "healthy": "maintain or expand current active lanes",
    "degraded": "keep execution conservative and prioritize verifier feedback",
    "poor": "reduce expansion and route more work to verification",
    "insufficient_history": "collect more local return events before adjusting activation",
}


def legacy_encounter_rate_recommendation_source() -> str:
    return LEGACY_ENCOUNTER_RATE_RECOMMENDATION_SOURCE


def legacy_encounter_rate_recommendation(status: str) -> str:
    return LEGACY_ENCOUNTER_RATE_RECOMMENDATIONS.get(
        status,
        LEGACY_ENCOUNTER_RATE_RECOMMENDATIONS["insufficient_history"],
    )
