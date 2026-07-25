from __future__ import annotations

from pheroos.conformance.profile import (
    COMMIT_AUTHORITY_CHECKS,
    profile_for_manifest,
)
from pheroos.conformance.report import CheckResult
from pheroos.protocol import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    HYBRID_COMMIT_PROFILE_VERSION,
    CapabilityManifest,
    CollectiveCommitPolicy,
    collective_fallback_id,
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
    has_hybrid_pheromone_features,
    validate_capability_manifest,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        return CheckResult("commit_policy_contract", True)

    problems: list[str] = []
    diagnostics = [
        item for item in validate_capability_manifest(manifest) if item.level == "error"
    ]
    problems.extend(f"diagnostic:{item.code}" for item in diagnostics)
    if type(policy) is not CollectiveCommitPolicy:
        problems.append("canonical_policy_type")
        return _result(problems)
    problems.extend(_target_and_fallback_problems(manifest, policy))
    profile_problems, profile_version = _profile_contract_problems(manifest, policy)
    problems.extend(profile_problems)
    if profile_version is not None:
        problems.extend(_authority_root_problems(manifest, policy, profile_version))
    return _result(problems)


def _target_and_fallback_problems(
    manifest: CapabilityManifest,
    policy: CollectiveCommitPolicy,
) -> list[str]:
    problems: list[str] = []
    target_ids = {target.id for target in manifest.protocol.targets}
    candidates = {candidate.id: candidate for candidate in manifest.protocol.candidates}
    fallback_id = policy.terminal_outcome.safe_fallback_candidate
    fallback = candidates.get(fallback_id)

    if policy.target not in target_ids:
        problems.append("declared_target")
    if policy.target != manifest.protocol.quorum_policy.target:
        problems.append("quorum_target_binding")
    if fallback_id != manifest.protocol.quorum_policy.fallback_candidate:
        problems.append("quorum_fallback_binding")
    if fallback_id != collective_fallback_id(manifest.protocol):
        problems.append("collective_fallback_binding")
    if fallback is None:
        problems.append("declared_fallback")
    elif not fallback.safe_fallback:
        problems.append("safe_fallback_marker")
    elif fallback.target != policy.target:
        problems.append("fallback_target_binding")
    return problems


def _profile_contract_problems(
    manifest: CapabilityManifest,
    policy: CollectiveCommitPolicy,
) -> tuple[list[str], str | None]:
    problems: list[str] = []
    try:
        selected = profile_for_manifest(manifest)
    except (TypeError, ValueError) as exc:
        problems.append(f"profile_selection:{type(exc).__name__}:{exc}")
        return problems, None
    expected_version = _expected_profile_version(manifest, policy)
    if selected.version != expected_version:
        problems.append(f"profile_selection:{selected.version}!={expected_version}")
    missing_authority_checks = sorted(
        set(COMMIT_AUTHORITY_CHECKS) - set(selected.required_checks)
    )
    problems.extend(f"profile_missing:{name}" for name in missing_authority_checks)
    return problems, selected.version


def _authority_root_problems(
    manifest: CapabilityManifest,
    policy: CollectiveCommitPolicy,
    profile_version: str,
) -> list[str]:
    problems: list[str] = []
    manifest_root = commit_manifest_fingerprint(
        manifest,
        profile=profile_version,
    )
    policy_root = commit_policy_fingerprint(policy, profile=profile_version)
    if not _is_sha256_root(manifest_root):
        problems.append("manifest_authority_root")
    if not _is_sha256_root(policy_root):
        problems.append("policy_authority_root")
    if manifest_root != commit_manifest_fingerprint(
        manifest,
        profile=profile_version,
    ):
        problems.append("manifest_authority_root_nondeterministic")
    if policy_root != commit_policy_fingerprint(policy, profile=profile_version):
        problems.append("policy_authority_root_nondeterministic")
    return problems


def _expected_profile_version(
    manifest: CapabilityManifest,
    policy: CollectiveCommitPolicy,
) -> str:
    if policy.assurance == "distributed":
        return DISTRIBUTED_COMMIT_PROFILE_VERSION
    if policy.assurance == "certified":
        return CERTIFIED_COMMIT_PROFILE_VERSION
    if policy.assurance == "evidence_bound" and has_hybrid_pheromone_features(
        manifest.protocol.collective_decision_policy
    ):
        return HYBRID_COMMIT_PROFILE_VERSION
    return COMMIT_INTEGRITY_PROFILE_VERSION


def _is_sha256_root(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _result(problems: list[str]) -> CheckResult:
    unique = sorted(set(problems))
    return CheckResult(
        "commit_policy_contract",
        not unique,
        ", ".join(unique),
    )


__all__ = ["check"]
