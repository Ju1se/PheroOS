"""Leaf-level registry projection for manifest conformance checks.

This module deliberately owns only immutable check identities.  It must not
import the aggregate runner, concrete check implementations, or the Commit
TCK.  The runner binds these identities to callables; independent conformance
probes can inspect registration without creating a runner/check/TCK cycle.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


REGISTERED_MANIFEST_CHECK_NAMES: tuple[str, ...] = (
    "candidate_declaration",
    "quorum_policy",
    "collective_policy",
    "safe_fallback_collective",
    "score_breakdown_contract",
    "layer_coordination_policy",
    "policy_adjustment_bounds",
    "hybrid_trace_contract",
    "hybrid_authority_boundary",
    "commit_policy_contract",
    "commit_trace_contract",
    "commit_numeric_contract",
    "principal_attestation_contract",
    "risk_monotonicity_contract",
    "membership_snapshot_contract",
    "observation_binding_contract",
    "counterevidence_contract",
    "challenge_coverage_contract",
    "support_lease_contract",
    "commit_metrics_contract",
    "commit_channel_separation",
    "commit_window_contract",
    "commit_liveness_contract",
    "commit_authority_boundary",
    "commit_certificate_contract",
    "certificate_output_contract",
    "distributed_finality_contract",
    "certificate_conflict_contract",
    "no_assurance_downgrade",
    "recovery_policy",
    "output_contract",
    "trace_contract",
    "driver_contract",
    "kernel_contract",
    "extension_contract",
)


@dataclass(frozen=True)
class ActiveManifestCheckProjection:
    required: tuple[str, ...]
    registered: tuple[str, ...]
    missing: tuple[str, ...]
    skipped_or_na: tuple[str, ...]


def project_active_manifest_checks(
    required_checks: Iterable[str],
) -> ActiveManifestCheckProjection:
    """Project required checks against the immutable built-in registry."""

    required = tuple(required_checks)
    registered_names = frozenset(REGISTERED_MANIFEST_CHECK_NAMES)
    registered = tuple(
        name
        for name in required
        if name == "manifest_schema" or name in registered_names
    )
    missing = tuple(sorted(set(required) - set(registered)))
    skipped_or_na = tuple(
        name for name in registered if name.lower().startswith(("skip", "n/a", "na:"))
    )
    return ActiveManifestCheckProjection(
        required=required,
        registered=registered,
        missing=missing,
        skipped_or_na=skipped_or_na,
    )


__all__ = [
    "ActiveManifestCheckProjection",
    "REGISTERED_MANIFEST_CHECK_NAMES",
    "project_active_manifest_checks",
]
