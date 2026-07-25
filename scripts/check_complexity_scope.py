#!/usr/bin/env python3
"""Verify the static WP-09 trust-path complexity and module-size scope."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "process" / "complexity-scope-v1.json"
MANIFEST_VERSION = "pheroos-complexity-scope-v1"
TRUST_PATH_CATEGORY = "trust_path"

_CORE_TRUST_PATH_FUNCTIONS = (
    "pheroos.protocol.validation.validate_capability_manifest",
    "pheroos.protocol.validation._validate_capability_manifest_v1",
    "pheroos.trace._validation_core._validate_declared_event_lineage",
    "pheroos.governance._pheromone.invariants.validate_pheromone_policy",
    "pheroos.governance._commit.evaluation.assess_optimal_commit",
    "pheroos.governance._commit_state.liveness.issue_commit_liveness_input",
    "pheroos.governance._commit_state.liveness.reduce_commit_liveness",
    (
        "pheroos.governance._commit_state.liveness."
        "_validate_liveness_input_matches_window"
    ),
    (
        "pheroos.governance._commit_state.liveness."
        "_validate_liveness_current_authority_heads"
    ),
    "pheroos.governance._commit_state.liveness._outcome_from_liveness",
)
_HYBRID_TRACE_TRUST_PATH_FUNCTIONS = (
    "check",
    "check_actual_trace",
    "collective_authority_problems",
    "replay_trace_problems",
    "pheromone_lifecycle_policy_problems",
    "pheromone_score_reconstruction_problems",
    "pheromone_derived_trace_problems",
    "policy_adjustment_trace_problems",
    "coordination_replay_problems",
    "layer_pheromone_lineage_problems",
    "event_stage",
)
_REFERENCE_ADAPTER_METHODS = (
    "evaluate",
    "_canonical_fingerprint",
    "_canonical_set_fingerprint",
    "_fixed_point_multiply",
    "_fixed_point_ratio",
    "_manifest_validation",
    "_terminal_priority",
    "_trace_replay",
    "_matrix_case",
)
_REFERENCE_FIXTURE_HANDLERS = (
    "build_reference_scenario",
    "issue_reference_principal",
    "issue_reference_observation",
    "issue_reference_challenge",
    "issue_reference_disposition",
    "issue_reference_binding",
    "issue_reference_lease",
    "issue_reference_action_gates",
    "assess_reference_scenario",
    "initialize_reference_window",
    "rotate_reference_context",
    "build_reference_stable_commit",
    "build_reference_portable_commit",
    "build_reference_distributed_commit",
    "issue_reference_witness",
    "issue_reference_distributed_certificate",
    "issue_reference_semantic_conflict_certificate",
    "replay_state_with_receipts",
)

# This is the exact acceptance scope.  It is deliberately static: filesystem
# discovery, call-graph discovery, and current Ruff findings cannot add or
# remove a trust-path function.
REQUIRED_TRUST_PATH_FUNCTIONS = (
    *_CORE_TRUST_PATH_FUNCTIONS,
    *(
        f"pheroos.conformance.checks.hybrid_trace_contract.{name}"
        for name in _HYBRID_TRACE_TRUST_PATH_FUNCTIONS
    ),
    *(
        "pheroos.conformance._commit_tck.reference_adapter."
        f"ReferenceCommitTckAdapter.{name}"
        for name in _REFERENCE_ADAPTER_METHODS
    ),
    *(
        f"pheroos.conformance._commit_tck.reference_adapter._probe_case_{number:02d}"
        for number in range(1, 39)
    ),
    *(
        f"pheroos.conformance._commit_reference.{name}"
        for name in _REFERENCE_FIXTURE_HANDLERS
    ),
)
REQUIRED_MODULE_PATHS = (
    "pheroos/protocol/validation.py",
    "pheroos/trace/_validation_core.py",
    "pheroos/governance/_pheromone/invariants.py",
    "pheroos/governance/_commit/evaluation.py",
    "pheroos/governance/_commit_state/liveness.py",
    "pheroos/conformance/checks/hybrid_trace_contract.py",
    "pheroos/conformance/_commit_tck/reference_adapter.py",
    "pheroos/conformance/_commit_reference.py",
)
REPOSITORY_SCOPE = ("pheroos", "scripts", "tests")
_COMPLEXITY_PATTERN = re.compile(r"\((\d+) > \d+\)$")

# Hash only the immutable scope, baselines, and targets.  The enforcement phase
# may advance from baseline_locked to target_enforced without rewriting history.
LOCKED_SCOPE_SHA256 = (
    "sha256:754019743a98963e0ac5aac83fa354c3ad08671c439bd90bc220a0a8b7e66410"
)


def load_complexity_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load the manifest with duplicate-key and non-finite rejection."""

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("complexity scope manifest must be a JSON object")
    return value


