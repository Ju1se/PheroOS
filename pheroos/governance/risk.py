from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    commit_payload_fingerprint,
    require_scaled_integer,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    SUPPORTED_RISK_BANDS,
    CollectiveCommitPolicy,
    CommitAssurance,
    RiskBandPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_risk_bands


_RISK_ASSESSMENT_ISSUANCE = object()
_RISK_ASSESSMENT_CHAIN_STATE_ISSUANCE = object()
_COMMIT_THRESHOLD_ISSUANCE = object()


class RiskBand(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_RISK_ORDER = {band: index for index, band in enumerate(RiskBand)}
_RISK_ORDER_BY_VALUE = {band.value: index for band, index in _RISK_ORDER.items()}


class _RiskAssessmentChainCursor:
    """Process-local linear capability behind immutable issued chain states.

    The public state records remain frozen and fingerprinted.  This private cursor
    makes a state a one-shot transition capability: after a successful advance,
    reuse with the same request is idempotent and reuse with any different request
    is a fork.  The lock makes that rule atomic for concurrent local callers.
    """

    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "chain_id",
        "current_state_fingerprint",
        "current_state",
        "transitions",
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
        self.current_state_fingerprint = ""
        self.current_state: RiskAssessmentChainState | None = None
        self.transitions: dict[
            str,
            tuple[str, RiskAssessment, RiskAssessmentChainState],
        ] = {}
        self.lock = RLock()


_RISK_CHAIN_REGISTRY_LOCK = RLock()
_RISK_CHAIN_CURSORS: dict[str, _RiskAssessmentChainCursor] = {}


@dataclass(frozen=True)
class RiskAssessmentChainState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    revision: int
    latest_assessment_fingerprint: str
    latest_risk_band: str
    initialized_at_step: int
    last_issued_at_step: int
    expires_at_step: int
    previous_state_fingerprint: str
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
        _validate_risk_assessment_chain_state_shape(self)


@dataclass(frozen=True)
class RiskAssessment:
    assessment_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    risk_chain_id: str
    risk_chain_revision: int
    previous_chain_state_fingerprint: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    risk_band: RiskBand
    risk_input_fingerprints: tuple[str, ...]
    rationale_codes: tuple[str, ...]
    assessment_method: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    previous_assessment_fingerprint: str
    window_reset_required: bool
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "risk_input_fingerprints",
            _canonical_fingerprints(
                self.risk_input_fingerprints,
                "risk assessment input fingerprints",
            ),
        )
        object.__setattr__(
            self,
            "rationale_codes",
            require_commit_labels(
                self.rationale_codes,
                "risk assessment rationale_codes",
            ),
        )
        _validate_risk_assessment_shape(self)


