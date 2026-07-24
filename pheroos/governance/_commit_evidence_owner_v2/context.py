"""Manifest-derived Commit Evidence v2 policy and target context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
    EvidenceQualificationPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_evidence_qualification_policy

from pheroos.governance._commit_evidence_projection_v2.common import (
    evidence_root_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidencePolicySnapshotV2,
)


@dataclass(frozen=True, slots=True)
class CommitEvidenceContextV2:
    manifest: ScopedProtocolManifestV2
    manifest_root: str
    authority_policy_root: str
    commit_policy_root: str
    evidence_policy: CommitEvidencePolicySnapshotV2
    protocol_ref: str
    target_ref: str
    profile: str
    assurance: CommitAssurance
    declared_candidate_refs: frozenset[str]


def commit_evidence_context_v2(
    manifest: ScopedProtocolManifestV2,
    *,
    profile: str,
    target_ref: str,
) -> CommitEvidenceContextV2:
    """Validate and detach the exact Protocol declarations used to qualify."""

    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("commit evidence requires an exact scoped manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    require_text_v2(profile, "commit evidence profile")
    require_text_v2(target_ref, "commit evidence target_ref")
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("commit evidence manifest has no collective commit policy")
    if policy.target != target_ref:
        raise ValueError("commit evidence policy target is cross-bound")
    try:
        assurance = CommitAssurance(policy.assurance)
    except ValueError as exc:
        raise ValueError("commit evidence assurance is unsupported") from exc
    if profile not in COMMIT_PROFILES_BY_ASSURANCE.get(assurance.value, frozenset()):
        raise ValueError("commit evidence profile and assurance are mismatched")
    diagnostics = validate_evidence_qualification_policy(
        policy.evidence_qualification,
        path="collective_commit_policy.evidence_qualification",
    )
    if diagnostics:
        codes = ", ".join(sorted({item.code for item in diagnostics}))
        raise ValueError(f"commit evidence policy is invalid: {codes}")
    manifest_root = detached.manifest_root
    authority_policy_root = detached.authority_policy.root()
    commit_policy_root = commit_policy_fingerprint(policy, profile=profile)
    for label, value in (
        ("manifest_root", manifest_root),
        ("authority_policy_root", authority_policy_root),
        ("commit_policy_root", commit_policy_root),
    ):
        require_root_v2(value, f"commit evidence {label}")
    evidence_policy = _policy_snapshot(
        policy.evidence_qualification,
        _evidence_extensions(detached.to_dict()),
    )
    candidates = frozenset(
        item.id for item in detached.candidates if item.target == target_ref
    )
    if not candidates:
        raise ValueError("commit evidence target has no declared candidate")
    return CommitEvidenceContextV2(
        manifest=detached,
        manifest_root=manifest_root,
        authority_policy_root=authority_policy_root,
        commit_policy_root=commit_policy_root,
        evidence_policy=evidence_policy,
        protocol_ref=detached.id,
        target_ref=target_ref,
        profile=profile,
        assurance=assurance,
        declared_candidate_refs=candidates,
    )


def _policy_snapshot(
    policy: EvidenceQualificationPolicy, extensions: object
) -> CommitEvidencePolicySnapshotV2:
    if type(policy) is not EvidenceQualificationPolicy:
        raise TypeError(
            "commit evidence policy must use the exact Protocol declaration"
        )
    extensions_root = evidence_root_v2("policy-extensions", {"extensions": extensions})
    return CommitEvidencePolicySnapshotV2(
        numeric_scale=policy.numeric_scale,
        minimum_quality_ppm=policy.minimum_quality_ppm,
        minimum_relevance_ppm=policy.minimum_relevance_ppm,
        positive_group_cap=policy.positive_group_cap,
        counter_group_cap=policy.counter_group_cap,
        counter_weight_ppm=policy.counter_weight_ppm,
        minimum_positive_evidence=policy.minimum_positive_evidence,
        maximum_counterevidence=policy.maximum_counterevidence,
        maximum_counterevidence_ratio_ppm=policy.maximum_counterevidence_ratio_ppm,
        domain_contribution_floor=policy.domain_contribution_floor,
        minimum_source_diversity=policy.minimum_source_diversity,
        required_challenge_categories=tuple(policy.required_challenge_categories),
        observation_ttl_steps=policy.observation_ttl_steps,
        require_provenance=policy.require_provenance,
        require_trace=policy.require_trace,
        extensions_root=extensions_root,
    )


def _evidence_extensions(manifest: dict[str, object]) -> object:
    policy = manifest.get("collective_commit_policy")
    if type(policy) is not dict:
        raise ValueError("commit evidence portable policy is unavailable")
    evidence = cast(dict[str, object], policy).get("evidence_qualification")
    if type(evidence) is not dict:
        raise ValueError("commit evidence portable declaration is unavailable")
    return cast(dict[str, object], evidence).get("extensions", {})


__all__ = ["CommitEvidenceContextV2", "commit_evidence_context_v2"]
