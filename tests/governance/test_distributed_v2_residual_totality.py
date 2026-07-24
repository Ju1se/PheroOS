from __future__ import annotations

from dataclasses import fields, replace
from typing import Any, cast

import pytest

from pheroos.conformance.checks._distributed_v2_context_support import (
    capability_v2,
    root_v2,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    DistributedV2Vertical,
    build_verified_distributed_vertical_v2,
    external_witness_conflict_observation_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance._distributed_v2 import operations as operations_module
from pheroos.governance._distributed_v2 import (
    source_evaluation as source_evaluation_module,
)
from pheroos.governance._distributed_v2.authority_context import (
    _distributed_authority_context_v2,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.events import _event_type
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedEquivocationFindingV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
    _canonical_findings,
    _validate_finding_observations,
)
from pheroos.governance._distributed_v2.operations import (
    _committed_view_matches,
    _dependency_or_parent_changed,
    _finality_failure,
    _load_parent,
    _validated_session,
    _validated_source_and_heads,
)
from pheroos.governance._distributed_v2.reducer import (
    reduce_certificate_v2,
    reduce_witness_conflict_observation_v2,
)
from pheroos.governance._distributed_v2.source import (
    prepare_distributed_epoch_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_conflict_observation_v2,
)
from pheroos.governance._distributed_v2.source_evaluation import _verified_witnesses_v2
from pheroos.governance._distributed_v2.state_handle import (
    distributed_state_is_current_v2,
    require_current_distributed_state_v2,
    verified_distributed_commit_finality_input_v2,
)
from pheroos.governance._distributed_v2.state_records import _verify_parent
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedWitnessAttestationVerifierV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
)
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneV2,
    DistributedMutationKindV2,
    VerifiedDistributedAdvanceSourceV2,
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
)


@pytest.fixture(scope="module")
def vertical() -> DistributedV2Vertical:
    return build_verified_distributed_vertical_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "distributed-v2-residual-totality",
    )


@pytest.fixture(scope="module")
def observation(
    vertical: DistributedV2Vertical,
) -> DistributedWitnessConflictObservationV2:
    return external_witness_conflict_observation_v2(
        vertical,
        "distributed-v2-residual-totality",
    )


def _root(label: str) -> str:
    return root_v2(f"distributed-v2-residual-totality:{label}")


def _forge(instance: Any, **changes: object) -> Any:
    forged = object.__new__(type(instance))
    for field in fields(instance):
        object.__setattr__(
            forged,
            field.name,
            changes.get(field.name, getattr(instance, field.name)),
        )
    return forged


def _proposal_successor(
    vertical: DistributedV2Vertical,
    label: str,
) -> tuple[object, VerifiedDistributedAdvanceSourceV2]:
    return prepare_distributed_proposal_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        manifest=vertical.context.manifest,
        proposal_ref=f"proposal:distributed:residual:{label}",
        proposer_ref="principal:alpha",
        proposal_nonce=f"nonce:distributed:residual:{label}",
        provenance_ref=f"urn:test:distributed:residual:{label}",
        source_trace_roots=(_root(f"{label}:trace"),),
        mutation_ref=f"mutation:distributed:residual:{label}",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.proposal,
    )


def _prepare_conflict(
    vertical: DistributedV2Vertical,
    observation: DistributedWitnessConflictObservationV2,
    *,
    verifier: object | None = None,
):
    return prepare_distributed_witness_conflict_observation_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        parent_state=vertical.witness,
        manifest=vertical.context.manifest,
        observation=observation,
        trusted_verifier=vertical.verifier if verifier is None else verifier,
        mutation_ref="mutation:distributed:residual:conflict",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )


def _committed_view(
    vertical: DistributedV2Vertical,
    lane: DistributedLaneV2 = DistributedLaneV2.PROPOSAL,
) -> GovernanceCommitViewV2:
    request = {
        DistributedLaneV2.EPOCH: vertical.epoch_request,
        DistributedLaneV2.PROPOSAL: vertical.proposal_request,
        DistributedLaneV2.WITNESS: vertical.witness_request,
        DistributedLaneV2.CERTIFICATE: vertical.certificate_request,
    }[lane]
    return vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )


