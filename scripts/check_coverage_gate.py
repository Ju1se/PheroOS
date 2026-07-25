#!/usr/bin/env python3
"""Evaluate the checked-in WP-10 branch-coverage ratchet locally."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "process" / "coverage-scope-v1.json"
MANIFEST_VERSION = "pheroos-coverage-scope-v1"
COVERAGE_VERSION = "7.15.2"
MEASUREMENT_SHARDS = (
    "foundation",
    "governance-1",
    "governance-2",
    "governance-3",
    "governance-distributed-totality",
    "governance-4",
    "trace-1",
    "trace-2",
    "conformance-1",
    "conformance-finality-reference",
    "conformance-finality-independent",
    "conformance-2",
    "conformance-runtime",
    "ecosystem",
    "policy",
)
LOCKED_SCOPE_SHA256 = (
    "sha256:12d11285ec24b08eb80bb3752ca792c6e3b574ab6c7262c699eb4f51358a3fca"
)


@dataclass(frozen=True)
class CoverageMetrics:
    """Exact coverage counters; ratios are compared without rounding."""

    covered_lines: int = 0
    total_lines: int = 0
    covered_branches: int = 0
    total_branches: int = 0

    def plus(self, other: CoverageMetrics) -> CoverageMetrics:
        return CoverageMetrics(
            covered_lines=self.covered_lines + other.covered_lines,
            total_lines=self.total_lines + other.total_lines,
            covered_branches=self.covered_branches + other.covered_branches,
            total_branches=self.total_branches + other.total_branches,
        )


@dataclass(frozen=True)
class FileCoverage:
    """Coverage facts needed by ratchet and changed-source gates."""

    metrics: CoverageMetrics
    executable_lines: frozenset[int]
    executed_lines: frozenset[int]
    branch_arcs: frozenset[tuple[int, int]]
    missing_branch_arcs: frozenset[tuple[int, int]]


def load_coverage_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load JSON while rejecting duplicate keys and non-finite constants."""

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("coverage scope manifest must be a JSON object")
    return value


def manifest_shape_failures(manifest: Mapping[str, Any]) -> list[str]:
    """Return fail-closed shape and immutable-scope failures."""

    failures = _root_failures(manifest)
    if failures:
        return failures
    failures.extend(_tool_failures(manifest["tooling"]))
    failures.extend(_scope_failures(manifest["scope"]))
    failures.extend(_threshold_failures(manifest["thresholds"]))
    baseline_failures = _baseline_failures(manifest["baselines"])
    failures.extend(baseline_failures)
    if not baseline_failures:
        failures.extend(_baseline_source_binding_failures(manifest))
    failures.extend(_critical_branch_failures(manifest["critical_branches"]))
    observed = locked_scope_sha256(manifest)
    if observed != LOCKED_SCOPE_SHA256:
        failures.append(
            f"immutable coverage scope drift: {observed} != {LOCKED_SCOPE_SHA256}"
        )
    return failures


def locked_scope_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash every field whose weakening could increase reported coverage."""

    payload = {
        "baselines": manifest.get("baselines"),
        "critical_branches": manifest.get("critical_branches"),
        "measurement": manifest.get("measurement"),
        "scope": manifest.get("scope"),
        "thresholds": manifest.get("thresholds"),
        "tooling": manifest.get("tooling"),
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def included_source_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash the exact included source paths and bytes in canonical order."""

    digest = sha256()
    for path in sorted(_included_source_paths(manifest)):
        encoded_path = path.encode("utf-8")
        content = (ROOT / path).read_bytes()
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def load_coverage_data(
    manifest: Mapping[str, Any],
    *,
    data_file: Path,
) -> dict[str, FileCoverage]:
    """Render coverage.py data to JSON and return normalized file facts."""

    try:
        import coverage
    except ImportError as exc:  # pragma: no cover - CI dependency failure
        raise RuntimeError(
            f"coverage=={COVERAGE_VERSION} is required by the coverage gate"
        ) from exc
    if coverage.__version__ != COVERAGE_VERSION:
        raise RuntimeError(
            f"coverage version drift: {coverage.__version__} != {COVERAGE_VERSION}"
        )
    if not data_file.is_file():
        raise ValueError(f"coverage data file is missing: {data_file}")
    with TemporaryDirectory(prefix="pheroos-coverage-") as directory:
        output = Path(directory) / "coverage.json"
        cov = coverage.Coverage(
            data_file=str(data_file), branch=True, source=["pheroos"]
        )
        cov.set_option("run:relative_files", True)
        cov.load()
        cov.set_option(
            "report:exclude_lines",
            [item["regex"] for item in manifest["scope"]["line_exclusions"]],
        )
        cov.set_option("report:partial_branches", [])
        try:
            cov.json_report(
                outfile=str(output),
                omit=[item["path"] for item in manifest["scope"]["file_exclusions"]],
                pretty_print=False,
            )
        except coverage.exceptions.CoverageException as exc:
            raise ValueError(f"coverage data cannot be reported: {exc}") from exc
        document = json.loads(output.read_text(encoding="utf-8"))
    return _normalize_coverage_document(document)


def coverage_gate_failures(
    manifest: Mapping[str, Any],
    files: Mapping[str, FileCoverage],
    *,
    changed_lines: Mapping[str, frozenset[int]],
) -> list[str]:
    """Evaluate repository, authority, critical, and changed-source gates."""

    failures = _scope_presence_failures(manifest, files)
    failures.extend(_ratchet_failures(manifest, files))
    failures.extend(_critical_coverage_failures(manifest, files))
    failures.extend(_changed_coverage_failures(manifest, files, changed_lines))
    return failures


