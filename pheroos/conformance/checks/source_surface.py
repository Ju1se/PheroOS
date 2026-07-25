from __future__ import annotations

from pathlib import Path

from pheroos.conformance.report import CheckResult


REQUIRED_SOURCE_SURFACES = (
    "pheroos/protocol",
    "pheroos/kernel",
    "pheroos/governance",
    "pheroos/drivers",
    "pheroos/trace",
    "pheroos/conformance",
    "pheroos/cli",
)


def check(core_root: Path) -> CheckResult:
    missing = []
    for relative in REQUIRED_SOURCE_SURFACES:
        surface = core_root / relative
        if (
            not surface.is_dir()
            or not (surface / "__init__.py").is_file()
            or not any(surface.glob("*.py"))
        ):
            missing.append(relative)
    return CheckResult(
        "source_surface", not missing, ", ".join(f"missing:{item}" for item in missing)
    )


__all__ = ["REQUIRED_SOURCE_SURFACES", "check"]