@dataclass(frozen=True)
class CommitThresholdSnapshot:
    threshold_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    risk_policy_root: str
    risk_chain_id: str
    risk_chain_revision: int
    risk_chain_state_fingerprint: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    risk_assessment_fingerprint: str
    risk_band: RiskBand
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    minimum_support_clusters: int
    minimum_support_ratio_ppm: int
    minimum_source_diversity: int
    minimum_margin: int
    stability_steps: int
    required_challenge_categories: tuple[str, ...]
    minimum_assurance: CommitAssurance
    publishable_outcomes: tuple[str, ...]
    executable_outcomes: tuple[str, ...]
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_challenge_categories",
            require_commit_labels(
                self.required_challenge_categories,
                "commit threshold required challenge categories",
            ),
        )
        object.__setattr__(
            self,
            "publishable_outcomes",
            require_commit_labels(
                self.publishable_outcomes,
                "commit threshold publishable outcomes",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "executable_outcomes",
            require_commit_labels(
                self.executable_outcomes,
                "commit threshold executable outcomes",
                allow_empty=True,
            ),
        )
        _validate_threshold_snapshot_shape(self)


def initialize_risk_assessment_chain(
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
    issuer_id: str,
    authority: AuthorityLevel,
    initialized_at_step: int,
    expires_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> RiskAssessmentChainState:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "risk assessment chain initialization requires governance authority"
        )
    bindings = _normalized_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name="risk assessment chain",
    )
    risk_root = _validate_policy_binding(commit_policy, bindings)
    initialized = require_commit_step(
        initialized_at_step,
        "risk assessment chain initialized_at_step",
    )
    expires = require_commit_step(
        expires_at_step,
        "risk assessment chain expires_at_step",
    )
    if expires <= initialized:
        raise GovernanceError("risk assessment chain expiry must be after initialization")
    normalized_issuer = require_commit_text(
        issuer_id,
        "risk assessment chain issuer_id",
    )
    normalized_provenance = require_commit_text(
        provenance,
        "risk assessment chain provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "risk assessment chain trace_event_id",
    )
    authority_key = commit_payload_fingerprint(
        {
            **bindings,
            "risk_policy_root": risk_root,
        },
        schema="pheroos-risk-assessment-chain-authority-key-v1",
        profile=str(bindings["profile"]),
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority_key": authority_key,
            "authority": authority,
            "expires_at_step": expires,
            "initialized_at_step": initialized,
            "issuer_id": normalized_issuer,
            "provenance": normalized_provenance,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-risk-assessment-chain-base-v1",
        profile=str(bindings["profile"]),
    )
    with _RISK_CHAIN_REGISTRY_LOCK:
        cursor = _RISK_CHAIN_CURSORS.get(authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "risk assessment chain authority already has a different base"
                )
            current_state = cursor.current_state
            if (
                type(current_state) is not RiskAssessmentChainState
                or not risk_assessment_chain_state_is_current(current_state)
            ):
                raise GovernanceError(
                    "risk assessment chain current state is unavailable; "
                    "reinitialization is forbidden"
                )
            return current_state

        cursor = _RiskAssessmentChainCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
            chain_id=authority_key,
        )
        state = RiskAssessmentChainState(
            chain_id=authority_key,
            profile=str(bindings["profile"]),
            assurance=bindings["assurance"],
            manifest_root=str(bindings["manifest_root"]),
            commit_policy_root=str(bindings["commit_policy_root"]),
            risk_policy_root=risk_root,
            protocol_id=str(bindings["protocol_id"]),
            run_id=str(bindings["run_id"]),
            target=str(bindings["target"]),
            epoch=int(bindings["epoch"]),
            revision=0,
            latest_assessment_fingerprint="",
            latest_risk_band="",
            initialized_at_step=initialized,
            last_issued_at_step=initialized,
            expires_at_step=expires,
            previous_state_fingerprint="",
            issuer_id=normalized_issuer,
            authority=authority,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_risk_assessment_chain_state(state, cursor)
        cursor.current_state_fingerprint = (
            risk_assessment_chain_state_fingerprint(state)
        )
        cursor.current_state = state
        _RISK_CHAIN_CURSORS[authority_key] = cursor
        return state


def issue_risk_assessment(
    chain_state: RiskAssessmentChainState,
    *,
    assessment_id: str,
    risk_band: RiskBand,
    risk_input_fingerprints: Sequence[str],
    rationale_codes: Sequence[str],
    assessment_method: str,
    commit_policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    expires_at_step: int,
    provenance: str,
    trace_event_id: str,
    previous_assessment: RiskAssessment | None = None,
) -> tuple[RiskAssessment, RiskAssessmentChainState]:
    if type(risk_band) is not RiskBand:
        raise GovernanceError("risk assessment band must use the fixed RiskBand ABI")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("risk assessment issuance requires governance authority")
    bindings = _normalized_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name="risk assessment",
    )
    risk_root = _validate_policy_binding(commit_policy, bindings)
    if not risk_assessment_chain_state_is_authoritative(chain_state):
        raise GovernanceError("risk assessment chain state is not authoritative")
    if not _record_bindings_equal(chain_state, bindings):
        raise GovernanceError("risk assessment chain binding mismatch")
    if chain_state.risk_policy_root != risk_root:
        raise GovernanceError("risk assessment chain policy root mismatch")
    issued = require_commit_step(issued_at_step, "risk assessment issued_at_step")
    expires = require_commit_step(expires_at_step, "risk assessment expires_at_step")
    if expires != chain_state.expires_at_step:
        raise GovernanceError(
            "risk assessment cannot extend or alter the frozen expiry of its chain"
        )
    if expires <= issued:
        raise GovernanceError("risk assessment expiry must be after issuance")

    previous_fingerprint = ""
    reset_required = False
    if chain_state.revision == 0:
        if previous_assessment is not None:
            raise GovernanceError(
                "initial risk assessment cannot declare a predecessor"
            )
        if issued < chain_state.initialized_at_step:
            raise GovernanceError(
                "initial risk assessment predates its authoritative chain"
            )
    else:
        if previous_assessment is None:
            raise GovernanceError(
                "risk reassessment requires the authoritative latest predecessor"
            )
        if not risk_assessment_is_authoritative(previous_assessment):
            raise GovernanceError("previous risk assessment is not authoritative")
        if not _risk_assessment_is_head_of_state(
            previous_assessment,
            chain_state,
        ):
            raise GovernanceError(
                "previous risk assessment is not the chain head"
            )
        if issued <= chain_state.last_issued_at_step:
            raise GovernanceError(
                "risk reassessment must advance the logical issuance step"
            )
        if _RISK_ORDER[risk_band] < _RISK_ORDER[previous_assessment.risk_band]:
            raise GovernanceError("risk cannot decrease within an epoch")
        previous_fingerprint = risk_assessment_fingerprint(previous_assessment)
        reset_required = risk_band is not previous_assessment.risk_band

    parent_state_fingerprint = risk_assessment_chain_state_fingerprint(chain_state)
    assessment = RiskAssessment(
        assessment_id=require_commit_text(
            assessment_id,
            "risk assessment assessment_id",
        ),
        profile=bindings["profile"],
        assurance=bindings["assurance"],
        manifest_root=bindings["manifest_root"],
        commit_policy_root=bindings["commit_policy_root"],
        risk_policy_root=risk_root,
        risk_chain_id=chain_state.chain_id,
        risk_chain_revision=chain_state.revision + 1,
        previous_chain_state_fingerprint=parent_state_fingerprint,
        protocol_id=bindings["protocol_id"],
        run_id=bindings["run_id"],
        target=bindings["target"],
        epoch=bindings["epoch"],
        risk_band=risk_band,
        risk_input_fingerprints=tuple(risk_input_fingerprints),
        rationale_codes=tuple(rationale_codes),
        assessment_method=require_commit_text(
            assessment_method,
            "risk assessment method",
        ),
        issuer_id=require_commit_text(issuer_id, "risk assessment issuer_id"),
        authority=authority,
        issued_at_step=issued,
        expires_at_step=expires,
        previous_assessment_fingerprint=previous_fingerprint,
        window_reset_required=reset_required,
        provenance=require_commit_text(provenance, "risk assessment provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "risk assessment trace_event_id",
        ),
    )
    object.__setattr__(
        assessment,
        "_issuance",
        (_RISK_ASSESSMENT_ISSUANCE, _risk_assessment_snapshot(assessment)),
    )
    assessment_fingerprint = risk_assessment_fingerprint(assessment)
    cursor = chain_state._cursor
    if type(cursor) is not _RiskAssessmentChainCursor:
        raise GovernanceError("risk assessment chain cursor is invalid")
    request_fingerprint = commit_payload_fingerprint(
        {
            "assessment_fingerprint": assessment_fingerprint,
            "parent_state_fingerprint": parent_state_fingerprint,
        },
        schema="pheroos-risk-assessment-transition-request-v1",
        profile=chain_state.profile,
    )
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_state_fingerprint:
            prior = cursor.transitions.get(parent_state_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1], prior[2]
            raise GovernanceError(
                "risk assessment chain state is stale or would fork"
            )

        next_state = RiskAssessmentChainState(
            chain_id=chain_state.chain_id,
            profile=chain_state.profile,
            assurance=chain_state.assurance,
            manifest_root=chain_state.manifest_root,
            commit_policy_root=chain_state.commit_policy_root,
            risk_policy_root=chain_state.risk_policy_root,
            protocol_id=chain_state.protocol_id,
            run_id=chain_state.run_id,
            target=chain_state.target,
            epoch=chain_state.epoch,
            revision=chain_state.revision + 1,
            latest_assessment_fingerprint=assessment_fingerprint,
            latest_risk_band=risk_band.value,
            initialized_at_step=chain_state.initialized_at_step,
            last_issued_at_step=issued,
            expires_at_step=chain_state.expires_at_step,
            previous_state_fingerprint=parent_state_fingerprint,
            issuer_id=assessment.issuer_id,
            authority=authority,
            provenance=assessment.provenance,
            trace_event_id=assessment.trace_event_id,
        )
        next_state = _issue_risk_assessment_chain_state(next_state, cursor)
        next_state_fingerprint = risk_assessment_chain_state_fingerprint(next_state)
        cursor.current_state_fingerprint = next_state_fingerprint
        cursor.current_state = next_state
        cursor.transitions[parent_state_fingerprint] = (
            request_fingerprint,
            assessment,
            next_state,
        )
        return assessment, next_state


