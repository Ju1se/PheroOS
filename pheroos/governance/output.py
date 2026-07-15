from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from enum import StrEnum
from types import MappingProxyType
from collections.abc import Mapping

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.evidence import EvidenceGraph
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import QuorumDecision, quorum_decision_is_authoritative
from pheroos.governance.stop_signal import StopResolution
from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    OutcomeCertificate,
    evidence_commit_certificate_fingerprint,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    outcome_certificate_fingerprint,
    verify_evidence_commit_certificate,
    verify_outcome_certificate,
)
from pheroos.governance.commit_state import (
    DecisionOutcome,
    DecisionOutcomeKind,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance.permission import ActionPermission, action_permission_matches
from pheroos.governance.permission import action_permission_fingerprint
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_is_authoritative,
)
from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitState,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_matches,
)
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.trace import TraceEvent


@dataclass(frozen=True)
class OutputContract:
    committed_candidate_required: bool = True
    evidence_required: bool = True
    stop_resolution_required: bool = True
    publication_permission_required: bool = True

    def __post_init__(self) -> None:
        disabled = [
            name
            for name, enabled in (
                ("committed_candidate_required", self.committed_candidate_required),
                ("evidence_required", self.evidence_required),
                ("stop_resolution_required", self.stop_resolution_required),
                ("publication_permission_required", self.publication_permission_required),
            )
            if enabled is not True
        ]
        if disabled:
            raise GovernanceError(f"output authorization gate cannot be disabled: {disabled[0]}")


@dataclass(frozen=True)
class OutputAuthorizationResult:
    authorized: bool
    gates: dict[str, bool]
    trace_event: TraceEvent

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", MappingProxyType(dict(self.gates)))


def output_authorized(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    candidate_set: CandidateSet | None = None,
) -> bool:
    gates = output_gate_lineage(
        contract,
        decision,
        evidence,
        stop_resolutions,
        publication_permission=publication_permission,
        candidate_set=candidate_set,
    )
    return all(gates.values())


def output_gate_lineage(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    candidate_set: CandidateSet | None = None,
) -> dict[str, bool]:
    mandatory_contract = bool(
        isinstance(contract, OutputContract)
        and contract.committed_candidate_required is True
        and contract.evidence_required is True
        and contract.stop_resolution_required is True
        and contract.publication_permission_required is True
    )
    target_resolutions = [
        resolution
        for resolution in stop_resolutions
        if (
            isinstance(resolution, StopResolution)
            and isinstance(resolution.target, str)
            and resolution.target == decision.target
            and isinstance(resolution.action, str)
            and bool(resolution.action.strip())
            and isinstance(resolution.blocked, bool)
        )
    ]
    declared_candidate = False
    if candidate_set is not None:
        try:
            candidate_set.require_declared_for_target(decision.candidate_id, decision.target)
        except GovernanceError:
            pass
        else:
            declared_candidate = True
    return {
        "committed_candidate": (
            mandatory_contract
            and decision.committed
            and quorum_decision_is_authoritative(decision)
            and declared_candidate
        ),
        "evidence_provenance": (
            mandatory_contract and evidence.has_evidence() and evidence.has_provenance()
        ),
        "stop_resolution": mandatory_contract
        and not any(resolution.blocked for resolution in target_resolutions)
        and bool(target_resolutions),
        "publication_permission": mandatory_contract and publication_permission is True,
    }


def evaluate_output_authorization(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    protocol_id: str,
    candidate_set: CandidateSet | None = None,
) -> OutputAuthorizationResult:
    gates = output_gate_lineage(
        contract,
        decision,
        evidence,
        stop_resolutions,
        publication_permission=publication_permission,
        candidate_set=candidate_set,
    )
    authorized = all(gates.values())
    event = TraceEvent(
        event_type="output",
        protocol_id=protocol_id,
        target=decision.target,
        reason="output authorized by all four gates" if authorized else "output denied by contract gate",
        lineage={**gates, "authorized": authorized},
    )
    event.validate()
    return OutputAuthorizationResult(authorized=authorized, gates=gates, trace_event=event)


