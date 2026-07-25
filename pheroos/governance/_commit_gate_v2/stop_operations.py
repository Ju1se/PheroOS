"""Public-operation implementation for durable Commit Stop v2."""

from __future__ import annotations

from typing import cast

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
)
from pheroos.governance._authority_session_v2.operations import (
    _open_governance_authority_session_binding_v2,
)
from pheroos.governance._commit_gate_v2.common import _require_count
from pheroos.governance._commit_gate_v2.operations_common import (
    _advance_commit_gate_v2,
)
from pheroos.governance._commit_gate_v2.state_handle import (
    VerifiedCommitStopStateV2,
    _rehydrate_gate_state_v2,
    _require_current_state_v2,
    _state_is_current_v2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import (
    CommitStopRequestV2,
    CommitStopSnapshotV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceStateReaderV2,
)


def open_commit_stop_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitStopRequestV2,
) -> GovernanceAuthoritySessionV2:
    _require_request(request)
    if type(capability) is not GovernanceIssuerCapabilityV2:
        raise TypeError("commit stop session requires exact issuer capability v2")
    if capability.issuer_ref != request.snapshot.mutation_issuer_ref:
        raise ValueError("commit stop issuer_ref is not owned by the capability")
    return _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.resolution_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.RESOLVE_STOP,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=(),
    )


def resolve_commit_stop_v2(
    request: CommitStopRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    _require_request(request)
    return _advance_commit_gate_v2(
        request,
        source=source,
        authority_session=authority_session,
        kind="stop",
    )


def rehydrate_commit_stop_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitStopStateV2:
    return cast(
        VerifiedCommitStopStateV2,
        _rehydrate_gate_state_v2(
            payload, domain=domain, state_reader=state_reader, kind="stop"
        ),
    )


def commit_stop_state_is_current_v2(state: object) -> bool:
    return _state_is_current_v2(state, kind="stop")


def require_current_commit_stop_state_v2(
    state: object,
) -> CommitStopSnapshotV2:
    request = _require_current_state_v2(state, kind="stop")
    assert type(request) is CommitStopRequestV2
    return CommitStopSnapshotV2.from_dict(request.snapshot.to_dict())


def commit_stop_blocks_v2(state: object, *, current_step: int) -> bool:
    """Return whether the current authoritative Stop is fresh and blocking."""

    step = _require_count(current_step, "commit stop effective current_step")
    try:
        snapshot = require_current_commit_stop_state_v2(state)
    except Exception:
        return False
    return (
        snapshot.issued_at_step <= step < snapshot.expires_at_step and snapshot.blocked
    )


def _require_request(value: object) -> None:
    if type(value) is not CommitStopRequestV2:
        raise TypeError("commit stop operation requires exact request v2")


__all__: tuple[str, ...] = ()