def manifest_shape_failures(manifest: Mapping[str, Any]) -> list[str]:
    """Return fail-closed structural and immutable-scope failures."""

    failures = _root_shape_failures(manifest)
    if failures:
        return failures
    failures.extend(_policy_shape_failures(manifest["policy"]))
    failures.extend(_function_shape_failures(manifest["functions"]))
    failures.extend(_module_shape_failures(manifest["modules"]))
    failures.extend(_repository_shape_failures(manifest["repository_baseline"]))
    observed_hash = locked_scope_sha256(manifest)
    if observed_hash != LOCKED_SCOPE_SHA256:
        failures.append(
            "immutable complexity scope drift: "
            f"{observed_hash} != {LOCKED_SCOPE_SHA256}"
        )
    return failures


def complexity_scope_failures(
    manifest: Mapping[str, Any],
    *,
    function_complexities: Mapping[str, int],
    module_lines: Mapping[str, int],
    repository_metrics: Mapping[str, int],
    require_targets: bool,
) -> list[str]:
    """Evaluate one already-validated static scope observation."""

    failures = _function_observation_failures(
        manifest["functions"],
        function_complexities,
        require_targets=require_targets,
    )
    failures.extend(
        _module_observation_failures(
            manifest["modules"],
            module_lines,
            require_targets=require_targets,
        )
    )
    failures.extend(
        _repository_observation_failures(
            manifest,
            repository_metrics,
            require_targets=require_targets,
        )
    )
    return failures


def observe_function_complexities() -> dict[str, int]:
    """Measure every exact manifest function with Ruff's C901 algorithm."""

    findings = _ruff_findings(
        REQUIRED_MODULE_PATHS,
        maximum=0,
    )
    by_location = _qualified_functions_by_location(REQUIRED_MODULE_PATHS)
    observed: dict[str, int] = {}
    for finding in findings:
        location = _finding_location(finding)
        qualified = by_location.get(location)
        if qualified is None:
            raise ValueError(f"Ruff finding has no AST function at {location}")
        observed[qualified] = _finding_complexity(finding)
    return {
        name: observed[name]
        for name in REQUIRED_TRUST_PATH_FUNCTIONS
        if name in observed
    }


def observe_module_lines() -> dict[str, int]:
    """Return physical source lines for the exact checked-in module scope."""

    return {path: _line_count(ROOT / path) for path in REQUIRED_MODULE_PATHS}


def observe_repository_complexity() -> dict[str, int]:
    """Measure the repository-wide C901 ratchet without defining trust_path."""

    values = [
        _finding_complexity(item)
        for item in _ruff_findings(REPOSITORY_SCOPE, maximum=10)
    ]
    return {
        "complexity_sum": sum(values),
        "maximum_observed": max(values, default=0),
        "over_10_count": len(values),
        "over_20_count": sum(value > 20 for value in values),
        "over_25_count": sum(value > 25 for value in values),
    }