def declared_baseline_regressions(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> list[str]:
    """Reject lowering either checked baseline ratio from the base revision."""

    failures: list[str] = []
    for name in ("repository", "stable_authority"):
        failures.extend(
            _ratio_regressions(
                f"{name} declared baseline",
                _baseline_metrics(current["baselines"][name]),
                _baseline_metrics(previous["baselines"][name]),
            )
        )
    return failures


def discover_changed_lines(
    base_ref: str,
    *,
    include_worktree: bool,
) -> dict[str, frozenset[int]]:
    """Return added Python line numbers since one exact local Git base."""

    if not base_ref or set(base_ref) == {"0"}:
        raise ValueError("a non-zero coverage base ref is required")
    base_commit = _resolve_commit(base_ref)
    merged = _merge_changed_lines({}, _verified_git_changed_lines(base_commit, "HEAD"))
    if include_worktree:
        merged = _merge_changed_lines(
            merged,
            _verified_git_changed_lines("HEAD", None),
        )
        merged = _merge_changed_lines(merged, _untracked_changed_lines())
    return {path: frozenset(lines) for path, lines in merged.items()}


def resolve_ci_base_ref(pr_base: str | None, push_before: str | None) -> str:
    """Select one non-zero CI base without embedding shell control flow."""

    for candidate in (pr_base, push_before):
        if candidate and set(candidate) != {"0"}:
            return candidate
    return "HEAD^"


def _normalize_coverage_document(
    document: Mapping[str, Any],
) -> dict[str, FileCoverage]:
    meta = _mapping(document.get("meta"), "coverage metadata")
    if meta.get("branch_coverage") is not True:
        raise ValueError("coverage data was not measured with branch coverage")
    raw_files = document.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("coverage JSON has no files object")
    normalized: dict[str, FileCoverage] = {}
    for raw_path, raw in raw_files.items():
        if not isinstance(raw_path, str) or not isinstance(raw, dict):
            raise ValueError("coverage JSON file entry is malformed")
        path = _relative_source_path(raw_path)
        if path in normalized:
            raise ValueError(
                f"coverage source path is duplicated after normalization: {path}"
            )
        summary = _mapping(raw.get("summary"), f"coverage summary for {path}")
        executed = _integer_set(raw.get("executed_lines"), f"executed lines {path}")
        missing = _integer_set(raw.get("missing_lines"), f"missing lines {path}")
        executed_arcs = _arc_set(raw.get("executed_branches"), path)
        missing_arcs = _arc_set(raw.get("missing_branches"), path)
        normalized[path] = FileCoverage(
            metrics=CoverageMetrics(
                covered_lines=_integer(summary.get("covered_lines"), "covered_lines"),
                total_lines=_integer(summary.get("num_statements"), "num_statements"),
                covered_branches=_integer(
                    summary.get("covered_branches"), "covered_branches"
                ),
                total_branches=_integer(summary.get("num_branches"), "num_branches"),
            ),
            executable_lines=frozenset(executed | missing),
            executed_lines=frozenset(executed),
            branch_arcs=frozenset(executed_arcs | missing_arcs),
            missing_branch_arcs=frozenset(missing_arcs),
        )
    return normalized


def _root_failures(manifest: Mapping[str, Any]) -> list[str]:
    expected = {
        "baselines",
        "critical_branches",
        "manifest_version",
        "measurement",
        "scope",
        "thresholds",
        "tooling",
    }
    if set(manifest) != expected:
        return ["coverage manifest root fields must be exact"]
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return [f"coverage manifest_version must be {MANIFEST_VERSION}"]
    return _measurement_failures(manifest["measurement"])


def _measurement_failures(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != {
        "branch",
        "combine_command",
        "command",
        "process_coverage",
        "pytest_python_files",
        "shards",
        "source",
    }:
        return ["coverage measurement declaration must be exact"]
    if value["branch"] is not True or value["source"] != ["pheroos"]:
        return ["coverage measurement must use branch=True and source=pheroos"]
    if (
        value["command"]
        != "python -m coverage run --rcfile=@generated --branch --source=pheroos -m pytest -q @shard"
    ):
        return ["coverage measurement command is invalid"]
    if (
        value["combine_command"]
        != "CoverageData.update(map_path=repo_relative) @shard-data"
    ):
        return ["coverage combine command is invalid"]
    if value["process_coverage"] != {
        "parallel": True,
        "patch": ["subprocess"],
        "relative_files": True,
    }:
        return ["coverage subprocess measurement policy is invalid"]
    failures = _pytest_collection_policy_failures(value["pytest_python_files"])
    failures.extend(_measurement_shard_failures(value["shards"]))
    return failures


def _pytest_collection_policy_failures(value: object) -> list[str]:
    expected = ["test_*.py"]
    if value != expected:
        return ["coverage pytest python_files declaration must be exact"]
    try:
        document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"coverage pytest configuration cannot be read: {exc}"]
    configured = (
        document.get("tool", {})
        .get("pytest", {})
        .get("ini_options", {})
        .get("python_files")
    )
    if configured != expected:
        return ["pyproject pytest python_files must be exactly test_*.py"]
    return []


def _measurement_shard_failures(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["coverage measurement shards must be a list"]
    failures: list[str] = []
    names: list[str] = []
    test_files_by_shard: dict[str, set[str]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "pytest_targets"}:
            failures.append("coverage measurement shard entry must be exact")
            continue
        name = item.get("name")
        targets = item.get("pytest_targets")
        if not isinstance(name, str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", name
        ):
            failures.append("coverage measurement shard name is invalid")
            continue
        names.append(name)
        if not _string_list(targets):
            failures.append(f"coverage shard {name} targets must be nonempty strings")
            continue
        assert isinstance(targets, list)
        if len(targets) != len(set(targets)):
            failures.append(f"coverage shard {name} has duplicate targets")
        invalid = [target for target in targets if not _is_exact_test_file(target)]
        failures.extend(
            f"coverage shard {name} target is not an exact test file: {target}"
            for target in invalid
        )
        missing = [target for target in targets if not (ROOT / target).exists()]
        failures.extend(
            f"coverage shard {name} target is missing: {target}" for target in missing
        )
        test_files_by_shard[name] = _expanded_test_targets(targets)
    if tuple(names) != MEASUREMENT_SHARDS:
        failures.append("coverage measurement shard inventory/order is invalid")
    failures.extend(_overlapping_shard_failures(test_files_by_shard))
    failures.extend(_test_inventory_failures(test_files_by_shard))
    return failures


def _is_exact_test_file(target: str) -> bool:
    path = Path(target)
    return (
        target.startswith("tests/")
        and ".." not in path.parts
        and path.name.startswith("test_")
        and path.suffix == ".py"
        and (ROOT / path).is_file()
    )


def _expanded_test_targets(targets: Sequence[str]) -> set[str]:
    expanded: set[str] = set()
    for target in targets:
        path = ROOT / target
        if path.is_file() and path.name.startswith("test_") and path.suffix == ".py":
            expanded.add(target)
        elif path.is_dir():
            expanded.update(
                item.relative_to(ROOT).as_posix() for item in path.rglob("test_*.py")
            )
    return expanded


def _overlapping_shard_failures(
    test_files_by_shard: Mapping[str, set[str]],
) -> list[str]:
    owners: dict[str, str] = {}
    failures: list[str] = []
    for shard, paths in test_files_by_shard.items():
        for path in sorted(paths):
            prior = owners.setdefault(path, shard)
            if prior != shard:
                failures.append(
                    f"coverage test appears in multiple shards: {path} ({prior}, {shard})"
                )
    return failures


def _test_inventory_failures(
    test_files_by_shard: Mapping[str, set[str]],
) -> list[str]:
    expected = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").rglob("test_*.py")
    }
    observed = {path for paths in test_files_by_shard.values() for path in paths}
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    failures = [f"coverage test is unsharded: {path}" for path in missing]
    failures.extend(f"non-test path is in coverage shards: {path}" for path in extra)
    alternate = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").rglob("*_test.py")
        if not path.name.startswith("test_")
    )
    failures.extend(
        f"pytest alternate test filename is forbidden by the locked inventory: {path}"
        for path in alternate
    )
    return failures


