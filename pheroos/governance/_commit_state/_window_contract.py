from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, cast

from pheroos.governance._commit_state.invariants import _WindowBindings
from pheroos.governance._commit_state._record_views import CommitWindowStateView
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
)
from pheroos.governance._commit.assessment import (
    project_commit_assessment_for_window,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)


class _ThresholdSnapshotBindings(TypedDict):
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    risk_assessment_root: str
    threshold_root: str
    stability_steps: int
    issued_at_step: int
    expires_at_step: int
    risk_band: str
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    minimum_support_clusters: int
    minimum_support_ratio_ppm: int
    minimum_source_diversity: int
    minimum_margin: int
    required_challenge_categories: tuple[str, ...]
    minimum_assurance: str
    publishable_outcomes: tuple[str, ...]
    executable_outcomes: tuple[str, ...]


class _CommitAssessmentWindowView(TypedDict):
    assessment_ref: str
    status: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    context_ref: str
    risk_assessment_root: str
    risk_chain_state_root: str
    risk_policy_root: str
    membership_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
    threshold_root: str
    replay_state_ref: str
    replay_root: str
    support_replay_state_root: str
    support_replay_root: str
    collective_evidence_root: str
    collective_challenge_root: str
    collective_lease_root: str
    candidate_evidence_root: str
    candidate_challenge_root: str
    candidate_lease_root: str
    stop_resolution_root: str
    permission_root: str
    leader_candidate_id: str
    ready: bool
    reason_codes: tuple[str, ...]
    evaluated_at_step: int


def _threshold_snapshot_bindings(snapshot: object) -> _ThresholdSnapshotBindings:
    from pheroos.governance.risk import (
        CommitThresholdSnapshot,
        commit_threshold_snapshot_fingerprint,
        commit_threshold_snapshot_is_authoritative,
    )

    if type(
        snapshot
    ) is not CommitThresholdSnapshot or not commit_threshold_snapshot_is_authoritative(
        snapshot
    ):
        raise GovernanceError(
            "commit window requires an authoritative threshold snapshot"
        )
    return {
        "profile": snapshot.profile,
        "assurance": snapshot.assurance,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "protocol_id": snapshot.protocol_id,
        "run_id": snapshot.run_id,
        "target": snapshot.target,
        "epoch": snapshot.epoch,
        "risk_assessment_root": snapshot.risk_assessment_fingerprint,
        "threshold_root": commit_threshold_snapshot_fingerprint(snapshot),
        "stability_steps": snapshot.stability_steps,
        "issued_at_step": snapshot.issued_at_step,
        "expires_at_step": snapshot.expires_at_step,
        "risk_band": snapshot.risk_band.value,
        "minimum_positive_evidence": snapshot.minimum_positive_evidence,
        "maximum_counterevidence": snapshot.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            snapshot.maximum_counterevidence_ratio_ppm
        ),
        "minimum_support_clusters": snapshot.minimum_support_clusters,
        "minimum_support_ratio_ppm": snapshot.minimum_support_ratio_ppm,
        "minimum_source_diversity": snapshot.minimum_source_diversity,
        "minimum_margin": snapshot.minimum_margin,
        "required_challenge_categories": (snapshot.required_challenge_categories),
        "minimum_assurance": snapshot.minimum_assurance.value,
        "publishable_outcomes": snapshot.publishable_outcomes,
        "executable_outcomes": snapshot.executable_outcomes,
    }


def _validate_window_threshold_snapshot(
    snapshot: object,
    *,
    commit_policy: CollectiveCommitPolicy,
    bindings: _WindowBindings,
    risk_assessment_root: object,
    current_step: int,
) -> tuple[str, int]:
    observed = _threshold_snapshot_bindings(snapshot)
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if observed[name] != bindings[name]:
            raise GovernanceError(f"commit window threshold {name} binding mismatch")
    expected_risk = require_commit_fingerprint(
        risk_assessment_root,
        "commit window threshold risk assessment root",
    )
    if observed["risk_assessment_root"] != expected_risk:
        raise GovernanceError(
            "commit window threshold risk assessment binding mismatch"
        )
    current = require_commit_step(current_step, "commit window threshold step")
    if (
        not int(observed["issued_at_step"])
        <= current
        < int(observed["expires_at_step"])
    ):
        raise GovernanceError("commit window threshold snapshot is not fresh")
    try:
        band = commit_policy.risk_bands[str(observed["risk_band"])]
    except KeyError as exc:
        raise GovernanceError(
            "commit window threshold risk band is not declared"
        ) from exc
    exact_values = {
        "minimum_positive_evidence": band.minimum_positive_evidence,
        "maximum_counterevidence": band.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (band.maximum_counterevidence_ratio_ppm),
        "minimum_support_clusters": band.minimum_support_clusters,
        "minimum_support_ratio_ppm": band.minimum_support_ratio_ppm,
        "minimum_source_diversity": band.minimum_source_diversity,
        "minimum_margin": band.minimum_margin,
        "stability_steps": band.stability_steps,
        "minimum_assurance": band.minimum_assurance,
    }
    observed_values: Mapping[str, object] = observed
    if any(observed_values[name] != value for name, value in exact_values.items()):
        raise GovernanceError(
            "commit window threshold values do not match the risk band policy"
        )
    for name, observed_labels in (
        (
            "required_challenge_categories",
            observed["required_challenge_categories"],
        ),
        ("publishable_outcomes", observed["publishable_outcomes"]),
        ("executable_outcomes", observed["executable_outcomes"]),
    ):
        if set(observed_labels) != set(getattr(band, name)):
            raise GovernanceError(
                f"commit window threshold {name} does not match policy"
            )
    return (
        str(observed["threshold_root"]),
        int(observed["stability_steps"]),
    )


