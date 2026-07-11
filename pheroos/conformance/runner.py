from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pheroos.conformance.checks import (
    candidate_declaration,
    collective_policy,
    domain_neutrality,
    driver_lifecycle_boundary,
    driver_contract,
    extension_contract,
    hybrid_authority_boundary,
    hybrid_trace_contract,
    kernel_contract,
    kernel_import_boundary,
    layer_coordination_policy,
    manifest_schema,
    output_contract,
    pheromone_behavior,
    pheromone_diffusion,
    pheromone_kind_profile,
    pheromone_policy,
    pheromone_reinforcement,
    pheromone_response_model,
    pheromone_subject_scoring,
    policy_adjustment_bounds,
    public_abi_boundary,
    quorum_policy,
    recovery_policy,
    safe_fallback_collective,
    score_breakdown_contract,
    source_surface,
    swarm_trace_contract,
    trace_contract,
)
from pheroos.conformance.profile import (
    MANIFEST_PROFILE,
    SOURCE_PROFILE,
    ConformanceProfile,
    profile_for_manifest,
)
from pheroos.conformance.report import CheckResult, ConformanceReport
from pheroos.protocol.loader import load_capability_manifest
from pheroos.protocol.models import CapabilityManifest


ManifestCheck = Callable[[CapabilityManifest], CheckResult]


MANIFEST_CHECKS: dict[str, ManifestCheck] = {
    "candidate_declaration": candidate_declaration.check,
    "quorum_policy": quorum_policy.check,
    "collective_policy": collective_policy.check,
    "safe_fallback_collective": safe_fallback_collective.check,
    "score_breakdown_contract": score_breakdown_contract.check,
    "pheromone_policy": pheromone_policy.check,
    "pheromone_behavior": pheromone_behavior.check,
    "pheromone_subject_scoring": pheromone_subject_scoring.check,
    "pheromone_kind_profile": pheromone_kind_profile.check,
    "pheromone_diffusion": pheromone_diffusion.check,
    "pheromone_reinforcement": pheromone_reinforcement.check,
    "pheromone_response_model": pheromone_response_model.check,
    "layer_coordination_policy": layer_coordination_policy.check,
    "policy_adjustment_bounds": policy_adjustment_bounds.check,
    "hybrid_trace_contract": hybrid_trace_contract.check,
    "hybrid_authority_boundary": hybrid_authority_boundary.check,
    "recovery_policy": recovery_policy.check,
    "output_contract": output_contract.check,
    "trace_contract": trace_contract.check,
    "swarm_trace_contract": swarm_trace_contract.check,
    "driver_contract": driver_contract.check,
    "kernel_contract": kernel_contract.check,
    "extension_contract": extension_contract.check,
}


def validate_manifest(path: str | Path) -> ConformanceReport:
    manifest_path = Path(path)
    checks = [safe_check("manifest_schema", manifest_schema.check, manifest_path)]
    checks.append(profile_contract_check(MANIFEST_PROFILE, checks))
    return ConformanceReport(
        target=str(manifest_path),
        checks=checks,
        profile=MANIFEST_PROFILE.version,
    )


def run_conformance(path: str | Path, *, root: str | Path | None = None) -> ConformanceReport:
    """Run only the checks declared by the manifest-selected ABI profile.

    ``root`` remains accepted for source compatibility, but manifest
    conformance intentionally does not use it.  Source-boundary proof is a
    separate versioned profile exposed by :func:`run_source_conformance`.
    """

    del root
    target = Path(path)
    manifest_path = target / "capability.json" if target.is_dir() else target
    checks = [safe_check("manifest_schema", manifest_schema.check, manifest_path)]
    profile = MANIFEST_PROFILE
    if checks[0].ok:
        try:
            manifest = load_capability_manifest(manifest_path)
            profile = profile_for_manifest(manifest)
        except Exception as exc:  # total-function boundary for CLI consumers
            checks.append(exception_result("manifest_load", exc))
        else:
            for check_name in profile.required_checks:
                if check_name == "manifest_schema":
                    continue
                check = MANIFEST_CHECKS.get(check_name)
                if check is None:
                    checks.append(CheckResult(check_name, False, "check implementation is not registered"))
                    continue
                checks.append(safe_check(check_name, check, manifest))
    checks.append(profile_contract_check(profile, checks))
    return ConformanceReport(target=str(target), checks=checks, profile=profile.version)


def run_source_conformance(core_root: str | Path | None = None) -> ConformanceReport:
    """Prove repository/package source cohesion under an explicit profile.

    The root is never inferred from the current working directory.  When it is
    omitted, it is resolved from the installed ``pheroos.conformance`` package
    location, which is reliable for source/editable installs.  A wheel without
    all required source surfaces fails the ``source_surface`` check instead of
    receiving an empty-scan pass.
    """

    root = Path(core_root).resolve() if core_root is not None else Path(__file__).resolve().parents[2]
    checks = [
        safe_check("source_surface", source_surface.check, root),
        safe_check("domain_neutrality_public_core", domain_neutrality.check_public_core, root),
        safe_check("package_import_boundary", kernel_import_boundary.check, root),
        safe_check("driver_lifecycle_boundary", driver_lifecycle_boundary.check),
        safe_check("public_abi_boundary", public_abi_boundary.check),
    ]
    checks.append(profile_contract_check(SOURCE_PROFILE, checks))
    return ConformanceReport(target=str(root), checks=checks, profile=SOURCE_PROFILE.version)


def safe_check(name: str, check: Callable[..., CheckResult], *args: Any) -> CheckResult:
    try:
        result = check(*args)
    except Exception as exc:
        return exception_result(name, exc)
    if not isinstance(result, CheckResult):
        return CheckResult(name, False, f"invalid check result type: {type(result).__name__}")
    if result.name != name:
        return CheckResult(name, False, f"check returned mismatched name: {result.name}")
    return result


def exception_result(name: str, exc: Exception) -> CheckResult:
    detail = str(exc).strip()
    suffix = f": {detail}" if detail else ""
    return CheckResult(name, False, f"{type(exc).__name__}{suffix}")


def profile_contract_check(profile: ConformanceProfile, checks: list[CheckResult]) -> CheckResult:
    observed = {check.name: check for check in checks}
    missing = [name for name in profile.required_checks if name not in observed]
    failing = [name for name in profile.required_checks if name in observed and not observed[name].ok]
    detail = ", ".join([f"missing:{name}" for name in missing] + [f"failed:{name}" for name in failing])
    return CheckResult("profile_contract", not missing and not failing, detail)


__all__ = [
    "MANIFEST_CHECKS",
    "profile_contract_check",
    "run_conformance",
    "run_source_conformance",
    "safe_check",
    "validate_manifest",
]
