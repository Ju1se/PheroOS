from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.commit_numeric import (
    checked_add,
    commit_payload_fingerprint,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
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


class DecisionPhase(StrEnum):
    SEARCH = "search"
    DELIBERATE = "deliberate"
    QUORUM_PENDING = "quorum_pending"
    PROVISIONAL = "provisional"


class DecisionOutcomeKind(StrEnum):
    EVIDENCE_COMMIT = "evidence_commit"
    SAFE_FALLBACK = "safe_fallback"
    ADVISORY = "advisory"
    BLOCKED = "blocked"
    INVALID = "invalid"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    SAFETY_VIOLATION = "safety_violation"


class AuthorityScope(StrEnum):
    NONE = "none"
    GOVERNANCE_LOCAL = "governance_local"
    CERTIFIED = "certified"
    DISTRIBUTED = "distributed"
    DENIAL = "denial"


class CommitFinalityStatus(StrEnum):
    """Governance-qualified finality state consumed by bounded liveness.

    ``VERIFIED`` can only be issued by the certificate verifiers after they
    bind the exact current authority heads. Publication and execution remain
    separate, current-action authorization decisions.
    """

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


_DECISION_PROGRESS_ISSUANCE = object()
_DECISION_OUTCOME_ISSUANCE = object()
_COMMIT_WINDOW_STATE_ISSUANCE = object()
_COMMIT_WINDOW_SEAL_ISSUANCE = object()
_COMMIT_REPLAY_STATE_ISSUANCE = object()
_COMMIT_LIVENESS_INPUT_ISSUANCE = object()
_COMMIT_FINALITY_VERIFICATION_ISSUANCE = object()


class _CommitWindowCursor:
    """Strong process-local single head for one run/target window chain."""

    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "chain_id",
        "current_state",
        "current_state_fingerprint",
        "current_seal",
        "current_seal_fingerprint",
        "seal_generation",
        "seal_requests",
        "transitions",
        "liveness_inputs",
        "liveness_results",
        "current_progress",
        "current_progress_fingerprint",
        "terminal_result",
        "lock",
        "__weakref__",
    )

    def __init__(
        self,
        *,
        authority_key: str,
        base_fingerprint: str,
        chain_id: str,
    ) -> None:
        self.authority_key = authority_key
        self.base_fingerprint = base_fingerprint
        self.chain_id = chain_id
        self.current_state: CommitWindowState | None = None
        self.current_state_fingerprint = ""
        self.current_seal: CommitWindowSeal | None = None
        self.current_seal_fingerprint = ""
        self.seal_generation = 0
        self.seal_requests: dict[str, tuple[str, CommitWindowSeal]] = {}
        self.transitions: dict[
            str,
            tuple[str, CommitWindowState],
        ] = {}
        self.liveness_inputs: dict[
            str,
            tuple[str, CommitLivenessInput],
        ] = {}
        self.liveness_results: dict[
            tuple[str, int],
            tuple[str, DecisionProgress | DecisionOutcome],
        ] = {}
        self.current_progress: DecisionProgress | None = None
        self.current_progress_fingerprint = ""
        self.terminal_result: DecisionOutcome | None = None
        self.lock = RLock()


_COMMIT_WINDOW_REGISTRY_LOCK = RLock()
_COMMIT_WINDOW_CURSORS: dict[str, _CommitWindowCursor] = {}


class ReplayNamespace(StrEnum):
    PRINCIPAL = "principal"
    OBSERVATION = "observation"
    CHALLENGE = "challenge"
    COUNTEREVIDENCE_DISPOSITION = "counterevidence_disposition"
    MEMBERSHIP = "membership"
    SUPPORT_LEASE = "support_lease"
    SUPPORT_REVOCATION = "support_revocation"
    RISK_ASSESSMENT = "risk_assessment"
    THRESHOLD = "threshold"
    STOP_RESOLUTION = "stop_resolution"
    ACTION_PERMISSION = "action_permission"
    ASSESSMENT = "assessment"
    WITNESS = "witness"


class _CommitReplayCursor:
    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "current_state",
        "current_state_fingerprint",
        "transitions",
        "lock",
    )

    def __init__(self, *, authority_key: str, base_fingerprint: str) -> None:
        self.authority_key = authority_key
        self.base_fingerprint = base_fingerprint
        self.current_state: CommitReplayState | None = None
        self.current_state_fingerprint = ""
        self.transitions: dict[str, tuple[str, CommitReplayState]] = {}
        self.lock = RLock()


_COMMIT_REPLAY_REGISTRY_LOCK = RLock()
_COMMIT_REPLAY_CURSORS: dict[str, _CommitReplayCursor] = {}


@dataclass(frozen=True)
class DecisionProgress:
    phase: DecisionPhase
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    current_step: int
    absolute_deadline_step: int
    absolute_run_deadline_step: int
    remaining_reset_budget: int
    remaining_epoch_restart_budget: int
    minimum_stability_steps: int
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
    window_state_ref: str
    window_root: str
    sealed_window: bool
    seal_ref: str
    sealed_at_step: int
    heartbeat_continuous: bool
    heartbeat_sequence: int
    previous_progress_ref: str
    next_required_inputs: tuple[str, ...] = ()
    unmet_gates: tuple[str, ...] = ()
    leader_candidate_id: str = ""
    window_count: int = 0
    assessment_ref: str = ""
    terminal: bool = field(default=False, init=False)
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "next_required_inputs",
            _normalized_labels(self.next_required_inputs, "next required input"),
        )
        object.__setattr__(
            self,
            "unmet_gates",
            _normalized_labels(self.unmet_gates, "unmet gate"),
        )
        _validate_decision_progress(self)


@dataclass(frozen=True)
class DecisionOutcome:
    kind: DecisionOutcomeKind
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    current_step: int
    absolute_deadline_step: int
    absolute_run_deadline_step: int
    authority_scope: AuthorityScope
    authoritative_commit: bool
    epistemically_committed: bool
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
    window_state_ref: str
    window_root: str
    sealed_window: bool
    seal_ref: str
    sealed_at_step: int
    heartbeat_continuous: bool
    heartbeat_sequence: int
    previous_progress_ref: str
    candidate_id: str = ""
    reason_codes: tuple[str, ...] = ()
    assessment_ref: str = ""
    certificate_ref: str = ""
    delivery_eligible: bool = True
    publication_eligible: bool = False
    execution_eligible: bool = False
    terminal: bool = field(default=True, init=False)
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_codes",
            _normalized_labels(self.reason_codes, "decision reason code"),
        )
        _validate_decision_outcome(self)


@dataclass(frozen=True)
class CommitWindowState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    revision: int
    previous_state_fingerprint: str
    risk_assessment_root: str
    membership_root: str
    threshold_root: str
    minimum_stability_steps: int
    risk_chain_state_root: str
    risk_policy_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
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
    assessment_replay_state_ref: str
    assessment_replay_root: str
    initialized_at_step: int
    last_evaluated_step: int
    absolute_deadline_step: int
    absolute_run_deadline_step: int
    remaining_reset_budget: int
    remaining_epoch_restart_budget: int
    leader_candidate_id: str = ""
    window_count: int = 0
    ordered_assessment_refs: tuple[str, ...] = ()
    window_root: str = ""
    last_ready: bool = False
    last_assessment_ref: str = ""
    last_context_ref: str = ""
    last_assessment_status: str = ""
    last_assessment_reason_codes: tuple[str, ...] = ()
    reset_reason: str = "initialized"
    reset_budget_exhausted: bool = False
    issuer_id: str = ""
    authority: AuthorityLevel = AuthorityLevel.OBSERVER
    provenance: str = ""
    trace_event_id: str = ""
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ordered_assessment_refs",
            tuple(self.ordered_assessment_refs),
        )
        object.__setattr__(
            self,
            "last_assessment_reason_codes",
            _normalized_labels(
                self.last_assessment_reason_codes,
                "commit window last assessment reason code",
            ),
        )
        _validate_commit_window_state(self)


@dataclass(frozen=True)
class CommitWindowSeal:
    """A governance-issued immutable bridge from local receipt to late finality.

    The seal never rewrites ``CommitWindowState``.  It binds the exact current
    window fingerprint, every authority root, the claim/output payload and the
    original absolute deadlines.  A window transition invalidates current seal
    authority without making the historical receipt disappear.
    """

    chain_id: str
    generation: int
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    receipt_ref: str
    candidate_id: str
    claim_fingerprint: str
    output_payload_fingerprint: str
    context_ref: str
    assessment_ref: str
    window_state_ref: str
    window_root: str
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
    sealed_at_step: int
    absolute_deadline_step: int
    absolute_run_deadline_step: int
    remaining_reset_budget: int
    remaining_epoch_restart_budget: int
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_commit_window_seal(self)


@dataclass(frozen=True)
class CommitLivenessInput:
    """Governance-issued facts for the temporal terminal reducer.

    The record deliberately contains typed finality plus reason sets instead of
    caller-provided ready/terminal booleans.  Candidate readiness always comes
    from the bound authoritative ``CommitAssessment``.
    """

    input_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    current_step: int
    deadline_reached: bool
    context_ref: str
    assessment_ref: str
    assessment_status: str
    leader_candidate_id: str
    leader_ready_for_stability: bool
    assessment_reason_codes: tuple[str, ...]
    replay_state_ref: str
    replay_root: str
    risk_assessment_root: str
    risk_chain_state_root: str
    risk_policy_root: str
    membership_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
    threshold_root: str
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
    window_state_ref: str
    sealed_window: bool
    seal_ref: str
    sealed_at_step: int
    heartbeat_continuous: bool
    heartbeat_sequence: int
    previous_progress_ref: str
    finality_status: CommitFinalityStatus
    certificate_ref: str
    finality_verification_ref: str
    invalid_reason_codes: tuple[str, ...]
    safety_violation_reason_codes: tuple[str, ...]
    blocked_reason_codes: tuple[str, ...]
    finality_reason_codes: tuple[str, ...]
    next_required_inputs: tuple[str, ...]
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _authority_heads: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "invalid_reason_codes",
            "safety_violation_reason_codes",
            "blocked_reason_codes",
            "finality_reason_codes",
            "next_required_inputs",
            "assessment_reason_codes",
        ):
            object.__setattr__(
                self,
                name,
                _normalized_labels(
                    getattr(self, name),
                    f"commit liveness {name}",
                ),
            )
        _validate_commit_liveness_input(self)


@dataclass(frozen=True)
class CommitFinalityVerification:
    status: CommitFinalityStatus
    certificate_kind: str
    certificate_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    context_ref: str
    assessment_ref: str
    window_state_ref: str
    window_root: str
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
    verified_at_step: int
    verifier_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_commit_finality_verification(self)


@dataclass(frozen=True)
class ReplayReceipt:
    namespace: ReplayNamespace
    record_id: str
    nonce: str
    payload_fingerprint: str
    target: str
    candidate_id: str
    epoch: int
    principal_id: str

    def __post_init__(self) -> None:
        _validate_replay_receipt(self)


@dataclass(frozen=True)
class CommitReplayState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    revision: int
    initialized_at_step: int
    current_step: int
    previous_state_fingerprint: str
    receipts: tuple[ReplayReceipt, ...]
    receipt_root: str
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipts",
            _canonical_replay_receipts(self.receipts),
        )
        _validate_commit_replay_state(self)


def decision_progress_is_authoritative(progress: object) -> bool:
    if type(progress) is not DecisionProgress:
        return False
    try:
        issuance = progress._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _DECISION_PROGRESS_ISSUANCE
            and issuance[1] == _progress_snapshot(progress)
        )
    except Exception:
        return False


def decision_outcome_is_authoritative(outcome: object) -> bool:
    if type(outcome) is not DecisionOutcome:
        return False
    try:
        issuance = outcome._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _DECISION_OUTCOME_ISSUANCE
            and issuance[1] == _outcome_snapshot(outcome)
        )
    except Exception:
        return False


def select_terminal_outcome_kind(
    *,
    invalid: bool,
    safety_violation: bool,
    blocked: bool,
    evidence_commit_ready: bool,
    finality_unavailable: bool,
    deadline_reached: bool,
    deadline_outcome: str,
) -> DecisionOutcomeKind | None:
    for field_name, value in (
        ("invalid", invalid),
        ("safety_violation", safety_violation),
        ("blocked", blocked),
        ("evidence_commit_ready", evidence_commit_ready),
        ("finality_unavailable", finality_unavailable),
        ("deadline_reached", deadline_reached),
    ):
        if type(value) is not bool:
            raise GovernanceError(f"terminal condition {field_name} must be boolean")
    if deadline_outcome not in {
        DecisionOutcomeKind.SAFE_FALLBACK.value,
        DecisionOutcomeKind.ADVISORY.value,
    }:
        raise GovernanceError("terminal deadline outcome is unsupported")
    if invalid:
        return DecisionOutcomeKind.INVALID
    if safety_violation:
        return DecisionOutcomeKind.SAFETY_VIOLATION
    if blocked:
        return DecisionOutcomeKind.BLOCKED
    if evidence_commit_ready:
        return DecisionOutcomeKind.EVIDENCE_COMMIT
    if finality_unavailable:
        return DecisionOutcomeKind.FINALITY_UNAVAILABLE
    if deadline_reached:
        return DecisionOutcomeKind(deadline_outcome)
    return None


def initialize_commit_window_state(
    *,
    commit_policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    risk_assessment_root: str,
    membership_root: str,
    threshold_snapshot: object,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitWindowState:
    """Initialize the sole process-local window head for a run target.

    Every temporal parameter is derived from the bound policy.  There is no raw
    deadline, reset-budget, or stability-threshold initialization path.
    """

    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "commit window initialization requires governance authority"
        )
    current = require_commit_step(current_step, "commit window current_step")
    bindings = _normalized_window_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name="commit window",
    )
    normalized_risk = require_commit_fingerprint(
        risk_assessment_root,
        "commit window risk_assessment_root",
    )
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=risk_assessment_root,
        current_step=current,
    )
    normalized_membership = require_commit_fingerprint(
        membership_root,
        "commit window membership_root",
    )
    window_policy = commit_policy.commit_window
    absolute_deadline = checked_add(
        current,
        window_policy.deliberation_deadline_steps,
    )
    absolute_run_deadline = checked_add(
        current,
        window_policy.run_deadline_steps,
    )
    normalized_issuer = require_commit_text(
        issuer_id,
        "commit window issuer_id",
    )
    normalized_provenance = require_commit_text(
        provenance,
        "commit window provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "commit window trace_event_id",
    )
    authority_key = _commit_window_authority_key(bindings)
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": normalized_issuer,
            "membership_root": normalized_membership,
            "provenance": normalized_provenance,
            "risk_assessment_root": normalized_risk,
            "threshold_root": threshold_ref,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-commit-window-base-v1",
        profile=str(bindings["profile"]),
    )
    assessment_refs: tuple[str, ...] = ()
    with _COMMIT_WINDOW_REGISTRY_LOCK:
        cursor = _COMMIT_WINDOW_CURSORS.get(authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "commit window authority already has a different base"
                )
            current_state = cursor.current_state
            if (
                type(current_state) is not CommitWindowState
                or not commit_window_state_is_current(current_state)
            ):
                raise GovernanceError(
                    "commit window current state is unavailable; "
                    "reinitialization is forbidden"
                )
            return current_state

        cursor = _CommitWindowCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
            chain_id=authority_key,
        )
        state = CommitWindowState(
            chain_id=authority_key,
            profile=str(bindings["profile"]),
            assurance=bindings["assurance"],
            manifest_root=str(bindings["manifest_root"]),
            commit_policy_root=str(bindings["commit_policy_root"]),
            protocol_id=str(bindings["protocol_id"]),
            run_id=str(bindings["run_id"]),
            target=str(bindings["target"]),
            epoch=int(bindings["epoch"]),
            revision=0,
            previous_state_fingerprint="",
            risk_assessment_root=normalized_risk,
            membership_root=normalized_membership,
            threshold_root=threshold_ref,
            minimum_stability_steps=max(
                window_policy.minimum_stability_steps,
                threshold_stability,
            ),
            risk_chain_state_root="",
            risk_policy_root="",
            membership_snapshot_root="",
            membership_epoch_state_root="",
            support_replay_state_root="",
            support_replay_root="",
            collective_evidence_root="",
            collective_challenge_root="",
            collective_lease_root="",
            candidate_evidence_root="",
            candidate_challenge_root="",
            candidate_lease_root="",
            stop_resolution_root="",
            permission_root="",
            assessment_replay_state_ref="",
            assessment_replay_root="",
            initialized_at_step=current,
            last_evaluated_step=current,
            absolute_deadline_step=absolute_deadline,
            absolute_run_deadline_step=absolute_run_deadline,
            remaining_reset_budget=window_policy.maximum_leader_resets,
            remaining_epoch_restart_budget=window_policy.maximum_epoch_restarts,
            ordered_assessment_refs=assessment_refs,
            window_root=_window_root(
                assessment_refs,
                profile=str(bindings["profile"]),
                run_id=str(bindings["run_id"]),
                epoch=int(bindings["epoch"]),
            ),
            issuer_id=normalized_issuer,
            authority=authority,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_commit_window_state(state, cursor=cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = commit_window_state_fingerprint(state)
        _COMMIT_WINDOW_CURSORS[authority_key] = cursor
        return state


def advance_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
) -> CommitWindowState:
    """Advance an unsealed assessment window.

    Once a local receipt has sealed a stable head, ordinary advance is
    forbidden.  Callers must use :func:`reset_commit_window_state`, making the
    loss of a proof-visible seal explicit and budgeted.
    """

    return _transition_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
        explicit_unseal=False,
    )