def _tool_failures(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != {
        "branch_coverage",
        "ci_only",
        "name",
        "runtime_dependencies_empty",
        "version",
    }:
        return ["coverage tooling declaration must be exact"]
    expected = {
        "branch_coverage": True,
        "ci_only": True,
        "name": "coverage",
        "runtime_dependencies_empty": True,
        "version": COVERAGE_VERSION,
    }
    return [] if value == expected else ["coverage tooling policy is invalid"]


def _scope_failures(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != {
        "denominator",
        "file_exclusions",
        "groups",
        "line_exclusions",
    }:
        return ["coverage scope declaration must be exact"]
    denominator_failures = _denominator_failures(value["denominator"])
    file_failures = _file_exclusion_failures(value["file_exclusions"])
    line_failures = _line_exclusion_failures(value["line_exclusions"])
    failures = denominator_failures + file_failures
    failures.extend(line_failures)
    if not denominator_failures and not file_failures and not line_failures:
        failures.extend(_line_exclusion_source_failures(value))
    failures.extend(_group_failures(value["groups"]))
    return failures


def _denominator_failures(value: object) -> list[str]:
    expected = {
        "include": ["pheroos/*.py", "pheroos/**/*.py"],
        "included": True,
    }
    return [] if value == expected else ["coverage denominator must include all Python"]


def _file_exclusion_failures(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["coverage file_exclusions must be a list"]
    allowed = {"pheroos/governance/_public_api.py": "generated_facade"}
    observed: dict[str, str] = {}
    failures: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "category",
            "generator",
            "path",
            "sha256",
        }:
            failures.append("coverage file exclusion entry must be exact")
            continue
        path = item.get("path")
        category = item.get("category")
        generator = item.get("generator")
        digest = item.get("sha256")
        if not all(
            isinstance(part, str) and part for part in (path, category, generator)
        ):
            failures.append("coverage file exclusion values must be nonblank strings")
            continue
        assert isinstance(path, str)
        assert isinstance(category, str)
        observed[path] = category
        if generator != "scripts/generate_governance_public_api.py":
            failures.append(f"coverage exclusion {path} has an invalid generator")
        if not isinstance(digest, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", digest
        ):
            failures.append(f"coverage exclusion {path} has an invalid source digest")
        elif path in allowed:
            failures.extend(_generated_declaration_failures(path, digest))
    if observed != allowed:
        failures.append("only the declarative generated Governance API may be omitted")
    return failures


def _generated_declaration_failures(path: str, expected_digest: str) -> list[str]:
    source_path = ROOT / path
    if not source_path.is_file():
        return [f"coverage excluded declaration is missing: {path}"]
    content = source_path.read_bytes()
    observed_digest = "sha256:" + sha256(content).hexdigest()
    if observed_digest != expected_digest:
        return [f"coverage excluded declaration source drifted: {path}"]
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return [f"coverage excluded declaration cannot be parsed: {path}"]
    if not _is_static_public_api_declaration(tree):
        return [f"coverage excluded declaration contains runtime behavior: {path}"]
    return []


def _is_static_public_api_declaration(tree: ast.Module) -> bool:
    if len(tree.body) != 6:
        return False
    docstring, imported, *raw_assignments = tree.body
    if not (
        isinstance(docstring, ast.Expr)
        and isinstance(docstring.value, ast.Constant)
        and isinstance(docstring.value.value, str)
        and isinstance(imported, ast.ImportFrom)
        and imported.module == "types"
        and imported.level == 0
        and len(imported.names) == 1
        and imported.names[0].name == "MappingProxyType"
        and imported.names[0].asname is None
        and all(isinstance(item, ast.Assign) for item in raw_assignments)
    ):
        return False
    assignments = {
        item.targets[0].id: item.value
        for item in raw_assignments
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
    }
    if set(assignments) != {
        "COMPATIBILITY_MODULES",
        "PUBLIC_API",
        "PUBLIC_API_ORDER_SHA256",
        "__all__",
    }:
        return False
    order_hash = assignments["PUBLIC_API_ORDER_SHA256"]
    exports = assignments["PUBLIC_API"]
    modules = assignments["COMPATIBILITY_MODULES"]
    public_names = assignments["__all__"]
    return (
        isinstance(order_hash, ast.Constant)
        and isinstance(order_hash.value, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", order_hash.value))
        and _is_mapping_proxy_literal(exports, tuple_values=True)
        and _is_mapping_proxy_literal(modules, tuple_values=False)
        and isinstance(public_names, ast.List)
        and [
            item.value
            for item in public_names.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
        == ["COMPATIBILITY_MODULES", "PUBLIC_API", "PUBLIC_API_ORDER_SHA256"]
        and len(public_names.elts) == 3
    )


def _is_mapping_proxy_literal(node: ast.expr, *, tuple_values: bool) -> bool:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MappingProxyType"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Dict)
    ):
        return False
    mapping = node.args[0]
    keys = [
        item.value
        for item in mapping.keys
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    ]
    if len(keys) != len(mapping.keys) or len(keys) != len(set(keys)):
        return False
    if tuple_values:
        return all(
            isinstance(item, ast.Tuple)
            and len(item.elts) == 2
            and all(
                isinstance(part, ast.Constant) and isinstance(part.value, str)
                for part in item.elts
            )
            for item in mapping.values
        )
    return all(
        isinstance(item, ast.Constant) and isinstance(item.value, str)
        for item in mapping.values
    )


def _line_exclusion_failures(value: object) -> list[str]:
    expected = [
        {
            "ast_policy": "top_level_unshadowed_typing_type_checking",
            "id": "type_checking",
            "regex": "^if TYPE_CHECKING:",
        }
    ]
    return (
        [] if value == expected else ["coverage line exclusions are not the allowlist"]
    )


def _line_exclusion_source_failures(scope: Mapping[str, Any]) -> list[str]:
    manifest = {"scope": scope}
    failures: list[str] = []
    for path in sorted(_included_source_paths(manifest)):
        source = (ROOT / path).read_text(encoding="utf-8")
        failures.extend(_inline_no_cover_failures(path, source))
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            failures.append(
                f"coverage exclusion source cannot be parsed: {path}:{exc.lineno}"
            )
            continue
        failures.extend(_type_checking_guard_failures(path, source, tree))
    return failures


def _inline_no_cover_failures(path: str, source: str) -> list[str]:
    return [
        f"inline no-cover exclusion is forbidden: {path}:{line_number}"
        for line_number, line in enumerate(source.splitlines(), start=1)
        if re.search(
            r"#\s*pragma(?:[:\s])?\s*no\s*cover\b",
            line,
            flags=re.IGNORECASE,
        )
    ]


def _type_checking_guard_failures(
    path: str,
    source: str,
    tree: ast.Module,
) -> list[str]:
    candidates = {
        line_number
        for line_number, line in enumerate(source.splitlines(), start=1)
        if re.match(r"^if TYPE_CHECKING:", line)
    }
    if not candidates:
        return []
    guards = {
        node.lineno: node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
        and isinstance(node.test.ctx, ast.Load)
    }
    failures: list[str] = []
    if candidates != set(guards):
        failures.append(
            f"TYPE_CHECKING exclusion is not an exact top-level guard: {path}"
        )
        return failures
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "typing"
        and any(
            alias.name == "TYPE_CHECKING" and alias.asname is None
            for alias in node.names
        )
    ]
    if not imports or any(
        not any(item.lineno < line for item in imports) for line in candidates
    ):
        failures.append(
            f"TYPE_CHECKING guard requires a prior direct typing.TYPE_CHECKING import: {path}"
        )
    if _has_forbidden_name_binding(
        tree, "TYPE_CHECKING", allow_type_checking_import=True
    ):
        failures.append(f"TYPE_CHECKING binding is reassigned or shadowed: {path}")
    return failures


def _has_forbidden_name_binding(
    tree: ast.Module,
    name: str,
    *,
    allow_type_checking_import: bool = False,
) -> bool:
    return any(
        _node_has_forbidden_name_binding(
            tree,
            node,
            name,
            allow_type_checking_import=allow_type_checking_import,
        )
        for node in ast.walk(tree)
    )


def _node_has_forbidden_name_binding(
    tree: ast.Module,
    node: ast.AST,
    name: str,
    *,
    allow_type_checking_import: bool,
) -> bool:
    if isinstance(node, ast.Name) and node.id == name:
        return isinstance(node.ctx, ast.Store) or (
            isinstance(node.ctx, ast.Del)
            and not _allowed_post_guard_delete(tree, node, name)
        )
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.arg):
        return node.arg == name
    if isinstance(node, ast.ExceptHandler):
        return node.name == name
    if isinstance(node, (ast.MatchAs, ast.MatchStar)):
        return node.name == name
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _import_has_forbidden_name_binding(
            tree,
            node,
            name,
            allow_type_checking_import=allow_type_checking_import,
        )
    return False


def _import_has_forbidden_name_binding(
    tree: ast.Module,
    node: ast.Import | ast.ImportFrom,
    name: str,
    *,
    allow_type_checking_import: bool,
) -> bool:
    for alias in node.names:
        bound = alias.asname or alias.name.split(".", 1)[0]
        if bound != name:
            continue
        allowed = (
            allow_type_checking_import
            and isinstance(node, ast.ImportFrom)
            and node in tree.body
            and node.module == "typing"
            and alias.name == "TYPE_CHECKING"
            and alias.asname is None
        )
        if not allowed:
            return True
    return False


def _allowed_post_guard_delete(
    tree: ast.Module,
    target: ast.Name,
    name: str,
) -> bool:
    guards = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == name
    ]
    return any(
        isinstance(node, ast.Delete)
        and node in tree.body
        and len(node.targets) == 1
        and node.targets[0] is target
        and bool(guards)
        and node.lineno > max(guards)
        for node in tree.body
    )


