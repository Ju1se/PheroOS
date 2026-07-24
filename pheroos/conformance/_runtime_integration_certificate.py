"""Real Store-backed Certificate currentness fixture for Runtime Integration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json

from pheroos.conformance.checks._commit_finality_v2_certificate_support import (
    verified_certificate_v2,
)
from pheroos.conformance.checks._commit_finality_v2_decision_support import (
    FinalityDecisionV2Vertical,
    certified_decision_vertical_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateBodyV2,
    CommitCertificateRequestV2,
    CommitCertificateSnapshotV2,
    CommitCertificateStatusV2,
    VerifiedCommitCertificateStateV2,
    rehydrate_commit_certificate_state_v2,
    verified_commit_certificate_finality_input_v2,
)
from pheroos.governance.commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
)
from pheroos.governance._commit_certificate_v2.state_handle import (
    _verified_commit_certificate_state_material_v2,
)
from pheroos.governance._commit_finality_v2 import (
    _verified_commit_finality_input_material_v2,
)


@dataclass(frozen=True, slots=True)
class _CertificateStateObservationV1:
    """One fully revalidated, point-in-time observation of an opaque state."""

    snapshot: CommitCertificateSnapshotV2
    projection_matches: bool
    is_current: bool


def build_recovered_certificate_states_v1(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    label: str,
    scope_ref: str,
    with_successor: bool,
) -> tuple[
    VerifiedCommitCertificateStateV2,
    VerifiedCommitCertificateStateV2 | None,
]:
    """Commit actual Certificate state and rebind handles after Store restart."""

    (
        image,
        observed_wire,
        successor_wire,
        _observed_projection_wire,
        _successor_projection_wire,
        _body_wire,
    ) = _certificate_fixture_bytes_v1(
        label,
        scope_ref,
        with_successor,
    )
    observed = CommitCertificateRequestV2.from_dict(json.loads(observed_wire))
    successor = (
        None
        if successor_wire is None
        else CommitCertificateRequestV2.from_dict(json.loads(successor_wire))
    )
    domain = adapter.create_domain_v2(scope_ref)
    if observed.domain_root != domain.domain_root:
        raise RuntimeError("Certificate fixture domain is not canonical")
    restarted = adapter.restart_store_v2(_replay_store_v1(image, adapter, scope_ref))
    recovered_observed = rehydrate_commit_certificate_state_v2(
        observed.to_dict(),
        domain=domain,
        state_reader=restarted,
    )
    recovered_successor = (
        None
        if successor is None
        else rehydrate_commit_certificate_state_v2(
            successor.to_dict(),
            domain=domain,
            state_reader=restarted,
        )
    )
    return recovered_observed, recovered_successor


def build_certificate_observation_material_v1(
    *,
    label: str,
    scope_ref: str,
    with_successor: bool,
) -> tuple[
    CommitFinalityProjectionV2,
    CommitFinalityProjectionV2 | None,
    CommitCertificateBodyV2,
]:
    """Return projections generated from the exact committed fixture states."""

    (
        _image,
        _observed_wire,
        _successor_wire,
        observed_projection_wire,
        successor_projection_wire,
        body_wire,
    ) = _certificate_fixture_bytes_v1(label, scope_ref, with_successor)
    return (
        CommitFinalityProjectionV2.from_dict(json.loads(observed_projection_wire)),
        (
            None
            if successor_projection_wire is None
            else CommitFinalityProjectionV2.from_dict(
                json.loads(successor_projection_wire)
            )
        ),
        CommitCertificateBodyV2.from_dict(json.loads(body_wire)),
    )


def certificate_state_matches_projection_v1(
    state: VerifiedCommitCertificateStateV2,
    projection: CommitFinalityProjectionV2,
) -> bool:
    """Reverify one opaque state and compare every portable projection field."""

    observation = _observe_certificate_state_v1(state, projection)
    return observation is not None and observation.projection_matches


def _observe_certificate_state_v1(
    state: VerifiedCommitCertificateStateV2,
    projection: CommitFinalityProjectionV2,
) -> _CertificateStateObservationV1 | None:
    """Revalidate once and derive binding plus currentness from one Store view."""

    try:
        material = _verified_commit_certificate_state_material_v2(state)
        snapshot = material.snapshot
        body = snapshot.certificate.body
        if snapshot.status is CommitCertificateStatusV2.VERIFIED:
            status = CommitFinalityStatusV2.VERIFIED
        elif snapshot.status is CommitCertificateStatusV2.CONFLICT:
            status = CommitFinalityStatusV2.CONFLICT
        else:
            return None
        committed = material.view.committed_transition
        if committed is None:
            return None
        expected = (
            CommitFinalityOwnerV2.CERTIFICATE,
            status,
            snapshot.stream_ref,
            snapshot.revision,
            snapshot.transition_id,
            snapshot.snapshot_root,
            material.head.head_root,
            committed.receipt.receipt_root,
            body.seal_transition_id,
            body.seal_root,
            body.frozen_dependency_root,
            snapshot.current_step + 1,
            tuple(snapshot.reason_codes),
        )
        observed = (
            projection.owner,
            projection.status,
            projection.stream_ref,
            projection.revision,
            projection.transition_id,
            projection.snapshot_root,
            projection.head_root,
            projection.receipt_root,
            projection.seal_transition_id,
            projection.seal_root,
            projection.frozen_dependency_root,
            projection.verified_at_step,
            tuple(projection.reason_codes),
        )
        position = material.view.position_observation
        if position is None:
            return None
    except Exception:
        return None
    return _CertificateStateObservationV1(
        snapshot=snapshot,
        projection_matches=observed == expected,
        is_current=position.position is GovernanceCommitPositionV2.CURRENT,
    )


@lru_cache(maxsize=8)
def _certificate_fixture_bytes_v1(
    label: str,
    scope_ref: str,
    with_successor: bool,
) -> tuple[bytes, bytes, bytes | None, bytes, bytes | None, bytes]:
    """Cache bounded immutable fixture bytes, never Store or authority handles."""

    source_adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    vertical = certified_decision_vertical_v2(
        source_adapter,
        label,
        scope_ref=scope_ref,
    )
    observed = verified_certificate_v2(
        vertical,
        f"{label}:observed",
        certificate_id=f"certificate:runtime-integration:{label}",
    )
    observed_projection = _certificate_projection_v1(vertical, observed.state)
    observed_body = observed.state.snapshot.certificate.body
    successor = (
        verified_certificate_v2(
            vertical,
            f"{label}:successor",
            parent_state=observed.state,
            certificate_id=f"certificate:runtime-integration:{label}",
        )
        if with_successor
        else None
    )
    successor_projection = (
        None
        if successor is None
        else _certificate_projection_v1(vertical, successor.state)
    )
    support = vertical.context.support_context
    image = source_adapter.observe_store_v2(support.store, scope_ref).get("image_bytes")
    if type(image) is not bytes:
        raise RuntimeError("Certificate source Store image is unavailable")
    return (
        image,
        _canonical_request_bytes_v1(observed.request),
        (None if successor is None else _canonical_request_bytes_v1(successor.request)),
        _canonical_record_bytes_v1(observed_projection.to_dict()),
        (
            None
            if successor_projection is None
            else _canonical_record_bytes_v1(successor_projection.to_dict())
        ),
        _canonical_record_bytes_v1(observed_body.to_dict()),
    )


def _certificate_projection_v1(
    vertical: FinalityDecisionV2Vertical,
    state: VerifiedCommitCertificateStateV2,
) -> CommitFinalityProjectionV2:
    decision_state = vertical.state
    verified = verified_commit_certificate_finality_input_v2(
        state,
        sealed_decision_state=decision_state,
        current_step=decision_state.snapshot.current_step + 1,
    )
    material = _verified_commit_finality_input_material_v2(verified)
    return CommitFinalityProjectionV2.from_dict(material.projection.to_dict())


def _canonical_request_bytes_v1(request: CommitCertificateRequestV2) -> bytes:
    return _canonical_record_bytes_v1(request.to_dict())


def _canonical_record_bytes_v1(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _replay_store_v1(
    image: bytes,
    target_adapter: GovernanceStateStoreConformanceAdapterV2,
    scope_ref: str,
) -> GovernanceStateStoreV2:
    payload = json.loads(image)
    receipts = payload.get("receipts")
    if type(receipts) is not list:
        raise RuntimeError("Certificate source Store receipts are invalid")
    domain = target_adapter.create_domain_v2(scope_ref)
    target = target_adapter.create_store_v2((domain,))
    for item in receipts:
        if type(item) is not dict or type(item.get("batch")) is not dict:
            raise RuntimeError("Certificate source Store batch is invalid")
        batch = GovernanceCommitBatchV2.from_dict(item["batch"])
        attempt = target.atomic_commit_v2(batch)
        if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
            raise RuntimeError("independent Certificate batch replay failed")
    return target


__all__: tuple[str, ...] = ()
