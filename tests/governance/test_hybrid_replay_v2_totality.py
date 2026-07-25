from __future__ import annotations

from collections.abc import Mapping
from copy import copy, deepcopy
from dataclasses import replace
from enum import Enum
from typing import Any, cast

import pytest

from pheroos.governance import replay_state_from_hybrid_step
from pheroos.governance._authority_session_v2.operations import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance._hybrid_replay_v2.canonical import (
    _canonical_hybrid_value_v2,
)
from pheroos.governance._hybrid_replay_v2.evaluator import (
    _manifest_context,
    _require_parent_declarations,
)
from pheroos.governance._hybrid_replay_v2.operations import (
    _continuity_failure,
    advance_hybrid_replay_state_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    _reject_json_constant,
    _strict_json_object_pairs,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _detach_json,
    _issue_verified_hybrid_source_step_v2,
    _source_current_step,
    _topology_attenuation,
    _validate_source_step_v2,
    _verified_hybrid_source_material_v2,
)
from pheroos.governance._pheromone.records import PheromoneNeighborhood
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_protocol_manifest_v2_from_dict,
)
from tests.governance.test_hybrid_replay_v2_evaluator import (
    _commit as commit_evaluated_source,
)
from tests.governance.test_hybrid_replay_v2_evaluator import (
    _evaluate as evaluate_source,
)
from tests.governance.test_hybrid_replay_v2_evaluator import (
    _request as request_from_evaluated_source,
)
from tests.governance.test_hybrid_replay_v2_operations import (
    _advance,
    _context,
    _request as build_operation_request,
    _source_for,
)
from tests.governance.test_hybrid_replay_v2_operations_semantic_gaps import (
    _plain,
    _rebuild_view,
)
from tests.governance.test_hybrid_replay_v2_projection import (
    _fixture,
    _scoped_manifest,
    _step,
)


class _CanonicalEnum(Enum):
    VALUE = "value"


class _StoreProxy:
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        self.store = store

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(self, batch: Any) -> Any:
        return self.store.atomic_commit_v2(batch)


class _ProtocolExplodingStoreProxy(_StoreProxy):
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        super().__init__(store)
        self.armed = False

    def __getattribute__(self, name: str) -> object:
        if name not in {"arm", "armed"} and object.__getattribute__(self, "armed"):
            raise RuntimeError("hostile StateStore protocol lookup")
        return object.__getattribute__(self, name)

    def arm(self) -> None:
        object.__setattr__(self, "armed", True)


class _ParentViewFaultStore(_StoreProxy):
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        parent_transition_id: str,
        fault: str,
    ) -> None:
        super().__init__(store)
        self.parent_transition_id = parent_transition_id
        self.fault = fault

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        if transition_id == self.parent_transition_id and self.fault == "missing":
            raise KeyError(transition_id)
        view = super().load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if transition_id != self.parent_transition_id:
            return view
        committed = view.committed_transition
        assert committed is not None
        transition = committed.batch.transition
        assert transition is not None
        state = cast(dict[str, Any], _plain(transition.state_records))
        state.pop("schema")
        return _rebuild_view(view, state_records=state)


def _valid_source(scope_ref: str) -> tuple[object, VerifiedHybridSourceStepV2]:
    context = _context(scope_ref=scope_ref)
    source = evaluate_source(
        context=context,
        current_step=1,
        adjustment_id=f"trace:adjustment:{scope_ref}",
    )
    return context, source


def _clone_source(source: VerifiedHybridSourceStepV2) -> VerifiedHybridSourceStepV2:
    clone = object.__new__(VerifiedHybridSourceStepV2)
    for name in VerifiedHybridSourceStepV2.__slots__:
        object.__setattr__(clone, name, object.__getattribute__(source, name))
    return clone


def _child_request(
    context: Any,
    parent_step: Any,
    parent_request: Any,
    suffix: str,
) -> Any:
    child_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(parent_step),
        policy=parent_step.effective_policy,
        adjustment_id=f"trace:adjustment:{suffix}",
    )
    return build_operation_request(
        context,
        child_step,
        advance_ref=f"advance:{suffix}",
        current_step=2,
        parent=parent_request.snapshot,
    )


def _capability_for_proxy(context: Any, proxy: _StoreProxy) -> Any:
    return bind_governance_issuer_capability_v2(
        cast(GovernanceStateStoreV2, proxy),
        context.domain,
        context.grant,
        "run:hybrid-replay",
        3,
    )