def _group_failures(value: object) -> list[str]:
    required = {
        "authority_validator": True,
        "compatibility_facade": True,
        "generated_facade": False,
        "schema_declaration": True,
        "stable_owner": True,
        "tck_fixture": True,
    }
    if not isinstance(value, list):
        return ["coverage groups must be a list"]
    observed: dict[str, bool] = {}
    failures: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"included", "name", "patterns"}:
            failures.append("coverage group entry must be exact")
            continue
        name = item.get("name")
        included = item.get("included")
        patterns = item.get("patterns")
        if not isinstance(name, str) or type(included) is not bool:
            failures.append("coverage group name/included is invalid")
        elif not _string_list(patterns):
            failures.append(f"coverage group {name} patterns must be nonempty strings")
        else:
            observed[name] = included
    if observed != required:
        failures.append(
            "coverage groups must classify every required denominator family"
        )
    return failures


def _threshold_failures(value: object) -> list[str]:
    expected = {
        "authority_changed_branches_percent": 95,
        "authority_changed_lines_percent": 100,
        "final_repository_branch_percent": 85,
        "final_repository_line_percent": 90,
        "final_stable_authority_branch_percent": 95,
        "final_stable_authority_line_percent": 97,
        "ordinary_changed_lines_percent": 95,
    }
    return [] if value == expected else ["coverage thresholds must match WP-10 policy"]


def _baseline_failures(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"repository", "stable_authority"}:
        return ["coverage baselines must have both ratchet scopes"]
    failures: list[str] = []
    for name in ("repository", "stable_authority"):
        item = value[name]
        if not isinstance(item, dict) or set(item) != {
            "covered_branches",
            "covered_lines",
            "measurement_base_commit",
            "measurement_source_sha256",
            "total_branches",
            "total_lines",
        }:
            failures.append(f"coverage baseline {name} must be exact")
            continue
        failures.extend(_counter_failures(item, name))
    return failures


