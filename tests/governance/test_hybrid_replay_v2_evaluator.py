from __future__ import annotations

import inspect
import json
import pickle

import pytest

import pheroos.governance._swarm.pipeline as hybrid_pipeline

from pheroos.governance import (
    PolicyAdjustmentProposal,
)
from pheroos.governance._swarm.pipeline import evaluate_hybrid_collective_step
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
)
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._hybrid_replay_v2.evaluator import (
    evaluate_hybrid_collective_step_v2,
)
from pheroos.governance._hybrid_replay_v2.operations import (
    advance_hybrid_replay_state_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
    project_collective_policy_v2,
    restore_hybrid_replay_inputs_v2,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
)
from pheroos.governance._swarm.replay import _hybrid_authority_snapshot
from pheroos.governance._swarm.replay import _issue_hybrid_replay_state
from pheroos.governance._swarm.replay import hybrid_collective_step_is_authoritative
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from tests.governance.test_hybrid_replay_v2_operations import _context
from tests.governance.test_hybrid_replay_v2_projection import (
    _fixture,
    _scoped_manifest,
    _step,
)
from tests.swarm.test_hybrid_pheromone_vertical_slice import (
    deposits,
    feedback,
    layer_proposals,
    verified_scout,
)


def _evaluate(
    *,
    context,
    current_step: int,
    replay_state=None,
    adjustment_id: str,
    adjustment_field: str = "pheromone_positive_weight",
    adjustment_value: object = 1.2,
    manifest: ScopedProtocolManifestV2 | None = None,
    neighborhood=None,
    domain_root: str | None = None,
    scope_ref: str | None = None,
    run_ref: str = "run:hybrid-replay",
    observed_epoch: int = 3,
) -> VerifiedHybridSourceStepV2:
    active_manifest = manifest or _scoped_manifest()
    target = active_manifest.quorum_policy.target
    active_topology = neighborhood or _fixture()[3]
    return evaluate_hybrid_collective_step_v2(
        domain_root=(
            context.domain.domain_root if domain_root is None else domain_root
        ),
        scope_ref=context.domain.scope_ref if scope_ref is None else scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        manifest=active_manifest,
        current_step=current_step,
        scout_reports=[
            verified_scout(f"scout:{current_step}:a", "candidate:alpha", target),
            verified_scout(f"scout:{current_step}:b", "candidate:alpha", target),
        ],
        topology=active_topology,
        verified_replay_state=replay_state,
        deposits=(deposits(target) if replay_state is None else []),
        feedback=(feedback(target) if replay_state is None else []),
        layer_proposals=(layer_proposals(target) if replay_state is None else []),
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id=f"layer:evolutionary:{current_step}",
                adjustments={adjustment_field: adjustment_value},
                provenance="runtime:evolutionary",
                trace_event_id=adjustment_id,
            )
        ],
    )


def _request(context, source, advance_ref: str):
    return build_hybrid_replay_advance_request_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
        advance_ref=advance_ref,
        source=source,
    )


