from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from importlib.util import resolve_name
import inspect
import json
import pickle
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType, SimpleNamespace
import typing

import pytest

import pheroos.trace as trace
from pheroos.trace import event, store, validation
from pheroos.trace._contracts.base import TraceEventContract


ROOT = Path(__file__).resolve().parents[2]


def _trace_module(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _trace_import_graph() -> tuple[dict[str, set[str]], list[str]]:
    paths = sorted((ROOT / "pheroos" / "trace").rglob("*.py"))
    modules = {_trace_module(path) for path in paths}
    graph: dict[str, set[str]] = {module: set() for module in modules}
    aggregate_imports: list[str] = []
    for path in paths:
        source = _trace_module(path)
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str]
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package = (
                        source
                        if path.name == "__init__.py"
                        else source.rpartition(".")[0]
                    )
                    imported_module = resolve_name(
                        "." * node.level + (node.module or ""),
                        package,
                    )
                else:
                    imported_module = node.module or ""
                imported = [imported_module]
                imported.extend(
                    f"{imported_module}.{alias.name}"
                    for alias in node.names
                    if imported_module
                )
            else:
                continue
            if path.name != "__init__.py" and "pheroos.trace" in imported:
                aggregate_imports.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            graph[source].update(module for module in imported if module in modules)
    return graph, aggregate_imports