def _commit_window_authority_key(bindings: _WindowBindings) -> str:
    # Epoch and mutable authority heads are deliberately excluded: every epoch
    # restart and policy/risk/membership transition stays on this one run chain.
    return commit_payload_fingerprint(
        {
            "protocol_id": bindings["protocol_id"],
            "run_id": bindings["run_id"],
            "target": bindings["target"],
        },
        schema="pheroos-commit-window-authority-key-v1",
        # The authority identity must not partition by a caller-selected
        # profile; a profile change is a different base/transition on the same
        # protocol/run/target chain, never a parallel cursor.
        profile="pheroos-commit-integrity-v1",
    )


def _validate_window_chain_scope(
    state: CommitWindowStateView,
    bindings: _WindowBindings,
    *,
    allow_epoch_change: bool = False,
) -> None:
    for name in ("profile", "assurance", "protocol_id", "run_id", "target"):
        if getattr(state, name) != bindings[name]:
            raise GovernanceError(f"commit window {name} scope mismatch")
    if not allow_epoch_change and state.epoch != bindings["epoch"]:
        raise GovernanceError("commit window epoch scope mismatch")


def _authoritative_commit_assessment_view(
    assessment: object,
    *,
    current_step: int | None = None,
) -> _CommitAssessmentWindowView:
    return cast(
        _CommitAssessmentWindowView,
        project_commit_assessment_for_window(
            assessment,
            current_step=current_step,
        ),
    )


def _validate_assessment_matches_window_head(
    state: CommitWindowStateView,
    view: _CommitAssessmentWindowView,
) -> None:
    view_values: Mapping[str, object] = view
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(state, name) != view[name]:
            raise GovernanceError(f"commit liveness assessment {name} binding mismatch")
    for state_name, view_name in (
        ("risk_assessment_root", "risk_assessment_root"),
        ("membership_root", "membership_root"),
        ("threshold_root", "threshold_root"),
        ("last_assessment_ref", "assessment_ref"),
        ("last_context_ref", "context_ref"),
        ("last_assessment_status", "status"),
    ):
        if getattr(state, state_name) != view_values[view_name]:
            raise GovernanceError(
                f"commit liveness assessment {view_name} is not the window head"
            )
    if state.last_evaluated_step != view["evaluated_at_step"]:
        raise GovernanceError("commit liveness assessment step is not current")


def _window_reset_reason(
    state: CommitWindowStateView,
    *,
    current_step: int,
    ready: bool,
    leader_candidate_id: str,
    manifest_root: str,
    commit_policy_root: str,
    risk_assessment_root: str,
    membership_root: str,
    threshold_root: str,
) -> str:
    if (
        manifest_root != state.manifest_root
        or commit_policy_root != state.commit_policy_root
    ):
        return "policy_change"
    if risk_assessment_root != state.risk_assessment_root:
        return "risk_change"
    if membership_root != state.membership_root:
        return "membership_change"
    if threshold_root != state.threshold_root:
        return "threshold_change"
    if current_step != state.last_evaluated_step + 1:
        return "step_gap"
    if state.last_ready and ready and leader_candidate_id != state.leader_candidate_id:
        return "leader_change"
    if not ready:
        return "gate_failure"
    return "none"


def _window_root(
    assessment_refs: tuple[str, ...],
    *,
    profile: str,
    run_id: str,
    epoch: int,
) -> str:
    return commit_payload_fingerprint(
        {
            "epoch": epoch,
            "ordered_assessment_refs": assessment_refs,
            "run_id": run_id,
        },
        schema="pheroos-commit-window-root-v1",
        profile=profile,
    )
