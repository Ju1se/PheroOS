from __future__ import annotations

import ast
from dataclasses import MISSING, fields
import inspect
from pathlib import Path

import pheroos.conformance as conformance
import pheroos.conformance.commit_tck as facade
from pheroos.conformance._commit_tck import artifacts, models, mutations
from pheroos.conformance._commit_tck import reference_adapter, runner


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_PACKAGE = ROOT / "pheroos" / "conformance" / "_commit_tck"
PRIVATE_PREFIX = "pheroos.conformance._commit_tck."


def _private_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in sorted(PRIVATE_PACKAGE.glob("*.py")):
        name = path.stem
        graph[name] = set()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(PRIVATE_PREFIX):
                    graph[name].add(node.module.removeprefix(PRIVATE_PREFIX))
                assert node.module != "pheroos.conformance.commit_tck"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "pheroos.conformance.commit_tck"
                    if alias.name.startswith(PRIVATE_PREFIX):
                        graph[name].add(alias.name.removeprefix(PRIVATE_PREFIX))
    return graph


def test_private_commit_tck_modules_form_an_acyclic_dependency_graph() -> None:
    graph = _private_import_graph()

    assert set(graph) == {
        "__init__",
        "artifacts",
        "models",
        "mutations",
        "reference_adapter",
        "runner",
    }
    assert graph == {
        "__init__": set(),
        "artifacts": {"models", "mutations"},
        "models": set(),
        "mutations": {"models"},
        "reference_adapter": {"artifacts", "models"},
        "runner": {"artifacts", "models", "mutations", "reference_adapter"},
    }

    visited: set[str] = set()
    active: set[str] = set()

    def visit(module: str) -> None:
        assert module not in active, f"Commit TCK import cycle reaches {module}"
        if module in visited:
            return
        active.add(module)
        for dependency in graph[module]:
            visit(dependency)
        active.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)


def test_commit_tck_facade_preserves_type_identical_public_objects() -> None:
    assert conformance.CommitTckAdapter is facade.CommitTckAdapter
    assert conformance.CommitTckReport is facade.CommitTckReport
    assert conformance.CommitTckResult is facade.CommitTckResult
    assert conformance.CommitTckVector is facade.CommitTckVector
    assert conformance.ReferenceCommitTckAdapter is facade.ReferenceCommitTckAdapter

    assert facade.CommitTckAdapter is models.CommitTckAdapter
    assert facade.CommitTckReport is models.CommitTckReport
    assert facade.CommitTckResult is models.CommitTckResult
    assert facade.CommitTckVector is models.CommitTckVector
    assert facade.ReferenceCommitTckAdapter is (
        reference_adapter.ReferenceCommitTckAdapter
    )
    assert facade.commit_tck_artifact_root is artifacts.commit_tck_artifact_root
    assert facade.commit_tck_schema is artifacts.commit_tck_schema
    assert facade.load_commit_tck_vectors is artifacts.load_commit_tck_vectors
    assert facade.run_commit_tck is runner.run_commit_tck
    assert facade._request_from_vector is models.request_from_vector
    assert facade._variant_vector is mutations.variant_vector

    for name in facade.__all__:
        value = getattr(facade, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__module__ == "pheroos.conformance.commit_tck"


def test_commit_tck_facade_locks_signatures_fields_defaults_and_exports() -> None:
    assert facade.__all__ == [
        "COMMIT_TCK_ARTIFACT",
        "COMMIT_TCK_SCHEMA_ID",
        "COMMIT_TCK_VERSION",
        "CommitTckAdapter",
        "CommitTckReport",
        "CommitTckResult",
        "CommitTckVector",
        "ReferenceCommitTckAdapter",
        "commit_tck_artifact_root",
        "commit_tck_schema",
        "load_commit_tck_vectors",
        "run_commit_tck",
    ]
    assert str(inspect.signature(facade.run_commit_tck)) == (
        "(vectors: 'Sequence[CommitTckVector] | None' = None, *, "
        "adapter: 'CommitTckAdapter | None' = None) -> 'CommitTckReport'"
    )
    assert str(inspect.signature(facade.load_commit_tck_vectors)) == (
        "(path: 'str | Path | Any' = None) -> 'tuple[CommitTckVector, ...]'"
    )
    assert str(inspect.signature(facade.ReferenceCommitTckAdapter)) == "() -> 'None'"

    vector_fields = fields(facade.CommitTckVector)
    assert tuple(item.name for item in vector_fields) == (
        "id",
        "tck_version",
        "matrix_case",
        "title",
        "manifest",
        "profile",
        "prior_authoritative_state",
        "inputs",
        "expected",
        "mutations",
        "permutations",
    )
    assert all(item.default is MISSING for item in vector_fields[:-2])
    assert vector_fields[-2].default == ()
    assert vector_fields[-1].default == ()

    result_fields = fields(facade.CommitTckResult)
    assert tuple(item.name for item in result_fields) == (
        "vector_id",
        "matrix_case",
        "ok",
        "expected",
        "actual",
        "detail",
        "variant_failures",
    )
    assert result_fields[-2].default == ""
    assert result_fields[-1].default == ()


def test_commit_tck_facade_is_thin_and_contains_no_reference_semantics() -> None:
    path = ROOT / "pheroos" / "conformance" / "commit_tck.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    assert len(source.splitlines()) < 100
    definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert definitions <= {"__getattr__", "__dir__"}
    assert "pheroos.governance" not in source
    assert "_MATRIX_PROBES" not in source