def _finding(label: str) -> DistributedEquivocationFindingV2:
    return DistributedEquivocationFindingV2(
        principal_ref=f"principal:{label}",
        epoch=1,
        first_semantic_value_root=_root(f"{label}:semantic:first"),
        second_semantic_value_root=_root(f"{label}:semantic:second"),
        first_witness_root=_root(f"{label}:witness:first"),
        second_witness_root=_root(f"{label}:witness:second"),
    )


def test_portable_conflict_and_finding_round_trips_cover_nonempty_paths(
    observation: DistributedWitnessConflictObservationV2,
) -> None:
    assert (
        DistributedWitnessConflictObservationV2.from_dict(observation.to_dict())
        == observation
    )
    first = _finding("first")
    second = _finding("second")
    assert DistributedEquivocationFindingV2.from_dict(first.to_dict()) == first
    assert _canonical_findings((first,)) == (first,)
    _validate_finding_observations((), (first, second))


def test_epoch_transition_with_conflict_requires_recovery_authority(
    vertical: DistributedV2Vertical,
) -> None:
    certificate = cast(
        DistributedEpochStateV2,
        vertical.epoch.snapshot.state,
    ).transition_certificate
    with pytest.raises(ValueError, match="requires recovery authority"):
        replace(
            certificate,
            from_epoch=certificate.to_epoch,
            to_epoch=certificate.to_epoch + 1,
            prior_epoch_snapshot_root=vertical.epoch.snapshot.snapshot_root,
            conflict_history_roots=(_root("epoch:conflict"),),
            required_action_refs=("epoch_transition",),
            certificate_root="",
        )


def test_conflict_event_types_are_explicit() -> None:
    assert (
        _event_type(
            DistributedLaneV2.WITNESS,
            DistributedMutationKindV2.EQUIVOCATION_FROZEN,
        )
        == "distributed_witness_conflict_v2"
    )
    assert (
        _event_type(
            DistributedLaneV2.CERTIFICATE,
            DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN,
        )
        == "distributed_certificate_conflict_v2"
    )


def test_real_conflict_reducer_freezes_and_returns_snapshot(
    vertical: DistributedV2Vertical,
    observation: DistributedWitnessConflictObservationV2,
) -> None:
    snapshot = reduce_witness_conflict_observation_v2(
        observation=observation,
        parent=vertical.witness.snapshot,
        dependencies=vertical.witness.snapshot.dependencies,
        mutation_ref="mutation:distributed:residual:reducer-conflict",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )
    assert snapshot.mutation_kind is DistributedMutationKindV2.EQUIVOCATION_FROZEN
    state = cast(DistributedWitnessStateV2, snapshot.state)
    assert len(state.equivocations) == 1
    replayed = reduce_witness_conflict_observation_v2(
        observation=observation,
        parent=snapshot,
        dependencies=snapshot.dependencies,
        mutation_ref="mutation:distributed:residual:reducer-conflict-replay",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )
    replayed_state = cast(DistributedWitnessStateV2, replayed.state)
    assert replayed_state.equivocations == state.equivocations


def test_certificate_reducer_records_a_distinct_value_conflict(
    vertical: DistributedV2Vertical,
) -> None:
    parent = vertical.certificate.snapshot
    certificate = cast(
        DistributedCertificateStateV2,
        parent.state,
    ).certificates[0]
    distinct = _forge(
        certificate,
        value=_forge(
            certificate.value,
            semantic_value_root=_root("certificate:distinct-semantic-value"),
        ),
        certificate_root=_root("certificate:distinct"),
    )
    snapshot = reduce_certificate_v2(
        certificate=distinct,
        parent=parent,
        dependencies=parent.dependencies,
        mutation_ref="mutation:distributed:residual:certificate-conflict",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
    )
    assert (
        snapshot.mutation_kind is DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN
    )


def test_source_nonportability_and_real_conflict_preparation(
    vertical: DistributedV2Vertical,
    observation: DistributedWitnessConflictObservationV2,
) -> None:
    _, source = _proposal_successor(vertical, "source-reduce-ex")
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce_ex__(4)
    request, prepared = _prepare_conflict(vertical, observation)
    assert (
        request.snapshot.mutation_kind is DistributedMutationKindV2.EQUIVOCATION_FROZEN
    )
    assert type(prepared) is VerifiedDistributedAdvanceSourceV2