def risk_assessment_chain_state_is_authoritative(state: object) -> bool:
    if type(state) is not RiskAssessmentChainState:
        return False
    try:
        _validate_risk_assessment_chain_state_shape(state)
        issuance = state._issuance
        cursor = state._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _RISK_ASSESSMENT_CHAIN_STATE_ISSUANCE
            and issuance[1] == _risk_assessment_chain_state_snapshot(state)
            and type(cursor) is _RiskAssessmentChainCursor
            and cursor.chain_id == state.chain_id
        )
    except Exception:
        return False


def risk_assessment_chain_state_is_current(state: object) -> bool:
    if not risk_assessment_chain_state_is_authoritative(state):
        return False
    assert type(state) is RiskAssessmentChainState
    cursor = state._cursor
    assert type(cursor) is _RiskAssessmentChainCursor
    try:
        with cursor.lock:
            return (
                cursor.current_state is state
                and cursor.current_state_fingerprint
                == risk_assessment_chain_state_fingerprint(state)
            )
    except Exception:
        return False


def risk_assessment_chain_state_payload(
    state: RiskAssessmentChainState,
) -> dict[str, object]:
    if type(state) is not RiskAssessmentChainState:
        raise GovernanceError("risk assessment chain state must be canonical")
    _validate_risk_assessment_chain_state_shape(state)
    return {
        "assurance": state.assurance,
        "authority": state.authority,
        "chain_id": state.chain_id,
        "commit_policy_root": state.commit_policy_root,
        "epoch": state.epoch,
        "expires_at_step": state.expires_at_step,
        "initialized_at_step": state.initialized_at_step,
        "issuer_id": state.issuer_id,
        "last_issued_at_step": state.last_issued_at_step,
        "latest_assessment_fingerprint": state.latest_assessment_fingerprint,
        "latest_risk_band": state.latest_risk_band,
        "manifest_root": state.manifest_root,
        "previous_state_fingerprint": state.previous_state_fingerprint,
        "profile": state.profile,
        "protocol_id": state.protocol_id,
        "provenance": state.provenance,
        "revision": state.revision,
        "risk_policy_root": state.risk_policy_root,
        "run_id": state.run_id,
        "target": state.target,
        "trace_event_id": state.trace_event_id,
    }


def risk_assessment_chain_state_fingerprint(
    state: RiskAssessmentChainState,
) -> str:
    return _risk_assessment_chain_state_snapshot(state)


def risk_assessment_is_authoritative(assessment: object) -> bool:
    if type(assessment) is not RiskAssessment:
        return False
    try:
        _validate_risk_assessment_shape(assessment)
        issuance = assessment._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _RISK_ASSESSMENT_ISSUANCE
            and issuance[1] == _risk_assessment_snapshot(assessment)
        )
    except Exception:
        return False


def risk_assessment_is_latest(
    assessment: RiskAssessment | None,
    *,
    chain_state: RiskAssessmentChainState | None,
) -> bool:
    try:
        return bool(
            assessment is not None
            and chain_state is not None
            and risk_assessment_is_authoritative(assessment)
            and risk_assessment_chain_state_is_current(chain_state)
            and _risk_assessment_is_head_of_state(assessment, chain_state)
        )
    except GovernanceError:
        return False