class CommitOutputAction(StrEnum):
    DELIVER = "deliver"
    PUBLISH = "publish"
    EXECUTE = "execute"


_COMMIT_OUTPUT_AUTHORIZATION_ISSUANCE = object()


@dataclass(frozen=True)
class CommitOutputAuthorization:
    action: CommitOutputAction
    authorized: bool
    profile: str
    outcome_ref: str
    certificate_ref: str
    output_payload_fingerprint: str
    policy_ref: str
    threshold_ref: str
    stop_resolution_ref: str
    permission_ref: str
    distributed_state_ref: str
    distributed_conflict_root: str
    gates: Mapping[str, bool]
    reason_codes: tuple[str, ...]
    _issuance: object | None = dataclass_field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", MappingProxyType(dict(self.gates)))
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        _validate_commit_output_authorization(self)


def deliver_terminal_outcome(
    outcome: DecisionOutcome,
    *,
    output_payload_fingerprint: str,
) -> CommitOutputAuthorization:
    """Return every governance-issued terminal outcome to its caller.

    Delivery is not a publication claim and therefore does not accept a caller
    permission boolean, an action permission, or a stop-resolution substitute.
    """

    from pheroos.governance._commit_validation import require_commit_fingerprint

    try:
        output_ref = require_commit_fingerprint(
            output_payload_fingerprint,
            "commit delivery output payload fingerprint",
        )
        authoritative = decision_outcome_is_authoritative(outcome)
        terminal = bool(
            type(outcome) is DecisionOutcome
            and outcome.terminal is True
            and outcome.delivery_eligible is True
        )
        outcome_ref = (
            decision_outcome_fingerprint(outcome)
            if authoritative and type(outcome) is DecisionOutcome
            else ""
        )
    except GovernanceError:
        output_ref = ""
        authoritative = False
        terminal = False
        outcome_ref = ""
    gates = {
        "authoritative_terminal_outcome": authoritative and terminal,
        "output_payload_bound": bool(output_ref),
    }
    authorized = all(gates.values())
    reasons = tuple(
        name for name, satisfied in gates.items() if not satisfied
    ) or ("delivered",)
    return _issue_commit_output_authorization(
        action=CommitOutputAction.DELIVER,
        authorized=authorized,
        profile=(
            outcome.profile
            if type(outcome) is DecisionOutcome
            else "pheroos-commit-integrity-v1"
        ),
        outcome_ref=outcome_ref,
        certificate_ref="",
        output_payload_fingerprint=output_ref,
        policy_ref="",
        threshold_ref="",
        stop_resolution_ref="",
        permission_ref="",
        distributed_state_ref="",
        distributed_conflict_root="",
        gates=gates,
        reason_codes=reasons,
    )


def authorize_terminal_publication(
    outcome: DecisionOutcome,
    *,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: CommitThresholdSnapshot,
    certificate: LocalCommitReceipt | EvidenceCommitCertificate | OutcomeCertificate | DistributedCommitCertificate,
    output_payload_fingerprint: str,
    stop_resolution: StopResolutionVerification,
    permission: ActionPermission,
    current_step: int,
    trusted_issuer_attestations: Mapping[str, str] | None = None,
    distributed_state: DistributedCommitState | None = None,
    portable_certificate: EvidenceCommitCertificate | None = None,
    trusted_witness_attestations: Mapping[str, str] | None = None,
) -> CommitOutputAuthorization:
    return _authorize_terminal_action(
        outcome,
        action=CommitAction.PUBLISH,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        certificate=certificate,
        output_payload_fingerprint=output_payload_fingerprint,
        stop_resolution=stop_resolution,
        permission=permission,
        current_step=current_step,
        trusted_issuer_attestations=trusted_issuer_attestations,
        distributed_state=distributed_state,
        portable_certificate=portable_certificate,
        trusted_witness_attestations=trusted_witness_attestations,
    )


