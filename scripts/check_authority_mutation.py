#!/usr/bin/env python3
"""Run the small deterministic WP-10 authority mutation manifest."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "process" / "authority-mutation-v1.json"
MANIFEST_VERSION = "pheroos-authority-mutation-v1"
LOCKED_MANIFEST_SHA256 = (
    "sha256:3af14c876ac0b8c5cd15e09f5de31a705ab2988d56f9426d0759eeb65a0bb63f"
)
MutationState = Literal["KILLED", "SURVIVED", "EQUIVALENT_REVIEWED", "INVALID"]
STATES: tuple[MutationState, ...] = (
    "KILLED",
    "SURVIVED",
    "EQUIVALENT_REVIEWED",
    "INVALID",
)
FAMILIES = (
    "authority_level_scope_operation",
    "equality_threshold_quorum_deadline",
    "safe_fallback_stop_output_gate",
    "cas_expected_head_revision",
    "replay_duplicate_currentness",
    "certificate_fingerprint_binding",
    "nonfinite_bool_as_int",
)


@dataclass(frozen=True)
class MutationResult:
    """One classified deterministic mutant execution."""

    mutant_id: str
    family: str
    priority: str
    authority_graph: str
    state: MutationState
    detail: str


def load_mutation_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load a mutation manifest with strict JSON semantics."""

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("authority mutation manifest must be a JSON object")
    return value


def manifest_shape_failures(manifest: Mapping[str, Any]) -> list[str]:
    """Return shape, source-anchor, family, and immutable-root failures."""

    failures = _root_failures(manifest)
    if failures:
        return failures
    failures.extend(_policy_failures(manifest["policy"]))
    failures.extend(_family_failures(manifest["families"]))
    failures.extend(_mutant_failures(manifest["mutants"]))
    failures.extend(_profile_failures(manifest["profiles"], manifest["mutants"]))
    failures.extend(_p0_family_failures(manifest["mutants"]))
    observed = locked_manifest_sha256(manifest)
    if observed != LOCKED_MANIFEST_SHA256:
        failures.append(
            f"immutable mutation manifest drift: {observed} != {LOCKED_MANIFEST_SHA256}"
        )
    return failures