def risk_assessment_matches(
    assessment: RiskAssessment | None,
    *,
    chain_state: RiskAssessmentChainState | None,
    commit_policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    current_step: int,
) -> bool:
    try:
        bindings = _normalized_bindings(
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            field_name="expected risk assessment",
        )
        expected_risk_root = _validate_policy_binding(commit_policy, bindings)
        current = require_commit_step(current_step, "risk assessment current_step")
        return bool(
            risk_assessment_is_latest(
                assessment,
                chain_state=chain_state,
            )
            and assessment is not None
            and chain_state is not None
            and _record_bindings_equal(assessment, bindings)
            and _record_bindings_equal(chain_state, bindings)
            and assessment.risk_policy_root == expected_risk_root
            and chain_state.risk_policy_root == expected_risk_root
            and assessment.issued_at_step <= current < assessment.expires_at_step
        )
    except GovernanceError:
        return False


def risk_assessment_payload(assessment: RiskAssessment) -> dict[str, object]:
    if type(assessment) is not RiskAssessment:
        raise GovernanceError("risk assessment must use the canonical record")
    _validate_risk_assessment_shape(assessment)
    return {
        "assessment_id": assessment.assessment_id,
        "assessment_method": assessment.assessment_method,
        "assurance": assessment.assurance,
        "authority": assessment.authority,
        "commit_policy_root": assessment.commit_policy_root,
        "epoch": assessment.epoch,
        "expires_at_step": assessment.expires_at_step,
        "issued_at_step": assessment.issued_at_step,
        "issuer_id": assessment.issuer_id,
        "manifest_root": assessment.manifest_root,
        "previous_assessment_fingerprint": (
            assessment.previous_assessment_fingerprint
        ),
        "profile": assessment.profile,
        "protocol_id": assessment.protocol_id,
        "provenance": assessment.provenance,
        "rationale_codes": assessment.rationale_codes,
        "risk_band": assessment.risk_band,
        "risk_chain_id": assessment.risk_chain_id,
        "risk_chain_revision": assessment.risk_chain_revision,
        "risk_input_fingerprints": assessment.risk_input_fingerprints,
        "risk_policy_root": assessment.risk_policy_root,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "trace_event_id": assessment.trace_event_id,
        "window_reset_required": assessment.window_reset_required,
        "previous_chain_state_fingerprint": (
            assessment.previous_chain_state_fingerprint
        ),
    }


def risk_assessment_fingerprint(assessment: RiskAssessment) -> str:
    return _risk_assessment_snapshot(assessment)


def issue_commit_threshold_snapshot(
    assessment: RiskAssessment,
    *,
    chain_state: RiskAssessmentChainState,
    threshold_id: str,
    commit_policy: CollectiveCommitPolicy,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitThresholdSnapshot:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit threshold issuance requires governance authority")
    if not risk_assessment_is_latest(
        assessment,
        chain_state=chain_state,
    ):
        raise GovernanceError(
            "commit threshold issuance requires the authoritative latest risk assessment/state"
        )
    current = require_commit_step(current_step, "commit threshold current_step")
    if not risk_assessment_matches(
        assessment,
        chain_state=chain_state,
        commit_policy=commit_policy,
        profile=assessment.profile,
        assurance=assessment.assurance,
        manifest_root=assessment.manifest_root,
        commit_policy_root=assessment.commit_policy_root,
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        current_step=current,
    ):
        raise GovernanceError(
            "commit threshold risk assessment is stale or policy-mismatched"
        )
    band = commit_policy.risk_bands[assessment.risk_band.value]
    if type(band) is not RiskBandPolicy:  # guarded by policy validation
        raise GovernanceError("commit threshold risk band is not canonical")

    snapshot = CommitThresholdSnapshot(
        threshold_id=require_commit_text(
            threshold_id,
            "commit threshold threshold_id",
        ),
        profile=assessment.profile,
        assurance=assessment.assurance,
        manifest_root=assessment.manifest_root,
        commit_policy_root=assessment.commit_policy_root,
        risk_policy_root=assessment.risk_policy_root,
        risk_chain_id=chain_state.chain_id,
        risk_chain_revision=chain_state.revision,
        risk_chain_state_fingerprint=(
            risk_assessment_chain_state_fingerprint(chain_state)
        ),
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        risk_assessment_fingerprint=risk_assessment_fingerprint(assessment),
        risk_band=assessment.risk_band,
        minimum_positive_evidence=band.minimum_positive_evidence,
        maximum_counterevidence=band.maximum_counterevidence,
        maximum_counterevidence_ratio_ppm=(
            band.maximum_counterevidence_ratio_ppm
        ),
        minimum_support_clusters=band.minimum_support_clusters,
        minimum_support_ratio_ppm=band.minimum_support_ratio_ppm,
        minimum_source_diversity=band.minimum_source_diversity,
        minimum_margin=band.minimum_margin,
        stability_steps=band.stability_steps,
        required_challenge_categories=tuple(band.required_challenge_categories),
        minimum_assurance=CommitAssurance(band.minimum_assurance),
        publishable_outcomes=tuple(band.publishable_outcomes),
        executable_outcomes=tuple(band.executable_outcomes),
        issuer_id=require_commit_text(issuer_id, "commit threshold issuer_id"),
        authority=authority,
        issued_at_step=current,
        expires_at_step=assessment.expires_at_step,
        provenance=require_commit_text(provenance, "commit threshold provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit threshold trace_event_id",
        ),
    )
    object.__setattr__(
        snapshot,
        "_issuance",
        (_COMMIT_THRESHOLD_ISSUANCE, _threshold_snapshot(snapshot)),
    )
    return snapshot


def commit_threshold_snapshot_is_authoritative(snapshot: object) -> bool:
    if type(snapshot) is not CommitThresholdSnapshot:
        return False
    try:
        _validate_threshold_snapshot_shape(snapshot)
        issuance = snapshot._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_THRESHOLD_ISSUANCE
            and issuance[1] == _threshold_snapshot(snapshot)
        )
    except Exception:
        return False


