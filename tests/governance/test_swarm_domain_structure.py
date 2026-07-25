from __future__ import annotations

import ast
from importlib import import_module
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "pheroos" / "governance"

DOMAIN_MODULES = {
    "_pheromone": (
        "records",
        "legacy_normalization",
        "policy_validation",
        "invariants",
        "lifecycle",
        "scoring",
        "diffusion",
    ),
    "_swarm": (
        "signals",
        "records",
        "replay",
        "scoring",
        "trace",
        "pipeline",
    ),
}

ALLOWED_INTERNAL_EDGES = {
    "_pheromone.records": set(),
    "_pheromone.legacy_normalization": {"_pheromone.records"},
    "_pheromone.policy_validation": {"_pheromone.records"},
    "_pheromone.invariants": {
        "_pheromone.legacy_normalization",
        "_pheromone.policy_validation",
        "_pheromone.records",
    },
    "_pheromone.lifecycle": {"_pheromone.records", "_pheromone.invariants"},
    "_pheromone.scoring": {
        "_pheromone.records",
        "_pheromone.invariants",
        "_pheromone.lifecycle",
    },
    "_pheromone.diffusion": {
        "_pheromone.records",
        "_pheromone.invariants",
        "_pheromone.lifecycle",
    },
    "_swarm.signals": set(),
    "_swarm.records": set(),
    "_swarm.replay": {"_swarm.records", "_swarm.signals"},
    "_swarm.scoring": {"_swarm.records", "_swarm.signals"},
    "_swarm.trace": {
        "_swarm.records",
        "_swarm.replay",
        "_swarm.signals",
    },
    "_swarm.pipeline": {
        "_swarm.records",
        "_swarm.replay",
        "_swarm.scoring",
        "_swarm.signals",
        "_swarm.trace",
    },
}

REQUIRED_OWNERS = {
    "_pheromone.records": {"PheromoneTrail", "PheromonePolicy"},
    "_pheromone.legacy_normalization": set(),
    "_pheromone.policy_validation": set(),
    "_pheromone.invariants": {
        "validate_pheromone_policy",
        "validate_pheromone_trail",
    },
    "_pheromone.lifecycle": {
        "deposit_pheromone_trails",
        "evaporate_trails_with_records",
    },
    "_pheromone.scoring": {"score_pheromone_trails_result"},
    "_pheromone.diffusion": {"diffuse_pheromone_trails_with_records"},
    "_swarm.signals": {"ScoutReport", "validate_scout_report"},
    "_swarm.records": {"CollectiveDecisionState", "HybridCollectiveStep"},
    "_swarm.replay": {
        "hybrid_collective_step_is_authoritative",
        "replay_state_from_hybrid_step",
    },
    "_swarm.scoring": {"score_candidates", "candidate_score_lineage"},
    "_swarm.trace": {"_hybrid_step_trace_events"},
    "_swarm.pipeline": {
        "evaluate_collective_decision",
        "evaluate_hybrid_collective_step",
    },
}


def _source_module_name(package: str, module: str) -> str:
    return f"pheroos.governance.{package}.{module}"


def _tree(package: str, module: str) -> ast.Module:
    path = GOVERNANCE / package / f"{module}.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _private_edges(package: str, module: str) -> set[str]:
    edges = set()
    for node in ast.walk(_tree(package, module)):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        prefix = "pheroos.governance."
        if not node.module.startswith(prefix):
            continue
        remainder = node.module[len(prefix) :]
        if remainder.startswith(("_pheromone.", "_swarm.")):
            edges.add(remainder)
    return edges


def test_private_domain_import_graph_is_explicit_acyclic_and_one_way() -> None:
    observed = {}
    for package, modules in DOMAIN_MODULES.items():
        for module in modules:
            node = f"{package}.{module}"
            edges = _private_edges(package, module)
            same_domain_edges = {
                edge for edge in edges if edge.startswith(f"{package}.")
            }
            assert same_domain_edges == ALLOWED_INTERNAL_EDGES[node]
            observed[node] = edges

    # Swarm orchestration may consume pheromone lifecycle contracts; the
    # pheromone substrate must never import back into swarm orchestration.
    assert all(
        not edge.startswith("_swarm.")
        for node, edges in observed.items()
        if node.startswith("_pheromone.")
        for edge in edges
    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        assert node not in visiting, f"private governance import cycle at {node}"
        if node in visited:
            return
        visiting.add(node)
        for edge in observed[node]:
            if edge in observed:
                visit(edge)
        visiting.remove(node)
        visited.add(node)

    for node in observed:
        visit(node)


def test_private_domains_do_not_import_public_facades_or_runtime_registries() -> None:
    forbidden_modules = {
        "pheroos.governance",
        "pheroos.governance.pheromone",
        "pheroos.governance.collective",
    }
    for package, modules in DOMAIN_MODULES.items():
        for module in modules:
            tree = _tree(package, module)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert node.module not in forbidden_modules
                    assert node.module != "threading"
                elif isinstance(node, ast.Import):
                    assert all(
                        alias.name not in forbidden_modules for alias in node.names
                    )
                    assert all(alias.name != "threading" for alias in node.names)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in {
                        "register_export",
                        "register_service",
                        "get_service",
                    }


def test_every_lifecycle_algorithm_has_one_private_owner_and_thin_facade() -> None:
    for facade_name in ("pheromone", "collective"):
        path = GOVERNANCE / f"{facade_name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            for node in tree.body
        )
        assert len(path.read_text(encoding="utf-8").splitlines()) < 250

    definitions: dict[str, str] = {}
    for package, modules in DOMAIN_MODULES.items():
        facade_name = "pheromone" if package == "_pheromone" else "collective"
        facade = import_module(f"pheroos.governance.{facade_name}")
        expected_owner = f"pheroos.governance.{facade_name}"
        for module in modules:
            private = import_module(_source_module_name(package, module))
            tree = _tree(package, module)
            owned = {
                node.name
                for node in tree.body
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                )
            }
            assert REQUIRED_OWNERS[f"{package}.{module}"] <= owned
            for name in owned:
                assert name not in definitions, (
                    f"{name} is implemented by both {definitions[name]} and "
                    f"{package}.{module}"
                )
                definitions[name] = f"{package}.{module}"
            for name in private.__all__:
                private_value = getattr(private, name)
                assert getattr(facade, name) is private_value
                if inspect.isclass(private_value) or inspect.isroutine(private_value):
                    assert private_value.__module__ == expected_owner


def test_diffusion_owner_retains_queue_and_trace_index_complexity_guards() -> None:
    source = (GOVERNANCE / "_pheromone" / "diffusion.py").read_text(encoding="utf-8")
    assert "from collections import deque" in source
    assert "frontier = deque(" in source
    assert "frontier.popleft()" in source
    assert "trail_by_trace_id" in source
    assert ".pop(0)" not in source
    assert "reversed(diffused)" not in source