def reset_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
) -> CommitWindowState:
    """Explicitly invalidate a sealed window and begin a fresh stability run.

    This transition always consumes one leader-reset unit, even when the next
    assessment happens to reproduce the old roots.  It is the only non-epoch
    route out of a current sealed window and therefore prevents a late proof
    from being silently reused after heartbeat, head, leader or gate changes.
    """

    return _transition_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
        explicit_unseal=True,
    )


def _transition_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
    explicit_unseal: bool,
) -> CommitWindowState:
    if not commit_window_state_is_authoritative(state):
        raise GovernanceError("commit window state is not governance-issued")
    current = require_commit_step(current_step, "commit window current_step")
    if current <= state.last_evaluated_step:
        raise GovernanceError("commit window step must advance monotonically")
    if current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("commit window cannot advance at or after its deadline")
    view = _authoritative_commit_assessment_view(
        assessment,
        current_step=current,
    )
    bindings = _normalized_window_bindings(
        profile=view["profile"],
        assurance=view["assurance"],
        manifest_root=view["manifest_root"],
        commit_policy_root=view["commit_policy_root"],
        protocol_id=view["protocol_id"],
        run_id=view["run_id"],
        target=view["target"],
        epoch=view["epoch"],
        field_name="commit assessment window",
    )
    _validate_window_chain_scope(state, bindings)
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=view["risk_assessment_root"],
        current_step=current,
    )
    if threshold_ref != view["threshold_root"]:
        raise GovernanceError(
            "commit assessment threshold does not match the canonical snapshot"
        )
    ready = bool(view["ready"])
    leader = str(view["leader_candidate_id"]) if ready else ""
    assessment_ref = str(view["assessment_ref"])

    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    state_is_current = commit_window_state_is_current(state)
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        has_current_seal = bool(
            cursor.current_seal is not None
            and commit_window_seal_is_current(cursor.current_seal)
        )
    if has_current_seal and not explicit_unseal:
        raise GovernanceError(
            "sealed commit window requires an explicit reset/unseal transition"
        )
    if explicit_unseal and state_is_current and not has_current_seal:
        raise GovernanceError(
            "explicit reset/unseal requires a current sealed window"
        )

    reset_reason = _window_reset_reason(
        state,
        current_step=current,
        ready=ready,
        leader_candidate_id=leader,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        risk_assessment_root=str(view["risk_assessment_root"]),
        membership_root=str(view["membership_root"]),
        threshold_root=threshold_ref,
    )
    if explicit_unseal and reset_reason == "none":
        reset_reason = "explicit_unseal"
    consumes_reset = bool(
        explicit_unseal
        or (reset_reason != "none" and state.window_count > 0)
    )
    remaining_reset_budget = state.remaining_reset_budget
    exhausted = state.reset_budget_exhausted
    if consumes_reset:
        if remaining_reset_budget == 0:
            exhausted = True
        else:
            remaining_reset_budget -= 1

    if not ready or exhausted:
        next_count = 0
        next_leader = ""
        assessment_refs: tuple[str, ...] = ()
        next_ready = False
    elif reset_reason != "none" or not state.last_ready:
        next_count = 1
        next_leader = leader
        assessment_refs = (assessment_ref,)
        next_ready = True
    else:
        next_count = state.window_count + 1
        next_leader = leader
        assessment_refs = (*state.ordered_assessment_refs, assessment_ref)
        next_ready = True

    parent_fingerprint = commit_window_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "assessment_ref": assessment_ref,
            "current_step": current,
            "explicit_unseal": explicit_unseal,
            "parent_state_fingerprint": parent_fingerprint,
            "policy_root": bindings["commit_policy_root"],
            "threshold_root": threshold_ref,
        },
        schema="pheroos-commit-window-advance-request-v1",
        profile=state.profile,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        locked_seal = cursor.current_seal
        locked_sealed = bool(
            locked_seal is not None
            and commit_window_seal_is_current(locked_seal)
        )
        if locked_sealed and not explicit_unseal:
            raise GovernanceError(
                "sealed commit window requires an explicit reset/unseal transition"
            )
        if explicit_unseal and not locked_sealed:
            raise GovernanceError(
                "explicit reset/unseal lost its current seal authority"
            )
    next_state = CommitWindowState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        revision=state.revision + 1,
        previous_state_fingerprint=parent_fingerprint,
        risk_assessment_root=str(view["risk_assessment_root"]),
        membership_root=str(view["membership_root"]),
        threshold_root=threshold_ref,
        minimum_stability_steps=max(
            state.minimum_stability_steps,
            commit_policy.commit_window.minimum_stability_steps,
            threshold_stability,
        ),
        risk_chain_state_root=str(view["risk_chain_state_root"]),
        risk_policy_root=str(view["risk_policy_root"]),
        membership_snapshot_root=str(view["membership_snapshot_root"]),
        membership_epoch_state_root=str(view["membership_epoch_state_root"]),
        support_replay_state_root=str(view["support_replay_state_root"]),
        support_replay_root=str(view["support_replay_root"]),
        collective_evidence_root=str(view["collective_evidence_root"]),
        collective_challenge_root=str(view["collective_challenge_root"]),
        collective_lease_root=str(view["collective_lease_root"]),
        candidate_evidence_root=str(view["candidate_evidence_root"]),
        candidate_challenge_root=str(view["candidate_challenge_root"]),
        candidate_lease_root=str(view["candidate_lease_root"]),
        stop_resolution_root=str(view["stop_resolution_root"]),
        permission_root=str(view["permission_root"]),
        assessment_replay_state_ref=str(view["replay_state_ref"]),
        assessment_replay_root=str(view["replay_root"]),
        initialized_at_step=state.initialized_at_step,
        last_evaluated_step=current,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=remaining_reset_budget,
        remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
        leader_candidate_id=next_leader,
        window_count=next_count,
        ordered_assessment_refs=assessment_refs,
        window_root=_window_root(
            assessment_refs,
            profile=state.profile,
            run_id=state.run_id,
            epoch=state.epoch,
        ),
        last_ready=next_ready,
        last_assessment_ref=assessment_ref,
        last_context_ref=str(view["context_ref"]),
        last_assessment_status=str(view["status"]),
        last_assessment_reason_codes=tuple(view["reason_codes"]),
        reset_reason=(
            "reset_budget_exhausted" if exhausted else reset_reason
        ),
        reset_budget_exhausted=exhausted,
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        locked_seal = cursor.current_seal
        locked_sealed = bool(
            locked_seal is not None
            and commit_window_seal_is_current(locked_seal)
        )
        if locked_sealed and not explicit_unseal:
            raise GovernanceError(
                "sealed commit window requires an explicit reset/unseal transition"
            )
        if explicit_unseal and not locked_sealed:
            raise GovernanceError(
                "explicit reset/unseal lost its current seal authority"
            )
        next_state = _issue_commit_window_state(next_state, cursor=cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = commit_window_state_fingerprint(
            next_state
        )
        if explicit_unseal:
            cursor.current_seal = None
            cursor.current_seal_fingerprint = ""
            cursor.seal_generation += 1
        cursor.current_progress = None
        cursor.current_progress_fingerprint = ""
        cursor.transitions[parent_fingerprint] = (
            request_fingerprint,
            next_state,
        )
        return next_state


def restart_commit_window_epoch(
    state: CommitWindowState,
    *,
    new_epoch: int,
    current_step: int,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    membership_root: str,
) -> CommitWindowState:
    if not commit_window_state_is_authoritative(state):
        raise GovernanceError("commit window state is not governance-issued")
    current = require_commit_step(current_step, "epoch restart current_step")
    epoch = require_commit_step(new_epoch, "epoch restart new_epoch")
    if epoch <= state.epoch:
        raise GovernanceError("epoch restart must advance the epoch")
    if current <= state.last_evaluated_step:
        raise GovernanceError("epoch restart step must advance monotonically")
    if current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("epoch restart cannot extend the deliberation deadline")
    if state.remaining_epoch_restart_budget == 0:
        raise GovernanceError("epoch restart budget is exhausted")
    snapshot_bindings = _threshold_snapshot_bindings(threshold_snapshot)
    bindings = _normalized_window_bindings(
        profile=snapshot_bindings["profile"],
        assurance=snapshot_bindings["assurance"],
        manifest_root=snapshot_bindings["manifest_root"],
        commit_policy_root=snapshot_bindings["commit_policy_root"],
        protocol_id=snapshot_bindings["protocol_id"],
        run_id=snapshot_bindings["run_id"],
        target=snapshot_bindings["target"],
        epoch=snapshot_bindings["epoch"],
        field_name="commit window epoch restart",
    )
    if int(bindings["epoch"]) != epoch:
        raise GovernanceError("epoch restart threshold epoch mismatch")
    _validate_window_chain_scope(state, bindings, allow_epoch_change=True)
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=snapshot_bindings["risk_assessment_root"],
        current_step=current,
    )
    normalized_membership = require_commit_fingerprint(
        membership_root,
        "epoch restart membership_root",
    )
    parent_fingerprint = commit_window_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "current_step": current,
            "epoch": epoch,
            "membership_root": normalized_membership,
            "parent_state_fingerprint": parent_fingerprint,
            "policy_root": bindings["commit_policy_root"],
            "threshold_root": threshold_ref,
        },
        schema="pheroos-commit-window-epoch-restart-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        invalidates_seal = bool(
            cursor.current_seal is not None
            and commit_window_seal_is_current(cursor.current_seal)
        )
        if invalidates_seal and state.remaining_reset_budget == 0:
            raise GovernanceError(
                "sealed epoch restart requires remaining reset budget"
            )
    assessment_refs: tuple[str, ...] = ()
    restarted = CommitWindowState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=epoch,
        revision=state.revision + 1,
        previous_state_fingerprint=parent_fingerprint,
        risk_assessment_root=str(snapshot_bindings["risk_assessment_root"]),
        membership_root=normalized_membership,
        threshold_root=threshold_ref,
        minimum_stability_steps=max(
            state.minimum_stability_steps,
            commit_policy.commit_window.minimum_stability_steps,
            threshold_stability,
        ),
        risk_chain_state_root="",
        risk_policy_root="",
        membership_snapshot_root="",
        membership_epoch_state_root="",
        support_replay_state_root="",
        support_replay_root="",
        collective_evidence_root="",
        collective_challenge_root="",
        collective_lease_root="",
        candidate_evidence_root="",
        candidate_challenge_root="",
        candidate_lease_root="",
        stop_resolution_root="",
        permission_root="",
        assessment_replay_state_ref="",
        assessment_replay_root="",
        initialized_at_step=state.initialized_at_step,
        last_evaluated_step=current,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=(
            state.remaining_reset_budget - 1
            if invalidates_seal
            else state.remaining_reset_budget
        ),
        remaining_epoch_restart_budget=(
            state.remaining_epoch_restart_budget - 1
        ),
        ordered_assessment_refs=assessment_refs,
        window_root=_window_root(
            assessment_refs,
            profile=state.profile,
            run_id=state.run_id,
            epoch=epoch,
        ),
        reset_reason="epoch_change",
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        restarted = _issue_commit_window_state(restarted, cursor=cursor)
        cursor.current_state = restarted
        cursor.current_state_fingerprint = commit_window_state_fingerprint(
            restarted
        )
        if invalidates_seal:
            cursor.current_seal = None
            cursor.current_seal_fingerprint = ""
            cursor.seal_generation += 1
        cursor.current_progress = None
        cursor.current_progress_fingerprint = ""
        cursor.transitions[parent_fingerprint] = (
            request_fingerprint,
            restarted,
        )
        return restarted


def commit_window_ready(
    state: CommitWindowState,
) -> bool:
    if not commit_window_state_is_current(state):
        return False
    try:
        return bool(
            state.last_ready
            and not state.reset_budget_exhausted
            and state.window_count >= state.minimum_stability_steps
            and state.last_evaluated_step
            < min(state.absolute_deadline_step, state.absolute_run_deadline_step)
        )
    except (GovernanceError, AttributeError):
        return False


def _seal_commit_window_from_local_receipt(
    state: CommitWindowState,
    receipt: object,
) -> CommitWindowSeal:
    """Atomically register the one receipt-backed seal for a window head.

    This is an adapter boundary used by :mod:`pheroos.governance.certificate`
    after it has registered an authoritative ``LocalCommitReceipt``.  The
    delayed import avoids defining a second receipt type in this module.
    """

    from pheroos.governance.certificate import (
        LocalCommitReceipt,
        local_commit_receipt_fingerprint,
        local_commit_receipt_is_authoritative,
    )

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit window seal requires the current window head")
    if not commit_window_ready(state):
        raise GovernanceError("commit window seal requires a stable ready window")
    if (
        type(receipt) is not LocalCommitReceipt
        or not local_commit_receipt_is_authoritative(receipt)
    ):
        raise GovernanceError("commit window seal requires an authoritative receipt")
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    state_ref = commit_window_state_fingerprint(state)
    common = (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    )
    for name in common:
        if getattr(receipt, name) != getattr(state, name):
            raise GovernanceError(f"commit window seal receipt {name} mismatch")
    expected = {
        "candidate_id": state.leader_candidate_id,
        "context_root": state.last_context_ref,
        "assessment_root": state.last_assessment_ref,
        "window_state_root": state_ref,
        "window_root": state.window_root,
        "risk_assessment_root": state.risk_assessment_root,
        "risk_chain_state_root": state.risk_chain_state_root,
        "risk_policy_root": state.risk_policy_root,
        "membership_root": state.membership_root,
        "membership_snapshot_root": state.membership_snapshot_root,
        "membership_epoch_state_root": state.membership_epoch_state_root,
        "threshold_root": state.threshold_root,
        "replay_state_root": state.assessment_replay_state_ref,
        "replay_root": state.assessment_replay_root,
        "support_replay_state_root": state.support_replay_state_root,
        "support_replay_root": state.support_replay_root,
        "evidence_root": state.collective_evidence_root,
        "challenge_root": state.collective_challenge_root,
        "lease_root": state.collective_lease_root,
        "candidate_evidence_root": state.candidate_evidence_root,
        "candidate_challenge_root": state.candidate_challenge_root,
        "candidate_lease_root": state.candidate_lease_root,
        "stop_resolution_root": state.stop_resolution_root,
        "permission_root": state.permission_root,
        "issued_at_step": state.last_evaluated_step,
    }
    for name, expected_value in expected.items():
        if getattr(receipt, name) != expected_value:
            raise GovernanceError(
                f"commit window seal receipt {name} lineage mismatch"
            )

    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window seal cursor is invalid")
    request_ref = commit_payload_fingerprint(
        {
            "receipt_ref": receipt_ref,
            "window_state_ref": state_ref,
        },
        schema="pheroos-commit-window-seal-request-v1",
        profile=state.profile,
    )
    with cursor.lock:
        if (
            cursor.current_state is not state
            or cursor.current_state_fingerprint != state_ref
        ):
            raise GovernanceError("commit window seal state became stale")
        existing = cursor.current_seal
        if existing is not None:
            cached = cursor.seal_requests.get(receipt_ref)
            if (
                cached is not None
                and cached[0] == request_ref
                and cached[1] is existing
                and commit_window_seal_is_current(existing)
            ):
                return existing
            raise GovernanceError(
                "commit window is already sealed by a different local receipt"
            )
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        seal = CommitWindowSeal(
            chain_id=state.chain_id,
            generation=cursor.seal_generation,
            profile=state.profile,
            assurance=state.assurance,
            manifest_root=state.manifest_root,
            commit_policy_root=state.commit_policy_root,
            protocol_id=state.protocol_id,
            run_id=state.run_id,
            target=state.target,
            epoch=state.epoch,
            receipt_ref=receipt_ref,
            candidate_id=receipt.candidate_id,
            claim_fingerprint=receipt.claim_fingerprint,
            output_payload_fingerprint=receipt.output_payload_fingerprint,
            context_ref=receipt.context_root,
            assessment_ref=receipt.assessment_root,
            window_state_ref=receipt.window_state_root,
            window_root=receipt.window_root,
            risk_assessment_root=receipt.risk_assessment_root,
            risk_chain_state_root=receipt.risk_chain_state_root,
            risk_policy_root=receipt.risk_policy_root,
            membership_root=receipt.membership_root,
            membership_snapshot_root=receipt.membership_snapshot_root,
            membership_epoch_state_root=receipt.membership_epoch_state_root,
            threshold_root=receipt.threshold_root,
            replay_state_ref=receipt.replay_state_root,
            replay_root=receipt.replay_root,
            support_replay_state_root=receipt.support_replay_state_root,
            support_replay_root=receipt.support_replay_root,
            collective_evidence_root=receipt.evidence_root,
            collective_challenge_root=receipt.challenge_root,
            collective_lease_root=receipt.lease_root,
            candidate_evidence_root=receipt.candidate_evidence_root,
            candidate_challenge_root=receipt.candidate_challenge_root,
            candidate_lease_root=receipt.candidate_lease_root,
            stop_resolution_root=receipt.stop_resolution_root,
            permission_root=receipt.permission_root,
            sealed_at_step=receipt.issued_at_step,
            absolute_deadline_step=state.absolute_deadline_step,
            absolute_run_deadline_step=state.absolute_run_deadline_step,
            remaining_reset_budget=state.remaining_reset_budget,
            remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
            issuer_id=receipt.issuer_id,
            authority=receipt.authority,
            provenance=receipt.provenance,
            trace_event_id=receipt.trace_event_id,
        )
        object.__setattr__(
            seal,
            "_issuance",
            (
                _COMMIT_WINDOW_SEAL_ISSUANCE,
                commit_window_seal_fingerprint(seal),
            ),
        )
        object.__setattr__(seal, "_cursor", cursor)
        cursor.current_seal = seal
        cursor.current_seal_fingerprint = commit_window_seal_fingerprint(seal)
        cursor.seal_requests[receipt_ref] = (request_ref, seal)
        return seal