def authorize_terminal_execution(
    outcome: DecisionOutcome,
    *,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: CommitThresholdSnapshot,
    certificate: LocalCommitReceipt | EvidenceCommitCertificate | OutcomeCertificate | DistributedCommitCertificate,
    output_payload_fingerprint: str,
    stop_resolution: StopResolutionVerification,
    permission: ActionPermission,
    current_step: int,
    trusted_issuer_attestations: Mapping[str, str] | None = None,
    distributed_state: DistributedCommitState | None = None,
    portable_certificate: EvidenceCommitCertificate | None = None,
    trusted_witness_attestations: Mapping[str, str] | None = None,
) -> CommitOutputAuthorization:
    return _authorize_terminal_action(
        outcome,
        action=CommitAction.EXECUTE,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        certificate=certificate,
        output_payload_fingerprint=output_payload_fingerprint,
        stop_resolution=stop_resolution,
        permission=permission,
        current_step=current_step,
        trusted_issuer_attestations=trusted_issuer_attestations,
        distributed_state=distributed_state,
        portable_certificate=portable_certificate,
        trusted_witness_attestations=trusted_witness_attestations,
    )


def _authorize_terminal_action(
    outcome: DecisionOutcome,
    *,
    action: CommitAction,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: CommitThresholdSnapshot,
    certificate: LocalCommitReceipt | EvidenceCommitCertificate | OutcomeCertificate | DistributedCommitCertificate,
    output_payload_fingerprint: str,
    stop_resolution: StopResolutionVerification,
    permission: ActionPermission,
    current_step: int,
    trusted_issuer_attestations: Mapping[str, str] | None,
    distributed_state: DistributedCommitState | None,
    portable_certificate: EvidenceCommitCertificate | None,
    trusted_witness_attestations: Mapping[str, str] | None,
) -> CommitOutputAuthorization:
    from pheroos.governance._commit_validation import (
        require_commit_fingerprint,
        require_commit_step,
    )

    if action not in {CommitAction.PUBLISH, CommitAction.EXECUTE}:
        raise GovernanceError("commit output action must be publish or execute")
    try:
        current = require_commit_step(current_step, "commit output current_step")
        output_ref = require_commit_fingerprint(
            output_payload_fingerprint,
            "commit output payload fingerprint",
        )
    except GovernanceError:
        current = 0
        output_ref = ""

    authoritative_outcome = decision_outcome_is_authoritative(outcome)
    outcome_ref = ""
    if authoritative_outcome:
        try:
            outcome_ref = decision_outcome_fingerprint(outcome)
        except GovernanceError:
            authoritative_outcome = False

    policy_bound = _commit_output_policy_matches(
        commit_policy,
        outcome if type(outcome) is DecisionOutcome else None,
    )
    threshold_bound = _commit_output_threshold_matches(
        threshold_snapshot,
        outcome if type(outcome) is DecisionOutcome else None,
    )
    certificate_ref, certificate_valid = _bound_certificate(
        outcome if type(outcome) is DecisionOutcome else None,
        certificate,
        commit_policy=commit_policy,
        output_payload_fingerprint=output_ref,
        trusted_issuer_attestations=trusted_issuer_attestations,
        distributed_state=distributed_state,
        portable_certificate=portable_certificate,
        trusted_witness_attestations=trusted_witness_attestations,
    )

    policy_outcome_allowed = False
    threshold_outcome_allowed = False
    hard_kind_allowed = False
    if policy_bound and threshold_bound and type(outcome) is DecisionOutcome:
        terminal = commit_policy.terminal_outcome
        if action is CommitAction.PUBLISH:
            policy_outcome_allowed = outcome.kind.value in terminal.publishable_outcomes
            threshold_outcome_allowed = (
                outcome.kind.value in threshold_snapshot.publishable_outcomes
            )
            hard_kind_allowed = outcome.kind not in {
                DecisionOutcomeKind.INVALID,
                DecisionOutcomeKind.FINALITY_UNAVAILABLE,
                DecisionOutcomeKind.SAFETY_VIOLATION,
            }
        else:
            policy_outcome_allowed = outcome.kind.value in terminal.executable_outcomes
            threshold_outcome_allowed = (
                outcome.kind.value in threshold_snapshot.executable_outcomes
            )
            hard_kind_allowed = bool(
                outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT
                and outcome.authoritative_commit
                and outcome.epistemically_committed
            )

    stop_satisfied = bool(
        authoritative_outcome
        and certificate_valid
        and stop_resolution_verification_matches(
            stop_resolution,
            profile=outcome.profile,
            assurance=outcome.assurance,
            manifest_root=outcome.manifest_root,
            commit_policy_root=outcome.commit_policy_root,
            protocol_id=outcome.protocol_id,
            run_id=outcome.run_id,
            target=outcome.target,
            action=action,
            epoch=outcome.epoch,
            decision_ref=outcome_ref,
            certificate_ref=certificate_ref,
            current_step=current,
            require_unblocked=True,
        )
    )
    permission_satisfied = bool(
        authoritative_outcome
        and certificate_valid
        and action_permission_matches(
            permission,
            profile=outcome.profile,
            assurance=outcome.assurance,
            manifest_root=outcome.manifest_root,
            commit_policy_root=outcome.commit_policy_root,
            protocol_id=outcome.protocol_id,
            run_id=outcome.run_id,
            target=outcome.target,
            action=action,
            epoch=outcome.epoch,
            decision_ref=outcome_ref,
            certificate_ref=certificate_ref,
            current_step=current,
            require_allowed=True,
        )
    )
    gates = {
        "authoritative_terminal_outcome": bool(
            authoritative_outcome
            and type(outcome) is DecisionOutcome
            and outcome.terminal is True
        ),
        "policy_bound": policy_bound,
        "threshold_bound": threshold_bound,
        "policy_outcome_allowed": policy_outcome_allowed,
        "threshold_outcome_allowed": threshold_outcome_allowed,
        "hard_kind_allowed": hard_kind_allowed,
        "certificate_valid": certificate_valid,
        "output_payload_bound": bool(output_ref),
        f"{action.value}_stop_resolved": stop_satisfied,
        f"{action.value}_permission_allowed": permission_satisfied,
    }
    authorized = all(gates.values())
    reasons = tuple(
        name for name, satisfied in gates.items() if not satisfied
    ) or (f"{action.value}_authorized",)
    return _issue_commit_output_authorization(
        action=(
            CommitOutputAction.PUBLISH
            if action is CommitAction.PUBLISH
            else CommitOutputAction.EXECUTE
        ),
        authorized=authorized,
        profile=(
            outcome.profile
            if type(outcome) is DecisionOutcome
            else "pheroos-commit-integrity-v1"
        ),
        outcome_ref=outcome_ref,
        certificate_ref=certificate_ref,
        output_payload_fingerprint=output_ref,
        policy_ref=_safe_policy_ref(commit_policy, outcome),
        threshold_ref=_safe_threshold_ref(threshold_snapshot),
        stop_resolution_ref=_safe_stop_ref(stop_resolution),
        permission_ref=_safe_permission_ref(permission),
        distributed_state_ref=_safe_distributed_state_ref(distributed_state),
        distributed_conflict_root=_safe_distributed_conflict_root(
            distributed_state
        ),
        gates=gates,
        reason_codes=reasons,
    )