def _counter_failures(item: Mapping[str, object], name: str) -> list[str]:
    failures: list[str] = []
    for key in ("covered_branches", "covered_lines", "total_branches", "total_lines"):
        value = item[key]
        if type(value) is not int or value < 0:
            failures.append(f"coverage baseline {name}.{key} must be nonnegative int")
    commit = item["measurement_base_commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        failures.append(f"coverage baseline {name} base commit must be full SHA")
    source_digest = item["measurement_source_sha256"]
    if not isinstance(source_digest, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", source_digest
    ):
        failures.append(f"coverage baseline {name} source digest is invalid")
    if failures:
        return failures
    covered_lines = _integer(item["covered_lines"], "covered_lines")
    total_lines = _integer(item["total_lines"], "total_lines")
    covered_branches = _integer(item["covered_branches"], "covered_branches")
    total_branches = _integer(item["total_branches"], "total_branches")
    if covered_lines > total_lines:
        failures.append(f"coverage baseline {name} line counters are impossible")
    if covered_branches > total_branches:
        failures.append(f"coverage baseline {name} branch counters are impossible")
    return failures


def _baseline_source_binding_failures(manifest: Mapping[str, Any]) -> list[str]:
    repository = manifest["baselines"]["repository"]
    authority = manifest["baselines"]["stable_authority"]
    failures: list[str] = []
    if repository["measurement_base_commit"] != authority["measurement_base_commit"]:
        failures.append("coverage baselines must share one measurement base commit")
    if (
        repository["measurement_source_sha256"]
        != authority["measurement_source_sha256"]
    ):
        failures.append("coverage baselines must share one measurement source digest")
    expected = included_source_sha256(manifest)
    if repository["measurement_source_sha256"] != expected:
        failures.append(
            "coverage baseline source digest does not match included source: "
            f"{repository['measurement_source_sha256']} != {expected}"
        )
    return failures


def _critical_branch_failures(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["critical_branches must be a nonempty list"]
    failures: list[str] = []
    names: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "line",
            "name",
            "path",
            "source",
        }:
            failures.append("critical branch entry must be exact")
            continue
        name, path, line = item.get("name"), item.get("path"), item.get("line")
        if not isinstance(name, str) or not name or name in names:
            failures.append("critical branch names must be unique and nonblank")
        if not isinstance(path, str) or not path.startswith("pheroos/"):
            failures.append(f"critical branch {name} path is invalid")
        if type(line) is not int or line < 1:
            failures.append(f"critical branch {name} line is invalid")
        if (
            isinstance(name, str)
            and name
            and isinstance(path, str)
            and path.startswith("pheroos/")
            and type(line) is int
            and line >= 1
        ):
            failures.extend(
                _critical_source_anchor_failures(name, path, line, item["source"])
            )
        if isinstance(name, str):
            names.add(name)
    return failures


def _critical_source_anchor_failures(
    name: str,
    path: str,
    line: int,
    value: object,
) -> list[str]:
    expected = {"ast_kind", "end_line", "original", "sha256", "start_line"}
    if not isinstance(value, dict) or set(value) != expected:
        return [f"critical branch {name} source anchor must be exact"]
    start = value.get("start_line")
    end = value.get("end_line")
    original = value.get("original")
    digest = value.get("sha256")
    if (
        value.get("ast_kind") != "If"
        or type(start) is not int
        or type(end) is not int
        or start != line
        or end < start
        or not isinstance(original, str)
        or not original.endswith("\n")
        or not isinstance(digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    ):
        return [f"critical branch {name} source anchor values are invalid"]
    source_path = ROOT / path
    if not source_path.is_file():
        return [f"critical branch {name} source path is missing"]
    text = source_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    span = "".join(lines[start - 1 : end])
    if span != original or _text_sha256(span) != digest:
        return [f"critical branch {name} exact source span drifted"]
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return [f"critical branch {name} source cannot be parsed"]
    anchors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and node.lineno == start
        and node.test.end_lineno == end
    ]
    if len(anchors) != 1:
        return [f"critical branch {name} AST anchor drifted"]
    return []


def _text_sha256(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _scope_presence_failures(
    manifest: Mapping[str, Any], files: Mapping[str, FileCoverage]
) -> list[str]:
    expected = _included_source_paths(manifest)
    observed = set(files)
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    failures = [f"coverage source missing from data: {path}" for path in missing]
    failures.extend(
        f"coverage data contains out-of-scope source: {path}" for path in extra
    )
    return failures


def _ratchet_failures(
    manifest: Mapping[str, Any], files: Mapping[str, FileCoverage]
) -> list[str]:
    repository = _metrics_for_paths(files, _included_source_paths(manifest))
    stable_authority = _metrics_for_paths(
        files,
        _group_paths(manifest, "stable_owner")
        | _group_paths(manifest, "authority_validator"),
    )
    observations = {"repository": repository, "stable_authority": stable_authority}
    failures: list[str] = []
    for name, observed in observations.items():
        baseline = _baseline_metrics(manifest["baselines"][name])
        failures.extend(_ratio_regressions(name, observed, baseline))
    failures.extend(_final_target_failures(manifest, observations))
    return failures


def _final_target_failures(
    manifest: Mapping[str, Any],
    observations: Mapping[str, CoverageMetrics],
) -> list[str]:
    thresholds = manifest["thresholds"]
    repository = observations["repository"]
    authority = observations["stable_authority"]
    checks = (
        (
            "repository line coverage",
            repository.covered_lines,
            repository.total_lines,
            thresholds["final_repository_line_percent"],
        ),
        (
            "repository branch coverage",
            repository.covered_branches,
            repository.total_branches,
            thresholds["final_repository_branch_percent"],
        ),
        (
            "Stable/authority line coverage",
            authority.covered_lines,
            authority.total_lines,
            thresholds["final_stable_authority_line_percent"],
        ),
        (
            "Stable/authority branch coverage",
            authority.covered_branches,
            authority.total_branches,
            thresholds["final_stable_authority_branch_percent"],
        ),
    )
    failures: list[str] = []
    for name, covered, total, required in checks:
        failures.extend(
            _percent_failures(
                name,
                covered,
                total,
                required,
                empty_pass=False,
            )
        )
    return failures


def _critical_coverage_failures(
    manifest: Mapping[str, Any], files: Mapping[str, FileCoverage]
) -> list[str]:
    failures: list[str] = []
    for item in manifest["critical_branches"]:
        path, line, name = item["path"], item["line"], item["name"]
        coverage = files.get(path)
        if coverage is None:
            failures.append(f"critical branch {name} file is absent")
            continue
        arcs = {arc for arc in coverage.branch_arcs if arc[0] == line}
        missing = {arc for arc in coverage.missing_branch_arcs if arc[0] == line}
        if not arcs:
            failures.append(
                f"critical branch {name} has no branch arcs at {path}:{line}"
            )
        elif missing:
            failures.append(
                f"critical branch {name} is not fully covered: {sorted(missing)}"
            )
    return failures


def _changed_coverage_failures(
    manifest: Mapping[str, Any],
    files: Mapping[str, FileCoverage],
    changed_lines: Mapping[str, frozenset[int]],
) -> list[str]:
    authority_paths = _group_paths(manifest, "stable_owner") | _group_paths(
        manifest, "authority_validator"
    )
    included = _included_source_paths(manifest)
    authority = _changed_counts(files, changed_lines, authority_paths)
    ordinary = _changed_counts(files, changed_lines, included - authority_paths)
    thresholds = manifest["thresholds"]
    failures = _percent_failures(
        "changed authority lines",
        authority[0],
        authority[1],
        thresholds["authority_changed_lines_percent"],
    )
    failures.extend(
        _percent_failures(
            "changed authority branches",
            authority[2],
            authority[3],
            thresholds["authority_changed_branches_percent"],
        )
    )
    failures.extend(
        _percent_failures(
            "changed ordinary lines",
            ordinary[0],
            ordinary[1],
            thresholds["ordinary_changed_lines_percent"],
        )
    )
    return failures


def _changed_counts(
    files: Mapping[str, FileCoverage],
    changed: Mapping[str, frozenset[int]],
    selected_paths: set[str],
) -> tuple[int, int, int, int]:
    line_covered = line_total = branch_covered = branch_total = 0
    for path in selected_paths & set(changed) & set(files):
        coverage = files[path]
        lines = _canonical_changed_lines(path, changed[path])
        executable = lines & coverage.executable_lines
        line_total += len(executable)
        line_covered += len(executable & coverage.executed_lines)
        arcs = {arc for arc in coverage.branch_arcs if arc[0] in lines}
        branch_total += len(arcs)
        branch_covered += len(arcs - coverage.missing_branch_arcs)
    return line_covered, line_total, branch_covered, branch_total


def _canonical_changed_lines(path: str, lines: Iterable[int]) -> frozenset[int]:
    """Map physical diff lines to coverage.py's canonical statement lines."""

    try:
        import coverage
        from coverage.exceptions import CoverageException
        from coverage.parser import PythonParser
    except ImportError as exc:  # pragma: no cover - CI dependency failure
        raise RuntimeError(
            f"coverage=={COVERAGE_VERSION} is required by the coverage gate"
        ) from exc
    if coverage.__version__ != COVERAGE_VERSION:
        raise RuntimeError(
            f"coverage version drift: {coverage.__version__} != {COVERAGE_VERSION}"
        )
    try:
        parser = PythonParser(filename=str(ROOT / path))
        parser.parse_source()
    except CoverageException as exc:
        raise ValueError(f"changed source cannot be parsed: {path}: {exc}") from exc
    return frozenset(parser.first_lines(lines))


def _ratio_regressions(
    name: str, observed: CoverageMetrics, baseline: CoverageMetrics
) -> list[str]:
    failures: list[str] = []
    if not _ratio_at_least(
        observed.covered_lines,
        observed.total_lines,
        baseline.covered_lines,
        baseline.total_lines,
    ):
        failures.append(f"{name} line coverage regressed below locked baseline")
    if not _ratio_at_least(
        observed.covered_branches,
        observed.total_branches,
        baseline.covered_branches,
        baseline.total_branches,
    ):
        failures.append(f"{name} branch coverage regressed below locked baseline")
    return failures


def _percent_failures(
    name: str,
    covered: int,
    total: int,
    required: int,
    *,
    empty_pass: bool = True,
) -> list[str]:
    if total == 0:
        return [] if empty_pass else [f"{name} has an empty denominator"]
    if covered * 100 >= total * required:
        return []
    return [f"{name} is {covered}/{total}; requires at least {required}%"]


def _ratio_at_least(
    covered: int, total: int, baseline_covered: int, baseline_total: int
) -> bool:
    if total == 0 or baseline_total == 0:
        return total == baseline_total
    return covered * baseline_total >= baseline_covered * total


def _baseline_metrics(value: Mapping[str, Any]) -> CoverageMetrics:
    return CoverageMetrics(
        covered_lines=value["covered_lines"],
        total_lines=value["total_lines"],
        covered_branches=value["covered_branches"],
        total_branches=value["total_branches"],
    )


def _metrics_for_paths(
    files: Mapping[str, FileCoverage], paths: Iterable[str]
) -> CoverageMetrics:
    metrics = CoverageMetrics()
    for path in sorted(set(paths)):
        if path in files:
            metrics = metrics.plus(files[path].metrics)
    return metrics


def _included_source_paths(manifest: Mapping[str, Any]) -> set[str]:
    patterns = manifest["scope"]["denominator"]["include"]
    paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "pheroos").rglob("*.py")
        if _matches(path.relative_to(ROOT).as_posix(), patterns)
    }
    excluded = {item["path"] for item in manifest["scope"]["file_exclusions"]}
    return paths - excluded


def _group_paths(manifest: Mapping[str, Any], name: str) -> set[str]:
    group = next(item for item in manifest["scope"]["groups"] if item["name"] == name)
    all_paths = {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "pheroos").rglob("*.py")
    }
    return {path for path in all_paths if _matches(path, group["patterns"])}


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


@dataclass
class _PatchHunk:
    old_remaining: int
    new_remaining: int
    new_line: int

    @property
    def complete(self) -> bool:
        return self.old_remaining == 0 and self.new_remaining == 0


@dataclass
class _PatchState:
    current: str | None = None
    old_header: bool = False
    new_header: bool = False
    hunk: _PatchHunk | None = None
    seen: set[str] | None = None

    def seen_paths(self) -> set[str]:
        if self.seen is None:
            self.seen = set()
        return self.seen


def _parse_unified_zero_diff(
    text: str,
    *,
    path_statuses: Mapping[str, str] | None = None,
    expected_additions: Mapping[str, int] | None = None,
) -> dict[str, set[int]]:
    """Parse an exact Git ``--unified=0`` patch without trusting body text."""

    statuses = dict(path_statuses or _derive_patch_path_statuses(text))
    _validate_patch_inventory(statuses, expected_additions)
    changed: dict[str, set[int]] = {}
    observed_additions = {path: 0 for path in statuses}
    state = _PatchState()
    for line in text.splitlines():
        _consume_patch_line(line, state, statuses, changed, observed_additions)
    if state.hunk is not None and not state.hunk.complete:
        raise ValueError("truncated unified diff hunk")
    seen = state.seen_paths()
    if seen != set(statuses):
        missing = sorted(set(statuses) - seen)
        extra = sorted(seen - set(statuses))
        raise ValueError(
            f"unified diff path inventory mismatch: missing={missing}, extra={extra}"
        )
    _validate_patch_addition_counts(observed_additions, expected_additions)
    return changed