def commit_window_seal_for_state(
    state: CommitWindowState,
) -> CommitWindowSeal | None:
    if not commit_window_state_is_current(state):
        return None
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        return None
    with cursor.lock:
        seal = cursor.current_seal
        return seal if commit_window_seal_is_current(seal) else None


def commit_window_seal_is_authoritative(seal: object) -> bool:
    if type(seal) is not CommitWindowSeal:
        return False
    try:
        _validate_commit_window_seal(seal)
        issuance = seal._issuance
        cursor = seal._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_WINDOW_SEAL_ISSUANCE
            and issuance[1] == commit_window_seal_fingerprint(seal)
            and type(cursor) is _CommitWindowCursor
            and cursor.chain_id == seal.chain_id
        )
    except Exception:
        return False


def commit_window_seal_is_current(seal: object) -> bool:
    if not commit_window_seal_is_authoritative(seal):
        return False
    assert type(seal) is CommitWindowSeal
    cursor = seal._cursor
    assert type(cursor) is _CommitWindowCursor
    try:
        with cursor.lock:
            return bool(
                cursor.current_seal is seal
                and cursor.current_seal_fingerprint
                == commit_window_seal_fingerprint(seal)
                and cursor.current_state_fingerprint == seal.window_state_ref
                and cursor.seal_generation == seal.generation
            )
    except Exception:
        return False


def commit_window_seal_matches_receipt(
    state: CommitWindowState,
    receipt: object,
) -> bool:
    """Return whether ``receipt`` is the unique current seal authority."""

    try:
        from pheroos.governance.certificate import (
            LocalCommitReceipt,
            local_commit_receipt_fingerprint,
            local_commit_receipt_is_authoritative,
        )

        seal = commit_window_seal_for_state(state)
        return bool(
            seal is not None
            and type(receipt) is LocalCommitReceipt
            and local_commit_receipt_is_authoritative(receipt)
            and seal.receipt_ref == local_commit_receipt_fingerprint(receipt)
            and seal.output_payload_fingerprint
            == receipt.output_payload_fingerprint
            and seal.claim_fingerprint == receipt.claim_fingerprint
        )
    except Exception:
        return False


def commit_window_seal_payload(seal: CommitWindowSeal) -> dict[str, object]:
    if type(seal) is not CommitWindowSeal:
        raise GovernanceError("commit window seal must use the canonical record")
    _validate_commit_window_seal(seal)
    return {
        name: getattr(seal, name)
        for name in seal.__dataclass_fields__
        if not name.startswith("_")
    }


def commit_window_seal_fingerprint(seal: CommitWindowSeal) -> str:
    return commit_payload_fingerprint(
        commit_window_seal_payload(seal),
        schema="pheroos-commit-window-seal-v1",
        profile=seal.profile,
    )


def _issue_commit_finality_verification(
    **values: object,
) -> CommitFinalityVerification:
    """Private adapter target for certificate and receipt verifiers."""

    verification = CommitFinalityVerification(**values)  # type: ignore[arg-type]
    object.__setattr__(
        verification,
        "_issuance",
        (
            _COMMIT_FINALITY_VERIFICATION_ISSUANCE,
            commit_finality_verification_fingerprint(verification),
        ),
    )
    return verification


def commit_finality_verification_payload(
    value: CommitFinalityVerification,
) -> dict[str, object]:
    if type(value) is not CommitFinalityVerification:
        raise GovernanceError(
            "commit finality verification must use the canonical record"
        )
    _validate_commit_finality_verification(value)
    return {
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if not name.startswith("_")
    }


def commit_finality_verification_fingerprint(
    value: CommitFinalityVerification,
) -> str:
    return commit_payload_fingerprint(
        commit_finality_verification_payload(value),
        schema="pheroos-commit-finality-verification-v1",
        profile=value.profile,
    )


def commit_finality_verification_is_authoritative(value: object) -> bool:
    if type(value) is not CommitFinalityVerification:
        return False
    try:
        issuance = value._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_FINALITY_VERIFICATION_ISSUANCE
            and issuance[1] == commit_finality_verification_fingerprint(value)
        )
    except Exception:
        return False


def issue_commit_liveness_input(
    state: CommitWindowState,
    *,
    assessment: object | None,
    replay_state: CommitReplayState,
    risk_chain_state: object | None,
    risk_assessment: object | None = None,
    threshold_snapshot: object | None = None,
    membership_snapshot: object | None = None,
    membership_epoch_state: object | None,
    support_replay_state: object | None,
    commit_policy: CollectiveCommitPolicy | None = None,
    previous_progress: DecisionProgress | None = None,
    current_step: int,
    finality_status: CommitFinalityStatus,
    finality_verification: CommitFinalityVerification | None = None,
    certificate_ref: str = "",
    invalid_reason_codes: Sequence[str] = (),
    safety_violation_reason_codes: Sequence[str] = (),
    blocked_reason_codes: Sequence[str] = (),
    finality_reason_codes: Sequence[str] = (),
    next_required_inputs: Sequence[str] = (),
    input_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitLivenessInput:
    """Qualify temporal facts without accepting a caller readiness boolean."""

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit liveness input requires governance authority")
    current = require_commit_step(current_step, "commit liveness current_step")
    if current < state.last_evaluated_step:
        raise GovernanceError("commit liveness step cannot precede the window head")
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit liveness window cursor is invalid")
    deadline_reached = current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    seal = commit_window_seal_for_state(state)
    seal_ref = (
        commit_window_seal_fingerprint(seal) if seal is not None else ""
    )
    sealed_at_step = seal.sealed_at_step if seal is not None else 0
    previous_progress_ref = ""
    heartbeat_sequence = 0
    heartbeat_continuous = True
    if current == state.last_evaluated_step:
        if previous_progress is not None:
            raise GovernanceError(
                "initial liveness step cannot consume a previous heartbeat"
            )
    elif seal is not None:
        if previous_progress is None:
            if not deadline_reached:
                raise GovernanceError(
                    "late finality requires the authoritative previous heartbeat"
                )
            heartbeat_continuous = False
        else:
            if not decision_progress_is_authoritative(previous_progress):
                raise GovernanceError(
                    "late finality previous heartbeat is not authoritative"
                )
            with cursor.lock:
                if cursor.current_progress is not previous_progress:
                    raise GovernanceError(
                        "late finality previous heartbeat is not the current head"
                    )
            if previous_progress.current_step + 1 != current:
                raise GovernanceError(
                    "late finality heartbeat must advance exactly one logical step"
                )
            if (
                not previous_progress.sealed_window
                or not previous_progress.heartbeat_continuous
                or previous_progress.seal_ref != seal_ref
                or previous_progress.sealed_at_step != seal.sealed_at_step
                or previous_progress.window_state_ref != seal.window_state_ref
                or previous_progress.window_root != seal.window_root
            ):
                raise GovernanceError(
                    "late finality previous heartbeat does not preserve the seal"
                )
            previous_progress_ref = decision_progress_fingerprint(
                previous_progress
            )
            heartbeat_sequence = previous_progress.heartbeat_sequence + 1
    elif (
        current > state.last_evaluated_step
        and commit_window_ready(state)
        and not deadline_reached
    ):
        raise GovernanceError(
            "stable window requires a same-step local receipt seal"
        )
    elif previous_progress is not None:
        raise GovernanceError(
            "unsealed liveness cannot consume a sealed-window heartbeat"
        )
    if not commit_replay_state_matches(
        replay_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        current_step=current,
    ):
        raise GovernanceError("commit liveness replay head is not authoritative")

    if assessment is None:
        if state.last_assessment_ref:
            raise GovernanceError(
                "commit liveness must consume the window head assessment"
            )
        assessment_ref = ""
        context_ref = ""
        assessment_status = ""
        leader = ""
        ready = False
        assessment_reasons: tuple[str, ...] = ()
    else:
        view = _authoritative_commit_assessment_view(assessment)
        _validate_assessment_matches_window_head(state, view)
        if (
            commit_replay_state_fingerprint(replay_state)
            != state.assessment_replay_state_ref
            or replay_state.receipt_root != state.assessment_replay_root
        ):
            raise GovernanceError(
                "commit liveness replay head changed after the assessment"
            )
        _validate_liveness_current_authority_heads(
            state,
            commit_policy=commit_policy,
            risk_chain_state=risk_chain_state,
            risk_assessment=risk_assessment,
            threshold_snapshot=threshold_snapshot,
            membership_snapshot=membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            support_replay_state=support_replay_state,
            current_step=current,
            require_fresh_snapshot=bool(
                seal is not None and current > seal.sealed_at_step
                and not deadline_reached
            ),
        )
        assessment_ref = str(view["assessment_ref"])
        context_ref = str(view["context_ref"])
        assessment_status = str(view["status"])
        leader = str(view["leader_candidate_id"])
        ready = bool(view["ready"])
        assessment_reasons = tuple(view["reason_codes"])

    if type(finality_status) is not CommitFinalityStatus:
        raise GovernanceError("commit liveness finality status is invalid")
    if finality_status is CommitFinalityStatus.VERIFIED:
        if not commit_finality_verification_is_authoritative(
            finality_verification
        ):
            raise GovernanceError(
                "verified finality requires an authoritative typed verification"
            )
        assert finality_verification is not None
        _validate_finality_verification_matches_window(
            finality_verification,
            state=state,
            seal=seal,
            current_step=current,
        )
        if seal is None:
            raise GovernanceError(
                "verified finality requires the current receipt-backed seal"
            )
        if (
            state.assurance is CommitAssurance.EVIDENCE_BOUND
            and (
                current != seal.sealed_at_step
                or finality_verification.certificate_ref != seal.receipt_ref
            )
        ):
            raise GovernanceError(
                "evidence-bound finality requires its same-step local receipt"
            )
        if certificate_ref:
            raise GovernanceError(
                "verified finality cannot accept a bare certificate reference"
            )
        certificate = finality_verification.certificate_ref
        finality_verification_ref = (
            commit_finality_verification_fingerprint(finality_verification)
        )
    elif finality_verification is not None:
        raise GovernanceError(
            "non-verified finality cannot carry a finality verification"
        )
    elif certificate_ref:
        raise GovernanceError(
            "commit liveness cannot accept a bare certificate reference"
        )
    else:
        certificate = ""
        finality_verification_ref = ""

    value = CommitLivenessInput(
        input_id=require_commit_text(input_id, "commit liveness input_id"),
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=current,
        deadline_reached=deadline_reached,
        context_ref=context_ref,
        assessment_ref=assessment_ref,
        assessment_status=assessment_status,
        leader_candidate_id=leader,
        leader_ready_for_stability=ready,
        assessment_reason_codes=assessment_reasons,
        replay_state_ref=commit_replay_state_fingerprint(replay_state),
        replay_root=replay_state.receipt_root,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
        support_replay_state_root=state.support_replay_state_root,
        support_replay_root=state.support_replay_root,
        collective_evidence_root=state.collective_evidence_root,
        collective_challenge_root=state.collective_challenge_root,
        collective_lease_root=state.collective_lease_root,
        candidate_evidence_root=state.candidate_evidence_root,
        candidate_challenge_root=state.candidate_challenge_root,
        candidate_lease_root=state.candidate_lease_root,
        stop_resolution_root=state.stop_resolution_root,
        permission_root=state.permission_root,
        window_state_ref=commit_window_state_fingerprint(state),
        sealed_window=seal is not None,
        seal_ref=seal_ref,
        sealed_at_step=sealed_at_step,
        heartbeat_continuous=heartbeat_continuous,
        heartbeat_sequence=heartbeat_sequence,
        previous_progress_ref=previous_progress_ref,
        finality_status=finality_status,
        certificate_ref=certificate,
        finality_verification_ref=finality_verification_ref,
        invalid_reason_codes=tuple(invalid_reason_codes),
        safety_violation_reason_codes=tuple(
            safety_violation_reason_codes
        ),
        blocked_reason_codes=tuple(blocked_reason_codes),
        finality_reason_codes=tuple(finality_reason_codes),
        next_required_inputs=tuple(next_required_inputs),
        issuer_id=require_commit_text(issuer_id, "commit liveness issuer_id"),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "commit liveness provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit liveness trace_event_id",
        ),
    )
    object.__setattr__(
        value,
        "_issuance",
        (_COMMIT_LIVENESS_INPUT_ISSUANCE, commit_liveness_input_fingerprint(value)),
    )
    object.__setattr__(
        value,
        "_authority_heads",
        (
            replay_state,
            risk_chain_state,
            risk_assessment,
            threshold_snapshot,
            membership_snapshot,
            membership_epoch_state,
            support_replay_state,
            commit_policy,
        ),
    )
    request_ref = commit_liveness_input_fingerprint(value)
    cache_key = value.input_id
    with cursor.lock:
        cached = cursor.liveness_inputs.get(cache_key)
        if cached is not None:
            if cached[0] == request_ref:
                return cached[1]
            raise GovernanceError("commit liveness input id would fork")
        cursor.liveness_inputs[cache_key] = (request_ref, value)
        return value