def _commit_output_policy_matches(
    policy: object,
    outcome: DecisionOutcome | None,
) -> bool:
    try:
        return bool(
            type(policy) is CollectiveCommitPolicy
            and type(outcome) is DecisionOutcome
            and policy.assurance == outcome.assurance.value
            and policy.target == outcome.target
            and commit_policy_fingerprint(policy, profile=outcome.profile)
            == outcome.commit_policy_root
        )
    except (GovernanceError, ValueError):
        return False


def _commit_output_threshold_matches(
    threshold: object,
    outcome: DecisionOutcome | None,
) -> bool:
    try:
        return bool(
            type(threshold) is CommitThresholdSnapshot
            and commit_threshold_snapshot_is_authoritative(threshold)
            and type(outcome) is DecisionOutcome
            and threshold.profile == outcome.profile
            and threshold.assurance is outcome.assurance
            and threshold.manifest_root == outcome.manifest_root
            and threshold.commit_policy_root == outcome.commit_policy_root
            and threshold.protocol_id == outcome.protocol_id
            and threshold.run_id == outcome.run_id
            and threshold.target == outcome.target
            and threshold.epoch == outcome.epoch
            and threshold.risk_assessment_fingerprint
            == outcome.risk_assessment_root
            and commit_threshold_snapshot_fingerprint(threshold)
            == outcome.threshold_root
        )
    except (GovernanceError, ValueError):
        return False


