"""Read-only structural views shared by Commit State helper modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:

    class CommitScopeView(Protocol):
        @property
        def profile(self) -> str: ...

        @property
        def assurance(self) -> object: ...

        @property
        def manifest_root(self) -> str: ...

        @property
        def commit_policy_root(self) -> str: ...

        @property
        def protocol_id(self) -> str: ...

        @property
        def run_id(self) -> str: ...

        @property
        def target(self) -> str: ...

        @property
        def epoch(self) -> int: ...

    class AssessmentLineageView(Protocol):
        @property
        def assessment_ref(self) -> str: ...

        @property
        def context_ref(self) -> str: ...

        @property
        def risk_assessment_root(self) -> str: ...

        @property
        def risk_chain_state_root(self) -> str: ...

        @property
        def risk_policy_root(self) -> str: ...

        @property
        def membership_root(self) -> str: ...

        @property
        def membership_snapshot_root(self) -> str: ...

        @property
        def membership_epoch_state_root(self) -> str: ...

        @property
        def threshold_root(self) -> str: ...

        @property
        def replay_state_ref(self) -> str: ...

        @property
        def replay_root(self) -> str: ...

        @property
        def support_replay_state_root(self) -> str: ...

        @property
        def support_replay_root(self) -> str: ...

        @property
        def collective_evidence_root(self) -> str: ...

        @property
        def collective_challenge_root(self) -> str: ...

        @property
        def collective_lease_root(self) -> str: ...

        @property
        def candidate_evidence_root(self) -> str: ...

        @property
        def candidate_challenge_root(self) -> str: ...

        @property
        def candidate_lease_root(self) -> str: ...

        @property
        def stop_resolution_root(self) -> str: ...

        @property
        def permission_root(self) -> str: ...

    class SealedHeartbeatView(Protocol):
        @property
        def current_step(self) -> int: ...

        @property
        def window_state_ref(self) -> str: ...

        @property
        def sealed_window(self) -> bool: ...

        @property
        def seal_ref(self) -> str: ...

        @property
        def sealed_at_step(self) -> int: ...

        @property
        def heartbeat_continuous(self) -> bool: ...

        @property
        def heartbeat_sequence(self) -> int: ...

        @property
        def previous_progress_ref(self) -> str: ...

    class LivenessRecordView(AssessmentLineageView, SealedHeartbeatView, Protocol):
        """Common validation projection for liveness input and result records."""

    class CommitWindowStateView(CommitScopeView, Protocol):
        @property
        def absolute_deadline_step(self) -> int: ...

        @property
        def absolute_run_deadline_step(self) -> int: ...

        @property
        def authority(self) -> object: ...

        @property
        def assessment_replay_root(self) -> str: ...

        @property
        def assessment_replay_state_ref(self) -> str: ...

        @property
        def candidate_challenge_root(self) -> str: ...

        @property
        def candidate_evidence_root(self) -> str: ...

        @property
        def candidate_lease_root(self) -> str: ...

        @property
        def chain_id(self) -> str: ...

        @property
        def collective_challenge_root(self) -> str: ...

        @property
        def collective_evidence_root(self) -> str: ...

        @property
        def collective_lease_root(self) -> str: ...

        @property
        def initialized_at_step(self) -> int: ...

        @property
        def issuer_id(self) -> str: ...

        @property
        def last_assessment_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def last_assessment_ref(self) -> str: ...

        @property
        def last_assessment_status(self) -> str: ...

        @property
        def last_context_ref(self) -> str: ...

        @property
        def last_evaluated_step(self) -> int: ...

        @property
        def last_ready(self) -> bool: ...

        @property
        def leader_candidate_id(self) -> str: ...

        @property
        def membership_root(self) -> str: ...

        @property
        def membership_epoch_state_root(self) -> str: ...

        @property
        def membership_snapshot_root(self) -> str: ...

        @property
        def minimum_stability_steps(self) -> int: ...

        @property
        def ordered_assessment_refs(self) -> tuple[str, ...]: ...

        @property
        def previous_state_fingerprint(self) -> str: ...

        @property
        def permission_root(self) -> str: ...

        @property
        def provenance(self) -> str: ...

        @property
        def remaining_epoch_restart_budget(self) -> int: ...

        @property
        def remaining_reset_budget(self) -> int: ...

        @property
        def reset_budget_exhausted(self) -> bool: ...

        @property
        def reset_reason(self) -> str: ...

        @property
        def revision(self) -> int: ...

        @property
        def risk_assessment_root(self) -> str: ...

        @property
        def risk_chain_state_root(self) -> str: ...

        @property
        def risk_policy_root(self) -> str: ...

        @property
        def stop_resolution_root(self) -> str: ...

        @property
        def support_replay_root(self) -> str: ...

        @property
        def support_replay_state_root(self) -> str: ...

        @property
        def threshold_root(self) -> str: ...

        @property
        def trace_event_id(self) -> str: ...

        @property
        def window_count(self) -> int: ...

        @property
        def window_root(self) -> str: ...

    class CommitLivenessInputView(
        CommitScopeView,
        LivenessRecordView,
        Protocol,
    ):
        @property
        def input_id(self) -> str: ...

        @property
        def assessment_status(self) -> str: ...

        @property
        def leader_candidate_id(self) -> str: ...

        @property
        def leader_ready_for_stability(self) -> bool: ...

        @property
        def assessment_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def deadline_reached(self) -> bool: ...

        @property
        def finality_status(self) -> object: ...

        @property
        def certificate_ref(self) -> str: ...

        @property
        def finality_verification_ref(self) -> str: ...

        @property
        def invalid_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def safety_violation_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def blocked_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def finality_reason_codes(self) -> tuple[str, ...]: ...

        @property
        def next_required_inputs(self) -> tuple[str, ...]: ...

        @property
        def issuer_id(self) -> str: ...

        @property
        def authority(self) -> object: ...

        @property
        def provenance(self) -> str: ...

        @property
        def trace_event_id(self) -> str: ...

    class DecisionProgressView(CommitScopeView, LivenessRecordView, Protocol):
        @property
        def phase(self) -> object: ...

        @property
        def absolute_deadline_step(self) -> int: ...

        @property
        def absolute_run_deadline_step(self) -> int: ...

        @property
        def remaining_reset_budget(self) -> int: ...

        @property
        def remaining_epoch_restart_budget(self) -> int: ...

        @property
        def minimum_stability_steps(self) -> int: ...

        @property
        def next_required_inputs(self) -> tuple[str, ...]: ...

        @property
        def unmet_gates(self) -> tuple[str, ...]: ...

        @property
        def leader_candidate_id(self) -> str: ...

        @property
        def window_count(self) -> int: ...

        @property
        def terminal(self) -> bool: ...

        @property
        def window_root(self) -> str: ...

    class DecisionOutcomeView(CommitScopeView, LivenessRecordView, Protocol):
        @property
        def kind(self) -> object: ...

        @property
        def absolute_deadline_step(self) -> int: ...

        @property
        def absolute_run_deadline_step(self) -> int: ...

        @property
        def authority_scope(self) -> object: ...

        @property
        def authoritative_commit(self) -> bool: ...

        @property
        def epistemically_committed(self) -> bool: ...

        @property
        def candidate_id(self) -> str: ...

        @property
        def reason_codes(self) -> tuple[str, ...]: ...

        @property
        def certificate_ref(self) -> str: ...

        @property
        def delivery_eligible(self) -> bool: ...

        @property
        def publication_eligible(self) -> bool: ...

        @property
        def execution_eligible(self) -> bool: ...

        @property
        def terminal(self) -> bool: ...

        @property
        def window_root(self) -> str: ...
else:

    class CommitScopeView(Protocol):
        pass

    class AssessmentLineageView(Protocol):
        pass

    class SealedHeartbeatView(Protocol):
        pass

    class LivenessRecordView(AssessmentLineageView, SealedHeartbeatView, Protocol):
        """Runtime placeholder for the static liveness record projection."""

    class CommitWindowStateView(CommitScopeView, Protocol):
        pass

    class CommitLivenessInputView(
        CommitScopeView,
        LivenessRecordView,
        Protocol,
    ):
        pass

    class DecisionProgressView(CommitScopeView, LivenessRecordView, Protocol):
        pass

    class DecisionOutcomeView(CommitScopeView, LivenessRecordView, Protocol):
        pass


__all__ = [
    "AssessmentLineageView",
    "CommitLivenessInputView",
    "CommitScopeView",
    "CommitWindowStateView",
    "DecisionOutcomeView",
    "DecisionProgressView",
    "LivenessRecordView",
    "SealedHeartbeatView",
]
