from __future__ import annotations

import re
from pathlib import Path

from pheroos.conformance.report import CheckResult


CORE_SOURCE_PATHS = (
    "pheroos/protocol",
    "pheroos/kernel",
    "pheroos/governance",
    "pheroos/drivers",
    "pheroos/trace",
    "pheroos/conformance",
    "pheroos/cli",
)


def forbidden_terms() -> list[str]:
    # Keep the sentinels absent from this checker's own source so the scan can
    # include every core module without a special-case exclusion.
    fragments = (
        ("w", "rds"),
        ("value", "_investing"),
        ("formal", "_valuation"),
        ("investment", "_committee"),
        ("comp", "ustat"),
        ("c", "rsp"),
        ("i", "bes"),
    )
    return ["".join(parts) for parts in fragments]


def check_public_core(root: Path) -> CheckResult:
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(term) for term in forbidden_terms()) + r")\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for rel in CORE_SOURCE_PATHS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix != ".py":
                continue
            match = pattern.search(path.read_text(encoding="utf-8"))
            if match:
                offenders.append(
                    f"{path.relative_to(root).as_posix()}:{match.group(0)}"
                )
    return CheckResult(
        "domain_neutrality_public_core", not offenders, "; ".join(offenders)
    )
