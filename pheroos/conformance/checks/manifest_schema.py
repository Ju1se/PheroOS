from __future__ import annotations

from pathlib import Path

from pheroos.conformance.report import CheckResult
from pheroos.protocol.loader import load_capability_manifest
from pheroos.protocol.validation import validate_capability_manifest


def check(path: Path) -> CheckResult:
    try:
        manifest = load_capability_manifest(path)
        diagnostics = validate_capability_manifest(manifest)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("manifest_schema", False, str(exc))
    errors = [item for item in diagnostics if item.level == "error"]
    return CheckResult(
        "manifest_schema", not errors, "; ".join(item.code for item in errors)
    )