def test_private_canonicalizer_totality_guards_are_explicit() -> None:
    """Exercise pure canonical branches unreachable through strict ABI constructors."""

    assert _canonical_hybrid_value_v2(_CanonicalEnum.VALUE)[0] == "enum"
    assert _canonical_hybrid_value_v2({3, 1})[0] == "set"
    with pytest.raises(TypeError, match="unsupported Hybrid Replay v2 value"):
        _canonical_hybrid_value_v2(object())


def test_private_projection_json_parser_totality_guards_are_explicit() -> None:
    """Exercise JSON decoder callbacks that only malformed wire text can invoke."""

    with pytest.raises(ValueError, match="duplicate keys"):
        _strict_json_object_pairs([("field", 1), ("field", 2)])
    with pytest.raises(ValueError, match="non-finite constant"):
        _reject_json_constant("NaN")


def test_verified_source_handle_is_opaque_immutable_and_nonportable() -> None:
    _, source = _valid_source("scope:hybrid-replay-totality:opaque")

    assert repr(source) == "<VerifiedHybridSourceStepV2 redacted>"
    assert copy(source) is source
    assert deepcopy(source) is source
    with pytest.raises(AttributeError, match="immutable"):
        setattr(source, "context_root", "substituted")
    with pytest.raises(TypeError, match="final"):
        type("DerivedVerifiedHybridSource", (VerifiedHybridSourceStepV2,), {})
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        source.__getstate__()


def test_verified_source_material_rejects_forged_slot_shapes() -> None:
    missing = object.__new__(VerifiedHybridSourceStepV2)
    with pytest.raises(GovernanceError, match="proof is malformed"):
        _verified_hybrid_source_material_v2(missing)

    forged = object.__new__(VerifiedHybridSourceStepV2)
    for name in VerifiedHybridSourceStepV2.__slots__:
        object.__setattr__(forged, name, None)

    with pytest.raises(GovernanceError, match="material is malformed"):
        _verified_hybrid_source_material_v2(forged)


def test_verified_source_material_rechecks_current_step_binding() -> None:
    _, source = _valid_source("scope:hybrid-replay-totality:step-binding")
    forged = _clone_source(source)
    binding = object.__getattribute__(forged, "_binding")
    object.__setattr__(
        forged,
        "_binding",
        replace(binding, current_step=binding.current_step + 1),
    )

    with pytest.raises(GovernanceError, match="current_step changed"):
        _verified_hybrid_source_material_v2(forged)


def test_source_issuer_requires_exact_manifest_and_topology_types() -> None:
    context = _context(scope_ref="scope:hybrid-replay-totality:issuer-types")
    manifest, _, _, topology = _fixture()
    common = {
        "domain_root": context.domain.domain_root,
        "scope_ref": context.domain.scope_ref,
        "run_ref": "run:hybrid-replay",
        "observed_epoch": 3,
        "step": _step(),
        "input_policy_projection": {},
        "candidate_projection_root": "",
        "base_policy_projection_root": "",
        "topology_projection_root": "",
        "parent_snapshot": None,
        "current_step": 1,
    }

    with pytest.raises(TypeError, match="exact ScopedProtocolManifestV2"):
        _issue_verified_hybrid_source_step_v2(
            manifest=cast(ScopedProtocolManifestV2, object()),
            topology=topology,
            **common,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="exact PheromoneNeighborhood"):
        _issue_verified_hybrid_source_step_v2(
            manifest=manifest,
            topology=cast(PheromoneNeighborhood, object()),
            **common,  # type: ignore[arg-type]
        )


def test_private_source_step_totality_guards_are_explicit() -> None:
    """Exercise source-proof guards dominated by exact evaluated-step issuance."""

    manifest, _, _, _ = _fixture()
    step = _step()
    protocol_ref = manifest.id
    target_ref = manifest.quorum_policy.target

    with pytest.raises(GovernanceError, match="one pheromone_score"):
        _source_current_step(
            replace(
                step,
                trace_events=tuple(
                    event
                    for event in step.trace_events
                    if event.event_type != "pheromone_score"
                ),
            )
        )

    score = next(
        event for event in step.trace_events if event.event_type == "pheromone_score"
    )
    malformed_score = replace(
        score,
        lineage={**score.lineage, "current_step": True},
    )
    with pytest.raises(GovernanceError, match="current_step is malformed"):
        _source_current_step(
            replace(
                step,
                trace_events=tuple(
                    malformed_score if event is score else event
                    for event in step.trace_events
                ),
            )
        )

    with pytest.raises(GovernanceError, match="not evaluation-complete"):
        _validate_source_step_v2(object(), protocol_ref, target_ref)
    with pytest.raises(GovernanceError, match="not evaluation-complete"):
        _validate_source_step_v2(
            replace(step, trace_events=()),
            protocol_ref,
            target_ref,
        )
    with pytest.raises(GovernanceError, match="not evaluation-complete"):
        _validate_source_step_v2(
            replace(step, processed_feedback_ids=frozenset()),
            protocol_ref,
            target_ref,
        )


