from __future__ import annotations

from pathlib import Path

from pheroos.conformance.checks import (
    candidate_declaration,
    collective_policy,
    domain_neutrality,
    driver_contract,
    extension_contract,
    kernel_import_boundary,
    manifest_schema,
    output_contract,
    pheromone_behavior,
    pheromone_policy,
    quorum_policy,
    recovery_policy,
    safe_fallback_collective,
    swarm_trace_contract,
    trace_contract,
)
from pheroos.conformance.report import ConformanceReport
from pheroos.protocol.loader import load_capability_manifest


def validate_manifest(path: str | Path) -> ConformanceReport:
    manifest_path = Path(path)
    return ConformanceReport(target=str(manifest_path), checks=[manifest_schema.check(manifest_path)])


def run_conformance(path: str | Path, *, root: str | Path | None = None) -> ConformanceReport:
    target = Path(path)
    manifest_path = target / "capability.json" if target.is_dir() else target
    repo_root = Path(root) if root is not None else Path.cwd()
    checks = [manifest_schema.check(manifest_path)]
    if checks[0].ok:
        manifest = load_capability_manifest(manifest_path)
        checks.extend(
            [
                candidate_declaration.check(manifest),
                quorum_policy.check(manifest),
                collective_policy.check(manifest),
                safe_fallback_collective.check(manifest),
                pheromone_policy.check(manifest),
                pheromone_behavior.check(manifest),
                recovery_policy.check(manifest),
                output_contract.check(manifest),
                trace_contract.check(manifest),
                swarm_trace_contract.check(manifest),
                driver_contract.check(manifest),
                extension_contract.check(manifest),
            ]
        )
    checks.append(domain_neutrality.check_public_core(repo_root))
    checks.append(kernel_import_boundary.check(repo_root))
    return ConformanceReport(target=str(target), checks=checks)