def reduce_commit_liveness(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
) -> DecisionProgress | DecisionOutcome:
    """Reduce one logical step to issued progress or a deliverable terminal outcome."""

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if not _commit_liveness_input_was_issued(liveness_input):
        raise GovernanceError("commit liveness input is not governance-issued")
    _validate_liveness_input_matches_window(state, liveness_input)
    bindings = _normalized_window_bindings(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit liveness",
    )
    _validate_bound_commit_policy(commit_policy, bindings)

    current = liveness_input.current_step
    deadline_reached = current >= state.absolute_deadline_step
    run_deadline_reached = current >= state.absolute_run_deadline_step
    effective_deadline_reached = deadline_reached or run_deadline_reached
    assessment_safety = (
        liveness_input.assessment_status == "safety_violation"
    )
    hard_denial_codes = {
        "stop_blocked",
        "commit_permission_denied",
    }
    unresolved_authority_codes = {
        "stop_resolution_unresolved",
        "commit_permission_unresolved",
    }
    derived_blocked = bool(
        hard_denial_codes.intersection(liveness_input.assessment_reason_codes)
        or (
            effective_deadline_reached
            and unresolved_authority_codes.intersection(
                liveness_input.assessment_reason_codes
            )
        )
    )
    finality_satisfied = _finality_satisfied(liveness_input)
    before_deadline = not effective_deadline_reached
    assurance_step_valid = bool(
        (
            state.assurance is CommitAssurance.EVIDENCE_BOUND
            and current == state.last_evaluated_step
            and current == liveness_input.sealed_at_step
        )
        or (
            state.assurance
            in {CommitAssurance.CERTIFIED, CommitAssurance.DISTRIBUTED}
            and current >= liveness_input.sealed_at_step
        )
    )
    evidence_ready = bool(
        state.assurance is not CommitAssurance.ADVISORY
        and before_deadline
        and commit_window_ready(state)
        and liveness_input.sealed_window
        and liveness_input.heartbeat_continuous
        and assurance_step_valid
        and liveness_input.leader_ready_for_stability
        and finality_satisfied
    )
    finality_deadline_unavailable = _finality_unavailable_at_deadline(
        assurance=state.assurance,
        finality_status=liveness_input.finality_status,
        stability_satisfied=bool(
            commit_window_ready(state)
            and liveness_input.sealed_window
            and liveness_input.heartbeat_continuous
            and liveness_input.leader_ready_for_stability
        ),
        deadline_reached=effective_deadline_reached,
    )
    outcome_kind = select_terminal_outcome_kind(
        invalid=bool(liveness_input.invalid_reason_codes),
        safety_violation=bool(
            liveness_input.safety_violation_reason_codes
            or assessment_safety
            or liveness_input.finality_status is CommitFinalityStatus.CONFLICT
        ),
        blocked=bool(liveness_input.blocked_reason_codes or derived_blocked),
        evidence_commit_ready=evidence_ready,
        finality_unavailable=finality_deadline_unavailable,
        deadline_reached=effective_deadline_reached,
        deadline_outcome=commit_policy.terminal_outcome.deadline_outcome,
    )

    request_fingerprint = commit_payload_fingerprint(
        {
            "liveness_input": commit_liveness_input_fingerprint(liveness_input),
            "outcome_kind": outcome_kind.value if outcome_kind is not None else "",
            "window_state": liveness_input.window_state_ref,
        },
        schema="pheroos-commit-liveness-reduction-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    cache_key = (liveness_input.window_state_ref, current)
    with cursor.lock:
        cached = cursor.liveness_results.get(cache_key)
        if cached is not None:
            if cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit liveness decision would fork")
        if not _liveness_authority_heads_are_current(liveness_input):
            raise GovernanceError(
                "commit liveness authority heads are no longer current"
            )
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window already has a terminal outcome")

        if outcome_kind is None:
            result: DecisionProgress | DecisionOutcome = _progress_from_liveness(
                state,
                liveness_input,
            )
            cursor.current_progress = result
            cursor.current_progress_fingerprint = decision_progress_fingerprint(
                result
            )
        else:
            result = _outcome_from_liveness(
                state,
                commit_policy=commit_policy,
                liveness_input=liveness_input,
                kind=outcome_kind,
                deadline_reached=effective_deadline_reached,
                run_deadline_reached=run_deadline_reached,
                derived_blocked=derived_blocked,
            )
            cursor.terminal_result = result
            cursor.current_progress = None
            cursor.current_progress_fingerprint = ""
        cursor.liveness_results[cache_key] = (request_fingerprint, result)
        return result


def initialize_commit_replay_state(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitReplayState:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit replay initialization requires governance authority")
    normalized_profile = require_commit_profile(profile, "commit replay profile")
    if type(assurance) is not CommitAssurance:
        raise GovernanceError("commit replay assurance is invalid")
    _validate_profile_assurance(
        normalized_profile,
        assurance,
        field_name="commit replay",
    )
    normalized_manifest = require_commit_fingerprint(
        manifest_root,
        "commit replay manifest_root",
    )
    normalized_policy = require_commit_fingerprint(
        commit_policy_root,
        "commit replay commit_policy_root",
    )
    normalized_protocol = require_commit_text(
        protocol_id,
        "commit replay protocol_id",
    )
    normalized_run = require_commit_text(run_id, "commit replay run_id")
    current = require_commit_step(current_step, "commit replay current_step")
    normalized_issuer = require_commit_text(issuer_id, "commit replay issuer_id")
    normalized_provenance = require_commit_text(
        provenance,
        "commit replay provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "commit replay trace_event_id",
    )
    authority_key = commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": normalized_policy,
            "manifest_root": normalized_manifest,
            "profile": normalized_profile,
            "protocol_id": normalized_protocol,
            "run_id": normalized_run,
        },
        schema="pheroos-commit-replay-authority-key-v1",
        profile=normalized_profile,
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": normalized_issuer,
            "provenance": normalized_provenance,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-commit-replay-base-v1",
        profile=normalized_profile,
    )
    with _COMMIT_REPLAY_REGISTRY_LOCK:
        cursor = _COMMIT_REPLAY_CURSORS.get(authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "commit replay authority already has a different base"
                )
            if not commit_replay_state_is_current(cursor.current_state):
                raise GovernanceError("commit replay current state is unavailable")
            assert cursor.current_state is not None
            return cursor.current_state
        cursor = _CommitReplayCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
        )
        state = CommitReplayState(
            chain_id=authority_key,
            profile=normalized_profile,
            assurance=assurance,
            manifest_root=normalized_manifest,
            commit_policy_root=normalized_policy,
            protocol_id=normalized_protocol,
            run_id=normalized_run,
            revision=0,
            initialized_at_step=current,
            current_step=current,
            previous_state_fingerprint="",
            receipts=(),
            receipt_root=_commit_replay_receipt_root(
                (),
                profile=normalized_profile,
            ),
            issuer_id=normalized_issuer,
            authority=authority,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_commit_replay_state(state, cursor=cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = commit_replay_state_fingerprint(
            state
        )
        _COMMIT_REPLAY_CURSORS[authority_key] = cursor
        return state


def record_commit_replay_receipts(
    state: CommitReplayState,
    *,
    current_step: int,
    receipts: Sequence[ReplayReceipt],
) -> CommitReplayState:
    if not commit_replay_state_is_authoritative(state):
        raise GovernanceError("commit replay state is not governance-issued")
    current = require_commit_step(current_step, "commit replay current_step")
    if current < state.current_step:
        raise GovernanceError("commit replay step cannot move backwards")
    incoming = _canonical_replay_receipts(receipts)
    if not incoming:
        return state
    existing_by_nonce = {item.nonce: item for item in state.receipts}
    existing_by_id = {
        (item.namespace, item.record_id): item for item in state.receipts
    }
    existing_by_payload = {
        item.payload_fingerprint: item for item in state.receipts
    }
    additions: list[ReplayReceipt] = []
    for receipt in incoming:
        collisions = tuple(
            item
            for item in (
                existing_by_nonce.get(receipt.nonce),
                existing_by_id.get((receipt.namespace, receipt.record_id)),
                existing_by_payload.get(receipt.payload_fingerprint),
            )
            if item is not None
        )
        if collisions:
            if any(item != receipt for item in collisions):
                raise GovernanceError(
                    "commit replay receipt collision is a safety violation"
                )
            continue
        additions.append(receipt)
        existing_by_nonce[receipt.nonce] = receipt
        existing_by_id[(receipt.namespace, receipt.record_id)] = receipt
        existing_by_payload[receipt.payload_fingerprint] = receipt
    if not additions:
        return state

    combined = _canonical_replay_receipts((*state.receipts, *additions))
    parent_fingerprint = commit_replay_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "current_step": current,
            "parent_state_fingerprint": parent_fingerprint,
            "receipt_fingerprints": tuple(
                replay_receipt_fingerprint(item, profile=state.profile)
                for item in additions
            ),
        },
        schema="pheroos-commit-replay-transition-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitReplayCursor:
        raise GovernanceError("commit replay cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_fingerprint:
            cached = cursor.transitions.get(parent_fingerprint)
            if cached is not None and cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit replay state is stale or would fork")
    next_state = CommitReplayState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        revision=state.revision + 1,
        initialized_at_step=state.initialized_at_step,
        current_step=current,
        previous_state_fingerprint=parent_fingerprint,
        receipts=combined,
        receipt_root=_commit_replay_receipt_root(
            combined,
            profile=state.profile,
        ),
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_fingerprint:
            cached = cursor.transitions.get(parent_fingerprint)
            if cached is not None and cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit replay state is stale or would fork")
        next_state = _issue_commit_replay_state(next_state, cursor=cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = commit_replay_state_fingerprint(
            next_state
        )
        cursor.transitions[parent_fingerprint] = (request_fingerprint, next_state)
        return next_state


def _issue_decision_progress(**values: object) -> DecisionProgress:
    progress = DecisionProgress(**values)  # type: ignore[arg-type]
    object.__setattr__(
        progress,
        "_issuance",
        (_DECISION_PROGRESS_ISSUANCE, _progress_snapshot(progress)),
    )
    return progress


def _issue_decision_outcome(**values: object) -> DecisionOutcome:
    outcome = DecisionOutcome(**values)  # type: ignore[arg-type]
    object.__setattr__(
        outcome,
        "_issuance",
        (_DECISION_OUTCOME_ISSUANCE, _outcome_snapshot(outcome)),
    )
    return outcome


def _issue_commit_window_state(
    state: CommitWindowState,
    *,
    cursor: _CommitWindowCursor,
) -> CommitWindowState:
    object.__setattr__(
        state,
        "_issuance",
        (_COMMIT_WINDOW_STATE_ISSUANCE, commit_window_state_fingerprint(state)),
    )
    object.__setattr__(state, "_cursor", cursor)
    return state


def _issue_commit_replay_state(
    state: CommitReplayState,
    *,
    cursor: _CommitReplayCursor,
) -> CommitReplayState:
    object.__setattr__(
        state,
        "_issuance",
        (_COMMIT_REPLAY_STATE_ISSUANCE, commit_replay_state_fingerprint(state)),
    )
    object.__setattr__(state, "_cursor", cursor)
    return state


def commit_window_state_is_authoritative(state: object) -> bool:
    if type(state) is not CommitWindowState:
        return False
    try:
        _validate_commit_window_state(state)
        issuance = state._issuance
        cursor = state._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_WINDOW_STATE_ISSUANCE
            and issuance[1] == commit_window_state_fingerprint(state)
            and type(cursor) is _CommitWindowCursor
            and cursor.chain_id == state.chain_id
        )
    except Exception:
        return False


def commit_window_state_is_current(state: object) -> bool:
    if not commit_window_state_is_authoritative(state):
        return False
    assert type(state) is CommitWindowState
    cursor = state._cursor
    assert type(cursor) is _CommitWindowCursor
    try:
        with cursor.lock:
            return bool(
                cursor.current_state is state
                and cursor.current_state_fingerprint
                == commit_window_state_fingerprint(state)
            )
    except Exception:
        return False


def commit_liveness_input_is_authoritative(value: object) -> bool:
    return bool(
        _commit_liveness_input_was_issued(value)
        and _liveness_authority_heads_are_current(value)
    )


def _commit_liveness_input_was_issued(value: object) -> bool:
    if type(value) is not CommitLivenessInput:
        return False
    try:
        _validate_commit_liveness_input(value)
        issuance = value._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_LIVENESS_INPUT_ISSUANCE
            and issuance[1] == commit_liveness_input_fingerprint(value)
        )
    except Exception:
        return False


def commit_replay_state_is_authoritative(state: object) -> bool:
    if type(state) is not CommitReplayState:
        return False
    try:
        _validate_commit_replay_state(state)
        issuance = state._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_REPLAY_STATE_ISSUANCE
            and issuance[1] == commit_replay_state_fingerprint(state)
        )
    except Exception:
        return False


def commit_replay_state_is_current(state: object) -> bool:
    if not commit_replay_state_is_authoritative(state):
        return False
    assert type(state) is CommitReplayState
    cursor = state._cursor
    return bool(
        type(cursor) is _CommitReplayCursor
        and cursor.current_state is state
        and cursor.current_state_fingerprint
        == commit_replay_state_fingerprint(state)
    )


def commit_window_state_payload(state: CommitWindowState) -> dict[str, object]:
    if type(state) is not CommitWindowState:
        raise GovernanceError("commit window state must use the canonical record")
    _validate_commit_window_state(state)
    return {
        "absolute_deadline_step": state.absolute_deadline_step,
        "absolute_run_deadline_step": state.absolute_run_deadline_step,
        "assurance": state.assurance,
        "authority": state.authority,
        "assessment_replay_root": state.assessment_replay_root,
        "assessment_replay_state_ref": state.assessment_replay_state_ref,
        "candidate_challenge_root": state.candidate_challenge_root,
        "candidate_evidence_root": state.candidate_evidence_root,
        "candidate_lease_root": state.candidate_lease_root,
        "chain_id": state.chain_id,
        "collective_challenge_root": state.collective_challenge_root,
        "collective_evidence_root": state.collective_evidence_root,
        "collective_lease_root": state.collective_lease_root,
        "commit_policy_root": state.commit_policy_root,
        "epoch": state.epoch,
        "initialized_at_step": state.initialized_at_step,
        "issuer_id": state.issuer_id,
        "last_assessment_reason_codes": state.last_assessment_reason_codes,
        "last_assessment_ref": state.last_assessment_ref,
        "last_assessment_status": state.last_assessment_status,
        "last_context_ref": state.last_context_ref,
        "last_evaluated_step": state.last_evaluated_step,
        "last_ready": state.last_ready,
        "leader_candidate_id": state.leader_candidate_id,
        "manifest_root": state.manifest_root,
        "membership_root": state.membership_root,
        "membership_epoch_state_root": state.membership_epoch_state_root,
        "membership_snapshot_root": state.membership_snapshot_root,
        "minimum_stability_steps": state.minimum_stability_steps,
        "ordered_assessment_refs": state.ordered_assessment_refs,
        "previous_state_fingerprint": state.previous_state_fingerprint,
        "permission_root": state.permission_root,
        "profile": state.profile,
        "provenance": state.provenance,
        "protocol_id": state.protocol_id,
        "remaining_epoch_restart_budget": state.remaining_epoch_restart_budget,
        "remaining_reset_budget": state.remaining_reset_budget,
        "reset_budget_exhausted": state.reset_budget_exhausted,
        "reset_reason": state.reset_reason,
        "revision": state.revision,
        "risk_assessment_root": state.risk_assessment_root,
        "risk_chain_state_root": state.risk_chain_state_root,
        "risk_policy_root": state.risk_policy_root,
        "run_id": state.run_id,
        "target": state.target,
        "stop_resolution_root": state.stop_resolution_root,
        "support_replay_root": state.support_replay_root,
        "support_replay_state_root": state.support_replay_state_root,
        "threshold_root": state.threshold_root,
        "trace_event_id": state.trace_event_id,
        "window_count": state.window_count,
        "window_root": state.window_root,
    }


def commit_window_state_fingerprint(state: CommitWindowState) -> str:
    return commit_payload_fingerprint(
        commit_window_state_payload(state),
        schema="pheroos-commit-window-state-v1",
        profile=state.profile,
    )