def test_private_source_projection_totality_guards_are_explicit() -> None:
    """Exercise pure projection guards unreachable from exact topology models."""

    with pytest.raises(TypeError, match="attenuation must be numeric"):
        _topology_attenuation("0.5")
    with pytest.raises(TypeError, match="not canonical JSON"):
        _detach_json(object())


def test_manifest_context_rejects_nonexact_nonhybrid_and_cross_fallback_inputs() -> (
    None
):
    with pytest.raises(TypeError, match="exact ScopedProtocolManifestV2"):
        _manifest_context(cast(ScopedProtocolManifestV2, object()))

    payload = _scoped_manifest().to_dict()
    payload["collective_decision_policy"]["mode"] = "quorum"  # type: ignore[index]
    nonhybrid = scoped_protocol_manifest_v2_from_dict(payload)
    with pytest.raises(GovernanceError, match="declared Hybrid policy"):
        _manifest_context(nonhybrid)

    cross_fallback = ScopedProtocolManifestV2.from_dict(_scoped_manifest().to_dict())
    policy = cross_fallback.collective_decision_policy
    assert policy is not None
    object.__setattr__(policy, "fallback_candidate", "candidate:alpha")
    with pytest.raises(GovernanceError, match="fallbacks must match"):
        _manifest_context(cross_fallback)


@pytest.mark.parametrize("field", ("protocol_ref", "target_ref"))
def test_private_parent_declaration_identity_guards_are_explicit(field: str) -> None:
    """Exercise snapshot identity guards dominated by snapshot root validation."""

    context, source = _valid_source(
        f"scope:hybrid-replay-totality:parent-declaration:{field}"
    )
    request = request_from_evaluated_source(
        context,
        source,
        f"advance:hybrid-replay-totality:parent-declaration:{field}",
    )
    parent = request.snapshot
    payload = parent.to_dict()
    object.__setattr__(parent, field, f"substituted:{field}")

    with pytest.raises(GovernanceError, match=field.removesuffix("_ref")):
        _require_parent_declarations(
            parent,
            manifest=_scoped_manifest(),
            candidate_projection=cast(
                dict[str, object], payload["candidate_projection"]
            ),
            base_policy_projection=cast(
                dict[str, object], payload["policy_projection"]
            ),
            topology_projection=cast(dict[str, object], payload["topology_projection"]),
        )


def test_public_evaluator_requires_current_step_to_advance_verified_parent() -> None:
    context, source = _valid_source("scope:hybrid-replay-totality:parent-current-step")
    request = request_from_evaluated_source(
        context,
        source,
        "advance:hybrid-replay-totality:parent-current-step",
    )
    attempt = commit_evaluated_source(context, request, source)
    assert attempt.committed_transition is not None

    parent = rehydrate_hybrid_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )
    with pytest.raises(GovernanceError, match="must advance its verified parent"):
        evaluate_source(
            context=context,
            current_step=1,
            replay_state=parent,
            adjustment_id="trace:adjustment:parent-current-step:rejected",
        )


def test_public_advance_normalizes_dynamic_store_protocol_failure() -> None:
    context = _context(scope_ref="scope:hybrid-replay-totality:store-protocol")
    step = _step()
    request = build_operation_request(
        context,
        step,
        advance_ref="advance:hybrid-replay-totality:store-protocol",
        current_step=1,
    )
    proxy = _ProtocolExplodingStoreProxy(context.store)
    capability = _capability_for_proxy(context, proxy)
    session = open_hybrid_replay_authority_session_v2(capability, request)
    proxy.arm()

    attempt = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.path == "/authority_session"