def commit_threshold_snapshot_matches(
    snapshot: CommitThresholdSnapshot | None,
    *,
    assessment: RiskAssessment,
    chain_state: RiskAssessmentChainState,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
) -> bool:
    try:
        current = require_commit_step(current_step, "commit threshold current_step")
        if not risk_assessment_matches(
            assessment,
            chain_state=chain_state,
            commit_policy=commit_policy,
            profile=assessment.profile,
            assurance=assessment.assurance,
            manifest_root=assessment.manifest_root,
            commit_policy_root=assessment.commit_policy_root,
            protocol_id=assessment.protocol_id,
            run_id=assessment.run_id,
            target=assessment.target,
            epoch=assessment.epoch,
            current_step=current,
        ):
            return False
        if not commit_threshold_snapshot_is_authoritative(snapshot) or snapshot is None:
            return False
        if not _same_commit_scope(snapshot, assessment):
            return False
        if not _same_commit_scope(snapshot, chain_state):
            return False
        if (
            snapshot.risk_policy_root != assessment.risk_policy_root
            or snapshot.risk_policy_root != chain_state.risk_policy_root
            or snapshot.risk_chain_id != chain_state.chain_id
            or snapshot.risk_chain_revision != chain_state.revision
            or snapshot.risk_chain_state_fingerprint
            != risk_assessment_chain_state_fingerprint(chain_state)
            or snapshot.risk_assessment_fingerprint
            != risk_assessment_fingerprint(assessment)
            or snapshot.risk_band is not assessment.risk_band
            or not (snapshot.issued_at_step <= current < snapshot.expires_at_step)
        ):
            return False
        band = commit_policy.risk_bands[assessment.risk_band.value]
        return _threshold_values(snapshot) == _risk_band_values(band)
    except (GovernanceError, KeyError, ValueError):
        return False


def commit_threshold_snapshot_payload(
    snapshot: CommitThresholdSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not CommitThresholdSnapshot:
        raise GovernanceError("commit threshold must use the canonical record")
    _validate_threshold_snapshot_shape(snapshot)
    return {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "epoch": snapshot.epoch,
        "executable_outcomes": snapshot.executable_outcomes,
        "expires_at_step": snapshot.expires_at_step,
        "issued_at_step": snapshot.issued_at_step,
        "issuer_id": snapshot.issuer_id,
        "manifest_root": snapshot.manifest_root,
        "maximum_counterevidence": snapshot.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            snapshot.maximum_counterevidence_ratio_ppm
        ),
        "minimum_assurance": snapshot.minimum_assurance,
        "minimum_margin": snapshot.minimum_margin,
        "minimum_positive_evidence": snapshot.minimum_positive_evidence,
        "minimum_source_diversity": snapshot.minimum_source_diversity,
        "minimum_support_clusters": snapshot.minimum_support_clusters,
        "minimum_support_ratio_ppm": snapshot.minimum_support_ratio_ppm,
        "profile": snapshot.profile,
        "protocol_id": snapshot.protocol_id,
        "provenance": snapshot.provenance,
        "publishable_outcomes": snapshot.publishable_outcomes,
        "required_challenge_categories": snapshot.required_challenge_categories,
        "risk_assessment_fingerprint": snapshot.risk_assessment_fingerprint,
        "risk_band": snapshot.risk_band,
        "risk_chain_id": snapshot.risk_chain_id,
        "risk_chain_revision": snapshot.risk_chain_revision,
        "risk_chain_state_fingerprint": snapshot.risk_chain_state_fingerprint,
        "risk_policy_root": snapshot.risk_policy_root,
        "run_id": snapshot.run_id,
        "stability_steps": snapshot.stability_steps,
        "target": snapshot.target,
        "threshold_id": snapshot.threshold_id,
        "trace_event_id": snapshot.trace_event_id,
    }


def commit_threshold_snapshot_fingerprint(
    snapshot: CommitThresholdSnapshot,
) -> str:
    return _threshold_snapshot(snapshot)


def risk_transition_is_monotonic(
    previous: RiskAssessment,
    current: RiskAssessment,
) -> bool:
    if not (
        risk_assessment_is_authoritative(previous)
        and risk_assessment_is_authoritative(current)
    ):
        return False
    return bool(
        _same_commit_scope(previous, current)
        and previous.risk_policy_root == current.risk_policy_root
        and previous.risk_chain_id == current.risk_chain_id
        and current.risk_chain_revision == previous.risk_chain_revision + 1
        and current.previous_assessment_fingerprint
        == risk_assessment_fingerprint(previous)
        and current.issued_at_step > previous.issued_at_step
        and current.expires_at_step == previous.expires_at_step
        and _RISK_ORDER[current.risk_band] >= _RISK_ORDER[previous.risk_band]
        and current.window_reset_required
        is (current.risk_band is not previous.risk_band)
    )