def _commit(context, request, source):
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    return advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def test_genesis_evaluator_matches_v1_semantics_and_commits_bound_proof() -> None:
    context = _context(scope_ref="scope:hybrid-evaluator-genesis")
    source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:one",
    )
    expected = _step()

    assert type(source) is VerifiedHybridSourceStepV2
    assert _hybrid_authority_snapshot(source.source_step) == (
        _hybrid_authority_snapshot(expected)
    )
    request = _request(context, source, "advance:hybrid:evaluator:one")
    assert request.snapshot.manifest_root == _scoped_manifest().manifest_root
    assert request.snapshot.source_step_root
    attempt = _commit(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED


@pytest.mark.parametrize(
    "field",
    ["domain_root", "scope_ref", "run_ref", "observed_epoch"],
)
def test_genesis_source_context_cannot_be_restamped_or_substituted(
    field: str,
) -> None:
    context = _context(scope_ref=f"scope:hybrid-source-context:{field}")
    other = _context(scope_ref=f"scope:hybrid-source-context:{field}:other")
    source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id=f"trace:adjustment:source-context:{field}",
    )
    replacement: object = {
        "domain_root": other.domain.domain_root,
        "scope_ref": other.domain.scope_ref,
        "run_ref": "run:hybrid-replay:other",
        "observed_epoch": 4,
    }[field]
    source_arguments: dict[str, object] = {
        "context": context,
        "current_step": 1,
        "adjustment_id": f"trace:adjustment:source-context:{field}",
        field: replacement,
    }
    substituted = _evaluate(**source_arguments)  # type: ignore[arg-type]
    assert substituted.context_root != source.context_root

    request_arguments: dict[str, object] = {
        "domain_root": context.domain.domain_root,
        "scope_ref": context.domain.scope_ref,
        "run_ref": "run:hybrid-replay",
        "observed_epoch": 3,
        "advance_ref": f"advance:source-context:{field}:restamp",
        "source": source,
    }
    request_arguments[field] = replacement
    with pytest.raises(GovernanceError, match=field):
        build_hybrid_replay_advance_request_v2(  # type: ignore[arg-type]
            **request_arguments
        )

    request = _request(
        context,
        source,
        f"advance:source-context:{field}:advance-time",
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    before = context.store.snapshot_v2()
    rejected = advance_hybrid_replay_state_v2(
        request,
        source=substituted,
        authority_session=session,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None and rejected.failure.path == "/source"
    assert context.store.snapshot_v2() == before
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )


def test_evaluator_rejects_malformed_authority_context_before_issuance() -> None:
    context = _context(scope_ref="scope:hybrid-source-context:malformed")
    cases = (
        ("domain_root", "not-a-root"),
        ("scope_ref", ""),
        ("run_ref", ""),
        ("observed_epoch", True),
    )
    for field, value in cases:
        arguments: dict[str, object] = {
            "context": context,
            "current_step": 1,
            "adjustment_id": f"trace:adjustment:malformed:{field}",
            field: value,
        }
        with pytest.raises(ValueError, match=field):
            _evaluate(**arguments)  # type: ignore[arg-type]


def test_context_bound_source_exact_retry_is_idempotent() -> None:
    context = _context(scope_ref="scope:hybrid-source-context:exact-retry")
    source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:source-context:exact-retry",
    )
    request = _request(context, source, "advance:source-context:exact-retry")
    committed = _commit(context, request, source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert committed.committed_transition is not None
    before = context.store.snapshot_v2()

    retried = _commit(context, request, source)

    assert retried.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retried.committed_transition is not None
    assert retried.committed_transition.receipt.receipt_root == (
        committed.committed_transition.receipt.receipt_root
    )
    assert context.store.snapshot_v2() == before


@pytest.mark.parametrize(
    "field",
    ["domain_root", "scope_ref", "run_ref", "observed_epoch"],
)
def test_parent_source_evaluation_enforces_authority_context(field: str) -> None:
    context = _context(scope_ref=f"scope:hybrid-parent-context:{field}")
    other = _context(scope_ref=f"scope:hybrid-parent-context:{field}:other")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id=f"trace:adjustment:parent-context:{field}:one",
    )
    first_request = _request(
        context,
        first_source,
        f"advance:parent-context:{field}:one",
    )
    assert _commit(context, first_request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    parent = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    replacement: object = {
        "domain_root": other.domain.domain_root,
        "scope_ref": other.domain.scope_ref,
        "run_ref": "run:hybrid-replay:other",
        "observed_epoch": 2,
    }[field]
    arguments: dict[str, object] = {
        "context": context,
        "current_step": 2,
        "replay_state": parent,
        "adjustment_id": f"trace:adjustment:parent-context:{field}:two",
        field: replacement,
    }
    with pytest.raises(GovernanceError, match=field):
        _evaluate(**arguments)  # type: ignore[arg-type]


def test_parent_source_binds_the_new_observed_epoch_exactly() -> None:
    context = _context(scope_ref="scope:hybrid-parent-context:epoch")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:parent-context:epoch:one",
    )
    first_request = _request(context, first_source, "advance:parent-context:epoch:one")
    assert _commit(context, first_request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    parent = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    child_source = _evaluate(
        context=context,
        current_step=2,
        replay_state=parent,
        observed_epoch=4,
        adjustment_id="trace:adjustment:parent-context:epoch:two",
    )
    request = build_hybrid_replay_advance_request_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=4,
        advance_ref="advance:parent-context:epoch:two",
        source=child_source,
    )
    assert request.observed_epoch == 4
    with pytest.raises(GovernanceError, match="observed_epoch"):
        build_hybrid_replay_advance_request_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            run_ref="run:hybrid-replay",
            observed_epoch=5,
            advance_ref="advance:parent-context:epoch:restamped",
            source=child_source,
        )