class _RejectingWitnessVerifier:
    def verify_distributed_witness_v2(self, **_kwargs: object) -> bool:
        return False


def test_conflict_preparation_rejects_untrusted_attestation(
    vertical: DistributedV2Vertical,
    observation: DistributedWitnessConflictObservationV2,
) -> None:
    with pytest.raises(ValueError, match="attestation is not trusted"):
        _prepare_conflict(
            vertical,
            observation,
            verifier=_RejectingWitnessVerifier(),
        )


def test_epoch_preparation_requires_parent_when_lane_is_initialized(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(ValueError, match="parent state is required"):
        prepare_distributed_epoch_v2(
            membership_state=vertical.identity.membership,
            manifest=vertical.context.manifest,
            transition_certificate_ref="certificate:distributed:residual:epoch",
            mutation_ref="mutation:distributed:residual:epoch",
            mutation_issuer_ref=vertical.context.grant.issuer_ref,
            current_step=10,
            provenance_ref="urn:test:distributed:residual:epoch",
            source_trace_roots=(_root("epoch:trace"),),
        )


def test_existing_commit_reconciliation_and_committed_match(
    vertical: DistributedV2Vertical,
) -> None:
    request = vertical.proposal_request
    session = open_distributed_authority_session_v2(
        capability_v2(vertical.context, request.observed_epoch),
        request,
    )
    state, failure = _validated_session(session, request)
    assert failure is None
    assert state is not None
    assert _committed_view_matches(_committed_view(vertical), request, state)
    attempt = advance_distributed_commit_v2(
        request,
        source=object(),
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED


def test_advance_returns_preparation_failure(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, source = _proposal_successor(vertical, "advance-preparation-failure")
    request = cast(Any, request)
    session = open_distributed_authority_session_v2(
        capability_v2(vertical.context, request.observed_epoch),
        request,
    )
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    failure = _finality_failure(request, missing)
    monkeypatch.setattr(operations_module, "_reconcile", lambda *_args: None)
    monkeypatch.setattr(
        operations_module,
        "_validated_source_and_heads",
        lambda *_args: failure,
    )
    assert (
        advance_distributed_commit_v2(
            request,
            source=source,
            authority_session=session,
        )
        is failure
    )


def test_source_validation_returns_parent_failure(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, source = _proposal_successor(vertical, "parent-failure")
    request = cast(Any, request)
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    failure = _finality_failure(request, missing)
    monkeypatch.setattr(operations_module, "_load_parent", lambda *_args: failure)
    assert (
        _validated_source_and_heads(
            vertical.context.store,
            vertical.context.domain,
            request,
            source,
        )
        is failure
    )


def test_source_rebuild_exception_distinguishes_race_from_invalidity(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, source = _proposal_successor(vertical, "source-rebuild-exception")
    request = cast(Any, request)

    def fail_rebuild(*_args: object, **_kwargs: object) -> object:
        raise ValueError("controlled source rebuild failure")

    monkeypatch.setattr(
        operations_module,
        "verify_distributed_source_v2",
        fail_rebuild,
    )
    monkeypatch.setattr(
        operations_module,
        "_dependency_or_parent_changed",
        lambda *_args: True,
    )
    raced = _validated_source_and_heads(
        vertical.context.store,
        vertical.context.domain,
        request,
        source,
    )
    assert isinstance(raced, GovernanceCommitAttemptV2)
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED

    monkeypatch.setattr(
        operations_module,
        "_dependency_or_parent_changed",
        lambda *_args: False,
    )
    invalid = _validated_source_and_heads(
        vertical.context.store,
        vertical.context.domain,
        request,
        source,
    )
    assert isinstance(invalid, GovernanceCommitAttemptV2)
    assert invalid.disposition is GovernanceCommitDispositionV2.INVALID


class _PositionStore:
    def __init__(
        self,
        delegate: object,
        *,
        stream_ref: str,
        transition_id: str,
        replacement: GovernanceCommitViewV2,
    ) -> None:
        self.delegate = delegate
        self.stream_ref = stream_ref
        self.transition_id = transition_id
        self.replacement = replacement

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> object:
        if stream_ref == self.stream_ref and transition_id == self.transition_id:
            return self.replacement
        return self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )


def test_noncurrent_parent_is_rejected_after_historical_verification(
    vertical: DistributedV2Vertical,
) -> None:
    request, _ = _proposal_successor(vertical, "superseded-parent")
    request = cast(Any, request)
    current = _committed_view(vertical)
    assert current.position_observation is not None
    position = replace(
        current.position_observation,
        observed_revision=current.position_observation.observed_revision + 1,
        observed_head_root=_root("superseded:current-head"),
        position=GovernanceCommitPositionV2.SUPERSEDED,
        observation_root="",
    )
    superseded = replace(
        current,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
        view_root="",
    )
    store = _PositionStore(
        vertical.context.store,
        stream_ref=request.stream_ref,
        transition_id=request.parent_transition_id,
        replacement=superseded,
    )
    result = _load_parent(
        cast(Any, store),
        vertical.context.domain,
        request,
    )
    assert isinstance(result, GovernanceCommitAttemptV2)
    assert result.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED


def test_dependency_race_recheck_covers_parent_and_dependency_paths(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _proposal_successor(vertical, "race-recheck")
    request = cast(Any, request)
    parent = vertical.context.store.load_head_v2(
        request.scope_ref,
        request.stream_ref,
    )
    missing = vertical.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        "transition:missing",
    )
    failure = _finality_failure(request, missing)

    monkeypatch.setattr(
        operations_module,
        "_load_exact_head",
        lambda *_args: failure,
    )
    assert _dependency_or_parent_changed(
        vertical.context.store,
        vertical.context.domain,
        request,
        parent,
    )

    monkeypatch.setattr(
        operations_module,
        "_load_exact_head",
        lambda *_args: parent,
    )
    monkeypatch.setattr(
        operations_module,
        "_load_dependency_heads",
        lambda *_args: failure,
    )
    assert _dependency_or_parent_changed(
        vertical.context.store,
        vertical.context.domain,
        request,
        parent,
    )


def test_current_handle_and_finality_projection_success(
    vertical: DistributedV2Vertical,
) -> None:
    with pytest.raises(TypeError, match="not portable"):
        vertical.proposal.__reduce_ex__(4)
    assert (
        require_current_distributed_state_v2(vertical.proposal).snapshot_root
        == vertical.proposal.snapshot.snapshot_root
    )
    assert distributed_state_is_current_v2(vertical.proposal)
    projected = verified_distributed_commit_finality_input_v2(
        vertical.certificate,
        proposal_state=vertical.proposal,
        witness_state=vertical.witness,
        epoch_state=vertical.epoch,
        sealed_decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    assert projected is not None


def test_parent_history_verification_recurses_to_genesis(
    vertical: DistributedV2Vertical,
) -> None:
    parent = vertical.proposal.snapshot
    child = _forge(
        parent,
        revision=parent.revision + 1,
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
    )
    _verify_parent(child, vertical.context.domain, vertical.context.store)


def test_verified_witness_selection_exhausts_existing_principal_branch(
    vertical: DistributedV2Vertical,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = cast(
        DistributedProposalStateV2,
        vertical.proposal.snapshot.state,
    ).proposals[0]
    witness_state = cast(
        DistributedWitnessStateV2,
        vertical.witness.snapshot.state,
    )
    witness = witness_state.witnesses[0]
    later = _forge(witness, witness_root="sha256:" + ("f" * 64))
    context = _distributed_authority_context_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )
    monkeypatch.setattr(
        source_evaluation_module,
        "verify_distributed_witness_v2",
        lambda *_args, **_kwargs: True,
    )
    selected = _verified_witnesses_v2(
        context=context,
        proposals={proposal.proposal_digest: proposal},
        witness_state=_forge(witness_state, witnesses=(witness, later)),
        current_step=10,
        trusted_verifier=vertical.verifier,
    )
    assert selected == (witness,)


def test_verifier_protocol_declaration_is_inert() -> None:
    assert (
        DistributedWitnessAttestationVerifierV2.verify_distributed_witness_v2(
            object(),
            principal_ref="principal:test",
            verification_root=_root("protocol:verification"),
            signing_root=_root("protocol:signing"),
            attestation_ref="attestation:test",
        )
        is None
    )
