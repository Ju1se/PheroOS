from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.check_coverage_gate import (
    LOCKED_SCOPE_SHA256,
    MEASUREMENT_SHARDS,
    CoverageMetrics,
    FileCoverage,
    _changed_coverage_failures,
    _critical_branch_failures,
    _critical_coverage_failures,
    _combine_measurements,
    _declared_coverage_shard_files,
    _file_exclusion_failures,
    _final_target_failures,
    _git_changed_path_additions,
    _git_changed_path_statuses,
    _git_diff,
    _included_source_paths,
    _line_exclusion_source_failures,
    _normalize_coverage_document,
    _parse_unified_zero_diff,
    _pytest_collection_policy_failures,
    _ratio_regressions,
    _test_inventory_failures,
    _touch_denominator_source,
    _verified_git_changed_lines,
    declared_baseline_regressions,
    included_source_sha256,
    load_coverage_manifest,
    load_coverage_data,
    locked_scope_sha256,
    manifest_shape_failures,
    pytest_targets_for_shard,
    resolve_ci_base_ref,
)
from scripts.check_ci_supply_chain import COVERAGE_MEASUREMENT_SHARDS
from scripts.run_test_shard import main as run_test_shard


def _file(
    *,
    executable: set[int],
    executed: set[int],
    arcs: set[tuple[int, int]] = set(),
    missing_arcs: set[tuple[int, int]] = set(),
) -> FileCoverage:
    return FileCoverage(
        metrics=CoverageMetrics(
            covered_lines=len(executed),
            total_lines=len(executable),
            covered_branches=len(arcs - missing_arcs),
            total_branches=len(arcs),
        ),
        executable_lines=frozenset(executable),
        executed_lines=frozenset(executed),
        branch_arcs=frozenset(arcs),
        missing_branch_arcs=frozenset(missing_arcs),
    )


def test_checked_coverage_scope_is_locked_and_policy_exact() -> None:
    manifest = load_coverage_manifest()

    assert manifest_shape_failures(manifest) == []
    assert locked_scope_sha256(manifest) == LOCKED_SCOPE_SHA256
    assert manifest["tooling"] == {
        "branch_coverage": True,
        "ci_only": True,
        "name": "coverage",
        "runtime_dependencies_empty": True,
        "version": "7.15.2",
    }
    assert {
        item["measurement_source_sha256"] for item in manifest["baselines"].values()
    } == {included_source_sha256(manifest)}


def test_ci_base_resolution_prefers_pr_then_push_and_fails_safe_to_parent() -> None:
    assert resolve_ci_base_ref("a" * 40, "b" * 40) == "a" * 40
    assert resolve_ci_base_ref("", "b" * 40) == "b" * 40
    assert resolve_ci_base_ref("0" * 40, None) == "HEAD^"


def test_denominator_families_and_only_allowed_exclusions_are_explicit() -> None:
    manifest = load_coverage_manifest()
    groups = {item["name"]: item["included"] for item in manifest["scope"]["groups"]}

    assert groups == {
        "authority_validator": True,
        "compatibility_facade": True,
        "generated_facade": False,
        "schema_declaration": True,
        "stable_owner": True,
        "tck_fixture": True,
    }
    assert {item["path"] for item in manifest["scope"]["file_exclusions"]} == {
        "pheroos/governance/_public_api.py",
    }
    assert [item["id"] for item in manifest["scope"]["line_exclusions"]] == [
        "type_checking",
    ]
    assert manifest["measurement"]["pytest_python_files"] == ["test_*.py"]
    compatibility = next(
        item
        for item in manifest["scope"]["groups"]
        if item["name"] == "compatibility_facade"
    )
    generated = next(
        item
        for item in manifest["scope"]["groups"]
        if item["name"] == "generated_facade"
    )
    assert "pheroos/governance/__init__.py" in compatibility["patterns"]
    assert "pheroos/governance/__init__.py" not in generated["patterns"]
    assert "pheroos/governance/__init__.py" in _included_source_paths(manifest)