def commit_liveness_input_payload(
    value: CommitLivenessInput,
) -> dict[str, object]:
    if type(value) is not CommitLivenessInput:
        raise GovernanceError("commit liveness input must use the canonical record")
    _validate_commit_liveness_input(value)
    return {
        "assessment_reason_codes": value.assessment_reason_codes,
        "assessment_ref": value.assessment_ref,
        "assessment_status": value.assessment_status,
        "assurance": value.assurance,
        "authority": value.authority,
        "blocked_reason_codes": value.blocked_reason_codes,
        "certificate_ref": value.certificate_ref,
        "candidate_challenge_root": value.candidate_challenge_root,
        "candidate_evidence_root": value.candidate_evidence_root,
        "candidate_lease_root": value.candidate_lease_root,
        "collective_challenge_root": value.collective_challenge_root,
        "collective_evidence_root": value.collective_evidence_root,
        "collective_lease_root": value.collective_lease_root,
        "commit_policy_root": value.commit_policy_root,
        "context_ref": value.context_ref,
        "current_step": value.current_step,
        "deadline_reached": value.deadline_reached,
        "epoch": value.epoch,
        "finality_reason_codes": value.finality_reason_codes,
        "finality_status": value.finality_status,
        "finality_verification_ref": value.finality_verification_ref,
        "input_id": value.input_id,
        "invalid_reason_codes": value.invalid_reason_codes,
        "issuer_id": value.issuer_id,
        "leader_candidate_id": value.leader_candidate_id,
        "leader_ready_for_stability": value.leader_ready_for_stability,
        "manifest_root": value.manifest_root,
        "membership_root": value.membership_root,
        "membership_epoch_state_root": value.membership_epoch_state_root,
        "membership_snapshot_root": value.membership_snapshot_root,
        "next_required_inputs": value.next_required_inputs,
        "profile": value.profile,
        "permission_root": value.permission_root,
        "protocol_id": value.protocol_id,
        "provenance": value.provenance,
        "replay_root": value.replay_root,
        "replay_state_ref": value.replay_state_ref,
        "risk_assessment_root": value.risk_assessment_root,
        "risk_chain_state_root": value.risk_chain_state_root,
        "risk_policy_root": value.risk_policy_root,
        "run_id": value.run_id,
        "safety_violation_reason_codes": (
            value.safety_violation_reason_codes
        ),
        "target": value.target,
        "stop_resolution_root": value.stop_resolution_root,
        "support_replay_root": value.support_replay_root,
        "support_replay_state_root": value.support_replay_state_root,
        "sealed_window": value.sealed_window,
        "seal_ref": value.seal_ref,
        "sealed_at_step": value.sealed_at_step,
        "heartbeat_continuous": value.heartbeat_continuous,
        "heartbeat_sequence": value.heartbeat_sequence,
        "previous_progress_ref": value.previous_progress_ref,
        "threshold_root": value.threshold_root,
        "trace_event_id": value.trace_event_id,
        "window_state_ref": value.window_state_ref,
    }


def commit_liveness_input_fingerprint(value: CommitLivenessInput) -> str:
    return commit_payload_fingerprint(
        commit_liveness_input_payload(value),
        schema="pheroos-commit-liveness-input-v1",
        profile=value.profile,
    )


def replay_receipt_payload(receipt: ReplayReceipt) -> dict[str, object]:
    if type(receipt) is not ReplayReceipt:
        raise GovernanceError("replay receipt must use the canonical record")
    _validate_replay_receipt(receipt)
    return {
        "candidate_id": receipt.candidate_id,
        "epoch": receipt.epoch,
        "namespace": receipt.namespace,
        "nonce": receipt.nonce,
        "payload_fingerprint": receipt.payload_fingerprint,
        "principal_id": receipt.principal_id,
        "record_id": receipt.record_id,
        "target": receipt.target,
    }


def replay_receipt_fingerprint(
    receipt: ReplayReceipt,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        replay_receipt_payload(receipt),
        schema="pheroos-commit-replay-receipt-v1",
        profile=require_commit_profile(profile, "replay receipt profile"),
    )


def commit_replay_state_contains(
    state: CommitReplayState,
    receipt: ReplayReceipt,
) -> bool:
    try:
        return bool(
            commit_replay_state_is_current(state)
            and type(receipt) is ReplayReceipt
            and receipt in state.receipts
        )
    except GovernanceError:
        return False


def commit_replay_state_matches(
    state: CommitReplayState | None,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    current_step: int,
) -> bool:
    try:
        current = require_commit_step(current_step, "commit replay expected step")
        return bool(
            commit_replay_state_is_current(state)
            and state is not None
            and state.profile
            == require_commit_profile(profile, "commit replay expected profile")
            and state.assurance is assurance
            and state.manifest_root
            == require_commit_fingerprint(
                manifest_root,
                "commit replay expected manifest_root",
            )
            and state.commit_policy_root
            == require_commit_fingerprint(
                commit_policy_root,
                "commit replay expected commit_policy_root",
            )
            and state.protocol_id
            == require_commit_text(
                protocol_id,
                "commit replay expected protocol_id",
            )
            and state.run_id
            == require_commit_text(run_id, "commit replay expected run_id")
            and state.current_step <= current
        )
    except GovernanceError:
        return False


def commit_replay_state_payload(state: CommitReplayState) -> dict[str, object]:
    if type(state) is not CommitReplayState:
        raise GovernanceError("commit replay state must use the canonical record")
    _validate_commit_replay_state(state)
    return {
        "assurance": state.assurance,
        "authority": state.authority,
        "chain_id": state.chain_id,
        "commit_policy_root": state.commit_policy_root,
        "current_step": state.current_step,
        "initialized_at_step": state.initialized_at_step,
        "issuer_id": state.issuer_id,
        "manifest_root": state.manifest_root,
        "previous_state_fingerprint": state.previous_state_fingerprint,
        "profile": state.profile,
        "protocol_id": state.protocol_id,
        "provenance": state.provenance,
        "receipt_root": state.receipt_root,
        "receipts": tuple(replay_receipt_payload(item) for item in state.receipts),
        "revision": state.revision,
        "run_id": state.run_id,
        "trace_event_id": state.trace_event_id,
    }


def commit_replay_state_fingerprint(state: CommitReplayState) -> str:
    return commit_payload_fingerprint(
        commit_replay_state_payload(state),
        schema="pheroos-commit-replay-state-v1",
        profile=state.profile,
    )


def _validate_commit_window_state(state: CommitWindowState) -> None:
    _validate_commit_binding_values(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit window",
    )
    require_commit_fingerprint(state.chain_id, "commit window chain_id")
    revision = require_commit_step(state.revision, "commit window revision")
    if revision == 0:
        if state.previous_state_fingerprint:
            raise GovernanceError(
                "initial commit window cannot declare a predecessor"
            )
    else:
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "commit window previous_state_fingerprint",
        )
    for field_name in (
        "risk_assessment_root",
        "membership_root",
        "threshold_root",
        "window_root",
    ):
        require_commit_fingerprint(
            getattr(state, field_name),
            f"commit window {field_name}",
        )
    for field_name in (
        "initialized_at_step",
        "last_evaluated_step",
        "absolute_deadline_step",
        "absolute_run_deadline_step",
        "remaining_reset_budget",
        "remaining_epoch_restart_budget",
        "minimum_stability_steps",
        "window_count",
    ):
        require_commit_step(
            getattr(state, field_name),
            f"commit window {field_name}",
        )
    if state.minimum_stability_steps <= 0:
        raise GovernanceError("commit window stability threshold must be positive")
    if state.last_evaluated_step < state.initialized_at_step:
        raise GovernanceError("commit window evaluated before initialization")
    if state.last_evaluated_step >= state.absolute_deadline_step:
        raise GovernanceError("commit window state cannot survive its deadline")
    if state.absolute_deadline_step > state.absolute_run_deadline_step:
        raise GovernanceError("commit window deadline exceeds run deadline")
    if state.absolute_deadline_step <= state.initialized_at_step:
        raise GovernanceError("commit window deadline must follow initialization")
    for field_name in ("last_ready", "reset_budget_exhausted"):
        if type(getattr(state, field_name)) is not bool:
            raise GovernanceError(f"commit window {field_name} must be boolean")
    require_commit_text(state.reset_reason, "commit window reset_reason")
    require_commit_text(state.issuer_id, "commit window issuer_id")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("commit window authority is invalid")
    require_commit_text(state.provenance, "commit window provenance")
    require_commit_text(state.trace_event_id, "commit window trace_event_id")
    if state.last_assessment_ref:
        require_commit_fingerprint(
            state.last_assessment_ref,
            "commit window last_assessment_ref",
        )
        require_commit_fingerprint(
            state.last_context_ref,
            "commit window last_context_ref",
        )
        require_commit_text(
            state.last_assessment_status,
            "commit window last_assessment_status",
        )
        for name in (
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
            "assessment_replay_state_ref",
            "assessment_replay_root",
        ):
            require_commit_fingerprint(
                getattr(state, name),
                f"commit window {name}",
            )
        candidate_roots = (
            state.candidate_evidence_root,
            state.candidate_challenge_root,
            state.candidate_lease_root,
        )
        if any(candidate_roots) and not all(candidate_roots):
            raise GovernanceError(
                "commit window candidate lineage roots must be complete"
            )
        for value in candidate_roots:
            if value:
                require_commit_fingerprint(
                    value,
                    "commit window candidate lineage root",
                )
    elif (
        state.last_context_ref
        or state.last_assessment_status
        or state.last_assessment_reason_codes
        or state.risk_chain_state_root
        or state.risk_policy_root
        or state.membership_snapshot_root
        or state.membership_epoch_state_root
        or state.support_replay_state_root
        or state.support_replay_root
        or state.collective_evidence_root
        or state.collective_challenge_root
        or state.collective_lease_root
        or state.candidate_evidence_root
        or state.candidate_challenge_root
        or state.candidate_lease_root
        or state.stop_resolution_root
        or state.permission_root
        or state.assessment_replay_state_ref
        or state.assessment_replay_root
    ):
        raise GovernanceError(
            "commit window empty assessment lineage contains metadata"
        )
    for reference in state.ordered_assessment_refs:
        require_commit_fingerprint(reference, "commit window assessment_ref")
    if len(state.ordered_assessment_refs) != len(set(state.ordered_assessment_refs)):
        raise GovernanceError("commit window assessment lineage contains replay")
    if state.last_ready:
        require_commit_text(
            state.leader_candidate_id,
            "commit window leader_candidate_id",
        )
        if state.window_count <= 0:
            raise GovernanceError("ready commit window requires positive count")
        if len(state.ordered_assessment_refs) != state.window_count:
            raise GovernanceError(
                "commit window assessment lineage must match window_count"
            )
        if (
            not state.last_assessment_ref
            or state.last_assessment_status != "ready"
            or state.ordered_assessment_refs[-1] != state.last_assessment_ref
        ):
            raise GovernanceError(
                "ready commit window must end at its latest ready assessment"
            )
    elif (
        state.leader_candidate_id
        or state.window_count != 0
        or state.ordered_assessment_refs
    ):
        raise GovernanceError("non-ready commit window must have an empty window")
    expected_root = _window_root(
        state.ordered_assessment_refs,
        profile=state.profile,
        run_id=state.run_id,
        epoch=state.epoch,
    )
    if state.window_root != expected_root:
        raise GovernanceError("commit window root does not match ordered assessments")
    if state.reset_budget_exhausted and state.last_ready:
        raise GovernanceError("exhausted reset budget cannot retain a ready window")


def _validate_commit_window_seal(seal: CommitWindowSeal) -> None:
    _validate_commit_binding_values(
        profile=seal.profile,
        assurance=seal.assurance,
        manifest_root=seal.manifest_root,
        commit_policy_root=seal.commit_policy_root,
        protocol_id=seal.protocol_id,
        run_id=seal.run_id,
        target=seal.target,
        epoch=seal.epoch,
        field_name="commit window seal",
    )
    require_commit_fingerprint(seal.chain_id, "commit window seal chain_id")
    for name in (
        "receipt_ref",
        "claim_fingerprint",
        "output_payload_fingerprint",
        "context_ref",
        "assessment_ref",
        "window_state_ref",
        "window_root",
        "risk_assessment_root",
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "threshold_root",
        "replay_state_ref",
        "replay_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
    ):
        require_commit_fingerprint(
            getattr(seal, name),
            f"commit window seal {name}",
        )
    require_commit_text(seal.candidate_id, "commit window seal candidate_id")
    for name in (
        "generation",
        "sealed_at_step",
        "absolute_deadline_step",
        "absolute_run_deadline_step",
        "remaining_reset_budget",
        "remaining_epoch_restart_budget",
    ):
        require_commit_step(getattr(seal, name), f"commit window seal {name}")
    if seal.sealed_at_step >= seal.absolute_deadline_step:
        raise GovernanceError("commit window cannot be sealed at its deadline")
    if seal.absolute_deadline_step > seal.absolute_run_deadline_step:
        raise GovernanceError("commit window seal deadline exceeds run deadline")
    require_commit_text(seal.issuer_id, "commit window seal issuer_id")
    if type(seal.authority) is not AuthorityLevel or not can_verify(seal.authority):
        raise GovernanceError("commit window seal authority is invalid")
    require_commit_text(seal.provenance, "commit window seal provenance")
    require_commit_text(seal.trace_event_id, "commit window seal trace_event_id")


def _validate_commit_liveness_input(value: CommitLivenessInput) -> None:
    _validate_commit_binding_values(
        profile=value.profile,
        assurance=value.assurance,
        manifest_root=value.manifest_root,
        commit_policy_root=value.commit_policy_root,
        protocol_id=value.protocol_id,
        run_id=value.run_id,
        target=value.target,
        epoch=value.epoch,
        field_name="commit liveness input",
    )
    require_commit_text(value.input_id, "commit liveness input_id")
    require_commit_step(value.current_step, "commit liveness current_step")
    if type(value.deadline_reached) is not bool:
        raise GovernanceError("commit liveness deadline_reached must be boolean")
    for name in (
        "replay_state_ref",
        "replay_root",
        "window_state_ref",
        "risk_assessment_root",
        "membership_root",
        "threshold_root",
    ):
        require_commit_fingerprint(
            getattr(value, name),
            f"commit liveness {name}",
        )
    if value.assessment_ref:
        require_commit_fingerprint(
            value.assessment_ref,
            "commit liveness assessment_ref",
        )
        require_commit_fingerprint(
            value.context_ref,
            "commit liveness context_ref",
        )
        require_commit_text(
            value.assessment_status,
            "commit liveness assessment_status",
        )
        for name in (
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
        ):
            require_commit_fingerprint(
                getattr(value, name),
                f"commit liveness {name}",
            )
        candidate_roots = (
            value.candidate_evidence_root,
            value.candidate_challenge_root,
            value.candidate_lease_root,
        )
        if any(candidate_roots) and not all(candidate_roots):
            raise GovernanceError(
                "commit liveness candidate lineage roots must be complete"
            )
        for root in candidate_roots:
            if root:
                require_commit_fingerprint(
                    root,
                    "commit liveness candidate lineage root",
                )
    elif (
        value.context_ref
        or value.assessment_status
        or value.leader_candidate_id
        or value.leader_ready_for_stability
        or value.assessment_reason_codes
        or value.risk_chain_state_root
        or value.risk_policy_root
        or value.membership_snapshot_root
        or value.membership_epoch_state_root
        or value.support_replay_state_root
        or value.support_replay_root
        or value.collective_evidence_root
        or value.collective_challenge_root
        or value.collective_lease_root
        or value.candidate_evidence_root
        or value.candidate_challenge_root
        or value.candidate_lease_root
        or value.stop_resolution_root
        or value.permission_root
    ):
        raise GovernanceError(
            "commit liveness empty assessment cannot carry assessment metadata"
        )
    if value.leader_candidate_id:
        require_commit_text(
            value.leader_candidate_id,
            "commit liveness leader_candidate_id",
        )
    if type(value.leader_ready_for_stability) is not bool:
        raise GovernanceError(
            "commit liveness leader readiness must be boolean"
        )
    if value.leader_ready_for_stability and not value.leader_candidate_id:
        raise GovernanceError(
            "commit liveness ready leader requires a candidate"
        )
    for name, item in (
        ("sealed_window", value.sealed_window),
        ("heartbeat_continuous", value.heartbeat_continuous),
    ):
        if type(item) is not bool:
            raise GovernanceError(f"commit liveness {name} must be boolean")
    require_commit_step(value.sealed_at_step, "commit liveness sealed_at_step")
    require_commit_step(
        value.heartbeat_sequence,
        "commit liveness heartbeat_sequence",
    )
    if value.sealed_window:
        require_commit_fingerprint(value.seal_ref, "commit liveness seal_ref")
        if not value.assessment_ref:
            raise GovernanceError("sealed liveness requires assessment lineage")
        if value.sealed_at_step > value.current_step:
            raise GovernanceError("commit liveness seal is from the future")
    elif value.seal_ref or value.sealed_at_step or value.previous_progress_ref:
        raise GovernanceError("unsealed liveness cannot carry seal lineage")
    if value.previous_progress_ref:
        require_commit_fingerprint(
            value.previous_progress_ref,
            "commit liveness previous_progress_ref",
        )
        if not value.sealed_window or value.heartbeat_sequence == 0:
            raise GovernanceError(
                "commit liveness heartbeat predecessor requires a sealed sequence"
            )
    elif value.heartbeat_sequence != 0:
        raise GovernanceError(
            "initial commit liveness heartbeat sequence must be zero"
        )
    if not value.heartbeat_continuous and not value.sealed_window:
        raise GovernanceError(
            "only a sealed late-finality path can report heartbeat loss"
        )
    if type(value.finality_status) is not CommitFinalityStatus:
        raise GovernanceError("commit liveness finality status is invalid")
    if value.certificate_ref:
        require_commit_fingerprint(
            value.certificate_ref,
            "commit liveness certificate_ref",
        )
    if value.finality_verification_ref:
        require_commit_fingerprint(
            value.finality_verification_ref,
            "commit liveness finality_verification_ref",
        )
    if value.finality_status is CommitFinalityStatus.VERIFIED:
        if not value.certificate_ref or not value.finality_verification_ref:
            raise GovernanceError(
                "verified finality requires a typed certificate verification"
            )
        if not value.sealed_window or not value.heartbeat_continuous:
            raise GovernanceError(
                "verified finality requires a continuous receipt-backed seal"
            )
    elif value.certificate_ref or value.finality_verification_ref:
        raise GovernanceError(
            "non-verified finality cannot carry certificate authority"
        )
    require_commit_text(value.issuer_id, "commit liveness issuer_id")
    if type(value.authority) is not AuthorityLevel or not can_verify(value.authority):
        raise GovernanceError("commit liveness authority is invalid")
    require_commit_text(value.provenance, "commit liveness provenance")
    require_commit_text(value.trace_event_id, "commit liveness trace_event_id")


