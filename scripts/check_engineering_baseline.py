#!/usr/bin/env python3
"""Generate or verify the monotonic PheroOS engineering baseline."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs" / "process" / "engineering-baseline-v1.json"
BASELINE_VERSION = "pheroos-engineering-baseline-v1"

PUBLIC_INVENTORY = ROOT / "pheroos/conformance/abi/public-python-api-v1.json"
PUBLIC_LIFECYCLE = ROOT / "pheroos/conformance/abi/public-python-api-lifecycle-v1.json"
REFERENCE_PERFORMANCE = ROOT / "docs/process/reference-performance-v1.json"
CI_CONSTRAINTS = ROOT / "requirements/ci-constraints.txt"

EXACT_PATHS = (
    "project",
    "public_api",
    "schemas",
    "tck",
    "performance",
    "toolchain.ci_constraints_sha256",
    "quality.coverage",
)
UPPER_BOUND_PATHS = (
    "quality.ruff.findings_total",
    "quality.mypy.errors",
    "quality.mypy.files_with_errors",
    "quality.complexity.over_threshold_count",
    "quality.complexity.maximum_observed",
    "quality.complexity.complexity_sum",
    "quality.complexity.over_20_count",
    "quality.complexity.over_25_count",
    "dependencies.runtime_count",
    "dependencies.forbidden_core_import_count",
)
LOWER_BOUND_PATHS = ("tests.collected",)

# These hard ceilings duplicate the initial audit so replacing the JSON with
# weaker numbers cannot silently relax WP-00. Later work may lower them.
ABSOLUTE_MAXIMA = {
    "quality.ruff.findings_total": 1016,
    "quality.mypy.errors": 1150,
    "quality.mypy.files_with_errors": 88,
    "quality.complexity.over_threshold_count": 165,
    "quality.complexity.maximum_observed": 104,
    "quality.complexity.complexity_sum": 3216,
    "quality.complexity.over_20_count": 45,
    "quality.complexity.over_25_count": 28,
    "dependencies.runtime_count": 0,
    "dependencies.forbidden_core_import_count": 0,
}
ABSOLUTE_MINIMA = {"tests.collected": 1445}
ABSOLUTE_RUFF_BY_CODE = {
    "E402": 520,
    "E731": 1,
    "F401": 452,
    "F601": 1,
    "F811": 38,
    "F841": 4,
}
ABSOLUTE_MYPY_BY_CODE = {
    "arg-type": 485,
    "assignment": 25,
    "attr-defined": 565,
    "call-overload": 9,
    "dict-item": 2,
    "index": 4,
    "misc": 1,
    "no-redef": 2,
    "operator": 7,
    "return-value": 5,
    "type-var": 3,
    "union-attr": 38,
    "var-annotated": 4,
}

KNOWN_LIMITATIONS = (
    {
        "behavior": (
            "Draft v1 public issuers can create locally recognized sentinel "
            "records from a caller-supplied AuthorityLevel in a trusted process"
        ),
        "guarantee": "trusted_host_compatibility_only",
        "id": "WP00-CHAR-001",
        "replacement_wp": "WP-03",
        "status": "characterized_draft",
        "test": (
            "tests/governance/test_wp00_legacy_characterization.py::"
            "test_v1_public_issuer_is_trusted_host_compatibility_only"
        ),
    },
    {
        "behavior": (
            "Draft baseline output accepts a caller-provided publication boolean"
        ),
        "guarantee": "legacy_v1_only",
        "id": "WP00-CHAR-002",
        "replacement_wp": "WP-04",
        "status": "characterized_draft",
        "test": (
            "tests/governance/test_wp00_legacy_characterization.py::"
            "test_v1_baseline_output_accepts_caller_publication_boolean"
        ),
    },
    {
        "behavior": (
            "Draft v1 finalize reports a committed receipt as mismatched after "
            "a legal successor advances the current head"
        ),
        "guarantee": "known_v1_finality_limitation",
        "id": "WP00-CHAR-003",
        "replacement_wp": "WP-02",
        "status": "characterized_draft",
        "test": (
            "tests/governance/test_wp00_legacy_characterization.py::"
            "test_v1_finalize_mismatches_after_legal_successor"
        ),
    },
)


def build_observation() -> dict[str, Any]:
    """Collect deterministic source and pinned-tool observations."""

    inventory = _load_json(PUBLIC_INVENTORY)
    lifecycle = _load_json(PUBLIC_LIFECYCLE)
    performance = _load_json(REFERENCE_PERFORMANCE)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    return {
        "dependencies": {
            "forbidden_core_import_count": _forbidden_core_import_count(),
            "runtime_count": len(project["project"].get("dependencies", ())),
            "runtime_names": sorted(project["project"].get("dependencies", ())),
        },
        "performance": {
            "budget_ratios": performance["budget_ratios"],
            "budget_seconds": performance["budget_seconds"],
            "reference_baseline_sha256": _file_sha256(REFERENCE_PERFORMANCE),
            "version": performance["version"],
        },
        "project": _project_observation(project),
        "public_api": _public_api_observation(inventory, lifecycle),
        "quality": _quality_observation(),
        "schemas": _schema_observation(),
        "source": _source_observation(),
        "tck": _tck_observation(),
        "tests": {"collected": _collected_test_count()},
        "toolchain": {
            "ci_constraints_sha256": _file_sha256(CI_CONSTRAINTS),
            "pins": _constraint_pins(),
        },
    }


def render_baseline(observation: dict[str, Any], *, reason: str) -> bytes:
    """Render one canonical baseline document."""

    normalized_reason = _required_reason(reason)
    payload = {
        "known_limitations": list(KNOWN_LIMITATIONS),
        "observation": observation,
        "policy": {
            "exact_paths": list(EXACT_PATHS),
            "lower_bound_paths": list(LOWER_BOUND_PATHS),
            "upper_bound_paths": list(UPPER_BOUND_PATHS),
        },
        "reason": normalized_reason,
        "version": BASELINE_VERSION,
    }
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, Any]:
    loaded = _load_json(path)
    if not isinstance(loaded, dict):
        raise ValueError("engineering baseline must be a JSON object")
    return loaded


def write_baseline(
    path: Path,
    *,
    observation: dict[str, Any],
    reason: str,
) -> None:
    """Write a deterministic refresh without relaxing monotonic metrics."""

    normalized_reason = _required_reason(reason)
    if path.is_file():
        existing = load_baseline(path)
        regressions = refresh_regressions(existing, observation)
        if regressions:
            raise ValueError(
                "baseline refresh would regress: " + "; ".join(regressions)
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_baseline(observation, reason=normalized_reason)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(rendered)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def baseline_failures(
    baseline: dict[str, Any],
    observation: dict[str, Any],
) -> list[str]:
    """Return all drift and monotonic-regression failures."""

    failures = _baseline_shape_failures(baseline)
    if failures:
        return failures
    expected = baseline["observation"]
    for path in EXACT_PATHS:
        if _path_value(expected, path) != _path_value(observation, path):
            failures.append(f"exact baseline drift: {path}")
    for path in UPPER_BOUND_PATHS:
        expected_value = _numeric_path(expected, path)
        observed_value = _numeric_path(observation, path)
        if observed_value > expected_value:
            failures.append(
                f"upper-bound regression: {path}={observed_value} > {expected_value}"
            )
    for path in LOWER_BOUND_PATHS:
        expected_value = _numeric_path(expected, path)
        observed_value = _numeric_path(observation, path)
        if observed_value < expected_value:
            failures.append(
                f"lower-bound regression: {path}={observed_value} < {expected_value}"
            )
    failures.extend(
        _mapping_ceiling_failures(
            expected,
            observation,
            "quality.ruff.by_code",
        )
    )
    failures.extend(
        _mapping_ceiling_failures(
            expected,
            observation,
            "quality.mypy.by_code",
        )
    )
    failures.extend(_absolute_limit_failures(observation))
    return failures


def refresh_regressions(
    baseline: dict[str, Any],
    observation: dict[str, Any],
) -> list[str]:
    """Reject a write that weakens one-way gates; exact roots may migrate."""

    failures = _baseline_shape_failures(baseline, enforce_absolute=False)
    if failures:
        return failures
    expected = baseline["observation"]
    for path in UPPER_BOUND_PATHS:
        if _numeric_path(observation, path) > _numeric_path(expected, path):
            failures.append(f"refresh raises upper bound: {path}")
    for path in LOWER_BOUND_PATHS:
        if _numeric_path(observation, path) < _numeric_path(expected, path):
            failures.append(f"refresh lowers lower bound: {path}")
    failures.extend(
        _mapping_ceiling_failures(
            expected,
            observation,
            "quality.ruff.by_code",
            prefix="refresh raises code ceiling",
        )
    )
    failures.extend(
        _mapping_ceiling_failures(
            expected,
            observation,
            "quality.mypy.by_code",
            prefix="refresh raises code ceiling",
        )
    )
    failures.extend(_absolute_limit_failures(observation))
    return failures


def _baseline_shape_failures(
    baseline: dict[str, Any],
    *,
    enforce_absolute: bool = True,
) -> list[str]:
    failures: list[str] = []
    if baseline.get("version") != BASELINE_VERSION:
        failures.append("engineering baseline version is unsupported")
    if not isinstance(baseline.get("reason"), str) or not baseline["reason"].strip():
        failures.append("engineering baseline reason is missing")
    if baseline.get("known_limitations") != list(KNOWN_LIMITATIONS):
        failures.append("engineering baseline known limitations drifted")
    expected_policy = {
        "exact_paths": list(EXACT_PATHS),
        "lower_bound_paths": list(LOWER_BOUND_PATHS),
        "upper_bound_paths": list(UPPER_BOUND_PATHS),
    }
    if baseline.get("policy") != expected_policy:
        failures.append("engineering baseline policy drifted")
    if not isinstance(baseline.get("observation"), dict):
        failures.append("engineering baseline observation is missing")
    elif not failures and enforce_absolute:
        failures.extend(_absolute_limit_failures(baseline["observation"]))
    return failures


def _absolute_limit_failures(observation: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for path, maximum in ABSOLUTE_MAXIMA.items():
        value = _numeric_path(observation, path)
        if value > maximum:
            failures.append(f"absolute ceiling exceeded: {path}={value} > {maximum}")
    for path, minimum in ABSOLUTE_MINIMA.items():
        value = _numeric_path(observation, path)
        if value < minimum:
            failures.append(f"absolute floor crossed: {path}={value} < {minimum}")
    failures.extend(
        _hard_mapping_ceiling_failures(
            observation,
            "quality.ruff.by_code",
            ABSOLUTE_RUFF_BY_CODE,
        )
    )
    failures.extend(
        _hard_mapping_ceiling_failures(
            observation,
            "quality.mypy.by_code",
            ABSOLUTE_MYPY_BY_CODE,
        )
    )
    return failures


def _public_api_observation(
    inventory: dict[str, Any],
    lifecycle: dict[str, Any],
) -> dict[str, Any]:
    stability_counts: Counter[str] = Counter()
    for package in lifecycle["packages"].values():
        stability_counts.update(item["stability"] for item in package["exports"])
    return {
        "compatibility_surface_count": lifecycle["summary"][
            "compatibility_surface_count"
        ],
        "diagnostic_code_count": lifecycle["summary"]["diagnostic_code_count"],
        "diagnostic_registry_sha256": _canonical_sha256(lifecycle["diagnostic_codes"]),
        "error_type_count": lifecycle["summary"]["error_type_count"],
        "export_count": inventory["summary"]["export_count"],
        "inventory_sha256": _file_sha256(PUBLIC_INVENTORY),
        "lifecycle_sha256": _file_sha256(PUBLIC_LIFECYCLE),
        "package_export_counts": {
            name: package["export_count"]
            for name, package in sorted(inventory["packages"].items())
        },
        "stability_counts": {
            stability: stability_counts.get(stability, 0)
            for stability in lifecycle["stabilities"]
        },
    }


def _project_observation(project: dict[str, Any]) -> dict[str, Any]:
    package_version = project["project"]["version"]
    runtime_version = _assigned_string(ROOT / "pheroos/_version.py", "__version__")
    lifecycle_version = _assigned_string(
        ROOT / "pheroos/conformance/public_api_lifecycle.py",
        "PROJECT_API_VERSION",
    )
    if len({package_version, runtime_version, lifecycle_version}) != 1:
        raise ValueError("project version owners do not match")
    return {
        "lifecycle_version": lifecycle_version,
        "package_version": package_version,
        "requires_python": project["project"]["requires-python"],
        "runtime_version": runtime_version,
    }


def _schema_observation() -> dict[str, Any]:
    schemas: dict[str, Any] = {}
    for path in sorted((ROOT / "schemas").glob("*.json")):
        payload = _load_json(path)
        schemas[path.relative_to(ROOT).as_posix()] = {
            "id": payload.get("$id"),
            "sha256": _file_sha256(path),
        }
    return schemas


def _tck_observation() -> dict[str, Any]:
    from pheroos.conformance.commit_tck import commit_tck_artifact_root
    from pheroos.conformance.commit_tck_v2 import commit_tck_v2_artifact_root

    artifacts = (
        ROOT / "pheroos/conformance/tck/commit-integrity-v1.json",
        ROOT / "pheroos/conformance/tck/commit-integrity-v2.json",
    )
    observed: dict[str, Any] = {}
    for path in artifacts:
        payload = _load_json(path)
        relative = path.relative_to(ROOT).as_posix()
        cases = payload.get("vectors", payload.get("cases", ()))
        observed[relative] = {
            "case_count": len(cases),
            "sha256": _file_sha256(path),
            "version": payload["tck_version"],
        }
    observed[artifacts[0].relative_to(ROOT).as_posix()]["semantic_root"] = (
        commit_tck_artifact_root(artifacts[0])
    )
    observed[artifacts[1].relative_to(ROOT).as_posix()]["semantic_root"] = (
        commit_tck_v2_artifact_root(artifacts[1])
    )
    return observed


def _source_observation() -> dict[str, Any]:
    core_files = sorted((ROOT / "pheroos").rglob("*.py"))
    return {
        "conformance_loc": _python_loc(ROOT / "pheroos/conformance"),
        "core_python_files": len(core_files),
        "core_python_loc": sum(_line_count(path) for path in core_files),
        "governance_loc": _python_loc(ROOT / "pheroos/governance"),
    }


def _quality_observation() -> dict[str, Any]:
    ruff = _ruff_findings()
    complexity = _complexity_findings()
    return {
        "complexity": complexity,
        "coverage": _coverage_configuration(),
        "mypy": _mypy_findings(),
        "ruff": ruff,
    }


def _ruff_findings() -> dict[str, Any]:
    completed = _run_tool(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "pheroos",
            "scripts",
            "tests",
            "--output-format",
            "json",
        ],
        accepted=(0, 1),
    )
    findings = json.loads(completed.stdout)
    by_code = Counter(item["code"] for item in findings)
    return {
        "by_code": dict(sorted(by_code.items())),
        "findings_total": len(findings),
        "scope": ["pheroos", "scripts", "tests"],
    }


def _complexity_findings() -> dict[str, Any]:
    completed = _run_tool(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "pheroos",
            "scripts",
            "tests",
            "--select",
            "C901",
            "--output-format",
            "json",
        ],
        accepted=(0, 1),
    )
    findings = json.loads(completed.stdout)
    complexities = []
    for item in findings:
        match = re.search(r"\((\d+) > 10\)$", item["message"])
        if match is None:
            raise RuntimeError("Ruff C901 output has an unsupported message")
        complexities.append(int(match.group(1)))
    return {
        "complexity_sum": sum(complexities),
        "maximum_observed": max(complexities, default=0),
        "over_20_count": sum(value > 20 for value in complexities),
        "over_25_count": sum(value > 25 for value in complexities),
        "over_threshold_count": len(findings),
        "scope": ["pheroos", "scripts", "tests"],
        "threshold": 10,
    }


def _mypy_findings() -> dict[str, Any]:
    completed = _run_tool(
        [sys.executable, "-m", "mypy", "--no-incremental", "pheroos"],
        accepted=(0, 1),
    )
    error_lines = [
        line for line in completed.stdout.splitlines() if ": error: " in line
    ]
    by_code: Counter[str] = Counter()
    files: set[str] = set()
    for line in error_lines:
        match = re.search(r"\[([^\]]+)\]\s*$", line)
        by_code[match.group(1) if match is not None else "unclassified"] += 1
        files.add(line.split(":", maxsplit=1)[0])
    return {
        "by_code": dict(sorted(by_code.items())),
        "errors": len(error_lines),
        "files_with_errors": len(files),
        "scope": ["pheroos"],
    }


def _collected_test_count() -> int:
    completed = _run_tool(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        accepted=(0,),
    )
    matches = re.findall(r"(\d+) tests? collected", completed.stdout)
    if len(matches) != 1:
        raise RuntimeError("pytest collection count is unavailable or ambiguous")
    return int(matches[0])


def _coverage_configuration() -> dict[str, Any]:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    constraints = CI_CONSTRAINTS.read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
    configured = all(
        (
            "[tool.coverage." in pyproject,
            re.search(r"^coverage==", constraints, re.MULTILINE) is not None,
            "--cov" in workflow or "coverage run" in workflow,
        )
    )
    return {
        "branch_percent": None,
        "line_percent": None,
        "status": "configured" if configured else "not_configured",
    }


def _constraint_pins() -> dict[str, str]:
    try:
        module = import_module("scripts.check_ci_supply_chain")
    except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
        module = import_module("check_ci_supply_chain")

    value = module.parse_hashed_requirements(CI_CONSTRAINTS.read_bytes())
    if not isinstance(value, dict):
        raise TypeError("CI wheel lock parser returned an invalid mapping")
    return value


def _forbidden_core_import_count() -> int:
    from pheroos.conformance.checks.kernel_import_boundary import check

    result = check(ROOT)
    if result.ok:
        return 0
    return len(tuple(item for item in result.detail.split("; ") if item))


def _run_tool(
    command: list[str],
    *,
    accepted: tuple[int, ...],
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = "0"
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode not in accepted:
        raise RuntimeError(
            f"baseline command failed ({completed.returncode}): "
            f"{' '.join(command)}\n{completed.stdout}{completed.stderr}"
        )
    return completed


def _mapping_ceiling_failures(
    expected: dict[str, Any],
    observed: dict[str, Any],
    path: str,
    *,
    prefix: str = "code-count regression",
) -> list[str]:
    expected_mapping = _path_value(expected, path)
    observed_mapping = _path_value(observed, path)
    if not isinstance(expected_mapping, dict) or not isinstance(observed_mapping, dict):
        raise ValueError(f"engineering baseline path is not a mapping: {path}")
    failures: list[str] = []
    for code in sorted(set(expected_mapping) | set(observed_mapping)):
        expected_count = expected_mapping.get(code, 0)
        observed_count = observed_mapping.get(code, 0)
        if type(expected_count) is not int or type(observed_count) is not int:
            raise ValueError(
                f"engineering baseline code count is invalid: {path}.{code}"
            )
        if observed_count > expected_count:
            failures.append(
                f"{prefix}: {path}.{code}={observed_count} > {expected_count}"
            )
    return failures


def _hard_mapping_ceiling_failures(
    observation: dict[str, Any],
    path: str,
    maxima: dict[str, int],
) -> list[str]:
    observed = _path_value(observation, path)
    if not isinstance(observed, dict):
        raise ValueError(f"engineering baseline path is not a mapping: {path}")
    failures: list[str] = []
    for code in sorted(set(maxima) | set(observed)):
        value = observed.get(code, 0)
        if type(value) is not int or value < 0:
            raise ValueError(
                f"engineering baseline code count is invalid: {path}.{code}"
            )
        maximum = maxima.get(code, 0)
        if value > maximum:
            failures.append(
                f"absolute code ceiling exceeded: {path}.{code}={value} > {maximum}"
            )
    return failures


def _path_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            raise ValueError(f"engineering baseline path is missing: {path}")
        value = value[component]
    return value


def _numeric_path(payload: dict[str, Any], path: str) -> int:
    value = _path_value(payload, path)
    if type(value) is not int or value < 0:
        raise ValueError(
            f"engineering baseline path is not a non-negative integer: {path}"
        )
    return value


def _required_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("baseline write reason must be nonblank")
    return reason.strip()


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_nonfinite_json_constant,
    )
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return loaded


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _assigned_string(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, str) and value:
            return value
        break
    raise ValueError(f"{path.relative_to(ROOT)} has no canonical string {name}")


def _canonical_sha256(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _line_count(path: Path) -> int:
    data = path.read_bytes()
    return data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))


def _python_loc(directory: Path) -> int:
    return sum(_line_count(path) for path in sorted(directory.rglob("*.py")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument(
        "--reason",
        help="required audit reason for --write",
    )
    args = parser.parse_args(argv)
    if args.write and (args.reason is None or not args.reason.strip()):
        parser.error("--write requires a nonblank --reason")

    observation = build_observation()
    if args.write:
        try:
            write_baseline(
                BASELINE_PATH,
                observation=observation,
                reason=args.reason,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        print(f"wrote {BASELINE_PATH.relative_to(ROOT)}")
        return 0

    try:
        baseline = load_baseline()
        failures = baseline_failures(baseline, observation)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("engineering baseline verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
