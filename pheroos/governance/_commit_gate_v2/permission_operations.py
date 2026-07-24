"""Public-operation implementation for durable Commit Permission v2."""

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
from pheroos.governance._commit_gate_v2.common import _require_count, _require_text
from pheroos.governance._commit_gate_v2.operations_common import (
    _advance_commit_gate_v2,
)
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionRequestV2,
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.state_handle import (
    VerifiedCommitPermissionStateV2,
    _rehydrate_gate_state_v2,
    _require_current_state_v2,
    _state_is_current_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceStateReaderV2,
)


def open_commit_permission_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitPermissionRequestV2,
) -> GovernanceAuthoritySessionV2:
    _require_request(request)
    if type(capability) is not GovernanceIssuerCapabilityV2:
        raise TypeError("commit permission session requires exact issuer capability v2")
    if capability.issuer_ref != request.snapshot.mutation_issuer_ref:
        raise ValueError("commit permission issuer_ref is not owned by the capability")
    return _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.permission_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=("commit",),
    )


def issue_commit_permission_v2(
    request: CommitPermissionRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    _require_request(request)
    return _advance_commit_gate_v2(
        request,
        source=source,
        authority_session=authority_session,
        kind="permission",
    )


def rehydrate_commit_permission_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitPermissionStateV2:
    return cast(
        VerifiedCommitPermissionStateV2,
        _rehydrate_gate_state_v2(
            payload, domain=domain, state_reader=state_reader, kind="permission"
        ),
    )


def commit_permission_state_is_current_v2(state: object) -> bool:
    return _state_is_current_v2(state, kind="permission")


def require_current_commit_permission_state_v2(
    state: object,
) -> CommitPermissionSnapshotV2:
    request = _require_current_state_v2(state, kind="permission")
    assert type(request) is CommitPermissionRequestV2
    return CommitPermissionSnapshotV2.from_dict(request.snapshot.to_dict())


def commit_permission_allows_v2(
    state: object,
    *,
    current_step: int,
    candidate_ref: str,
) -> bool:
    """Return whether current durable permission allows one declared candidate."""

    step = _require_count(current_step, "commit permission effective current_step")
    candidate = _require_text(candidate_ref, "commit permission candidate_ref")
    try:
        snapshot = require_current_commit_permission_state_v2(state)
    except Exception:
        return False
    return (
        snapshot.issued_at_step <= step < snapshot.expires_at_step
        and snapshot.allowed
        and candidate in snapshot.candidate_refs
    )


def _require_request(value: object) -> None:
    if type(value) is not CommitPermissionRequestV2:
        raise TypeError("commit permission operation requires exact request v2")


__all__: tuple[str, ...] = ()