def _validate_commit_finality_verification(
    value: CommitFinalityVerification,
) -> None:
    _validate_commit_binding_values(
        profile=value.profile,
        assurance=value.assurance,
        manifest_root=value.manifest_root,
        commit_policy_root=value.commit_policy_root,
        protocol_id=value.protocol_id,
        run_id=value.run_id,
        target=value.target,
        epoch=value.epoch,
        field_name="commit finality verification",
    )
    if value.status is not CommitFinalityStatus.VERIFIED:
        raise GovernanceError("commit finality verification must be verified")
    expected_kind = {
        CommitAssurance.EVIDENCE_BOUND: "local_commit_receipt",
        CommitAssurance.CERTIFIED: "evidence_commit_certificate",
        CommitAssurance.DISTRIBUTED: "distributed_commit_certificate",
    }.get(value.assurance)
    if value.certificate_kind != expected_kind:
        raise GovernanceError(
            "commit finality certificate kind does not match assurance"
        )
    require_commit_fingerprint(
        value.certificate_ref,
        "commit finality certificate_ref",
    )
    require_commit_text(value.candidate_id, "commit finality candidate_id")
    for name in (
        "context_ref",
        "assessment_ref",
        "window_state_ref",
        "window_root",
        "risk_assessment_root",
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "threshold_root",
        "replay_state_ref",
        "replay_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
    ):
        require_commit_fingerprint(
            getattr(value, name),
            f"commit finality {name}",
        )
    require_commit_step(
        value.verified_at_step,
        "commit finality verified_at_step",
    )
    require_commit_text(value.verifier_id, "commit finality verifier_id")
    if type(value.authority) is not AuthorityLevel or not can_verify(value.authority):
        raise GovernanceError("commit finality verifier authority is invalid")
    require_commit_text(value.provenance, "commit finality provenance")
    require_commit_text(value.trace_event_id, "commit finality trace_event_id")


def _validate_commit_replay_state(state: CommitReplayState) -> None:
    profile = require_commit_profile(state.profile, "commit replay profile")
    if type(state.assurance) is not CommitAssurance:
        raise GovernanceError("commit replay assurance is invalid")
    _validate_profile_assurance(profile, state.assurance, field_name="commit replay")
    require_commit_fingerprint(state.chain_id, "commit replay chain_id")
    require_commit_fingerprint(state.manifest_root, "commit replay manifest_root")
    require_commit_fingerprint(
        state.commit_policy_root,
        "commit replay commit_policy_root",
    )
    require_commit_text(state.protocol_id, "commit replay protocol_id")
    require_commit_text(state.run_id, "commit replay run_id")
    revision = require_commit_step(state.revision, "commit replay revision")
    initialized = require_commit_step(
        state.initialized_at_step,
        "commit replay initialized_at_step",
    )
    require_commit_step(state.current_step, "commit replay current_step")
    if state.current_step < initialized:
        raise GovernanceError("commit replay current step predates initialization")
    if revision == 0:
        if state.previous_state_fingerprint or state.receipts:
            raise GovernanceError("initial commit replay state must be empty")
    else:
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "commit replay previous_state_fingerprint",
        )
        if not state.receipts:
            raise GovernanceError("advanced commit replay state requires receipts")
    canonical = _canonical_replay_receipts(state.receipts)
    if canonical != state.receipts:
        raise GovernanceError("commit replay receipts are not canonical")
    expected_root = _commit_replay_receipt_root(canonical, profile=profile)
    require_commit_fingerprint(state.receipt_root, "commit replay receipt_root")
    if state.receipt_root != expected_root:
        raise GovernanceError("commit replay receipt root mismatch")
    require_commit_text(state.issuer_id, "commit replay issuer_id")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("commit replay authority is invalid")
    require_commit_text(state.provenance, "commit replay provenance")
    require_commit_text(state.trace_event_id, "commit replay trace_event_id")


def _validate_replay_receipt(receipt: ReplayReceipt) -> None:
    if type(receipt.namespace) is not ReplayNamespace:
        raise GovernanceError("replay receipt namespace is invalid")
    require_commit_text(receipt.record_id, "replay receipt record_id")
    require_commit_text(receipt.nonce, "replay receipt nonce")
    require_commit_fingerprint(
        receipt.payload_fingerprint,
        "replay receipt payload_fingerprint",
    )
    require_commit_text(receipt.target, "replay receipt target")
    if receipt.candidate_id:
        require_commit_text(receipt.candidate_id, "replay receipt candidate_id")
    require_commit_step(receipt.epoch, "replay receipt epoch")
    if receipt.principal_id:
        require_commit_text(receipt.principal_id, "replay receipt principal_id")


def _canonical_replay_receipts(
    receipts: Sequence[ReplayReceipt],
) -> tuple[ReplayReceipt, ...]:
    if isinstance(receipts, (str, bytes, bytearray)):
        raise GovernanceError("replay receipts must be a sequence")
    normalized = tuple(receipts)
    if any(type(item) is not ReplayReceipt for item in normalized):
        raise GovernanceError("replay receipts contain a non-canonical record")
    for item in normalized:
        _validate_replay_receipt(item)
    canonical = tuple(
        sorted(
            normalized,
            key=lambda item: replay_receipt_fingerprint(
                item,
                profile="pheroos-commit-integrity-v1",
            ),
        )
    )
    if len(set(canonical)) != len(canonical):
        # Exact duplicate receipts are semantically idempotent; retain one.
        deduplicated: list[ReplayReceipt] = []
        seen: set[ReplayReceipt] = set()
        for item in canonical:
            if item not in seen:
                seen.add(item)
                deduplicated.append(item)
        canonical = tuple(deduplicated)
    by_nonce: dict[str, ReplayReceipt] = {}
    by_id: dict[tuple[ReplayNamespace, str], ReplayReceipt] = {}
    by_payload: dict[str, ReplayReceipt] = {}
    for item in canonical:
        for existing in (
            by_nonce.get(item.nonce),
            by_id.get((item.namespace, item.record_id)),
            by_payload.get(item.payload_fingerprint),
        ):
            if existing is not None and existing != item:
                raise GovernanceError(
                    "replay receipt set contains a safety collision"
                )
        by_nonce[item.nonce] = item
        by_id[(item.namespace, item.record_id)] = item
        by_payload[item.payload_fingerprint] = item
    return canonical


def _commit_replay_receipt_root(
    receipts: Sequence[ReplayReceipt],
    *,
    profile: str,
) -> str:
    normalized = _canonical_replay_receipts(receipts)
    return commit_payload_fingerprint(
        {
            "receipt_fingerprints": tuple(
                replay_receipt_fingerprint(item, profile=profile)
                for item in normalized
            )
        },
        schema="pheroos-commit-replay-receipt-root-v1",
        profile=profile,
    )


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


def _threshold_snapshot_bindings(snapshot: object) -> dict[str, object]:
    from pheroos.governance.risk import (
        CommitThresholdSnapshot,
        commit_threshold_snapshot_fingerprint,
        commit_threshold_snapshot_is_authoritative,
    )

    if (
        type(snapshot) is not CommitThresholdSnapshot
        or not commit_threshold_snapshot_is_authoritative(snapshot)
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
        "required_challenge_categories": (
            snapshot.required_challenge_categories
        ),
        "minimum_assurance": snapshot.minimum_assurance.value,
        "publishable_outcomes": snapshot.publishable_outcomes,
        "executable_outcomes": snapshot.executable_outcomes,
    }