def test_measurement_shards_cover_every_test_exactly_once() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = load_coverage_manifest()
    shards = manifest["measurement"]["shards"]

    assert tuple(item["name"] for item in shards) == MEASUREMENT_SHARDS
    assert COVERAGE_MEASUREMENT_SHARDS == MEASUREMENT_SHARDS
    targets = [target for shard in shards for target in shard["pytest_targets"]]
    expected = {
        path.relative_to(root).as_posix()
        for path in (root / "tests").rglob("test_*.py")
    }
    assert len(targets) == len(set(targets))
    assert set(targets) == expected


def test_measurement_shard_omission_is_fail_closed() -> None:
    manifest = deepcopy(load_coverage_manifest())
    manifest["measurement"]["shards"][1]["pytest_targets"].pop()

    assert any(
        "coverage test is unsharded" in item
        for item in manifest_shape_failures(manifest)
    )


def test_pytest_collection_policy_rejects_default_alternate_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_files = ["test_*.py", "*_test.py"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)

    assert _pytest_collection_policy_failures(["test_*.py"]) == [
        "pyproject pytest python_files must be exactly test_*.py"
    ]


def test_alternate_security_test_filename_is_rejected_from_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "security_test.py").write_text(
        "def test_hidden(): pass\n", encoding="utf-8"
    )
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)

    assert _test_inventory_failures({"foundation": set()}) == [
        "pytest alternate test filename is forbidden by the locked inventory: "
        "tests/security_test.py"
    ]


def test_coverage_artifact_inventory_rejects_missing_or_extra_shards(
    tmp_path: Path,
) -> None:
    for shard in MEASUREMENT_SHARDS:
        (tmp_path / f".coverage.{shard}").write_bytes(b"coverage")

    assert [path.name for path in _declared_coverage_shard_files(tmp_path)] == [
        f".coverage.{shard}" for shard in MEASUREMENT_SHARDS
    ]
    (tmp_path / ".coverage.injected").write_bytes(b"injected")

    with pytest.raises(ValueError, match="unexpected=.*injected"):
        _declared_coverage_shard_files(tmp_path)


def test_stable_owner_scope_matches_checked_candidate_artifact() -> None:
    root = Path(__file__).resolve().parents[2]
    artifact = json.loads(
        (root / "pheroos/conformance/abi/stable-python-api-v1.json").read_text(
            encoding="utf-8"
        )
    )
    owners = {
        item["shape"]["binding_owner"]
        for package in artifact["packages"].values()
        for item in package["exports"]
        if item["shape"].get("binding_owner")
    }
    expected: set[str] = set()
    for owner in owners:
        module = root / (owner.replace(".", "/") + ".py")
        if module.is_file():
            expected.add(module.relative_to(root).as_posix())
        else:
            expected.add(owner.replace(".", "/") + "/__init__.py")
    manifest = load_coverage_manifest()
    stable = next(
        item for item in manifest["scope"]["groups"] if item["name"] == "stable_owner"
    )

    assert set(stable["patterns"]) == expected


def test_locked_scope_rejects_baseline_or_exclusion_weakening() -> None:
    baseline = deepcopy(load_coverage_manifest())
    baseline["baselines"]["repository"]["covered_lines"] -= 1
    exclusion = deepcopy(load_coverage_manifest())
    exclusion["scope"]["file_exclusions"].append(
        {
            "category": "generated_facade",
            "generator": "scripts/generate_governance_public_api.py",
            "path": "pheroos/governance/output.py",
            "sha256": "sha256:" + "0" * 64,
        }
    )

    assert any(
        "immutable coverage scope drift" in item
        for item in manifest_shape_failures(baseline)
    )
    assert any(
        "only the declarative generated" in item
        for item in manifest_shape_failures(exclusion)
    )


def test_excluded_generated_declaration_cannot_gain_runtime_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "pheroos/governance/_public_api.py"
    source = (
        '"""deceptive generated declaration"""\n'
        "from types import MappingProxyType\n"
        "def execute() -> None:\n"
        "    raise RuntimeError\n"
    )
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)
    exclusion = {
        "category": "generated_facade",
        "generator": "scripts/generate_governance_public_api.py",
        "path": path,
        "sha256": "sha256:" + sha256(source.encode("utf-8")).hexdigest(),
    }

    assert _file_exclusion_failures([exclusion]) == [
        "coverage excluded declaration contains runtime behavior: " + path
    ]