def commit_threshold_transition_requires_reset(
    previous: CommitThresholdSnapshot,
    current: CommitThresholdSnapshot,
) -> bool:
    if not (
        commit_threshold_snapshot_is_authoritative(previous)
        and commit_threshold_snapshot_is_authoritative(current)
    ):
        raise GovernanceError(
            "threshold transition requires authoritative snapshots"
        )
    for name in ("protocol_id", "run_id", "target"):
        if getattr(previous, name) != getattr(current, name):
            raise GovernanceError("threshold transition scope mismatch")
    return bool(
        previous.epoch != current.epoch
        or previous.manifest_root != current.manifest_root
        or previous.commit_policy_root != current.commit_policy_root
        or previous.risk_policy_root != current.risk_policy_root
        or previous.risk_band is not current.risk_band
        or _threshold_values(previous) != _threshold_values(current)
    )


def risk_policy_root(
    policy: CollectiveCommitPolicy,
    *,
    profile: str,
) -> str:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("risk policy root requires CollectiveCommitPolicy")
    normalized_profile = require_commit_profile(profile, "risk policy profile")
    _validate_risk_table(policy)
    return commit_payload_fingerprint(
        {
            "risk_bands": {
                name: _risk_band_payload(policy.risk_bands[name])
                for name in SUPPORTED_RISK_BANDS
            }
        },
        schema="pheroos-risk-band-policy-root-v1",
        profile=normalized_profile,
    )


def _validate_risk_assessment_shape(assessment: RiskAssessment) -> None:
    _validate_bound_record(assessment, "risk assessment")
    for name in (
        "assessment_id",
        "assessment_method",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(assessment, name), f"risk assessment {name}")
    if type(assessment.risk_band) is not RiskBand:
        raise GovernanceError("risk assessment band is invalid")
    for name in (
        "risk_policy_root",
        "risk_chain_id",
        "previous_chain_state_fingerprint",
    ):
        require_commit_fingerprint(getattr(assessment, name), f"risk assessment {name}")
    revision = require_commit_step(
        assessment.risk_chain_revision,
        "risk assessment risk_chain_revision",
    )
    if revision <= 0:
        raise GovernanceError("risk assessment chain revision must be positive")
    _canonical_fingerprints(
        assessment.risk_input_fingerprints,
        "risk assessment input fingerprints",
    )
    require_commit_labels(
        assessment.rationale_codes,
        "risk assessment rationale_codes",
    )
    if assessment.previous_assessment_fingerprint:
        require_commit_fingerprint(
            assessment.previous_assessment_fingerprint,
            "risk assessment previous_assessment_fingerprint",
        )
    if revision == 1 and assessment.previous_assessment_fingerprint:
        raise GovernanceError("initial risk assessment cannot name a predecessor")
    if revision > 1 and not assessment.previous_assessment_fingerprint:
        raise GovernanceError("risk reassessment must name its predecessor")
    if type(assessment.window_reset_required) is not bool:
        raise GovernanceError("risk assessment reset flag must be boolean")
    if not assessment.previous_assessment_fingerprint and assessment.window_reset_required:
        raise GovernanceError("initial risk assessment cannot require a risk reset")
    if type(assessment.authority) is not AuthorityLevel or not can_verify(
        assessment.authority
    ):
        raise GovernanceError("risk assessment authority is invalid")
    issued = require_commit_step(
        assessment.issued_at_step,
        "risk assessment issued_at_step",
    )
    expires = require_commit_step(
        assessment.expires_at_step,
        "risk assessment expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("risk assessment expiry must be after issuance")


def _validate_risk_assessment_chain_state_shape(
    state: RiskAssessmentChainState,
) -> None:
    _validate_bound_record(state, "risk assessment chain state")
    for name in (
        "chain_id",
        "risk_policy_root",
    ):
        require_commit_fingerprint(
            getattr(state, name),
            f"risk assessment chain state {name}",
        )
    for name in ("issuer_id", "provenance", "trace_event_id"):
        require_commit_text(
            getattr(state, name),
            f"risk assessment chain state {name}",
        )
    revision = require_commit_step(
        state.revision,
        "risk assessment chain state revision",
    )
    initialized = require_commit_step(
        state.initialized_at_step,
        "risk assessment chain state initialized_at_step",
    )
    last_issued = require_commit_step(
        state.last_issued_at_step,
        "risk assessment chain state last_issued_at_step",
    )
    expires = require_commit_step(
        state.expires_at_step,
        "risk assessment chain state expires_at_step",
    )
    if expires <= initialized:
        raise GovernanceError("risk assessment chain expiry must be after initialization")
    if not initialized <= last_issued < expires:
        raise GovernanceError("risk assessment chain issuance step is out of bounds")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("risk assessment chain authority is invalid")
    if revision == 0:
        if (
            state.latest_assessment_fingerprint
            or state.latest_risk_band
            or state.previous_state_fingerprint
        ):
            raise GovernanceError("empty risk assessment chain has a forged head")
        if last_issued != initialized:
            raise GovernanceError("empty risk assessment chain issuance step is invalid")
    else:
        require_commit_fingerprint(
            state.latest_assessment_fingerprint,
            "risk assessment chain latest_assessment_fingerprint",
        )
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "risk assessment chain previous_state_fingerprint",
        )
        if state.latest_risk_band not in _RISK_ORDER_BY_VALUE:
            raise GovernanceError("risk assessment chain latest risk band is invalid")