def _consume_patch_line(
    line: str,
    state: _PatchState,
    statuses: Mapping[str, str],
    changed: dict[str, set[int]],
    observed_additions: dict[str, int],
) -> None:
    if _consume_active_patch_hunk(line, state, changed, observed_additions):
        return
    state.hunk = None
    if line.startswith("diff --git "):
        state.current = _patch_header_path(line, statuses, state.seen_paths())
        state.seen_paths().add(state.current)
        state.old_header = state.new_header = False
        return
    if state.current is None:
        if line:
            raise ValueError(f"unframed unified diff content: {line}")
        return
    _consume_patch_section_line(line, state, statuses)


def _consume_active_patch_hunk(
    line: str,
    state: _PatchState,
    changed: dict[str, set[int]],
    observed_additions: dict[str, int],
) -> bool:
    hunk = state.hunk
    if hunk is None or hunk.complete:
        return False
    if line == "\\ No newline at end of file":
        return True
    _consume_patch_hunk_line(
        line,
        hunk,
        state.current,
        changed,
        observed_additions,
    )
    return True


def _consume_patch_section_line(
    line: str,
    state: _PatchState,
    statuses: Mapping[str, str],
) -> None:
    assert state.current is not None
    if line.startswith("--- "):
        _validate_old_patch_header(
            line,
            state.current,
            statuses[state.current],
            state.old_header,
            state.new_header,
        )
        state.old_header = True
    elif line.startswith("+++ "):
        _validate_new_patch_header(
            line,
            state.current,
            state.old_header,
            state.new_header,
        )
        state.new_header = True
    elif line.startswith("@@"):
        if not state.old_header or not state.new_header:
            raise ValueError(f"unframed unified diff hunk for {state.current}")
        state.hunk = _parse_patch_hunk_header(line)
    elif not _allowed_patch_metadata(line, state.current):
        raise ValueError(f"unexpected unified diff content for {state.current}: {line}")