def test_baseline_source_digest_must_bind_the_current_denominator() -> None:
    manifest = deepcopy(load_coverage_manifest())
    for baseline in manifest["baselines"].values():
        baseline["measurement_source_sha256"] = "sha256:" + "0" * 64

    assert any(
        "source digest does not match included source" in item
        for item in manifest_shape_failures(manifest)
    )


def test_line_exclusions_reject_indented_runtime_guards() -> None:
    manifest = deepcopy(load_coverage_manifest())
    manifest["scope"]["line_exclusions"][0]["regex"] = "^\\s*if TYPE_CHECKING:"

    assert any(
        "line exclusions are not the allowlist" in item
        for item in manifest_shape_failures(manifest)
    )


@pytest.mark.parametrize(
    ("module", "path", "arguments"),
    [
        ("pheroos.cli.main", "pheroos/cli/main.py", ["--help"]),
        (
            "pheroos.conformance.commit_tck_v2_spec_adapter",
            "pheroos/conformance/commit_tck_v2_spec_adapter.py",
            [],
        ),
    ],
)
def test_executable_main_guards_are_covered_by_subprocess_execution(
    tmp_path: Path,
    module: str,
    path: str,
    arguments: list[str],
) -> None:
    coverage = pytest.importorskip("coverage")
    root = Path(__file__).resolve().parents[2]
    data_file = tmp_path / (module.replace(".", "-") + ".coverage")
    code = f"""\
import coverage
import importlib
import runpy
import sys
sys.path.insert(0, {str(root)!r})
cov = coverage.Coverage(data_file={str(data_file)!r}, branch=True, source=["pheroos"])
cov.start()
importlib.import_module({module!r})
sys.argv = [{module!r}, *{arguments!r}]
try:
    runpy.run_module({module!r}, run_name="__main__")
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise
finally:
    cov.stop()
    cov.save()
"""
    env = dict(os.environ)
    env.pop("COVERAGE_FILE", None)
    env.pop("COVERAGE_PROCESS_START", None)
    adapter_input = ""
    if module.endswith("commit_tck_v2_spec_adapter"):
        adapter_input = (
            '{"message_type":"handshake","adapter_protocol":'
            '"pheroos-commit-tck-jsonl-v2","session_id":"coverage",'
            '"tck_version":"pheroos-commit-integrity-tck-v2",'
            '"request_version":"pheroos-commit-tck-request-v2",'
            '"response_version":"pheroos-commit-tck-response-v2",'
            '"operations":["fixed_point_multiply"]}\n'
            '{"message_type":"close","session_id":"coverage"}\n'
        )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=root,
        env=env,
        input=adapter_input,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
    data = coverage.CoverageData(basename=str(data_file))
    data.read()
    measured = next(item for item in data.measured_files() if item.endswith(path))
    guard_line = next(
        number
        for number, line in enumerate(
            (root / path).read_text(encoding="utf-8").splitlines(), start=1
        )
        if line.startswith('if __name__ == "__main__":')
    )
    assert guard_line in (data.lines(measured) or [])
    guard_destinations = {
        destination
        for origin, destination in (data.arcs(measured) or [])
        if origin == guard_line and destination != guard_line
    }
    assert len(guard_destinations) == 2


def _line_guard_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    scope = deepcopy(load_coverage_manifest()["scope"])
    target = tmp_path / "pheroos" / "guarded.py"
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)
    return _line_exclusion_source_failures(scope)


def test_type_checking_exclusion_requires_direct_unshadowed_top_level_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = """\
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from package import StaticType

del TYPE_CHECKING
"""

    assert _line_guard_failures(tmp_path, monkeypatch, source) == []


def test_included_source_rejects_inline_no_cover_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures = _line_guard_failures(
        tmp_path,
        monkeypatch,
        "def authorize(value: bool) -> bool:\n"
        "    if value:  # PRAGMA: NO COVER\n"
        "        return True\n"
        "    return False\n",
    )

    assert failures == ["inline no-cover exclusion is forbidden: pheroos/guarded.py:2"]


