from __future__ import annotations

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import (
    validate_certificate_policy,
    validate_commit_window_policy,
    validate_distributed_commit_policy,
    validate_evidence_qualification_policy,
    validate_risk_bands,
    validate_support_lease_policy,
    validate_terminal_outcome_policy,
)


def _validate_bound_commit_policy(
    policy: CollectiveCommitPolicy,
    bindings: dict[str, object],
) -> None:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError(
            "commit window requires a canonical CollectiveCommitPolicy"
        )
    assurance = bindings["assurance"]
    if type(assurance) is not CommitAssurance:
        raise GovernanceError("commit window assurance binding is invalid")
    if policy.policy_version != COMMIT_POLICY_VERSION or policy.model != COMMIT_MODEL:
        raise GovernanceError("commit window policy version or model is unsupported")
    if policy.assurance != assurance.value:
        raise GovernanceError("commit window policy assurance binding mismatch")
    if policy.target != bindings["target"]:
        raise GovernanceError("commit window policy target binding mismatch")
    observed_root = commit_policy_fingerprint(
        policy,
        profile=str(bindings["profile"]),
    )
    if observed_root != bindings["commit_policy_root"]:
        raise GovernanceError("commit window policy root binding mismatch")
    diagnostics = (
        *validate_evidence_qualification_policy(
            policy.evidence_qualification,
            path="collective_commit_policy.evidence_qualification",
        ),
        *validate_support_lease_policy(
            policy.support_lease,
            path="collective_commit_policy.support_lease",
        ),
        *validate_commit_window_policy(
            policy.commit_window,
            path="collective_commit_policy.commit_window",
        ),
        *validate_terminal_outcome_policy(
            policy.terminal_outcome,
            assurance=policy.assurance,
            path="collective_commit_policy.terminal_outcome",
        ),
        *validate_certificate_policy(
            policy.certificate,
            assurance=policy.assurance,
            path="collective_commit_policy.certificate",
        ),
        *validate_distributed_commit_policy(
            policy.distributed,
            assurance=policy.assurance,
            path="collective_commit_policy.distributed",
        ),
        *validate_risk_bands(
            policy,
            path="collective_commit_policy.risk_bands",
        ),
    )
    if diagnostics:
        codes = ", ".join(sorted({item.code for item in diagnostics}))
        raise GovernanceError(f"commit window policy is invalid: {codes}")


def _validate_commit_binding_values(
    *,
    profile: object,
    assurance: CommitAssurance,
    manifest_root: object,
    commit_policy_root: object,
    protocol_id: object,
    run_id: object,
    target: object,
    epoch: object,
    field_name: str,
) -> None:
    if type(assurance) is not CommitAssurance:
        raise GovernanceError(f"{field_name} assurance is invalid")
    _validate_profile_assurance(profile, assurance, field_name=field_name)
    require_commit_fingerprint(manifest_root, f"{field_name} manifest_root")
    require_commit_fingerprint(
        commit_policy_root,
        f"{field_name} commit_policy_root",
    )
    require_commit_text(protocol_id, f"{field_name} protocol_id")
    require_commit_text(run_id, f"{field_name} run_id")
    require_commit_text(target, f"{field_name} target")
    require_commit_step(epoch, f"{field_name} epoch")


def _normalized_window_bindings(
    *,
    profile: object,
    assurance: CommitAssurance,
    manifest_root: object,
    commit_policy_root: object,
    protocol_id: object,
    run_id: object,
    target: object,
    epoch: object,
    field_name: str,
) -> dict[str, object]:
    _validate_commit_binding_values(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name=field_name,
    )
    return {
        "profile": require_commit_profile(profile, f"{field_name} profile"),
        "assurance": assurance,
        "manifest_root": require_commit_fingerprint(
            manifest_root,
            f"{field_name} manifest_root",
        ),
        "commit_policy_root": require_commit_fingerprint(
            commit_policy_root,
            f"{field_name} commit_policy_root",
        ),
        "protocol_id": require_commit_text(
            protocol_id,
            f"{field_name} protocol_id",
        ),
        "run_id": require_commit_text(run_id, f"{field_name} run_id"),
        "target": require_commit_text(target, f"{field_name} target"),
        "epoch": require_commit_step(epoch, f"{field_name} epoch"),
    }


def _validate_profile_assurance(
    profile: object,
    assurance: CommitAssurance,
    *,
    field_name: str,
) -> None:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")


def _normalized_labels(values: object, label: str) -> tuple[str, ...]:
    return require_commit_labels(
        values,
        f"{label} values",
        allow_empty=True,
    )


def _require_binding(value: object, field_name: str) -> str:
    return require_commit_text(value, field_name)


def _require_non_negative_integer(value: object, field_name: str) -> int:
    return require_commit_step(value, field_name)