def test_restart_rehydration_produces_exact_next_v1_output_and_trace() -> None:
    context = _context(scope_ref="scope:hybrid-evaluator-restart")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:restart:one",
    )
    first_request = _request(context, first_source, "advance:restart:one")
    assert _commit(context, first_request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    portable = json.loads(first_request.canonical_bytes())
    restarted = rehydrate_hybrid_replay_state_v2(
        portable,
        domain=context.domain,
        state_reader=context.store,
    )
    live = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )

    restarted_source = _evaluate(
        context=context,
        current_step=2,
        replay_state=restarted,
        adjustment_id="trace:adjustment:restart:two",
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
    )
    live_source = _evaluate(
        context=context,
        current_step=2,
        replay_state=live,
        adjustment_id="trace:adjustment:restart:two",
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
    )
    assert restarted_source.context_root == live_source.context_root
    assert _hybrid_authority_snapshot(restarted_source.source_step) == (
        _hybrid_authority_snapshot(live_source.source_step)
    )

    first_step = first_source.source_step
    protocol, _, candidates, neighborhood = _fixture()
    restored_legacy_input = restore_hybrid_replay_inputs_v2(first_request.snapshot)
    expected = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=first_step.effective_policy,
        target=protocol.quorum_policy.target,
        current_step=2,
        scout_reports=[
            verified_scout(
                "scout:2:a", "candidate:alpha", protocol.quorum_policy.target
            ),
            verified_scout(
                "scout:2:b", "candidate:alpha", protocol.quorum_policy.target
            ),
        ],
        topology=neighborhood,
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id="layer:evolutionary:2",
                adjustments={"pheromone_exploration_floor": 0.25},
                provenance="runtime:evolutionary",
                trace_event_id="trace:adjustment:restart:two",
            )
        ],
        # This branch intentionally exercises the legacy v1 evaluator for the
        # differential vector. The v2 production path above does not issue or
        # consume this process-local compatibility token.
        replay_state=_issue_hybrid_replay_state(
            restored_legacy_input.replay_state,
            protocol_id=protocol.id,
            target=protocol.quorum_policy.target,
        ),
        fallback_candidate_id=protocol.quorum_policy.fallback_candidate,
    )
    restarted_step = restarted_source.source_step
    assert restarted_step.decision == expected.decision
    assert restarted_step.state == expected.state
    assert restarted_step.active_trails == expected.active_trails
    assert restarted_step.trace_events == expected.trace_events
    assert dict(restarted_step.deposit_replay_receipts) == dict(
        expected.deposit_replay_receipts
    )
    assert dict(restarted_step.diffusion_replay_receipts) == dict(
        expected.diffusion_replay_receipts
    )
    assert dict(restarted_step.feedback_replay_receipts) == dict(
        expected.feedback_replay_receipts
    )
    assert dict(restarted_step.adjustment_replay_receipts) == dict(
        expected.adjustment_replay_receipts
    )
    assert project_collective_policy_v2(restarted_step.effective_policy) == (
        project_collective_policy_v2(expected.effective_policy)
    )
    restarted_request = _request(
        context,
        restarted_source,
        "advance:restart:two",
    )
    live_request = _request(context, live_source, "advance:restart:two")
    assert restarted_request.canonical_bytes() == live_request.canonical_bytes()
    assert _commit(context, restarted_request, restarted_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )


@pytest.mark.parametrize("raw_kind", ["snapshot", "dict", "legacy"])
def test_raw_replay_shapes_fail_closed(raw_kind: str) -> None:
    context = _context(scope_ref=f"scope:hybrid-evaluator-raw:{raw_kind}")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id=f"trace:adjustment:raw:{raw_kind}",
    )
    request = _request(context, first_source, f"advance:raw:{raw_kind}")
    assert _commit(context, request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    if raw_kind == "snapshot":
        raw = request.snapshot
    elif raw_kind == "dict":
        raw = request.to_dict()
    else:
        raw = replay_state_from_hybrid_step(_step())
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _evaluate(
            context=context,
            current_step=2,
            replay_state=raw,
            adjustment_id=f"trace:adjustment:raw:child:{raw_kind}",
        )


def test_source_proof_is_nonportable_and_bare_v1_step_is_never_accepted() -> None:
    context = _context(scope_ref="scope:hybrid-evaluator-bare")
    source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:bare",
    )
    request = _request(context, source, "advance:bare")
    legacy = source.source_step
    with pytest.raises(TypeError, match="VerifiedHybridSourceStepV2"):
        build_hybrid_replay_advance_request_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            run_ref="run:hybrid-replay",
            observed_epoch=3,
            advance_ref="advance:bare:build",
            source=legacy,  # type: ignore[arg-type]
        )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    rejected = advance_hybrid_replay_state_v2(
        request,
        source=legacy,  # type: ignore[arg-type]
        authority_session=session,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None and rejected.failure.path == "/source"
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedHybridSourceStepV2()
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)