def _cyclic_components(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    stacked: set[str] = set()
    cycles: list[tuple[str, ...]] = []
    for module in sorted(graph):
        if module not in indexes:
            _visit_component(
                module,
                graph=graph,
                indexes=indexes,
                lowlinks=lowlinks,
                stack=stack,
                stacked=stacked,
                cycles=cycles,
            )
    return cycles


def _visit_component(
    module: str,
    *,
    graph: dict[str, set[str]],
    indexes: dict[str, int],
    lowlinks: dict[str, int],
    stack: list[str],
    stacked: set[str],
    cycles: list[tuple[str, ...]],
) -> None:
    indexes[module] = len(indexes)
    lowlinks[module] = indexes[module]
    stack.append(module)
    stacked.add(module)
    for dependency in sorted(graph[module]):
        if dependency not in indexes:
            _visit_component(
                dependency,
                graph=graph,
                indexes=indexes,
                lowlinks=lowlinks,
                stack=stack,
                stacked=stacked,
                cycles=cycles,
            )
            lowlinks[module] = min(lowlinks[module], lowlinks[dependency])
        elif dependency in stacked:
            lowlinks[module] = min(lowlinks[module], indexes[dependency])
    if lowlinks[module] != indexes[module]:
        return
    component: list[str] = []
    while True:
        dependency = stack.pop()
        stacked.remove(dependency)
        component.append(dependency)
        if dependency == module:
            break
    if len(component) > 1 or module in graph[module]:
        cycles.append(tuple(sorted(component)))


def test_static_contracts_cover_every_builtin_exactly_once() -> None:
    contracts = validation.TRACE_EVENT_CONTRACTS
    event_types = tuple(contract.event_type for contract in contracts)

    assert isinstance(contracts, tuple)
    assert len(event_types) == len(set(event_types))
    assert frozenset(event_types) == trace.VALID_EVENT_TYPES
    assert isinstance(validation._TRACE_EVENT_CONTRACTS_BY_TYPE, MappingProxyType)
    assert set(validation._TRACE_EVENT_CONTRACTS_BY_TYPE) == set(event_types)
    assert all(isinstance(contract, TraceEventContract) for contract in contracts)
    assert all(callable(contract.validator) for contract in contracts)
    assert all(not hasattr(contract, "validators") for contract in contracts)
    assert {
        contract.event_type: contract.required_fields
        for contract in contracts
        if contract.schema_condition
    } == dict(trace.EVENT_LINEAGE_CONTRACTS)

    with pytest.raises(TypeError):
        validation._TRACE_EVENT_CONTRACTS_BY_TYPE["forged"] = contracts[0]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        contracts[0].event_type = "forged"  # type: ignore[misc]


def test_unknown_builtin_fails_closed_but_extension_lineage_stays_open() -> None:
    unknown = SimpleNamespace(
        event_type="authority_future",
        protocol_id="protocol:test",
        target="decision:test",
        reason="undeclared authority",
        lineage={},
    )
    with pytest.raises(ValueError, match="unsupported trace event type"):
        trace.validate_event_lineage(unknown)

    extension = trace.TraceEvent(
        event_type="ext.acme.observation",
        protocol_id="protocol:test",
        target="decision:test",
        reason="non-authoritative extension metadata",
        lineage={"provider_shape": {"any": ["json", 1]}},
    )
    extension.validate()


@pytest.mark.parametrize(
    ("event_type", "lineage", "mutated_leaf", "value", "message"),
    [
        (
            "scout_report",
            {
                "scout_id": "scout:a",
                "candidate_id": "candidate:a",
                "evidence_id": "evidence:a",
                "provenance": "driver:a",
                "support": 1.0,
                "source_trace_event_id": "trace:scout:a",
                "verification_trace_event_id": "trace:verify:a",
            },
            "support",
            True,
            "support",
        ),
        (
            "pheromone_deposit",
            {
                "source_id": "scout:a",
                "provenance": "driver:a",
                "subject_type": "candidate",
                "subject_id": "candidate:a",
                "candidate_id": "candidate:a",
                "kind": "positive",
                "source_kind": "positive",
                "source_strength": 0.0,
                "old_strength": 0.0,
                "requested_strength": 1.0,
                "applied_strength": 1.0,
                "new_strength": 1.0,
                "round_budget_remaining": 0.0,
                "source_budget_remaining": 0.0,
                "step": 1,
                "deposited_at_step": 1,
                "updated_at_step": 1,
                "source_trace_event_id": "trace:deposit:a",
                "trace_event_id": "trace:deposit:a",
            },
            "new_strength",
            2.0,
            "reconstruct",
        ),
        (
            "layer_proposal",
            {
                "layer_id": "learned",
                "source_id": "layer:a",
                "action": "support",
                "effect": "candidate_preference",
                "candidate_id": "candidate:a",
                "confidence": 0.8,
                "support": 1.0,
                "risk": 0.0,
                "proposed_strength": 0.0,
                "proposed_pheromone_kind": "",
                "subject_type": "candidate",
                "subject_id": "candidate:a",
                "evidence_id": "evidence:a",
                "provenance": "runtime:a",
                "source_trace_event_id": "trace:proposal:a",
            },
            "layer_id",
            "untrusted-runtime",
            "unsupported",
        ),
        (
            "output",
            {
                "committed_candidate": True,
                "evidence_provenance": True,
                "stop_resolution": True,
                "publication_permission": True,
                "authorized": True,
            },
            "publication_permission",
            False,
            "four declared output gates",
        ),
    ],
)
def test_authority_event_leaf_mutation_is_rejected(
    event_type: str,
    lineage: dict[str, object],
    mutated_leaf: str,
    value: object,
    message: str,
) -> None:
    trace.TraceEvent(
        event_type=event_type,
        protocol_id="protocol:test",
        target="decision:test",
        reason="valid control",
        lineage=lineage,
    ).validate()
    mutated = dict(lineage)
    mutated[mutated_leaf] = value

    with pytest.raises(ValueError, match=message):
        trace.TraceEvent(
            event_type=event_type,
            protocol_id="protocol:test",
            target="decision:test",
            reason="mutated authority leaf",
            lineage=mutated,
        ).validate()


def test_trace_schema_bytes_remain_v1_canonical() -> None:
    from pheroos.trace.schema import trace_schema

    generated = (json.dumps(trace_schema(), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    assert generated == (ROOT / "schemas" / "trace.schema.json").read_bytes()


def test_modular_facade_preserves_pickle_from_star_dir_and_signatures() -> None:
    assert trace.TraceEvent is event.TraceEvent
    assert trace.TraceRecord is store.TraceRecord
    assert trace.InMemoryTraceStore is store.InMemoryTraceStore
    assert trace.TraceEvent.__module__ == "pheroos.trace"
    assert trace.TraceRecord.__module__ == "pheroos.trace"
    assert trace.InMemoryTraceStore.__module__ == "pheroos.trace"
    assert trace.validate_event_lineage is validation.validate_event_lineage
    assert inspect.signature(trace.make_commit_trace_event) == inspect.signature(
        event.make_commit_trace_event
    )
    assert typing.get_type_hints(trace.TraceEvent)["lineage"] == dict[str, typing.Any]
    assert (
        typing.get_type_hints(trace.validate_event_lineage)["event"] is trace.TraceEvent
    )

    event_value = trace.TraceEvent("plan", "protocol:test", "decision:test", "plan")
    trace_store = trace.InMemoryTraceStore()
    trace_store.append(event_value)
    assert pickle.loads(pickle.dumps(trace.TraceEvent)) is trace.TraceEvent
    assert pickle.loads(pickle.dumps(event_value)) == event_value
    restored_store = pickle.loads(pickle.dumps(trace_store))
    assert restored_store.records == trace_store.records

    namespace: dict[str, object] = {}
    exec("from pheroos.trace import *", {}, namespace)
    assert set(namespace) == set(trace.__all__)
    assert all(getattr(trace, name) is namespace[name] for name in trace.__all__)
    assert set(trace.__all__).issubset(dir(trace))


def test_trace_import_boundary_is_static_and_runtime_clean() -> None:
    forbidden = {
        "pheroos.governance",
        "pheroos.kernel",
        "pheroos.drivers",
        "pheroos.conformance",
        "pheroos.cli",
    }
    violations: list[str] = []
    for path in sorted((ROOT / "pheroos" / "trace").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            for module_name in imported:
                if any(
                    module_name == name or module_name.startswith(name + ".")
                    for name in forbidden
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{module_name}")
    assert violations == []

    script = (
        "import sys; import pheroos.trace; "
        f"forbidden={forbidden!r}; "
        "loaded={name for name in sys.modules "
        "if any(name == root or name.startswith(root + '.') for root in forbidden)}; "
        "assert not loaded, sorted(loaded)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_trace_private_import_graph_is_one_way() -> None:
    graph, aggregate_imports = _trace_import_graph()

    assert aggregate_imports == []
    assert _cyclic_components(graph) == []