def test_public_advance_normalizes_malformed_exact_source_handle() -> None:
    context = _context(scope_ref="scope:hybrid-replay-totality:malformed-source")
    step = _step()
    request = build_operation_request(
        context,
        step,
        advance_ref="advance:hybrid-replay-totality:malformed-source",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    forged = object.__new__(VerifiedHybridSourceStepV2)
    for name in VerifiedHybridSourceStepV2.__slots__:
        object.__setattr__(forged, name, None)

    attempt = advance_hybrid_replay_state_v2(
        request,
        source=forged,
        authority_session=session,
    )

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.path == "/source"


def test_public_advance_normalizes_missing_parent_view_exception() -> None:
    context = _context(scope_ref="scope:hybrid-replay-totality:missing-parent")
    parent_step = _step()
    parent_request = build_operation_request(
        context,
        parent_step,
        advance_ref="advance:hybrid-replay-totality:missing-parent:parent",
        current_step=1,
    )
    child_request = _child_request(
        context,
        parent_step,
        parent_request,
        "hybrid-replay-totality:missing-parent:child",
    )
    proxy = _ParentViewFaultStore(
        context.store,
        parent_request.transition_id,
        "missing",
    )
    capability = _capability_for_proxy(context, proxy)
    session = open_hybrid_replay_authority_session_v2(capability, child_request)

    attempt = advance_hybrid_replay_state_v2(
        child_request,
        source=_source_for(child_request),
        authority_session=session,
    )

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.path == "/snapshot/parent_transition_id"


def test_public_advance_normalizes_malformed_committed_parent_state() -> None:
    context = _context(scope_ref="scope:hybrid-replay-totality:malformed-parent")
    parent_step = _step()
    parent_request = build_operation_request(
        context,
        parent_step,
        advance_ref="advance:hybrid-replay-totality:malformed-parent:parent",
        current_step=1,
    )
    assert (
        _advance(context, parent_request, parent_step).committed_transition is not None
    )
    child_request = _child_request(
        context,
        parent_step,
        parent_request,
        "hybrid-replay-totality:malformed-parent:child",
    )
    proxy = _ParentViewFaultStore(
        context.store,
        parent_request.transition_id,
        "malformed",
    )
    capability = _capability_for_proxy(context, proxy)
    session = open_hybrid_replay_authority_session_v2(capability, child_request)

    attempt = advance_hybrid_replay_state_v2(
        child_request,
        source=_source_for(child_request),
        authority_session=session,
    )

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.path == "/snapshot/parent_transition_id"


def test_private_continuity_guard_rejects_removed_parent_receipt() -> None:
    """Exercise the pure continuity guard after portable constructor validation."""

    context = _context(scope_ref="scope:hybrid-replay-totality:continuity")
    step = _step()
    parent_request = build_operation_request(
        context,
        step,
        advance_ref="advance:hybrid-replay-totality:continuity:parent",
        current_step=1,
    )
    assert _advance(context, parent_request, step).committed_transition is not None
    child_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(step),
        policy=step.effective_policy,
        adjustment_id="trace:adjustment:hybrid-replay-totality:continuity:child",
    )
    child_request = build_operation_request(
        context,
        child_step,
        advance_ref="advance:hybrid-replay-totality:continuity:child",
        current_step=2,
        parent=parent_request.snapshot,
    )

    original_target = child_request.snapshot.target_ref
    object.__setattr__(child_request.snapshot, "target_ref", "target:substituted")
    immutable_failure = _continuity_failure(
        child_request,
        parent_request.snapshot,
    )
    assert immutable_failure is not None
    assert immutable_failure[1] == "/snapshot"
    object.__setattr__(child_request.snapshot, "target_ref", original_target)

    original_revision = child_request.snapshot.revision
    object.__setattr__(
        child_request.snapshot,
        "revision",
        parent_request.snapshot.revision,
    )
    revision_failure = _continuity_failure(
        child_request,
        parent_request.snapshot,
    )
    assert revision_failure is not None
    assert revision_failure[1] == "/snapshot/revision"
    object.__setattr__(child_request.snapshot, "revision", original_revision)

    child_receipts = child_request.snapshot.replay_receipts
    object.__setattr__(
        child_request.snapshot,
        "replay_receipts",
        tuple(
            receipt
            for receipt in child_receipts
            if receipt["event_id"] != "trace:adjustment:one"
        ),
    )

    failure = _continuity_failure(child_request, parent_request.snapshot)

    assert failure is not None
    assert failure[1] == "/snapshot/replay_receipts"

    session = open_hybrid_replay_authority_session_v2(
        context.capability,
        child_request,
    )
    attempt = advance_hybrid_replay_state_v2(
        child_request,
        source=_source_for(child_request),
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.path == "/snapshot/replay_receipts"
