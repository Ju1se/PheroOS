"""Store-current parent access used by Support v2 source preparation."""

from __future__ import annotations

from typing import cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._support_v2.membership_contracts import (
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
)
from pheroos.governance._support_v2.membership_state import (
    _decode_state_records as _decode_membership_state_records,
)
from pheroos.governance._support_v2.support_state_contracts import SupportSnapshotV2
from pheroos.governance._support_v2.support_state_handle import (
    _current_support_source_material_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    governance_authority_state_root_v2,
)
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


def _support_parent(
    state: object,
) -> tuple[SupportSnapshotV2, GovernanceReadPreconditionV2]:
    return _current_support_source_material_v2(state)


def _membership_parent(
    state: object,
) -> tuple[MembershipSnapshotV2, GovernanceReadPreconditionV2]:
    snapshot, membership, _ = _membership_parent_authority_material_v2(state)
    return snapshot, membership


def _membership_parent_authority_material_v2(
    state: object,
) -> tuple[
    MembershipSnapshotV2,
    GovernanceReadPreconditionV2,
    GovernanceReadPreconditionV2,
]:
    """Return current Membership and its transitive verification head."""

    if type(state) is not VerifiedMembershipStateV2:
        raise TypeError("support issuance requires verified Membership v2 state")
    reader, domain, request = _membership_handle_fields(state)
    try:
        head = reader.load_head_v2(request.scope_ref, request.stream_ref)
        verification_head = reader.load_head_v2(
            request.scope_ref,
            request.snapshot.verification_stream_ref,
        )
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    _validate_membership_heads(request, domain, head, verification_head)
    _validate_membership_projection(reader, domain, request, (head))
    membership_head = head
    current_verification_head = verification_head
    snapshot = MembershipSnapshotV2.from_dict(request.snapshot.to_dict())
    return (
        snapshot,
        GovernanceReadPreconditionV2(
            stream_ref=membership_head.stream_ref,
            expected_revision=membership_head.revision,
            expected_root=membership_head.head_root,
        ),
        GovernanceReadPreconditionV2(
            stream_ref=current_verification_head.stream_ref,
            expected_revision=current_verification_head.revision,
            expected_root=current_verification_head.head_root,
        ),
    )


def _membership_handle_fields(
    state: VerifiedMembershipStateV2,
) -> tuple[GovernanceStateReaderV2, AuthorityDomainV2, MembershipCommitRequestV2]:
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        receipt_root = object.__getattribute__(state, "_receipt_root")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state",
        ) from exc
    if (
        type(domain) is not AuthorityDomainV2
        or type(request) is not MembershipCommitRequestV2
        or type(receipt_root) is not str
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state",
        )
    _require_root(receipt_root, "support membership handle receipt_root")
    try:
        conforms = isinstance(reader, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("support membership StateReader v2 is invalid") from exc
    if not conforms:
        raise TypeError("support membership StateReader v2 is invalid")
    return (
        cast(GovernanceStateReaderV2, reader),
        AuthorityDomainV2.from_dict(domain.to_dict()),
        MembershipCommitRequestV2.from_dict(request.to_dict()),
    )


def _validate_membership_heads(
    request: MembershipCommitRequestV2,
    domain: AuthorityDomainV2,
    head: object,
    verification_head: object,
) -> None:
    if (
        type(head) is not GovernanceHeadV2
        or type(verification_head) is not GovernanceHeadV2
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state/head",
        )
    snapshot = request.snapshot
    expected_context = (domain.domain_root, domain.scope_ref, request.stream_ref)
    observed_context = (head.domain_root, head.scope_ref, head.stream_ref)
    verification_context = (
        verification_head.domain_root,
        verification_head.scope_ref,
        verification_head.stream_ref,
    )
    expected_verification_context = (
        domain.domain_root,
        domain.scope_ref,
        snapshot.verification_stream_ref,
    )
    if (
        observed_context != expected_context
        or verification_context != expected_verification_context
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state/head",
        )
    if (
        head.revision != snapshot.revision
        or head.transition_id != request.transition_id
        or verification_head.stream_ref != snapshot.verification_stream_ref
        or verification_head.transition_id != snapshot.verification_transition_id
        or verification_head.revision != snapshot.verification_revision
        or verification_head.head_root != snapshot.verification_head_root
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/membership_state/position",
        )


def _validate_membership_projection(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: MembershipCommitRequestV2,
    head: GovernanceHeadV2,
) -> None:
    try:
        records = reader.load_state_v2(request.scope_ref, request.stream_ref)
        committed, _ = _decode_membership_state_records(records, domain)
        state_root = governance_authority_state_root_v2(
            request.scope_ref,
            request.stream_ref,
            records,
        )
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state/state",
        ) from exc
    if committed.to_dict() != request.to_dict() or state_root != head.state_root:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/membership_state/state",
        )


__all__: tuple[str, ...] = ()