def _validate_threshold_snapshot_shape(snapshot: CommitThresholdSnapshot) -> None:
    _validate_bound_record(snapshot, "commit threshold")
    for name in ("threshold_id", "issuer_id", "provenance", "trace_event_id"):
        require_commit_text(getattr(snapshot, name), f"commit threshold {name}")
    for name in (
        "risk_policy_root",
        "risk_assessment_fingerprint",
        "risk_chain_id",
        "risk_chain_state_fingerprint",
    ):
        require_commit_fingerprint(getattr(snapshot, name), f"commit threshold {name}")
    if require_commit_step(
        snapshot.risk_chain_revision,
        "commit threshold risk_chain_revision",
    ) <= 0:
        raise GovernanceError("commit threshold chain revision must be positive")
    if type(snapshot.risk_band) is not RiskBand:
        raise GovernanceError("commit threshold risk band is invalid")
    if type(snapshot.minimum_assurance) is not CommitAssurance:
        raise GovernanceError("commit threshold minimum assurance is invalid")
    for name in (
        "minimum_positive_evidence",
        "maximum_counterevidence",
        "minimum_support_clusters",
        "minimum_source_diversity",
        "minimum_margin",
        "stability_steps",
    ):
        require_commit_step(getattr(snapshot, name), f"commit threshold {name}")
    if snapshot.minimum_positive_evidence <= 0:
        raise GovernanceError("commit threshold positive evidence must be positive")
    if snapshot.minimum_support_clusters <= 0:
        raise GovernanceError("commit threshold support clusters must be positive")
    if snapshot.minimum_source_diversity <= 0:
        raise GovernanceError("commit threshold diversity must be positive")
    if snapshot.minimum_margin <= 0 or snapshot.stability_steps <= 0:
        raise GovernanceError("commit threshold margin/window must be positive")
    require_scaled_integer(
        snapshot.maximum_counterevidence_ratio_ppm,
        "commit threshold maximum counterevidence ratio",
        maximum=WEIGHT_SCALE,
    )
    ratio = require_scaled_integer(
        snapshot.minimum_support_ratio_ppm,
        "commit threshold minimum support ratio",
        maximum=WEIGHT_SCALE,
    )
    if ratio <= 0:
        raise GovernanceError("commit threshold support ratio must be positive")
    require_commit_labels(
        snapshot.required_challenge_categories,
        "commit threshold required challenge categories",
    )
    require_commit_labels(
        snapshot.publishable_outcomes,
        "commit threshold publishable outcomes",
        allow_empty=True,
    )
    require_commit_labels(
        snapshot.executable_outcomes,
        "commit threshold executable outcomes",
        allow_empty=True,
    )
    if type(snapshot.authority) is not AuthorityLevel or not can_verify(
        snapshot.authority
    ):
        raise GovernanceError("commit threshold authority is invalid")
    issued = require_commit_step(
        snapshot.issued_at_step,
        "commit threshold issued_at_step",
    )
    expires = require_commit_step(
        snapshot.expires_at_step,
        "commit threshold expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("commit threshold expiry must be after issuance")


def _validate_bound_record(record: object, field_name: str) -> None:
    profile = require_commit_profile(getattr(record, "profile"), f"{field_name} profile")
    assurance = require_commit_assurance(
        getattr(record, "assurance"),
        f"{field_name} assurance",
    )
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    require_commit_fingerprint(
        getattr(record, "manifest_root"),
        f"{field_name} manifest_root",
    )
    require_commit_fingerprint(
        getattr(record, "commit_policy_root"),
        f"{field_name} commit_policy_root",
    )
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(getattr(record, name), f"{field_name} {name}")
    require_commit_step(getattr(record, "epoch"), f"{field_name} epoch")


def _normalized_bindings(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    field_name: str,
) -> dict[str, object]:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        f"{field_name} assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[
        normalized_assurance.value
    ]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    return {
        "profile": normalized_profile,
        "assurance": normalized_assurance,
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


def _validate_policy_binding(
    policy: object,
    bindings: Mapping[str, object],
) -> str:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("risk issuance requires CollectiveCommitPolicy")
    if policy.target != bindings["target"]:
        raise GovernanceError("risk policy target binding mismatch")
    assurance = bindings["assurance"]
    if type(assurance) is not CommitAssurance or policy.assurance != assurance.value:
        raise GovernanceError("risk policy assurance binding mismatch")
    observed_policy_root = commit_policy_fingerprint(
        policy,
        profile=str(bindings["profile"]),
    )
    if observed_policy_root != bindings["commit_policy_root"]:
        raise GovernanceError("risk commit policy root binding mismatch")
    _validate_risk_table(policy)
    return risk_policy_root(policy, profile=str(bindings["profile"]))


def _validate_risk_table(policy: CollectiveCommitPolicy) -> None:
    diagnostics = validate_risk_bands(policy, path="collective_commit_policy.risk_bands")
    if diagnostics:
        codes = ", ".join(sorted({item.code for item in diagnostics}))
        raise GovernanceError(f"risk policy is invalid or non-monotonic: {codes}")


def _record_bindings_equal(record: object, bindings: Mapping[str, object]) -> bool:
    return all(getattr(record, name) == value for name, value in bindings.items())


def _same_commit_scope(left: object, right: object) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        )
    )