def locked_manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash every mutation, scoring rule, profile, and review declaration."""

    canonical = json.dumps(
        {
            "families": manifest.get("families"),
            "mutants": manifest.get("mutants"),
            "policy": manifest.get("policy"),
            "profiles": manifest.get("profiles"),
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def mutation_gate_failures(
    manifest: Mapping[str, Any], results: Sequence[MutationResult]
) -> list[str]:
    """Evaluate four-state classification and the fixed WP-10 score rules."""

    normalized = _normalized_active_results(manifest, results)
    failures = _classification_failures(normalized)
    failures.extend(_p0_score_failures(manifest, normalized))
    failures.extend(_authority_graph_score_failures(manifest, normalized))
    return failures


def _normalized_active_results(
    manifest: Mapping[str, Any], results: Sequence[MutationResult]
) -> list[MutationResult]:
    by_id: dict[str, list[MutationResult]] = {}
    for result in results:
        by_id.setdefault(result.mutant_id, []).append(result)
    return [
        _normalized_result(manifest, mutant_id, by_id.get(mutant_id, []))
        for mutant_id in sorted(manifest["profiles"]["active"])
    ]


def _normalized_result(
    manifest: Mapping[str, Any],
    mutant_id: str,
    candidates: Sequence[MutationResult],
) -> MutationResult:
    mutant = _mutant_by_id(manifest, mutant_id)
    if not candidates:
        detail = "missing or unexecuted result"
    elif len(candidates) != 1:
        detail = "duplicate results are unclassified"
    else:
        result = candidates[0]
        expected = (
            mutant["family"],
            mutant["priority"],
            mutant["authority_graph"],
        )
        observed = (result.family, result.priority, result.authority_graph)
        if result.state not in STATES:
            detail = f"unclassified result state: {result.state!r}"
        elif observed != expected:
            detail = "result metadata does not match the checked mutant"
        else:
            return result
    return MutationResult(
        mutant_id,
        mutant["family"],
        mutant["priority"],
        mutant["authority_graph"],
        "SURVIVED",
        detail,
    )


def run_profile(
    manifest: Mapping[str, Any],
    *,
    profile: str,
) -> tuple[list[MutationResult], float]:
    """Run an isolated unmutated control before each isolated mutant."""

    selected = [_mutant_by_id(manifest, item) for item in manifest["profiles"][profile]]
    started = time.monotonic()
    results = [_execute_mutant(item) for item in selected]
    return results, time.monotonic() - started


@dataclass(frozen=True)
class _ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed: float
    timed_out: bool = False


def _execute_mutant(mutant: Mapping[str, Any]) -> MutationResult:
    if mutant["equivalent_review"] is not None:
        return _result(mutant, "EQUIVALENT_REVIEWED", "reviewed equivalent")
    try:
        with TemporaryDirectory(prefix=f"pheroos-mutant-{mutant['id']}-") as directory:
            root = Path(directory)
            shutil.copytree(
                ROOT / "pheroos",
                root / "pheroos",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            control = _run_tests(
                root, tuple(mutant["tests"]), mutant["timeout_seconds"]
            )
            if control.returncode != 0:
                return _result(
                    mutant,
                    "INVALID",
                    _process_detail(control, "isolated unmutated control failed"),
                )
            _apply_mutation(root, mutant)
            process = _run_tests(
                root, tuple(mutant["tests"]), mutant["timeout_seconds"]
            )
    except (OSError, ValueError) as exc:
        return _result(mutant, "INVALID", str(exc))
    state, detail = _classify_process(process)
    return _result(mutant, state, detail)


def _run_tests(source_root: Path, tests: Sequence[str], timeout: int) -> _ProcessResult:
    code = (
        "import sys;"
        f"sys.path[:0]=[{str(source_root)!r},{str(ROOT)!r}];"
        "import pheroos;"
        "import pytest;"
        f"raise SystemExit(pytest.main({['-q', '--disable-warnings', '--maxfail=1', '--rootdir', str(ROOT), *tests]!r}))"
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return _ProcessResult(
            returncode=-1,
            stdout=_decoded(exc.stdout),
            stderr=_decoded(exc.stderr),
            elapsed=time.monotonic() - started,
            timed_out=True,
        )
    return _ProcessResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
        time.monotonic() - started,
    )


def _apply_mutation(root: Path, mutant: Mapping[str, Any]) -> None:
    source = mutant["source"]
    path = root / source["path"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start, end = source["start_line"], source["end_line"]
    span = "".join(lines[start - 1 : end])
    if span != source["original"]:
        raise ValueError(f"mutant {mutant['id']} exact source span drifted")
    if _text_sha256(span) != source["sha256"]:
        raise ValueError(f"mutant {mutant['id']} source span hash drifted")
    mutated = "".join(lines[: start - 1]) + source["replacement"] + "".join(lines[end:])
    if mutated == text:
        raise ValueError(f"mutant {mutant['id']} did not change source")
    try:
        compile(mutated, str(path), "exec")
    except SyntaxError as exc:
        raise ValueError(f"mutant {mutant['id']} is not valid Python") from exc
    path.write_text(mutated, encoding="utf-8")


def _classify_process(process: _ProcessResult) -> tuple[MutationState, str]:
    if process.timed_out:
        return "SURVIVED", "test timeout did not reliably kill mutant"
    if process.returncode == 0:
        return "SURVIVED", "selected tests passed"
    if process.returncode == 1:
        return "KILLED", "selected test assertion failed"
    if process.returncode in {2, 3, 4, 5}:
        return "INVALID", _process_detail(process, "pytest infrastructure failure")
    return "SURVIVED", _process_detail(
        process, "unexpected process failure did not reliably kill mutant"
    )


def _process_detail(process: _ProcessResult, prefix: str) -> str:
    tail = "\n".join((process.stdout + "\n" + process.stderr).splitlines()[-4:])
    return f"{prefix} (exit={process.returncode}): {tail}"[:800]


def _result(
    mutant: Mapping[str, Any], state: MutationState, detail: str
) -> MutationResult:
    return MutationResult(
        mutant["id"],
        mutant["family"],
        mutant["priority"],
        mutant["authority_graph"],
        state,
        detail,
    )


def _root_failures(manifest: Mapping[str, Any]) -> list[str]:
    expected = {"families", "manifest_version", "mutants", "policy", "profiles"}
    if set(manifest) != expected:
        return ["mutation manifest root fields must be exact"]
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return [f"mutation manifest_version must be {MANIFEST_VERSION}"]
    return []


def _policy_failures(value: object) -> list[str]:
    expected = {
        "invalid_fails_gate": True,
        "max_duration_seconds": {"pr": 900, "release": 2700},
        "missing_result_state": "SURVIVED",
        "p0_family_kill_percent": 100,
        "score_formula": "KILLED/(KILLED+SURVIVED)",
        "stable_authority_score_percent": 95,
        "states": list(STATES),
        "surviving_p0_max": 0,
        "unmutated_control": "same_temporary_copy_and_import_layout",
    }
    return [] if value == expected else ["mutation scoring policy must match WP-10"]


def _family_failures(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["mutation families must be a list"]
    observed: list[str] = []
    failures: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"description", "id", "priority"}:
            failures.append("mutation family entry must be exact")
            continue
        if item.get("priority") != "P0" or not isinstance(item.get("description"), str):
            failures.append(f"mutation family {item.get('id')} must be described P0")
        identifier = item.get("id")
        observed.append(identifier if isinstance(identifier, str) else "")
    if tuple(observed) != FAMILIES:
        failures.append("mutation families must be the fixed ordered seven-family set")
    return failures


def _mutant_failures(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["mutation manifest needs mutants"]
    failures: list[str] = []
    identifiers: set[str] = set()
    for item in value:
        failures.extend(_one_mutant_failures(item, identifiers))
    return failures


def _one_mutant_failures(value: object, identifiers: set[str]) -> list[str]:
    expected = {
        "authority_graph",
        "equivalent_review",
        "family",
        "id",
        "priority",
        "source",
        "tests",
        "timeout_seconds",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return ["mutation entry must be an exact object"]
    failures: list[str] = []
    identifier = value["id"]
    if not isinstance(identifier, str) or not identifier or identifier in identifiers:
        failures.append("mutation ids must be unique and nonblank")
    else:
        identifiers.add(identifier)
    if value["family"] not in FAMILIES:
        failures.append(f"mutant {identifier} family is invalid")
    if value["priority"] != "P0" or value["authority_graph"] != "stable_authority":
        failures.append(f"mutant {identifier} must be P0 stable_authority")
    if not _test_list(value["tests"]):
        failures.append(f"mutant {identifier} tests must be exact selectors")
    timeout = value["timeout_seconds"]
    if type(timeout) is not int or not 1 <= timeout <= 120:
        failures.append(f"mutant {identifier} timeout must be 1..120 seconds")
    failures.extend(_source_failures(identifier, value["source"]))
    failures.extend(_review_failures(identifier, value["equivalent_review"]))
    return failures


def _source_failures(identifier: str, value: object) -> list[str]:
    expected = {"end_line", "original", "path", "replacement", "sha256", "start_line"}
    if not isinstance(value, dict) or set(value) != expected:
        return [f"mutant {identifier} source declaration must be exact"]
    failures: list[str] = []
    path = value["path"]
    start, end = value["start_line"], value["end_line"]
    if not isinstance(path, str) or not path.startswith("pheroos/") or ".." in path:
        failures.append(f"mutant {identifier} source path is invalid")
        return failures
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        failures.append(f"mutant {identifier} source lines are invalid")
        return failures
    original, replacement = value["original"], value["replacement"]
    if (
        not isinstance(original, str)
        or not isinstance(replacement, str)
        or original == replacement
    ):
        failures.append(f"mutant {identifier} source texts are invalid")
        return failures
    source_path = ROOT / path
    if not source_path.is_file():
        failures.append(f"mutant {identifier} source path is missing")
        return failures
    span = "".join(
        source_path.read_text(encoding="utf-8").splitlines(keepends=True)[
            start - 1 : end
        ]
    )
    if span != original or _text_sha256(span) != value["sha256"]:
        failures.append(f"mutant {identifier} source anchor drifted")
    return failures


def _review_failures(identifier: str, value: object) -> list[str]:
    if value is None:
        return []
    expected = {"exact_source_span", "reason", "reviewed_by"}
    if not isinstance(value, dict) or set(value) != expected:
        return [f"mutant {identifier} equivalent review must be exact"]
    if not all(isinstance(item, str) and item for item in value.values()):
        return [f"mutant {identifier} equivalent review fields must be nonblank"]
    return []


def _profile_failures(profiles: object, mutants: object) -> list[str]:
    if not isinstance(profiles, dict) or set(profiles) != {"active", "pr", "release"}:
        return ["mutation profiles must be exact"]
    if not isinstance(mutants, list):
        return ["mutation profiles cannot resolve mutants"]
    all_ids = [item.get("id") for item in mutants if isinstance(item, dict)]
    failures: list[str] = []
    for name in ("active", "pr", "release"):
        selected = profiles[name]
        if not isinstance(selected, list) or any(
            not isinstance(item, str) for item in selected
        ):
            failures.append(f"mutation profile {name} must be a unique list")
        elif len(selected) != len(set(selected)):
            failures.append(f"mutation profile {name} must be a unique list")
        elif any(item not in all_ids for item in selected):
            failures.append(f"mutation profile {name} references unknown mutant")
    if profiles.get("pr") != all_ids or profiles.get("release") != all_ids:
        failures.append("all checked-in P0 mutants must run in PR and release profiles")
    failures.extend(_profile_timeout_failures(profiles, mutants))
    return failures


def _profile_timeout_failures(
    profiles: Mapping[str, object], mutants: Sequence[object]
) -> list[str]:
    by_id = {
        item["id"]: item
        for item in mutants
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    failures: list[str] = []
    for name, limit in (("pr", 900), ("release", 2700)):
        selected = profiles.get(name)
        if not isinstance(selected, list) or any(
            item not in by_id for item in selected
        ):
            continue
        timeouts = [by_id[item].get("timeout_seconds") for item in selected]
        if any(type(timeout) is not int for timeout in timeouts):
            continue
        timeout_sum = sum(timeout for timeout in timeouts if type(timeout) is int)
        worst_case = max(120, timeout_sum) + timeout_sum
        if worst_case > limit:
            failures.append(
                f"mutation profile {name} timeout budget exceeds {limit} seconds"
            )
    return failures


def _p0_family_failures(mutants: object) -> list[str]:
    if not isinstance(mutants, list):
        return []
    valid = Counter(
        item.get("family")
        for item in mutants
        if isinstance(item, dict)
        and item.get("priority") == "P0"
        and item.get("equivalent_review") is None
    )
    return [
        f"P0 family {family} needs a valid non-equivalent mutant"
        for family in FAMILIES
        if valid[family] < 1
    ]


def _classification_failures(results: Sequence[MutationResult]) -> list[str]:
    failures = [
        f"mutant {item.mutant_id} is INVALID: {item.detail}"
        for item in results
        if item.state == "INVALID"
    ]
    failures.extend(
        f"P0 mutant {item.mutant_id} survived: {item.detail}"
        for item in results
        if item.priority == "P0" and item.state == "SURVIVED"
    )
    return failures


def _p0_score_failures(
    manifest: Mapping[str, Any], results: Sequence[MutationResult]
) -> list[str]:
    failures: list[str] = []
    for family in FAMILIES:
        selected = [
            item for item in results if item.priority == "P0" and item.family == family
        ]
        scoring = [item for item in selected if item.state in {"KILLED", "SURVIVED"}]
        killed = sum(item.state == "KILLED" for item in scoring)
        if (
            not scoring
            or killed * 100
            < len(scoring) * manifest["policy"]["p0_family_kill_percent"]
        ):
            failures.append(f"P0 mutation family {family} kill rate is below 100%")
    survivors = sum(
        item.priority == "P0" and item.state == "SURVIVED" for item in results
    )
    if survivors > manifest["policy"]["surviving_p0_max"]:
        failures.append(f"surviving P0 mutants={survivors}; expected 0")
    return failures


def _authority_graph_score_failures(
    manifest: Mapping[str, Any], results: Sequence[MutationResult]
) -> list[str]:
    scoring = [
        item
        for item in results
        if item.authority_graph == "stable_authority"
        and item.state in {"KILLED", "SURVIVED"}
    ]
    killed = sum(item.state == "KILLED" for item in scoring)
    required = manifest["policy"]["stable_authority_score_percent"]
    if not scoring or killed * 100 < len(scoring) * required:
        return [f"Stable authority mutation score is below {required}%"]
    return []


def _mutant_by_id(manifest: Mapping[str, Any], identifier: str) -> Mapping[str, Any]:
    for item in manifest["mutants"]:
        if isinstance(item, dict) and item.get("id") == identifier:
            return item
    raise ValueError(f"unknown mutant: {identifier}")


def _test_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, str) and item.startswith("tests/") and "::" in item
            for item in value
        )
    )


def _text_sha256(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _decoded(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--profile", choices=("pr", "release"), default="pr")
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run manifest validation, isolated mutants, and deterministic scoring."""

    args = _parser().parse_args(argv)
    try:
        manifest = load_mutation_manifest(args.manifest)
        failures = manifest_shape_failures(manifest)
        if failures:
            raise ValueError("; ".join(failures))
        active = dict(manifest)
        profiles = dict(manifest["profiles"])
        profiles["active"] = profiles[args.profile]
        active["profiles"] = profiles
        results, elapsed = run_profile(manifest, profile=args.profile)
        failures = mutation_gate_failures(active, results)
        limit = manifest["policy"]["max_duration_seconds"][args.profile]
        if elapsed > limit:
            failures.append(f"mutation profile exceeded {limit} seconds")
    except (OSError, ValueError) as exc:
        print(f"authority mutation gate: FAIL: {exc}", file=sys.stderr)
        return 2
    document = _result_document(args.profile, results, elapsed, failures)
    if args.json_output:
        args.json_output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for result in results:
        print(f"{result.mutant_id}: {result.state} ({result.detail})")
    print(_score_line(results))
    if failures:
        for failure in failures:
            print(f"authority mutation gate: FAIL: {failure}", file=sys.stderr)
        return 1
    print("authority mutation gate: PASS")
    return 0


def _result_document(
    profile: str,
    results: Sequence[MutationResult],
    elapsed: float,
    failures: Sequence[str],
) -> dict[str, object]:
    return {
        "elapsed_seconds": round(elapsed, 3),
        "failures": list(failures),
        "profile": profile,
        "results": [
            {
                "authority_graph": item.authority_graph,
                "detail": item.detail,
                "family": item.family,
                "id": item.mutant_id,
                "priority": item.priority,
                "state": item.state,
            }
            for item in results
        ],
        "score": _score(results),
    }


def _score(results: Sequence[MutationResult]) -> dict[str, int]:
    killed = sum(item.state == "KILLED" for item in results)
    survived = sum(item.state == "SURVIVED" for item in results)
    denominator = killed + survived
    return {
        "denominator": denominator,
        "killed": killed,
        "percent": 0 if denominator == 0 else killed * 100 // denominator,
        "survived": survived,
    }


def _score_line(results: Sequence[MutationResult]) -> str:
    score = _score(results)
    return (
        "mutation score: "
        f"{score['killed']}/{score['denominator']}={score['percent']}% "
        f"survived={score['survived']}"
    )


if __name__ == "__main__":  # pragma: no cover - unexecutable import guard
    raise SystemExit(main())