def test_included_source_rejects_default_no_cover_spelling_without_colon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures = _line_guard_failures(
        tmp_path,
        monkeypatch,
        "def authorize(value: bool) -> bool:\n"
        "    if value:  # pragma no cover\n"
        "        return True\n"
        "    return False\n",
    )

    assert failures == ["inline no-cover exclusion is forbidden: pheroos/guarded.py:2"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from typing import TYPE_CHECKING\n"
            "TYPE_CHECKING = True\n"
            "if TYPE_CHECKING:\n"
            "    runtime()\n",
            "binding is reassigned or shadowed",
        ),
        (
            "if TYPE_CHECKING:\n    runtime()\nfrom typing import TYPE_CHECKING\n",
            "requires a prior direct",
        ),
        (
            'PAYLOAD = """\nif TYPE_CHECKING:\n    runtime()\n"""\n',
            "not an exact top-level guard",
        ),
        (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    static()\n"
            "def runtime(TYPE_CHECKING: bool) -> None:\n"
            "    pass\n",
            "binding is reassigned or shadowed",
        ),
    ],
)
def test_type_checking_exclusion_rejects_textual_or_shadowed_bypasses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    expected: str,
) -> None:
    assert any(
        expected in failure
        for failure in _line_guard_failures(tmp_path, monkeypatch, source)
    )


def test_ratchet_compares_exact_ratios_without_rounding() -> None:
    baseline = CoverageMetrics(
        covered_lines=8, total_lines=10, covered_branches=3, total_branches=4
    )

    assert (
        _ratio_regressions(
            "scope",
            CoverageMetrics(80, 100, 75, 100),
            baseline,
        )
        == []
    )
    assert _ratio_regressions(
        "scope",
        CoverageMetrics(79, 100, 74, 100),
        baseline,
    ) == [
        "scope line coverage regressed below locked baseline",
        "scope branch coverage regressed below locked baseline",
    ]


def test_declared_baselines_cannot_be_lowered_from_base_revision() -> None:
    current = deepcopy(load_coverage_manifest())
    previous = deepcopy(current)
    for name in ("repository", "stable_authority"):
        current["baselines"][name].update(
            covered_lines=8,
            total_lines=10,
            covered_branches=8,
            total_branches=10,
        )
        previous["baselines"][name].update(
            covered_lines=9,
            total_lines=10,
            covered_branches=9,
            total_branches=10,
        )

    failures = declared_baseline_regressions(current, previous)

    assert failures == [
        "repository declared baseline line coverage regressed below locked baseline",
        "repository declared baseline branch coverage regressed below locked baseline",
        "stable_authority declared baseline line coverage regressed below locked baseline",
        "stable_authority declared baseline branch coverage regressed below locked baseline",
    ]


def test_final_repository_and_authority_targets_are_hard_failures() -> None:
    manifest = load_coverage_manifest()
    observations = {
        "repository": CoverageMetrics(899, 1000, 849, 1000),
        "stable_authority": CoverageMetrics(969, 1000, 949, 1000),
    }

    failures = _final_target_failures(manifest, observations)

    assert failures == [
        "repository line coverage is 899/1000; requires at least 90%",
        "repository branch coverage is 849/1000; requires at least 85%",
        "Stable/authority line coverage is 969/1000; requires at least 97%",
        "Stable/authority branch coverage is 949/1000; requires at least 95%",
    ]


def test_final_targets_accept_exact_boundaries() -> None:
    manifest = load_coverage_manifest()
    observations = {
        "repository": CoverageMetrics(900, 1000, 850, 1000),
        "stable_authority": CoverageMetrics(970, 1000, 950, 1000),
    }

    assert _final_target_failures(manifest, observations) == []


def test_changed_authority_lines_and_branches_fail_closed() -> None:
    pytest.importorskip("coverage")
    manifest = load_coverage_manifest()
    path = "pheroos/governance/output.py"
    coverage = _file(
        executable={10, 11},
        executed={10},
        arcs={(11, 12), (11, 13)},
        missing_arcs={(11, 13)},
    )

    failures = _changed_coverage_failures(
        manifest,
        {path: coverage},
        {path: frozenset({10, 11})},
    )

    assert any("changed authority lines" in item for item in failures)
    assert any("changed authority branches" in item for item in failures)


