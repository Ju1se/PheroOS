#!/usr/bin/env python3
"""Strictly type-check the Draft Stable candidate owner/import closure."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = Path("pheroos/conformance/abi/stable-python-api-v1.json")
CANDIDATE_VERSION = "pheroos-stable-python-api-v1"
MYPY_VERSION = "1.18.2"
PUBLIC_PACKAGES = (
    "pheroos.protocol",
    "pheroos.kernel",
    "pheroos.drivers",
    "pheroos.governance",
    "pheroos.trace",
    "pheroos.conformance",
)


def load_candidate(root: Path = ROOT) -> dict[str, Any]:
    """Load the checked candidate with duplicate/non-finite JSON rejected."""

    value = json.loads(
        (root / CANDIDATE_PATH).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("Stable typing candidate must be a JSON object")
    return value


def candidate_failures(candidate: Mapping[str, Any]) -> list[str]:
    """Return fail-closed metadata and owner-declaration failures."""

    failures: list[str] = []
    if candidate.get("artifact_version") != CANDIDATE_VERSION:
        failures.append("candidate artifact_version is not the supported version")
    if candidate.get("artifact_root") != _candidate_root(candidate):
        failures.append("candidate artifact_root does not bind its content")
    lifecycle = candidate.get("lifecycle")
    if not isinstance(lifecycle, dict):
        failures.append("candidate lifecycle must be an object")
    elif lifecycle != {
        "formal_stable": False,
        "stability": "draft",
        "status": "promotion_candidate",
    }:
        failures.append("candidate lifecycle is not the reviewed promotion state")
    packages = candidate.get("packages")
    if not isinstance(packages, dict) or tuple(sorted(packages)) != tuple(
        sorted(PUBLIC_PACKAGES)
    ):
        failures.append("candidate packages are not the six public facades")
        return failures
    try:
        owners = stable_owner_modules(candidate)
    except ValueError as exc:
        failures.append(str(exc))
    else:
        if not owners:
            failures.append("candidate declares no canonical owners")
    return failures


def stable_owner_modules(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    """Derive the exact canonical-owner module set from candidate exports."""

    packages = candidate.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("candidate packages must be an object")
    owners: set[str] = set()
    for package_name in PUBLIC_PACKAGES:
        package = packages.get(package_name)
        if not isinstance(package, dict):
            raise ValueError(f"candidate package missing: {package_name}")
        exports = package.get("exports")
        if not isinstance(exports, list) or not exports:
            raise ValueError(f"candidate exports must be non-empty: {package_name}")
        for index, entry in enumerate(exports):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"candidate export is not an object: {package_name}[{index}]"
                )
            shape = entry.get("shape")
            if not isinstance(shape, dict):
                raise ValueError(
                    f"candidate export shape missing: {package_name}[{index}]"
                )
            owner = shape.get("owner")
            if not isinstance(owner, str) or not owner.startswith("pheroos."):
                raise ValueError(
                    f"candidate owner must be a pheroos module: {package_name}[{index}]"
                )
            owners.add(owner)
    return tuple(sorted(owners))


def stable_owner_paths(root: Path, candidate: Mapping[str, Any]) -> tuple[Path, ...]:
    """Resolve every declared owner to exactly one in-tree Python source."""

    paths: list[Path] = []
    for module in stable_owner_modules(candidate):
        relative = Path(*module.split("."))
        choices = (root / relative.with_suffix(".py"), root / relative / "__init__.py")
        existing = [path for path in choices if path.is_file()]
        if len(existing) != 1:
            raise ValueError(
                f"candidate owner must resolve to exactly one source: {module}"
            )
        path = existing[0].resolve()
        try:
            relative_path = path.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"candidate owner escapes repository: {module}") from exc
        if not relative_path.parts or relative_path.parts[0] != "pheroos":
            raise ValueError(f"candidate owner is outside pheroos: {module}")
        paths.append(relative_path)
    return tuple(sorted(paths, key=lambda item: item.as_posix()))


def mypy_command(owner_paths: Sequence[Path]) -> tuple[str, ...]:
    """Return the exact strict command; imported modules use normal traversal."""

    if not owner_paths:
        raise ValueError("Stable typing owner path set must not be empty")
    return (
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        "--no-incremental",
        "--follow-imports=normal",
        "--show-error-codes",
        *(path.as_posix() for path in owner_paths),
    )


def check_stable_typing(root: Path = ROOT) -> int:
    """Validate the candidate scope and require zero strict Mypy errors."""

    try:
        candidate = load_candidate(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid Stable typing candidate: {exc}")
        return 1
    failures = candidate_failures(candidate)
    if failures:
        for failure in failures:
            print(f"invalid Stable typing candidate: {failure}")
        return 1
    try:
        observed_version = version("mypy")
    except PackageNotFoundError:
        print(f"missing required mypy=={MYPY_VERSION}")
        return 1
    if observed_version != MYPY_VERSION:
        print(f"mypy version drift: {observed_version} != {MYPY_VERSION}")
        return 1
    try:
        owner_paths = stable_owner_paths(root, candidate)
    except ValueError as exc:
        print(f"invalid Stable typing owner scope: {exc}")
        return 1
    completed = subprocess.run(
        mypy_command(owner_paths),
        cwd=root,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        print(
            "Stable owner/import closure strict typing failed "
            f"for {len(owner_paths)} canonical owners"
        )
        return 1
    print(
        "verified Stable owner/import closure strict typing: "
        f"{len(owner_paths)} canonical owners, normal imports, 0 errors"
    )
    return 0


def _candidate_root(candidate: Mapping[str, Any]) -> str:
    body = dict(candidate)
    body.pop("artifact_root", None)
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON value: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="require the complete Stable owner/import closure to pass strict Mypy",
    )
    parser.parse_args()
    return check_stable_typing()


if __name__ == "__main__":
    raise SystemExit(main())
