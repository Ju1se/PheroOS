from __future__ import annotations


COMMIT_ASSURANCE_ORDER = {
    "advisory": 0,
    "evidence_bound": 1,
    "certified": 2,
    "distributed": 3,
}
CERTIFICATE_MODE_BY_ASSURANCE = {
    "advisory": "none",
    "evidence_bound": "local_receipt",
    "certified": "portable",
    "distributed": "distributed",
}
NON_PUBLISHABLE_TERMINAL_OUTCOMES = frozenset(
    {"invalid", "finality_unavailable", "safety_violation"}
)
COMMIT_CRITICAL_EXTENSION_PREFIXES = (
    "x-critical",
    "ext.critical",
)