def test_changed_stable_owner_uses_authority_thresholds() -> None:
    pytest.importorskip("coverage")
    manifest = load_coverage_manifest()
    path = "pheroos/drivers/base.py"
    coverage = _file(
        executable={10},
        executed=set(),
    )

    failures = _changed_coverage_failures(
        manifest,
        {path: coverage},
        {path: frozenset({10})},
    )

    assert failures == ["changed authority lines is 0/1; requires at least 100%"]


def test_multiline_authority_condition_maps_to_its_branch_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("coverage")
    source = """\
def authorize(authority: bool, stopped: bool) -> bool:
    if (
        authority
        and stopped
    ):
        return True
    return False
"""
    path = "pheroos/governance/output.py"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)
    statement = source.splitlines().index("    if (") + 1
    continuation = source.splitlines().index("        and stopped") + 1
    coverage = _file(
        executable={statement},
        executed=set(),
        arcs={(statement, statement + 4), (statement, statement + 5)},
        missing_arcs={(statement, statement + 5)},
    )

    failures = _changed_coverage_failures(
        load_coverage_manifest(),
        {path: coverage},
        {path: frozenset({continuation})},
    )

    assert any("changed authority lines" in failure for failure in failures)
    assert any("changed authority branches" in failure for failure in failures)


def test_multiline_ordinary_call_maps_to_its_statement_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("coverage")
    source = """\
def values() -> tuple[str, ...]:
    return tuple(
        [
            "value",
        ]
    )
"""
    path = "pheroos/drivers/data.py"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)
    statement = source.splitlines().index("    return tuple(") + 1
    continuation = source.splitlines().index('            "value",') + 1
    coverage = _file(executable={statement}, executed=set())

    failures = _changed_coverage_failures(
        load_coverage_manifest(),
        {path: coverage},
        {path: frozenset({continuation})},
    )

    assert failures == ["changed ordinary lines is 0/1; requires at least 95%"]


def test_named_critical_branch_requires_both_arcs() -> None:
    manifest = deepcopy(load_coverage_manifest())
    manifest["critical_branches"] = [
        {"line": 7, "name": "critical", "path": "pheroos/governance/output.py"}
    ]
    coverage = _file(
        executable={7},
        executed={7},
        arcs={(7, 8), (7, 9)},
        missing_arcs={(7, 9)},
    )

    assert _critical_coverage_failures(
        manifest, {"pheroos/governance/output.py": coverage}
    ) == ["critical branch critical is not fully covered: [(7, 9)]"]


def _critical_entry(path: str, line: int, original: str) -> dict[str, object]:
    return {
        "line": line,
        "name": "critical",
        "path": path,
        "source": {
            "ast_kind": "If",
            "end_line": line,
            "original": original,
            "sha256": "sha256:" + sha256(original.encode("utf-8")).hexdigest(),
            "start_line": line,
        },
    }


def test_critical_branch_source_span_and_ast_anchor_are_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "pheroos/governance/gate.py"
    source = "def gate(value: bool) -> bool:\n    if value:\n        return True\n    return False\n"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)

    assert (
        _critical_branch_failures([_critical_entry(path, 2, "    if value:\n")]) == []
    )


def test_critical_branch_rejects_ast_kind_spoof_with_matching_span_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "pheroos/governance/gate.py"
    source = "def gate(value: bool) -> bool:\n    while value:\n        return True\n    return False\n"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)

    assert _critical_branch_failures(
        [_critical_entry(path, 2, "    while value:\n")]
    ) == ["critical branch critical AST anchor drifted"]


