"""Opaque rehydrated Certificate state and Decision finality adapter."""

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
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateStatusV2,
)
from pheroos.governance._commit_certificate_v2.request import (
    CommitCertificateRequestV2,
)
from pheroos.governance._commit_certificate_v2.decision_leaves import (
    _authority_leaves,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    CommitCertificateSnapshotV2,
)
from pheroos.governance._commit_certificate_v2.state_records import (
    _decode_committed_certificate_view_v2,
    _head_from_view_v2,
)
from pheroos.governance._commit_decision_v2.seal_context import (
    _CommitDecisionSealContextMaterialV2,
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
)
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _CommitCertificateStateMaterialV2:
    domain: AuthorityDomainV2
    reader: GovernanceStateReaderV2
    request: CommitCertificateRequestV2
    snapshot: CommitCertificateSnapshotV2
    view: GovernanceCommitViewV2
    head: GovernanceHeadV2


@dataclass(frozen=True, slots=True)
class _CommitCertificateFinalityMaterialV2:
    projection: CommitFinalityProjectionV2
    certificate_precondition: GovernanceReadPreconditionV2
    certificate_receipt_root: str
    certificate_inclusion_root: str


@final
class VerifiedCommitCertificateStateV2:
    """Opaque state whose every observation revalidates committed history."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitCertificateStateV2:
        raise TypeError("VerifiedCommitCertificateStateV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitCertificateStateV2 is immutable")

    def __copy__(self) -> VerifiedCommitCertificateStateV2:
        _verified_commit_certificate_state_material_v2(self)
        return self

    def __deepcopy__(
        self, _memo: dict[int, object]
    ) -> VerifiedCommitCertificateStateV2:
        _verified_commit_certificate_state_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitCertificateStateV2 redacted>"

    @property
    def snapshot(self) -> CommitCertificateSnapshotV2:
        material = _verified_commit_certificate_state_material_v2(self)
        return CommitCertificateSnapshotV2.from_dict(material.snapshot.to_dict())

    @property
    def request_root(self) -> str:
        return _verified_commit_certificate_state_material_v2(self).request.request_root

    @property
    def stream_ref(self) -> str:
        return _verified_commit_certificate_state_material_v2(self).request.stream_ref

    @property
    def transition_id(self) -> str:
        return _verified_commit_certificate_state_material_v2(
            self
        ).request.transition_id

    @property
    def receipt_root(self) -> str:
        material = _verified_commit_certificate_state_material_v2(self)
        assert material.view.committed_transition is not None
        return material.view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        material = _verified_commit_certificate_state_material_v2(self)
        assert material.view.position_observation is not None
        return material.view.position_observation.position


@final
class _VerifiedCommitCertificateFinalityContextV2:
    __slots__ = (
        "_anchor_root",
        "_certificate_state",
        "_current_step",
        "_decision_state",
    )

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> _VerifiedCommitCertificateFinalityContextV2:
        raise TypeError("verified certificate finality context cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("verified certificate finality context is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("verified certificate finality context is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified certificate finality context is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified certificate finality context is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified certificate finality context is not portable")

    def __repr__(self) -> str:
        return "<_VerifiedCommitCertificateFinalityContextV2 redacted>"


def rehydrate_commit_certificate_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitCertificateStateV2:
    _require_domain(domain)
    _require_reader(state_reader)
    request = _request_from_portable(payload)
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    material = _load_verified_material(
        state_reader,
        domain,
        request,
        expected_receipt_root=None,
    )
    assert material.view.committed_transition is not None
    state = object.__new__(VerifiedCommitCertificateStateV2)
    object.__setattr__(state, "_reader", state_reader)
    object.__setattr__(state, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        state, "_request", CommitCertificateRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(
        state,
        "_receipt_root",
        material.view.committed_transition.receipt.receipt_root,
    )
    return state


def commit_certificate_state_is_current_v2(state: object) -> bool:
    try:
        material = _verified_commit_certificate_state_material_v2(state)
        assert material.view.position_observation is not None
        return (
            material.view.position_observation.position
            is GovernanceCommitPositionV2.CURRENT
        )
    except Exception:
        return False


def require_current_commit_certificate_state_v2(
    state: object,
) -> CommitCertificateSnapshotV2:
    material = _verified_commit_certificate_state_material_v2(state)
    assert material.view.position_observation is not None
    if (
        material.view.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return CommitCertificateSnapshotV2.from_dict(material.snapshot.to_dict())


def _verified_commit_certificate_state_material_v2(
    state: object,
) -> _CommitCertificateStateMaterialV2:
    if type(state) is not VerifiedCommitCertificateStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        receipt_root = object.__getattribute__(state, "_receipt_root")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        ) from exc
    _require_domain(domain)
    _require_reader(reader)
    if type(request) is not CommitCertificateRequestV2 or type(receipt_root) is not str:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return _load_verified_material(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        CommitCertificateRequestV2.from_dict(request.to_dict()),
        expected_receipt_root=receipt_root,
    )


def _load_verified_material(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: CommitCertificateRequestV2,
    *,
    expected_receipt_root: str | None,
) -> _CommitCertificateStateMaterialV2:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "/transition_id",
        )
    try:
        committed, snapshot, _ = _decode_committed_certificate_view_v2(
            view,
            domain,
            reader=reader,
        )
        head = _head_from_view_v2(view, domain)
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if committed.to_dict() != request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return _CommitCertificateStateMaterialV2(
        domain=AuthorityDomainV2.from_dict(domain.to_dict()),
        reader=reader,
        request=committed,
        snapshot=snapshot,
        view=view,
        head=head,
    )


def _verified_commit_certificate_finality_context_v2(
    certificate_state: object,
    *,
    sealed_decision_state: object,
    current_step: int,
) -> _VerifiedCommitCertificateFinalityContextV2:
    material = _build_finality_material(
        certificate_state,
        sealed_decision_state=sealed_decision_state,
        current_step=current_step,
    )
    context = object.__new__(_VerifiedCommitCertificateFinalityContextV2)
    object.__setattr__(context, "_certificate_state", certificate_state)
    object.__setattr__(context, "_decision_state", sealed_decision_state)
    object.__setattr__(context, "_current_step", current_step)
    object.__setattr__(context, "_anchor_root", material.projection.projection_root)
    return context


def _verified_commit_certificate_finality_context_material_v2(
    context: object,
) -> _CommitCertificateFinalityMaterialV2:
    if type(context) is not _VerifiedCommitCertificateFinalityContextV2:
        raise TypeError("commit certificate finality context has the wrong exact type")
    try:
        certificate_state = object.__getattribute__(context, "_certificate_state")
        decision_state = object.__getattribute__(context, "_decision_state")
        current_step = object.__getattribute__(context, "_current_step")
        anchor_root = object.__getattribute__(context, "_anchor_root")
    except AttributeError as exc:
        raise TypeError("commit certificate finality context is incomplete") from exc
    if type(current_step) is not int or type(anchor_root) is not str:
        raise TypeError("commit certificate finality context anchor is invalid")
    material = _build_finality_material(
        certificate_state,
        sealed_decision_state=decision_state,
        current_step=current_step,
    )
    if material.projection.projection_root != anchor_root:
        raise ValueError("commit certificate finality context anchor is mismatched")
    return material


def _build_finality_material(
    certificate_state: object,
    *,
    sealed_decision_state: object,
    current_step: int,
) -> _CommitCertificateFinalityMaterialV2:
    certificate = _verified_commit_certificate_state_material_v2(certificate_state)
    if type(sealed_decision_state) is not VerifiedCommitDecisionStateV2:
        raise TypeError("commit certificate finality requires verified Decision state")
    decision = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(sealed_decision_state)
    )
    if type(current_step) is not int:
        raise TypeError("commit certificate finality step must be an exact integer")
    if (
        certificate.view.position_observation is None
        or certificate.view.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/certificate/position",
        )
    if current_step != decision.snapshot.current_step + 1:
        raise ValueError(
            "commit certificate finality requires the exact next heartbeat"
        )
    if current_step >= decision.snapshot.finality_deadline_step:
        raise ValueError("commit certificate finality deadline has elapsed")
    _require_certificate_matches_decision(certificate.snapshot, decision)
    _require_upstreams_current(certificate, decision)
    status = (
        CommitFinalityStatusV2.VERIFIED
        if certificate.snapshot.status is CommitCertificateStatusV2.VERIFIED
        else CommitFinalityStatusV2.CONFLICT
    )
    assert certificate.view.committed_transition is not None
    receipt = certificate.view.committed_transition.receipt
    inclusion = certificate.view.committed_transition.inclusion_proof
    projection = CommitFinalityProjectionV2(
        owner=CommitFinalityOwnerV2.CERTIFICATE,
        status=status,
        stream_ref=certificate.snapshot.stream_ref,
        revision=certificate.snapshot.revision,
        transition_id=certificate.snapshot.transition_id,
        snapshot_root=certificate.snapshot.snapshot_root,
        head_root=certificate.head.head_root,
        receipt_root=receipt.receipt_root,
        seal_transition_id=decision.seal_inclusion.transition_id,
        seal_root=decision.seal_inclusion.seal_root,
        frozen_dependency_root=decision.seal_inclusion.frozen_dependency_root,
        verified_at_step=current_step,
        reason_codes=certificate.snapshot.reason_codes,
    )
    return _CommitCertificateFinalityMaterialV2(
        projection=projection,
        certificate_precondition=GovernanceReadPreconditionV2(
            stream_ref=certificate.head.stream_ref,
            expected_revision=certificate.head.revision,
            expected_root=certificate.head.head_root,
        ),
        certificate_receipt_root=receipt.receipt_root,
        certificate_inclusion_root=inclusion.inclusion_root,
    )


def _require_certificate_matches_decision(
    certificate: CommitCertificateSnapshotV2,
    decision: _CommitDecisionSealContextMaterialV2,
) -> None:
    body = certificate.certificate.body
    snapshot = decision.snapshot
    seal = snapshot.seal
    assessment = snapshot.assessment
    assert seal is not None and assessment is not None
    metrics = tuple(
        item
        for item in assessment.candidate_metrics
        if item.candidate_ref == seal.candidate_ref
        and item.claim_root == seal.claim_root
    )
    observed = (
        body.domain_root,
        body.scope_ref,
        body.protocol_ref,
        body.run_ref,
        body.target_ref,
        body.epoch,
        body.profile,
        body.assurance,
        body.manifest_root,
        body.commit_policy_root,
        body.decision_stream_ref,
        body.decision_revision,
        body.decision_transition_id,
        body.decision_snapshot_root,
        body.decision_head_root,
        body.decision_receipt_root,
        body.decision_inclusion_root,
        body.seal_transition_id,
        body.seal_revision,
        body.seal_snapshot_root,
        body.seal_receipt_root,
        body.seal_head_root,
        body.seal_inclusion_root,
        body.seal_root,
        body.window_root,
        body.frozen_dependency_root,
        body.assessment_root,
        body.candidate_ref,
        body.claim_root,
        body.output_contract_root,
        body.output_payload_root,
    )
    expected = (
        snapshot.domain_root,
        snapshot.scope_ref,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
        snapshot.epoch,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.stream_ref,
        snapshot.revision,
        snapshot.transition_id,
        snapshot.snapshot_root,
        decision.decision_head.head_root,
        decision.current_inclusion.receipt_root,
        decision.current_inclusion.inclusion_root,
        decision.seal_inclusion.transition_id,
        decision.seal_inclusion.revision,
        decision.seal_inclusion.snapshot_root,
        decision.seal_inclusion.receipt_root,
        decision.seal_inclusion.head_root,
        decision.seal_inclusion.inclusion_root,
        seal.seal_root,
        seal.window_root,
        seal.frozen_dependency_root,
        assessment.assessment_root,
        seal.candidate_ref,
        seal.claim_root,
        seal.output_contract_root,
        seal.output_payload_root,
    )
    if observed != expected or len(metrics) != 1:
        raise ValueError("commit certificate is cross-bound to Decision authority")
    if (
        body.evidence_root,
        body.challenge_root,
        body.lease_root,
        tuple(item.to_dict() for item in body.authority_leaves),
    ) != (
        metrics[0].evidence_root,
        metrics[0].challenge_root,
        metrics[0].lease_root,
        tuple(item.to_dict() for item in _authority_leaves(snapshot.dependencies)),
    ):
        raise ValueError(
            "commit certificate evidence or authority leaves are mismatched"
        )


def _require_upstreams_current(
    certificate: _CommitCertificateStateMaterialV2,
    decision: _CommitDecisionSealContextMaterialV2,
) -> None:
    if (
        certificate.domain.domain_root != decision.domain.domain_root
        or certificate.domain.scope_ref != decision.domain.scope_ref
    ):
        raise ValueError("commit certificate finality domain is cross-bound")
    for leaf in certificate.snapshot.certificate.body.authority_leaves:
        try:
            head = certificate.reader.load_head_v2(
                certificate.snapshot.scope_ref,
                leaf.stream_ref,
            )
        except KeyError as exc:
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/certificate/dependencies",
            ) from exc
        if type(head) is not GovernanceHeadV2:
            raise ValueError("commit certificate finality dependency head is invalid")
        if (
            head.revision != leaf.revision
            or head.transition_id != leaf.transition_id
            or head.head_root != leaf.head_root
        ):
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/certificate/dependencies",
            )


def _request_from_portable(value: object) -> CommitCertificateRequestV2:
    try:
        if type(value) is CommitCertificateRequestV2:
            value = value.to_dict()
        return CommitCertificateRequestV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("commit certificate requires an exact authority domain")


def _require_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit certificate requires StateReader v2") from exc
    if not conforms:
        raise TypeError("commit certificate requires StateReader v2")


__all__: tuple[str, ...] = ()