def _bound_certificate(
    outcome: DecisionOutcome | None,
    certificate: object,
    *,
    commit_policy: CollectiveCommitPolicy,
    output_payload_fingerprint: str,
    trusted_issuer_attestations: Mapping[str, str] | None,
    distributed_state: object | None,
    portable_certificate: EvidenceCommitCertificate | None,
    trusted_witness_attestations: Mapping[str, str] | None,
) -> tuple[str, bool]:
    if type(outcome) is not DecisionOutcome or not output_payload_fingerprint:
        return "", False
    try:
        if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
            if outcome.assurance is CommitAssurance.EVIDENCE_BOUND:
                if type(certificate) is not LocalCommitReceipt:
                    return "", False
                ref = local_commit_receipt_fingerprint(certificate)
                return ref, bool(
                    outcome.certificate_ref == ref
                    and local_commit_receipt_is_authoritative(certificate)
                    and _certificate_lineage_matches_outcome(
                        certificate,
                        outcome,
                        output_payload_fingerprint=output_payload_fingerprint,
                    )
                )
            if outcome.assurance is CommitAssurance.CERTIFIED:
                if type(certificate) is not EvidenceCommitCertificate:
                    return "", False
                ref = evidence_commit_certificate_fingerprint(certificate)
                return ref, bool(
                    outcome.certificate_ref == ref
                    and verify_evidence_commit_certificate(
                        certificate,
                        trusted_issuer_attestations=(
                            trusted_issuer_attestations or {}
                        ),
                        expected_certificate_ref=ref,
                        expected_output_payload_fingerprint=(
                            output_payload_fingerprint
                        ),
                    )
                    and _certificate_lineage_matches_outcome(
                        certificate,
                        outcome,
                        output_payload_fingerprint=output_payload_fingerprint,
                    )
                )
            if outcome.assurance is CommitAssurance.DISTRIBUTED:
                from pheroos.governance.distributed_commit import (
                    DistributedCommitCertificate,
                    DistributedCommitState,
                    distributed_commit_certificate_fingerprint,
                    distributed_commit_certificate_is_current_final,
                    verify_distributed_commit_certificate,
                )

                if (
                    type(certificate) is not DistributedCommitCertificate
                    or type(distributed_state) is not DistributedCommitState
                    or type(portable_certificate) is not EvidenceCommitCertificate
                ):
                    return "", False
                ref = distributed_commit_certificate_fingerprint(certificate)
                return ref, bool(
                    outcome.certificate_ref == ref
                    and verify_distributed_commit_certificate(
                        certificate,
                        commit_policy=commit_policy,
                        portable_certificate=portable_certificate,
                        trusted_issuer_attestations=(
                            trusted_issuer_attestations or {}
                        ),
                        trusted_witness_attestations=(
                            trusted_witness_attestations or {}
                        ),
                        expected_certificate_ref=ref,
                        require_final=True,
                    )
                    and distributed_commit_certificate_is_current_final(
                        certificate,
                        distributed_state,
                    )
                    and _distributed_certificate_lineage_matches_outcome(
                        certificate,
                        outcome,
                        output_payload_fingerprint=output_payload_fingerprint,
                    )
                )
            return "", False

        if type(certificate) is not OutcomeCertificate:
            return "", False
        ref = outcome_certificate_fingerprint(certificate)
        return ref, bool(
            certificate.outcome_ref == decision_outcome_fingerprint(outcome)
            and certificate.outcome_kind is outcome.kind
            and certificate.profile == outcome.profile
            and certificate.assurance is outcome.assurance
            and certificate.output_payload_fingerprint
            == output_payload_fingerprint
            and verify_outcome_certificate(
                certificate,
                trusted_issuer_attestations=trusted_issuer_attestations,
                expected_certificate_ref=ref,
                expected_output_payload_fingerprint=output_payload_fingerprint,
            )
        )
    except (GovernanceError, ValueError):
        return "", False


