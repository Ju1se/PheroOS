from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.check_authority_mutation import (
    FAMILIES,
    LOCKED_MANIFEST_SHA256,
    MutationResult,
    _classify_process,
    _execute_mutant,
    _ProcessResult,
    load_mutation_manifest,
    locked_manifest_sha256,
    manifest_shape_failures,
    mutation_gate_failures,
)


def _result(mutant: dict[str, object], state: str) -> MutationResult:
    return MutationResult(
        mutant_id=str(mutant["id"]),
        family=str(mutant["family"]),
        priority=str(mutant["priority"]),
        authority_graph=str(mutant["authority_graph"]),
        state=state,  # type: ignore[arg-type]
        detail="simulated",
    )


def test_checked_mutation_manifest_is_exact_locked_and_source_anchored() -> None:
    manifest = load_mutation_manifest()

    assert manifest_shape_failures(manifest) == []
    assert locked_manifest_sha256(manifest) == LOCKED_MANIFEST_SHA256
    assert tuple(item["id"] for item in manifest["families"]) == FAMILIES
    assert len(manifest["mutants"]) == len(FAMILIES) == 7


def test_all_seven_killed_pass_fixed_p0_and_stable_authority_scores() -> None:
    manifest = load_mutation_manifest()
    results = [_result(item, "KILLED") for item in manifest["mutants"]]

    assert mutation_gate_failures(manifest, results) == []


def test_missing_result_is_scored_as_survived_and_fails_p0() -> None:
    manifest = load_mutation_manifest()
    results = [_result(item, "KILLED") for item in manifest["mutants"][:-1]]

    failures = mutation_gate_failures(manifest, results)

    assert any("missing or unexecuted" in item for item in failures)
    assert any("kill rate is below 100%" in item for item in failures)
    assert any("surviving P0 mutants=1" in item for item in failures)


def test_invalid_is_not_scored_but_fails_the_gate() -> None:
    manifest = load_mutation_manifest()
    results = [_result(item, "KILLED") for item in manifest["mutants"]]
    results[0] = _result(manifest["mutants"][0], "INVALID")

    failures = mutation_gate_failures(manifest, results)

    assert any("is INVALID" in item for item in failures)
    assert any(FAMILIES[0] in item and "kill rate" in item for item in failures)


def test_unclassified_or_duplicate_result_is_scored_as_survived() -> None:
    manifest = load_mutation_manifest()
    results = [_result(item, "KILLED") for item in manifest["mutants"]]
    results[0] = _result(manifest["mutants"][0], "UNKNOWN")
    results.append(results[1])

    failures = mutation_gate_failures(manifest, results)

    assert any("unclassified result state" in item for item in failures)
    assert any("duplicate results" in item for item in failures)
    assert any("surviving P0 mutants=2" in item for item in failures)


def test_timeout_or_non_pytest_process_failure_is_survived() -> None:
    timed_out = _ProcessResult(-1, "", "", 30.0, timed_out=True)
    crashed = _ProcessResult(-9, "", "terminated", 0.1)
    infrastructure = _ProcessResult(3, "", "internal error", 0.1)

    assert _classify_process(timed_out)[0] == "SURVIVED"
    assert _classify_process(crashed)[0] == "SURVIVED"
    assert _classify_process(infrastructure)[0] == "INVALID"


def test_source_span_drift_and_manifest_weakening_fail_closed() -> None:
    source = deepcopy(load_mutation_manifest())
    source["mutants"][0]["source"]["original"] = "pass\n"
    policy = deepcopy(load_mutation_manifest())
    policy["policy"]["surviving_p0_max"] = 1
    control = deepcopy(load_mutation_manifest())
    control["policy"]["unmutated_control"] = "repository_root_only"

    assert any(
        "source anchor drifted" in item for item in manifest_shape_failures(source)
    )
    assert any("scoring policy" in item for item in manifest_shape_failures(policy))
    assert any("scoring policy" in item for item in manifest_shape_failures(control))


def test_pr_profile_timeout_budget_is_fail_closed() -> None:
    manifest = deepcopy(load_mutation_manifest())
    for mutant in manifest["mutants"]:
        mutant["timeout_seconds"] = 120

    assert any(
        "profile pr timeout budget" in item
        for item in manifest_shape_failures(manifest)
    )


def test_reviewed_equivalent_cannot_replace_required_p0_mutant() -> None:
    manifest = deepcopy(load_mutation_manifest())
    manifest["mutants"][0]["equivalent_review"] = {
        "exact_source_span": "pheroos/example.py:1",
        "reason": "proved equivalent",
        "reviewed_by": "maintainer",
    }

    assert any(
        FAMILIES[0] in item and "valid non-equivalent" in item
        for item in manifest_shape_failures(manifest)
    )


def test_path_sensitive_unmutated_control_cannot_fake_a_killed_mutant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "pheroos"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from .gate import authorize\n", encoding="utf-8"
    )
    original = "def authorize() -> bool:\n    return True\n"
    (package / "gate.py").write_text(original, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_path_sensitive.py").write_text(
        "from pathlib import Path\n"
        "import pheroos\n\n"
        "def test_import_comes_from_repository_layout() -> None:\n"
        "    expected = Path(__file__).resolve().parents[1] / 'pheroos' / '__init__.py'\n"
        "    assert Path(pheroos.__file__).resolve() == expected\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_authority_mutation.ROOT", tmp_path)
    mutant = {
        "authority_graph": "stable_authority",
        "equivalent_review": None,
        "family": FAMILIES[0],
        "id": "path-sensitive",
        "priority": "P0",
        "source": {
            "end_line": 2,
            "original": "    return True\n",
            "path": "pheroos/gate.py",
            "replacement": "    return False\n",
            "sha256": "sha256:" + sha256(b"    return True\n").hexdigest(),
            "start_line": 2,
        },
        "tests": [
            "tests/test_path_sensitive.py::test_import_comes_from_repository_layout"
        ],
        "timeout_seconds": 30,
    }

    result = _execute_mutant(mutant)

    assert result.state == "INVALID"
    assert "isolated unmutated control failed" in result.detail


def test_control_and_mutant_use_the_same_temporary_source_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "pheroos"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "gate.py").write_text(
        "def authorize() -> bool:\n    return True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_authority_mutation.ROOT", tmp_path)
    observed: list[tuple[Path, str]] = []

    def run_tests(source_root: Path, _tests: object, _timeout: int) -> _ProcessResult:
        observed.append(
            (
                source_root,
                (source_root / "pheroos" / "gate.py").read_text(encoding="utf-8"),
            )
        )
        return _ProcessResult(0 if len(observed) == 1 else 1, "", "", 0.01)

    monkeypatch.setattr("scripts.check_authority_mutation._run_tests", run_tests)
    mutant = {
        "authority_graph": "stable_authority",
        "equivalent_review": None,
        "family": FAMILIES[0],
        "id": "same-layout",
        "priority": "P0",
        "source": {
            "end_line": 2,
            "original": "    return True\n",
            "path": "pheroos/gate.py",
            "replacement": "    return False\n",
            "sha256": "sha256:" + sha256(b"    return True\n").hexdigest(),
            "start_line": 2,
        },
        "tests": ["tests/test_gate.py::test_gate"],
        "timeout_seconds": 30,
    }

    result = _execute_mutant(mutant)

    assert result.state == "KILLED"
    assert observed[0][0] == observed[1][0]
    assert observed[0][0] != tmp_path
    assert "return True" in observed[0][1]
    assert "return False" in observed[1][1]