def _validate_window_threshold_snapshot(
    snapshot: object,
    *,
    commit_policy: CollectiveCommitPolicy,
    bindings: dict[str, object],
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
            raise GovernanceError(
                f"commit window threshold {name} binding mismatch"
            )
    expected_risk = require_commit_fingerprint(
        risk_assessment_root,
        "commit window threshold risk assessment root",
    )
    if observed["risk_assessment_root"] != expected_risk:
        raise GovernanceError(
            "commit window threshold risk assessment binding mismatch"
        )
    current = require_commit_step(current_step, "commit window threshold step")
    if not int(observed["issued_at_step"]) <= current < int(
        observed["expires_at_step"]
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
        "maximum_counterevidence_ratio_ppm": (
            band.maximum_counterevidence_ratio_ppm
        ),
        "minimum_support_clusters": band.minimum_support_clusters,
        "minimum_support_ratio_ppm": band.minimum_support_ratio_ppm,
        "minimum_source_diversity": band.minimum_source_diversity,
        "minimum_margin": band.minimum_margin,
        "stability_steps": band.stability_steps,
        "minimum_assurance": band.minimum_assurance,
    }
    if any(observed[name] != value for name, value in exact_values.items()):
        raise GovernanceError(
            "commit window threshold values do not match the risk band policy"
        )
    for name in (
        "required_challenge_categories",
        "publishable_outcomes",
        "executable_outcomes",
    ):
        if set(observed[name]) != set(getattr(band, name)):
            raise GovernanceError(
                f"commit window threshold {name} does not match policy"
            )
    return (
        str(observed["threshold_root"]),
        int(observed["stability_steps"]),
    )


def _commit_window_authority_key(bindings: dict[str, object]) -> str:
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
    state: CommitWindowState,
    bindings: dict[str, object],
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
) -> dict[str, object]:
    # Delayed import preserves commit_state -> commit acyclicity at import time.
    from pheroos.governance.commit import (
        CommitAssessment,
        CommitAssessmentStatus,
        commit_assessment_fingerprint,
        commit_assessment_is_authoritative,
    )

    if (
        type(assessment) is not CommitAssessment
        or not commit_assessment_is_authoritative(assessment)
    ):
        raise GovernanceError(
            "commit window requires an authoritative CommitAssessment"
        )
    if current_step is not None and assessment.evaluated_at_step != current_step:
        raise GovernanceError(
            "commit assessment step does not match the window transition"
        )
    ready = bool(
        assessment.status is CommitAssessmentStatus.READY
        and assessment.unique_leader
        and assessment.leader_ready_for_stability
        and assessment.leader_candidate_id
    )
    if ready:
        require_commit_text(
            assessment.leader_candidate_id,
            "commit assessment window leader",
        )
    leader_metrics = next(
        (
            item
            for item in assessment.candidate_metrics
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    return {
        "assessment_ref": commit_assessment_fingerprint(assessment),
        "status": assessment.status.value,
        "profile": assessment.profile,
        "assurance": assessment.assurance,
        "manifest_root": assessment.manifest_root,
        "commit_policy_root": assessment.commit_policy_root,
        "protocol_id": assessment.protocol_id,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "epoch": assessment.epoch,
        "context_ref": assessment.context_fingerprint,
        "risk_assessment_root": assessment.risk_assessment_fingerprint,
        "risk_chain_state_root": assessment.risk_chain_state_fingerprint,
        "risk_policy_root": assessment.risk_policy_root,
        "membership_root": assessment.membership_root,
        "membership_snapshot_root": (
            assessment.membership_snapshot_fingerprint
        ),
        "membership_epoch_state_root": (
            assessment.membership_epoch_state_fingerprint
        ),
        "threshold_root": assessment.threshold_fingerprint,
        "replay_state_ref": assessment.replay_state_fingerprint,
        "replay_root": assessment.replay_receipt_root,
        "support_replay_state_root": (
            assessment.support_replay_state_fingerprint
        ),
        "support_replay_root": assessment.support_replay_root,
        "collective_evidence_root": assessment.collective_evidence_root,
        "collective_challenge_root": assessment.collective_challenge_root,
        "collective_lease_root": assessment.collective_lease_root,
        "candidate_evidence_root": (
            leader_metrics.evidence_root if leader_metrics is not None else ""
        ),
        "candidate_challenge_root": (
            leader_metrics.challenge_root if leader_metrics is not None else ""
        ),
        "candidate_lease_root": (
            leader_metrics.lease_root if leader_metrics is not None else ""
        ),
        "stop_resolution_root": assessment.stop_resolution_fingerprint,
        "permission_root": assessment.permission_fingerprint,
        "leader_candidate_id": assessment.leader_candidate_id,
        "ready": ready,
        "reason_codes": assessment.reason_codes,
        "evaluated_at_step": assessment.evaluated_at_step,
    }


def _validate_assessment_matches_window_head(
    state: CommitWindowState,
    view: dict[str, object],
) -> None:
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
            raise GovernanceError(
                f"commit liveness assessment {name} binding mismatch"
            )
    for state_name, view_name in (
        ("risk_assessment_root", "risk_assessment_root"),
        ("membership_root", "membership_root"),
        ("threshold_root", "threshold_root"),
        ("last_assessment_ref", "assessment_ref"),
        ("last_context_ref", "context_ref"),
        ("last_assessment_status", "status"),
    ):
        if getattr(state, state_name) != view[view_name]:
            raise GovernanceError(
                f"commit liveness assessment {view_name} is not the window head"
            )
    if state.last_evaluated_step != view["evaluated_at_step"]:
        raise GovernanceError("commit liveness assessment step is not current")


def _validate_liveness_input_matches_window(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
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
        if getattr(state, name) != getattr(value, name):
            raise GovernanceError(f"commit liveness {name} binding mismatch")
    if value.window_state_ref != commit_window_state_fingerprint(state):
        raise GovernanceError("commit liveness window head binding mismatch")
    if value.current_step < state.last_evaluated_step:
        raise GovernanceError("commit liveness step predates the window head")
    expected_deadline = value.current_step >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    if value.deadline_reached is not expected_deadline:
        raise GovernanceError("commit liveness deadline state mismatch")
    if value.assessment_ref != state.last_assessment_ref:
        raise GovernanceError("commit liveness assessment head mismatch")
    if value.context_ref != state.last_context_ref:
        raise GovernanceError("commit liveness context head mismatch")
    if value.assessment_status != state.last_assessment_status:
        raise GovernanceError("commit liveness assessment status mismatch")
    if value.assessment_reason_codes != state.last_assessment_reason_codes:
        raise GovernanceError("commit liveness assessment reasons mismatch")
    for name in (
        "risk_assessment_root",
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "threshold_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
    ):
        if getattr(value, name) != getattr(state, name):
            raise GovernanceError(f"commit liveness {name} mismatch")
    if state.last_ready and value.leader_candidate_id != state.leader_candidate_id:
        raise GovernanceError("commit liveness leader candidate mismatch")
    seal = commit_window_seal_for_state(state)
    if value.sealed_window is not (seal is not None):
        raise GovernanceError("commit liveness sealed-window state mismatch")
    if seal is not None:
        if (
            value.seal_ref != commit_window_seal_fingerprint(seal)
            or value.sealed_at_step != seal.sealed_at_step
            or value.window_state_ref != seal.window_state_ref
        ):
            raise GovernanceError("commit liveness seal lineage mismatch")
    if (
        not value.heartbeat_continuous
        and value.current_step
        < min(state.absolute_deadline_step, state.absolute_run_deadline_step)
    ):
        raise GovernanceError(
            "commit liveness heartbeat loss requires a terminal deadline"
        )


def _validate_liveness_current_authority_heads(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy | None,
    risk_chain_state: object | None,
    risk_assessment: object | None,
    threshold_snapshot: object | None,
    membership_snapshot: object | None,
    membership_epoch_state: object | None,
    support_replay_state: object | None,
    current_step: int,
    require_fresh_snapshot: bool,
) -> None:
    from pheroos.governance.risk import (
        commit_threshold_snapshot_fingerprint,
        commit_threshold_snapshot_matches,
        risk_assessment_fingerprint,
        risk_assessment_chain_state_fingerprint,
        risk_assessment_chain_state_is_current,
    )
    from pheroos.governance.support_lease import (
        eligible_membership_epoch_state_fingerprint,
        eligible_membership_epoch_state_is_current,
        eligible_principal_snapshot_fingerprint,
        eligible_principal_snapshot_matches,
        support_lease_replay_state_fingerprint,
        support_lease_replay_state_is_current,
    )

    if (
        not risk_assessment_chain_state_is_current(risk_chain_state)
        or risk_assessment_chain_state_fingerprint(risk_chain_state)
        != state.risk_chain_state_root
    ):
        raise GovernanceError(
            "commit liveness risk authority head changed after assessment"
        )
    if (
        not eligible_membership_epoch_state_is_current(membership_epoch_state)
        or eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        != state.membership_epoch_state_root
    ):
        raise GovernanceError(
            "commit liveness membership authority head changed after assessment"
        )
    if (
        not support_lease_replay_state_is_current(support_replay_state)
        or support_lease_replay_state_fingerprint(support_replay_state)
        != state.support_replay_state_root
    ):
        raise GovernanceError(
            "commit liveness support replay head changed after assessment"
        )
    if commit_policy is None:
        raise GovernanceError("commit liveness requires the bound commit policy")
    bindings = _normalized_window_bindings(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit liveness authority heads",
    )
    _validate_bound_commit_policy(commit_policy, bindings)
    if (
        risk_assessment_fingerprint(risk_assessment)
        != state.risk_assessment_root
        or commit_threshold_snapshot_fingerprint(threshold_snapshot)
        != state.threshold_root
    ):
        raise GovernanceError(
            "commit liveness risk or threshold root changed after assessment"
        )
    if (
        eligible_principal_snapshot_fingerprint(membership_snapshot)
        != state.membership_snapshot_root
        or getattr(membership_snapshot, "membership_root", None)
        != state.membership_root
    ):
        raise GovernanceError(
            "commit liveness membership root changed after assessment"
        )
    if not require_fresh_snapshot:
        return
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=commit_policy,
        current_step=current_step,
    ):
        raise GovernanceError(
            "late finality risk assessment or threshold is stale"
        )
    if (
        risk_assessment_fingerprint(risk_assessment)
        != state.risk_assessment_root
        or commit_threshold_snapshot_fingerprint(threshold_snapshot)
        != state.threshold_root
    ):
        raise GovernanceError(
            "late finality risk or threshold root changed after sealing"
        )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=current_step,
    ):
        raise GovernanceError(
            "late finality eligible-principal snapshot is stale"
        )
    if (
        eligible_principal_snapshot_fingerprint(membership_snapshot)
        != state.membership_snapshot_root
        or getattr(membership_snapshot, "membership_root", None)
        != state.membership_root
    ):
        raise GovernanceError(
            "late finality membership root changed after sealing"
        )


def _liveness_authority_heads_are_current(value: CommitLivenessInput) -> bool:
    try:
        heads = value._authority_heads
        if not isinstance(heads, tuple) or len(heads) != 8:
            return False
        (
            replay_state,
            risk_state,
            risk_assessment,
            threshold_snapshot,
            membership_snapshot,
            membership_state,
            support_state,
            commit_policy,
        ) = heads
        if not (
            commit_replay_state_is_current(replay_state)
            and commit_replay_state_fingerprint(replay_state)
            == value.replay_state_ref
            and replay_state.receipt_root == value.replay_root
        ):
            return False
        if not value.assessment_ref:
            return True
        from pheroos.governance.risk import (
            commit_threshold_snapshot_fingerprint,
            commit_threshold_snapshot_matches,
            risk_assessment_fingerprint,
            risk_assessment_chain_state_fingerprint,
            risk_assessment_chain_state_is_current,
        )
        from pheroos.governance.support_lease import (
            eligible_membership_epoch_state_fingerprint,
            eligible_membership_epoch_state_is_current,
            eligible_principal_snapshot_fingerprint,
            eligible_principal_snapshot_matches,
            support_lease_replay_state_fingerprint,
            support_lease_replay_state_is_current,
        )

        base_current = bool(
            risk_assessment_chain_state_is_current(risk_state)
            and risk_assessment_chain_state_fingerprint(risk_state)
            == value.risk_chain_state_root
            and eligible_membership_epoch_state_is_current(membership_state)
            and eligible_membership_epoch_state_fingerprint(membership_state)
            == value.membership_epoch_state_root
            and support_lease_replay_state_is_current(support_state)
            and support_lease_replay_state_fingerprint(support_state)
            == value.support_replay_state_root
        )
        if not base_current:
            return False
        bindings = _normalized_window_bindings(
            profile=value.profile,
            assurance=value.assurance,
            manifest_root=value.manifest_root,
            commit_policy_root=value.commit_policy_root,
            protocol_id=value.protocol_id,
            run_id=value.run_id,
            target=value.target,
            epoch=value.epoch,
            field_name="commit liveness authority heads",
        )
        _validate_bound_commit_policy(commit_policy, bindings)
        if not (
            risk_assessment_fingerprint(risk_assessment)
            == value.risk_assessment_root
            and commit_threshold_snapshot_fingerprint(threshold_snapshot)
            == value.threshold_root
            and eligible_principal_snapshot_fingerprint(membership_snapshot)
            == value.membership_snapshot_root
            and getattr(membership_snapshot, "membership_root", None)
            == value.membership_root
        ):
            return False
        if not (
            value.sealed_window
            and value.current_step > value.sealed_at_step
            and not value.deadline_reached
        ):
            return True
        return bool(
            commit_threshold_snapshot_matches(
                threshold_snapshot,
                assessment=risk_assessment,
                chain_state=risk_state,
                commit_policy=commit_policy,
                current_step=value.current_step,
            )
            and eligible_principal_snapshot_matches(
                membership_snapshot,
                epoch_state=membership_state,
                profile=value.profile,
                assurance=value.assurance,
                manifest_root=value.manifest_root,
                commit_policy_root=value.commit_policy_root,
                protocol_id=value.protocol_id,
                run_id=value.run_id,
                target=value.target,
                epoch=value.epoch,
                current_step=value.current_step,
            )
        )
    except Exception:
        return False


def _validate_finality_verification_matches_window(
    verification: CommitFinalityVerification,
    *,
    state: CommitWindowState,
    seal: CommitWindowSeal | None,
    current_step: int,
) -> None:
    if verification.verified_at_step != current_step:
        raise GovernanceError(
            "commit finality must be freshly verified at the liveness step"
        )
    if seal is None or not commit_window_seal_is_current(seal):
        raise GovernanceError(
            "commit finality requires the current receipt-backed seal"
        )
    if current_step >= min(
        seal.absolute_deadline_step,
        seal.absolute_run_deadline_step,
    ):
        raise GovernanceError("commit finality cannot be verified at its deadline")
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
        if getattr(verification, name) != getattr(state, name):
            raise GovernanceError(f"commit finality {name} binding mismatch")
    expected = {
        "candidate_id": seal.candidate_id,
        "context_ref": seal.context_ref,
        "assessment_ref": seal.assessment_ref,
        "window_state_ref": seal.window_state_ref,
        "window_root": seal.window_root,
        "risk_assessment_root": seal.risk_assessment_root,
        "risk_chain_state_root": seal.risk_chain_state_root,
        "risk_policy_root": seal.risk_policy_root,
        "membership_root": seal.membership_root,
        "membership_snapshot_root": seal.membership_snapshot_root,
        "membership_epoch_state_root": seal.membership_epoch_state_root,
        "threshold_root": seal.threshold_root,
        "replay_state_ref": seal.replay_state_ref,
        "replay_root": seal.replay_root,
        "support_replay_state_root": seal.support_replay_state_root,
        "support_replay_root": seal.support_replay_root,
        "collective_evidence_root": seal.collective_evidence_root,
        "collective_challenge_root": seal.collective_challenge_root,
        "collective_lease_root": seal.collective_lease_root,
        "candidate_evidence_root": seal.candidate_evidence_root,
        "candidate_challenge_root": seal.candidate_challenge_root,
        "candidate_lease_root": seal.candidate_lease_root,
        "stop_resolution_root": seal.stop_resolution_root,
        "permission_root": seal.permission_root,
    }
    for name, value in expected.items():
        if getattr(verification, name) != value:
            raise GovernanceError(f"commit finality {name} lineage mismatch")


def _finality_satisfied(value: CommitLivenessInput) -> bool:
    if value.assurance in {
        CommitAssurance.EVIDENCE_BOUND,
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        return bool(
            value.finality_status is CommitFinalityStatus.VERIFIED
            and value.certificate_ref
            and value.finality_verification_ref
        )
    return False


def _finality_unavailable_at_deadline(
    *,
    assurance: CommitAssurance,
    finality_status: CommitFinalityStatus,
    stability_satisfied: bool,
    deadline_reached: bool,
) -> bool:
    return bool(
        assurance in {
            CommitAssurance.CERTIFIED,
            CommitAssurance.DISTRIBUTED,
        }
        and stability_satisfied
        and deadline_reached
        and finality_status
        in {
            CommitFinalityStatus.PENDING,
            CommitFinalityStatus.PROVISIONAL,
            CommitFinalityStatus.UNAVAILABLE,
        }
    )


def _progress_from_liveness(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> DecisionProgress:
    if value.current_step >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("decision progress cannot survive a deadline")
    if not value.assessment_ref:
        phase = DecisionPhase.SEARCH
    elif (
        commit_window_ready(state)
        and value.sealed_window
        and not _finality_satisfied(value)
    ):
        phase = DecisionPhase.PROVISIONAL
    elif state.last_ready:
        phase = DecisionPhase.QUORUM_PENDING
    else:
        phase = DecisionPhase.DELIBERATE

    requirements = set(value.next_required_inputs)
    unmet = set(value.assessment_reason_codes)
    if not value.assessment_ref:
        requirements.add("commit_assessment")
    elif state.last_ready and not commit_window_ready(state):
        requirements.add("consecutive_stability_assessment")
    elif commit_window_ready(state) and not value.sealed_window:
        requirements.add("local_commit_receipt")
    elif commit_window_ready(state) and not _finality_satisfied(value):
        requirements.add("verified_finality")
    if not requirements and not unmet:
        requirements.add("next_commit_assessment")
    return _issue_decision_progress(
        phase=phase,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=value.current_step,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=state.remaining_reset_budget,
        remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
        minimum_stability_steps=state.minimum_stability_steps,
        context_ref=value.context_ref,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
        replay_state_ref=value.replay_state_ref,
        replay_root=value.replay_root,
        support_replay_state_root=state.support_replay_state_root,
        support_replay_root=state.support_replay_root,
        collective_evidence_root=state.collective_evidence_root,
        collective_challenge_root=state.collective_challenge_root,
        collective_lease_root=state.collective_lease_root,
        candidate_evidence_root=state.candidate_evidence_root,
        candidate_challenge_root=state.candidate_challenge_root,
        candidate_lease_root=state.candidate_lease_root,
        stop_resolution_root=state.stop_resolution_root,
        permission_root=state.permission_root,
        window_state_ref=value.window_state_ref,
        window_root=state.window_root,
        sealed_window=value.sealed_window,
        seal_ref=value.seal_ref,
        sealed_at_step=value.sealed_at_step,
        heartbeat_continuous=value.heartbeat_continuous,
        heartbeat_sequence=value.heartbeat_sequence,
        previous_progress_ref=value.previous_progress_ref,
        next_required_inputs=tuple(requirements),
        unmet_gates=tuple(unmet),
        leader_candidate_id=(
            state.leader_candidate_id
            if state.last_ready
            else value.leader_candidate_id
        ),
        window_count=state.window_count,
        assessment_ref=value.assessment_ref,
    )


def _outcome_from_liveness(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
    kind: DecisionOutcomeKind,
    deadline_reached: bool,
    run_deadline_reached: bool,
    derived_blocked: bool,
) -> DecisionOutcome:
    reasons: set[str] = set()
    if kind is DecisionOutcomeKind.INVALID:
        reasons.update(liveness_input.invalid_reason_codes)
        reasons.add("invalid")
    elif kind is DecisionOutcomeKind.SAFETY_VIOLATION:
        reasons.update(liveness_input.safety_violation_reason_codes)
        reasons.update(liveness_input.assessment_reason_codes)
        reasons.update(liveness_input.finality_reason_codes)
        reasons.add("safety_violation")
    elif kind is DecisionOutcomeKind.BLOCKED:
        reasons.update(liveness_input.blocked_reason_codes)
        if derived_blocked:
            reasons.update(liveness_input.assessment_reason_codes)
        reasons.add("blocked")
    elif kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        reasons.update(("evidence_commit", "stability_satisfied"))
        if liveness_input.current_step > liveness_input.sealed_at_step:
            reasons.add("late_finality_verified")
    elif kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
        reasons.update(liveness_input.finality_reason_codes)
        reasons.add("finality_unavailable")
    else:
        reasons.add(kind.value)
    if deadline_reached:
        reasons.add("deadline_reached")
    if run_deadline_reached:
        reasons.add("run_deadline_reached")

    if kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        candidate = state.leader_candidate_id
        scope = AuthorityScope(
            COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE[state.assurance.value]
        )
        authoritative = True
        epistemic = True
        certificate = liveness_input.certificate_ref
    elif kind is DecisionOutcomeKind.SAFE_FALLBACK:
        candidate = commit_policy.terminal_outcome.safe_fallback_candidate
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""
    elif kind is DecisionOutcomeKind.ADVISORY:
        candidate = liveness_input.leader_candidate_id
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""
    elif kind is DecisionOutcomeKind.BLOCKED:
        candidate = ""
        scope = AuthorityScope.DENIAL
        authoritative = False
        epistemic = False
        certificate = ""
    else:
        candidate = ""
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""

    # Certificate verification and current publish/execute permission remain
    # independent. Bounded liveness never pre-authorizes either action.
    return _issue_decision_outcome(
        kind=kind,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=liveness_input.current_step,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        authority_scope=scope,
        authoritative_commit=authoritative,
        epistemically_committed=epistemic,
        context_ref=liveness_input.context_ref,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
        replay_state_ref=liveness_input.replay_state_ref,
        replay_root=liveness_input.replay_root,
        support_replay_state_root=state.support_replay_state_root,
        support_replay_root=state.support_replay_root,
        collective_evidence_root=state.collective_evidence_root,
        collective_challenge_root=state.collective_challenge_root,
        collective_lease_root=state.collective_lease_root,
        candidate_evidence_root=state.candidate_evidence_root,
        candidate_challenge_root=state.candidate_challenge_root,
        candidate_lease_root=state.candidate_lease_root,
        stop_resolution_root=state.stop_resolution_root,
        permission_root=state.permission_root,
        window_state_ref=liveness_input.window_state_ref,
        window_root=state.window_root,
        sealed_window=liveness_input.sealed_window,
        seal_ref=liveness_input.seal_ref,
        sealed_at_step=liveness_input.sealed_at_step,
        heartbeat_continuous=liveness_input.heartbeat_continuous,
        heartbeat_sequence=liveness_input.heartbeat_sequence,
        previous_progress_ref=liveness_input.previous_progress_ref,
        candidate_id=candidate,
        reason_codes=tuple(reasons),
        assessment_ref=liveness_input.assessment_ref,
        certificate_ref=certificate,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
    )


def _window_reset_reason(
    state: CommitWindowState,
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
    if manifest_root != state.manifest_root or commit_policy_root != state.commit_policy_root:
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
    record: DecisionProgress | DecisionOutcome,
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


def _validate_decision_progress(progress: DecisionProgress) -> None:
    if type(progress.phase) is not DecisionPhase:
        raise GovernanceError("decision progress phase is invalid")
    if type(progress.assurance) is not CommitAssurance:
        raise GovernanceError("decision progress assurance is invalid")
    _validate_profile_assurance(
        progress.profile,
        progress.assurance,
        field_name="decision progress",
    )
    require_commit_fingerprint(
        progress.manifest_root,
        "decision progress manifest_root",
    )
    require_commit_fingerprint(
        progress.commit_policy_root,
        "decision progress commit_policy_root",
    )
    _require_binding(progress.protocol_id, "decision progress protocol id")
    _require_binding(progress.run_id, "decision progress run id")
    _require_binding(progress.target, "decision progress target")
    for name, value in (
        ("epoch", progress.epoch),
        ("current step", progress.current_step),
        ("absolute deadline step", progress.absolute_deadline_step),
        ("absolute run deadline step", progress.absolute_run_deadline_step),
        ("remaining reset budget", progress.remaining_reset_budget),
        ("remaining epoch restart budget", progress.remaining_epoch_restart_budget),
        ("minimum stability steps", progress.minimum_stability_steps),
        ("window count", progress.window_count),
    ):
        _require_non_negative_integer(value, f"decision progress {name}")
    if progress.current_step >= progress.absolute_deadline_step:
        raise GovernanceError(
            "decision progress cannot exist at or after the absolute deadline"
        )
    if progress.current_step >= progress.absolute_run_deadline_step:
        raise GovernanceError(
            "decision progress cannot exist at or after the run deadline"
        )
    if progress.minimum_stability_steps <= 0:
        raise GovernanceError(
            "decision progress minimum stability steps must be positive"
        )
    if progress.absolute_deadline_step > progress.absolute_run_deadline_step:
        raise GovernanceError(
            "decision progress deadline exceeds the absolute run deadline"
        )
    if progress.leader_candidate_id:
        require_commit_text(
            progress.leader_candidate_id,
            "decision progress leader candidate",
        )
    if progress.assessment_ref:
        require_commit_fingerprint(
            progress.assessment_ref,
            "decision progress assessment ref",
        )
    for name in (
        "risk_assessment_root",
        "membership_root",
        "threshold_root",
        "replay_state_ref",
        "replay_root",
        "window_state_ref",
        "window_root",
    ):
        require_commit_fingerprint(
            getattr(progress, name),
            f"decision progress {name}",
        )
    if progress.context_ref:
        require_commit_fingerprint(
            progress.context_ref,
            "decision progress context_ref",
        )
    if bool(progress.assessment_ref) is not bool(progress.context_ref):
        raise GovernanceError(
            "decision progress assessment and context lineage must co-exist"
        )
    _validate_assessment_lineage_roots(
        progress,
        has_assessment=bool(progress.assessment_ref),
        field_name="decision progress",
    )
    _validate_sealed_heartbeat_lineage(
        progress,
        field_name="decision progress",
    )
    if not progress.heartbeat_continuous:
        raise GovernanceError("decision progress requires a continuous heartbeat")
    if progress.terminal is not False:
        raise GovernanceError("decision progress cannot be terminal")
    if not progress.next_required_inputs and not progress.unmet_gates:
        raise GovernanceError(
            "decision progress must identify a required input or unmet gate"
        )


def _validate_decision_outcome(outcome: DecisionOutcome) -> None:
    if type(outcome.kind) is not DecisionOutcomeKind:
        raise GovernanceError("decision outcome kind is invalid")
    if type(outcome.assurance) is not CommitAssurance:
        raise GovernanceError("decision outcome assurance is invalid")
    if type(outcome.authority_scope) is not AuthorityScope:
        raise GovernanceError("decision outcome authority scope is invalid")
    _validate_profile_assurance(
        outcome.profile,
        outcome.assurance,
        field_name="decision outcome",
    )
    require_commit_fingerprint(
        outcome.manifest_root,
        "decision outcome manifest_root",
    )
    require_commit_fingerprint(
        outcome.commit_policy_root,
        "decision outcome commit_policy_root",
    )
    _require_binding(outcome.protocol_id, "decision outcome protocol id")
    _require_binding(outcome.run_id, "decision outcome run id")
    _require_binding(outcome.target, "decision outcome target")
    _require_non_negative_integer(outcome.epoch, "decision outcome epoch")
    _require_non_negative_integer(
        outcome.current_step,
        "decision outcome current step",
    )
    _require_non_negative_integer(
        outcome.absolute_deadline_step,
        "decision outcome absolute deadline step",
    )
    _require_non_negative_integer(
        outcome.absolute_run_deadline_step,
        "decision outcome absolute run deadline step",
    )
    if outcome.absolute_deadline_step > outcome.absolute_run_deadline_step:
        raise GovernanceError(
            "decision outcome deadline exceeds the absolute run deadline"
        )
    for name, value in (
        ("authoritative_commit", outcome.authoritative_commit),
        ("epistemically_committed", outcome.epistemically_committed),
        ("delivery_eligible", outcome.delivery_eligible),
        ("publication_eligible", outcome.publication_eligible),
        ("execution_eligible", outcome.execution_eligible),
    ):
        if type(value) is not bool:
            raise GovernanceError(f"decision outcome {name} must be a boolean")
    if outcome.terminal is not True:
        raise GovernanceError("decision outcome must be terminal")
    if not outcome.delivery_eligible:
        raise GovernanceError("terminal decision outcome must be deliverable")
    if outcome.candidate_id:
        require_commit_text(outcome.candidate_id, "decision outcome candidate")
    if outcome.assessment_ref:
        require_commit_fingerprint(
            outcome.assessment_ref,
            "decision outcome assessment ref",
        )
    for name in (
        "risk_assessment_root",
        "membership_root",
        "threshold_root",
        "replay_state_ref",
        "replay_root",
        "window_state_ref",
        "window_root",
    ):
        require_commit_fingerprint(
            getattr(outcome, name),
            f"decision outcome {name}",
        )
    if outcome.context_ref:
        require_commit_fingerprint(
            outcome.context_ref,
            "decision outcome context_ref",
        )
    if bool(outcome.assessment_ref) is not bool(outcome.context_ref):
        raise GovernanceError(
            "decision outcome assessment and context lineage must co-exist"
        )
    _validate_assessment_lineage_roots(
        outcome,
        has_assessment=bool(outcome.assessment_ref),
        field_name="decision outcome",
    )
    _validate_sealed_heartbeat_lineage(
        outcome,
        field_name="decision outcome",
    )
    if outcome.certificate_ref:
        require_commit_fingerprint(
            outcome.certificate_ref,
            "decision outcome certificate ref",
        )
    if not outcome.reason_codes:
        raise GovernanceError("decision outcome requires at least one reason code")
    if (
        "deadline_reached" in outcome.reason_codes
        and outcome.current_step < outcome.absolute_deadline_step
    ):
        raise GovernanceError(
            "deadline outcome cannot be issued before the absolute deadline"
        )

    if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        if outcome.assurance is CommitAssurance.ADVISORY:
            raise GovernanceError("advisory assurance cannot issue an evidence commit")
        if not outcome.authoritative_commit or not outcome.epistemically_committed:
            raise GovernanceError(
                "evidence commit outcome must carry epistemic commit authority"
            )
        expected_scope = COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE[outcome.assurance.value]
        if outcome.authority_scope.value != expected_scope:
            raise GovernanceError(
                "evidence commit authority scope does not match assurance"
            )
        if not outcome.candidate_id:
            raise GovernanceError("evidence commit candidate is required")
        if not outcome.assessment_ref:
            raise GovernanceError("evidence commit assessment_ref is required")
        if not outcome.certificate_ref:
            raise GovernanceError(
                "evidence commit requires its assurance-specific commit proof"
            )
        if not outcome.sealed_window or not outcome.heartbeat_continuous:
            raise GovernanceError(
                "evidence commit requires continuous sealed-window authority"
            )
    else:
        if outcome.authoritative_commit or outcome.epistemically_committed:
            raise GovernanceError(
                "non-commit outcome cannot carry epistemic commit authority"
            )
        if outcome.execution_eligible:
            raise GovernanceError("non-commit outcome cannot authorize execution")

    if outcome.kind in {
        DecisionOutcomeKind.INVALID,
        DecisionOutcomeKind.FINALITY_UNAVAILABLE,
        DecisionOutcomeKind.SAFETY_VIOLATION,
    } and outcome.publication_eligible:
        raise GovernanceError(
            f"{outcome.kind.value} outcome cannot authorize publication"
        )
    if outcome.kind is DecisionOutcomeKind.BLOCKED:
        if outcome.authority_scope is not AuthorityScope.DENIAL:
            raise GovernanceError("blocked outcome must use denial authority scope")
    elif outcome.kind is not DecisionOutcomeKind.EVIDENCE_COMMIT:
        if outcome.authority_scope is not AuthorityScope.NONE:
            raise GovernanceError(
                "non-commit outcome must use the none authority scope"
            )
    elif outcome.authority_scope is AuthorityScope.DENIAL:
        raise GovernanceError("denial authority scope is reserved for blocked outcome")
    if (
        outcome.kind is DecisionOutcomeKind.SAFE_FALLBACK
        and not outcome.candidate_id
    ):
        raise GovernanceError("safe fallback candidate is required")


def _progress_snapshot(progress: DecisionProgress) -> str:
    return commit_payload_fingerprint(
        decision_progress_payload(progress),
        schema="pheroos-decision-progress-v1",
        profile=progress.profile,
    )


def _outcome_snapshot(outcome: DecisionOutcome) -> str:
    return commit_payload_fingerprint(
        decision_outcome_payload(outcome),
        schema="pheroos-decision-outcome-v1",
        profile=outcome.profile,
    )


def decision_progress_payload(progress: DecisionProgress) -> dict[str, object]:
    if type(progress) is not DecisionProgress:
        raise GovernanceError("decision progress must use the canonical record")
    _validate_decision_progress(progress)
    return {
        "assurance": progress.assurance,
        "absolute_deadline_step": progress.absolute_deadline_step,
        "absolute_run_deadline_step": progress.absolute_run_deadline_step,
        "assessment_ref": progress.assessment_ref,
        "candidate_challenge_root": progress.candidate_challenge_root,
        "candidate_evidence_root": progress.candidate_evidence_root,
        "candidate_lease_root": progress.candidate_lease_root,
        "collective_challenge_root": progress.collective_challenge_root,
        "collective_evidence_root": progress.collective_evidence_root,
        "collective_lease_root": progress.collective_lease_root,
        "commit_policy_root": progress.commit_policy_root,
        "context_ref": progress.context_ref,
        "current_step": progress.current_step,
        "epoch": progress.epoch,
        "leader_candidate_id": progress.leader_candidate_id,
        "manifest_root": progress.manifest_root,
        "membership_root": progress.membership_root,
        "membership_epoch_state_root": progress.membership_epoch_state_root,
        "membership_snapshot_root": progress.membership_snapshot_root,
        "minimum_stability_steps": progress.minimum_stability_steps,
        "next_required_inputs": progress.next_required_inputs,
        "phase": progress.phase,
        "permission_root": progress.permission_root,
        "profile": progress.profile,
        "protocol_id": progress.protocol_id,
        "remaining_epoch_restart_budget": progress.remaining_epoch_restart_budget,
        "remaining_reset_budget": progress.remaining_reset_budget,
        "replay_root": progress.replay_root,
        "replay_state_ref": progress.replay_state_ref,
        "risk_assessment_root": progress.risk_assessment_root,
        "risk_chain_state_root": progress.risk_chain_state_root,
        "risk_policy_root": progress.risk_policy_root,
        "run_id": progress.run_id,
        "sealed_window": progress.sealed_window,
        "seal_ref": progress.seal_ref,
        "sealed_at_step": progress.sealed_at_step,
        "heartbeat_continuous": progress.heartbeat_continuous,
        "heartbeat_sequence": progress.heartbeat_sequence,
        "previous_progress_ref": progress.previous_progress_ref,
        "target": progress.target,
        "stop_resolution_root": progress.stop_resolution_root,
        "support_replay_root": progress.support_replay_root,
        "support_replay_state_root": progress.support_replay_state_root,
        "terminal": progress.terminal,
        "threshold_root": progress.threshold_root,
        "unmet_gates": progress.unmet_gates,
        "window_count": progress.window_count,
        "window_root": progress.window_root,
        "window_state_ref": progress.window_state_ref,
    }


def decision_outcome_payload(outcome: DecisionOutcome) -> dict[str, object]:
    if type(outcome) is not DecisionOutcome:
        raise GovernanceError("decision outcome must use the canonical record")
    _validate_decision_outcome(outcome)
    return {
        "assurance": outcome.assurance,
        "absolute_deadline_step": outcome.absolute_deadline_step,
        "absolute_run_deadline_step": outcome.absolute_run_deadline_step,
        "assessment_ref": outcome.assessment_ref,
        "authoritative_commit": outcome.authoritative_commit,
        "authority_scope": outcome.authority_scope,
        "candidate_id": outcome.candidate_id,
        "candidate_challenge_root": outcome.candidate_challenge_root,
        "candidate_evidence_root": outcome.candidate_evidence_root,
        "candidate_lease_root": outcome.candidate_lease_root,
        "certificate_ref": outcome.certificate_ref,
        "collective_challenge_root": outcome.collective_challenge_root,
        "collective_evidence_root": outcome.collective_evidence_root,
        "collective_lease_root": outcome.collective_lease_root,
        "commit_policy_root": outcome.commit_policy_root,
        "context_ref": outcome.context_ref,
        "current_step": outcome.current_step,
        "delivery_eligible": outcome.delivery_eligible,
        "epistemically_committed": outcome.epistemically_committed,
        "epoch": outcome.epoch,
        "execution_eligible": outcome.execution_eligible,
        "kind": outcome.kind,
        "manifest_root": outcome.manifest_root,
        "membership_root": outcome.membership_root,
        "membership_epoch_state_root": outcome.membership_epoch_state_root,
        "membership_snapshot_root": outcome.membership_snapshot_root,
        "profile": outcome.profile,
        "permission_root": outcome.permission_root,
        "protocol_id": outcome.protocol_id,
        "publication_eligible": outcome.publication_eligible,
        "reason_codes": outcome.reason_codes,
        "replay_root": outcome.replay_root,
        "replay_state_ref": outcome.replay_state_ref,
        "risk_assessment_root": outcome.risk_assessment_root,
        "risk_chain_state_root": outcome.risk_chain_state_root,
        "risk_policy_root": outcome.risk_policy_root,
        "run_id": outcome.run_id,
        "sealed_window": outcome.sealed_window,
        "seal_ref": outcome.seal_ref,
        "sealed_at_step": outcome.sealed_at_step,
        "heartbeat_continuous": outcome.heartbeat_continuous,
        "heartbeat_sequence": outcome.heartbeat_sequence,
        "previous_progress_ref": outcome.previous_progress_ref,
        "target": outcome.target,
        "stop_resolution_root": outcome.stop_resolution_root,
        "support_replay_root": outcome.support_replay_root,
        "support_replay_state_root": outcome.support_replay_state_root,
        "terminal": outcome.terminal,
        "threshold_root": outcome.threshold_root,
        "window_root": outcome.window_root,
        "window_state_ref": outcome.window_state_ref,
    }


def decision_progress_fingerprint(progress: DecisionProgress) -> str:
    return _progress_snapshot(progress)


def decision_outcome_fingerprint(outcome: DecisionOutcome) -> str:
    return _outcome_snapshot(outcome)


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


def _validate_profile_assurance(
    profile: object,
    assurance: CommitAssurance,
    *,
    field_name: str,
) -> None:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")


__all__ = [
    "AuthorityScope",
    "CommitAssurance",
    "CommitFinalityStatus",
    "CommitFinalityVerification",
    "CommitLivenessInput",
    "CommitReplayState",
    "CommitWindowSeal",
    "CommitWindowState",
    "DecisionOutcome",
    "DecisionOutcomeKind",
    "DecisionPhase",
    "DecisionProgress",
    "ReplayNamespace",
    "ReplayReceipt",
    "advance_commit_window_state",
    "commit_replay_state_fingerprint",
    "commit_replay_state_is_authoritative",
    "commit_replay_state_is_current",
    "commit_replay_state_contains",
    "commit_replay_state_matches",
    "commit_replay_state_payload",
    "commit_liveness_input_fingerprint",
    "commit_liveness_input_is_authoritative",
    "commit_liveness_input_payload",
    "commit_finality_verification_fingerprint",
    "commit_finality_verification_is_authoritative",
    "commit_finality_verification_payload",
    "commit_window_ready",
    "commit_window_seal_fingerprint",
    "commit_window_seal_for_state",
    "commit_window_seal_is_authoritative",
    "commit_window_seal_is_current",
    "commit_window_seal_matches_receipt",
    "commit_window_seal_payload",
    "commit_window_state_fingerprint",
    "commit_window_state_is_authoritative",
    "commit_window_state_is_current",
    "commit_window_state_payload",
    "decision_outcome_fingerprint",
    "decision_outcome_is_authoritative",
    "decision_outcome_payload",
    "decision_progress_fingerprint",
    "decision_progress_is_authoritative",
    "decision_progress_payload",
    "initialize_commit_replay_state",
    "initialize_commit_window_state",
    "issue_commit_liveness_input",
    "record_commit_replay_receipts",
    "reduce_commit_liveness",
    "reset_commit_window_state",
    "replay_receipt_fingerprint",
    "replay_receipt_payload",
    "restart_commit_window_epoch",
    "select_terminal_outcome_kind",
]