def test_v2_path_neither_reads_nor_issues_legacy_hybrid_sentinels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Hybrid Replay v2 touched a legacy issuance sentinel")

    monkeypatch.setattr(
        hybrid_pipeline,
        "hybrid_replay_state_is_authoritative",
        forbidden,
    )
    monkeypatch.setattr(hybrid_pipeline, "_issue_hybrid_collective_step", forbidden)
    context = _context(scope_ref="scope:hybrid-evaluator-no-legacy-token")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:no-legacy-token:one",
    )
    assert hybrid_collective_step_is_authoritative(first_source.source_step) is False
    first_request = _request(
        context,
        first_source,
        "advance:no-legacy-token:one",
    )
    assert _commit(context, first_request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    parent = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    second_source = _evaluate(
        context=context,
        current_step=2,
        replay_state=parent,
        adjustment_id="trace:adjustment:no-legacy-token:two",
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
    )
    assert hybrid_collective_step_is_authoritative(second_source.source_step) is False


def test_source_proof_nested_context_tampering_fails_closed() -> None:
    context = _context(scope_ref="scope:hybrid-evaluator-source-tamper")
    source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:source-tamper",
    )
    projection = object.__getattribute__(source, "_input_policy_projection")
    projection["pheromone_positive_weight"] = float(1.5).hex()

    with pytest.raises(GovernanceError, match="authority binding"):
        _ = source.context_root


def test_parent_manifest_and_topology_are_exact_context_bindings() -> None:
    context = _context(scope_ref="scope:hybrid-evaluator-context")
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:context:one",
    )
    request = _request(context, first_source, "advance:context:one")
    assert _commit(context, request, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    parent = rehydrate_hybrid_replay_state_v2(
        request.to_dict(), domain=context.domain, state_reader=context.store
    )

    changed = _scoped_manifest().to_dict()
    changed["id"] = "swarm.hybrid-pheromone.changed"
    changed_manifest = ScopedProtocolManifestV2.from_dict(changed)
    with pytest.raises(GovernanceError, match="manifest"):
        _evaluate(
            context=context,
            current_step=2,
            replay_state=parent,
            adjustment_id="trace:adjustment:context:manifest",
            manifest=changed_manifest,
        )

    neighborhood = _fixture()[3]
    changed_topology = type(neighborhood)(
        subjects=list(neighborhood.subjects),
        edges=[
            type(edge)(
                source_subject_type=edge.source_subject_type,
                source_subject_id=edge.source_subject_id,
                target_subject_type=edge.target_subject_type,
                target_subject_id=edge.target_subject_id,
                attenuation=(0.25 if index == 0 else edge.attenuation),
            )
            for index, edge in enumerate(neighborhood.edges)
        ],
    )
    with pytest.raises(GovernanceError, match="topology"):
        _evaluate(
            context=context,
            current_step=2,
            replay_state=parent,
            adjustment_id="trace:adjustment:context:topology",
            neighborhood=changed_topology,
        )


def test_superseded_and_sealed_parents_cannot_be_reused() -> None:
    context = _context(
        scope_ref="scope:hybrid-evaluator-position",
        operations=(
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    first_source = _evaluate(
        context=context,
        current_step=1,
        adjustment_id="trace:adjustment:position:one",
    )
    first = _request(context, first_source, "advance:position:one")
    assert _commit(context, first, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    old_parent = rehydrate_hybrid_replay_state_v2(
        first.to_dict(), domain=context.domain, state_reader=context.store
    )
    second_source = _evaluate(
        context=context,
        current_step=2,
        replay_state=old_parent,
        adjustment_id="trace:adjustment:position:two",
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.2,
    )
    second = _request(context, second_source, "advance:position:two")
    assert _commit(context, second, second_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _evaluate(
            context=context,
            current_step=3,
            replay_state=old_parent,
            adjustment_id="trace:adjustment:position:stale",
        )

    current = rehydrate_hybrid_replay_state_v2(
        second.to_dict(), domain=context.domain, state_reader=context.store
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref, context.grant.grant_ref
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        request_ref="request:hybrid-evaluator:retire",
        transition_id="transition:hybrid-evaluator:retire",
        stream_refs=tuple(sorted((grant_stream, second.stream_ref))),
        reason_ref="reason:complete",
        observed_epoch=3,
    )
    retire_session = open_governance_authority_session_v2(
        context.capability, retirement
    )
    assert (
        retire_governance_domain_v2(
            retirement, authority_session=retire_session
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _evaluate(
            context=context,
            current_step=3,
            replay_state=current,
            adjustment_id="trace:adjustment:position:sealed",
        )


def test_v2_signature_has_no_raw_replay_or_declaration_fragments() -> None:
    parameters = inspect.signature(evaluate_hybrid_collective_step_v2).parameters
    assert "manifest" in parameters
    assert {
        "protocol_id",
        "candidate_set",
        "base_policy",
        "target",
        "existing_trails",
        "processed_pheromone_event_ids",
        "processed_feedback_ids",
        "processed_adjustment_ids",
        "replay_state",
    }.isdisjoint(parameters)