def locked_scope_sha256(manifest: Mapping[str, Any]) -> str:
    """Return the canonical root of immutable scope and limit fields."""

    payload = {
        "functions": manifest.get("functions"),
        "modules": manifest.get("modules"),
        "policy": manifest.get("policy"),
        "repository_baseline": manifest.get("repository_baseline"),
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def _root_shape_failures(manifest: Mapping[str, Any]) -> list[str]:
    required = {
        "enforcement",
        "functions",
        "measurement",
        "modules",
        "policy",
        "repository_baseline",
        "version",
    }
    failures = _exact_keys_failures(manifest, required, label="manifest")
    if manifest.get("version") != MANIFEST_VERSION:
        failures.append("complexity scope manifest version is unsupported")
    if manifest.get("enforcement") not in {"baseline_locked", "target_enforced"}:
        failures.append("complexity scope enforcement phase is unsupported")
    if not isinstance(manifest.get("functions"), list):
        failures.append("complexity scope functions must be an array")
    if not isinstance(manifest.get("modules"), list):
        failures.append("complexity scope modules must be an array")
    if not isinstance(manifest.get("policy"), dict):
        failures.append("complexity scope policy must be an object")
    if not isinstance(manifest.get("repository_baseline"), dict):
        failures.append("repository baseline must be an object")
    return failures


def _policy_shape_failures(policy: Mapping[str, Any]) -> list[str]:
    expected = {
        "new_or_modified_default_maximum": 15,
        "repository_over_10_target": 64,
        "tracked_function_target_maximum": 20,
        "trust_path_absolute_maximum": 25,
        "trust_path_category": TRUST_PATH_CATEGORY,
    }
    failures = _exact_keys_failures(policy, set(expected), label="policy")
    for key, value in expected.items():
        if policy.get(key) != value:
            failures.append(f"complexity policy {key} must equal {value!r}")
    return failures


def _function_shape_failures(functions: Sequence[object]) -> list[str]:
    required_keys = {
        "baseline_complexity",
        "category",
        "owner",
        "qualified_function",
        "target_complexity",
    }
    failures: list[str] = []
    names: list[str] = []
    for index, raw in enumerate(functions):
        if not isinstance(raw, dict):
            failures.append(f"functions[{index}] must be an object")
            continue
        failures.extend(
            _exact_keys_failures(raw, required_keys, label=f"functions[{index}]")
        )
        name = raw.get("qualified_function")
        if isinstance(name, str):
            names.append(name)
        else:
            failures.append(f"functions[{index}].qualified_function is invalid")
        failures.extend(_common_scope_entry_failures(raw, label=f"functions[{index}]"))
        failures.extend(
            _complexity_limit_shape_failures(raw, label=f"functions[{index}]")
        )
    if tuple(names) != REQUIRED_TRUST_PATH_FUNCTIONS:
        failures.append("trust_path function scope does not match the static WP-09 set")
    return failures


def _module_shape_failures(modules: Sequence[object]) -> list[str]:
    required_keys = {
        "baseline_lines",
        "category",
        "owner",
        "path",
        "target_lines",
    }
    failures: list[str] = []
    paths: list[str] = []
    for index, raw in enumerate(modules):
        if not isinstance(raw, dict):
            failures.append(f"modules[{index}] must be an object")
            continue
        failures.extend(
            _exact_keys_failures(raw, required_keys, label=f"modules[{index}]")
        )
        path = raw.get("path")
        if isinstance(path, str):
            paths.append(path)
        else:
            failures.append(f"modules[{index}].path is invalid")
        failures.extend(_common_scope_entry_failures(raw, label=f"modules[{index}]"))
        failures.extend(_line_limit_shape_failures(raw, label=f"modules[{index}]"))
    if tuple(paths) != REQUIRED_MODULE_PATHS:
        failures.append("module scope does not match the static WP-09 set")
    return failures


def _repository_shape_failures(baseline: Mapping[str, Any]) -> list[str]:
    keys = {
        "complexity_sum",
        "maximum_observed",
        "over_10_count",
        "over_20_count",
        "over_25_count",
        "scope",
    }
    failures = _exact_keys_failures(baseline, keys, label="repository_baseline")
    if baseline.get("scope") != list(REPOSITORY_SCOPE):
        failures.append("repository complexity scope must be pheroos/scripts/tests")
    for key in keys - {"scope"}:
        if not _positive_integer(baseline.get(key)):
            failures.append(f"repository baseline {key} must be a positive integer")
    return failures


def _common_scope_entry_failures(
    entry: Mapping[str, Any],
    *,
    label: str,
) -> list[str]:
    failures: list[str] = []
    if entry.get("category") != TRUST_PATH_CATEGORY:
        failures.append(f"{label}.category must be {TRUST_PATH_CATEGORY!r}")
    owner = entry.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        failures.append(f"{label}.owner must be nonblank")
    return failures


def _complexity_limit_shape_failures(
    entry: Mapping[str, Any],
    *,
    label: str,
) -> list[str]:
    failures: list[str] = []
    baseline = entry.get("baseline_complexity")
    target = entry.get("target_complexity")
    if not _positive_integer(baseline):
        failures.append(f"{label}.baseline_complexity must be positive")
    if (
        not isinstance(target, int)
        or isinstance(target, bool)
        or target <= 0
        or target > 20
    ):
        failures.append(f"{label}.target_complexity must be in 1..20")
    return failures


def _line_limit_shape_failures(
    entry: Mapping[str, Any],
    *,
    label: str,
) -> list[str]:
    failures: list[str] = []
    if not _positive_integer(entry.get("baseline_lines")):
        failures.append(f"{label}.baseline_lines must be positive")
    if not _positive_integer(entry.get("target_lines")):
        failures.append(f"{label}.target_lines must be positive")
    return failures


def _function_observation_failures(
    entries: Sequence[Mapping[str, Any]],
    observed: Mapping[str, int],
    *,
    require_targets: bool,
) -> list[str]:
    failures: list[str] = []
    for entry in entries:
        name = entry["qualified_function"]
        value = observed.get(name)
        if value is None:
            failures.append(f"trust_path function is missing: {name}")
            continue
        limit_key = "target_complexity" if require_targets else "baseline_complexity"
        limit = entry[limit_key]
        if value > limit:
            failures.append(f"{name} complexity {value} exceeds {limit_key} {limit}")
    return failures


def _module_observation_failures(
    entries: Sequence[Mapping[str, Any]],
    observed: Mapping[str, int],
    *,
    require_targets: bool,
) -> list[str]:
    failures: list[str] = []
    for entry in entries:
        path = entry["path"]
        value = observed.get(path)
        if value is None:
            failures.append(f"trust_path module is missing: {path}")
            continue
        limit_key = "target_lines" if require_targets else "baseline_lines"
        limit = entry[limit_key]
        if value > limit:
            failures.append(f"{path} lines {value} exceed {limit_key} {limit}")
    return failures


def _repository_observation_failures(
    manifest: Mapping[str, Any],
    observed: Mapping[str, int],
    *,
    require_targets: bool,
) -> list[str]:
    baseline = manifest["repository_baseline"]
    failures = [
        f"repository {key} {observed.get(key)!r} exceeds baseline {limit}"
        for key, limit in baseline.items()
        if key != "scope"
        and (not _nonnegative_integer(observed.get(key)) or observed[key] > limit)
    ]
    target = manifest["policy"]["repository_over_10_target"]
    if require_targets and observed.get("over_10_count", target + 1) > target:
        failures.append(
            "repository over_10_count exceeds final target: "
            f"{observed.get('over_10_count')!r} > {target}"
        )
    return failures


def _ruff_findings(paths: Sequence[str], *, maximum: int) -> list[dict[str, Any]]:
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        *paths,
        "--select",
        "C901",
        "--config",
        f"lint.mccabe.max-complexity={maximum}",
        "--output-format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"Ruff C901 measurement failed ({completed.returncode}): "
            f"{completed.stdout}{completed.stderr}"
        )
    value = json.loads(completed.stdout)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Ruff C901 output must be an array of objects")
    return value


