from __future__ import annotations

from collections.abc import Sequence
from threading import RLock

from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)
from pheroos.governance._risk.invariants import (
    _normalized_bindings,
    _record_bindings_equal,
    _same_commit_scope,
    _validate_policy_binding,
)
from pheroos.governance._risk.payloads import (
    _risk_assessment_chain_state_snapshot,
    _risk_assessment_snapshot,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance._risk.records import (
    _RISK_ORDER,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
    _validate_risk_assessment_chain_state_shape,
    _validate_risk_assessment_shape,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)


_RISK_ASSESSMENT_ISSUANCE = object()
_RISK_ASSESSMENT_CHAIN_STATE_ISSUANCE = object()
_LEGACY_RISK_CHAIN_CURSORS = "legacy.risk.chain_cursors"


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
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_RISK_CHAIN_CURSORS, authority_key)
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
        registry.set(_LEGACY_RISK_CHAIN_CURSORS, authority_key, cursor)
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