def _certificate_lineage_matches_outcome(
    certificate: LocalCommitReceipt | EvidenceCommitCertificate,
    outcome: DecisionOutcome,
    *,
    output_payload_fingerprint: str,
) -> bool:
    return bool(
        certificate.profile == outcome.profile
        and certificate.assurance is outcome.assurance
        and certificate.manifest_root == outcome.manifest_root
        and certificate.commit_policy_root == outcome.commit_policy_root
        and certificate.protocol_id == outcome.protocol_id
        and certificate.run_id == outcome.run_id
        and certificate.target == outcome.target
        and certificate.epoch == outcome.epoch
        and certificate.candidate_id == outcome.candidate_id
        and certificate.output_payload_fingerprint == output_payload_fingerprint
        and certificate.risk_chain_state_root == outcome.risk_chain_state_root
        and certificate.risk_assessment_root == outcome.risk_assessment_root
        and certificate.risk_policy_root == outcome.risk_policy_root
        and certificate.membership_snapshot_root
        == outcome.membership_snapshot_root
        and certificate.membership_epoch_state_root
        == outcome.membership_epoch_state_root
        and certificate.membership_root == outcome.membership_root
        and certificate.threshold_root == outcome.threshold_root
        and certificate.replay_state_root == outcome.replay_state_ref
        and certificate.replay_root == outcome.replay_root
        and certificate.support_replay_state_root
        == outcome.support_replay_state_root
        and certificate.support_replay_root == outcome.support_replay_root
        and certificate.evidence_root == outcome.collective_evidence_root
        and certificate.challenge_root == outcome.collective_challenge_root
        and certificate.lease_root == outcome.collective_lease_root
        and certificate.candidate_evidence_root
        == outcome.candidate_evidence_root
        and certificate.candidate_challenge_root
        == outcome.candidate_challenge_root
        and certificate.candidate_lease_root == outcome.candidate_lease_root
        and certificate.window_state_root == outcome.window_state_ref
        and certificate.window_root == outcome.window_root
        and certificate.stop_resolution_root == outcome.stop_resolution_root
        and certificate.permission_root == outcome.permission_root
        and certificate.context_root == outcome.context_ref
        and certificate.assessment_root == outcome.assessment_ref
    )


def _distributed_certificate_lineage_matches_outcome(
    certificate: object,
    outcome: DecisionOutcome,
    *,
    output_payload_fingerprint: str,
) -> bool:
    try:
        proposal = certificate.proposal
        exact = {
            "profile": outcome.profile,
            "assurance": outcome.assurance,
            "manifest_root": outcome.manifest_root,
            "commit_policy_root": outcome.commit_policy_root,
            "protocol_id": outcome.protocol_id,
            "run_id": outcome.run_id,
            "target": outcome.target,
            "epoch": outcome.epoch,
            "candidate_id": outcome.candidate_id,
            "output_payload_fingerprint": output_payload_fingerprint,
            "risk_chain_state_root": outcome.risk_chain_state_root,
            "risk_assessment_root": outcome.risk_assessment_root,
            "risk_policy_root": outcome.risk_policy_root,
            "membership_snapshot_root": outcome.membership_snapshot_root,
            "membership_epoch_state_root": outcome.membership_epoch_state_root,
            "membership_root": outcome.membership_root,
            "threshold_root": outcome.threshold_root,
            "replay_state_root": outcome.replay_state_ref,
            "replay_root": outcome.replay_root,
            "support_replay_state_root": outcome.support_replay_state_root,
            "support_replay_root": outcome.support_replay_root,
            "evidence_root": outcome.collective_evidence_root,
            "challenge_root": outcome.collective_challenge_root,
            "lease_root": outcome.collective_lease_root,
            "candidate_evidence_root": outcome.candidate_evidence_root,
            "candidate_challenge_root": outcome.candidate_challenge_root,
            "candidate_lease_root": outcome.candidate_lease_root,
            "window_state_root": outcome.window_state_ref,
            "window_root": outcome.window_root,
            "stop_resolution_root": outcome.stop_resolution_root,
            "permission_root": outcome.permission_root,
            "context_root": outcome.context_ref,
            "assessment_root": outcome.assessment_ref,
        }
        return all(getattr(proposal, name) == value for name, value in exact.items())
    except (AttributeError, GovernanceError):
        return False


