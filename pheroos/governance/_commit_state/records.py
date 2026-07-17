from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

from pheroos.governance._commit_state.invariants import (
    _normalized_labels,
    _normalized_window_bindings,
    _require_binding,
    _require_non_negative_integer,
    _validate_bound_commit_policy,
    _validate_commit_binding_values,
    _validate_profile_assurance,
)
from pheroos.governance._commit_state._liveness_contract import (
    _validate_assessment_lineage_roots,
    _validate_sealed_heartbeat_lineage,
)
from pheroos.governance._commit_state.payloads import (
    build_commit_liveness_input_payload,
    build_commit_window_state_payload,
    build_decision_outcome_payload,
    build_decision_progress_payload,
)
from pheroos.governance._commit_state._replay_contract import (
    canonical_replay_receipts as _canonical_replay_receipts_engine,
)
from pheroos.governance._commit_state._window_contract import _window_root
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.common import AuthorityScope
from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)


_DECISION_PROGRESS_ISSUANCE = object()
_DECISION_OUTCOME_ISSUANCE = object()
_COMMIT_WINDOW_STATE_ISSUANCE = object()
_COMMIT_WINDOW_SEAL_ISSUANCE = object()
_COMMIT_REPLAY_STATE_ISSUANCE = object()
_COMMIT_LIVENESS_INPUT_ISSUANCE = object()
_COMMIT_FINALITY_VERIFICATION_ISSUANCE = object()

_LEGACY_COMMIT_WINDOW_CURSORS = "legacy.commit.window_cursors"
_LEGACY_COMMIT_REPLAY_CURSORS = "legacy.commit.replay_cursors"


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
        self.transitions: dict[str, tuple[str, CommitWindowState]] = {}
        self.liveness_inputs: dict[str, tuple[str, CommitLivenessInput]] = {}
        self.liveness_results: dict[
            tuple[str, int],
            tuple[str, DecisionProgress | DecisionOutcome],
        ] = {}
        self.current_progress: DecisionProgress | None = None
        self.current_progress_fingerprint = ""
        self.terminal_result: DecisionOutcome | None = None
        self.lock = RLock()


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
        and cursor.current_state_fingerprint == commit_replay_state_fingerprint(state)
    )


def commit_window_state_payload(state: CommitWindowState) -> dict[str, object]:
    if type(state) is not CommitWindowState:
        raise GovernanceError("commit window state must use the canonical record")
    _validate_commit_window_state(state)
    return build_commit_window_state_payload(state)


def commit_window_state_fingerprint(state: CommitWindowState) -> str:
    return commit_payload_fingerprint(
        commit_window_state_payload(state),
        schema="pheroos-commit-window-state-v1",
        profile=state.profile,
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
            raise GovernanceError("initial commit window cannot declare a predecessor")
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
        raise GovernanceError("commit liveness leader readiness must be boolean")
    if value.leader_ready_for_stability and not value.leader_candidate_id:
        raise GovernanceError("commit liveness ready leader requires a candidate")
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
        raise GovernanceError("initial commit liveness heartbeat sequence must be zero")
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
    return _canonical_replay_receipts_engine(
        receipts,
        receipt_type=ReplayReceipt,
        validate_receipt=_validate_replay_receipt,
        receipt_fingerprint=replay_receipt_fingerprint,
    )


def _commit_replay_receipt_root(
    receipts: Sequence[ReplayReceipt],
    *,
    profile: str,
) -> str:
    normalized = _canonical_replay_receipts(receipts)
    return commit_payload_fingerprint(
        {
            "receipt_fingerprints": tuple(
                replay_receipt_fingerprint(item, profile=profile) for item in normalized
            )
        },
        schema="pheroos-commit-replay-receipt-root-v1",
        profile=profile,
    )


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

    if (
        outcome.kind
        in {
            DecisionOutcomeKind.INVALID,
            DecisionOutcomeKind.FINALITY_UNAVAILABLE,
            DecisionOutcomeKind.SAFETY_VIOLATION,
        }
        and outcome.publication_eligible
    ):
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
    if outcome.kind is DecisionOutcomeKind.SAFE_FALLBACK and not outcome.candidate_id:
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
    return build_decision_progress_payload(progress)


def decision_outcome_payload(outcome: DecisionOutcome) -> dict[str, object]:
    if type(outcome) is not DecisionOutcome:
        raise GovernanceError("decision outcome must use the canonical record")
    _validate_decision_outcome(outcome)
    return build_decision_outcome_payload(outcome)


def decision_progress_fingerprint(progress: DecisionProgress) -> str:
    return _progress_snapshot(progress)


def decision_outcome_fingerprint(outcome: DecisionOutcome) -> str:
    return _outcome_snapshot(outcome)


for _name in (
    "DecisionPhase",
    "DecisionOutcomeKind",
    "CommitFinalityStatus",
    "ReplayNamespace",
    "DecisionProgress",
    "DecisionOutcome",
    "CommitWindowState",
    "CommitWindowSeal",
    "CommitLivenessInput",
    "CommitFinalityVerification",
    "ReplayReceipt",
    "CommitReplayState",
    "decision_progress_is_authoritative",
    "decision_outcome_is_authoritative",
    "commit_finality_verification_payload",
    "commit_finality_verification_fingerprint",
    "commit_finality_verification_is_authoritative",
    "commit_window_state_is_authoritative",
    "commit_window_state_is_current",
    "commit_replay_state_is_authoritative",
    "commit_replay_state_is_current",
    "commit_window_state_payload",
    "commit_window_state_fingerprint",
    "replay_receipt_payload",
    "replay_receipt_fingerprint",
    "commit_replay_state_contains",
    "commit_replay_state_matches",
    "commit_replay_state_payload",
    "commit_replay_state_fingerprint",
    "decision_progress_payload",
    "decision_outcome_payload",
    "decision_progress_fingerprint",
    "decision_outcome_fingerprint",
):
    globals()[_name].__module__ = "pheroos.governance.commit_state"
del _name