def _derive_patch_path_statuses(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    pattern = re.compile(r"^diff --git a/(.+) b/(.+)$")
    for line in text.splitlines():
        match = pattern.fullmatch(line)
        if match is None:
            continue
        left, right = match.groups()
        if left != right or left in statuses:
            raise ValueError(f"ambiguous unified diff path header: {line}")
        statuses[left] = "M"
    return statuses


def _validate_patch_inventory(
    statuses: Mapping[str, str],
    expected_additions: Mapping[str, int] | None,
) -> None:
    if any(
        not path or path.startswith("/") or "\x00" in path or status not in {"A", "M"}
        for path, status in statuses.items()
    ):
        raise ValueError("Git raw path/status inventory is invalid")
    if expected_additions is not None and set(expected_additions) != set(statuses):
        raise ValueError("Git raw and numstat path inventories differ")


def _patch_header_path(
    line: str,
    statuses: Mapping[str, str],
    seen: set[str],
) -> str:
    matches = [path for path in statuses if line == f"diff --git a/{path} b/{path}"]
    if len(matches) != 1 or matches[0] in seen:
        raise ValueError(
            f"unified diff contains an undeclared or duplicate path: {line}"
        )
    return matches[0]


def _validate_old_patch_header(
    line: str,
    path: str,
    status: str,
    old_header: bool,
    new_header: bool,
) -> None:
    expected = "--- /dev/null" if status == "A" else f"--- a/{path}"
    if old_header or new_header or line != expected:
        raise ValueError(f"unified diff old path is invalid for {path}: {line}")


def _validate_new_patch_header(
    line: str,
    path: str,
    old_header: bool,
    new_header: bool,
) -> None:
    if not old_header or new_header or line != f"+++ b/{path}":
        raise ValueError(f"unified diff new path is invalid for {path}: {line}")


def _parse_patch_hunk_header(line: str) -> _PatchHunk:
    match = re.fullmatch(
        r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?",
        line,
    )
    if match is None:
        raise ValueError(f"malformed unified diff hunk: {line}")
    old_start, old_count, new_start, new_count = match.groups()
    del old_start
    return _PatchHunk(
        old_remaining=int(old_count or "1"),
        new_remaining=int(new_count or "1"),
        new_line=int(new_start),
    )


def _consume_patch_hunk_line(
    line: str,
    hunk: _PatchHunk,
    path: str | None,
    changed: dict[str, set[int]],
    observed_additions: dict[str, int],
) -> None:
    if path is None:
        raise ValueError("unframed unified diff hunk body")
    prefix = line[:1]
    if prefix == "+":
        if hunk.new_remaining < 1:
            raise ValueError(f"unified diff hunk has excess additions for {path}")
        if path.endswith(".py"):
            changed.setdefault(path, set()).add(hunk.new_line)
        observed_additions[path] += 1
        hunk.new_remaining -= 1
        hunk.new_line += 1
        return
    if prefix == "-":
        if hunk.old_remaining < 1:
            raise ValueError(f"unified diff hunk has excess deletions for {path}")
        hunk.old_remaining -= 1
        return
    if prefix == " ":
        if hunk.old_remaining < 1 or hunk.new_remaining < 1:
            raise ValueError(f"unified diff hunk has excess context for {path}")
        hunk.old_remaining -= 1
        hunk.new_remaining -= 1
        hunk.new_line += 1
        return
    raise ValueError(f"malformed unified diff hunk body for {path}: {line}")


def _allowed_patch_metadata(line: str, path: str) -> bool:
    if not line or line == "\\ No newline at end of file":
        return True
    prefixes = (
        "index ",
        "new file mode ",
        "old mode ",
        "new mode ",
        "deleted file mode ",
        "similarity index ",
        "dissimilarity index ",
    )
    if line.startswith(prefixes):
        return True
    return line == f"Binary files a/{path} and b/{path} differ"


def _validate_patch_addition_counts(
    observed: Mapping[str, int],
    expected: Mapping[str, int] | None,
) -> None:
    if expected is None:
        return
    mismatches = [
        f"{path}:{observed[path]}!={expected[path]}"
        for path in sorted(expected)
        if observed[path] != expected[path]
    ]
    if mismatches:
        raise ValueError(
            "unified diff/numstat addition mismatch: " + ", ".join(mismatches)
        )


def _git_diff(base: str, head: str | None) -> str:
    command = [
        "git",
        "-c",
        "core.quotePath=false",
        "diff",
        "--no-color",
        "--unified=0",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--diff-filter=AM",
        base,
    ]
    if head is not None:
        command.append(head)
    command.extend(["--", "pheroos"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git diff failed for {base}")
    return result.stdout


def _verified_git_changed_lines(base: str, head: str | None) -> dict[str, set[int]]:
    typechanged = sorted(_git_typechanged_python_paths(base, head))
    if typechanged:
        raise ValueError(
            "changed Python paths have unsupported Git type changes: "
            + ", ".join(typechanged)
        )
    statuses = _git_changed_path_statuses(base, head)
    additions = _git_changed_path_additions(base, head)
    return _parse_unified_zero_diff(
        _git_diff(base, head),
        path_statuses=statuses,
        expected_additions=additions,
    )


def _git_typechanged_python_paths(base: str, head: str | None) -> set[str]:
    command = [
        "git",
        "diff",
        "--name-only",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--diff-filter=T",
        base,
    ]
    if head is not None:
        command.append(head)
    command.extend(["--", "pheroos"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip()
        raise ValueError(detail or f"git type-change scan failed for {base}")
    return {
        path
        for raw_path in result.stdout.split(b"\0")
        if (path := os.fsdecode(raw_path)).endswith(".py")
    }


def _git_added_python_paths(base: str, head: str | None) -> set[str]:
    return {
        path
        for path, additions in _git_changed_path_additions(base, head).items()
        if path.endswith(".py") and additions > 0
    }


def _git_changed_path_statuses(base: str, head: str | None) -> dict[str, str]:
    command = [
        "git",
        "diff",
        "--raw",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--diff-filter=AM",
        base,
    ]
    if head is not None:
        command.append(head)
    command.extend(["--", "pheroos"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip()
        raise ValueError(detail or f"git raw diff failed for {base}")
    records = result.stdout.split(b"\0")
    if records and records[-1] == b"":
        records.pop()
    if len(records) % 2:
        raise ValueError("malformed NUL-delimited Git raw record")
    statuses: dict[str, str] = {}
    for index in range(0, len(records), 2):
        header, raw_path = records[index : index + 2]
        fields = header.split(b" ")
        if len(fields) != 5 or not fields[0].startswith(b":"):
            raise ValueError("malformed NUL-delimited Git raw header")
        status = os.fsdecode(fields[4])
        path = os.fsdecode(raw_path)
        if not re.fullmatch(r"[AM]", status) or not path or path in statuses:
            raise ValueError("invalid or duplicate Git raw path/status")
        statuses[path] = status
    return statuses


def _git_changed_path_additions(base: str, head: str | None) -> dict[str, int]:
    command = [
        "git",
        "diff",
        "--numstat",
        "-z",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--diff-filter=AM",
        base,
    ]
    if head is not None:
        command.append(head)
    command.extend(["--", "pheroos"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip()
        raise ValueError(detail or f"git numstat failed for {base}")
    additions_by_path: dict[str, int] = {}
    for raw_record in result.stdout.split(b"\0"):
        if not raw_record:
            continue
        fields = raw_record.split(b"\t", 2)
        if len(fields) != 3:
            raise ValueError("malformed NUL-delimited Git numstat record")
        additions, _, raw_path = fields
        path = os.fsdecode(raw_path)
        if additions == b"-":
            raise ValueError(f"changed path is binary and cannot be audited: {path}")
        try:
            added = int(additions)
        except ValueError as exc:
            raise ValueError(f"invalid Git numstat additions for {path}") from exc
        if added < 0 or not path or path in additions_by_path:
            raise ValueError(f"invalid or duplicate Git numstat path: {path}")
        additions_by_path[path] = added
    return additions_by_path


def _merge_changed_lines(
    left: Mapping[str, set[int]], right: Mapping[str, set[int]]
) -> dict[str, set[int]]:
    merged = {path: set(lines) for path, lines in left.items()}
    for path, lines in right.items():
        merged.setdefault(path, set()).update(lines)
    return merged


def _untracked_changed_lines() -> dict[str, set[int]]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            "pheroos",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip()
        raise ValueError(detail or "git untracked source scan failed")
    changed: dict[str, set[int]] = {}
    for raw_path in result.stdout.split(b"\0"):
        path = os.fsdecode(raw_path)
        if path.endswith(".py"):
            count = len((ROOT / path).read_text(encoding="utf-8").splitlines())
            changed[path] = set(range(1, count + 1))
    return changed


def _relative_source_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(ROOT).as_posix()
        except ValueError as exc:
            raise ValueError(f"coverage source is outside repository: {path}") from exc
    return candidate.as_posix()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _integer_set(value: object, label: str) -> set[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise ValueError(f"{label} must be an integer list")
    return set(value)


def _arc_set(value: object, path: str) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        raise ValueError(f"coverage branches for {path} must be a list")
    arcs: set[tuple[int, int]] = set()
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or any(type(part) is not int for part in item)
        ):
            raise ValueError(f"coverage branch for {path} is malformed")
        arcs.add((item[0], item[1]))
    return arcs


def _string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item) for item in value)
    )


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
    parser.add_argument("--data-file", type=Path, default=ROOT / ".coverage")
    parser.add_argument("--base-ref", default=os.environ.get("COVERAGE_BASE_REF"))
    parser.add_argument("--include-worktree", action="store_true")
    parser.add_argument("--skip-changed", action="store_true")
    parser.add_argument("--emit-ci-base", action="store_true")
    measurement = parser.add_mutually_exclusive_group()
    measurement.add_argument("--measure", action="store_true")
    measurement.add_argument("--measure-shard", choices=MEASUREMENT_SHARDS)
    measurement.add_argument("--combine-shards-dir", type=Path)
    parser.add_argument("--measure-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local gate and print deterministic counters."""

    args = _parser().parse_args(argv)
    if args.emit_ci_base:
        print(
            "COVERAGE_BASE_REF="
            + resolve_ci_base_ref(
                os.environ.get("PR_BASE_SHA"),
                os.environ.get("PUSH_BEFORE_SHA"),
            )
        )
        return 0
    try:
        manifest = _load_valid_manifest(args.manifest)
        _validate_measurement_options(args)
        files = _measure_and_load(args, manifest)
        if args.measure_only:
            return _report_measurement_only(args, manifest, files)
        changed = _changed_lines_for_options(args)
        failures = coverage_gate_failures(manifest, files, changed_lines=changed)
        failures.extend(
            _baseline_history_failures(manifest, args.base_ref, args.manifest)
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"coverage gate: FAIL: {exc}", file=sys.stderr)
        return 2
    return _report_gate(manifest, files, failures)


def _load_valid_manifest(path: Path) -> dict[str, Any]:
    manifest = load_coverage_manifest(path)
    failures = manifest_shape_failures(manifest)
    if failures:
        raise ValueError("invalid coverage manifest:\n" + "\n".join(failures))
    return manifest


def _validate_measurement_options(args: argparse.Namespace) -> None:
    if args.measure_only and args.measure_shard is None:
        raise ValueError("--measure-only requires --measure-shard")
    if args.measure_shard is not None and not args.measure_only:
        raise ValueError("--measure-shard requires --measure-only")


def _measure_and_load(
    args: argparse.Namespace, manifest: Mapping[str, Any]
) -> dict[str, FileCoverage]:
    if args.measure:
        _run_all_measurements(manifest, args.data_file)
    elif args.measure_shard is not None:
        _run_measurement(manifest, args.data_file, args.measure_shard)
    elif args.combine_shards_dir is not None:
        _combine_declared_shards(args.combine_shards_dir, args.data_file)
    return load_coverage_data(manifest, data_file=args.data_file)


def _report_measurement_only(
    args: argparse.Namespace,
    manifest: Mapping[str, Any],
    files: Mapping[str, FileCoverage],
) -> int:
    failures = _scope_presence_failures(manifest, files)
    if failures:
        for failure in failures:
            print(f"coverage gate: FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"coverage measurement shard {args.measure_shard}: PASS")
    return 0


def _changed_lines_for_options(
    args: argparse.Namespace,
) -> Mapping[str, frozenset[int]]:
    if args.skip_changed:
        return {}
    if not args.base_ref:
        raise ValueError("--base-ref is required unless --skip-changed is used")
    return discover_changed_lines(
        args.base_ref,
        include_worktree=args.include_worktree,
    )


def _baseline_history_failures(
    manifest: Mapping[str, Any], base_ref: str | None, manifest_path: Path
) -> list[str]:
    if not base_ref:
        return []
    previous = _coverage_manifest_at_ref(base_ref, manifest_path)
    if previous is None:
        return []
    return declared_baseline_regressions(manifest, previous)


def _coverage_manifest_at_ref(
    base_ref: str, manifest_path: Path
) -> Mapping[str, Any] | None:
    commit = _resolve_commit(base_ref)
    try:
        relative = manifest_path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("coverage manifest must be inside the repository") from exc
    listing = subprocess.run(
        ["git", "ls-tree", "-z", "--full-tree", commit, "--", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if listing.returncode != 0:
        detail = os.fsdecode(listing.stderr).strip()
        raise ValueError(detail or "base coverage manifest inventory failed")
    if not listing.stdout:
        return None
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "base coverage manifest read failed")
    value = json.loads(
        result.stdout,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError("base coverage scope manifest must be a JSON object")
    if value.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("base coverage scope manifest version is invalid")
    failures = _baseline_failures(value.get("baselines"))
    if failures:
        raise ValueError("base coverage baselines are invalid:\n" + "\n".join(failures))
    return value


def _resolve_commit(ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(result.stderr.strip() or f"invalid Git base ref: {ref}")
    return commit


def _report_gate(
    manifest: Mapping[str, Any],
    files: Mapping[str, FileCoverage],
    failures: Sequence[str],
) -> int:
    repository = _metrics_for_paths(files, _included_source_paths(manifest))
    authority = _metrics_for_paths(
        files,
        _group_paths(manifest, "stable_owner")
        | _group_paths(manifest, "authority_validator"),
    )
    print("coverage gate repository:", _format_metrics(repository))
    print("coverage gate stable_authority:", _format_metrics(authority))
    if failures:
        for failure in failures:
            print(f"coverage gate: FAIL: {failure}", file=sys.stderr)
        return 1
    print("coverage gate: PASS")
    return 0


def _format_metrics(metrics: CoverageMetrics) -> str:
    return (
        f"lines={metrics.covered_lines}/{metrics.total_lines} "
        f"branches={metrics.covered_branches}/{metrics.total_branches}"
    )


def _run_all_measurements(manifest: Mapping[str, Any], data_file: Path) -> None:
    data_file.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="pheroos-coverage-shards-", dir=data_file.parent
    ) as directory:
        shard_files: list[Path] = []
        for shard in MEASUREMENT_SHARDS:
            shard_file = Path(directory) / f".coverage.{shard}"
            _run_measurement(manifest, shard_file, shard)
            shard_files.append(shard_file)
        _combine_measurements(shard_files, data_file)


def _run_measurement(
    manifest: Mapping[str, Any], data_file: Path, shard_name: str
) -> None:
    targets = pytest_targets_for_shard(manifest, shard_name)
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file = data_file.resolve()
    _erase_measurement_files(data_file)
    env = dict(os.environ)
    env["COVERAGE_FILE"] = str(data_file)
    with TemporaryDirectory(prefix="pheroos-coverage-config-") as directory:
        config = Path(directory) / ".coveragerc"
        config.write_text(_measurement_config(data_file), encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--rcfile={config}",
            "--branch",
            "--source=pheroos",
            "-m",
            "pytest",
            "-q",
            *targets,
        ]
        measured = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    if measured.returncode != 0:
        tail = "\n".join((measured.stdout + measured.stderr).splitlines()[-40:])
        raise ValueError(f"coverage measurement tests failed:\n{tail}")
    fragments = sorted(data_file.parent.glob(data_file.name + ".*"))
    if not fragments:
        raise ValueError(f"coverage shard {shard_name} produced no process data")
    _combine_measurements(
        fragments,
        data_file,
        erase_output=False,
        keep=False,
    )
    _touch_denominator_source(manifest, data_file)
    summary = next(
        (line for line in reversed(measured.stdout.splitlines()) if line.strip()),
        "pytest completed without a summary line",
    )
    print(
        f"coverage measurement {shard_name}: {summary}; process-data={len(fragments)}"
    )


def _measurement_config(data_file: Path) -> str:
    return (
        "[run]\n"
        "branch = true\n"
        f"data_file = {data_file}\n"
        "parallel = true\n"
        "patch =\n"
        "    subprocess\n"
        "relative_files = true\n"
        "source =\n"
        "    pheroos\n"
    )


def _erase_measurement_files(data_file: Path) -> None:
    data_file.unlink(missing_ok=True)
    for fragment in data_file.parent.glob(data_file.name + ".*"):
        if fragment.is_file():
            fragment.unlink()


def _touch_denominator_source(manifest: Mapping[str, Any], data_file: Path) -> None:
    """Register every denominator file as zero-hit without importing it."""

    try:
        import coverage
    except ImportError as exc:  # pragma: no cover - CI dependency failure
        raise RuntimeError(
            f"coverage=={COVERAGE_VERSION} is required by the coverage gate"
        ) from exc
    data = coverage.CoverageData(basename=str(data_file))
    data.read()
    data.touch_files(sorted(_included_source_paths(manifest)))
    data.write()


def pytest_targets_for_shard(manifest: Mapping[str, Any], shard_name: str) -> list[str]:
    for shard in manifest["measurement"]["shards"]:
        if shard["name"] == shard_name:
            return list(shard["pytest_targets"])
    raise ValueError(f"unknown coverage measurement shard: {shard_name}")


def _declared_coverage_shard_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"coverage shard directory is missing: {directory}")
    expected_names = {f".coverage.{name}" for name in MEASUREMENT_SHARDS}
    observed_names = {
        item.name for item in directory.iterdir() if item.name.startswith(".coverage.")
    }
    missing = sorted(expected_names - observed_names)
    extra = sorted(observed_names - expected_names)
    if missing or extra:
        details = [f"missing={missing}" if missing else ""]
        details.append(f"unexpected={extra}" if extra else "")
        raise ValueError(
            "coverage shard artifact inventory is not exact: "
            + " ".join(item for item in details if item)
        )
    paths = [directory / f".coverage.{name}" for name in MEASUREMENT_SHARDS]
    invalid = [path.name for path in paths if not path.is_file() or path.is_symlink()]
    if invalid:
        raise ValueError(
            "coverage shard artifacts must be regular files: " + ", ".join(invalid)
        )
    return paths


def _combine_declared_shards(directory: Path, data_file: Path) -> None:
    _combine_measurements(
        _declared_coverage_shard_files(directory),
        data_file.resolve(),
    )


def _combine_measurements(
    shard_files: Sequence[Path],
    data_file: Path,
    *,
    erase_output: bool = True,
    keep: bool = True,
) -> None:
    try:
        import coverage
        from coverage.exceptions import CoverageException
    except ImportError as exc:  # pragma: no cover - CI dependency failure
        raise RuntimeError(
            f"coverage=={COVERAGE_VERSION} is required by the coverage gate"
        ) from exc
    if coverage.__version__ != COVERAGE_VERSION:
        raise RuntimeError(
            f"coverage version drift: {coverage.__version__} != {COVERAGE_VERSION}"
        )
    data_file = data_file.resolve()
    if not erase_output and data_file.exists():
        raise ValueError(f"coverage combine output already exists: {data_file}")
    data_file.unlink(missing_ok=True)
    temporary = data_file.with_name(data_file.name + ".combining")
    temporary.unlink(missing_ok=True)
    try:
        combined = coverage.CoverageData(basename=str(temporary))
        for shard_file in shard_files:
            _merge_coverage_shard(combined, shard_file)
        combined.write()
        os.replace(temporary, data_file)
    except CoverageException as exc:
        raise ValueError(f"coverage shard combine failed: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    if not keep:
        for shard_file in shard_files:
            shard_file.unlink(missing_ok=True)


def _merge_coverage_shard(combined: Any, shard_file: Path) -> None:
    import coverage

    shard_path = shard_file.resolve()
    if not shard_path.is_file():
        raise ValueError(f"coverage shard data is missing: {shard_file}")
    shard = coverage.CoverageData(basename=str(shard_path))
    shard.read()
    if not shard.has_arcs():
        raise ValueError(f"coverage shard lacks branch data: {shard_file}")
    for measured in shard.measured_files():
        _repo_relative_coverage_path(measured)
    combined.update(shard, map_path=_repo_relative_coverage_path)


def _repo_relative_coverage_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(ROOT)
        except ValueError as exc:
            raise ValueError(f"coverage source is outside repository: {path}") from exc
    if ".." in candidate.parts:
        raise ValueError(f"coverage source path escapes repository: {path}")
    normalized = candidate.as_posix()
    if not normalized.startswith("pheroos/") or not normalized.endswith(".py"):
        raise ValueError(f"coverage source is outside the Python denominator: {path}")
    return normalized


if __name__ == "__main__":  # pragma: no cover - unexecutable import guard
    raise SystemExit(main())