def test_critical_branch_rejects_source_span_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "pheroos/governance/gate.py"
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(
        "def gate(value: bool) -> bool:\n    if not value:\n        return True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("scripts.check_coverage_gate.ROOT", tmp_path)

    assert _critical_branch_failures([_critical_entry(path, 2, "    if value:\n")]) == [
        "critical branch critical exact source span drifted"
    ]


def test_unified_zero_diff_parser_tracks_only_added_python_lines() -> None:
    diff = """\
diff --git a/pheroos/a.py b/pheroos/a.py
--- a/pheroos/a.py
+++ b/pheroos/a.py
@@ -2,0 +3,2 @@
+first
+second
diff --git a/docs/a.md b/docs/a.md
--- a/docs/a.md
+++ b/docs/a.md
@@ -0,0 +1 @@
+ignored
"""

    assert _parse_unified_zero_diff(diff) == {"pheroos/a.py": {3, 4}}


def test_unified_diff_source_text_cannot_forge_a_new_file_header() -> None:
    diff = """\
diff --git a/pheroos/a.py b/pheroos/a.py
--- a/pheroos/a.py
+++ b/pheroos/a.py
@@ -1,2 +1,2 @@
-old
++++ b/pheroos/fake.py
 context
"""

    assert _parse_unified_zero_diff(
        diff,
        path_statuses={"pheroos/a.py": "M"},
        expected_additions={"pheroos/a.py": 1},
    ) == {"pheroos/a.py": {1}}


def test_unified_diff_rejects_misassigned_or_extra_path_headers() -> None:
    misassigned = """\
diff --git a/pheroos/a.py b/pheroos/a.py
--- a/pheroos/a.py
+++ b/pheroos/fake.py
@@ -0,0 +1 @@
+changed
"""
    extra = """\
diff --git a/pheroos/a.py b/pheroos/a.py
--- a/pheroos/a.py
+++ b/pheroos/a.py
@@ -0,0 +1 @@
+changed
diff --git a/pheroos/fake.py b/pheroos/fake.py
--- a/pheroos/fake.py
+++ b/pheroos/fake.py
@@ -0,0 +1 @@
+forged
"""

    with pytest.raises(ValueError, match="new path is invalid"):
        _parse_unified_zero_diff(
            misassigned,
            path_statuses={"pheroos/a.py": "M"},
            expected_additions={"pheroos/a.py": 1},
        )
    with pytest.raises(ValueError, match="undeclared or duplicate"):
        _parse_unified_zero_diff(
            extra,
            path_statuses={"pheroos/a.py": "M"},
            expected_additions={"pheroos/a.py": 1},
        )


def test_unified_diff_rejects_numstat_addition_mismatch() -> None:
    diff = """\
diff --git a/pheroos/a.py b/pheroos/a.py
--- a/pheroos/a.py
+++ b/pheroos/a.py
@@ -0,0 +1 @@
+changed
"""

    with pytest.raises(ValueError, match="addition mismatch"):
        _parse_unified_zero_diff(
            diff,
            path_statuses={"pheroos/a.py": "M"},
            expected_additions={"pheroos/a.py": 2},
        )


def test_changed_diff_rejects_a_quoted_python_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quoted = """\
diff --git "a/pheroos/café.py" "b/pheroos/café.py"
--- "a/pheroos/café.py"
+++ "b/pheroos/café.py"
@@ -0,0 +1 @@
+changed
"""
    monkeypatch.setattr("scripts.check_coverage_gate._git_diff", lambda *_: quoted)
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_changed_path_statuses",
        lambda *_: {"pheroos/café.py": "M"},
    )
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_changed_path_additions",
        lambda *_: {"pheroos/café.py": 1},
    )
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_typechanged_python_paths",
        lambda *_: set(),
    )

    with pytest.raises(ValueError, match="undeclared"):
        _verified_git_changed_lines("base", "HEAD")


def test_git_nul_raw_and_numstat_inventories_are_parsed_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter(
        [
            SimpleNamespace(
                returncode=0,
                stdout=(b":100644 100644 0123456 789abcd M\0pheroos/a.py\0"),
                stderr=b"",
            ),
            SimpleNamespace(
                returncode=0,
                stdout=b"2\t1\tpheroos/a.py\0",
                stderr=b"",
            ),
        ]
    )
    monkeypatch.setattr(
        "scripts.check_coverage_gate.subprocess.run",
        lambda *_args, **_kwargs: next(results),
    )

    assert _git_changed_path_statuses("base", "HEAD") == {"pheroos/a.py": "M"}
    assert _git_changed_path_additions("base", "HEAD") == {"pheroos/a.py": 2}