def _issue_commit_output_authorization(
    **values: object,
) -> CommitOutputAuthorization:
    result = CommitOutputAuthorization(**values)  # type: ignore[arg-type]
    fingerprint = commit_output_authorization_fingerprint(result)
    object.__setattr__(
        result,
        "_issuance",
        (_COMMIT_OUTPUT_AUTHORIZATION_ISSUANCE, fingerprint),
    )
    return result


def _validate_commit_output_authorization(
    result: CommitOutputAuthorization,
) -> None:
    from pheroos.governance._commit_validation import (
        require_commit_fingerprint,
        require_commit_labels,
        require_commit_profile,
    )

    if type(result.action) is not CommitOutputAction:
        raise GovernanceError("commit output authorization action is invalid")
    if type(result.authorized) is not bool:
        raise GovernanceError("commit output authorization authorized must be boolean")
    require_commit_profile(result.profile, "commit output authorization profile")
    for name in (
        "outcome_ref",
        "certificate_ref",
        "output_payload_fingerprint",
        "policy_ref",
        "threshold_ref",
        "stop_resolution_ref",
        "permission_ref",
        "distributed_state_ref",
        "distributed_conflict_root",
    ):
        value = getattr(result, name)
        if value:
            require_commit_fingerprint(
                value,
                f"commit output authorization {name}",
            )
    if not isinstance(result.gates, Mapping) or not result.gates:
        raise GovernanceError("commit output authorization gates are required")
    normalized_gates: dict[str, bool] = {}
    for name, value in result.gates.items():
        if not isinstance(name, str) or not name or name != name.strip():
            raise GovernanceError("commit output gate name is invalid")
        if type(value) is not bool:
            raise GovernanceError("commit output gate value must be boolean")
        normalized_gates[name] = value
    if result.authorized is not all(normalized_gates.values()):
        raise GovernanceError("commit output authorization gate result is inconsistent")
    require_commit_labels(
        result.reason_codes,
        "commit output authorization reason_codes",
    )
    if result.authorized and not (
        result.outcome_ref and result.output_payload_fingerprint
    ):
        raise GovernanceError("authorized output requires outcome and payload refs")
    if bool(result.distributed_state_ref) is not bool(
        result.distributed_conflict_root
    ):
        raise GovernanceError(
            "distributed state and conflict roots must be bound together"
        )
    if result.action is CommitOutputAction.DELIVER:
        if any(
            (
                result.certificate_ref,
                result.policy_ref,
                result.threshold_ref,
                result.stop_resolution_ref,
                result.permission_ref,
                result.distributed_state_ref,
                result.distributed_conflict_root,
            )
        ):
            raise GovernanceError("delivery cannot claim publish/execute authority refs")
    elif result.authorized and not all(
        (
            result.certificate_ref,
            result.policy_ref,
            result.threshold_ref,
            result.stop_resolution_ref,
            result.permission_ref,
        )
    ):
        raise GovernanceError(
            "authorized publish/execute result requires every authority ref"
        )


