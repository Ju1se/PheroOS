from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from runtime.swarm.legacy_target_aliases import (
    legacy_formal_valuation_target,
    legacy_report_publication_target,
)
from runtime.swarm.target_registry import (
    TARGET_DATA_GATE,
    canonical_target,
)


LEGACY_QUORUM_FORMAL_FLAG = "formal_valuation_blocked"
LEGACY_QUORUM_PUBLICATION_FLAG = "report_publication_blocked"


def legacy_quorum_block_flags(active_blocker_targets: Iterable[Any]) -> dict[str, bool]:
    targets = {
        canonical_target(target)
        for target in active_blocker_targets
        if str(target or "").strip()
    }
    formal_target = legacy_formal_valuation_target()
    publication_target = legacy_report_publication_target()
    return {
        LEGACY_QUORUM_FORMAL_FLAG: formal_target in targets,
        LEGACY_QUORUM_PUBLICATION_FLAG: bool({publication_target, TARGET_DATA_GATE} & targets),
    }


def legacy_quorum_flags_from_report(report: dict[str, Any]) -> dict[str, bool]:
    return {
        LEGACY_QUORUM_FORMAL_FLAG: bool(report.get(LEGACY_QUORUM_FORMAL_FLAG)),
        LEGACY_QUORUM_PUBLICATION_FLAG: bool(report.get(LEGACY_QUORUM_PUBLICATION_FLAG)),
    }


def legacy_blocked_conclusion_targets_from_quorum_flags(report: dict[str, Any]) -> list[str]:
    flags = legacy_quorum_flags_from_report(report)
    targets: list[str] = []
    if flags[LEGACY_QUORUM_FORMAL_FLAG]:
        targets.append(legacy_formal_valuation_target())
    if flags[LEGACY_QUORUM_PUBLICATION_FLAG]:
        targets.append(legacy_report_publication_target())
    return sorted(set(targets))
