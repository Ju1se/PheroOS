from __future__ import annotations

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
)
from pheroos.governance.errors import GovernanceError


def _validate_assessment_lineage_roots(
    record: object,
    *,
    has_assessment: bool,
    field_name: str,
) -> None:
    mandatory = (
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "stop_resolution_root",
        "permission_root",
    )
    candidate = (
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
    )
    if has_assessment:
        for name in mandatory:
            require_commit_fingerprint(
                getattr(record, name),
                f"{field_name} {name}",
            )
        values = tuple(getattr(record, name) for name in candidate)
        if any(values) and not all(values):
            raise GovernanceError(
                f"{field_name} candidate lineage roots must be complete"
            )
        for value in values:
            if value:
                require_commit_fingerprint(
                    value,
                    f"{field_name} candidate lineage root",
                )
    elif any(getattr(record, name) for name in (*mandatory, *candidate)):
        raise GovernanceError(
            f"{field_name} cannot carry assessment lineage without an assessment"
        )


def _validate_sealed_heartbeat_lineage(
    record: object,
    *,
    field_name: str,
) -> None:
    for name in ("sealed_window", "heartbeat_continuous"):
        if type(getattr(record, name)) is not bool:
            raise GovernanceError(f"{field_name} {name} must be boolean")
    require_commit_step(record.sealed_at_step, f"{field_name} sealed_at_step")
    require_commit_step(
        record.heartbeat_sequence,
        f"{field_name} heartbeat_sequence",
    )
    if record.sealed_window:
        require_commit_fingerprint(record.seal_ref, f"{field_name} seal_ref")
        if record.sealed_at_step > record.current_step:
            raise GovernanceError(f"{field_name} seal is from the future")
    elif (
        record.seal_ref
        or record.sealed_at_step
        or record.previous_progress_ref
        or record.heartbeat_sequence
    ):
        raise GovernanceError(f"unsealed {field_name} carries seal lineage")
    if record.previous_progress_ref:
        require_commit_fingerprint(
            record.previous_progress_ref,
            f"{field_name} previous_progress_ref",
        )
        if not record.sealed_window or record.heartbeat_sequence == 0:
            raise GovernanceError(
                f"{field_name} predecessor requires a sealed heartbeat sequence"
            )
    elif record.heartbeat_sequence != 0:
        raise GovernanceError(f"{field_name} initial heartbeat sequence must be zero")