def commit_output_authorization_payload(
    result: CommitOutputAuthorization,
) -> dict[str, object]:
    if type(result) is not CommitOutputAuthorization:
        raise GovernanceError(
            "commit output authorization must use the canonical record"
        )
    _validate_commit_output_authorization(result)
    return {
        "action": result.action,
        "authorized": result.authorized,
        "certificate_ref": result.certificate_ref,
        "gates": dict(result.gates),
        "distributed_conflict_root": result.distributed_conflict_root,
        "distributed_state_ref": result.distributed_state_ref,
        "outcome_ref": result.outcome_ref,
        "output_payload_fingerprint": result.output_payload_fingerprint,
        "permission_ref": result.permission_ref,
        "policy_ref": result.policy_ref,
        "profile": result.profile,
        "reason_codes": result.reason_codes,
        "stop_resolution_ref": result.stop_resolution_ref,
        "threshold_ref": result.threshold_ref,
    }


def commit_output_authorization_fingerprint(
    result: CommitOutputAuthorization,
) -> str:
    return commit_payload_fingerprint(
        commit_output_authorization_payload(result),
        schema="pheroos-commit-output-authorization-v1",
        profile=result.profile,
    )


def commit_output_authorization_is_authoritative(result: object) -> bool:
    if type(result) is not CommitOutputAuthorization:
        return False
    try:
        issuance = result._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_OUTPUT_AUTHORIZATION_ISSUANCE
            and issuance[1] == commit_output_authorization_fingerprint(result)
        )
    except Exception:
        return False


def _safe_policy_ref(
    policy: object,
    outcome: object,
) -> str:
    try:
        if type(policy) is not CollectiveCommitPolicy or type(outcome) is not DecisionOutcome:
            return ""
        return commit_policy_fingerprint(policy, profile=outcome.profile)
    except (GovernanceError, ValueError):
        return ""


def _safe_threshold_ref(threshold: object) -> str:
    try:
        if type(threshold) is not CommitThresholdSnapshot:
            return ""
        return commit_threshold_snapshot_fingerprint(threshold)
    except GovernanceError:
        return ""


def _safe_stop_ref(stop: object) -> str:
    try:
        if type(stop) is not StopResolutionVerification:
            return ""
        return stop_resolution_verification_fingerprint(stop)
    except GovernanceError:
        return ""


def _safe_permission_ref(permission: object) -> str:
    try:
        if type(permission) is not ActionPermission:
            return ""
        return action_permission_fingerprint(permission)
    except GovernanceError:
        return ""


def _safe_distributed_state_ref(state: object) -> str:
    try:
        from pheroos.governance.distributed_commit import (
            DistributedCommitState,
            distributed_commit_state_fingerprint,
        )

        if type(state) is not DistributedCommitState:
            return ""
        return distributed_commit_state_fingerprint(state)
    except (GovernanceError, ValueError):
        return ""


def _safe_distributed_conflict_root(state: object) -> str:
    try:
        from pheroos.governance.distributed_commit import (
            DistributedCommitState,
            distributed_commit_state_payload,
        )

        if type(state) is not DistributedCommitState:
            return ""
        payload = distributed_commit_state_payload(state)
        return commit_payload_fingerprint(
            {
                "conflict_findings": payload["conflict_findings"],
                "epoch": state.epoch,
                "frozen": state.frozen,
                "transitioned": state.transitioned,
            },
            schema="pheroos-distributed-output-conflict-root-v1",
            profile=state.profile,
        )
    except (GovernanceError, KeyError, ValueError):
        return ""


__all__ = [
    "CommitOutputAction",
    "CommitOutputAuthorization",
    "OutputAuthorizationResult",
    "OutputContract",
    "authorize_terminal_execution",
    "authorize_terminal_publication",
    "commit_output_authorization_fingerprint",
    "commit_output_authorization_is_authoritative",
    "commit_output_authorization_payload",
    "deliver_terminal_outcome",
    "evaluate_output_authorization",
    "output_authorized",
    "output_gate_lineage",
]
