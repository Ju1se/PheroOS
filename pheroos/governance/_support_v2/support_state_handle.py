"""Opaque Store-reverified Support v2 state handle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.common import _require_count_v2
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportSnapshotV2,
)
from pheroos.governance._support_v2.support_committed_state import (
    _decode_state_records,
)
from pheroos.governance._support_v2.support_state_load import (
    _load_verified_request_view,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    governance_authority_state_root_v2,
)


@dataclass(frozen=True, slots=True)
class _VerifiedSupportAnchorV2:
    receipt_root: str
    head_root: str
    revision: int

    def __post_init__(self) -> None:
        _require_root(self.receipt_root, "support anchor receipt_root")
        _require_root(self.head_root, "support anchor head_root")
        _require_count_v2(self.revision, "support anchor revision", minimum=1)

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified support anchor is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified support anchor is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified support anchor is not portable")


@final
class VerifiedSupportStateV2:
    """Opaque Support state whose every observation is Store-reverified."""

    __slots__ = ("_anchor", "_domain", "_reader", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedSupportStateV2:
        raise TypeError("VerifiedSupportStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedSupportStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedSupportStateV2 is immutable")

    def __copy__(self) -> VerifiedSupportStateV2:
        _verified_state_view(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedSupportStateV2:
        _verified_state_view(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedSupportStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedSupportStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedSupportStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedSupportStateV2 redacted>"

    @property
    def snapshot(self) -> SupportSnapshotV2:
        request, _ = _verified_state_view(self)
        return SupportSnapshotV2.from_dict(request.snapshot.to_dict())

    @property
    def request_root(self) -> str:
        request, _ = _verified_state_view(self)
        return request.request_root

    @property
    def stream_ref(self) -> str:
        request, _ = _verified_state_view(self)
        return request.stream_ref

    @property
    def transition_id(self) -> str:
        request, _ = _verified_state_view(self)
        return request.transition_id

    @property
    def receipt_root(self) -> str:
        _, view = _verified_state_view(self)
        assert view.committed_transition is not None
        return view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        _, view = _verified_state_view(self)
        assert view.position_observation is not None
        return view.position_observation.position


def support_state_is_current_v2(state: object) -> bool:
    try:
        _, view = _verified_state_view(state)
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def require_current_support_state_v2(state: object) -> SupportSnapshotV2:
    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return SupportSnapshotV2.from_dict(request.snapshot.to_dict())


def _current_support_source_material_v2(
    state: object,
) -> tuple[SupportSnapshotV2, GovernanceReadPreconditionV2]:
    request, head = _verified_current_state_material_v2(state)
    snapshot = SupportSnapshotV2.from_dict(request.snapshot.to_dict())
    return snapshot, GovernanceReadPreconditionV2(
        stream_ref=head.stream_ref,
        expected_revision=head.revision,
        expected_root=head.head_root,
    )


def _verified_current_state_material_v2(
    state: object,
) -> tuple[SupportAdvanceRequestV2, GovernanceHeadV2]:
    reader, domain, request, anchor = _state_handle_fields(state)
    try:
        head = reader.load_head_v2(request.scope_ref, request.stream_ref)
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    if type(head) is not GovernanceHeadV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/head",
        )
    detached_head = GovernanceHeadV2.from_dict(head.to_dict())
    expected_context = (domain.domain_root, domain.scope_ref, request.stream_ref)
    observed_context = (
        detached_head.domain_root,
        detached_head.scope_ref,
        detached_head.stream_ref,
    )
    if observed_context != expected_context:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/head",
        )
    if (
        detached_head.revision != request.snapshot.revision
        or detached_head.revision != anchor.revision
        or detached_head.transition_id != request.transition_id
        or detached_head.head_root != anchor.head_root
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    _validate_current_projection(reader, domain, request, detached_head)
    return SupportAdvanceRequestV2.from_dict(request.to_dict()), detached_head


def _validate_current_projection(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: SupportAdvanceRequestV2,
    head: GovernanceHeadV2,
) -> None:
    try:
        records = reader.load_state_v2(request.scope_ref, request.stream_ref)
        committed, _, _, _, _ = _decode_state_records(records, domain)
        state_root = governance_authority_state_root_v2(
            request.scope_ref,
            request.stream_ref,
            records,
        )
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state",
        ) from exc
    if committed.to_dict() != request.to_dict() or state_root != head.state_root:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state",
        )


def _state_handle_fields(
    state: object,
) -> tuple[
    GovernanceStateReaderV2,
    AuthorityDomainV2,
    SupportAdvanceRequestV2,
    _VerifiedSupportAnchorV2,
]:
    if type(state) is not VerifiedSupportStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        anchor = object.__getattribute__(state, "_anchor")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        ) from exc
    _require_domain(domain)
    _require_state_reader(reader)
    if (
        type(request) is not SupportAdvanceRequestV2
        or type(anchor) is not _VerifiedSupportAnchorV2
        or anchor.revision != request.snapshot.revision
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return (
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        SupportAdvanceRequestV2.from_dict(request.to_dict()),
        anchor,
    )


def _verified_state_view(
    state: object,
) -> tuple[SupportAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedSupportStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        anchor = object.__getattribute__(state, "_anchor")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        ) from exc
    _require_domain(domain)
    _require_state_reader(reader)
    if (
        type(request) is not SupportAdvanceRequestV2
        or type(anchor) is not _VerifiedSupportAnchorV2
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    detached = SupportAdvanceRequestV2.from_dict(request.to_dict())
    return _load_verified_request_view(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        detached,
        expected_receipt_root=anchor.receipt_root,
    )


def _make_verified_state(
    *,
    state_reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: SupportAdvanceRequestV2,
    view: GovernanceCommitViewV2,
) -> VerifiedSupportStateV2:
    if type(view) is not GovernanceCommitViewV2 or view.committed_transition is None:
        raise TypeError("support state requires one verified committed view")
    receipt = view.committed_transition.receipt
    handle = object.__new__(VerifiedSupportStateV2)
    object.__setattr__(handle, "_reader", state_reader)
    object.__setattr__(handle, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        handle,
        "_request",
        SupportAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(
        handle,
        "_anchor",
        _VerifiedSupportAnchorV2(
            receipt_root=receipt.receipt_root,
            head_root=receipt.head_root,
            revision=receipt.revision,
        ),
    )
    return handle


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("support state requires exact AuthorityDomainV2")


def _require_state_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("support state requires StateReader v2") from exc
    if not conforms:
        raise TypeError("support state requires StateReader v2")


__all__: tuple[str, ...] = ()