def _risk_assessment_is_head_of_state(
    assessment: RiskAssessment,
    state: RiskAssessmentChainState,
) -> bool:
    return bool(
        risk_assessment_is_authoritative(assessment)
        and risk_assessment_chain_state_is_authoritative(state)
        and _same_commit_scope(assessment, state)
        and assessment.risk_policy_root == state.risk_policy_root
        and assessment.risk_chain_id == state.chain_id
        and assessment.risk_chain_revision == state.revision
        and risk_assessment_fingerprint(assessment)
        == state.latest_assessment_fingerprint
        and assessment.risk_band.value == state.latest_risk_band
        and assessment.issued_at_step == state.last_issued_at_step
        and assessment.expires_at_step == state.expires_at_step
    )


def _risk_band_payload(band: RiskBandPolicy) -> dict[str, object]:
    if type(band) is not RiskBandPolicy:
        raise GovernanceError("risk band must use the Protocol ABI record")
    return {
        "executable_outcomes": tuple(
            require_commit_labels(
                band.executable_outcomes,
                "risk band executable outcomes",
                allow_empty=True,
            )
        ),
        "maximum_counterevidence": band.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            band.maximum_counterevidence_ratio_ppm
        ),
        "minimum_assurance": band.minimum_assurance,
        "minimum_margin": band.minimum_margin,
        "minimum_positive_evidence": band.minimum_positive_evidence,
        "minimum_source_diversity": band.minimum_source_diversity,
        "minimum_support_clusters": band.minimum_support_clusters,
        "minimum_support_ratio_ppm": band.minimum_support_ratio_ppm,
        "publishable_outcomes": tuple(
            require_commit_labels(
                band.publishable_outcomes,
                "risk band publishable outcomes",
                allow_empty=True,
            )
        ),
        "required_challenge_categories": tuple(
            require_commit_labels(
                band.required_challenge_categories,
                "risk band required challenge categories",
            )
        ),
        "stability_steps": band.stability_steps,
    }


def _risk_band_values(band: RiskBandPolicy) -> tuple[object, ...]:
    payload = _risk_band_payload(band)
    return tuple(payload[name] for name in sorted(payload))


def _threshold_values(snapshot: CommitThresholdSnapshot) -> tuple[object, ...]:
    return _risk_band_values(
        RiskBandPolicy(
            minimum_positive_evidence=snapshot.minimum_positive_evidence,
            maximum_counterevidence=snapshot.maximum_counterevidence,
            maximum_counterevidence_ratio_ppm=(
                snapshot.maximum_counterevidence_ratio_ppm
            ),
            minimum_support_clusters=snapshot.minimum_support_clusters,
            minimum_support_ratio_ppm=snapshot.minimum_support_ratio_ppm,
            minimum_source_diversity=snapshot.minimum_source_diversity,
            minimum_margin=snapshot.minimum_margin,
            stability_steps=snapshot.stability_steps,
            required_challenge_categories=list(
                snapshot.required_challenge_categories
            ),
            minimum_assurance=snapshot.minimum_assurance.value,
            publishable_outcomes=list(snapshot.publishable_outcomes),
            executable_outcomes=list(snapshot.executable_outcomes),
        )
    )


def _risk_assessment_snapshot(assessment: RiskAssessment) -> str:
    return commit_payload_fingerprint(
        risk_assessment_payload(assessment),
        schema="pheroos-risk-assessment-v1",
        profile=assessment.profile,
    )


def _risk_assessment_chain_state_snapshot(
    state: RiskAssessmentChainState,
) -> str:
    return commit_payload_fingerprint(
        risk_assessment_chain_state_payload(state),
        schema="pheroos-risk-assessment-chain-state-v1",
        profile=state.profile,
    )


def _issue_risk_assessment_chain_state(
    state: RiskAssessmentChainState,
    cursor: _RiskAssessmentChainCursor,
) -> RiskAssessmentChainState:
    if cursor.chain_id != state.chain_id:
        raise GovernanceError("risk assessment chain cursor binding mismatch")
    object.__setattr__(state, "_cursor", cursor)
    object.__setattr__(
        state,
        "_issuance",
        (
            _RISK_ASSESSMENT_CHAIN_STATE_ISSUANCE,
            _risk_assessment_chain_state_snapshot(state),
        ),
    )
    return state


def _threshold_snapshot(snapshot: CommitThresholdSnapshot) -> str:
    return commit_payload_fingerprint(
        commit_threshold_snapshot_payload(snapshot),
        schema="pheroos-commit-threshold-snapshot-v1",
        profile=snapshot.profile,
    )


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in normalized:
        require_commit_fingerprint(value, field_name)
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(normalized))


__all__ = [
    "CommitThresholdSnapshot",
    "RiskAssessment",
    "RiskAssessmentChainState",
    "RiskBand",
    "commit_threshold_snapshot_fingerprint",
    "commit_threshold_snapshot_is_authoritative",
    "commit_threshold_snapshot_matches",
    "commit_threshold_snapshot_payload",
    "commit_threshold_transition_requires_reset",
    "initialize_risk_assessment_chain",
    "issue_commit_threshold_snapshot",
    "issue_risk_assessment",
    "risk_assessment_chain_state_fingerprint",
    "risk_assessment_chain_state_is_authoritative",
    "risk_assessment_chain_state_is_current",
    "risk_assessment_chain_state_payload",
    "risk_assessment_fingerprint",
    "risk_assessment_is_authoritative",
    "risk_assessment_is_latest",
    "risk_assessment_matches",
    "risk_assessment_payload",
    "risk_policy_root",
    "risk_transition_is_monotonic",
]