def _qualified_functions_by_location(
    paths: Sequence[str],
) -> dict[tuple[str, int], str]:
    by_location: dict[tuple[str, int], str] = {}
    for raw_path in paths:
        path = ROOT / raw_path
        module = raw_path.removesuffix(".py").replace("/", ".")
        visitor = _QualifiedFunctionVisitor(module, raw_path, by_location)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=raw_path))
    return by_location


class _QualifiedFunctionVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module: str,
        path: str,
        output: dict[tuple[str, int], str],
    ) -> None:
        self._module = module
        self._path = path
        self._output = output
        self._parents: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_parent(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_parent(self, node: ast.ClassDef) -> None:
        self._parents.append(node.name)
        self.generic_visit(node)
        self._parents.pop()

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        qualified = ".".join((self._module, *self._parents, node.name))
        self._output[(self._path, node.lineno)] = qualified
        self._parents.append(node.name)
        self.generic_visit(node)
        self._parents.pop()


def _finding_location(finding: Mapping[str, Any]) -> tuple[str, int]:
    raw_path = finding.get("filename")
    location = finding.get("location")
    if not isinstance(raw_path, str) or not isinstance(location, dict):
        raise ValueError("Ruff finding path/location is invalid")
    row = location.get("row")
    if type(row) is not int:
        raise ValueError("Ruff finding row is invalid")
    path = Path(raw_path)
    if path.is_absolute():
        path = path.relative_to(ROOT)
    return str(path), row


def _finding_complexity(finding: Mapping[str, Any]) -> int:
    message = finding.get("message")
    if not isinstance(message, str):
        raise ValueError("Ruff finding message is invalid")
    match = _COMPLEXITY_PATTERN.search(message)
    if match is None:
        raise ValueError(f"unsupported Ruff C901 message: {message!r}")
    return int(match.group(1))


def _exact_keys_failures(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    label: str,
) -> list[str]:
    observed = set(value)
    return [] if observed == expected else [f"{label} keys must be {sorted(expected)}"]


def _positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def _nonnegative_integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _line_count(path: Path) -> int:
    data = path.read_bytes()
    return data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--require-targets", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = load_complexity_manifest()
        failures = manifest_shape_failures(manifest)
        if not failures:
            require_targets = (
                args.require_targets or manifest["enforcement"] == "target_enforced"
            )
            failures.extend(
                complexity_scope_failures(
                    manifest,
                    function_complexities=observe_function_complexities(),
                    module_lines=observe_module_lines(),
                    repository_metrics=observe_repository_complexity(),
                    require_targets=require_targets,
                )
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    phase = "target" if require_targets else "baseline"
    print(f"complexity scope {phase} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