def test_verified_diff_rejects_raw_numstat_inventory_disagreement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_typechanged_python_paths",
        lambda *_: set(),
    )
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_changed_path_statuses",
        lambda *_: {"pheroos/a.py": "M"},
    )
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_changed_path_additions",
        lambda *_: {"pheroos/fake.py": 1},
    )
    monkeypatch.setattr("scripts.check_coverage_gate._git_diff", lambda *_: "")

    with pytest.raises(ValueError, match="raw and numstat"):
        _verified_git_changed_lines("base", "HEAD")


def test_git_diff_forces_stable_unquoted_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        observed.extend(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("scripts.check_coverage_gate.subprocess.run", run)

    assert _git_diff("base", "HEAD") == ""
    assert observed[:4] == ["git", "-c", "core.quotePath=false", "diff"]
    assert "--no-renames" in observed
    assert "--src-prefix=a/" in observed
    assert "--dst-prefix=b/" in observed


def test_changed_diff_rejects_python_type_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.check_coverage_gate._git_diff", lambda *_: "")
    monkeypatch.setattr(
        "scripts.check_coverage_gate._git_typechanged_python_paths",
        lambda *_: {"pheroos/governance/output.py"},
    )

    with pytest.raises(ValueError, match="unsupported Git type changes"):
        _verified_git_changed_lines("base", "HEAD")


def test_boolean_baseline_counter_is_rejected() -> None:
    manifest = deepcopy(load_coverage_manifest())
    manifest["baselines"]["repository"]["covered_lines"] = True

    assert any("covered_lines" in item for item in manifest_shape_failures(manifest))


def test_statement_only_coverage_data_is_rejected() -> None:
    document = {"meta": {"branch_coverage": False}, "files": {}}

    with pytest.raises(ValueError, match="branch coverage"):
        _normalize_coverage_document(document)


def test_zero_touch_keeps_unimported_denominator_source_uncovered(
    tmp_path: Path,
) -> None:
    coverage = pytest.importorskip("coverage")
    manifest = load_coverage_manifest()
    data_file = tmp_path / ".coverage"
    data = coverage.CoverageData(basename=str(data_file))
    data.add_arcs({"pheroos/_version.py": {(3, 3)}})
    data.write()

    _touch_denominator_source(manifest, data_file)
    files = load_coverage_data(manifest, data_file=data_file)
    touched = files["pheroos/governance/_support_v2/support_contracts.py"]

    assert touched.metrics.covered_lines == 0
    assert touched.metrics.total_lines > 0
    assert files["pheroos/_version.py"].metrics.covered_lines == 1
    failures = _final_target_failures(
        manifest,
        {"repository": touched.metrics, "stable_authority": touched.metrics},
    )
    assert any("repository line coverage" in failure for failure in failures)
    assert any("Stable/authority line coverage" in failure for failure in failures)


def test_combine_unions_absolute_and_relative_coverage_paths(tmp_path: Path) -> None:
    coverage = pytest.importorskip("coverage")
    relative = "pheroos/_version.py"
    absolute = str((Path(__file__).resolve().parents[2] / relative).resolve())
    first_path = tmp_path / ".coverage.first"
    second_path = tmp_path / ".coverage.second"
    output = tmp_path / ".coverage.combined"
    first = coverage.CoverageData(basename=str(first_path))
    first.add_arcs({relative: {(3, 3)}})
    first.write()
    second = coverage.CoverageData(basename=str(second_path))
    second.add_arcs({absolute: {(5, 5)}})
    second.write()

    _combine_measurements([first_path, second_path], output)
    combined = coverage.CoverageData(basename=str(output))
    combined.read()

    assert combined.measured_files() == {relative}
    assert combined.lines(relative) == [3, 5]


def test_noncoverage_runner_uses_the_same_checked_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[list[str]] = []

    def run(command: list[str], *, check: bool) -> SimpleNamespace:
        assert check is False
        observed.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.run_test_shard.subprocess.run", run)

    assert run_test_shard(["foundation"]) == 0
    assert observed[0][:4] == [sys.executable, "-m", "pytest", "-q"]
    assert observed[0][4:] == pytest_targets_for_shard(
        load_coverage_manifest(), "foundation"
    )
