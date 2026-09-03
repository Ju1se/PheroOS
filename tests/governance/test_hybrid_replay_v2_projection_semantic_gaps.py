from __future__ import annotations

from dataclasses import dataclass, replace
import json
from types import MappingProxyType
from typing import Any, Callable

import pytest

from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._authority_store_v2_contracts.foundation import _compute_root
from pheroos.governance._hybrid_replay_v2.contracts import HybridReplaySnapshotV2
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
    project_collective_policy_v2,
    project_topology_v2,
    restore_hybrid_replay_inputs_v2,
    verify_hybrid_replay_request_source_v2,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _issue_verified_hybrid_source_step_v2,
)
from pheroos.governance._pheromone.records import PheromoneNeighborhood
from pheroos.governance._swarm.records import HybridCollectiveStep
from pheroos.governance.errors import GovernanceError
from pheroos.governance.policy_adjustment import RunScopedPolicyOverlay
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
)
from tests.governance.test_hybrid_replay_v2_projection import (
    DOMAIN_ROOT,
    _fixture,
    _request,
    _source,
    _step,
    _with_snapshot_mutation,
)


def _build(step: HybridCollectiveStep, *, advance_ref: str) -> object:
    return build_hybrid_replay_advance_request_v2(
        domain_root=DOMAIN_ROOT,
        scope_ref="scope:test",
        run_ref="run:test",
        observed_epoch=3,
        advance_ref=advance_ref,
        source=_source(step, current_step=1),
    )


def _replace_receipt_fingerprint(
    step: HybridCollectiveStep,
    field: str,
    mutate: Callable[[list[object]], None],
) -> str:
    receipts = dict(getattr(step, field))
    event_id, fingerprint = next(iter(receipts.items()))
    values = list(fingerprint)
    mutate(values)
    receipts[event_id] = tuple(values)
    object.__setattr__(step, field, MappingProxyType(receipts))
    return event_id


def _replace_diffusion_causal_payload(
    step: HybridCollectiveStep,
    mutate: Callable[[dict[str, Any]], None],
) -> str:
    receipts = dict(step.diffusion_replay_receipts)
    event_id, fingerprint = next(iter(receipts.items()))
    envelope = json.loads(fingerprint[1])
    mutate(envelope)
    canonical = json.dumps(
        envelope,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    receipts[event_id] = ("diffusion-v1", canonical)
    object.__setattr__(step, "diffusion_replay_receipts", MappingProxyType(receipts))
    return event_id


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda policy: object.__setattr__(
                policy, "pheromone_positive_weight", "not-a-number"
            ),
            "finite protocol number",
        ),
        (
            lambda policy: object.__setattr__(policy, "extensions", {"x-feature": 1}),
            "extension semantics",
        ),
        (
            lambda policy: object.__setattr__(
                policy,
                "pheromone_kind_profiles",
                MappingProxyType({"": PheromoneKindProfile()}),
            ),
            "kind must be non-empty",
        ),
        (
            lambda policy: object.__setattr__(
                policy,
                "pheromone_kind_profiles",
                MappingProxyType({"positive": object()}),
            ),
            "exact PheromoneKindProfile",
        ),
        (
            lambda policy: object.__setattr__(
                policy,
                "pheromone_kind_profiles",
                MappingProxyType(
                    {"positive": PheromoneKindProfile(extensions={"x": True})}
                ),
            ),
            "kind-profile extension",
        ),
        (
            lambda policy: object.__setattr__(
                policy, "layer_weight_bounds", MappingProxyType({})
            ),
            "declare every layer",
        ),
        (
            lambda policy: object.__setattr__(
                policy,
                "layer_weight_bounds",
                MappingProxyType(
                    {
                        "evolutionary": (0.0,),
                        "learned": (0.0, 1.0),
                        "metacognitive": (0.0, 1.0),
                        "reactive": (0.0, 1.0),
                    }
                ),
            ),
            "exact pair",
        ),
    ),
)
def test_policy_projection_rejects_semantically_unrepresentable_models(
    mutate: Callable[[CollectiveDecisionPolicy], None],
    message: str,
) -> None:
    _, policy, _, _ = _fixture()
    mutate(policy)
    with pytest.raises((GovernanceError, TypeError), match=message):
        project_collective_policy_v2(policy)


def test_policy_projection_rejects_wrong_model_and_invalid_adjustment_bounds() -> None:
    with pytest.raises(TypeError, match="exact CollectiveDecisionPolicy"):
        project_collective_policy_v2(object())  # type: ignore[arg-type]

    _, base, _, _ = _fixture()
    invalid_bounds: tuple[dict[object, object], str, type[Exception]] = (
        ({1: (0.0, 1.0)}, "field must be text", TypeError),
        ({"x": 1.0}, "unsupported shape", TypeError),
        ({"x": {"allowed_values": "linear"}}, "exact array", TypeError),
        ({"x": {"unexpected": []}}, "unknown fields", ValueError),
    )
    for bounds, message, error in invalid_bounds:
        policy = replace(base, policy_adjustment_bounds=bounds)  # type: ignore[arg-type]
        with pytest.raises(error, match=message):
            project_collective_policy_v2(policy)


def test_policy_projection_accepts_mapping_ranges_and_text_adjustments() -> None:
    _, base, _, _ = _fixture()
    ranged = replace(
        base,
        policy_adjustment_bounds={
            **dict(base.policy_adjustment_bounds),
            "pheromone_negative_weight": {"min": 0.1, "max": 1.5},
        },
    )
    projected = project_collective_policy_v2(ranged)
    selected = next(
        item
        for item in projected["policy_adjustment_bounds"]  # type: ignore[union-attr]
        if item["field_ref"] == "pheromone_negative_weight"
    )
    assert selected["bound_kind"] == "binary64_range"

    step = _step(
        adjustment_field="pheromone_response_model",
        adjustment_value="saturating",
    )
    request = _build(step, advance_ref="advance:text-adjustment")
    assert request.snapshot.overlay["values"][0]["value_kind"] == "text"  # type: ignore[union-attr]
    restored = restore_hybrid_replay_inputs_v2(request.snapshot)  # type: ignore[union-attr]
    assert dict(restored.replay_state.adjustment_replay_receipts)


def test_topology_projection_requires_exact_neighborhood() -> None:
    with pytest.raises(TypeError, match="exact PheromoneNeighborhood"):
        project_topology_v2(object())  # type: ignore[arg-type]
    assert project_topology_v2(PheromoneNeighborhood()) == {
        "subjects": [],
        "edges": [],
    }


@pytest.mark.parametrize(
    ("field", "mutate", "message"),
    (
        (
            "deposit_replay_receipts",
            lambda values: values.__setitem__(2, 1),
            "exact binary64",
        ),
        (
            "deposit_replay_receipts",
            lambda values: values.__setitem__(13, "trace:other"),
            "event id is mismatched",
        ),
        (
            "deposit_replay_receipts",
            lambda values: values.__setitem__(17, ["not-a-tuple"]),
            "exact text tuple",
        ),
        (
            "deposit_replay_receipts",
            lambda values: values.__setitem__(17, ()),
            "did not decode exactly",
        ),
        (
            "feedback_replay_receipts",
            lambda values: values.__setitem__(1, 1),
            "text field has invalid type",
        ),
        (
            "feedback_replay_receipts",
            lambda values: values.__setitem__(12, True),
            "step must be an exact integer",
        ),
        (
            "feedback_replay_receipts",
            lambda values: values.__setitem__(11, "trace:other"),
            "event id is mismatched",
        ),
        (
            "adjustment_replay_receipts",
            lambda values: values.__setitem__(1, 1),
            "text field has invalid type",
        ),
        (
            "adjustment_replay_receipts",
            lambda values: values.__setitem__(3, []),
            "values must be an exact tuple",
        ),
        (
            "adjustment_replay_receipts",
            lambda values: values.__setitem__(
                3,
                (
                    ("pheromone_positive_weight", 1.2),
                    ("pheromone_positive_weight", 1.3),
                ),
            ),
            "not canonical",
        ),
        (
            "adjustment_replay_receipts",
            lambda values: values.__setitem__(5, "trace:other"),
            "event id is mismatched",
        ),
        (
            "adjustment_replay_receipts",
            lambda values: values.__setitem__(3, (("pheromone_response_model", 1.0),)),
            "text adjustment must be exact text",
        ),
    ),
)
def test_public_request_build_rejects_malformed_replay_fingerprints(
    field: str,
    mutate: Callable[[list[object]], None],
    message: str,
) -> None:
    step = _step()
    _replace_receipt_fingerprint(step, field, mutate)
    with pytest.raises((TypeError, ValueError), match=message):
        _build(step, advance_ref=f"advance:bad:{field}:{message}")


def test_public_request_build_rejects_non_tuple_fingerprint_and_empty_event_id() -> (
    None
):
    step = _step()
    receipts = dict(step.deposit_replay_receipts)
    event_id, fingerprint = next(iter(receipts.items()))
    receipts[event_id] = list(fingerprint)  # type: ignore[assignment]
    object.__setattr__(step, "deposit_replay_receipts", MappingProxyType(receipts))
    with pytest.raises(TypeError, match="fingerprint must be an exact tuple"):
        _build(step, advance_ref="advance:fingerprint-not-tuple")

    step = _step()
    receipts = dict(step.deposit_replay_receipts)
    _, fingerprint = next(iter(receipts.items()))
    receipts[""] = fingerprint
    object.__setattr__(step, "deposit_replay_receipts", MappingProxyType(receipts))
    object.__setattr__(
        step,
        "processed_pheromone_event_ids",
        frozenset((*step.processed_pheromone_event_ids, "")),
    )
    with pytest.raises(TypeError, match="event id must be non-empty"):
        _build(step, advance_ref="advance:empty-event-id")


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda envelope: envelope.clear(), "fields are invalid"),
        (
            lambda envelope: envelope.__setitem__("version", "unsupported"),
            "version is unsupported",
        ),
        (
            lambda envelope: envelope["payload"].__setitem__("lifecycle", "deposit"),
            "lifecycle is invalid",
        ),
        (
            lambda envelope: envelope["payload"]["input"]["source_trail"].__setitem__(
                "lineage_event_ids", "not-an-array"
            ),
            "source lineage is malformed",
        ),
        (
            lambda envelope: envelope["payload"]["input"].__setitem__(
                "derived_trace_event_id", "trace:other"
            ),
            "event id is mismatched",
        ),
    ),
)
def test_public_request_build_rejects_malformed_diffusion_causality(
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    step = _step()
    _replace_diffusion_causal_payload(step, mutate)
    with pytest.raises((TypeError, ValueError), match=message):
        _build(step, advance_ref=f"advance:diffusion:{message}")


def test_public_request_build_rejects_invalid_and_noncanonical_diffusion_json() -> None:
    for canonical, message in (
        ("[", "not valid JSON"),
        ("[]", "must be an exact JSON object"),
    ):
        step = _step()
        receipts = dict(step.diffusion_replay_receipts)
        event_id = next(iter(receipts))
        receipts[event_id] = ("diffusion-v1", canonical)
        object.__setattr__(
            step, "diffusion_replay_receipts", MappingProxyType(receipts)
        )
        with pytest.raises((TypeError, ValueError), match=message):
            _build(step, advance_ref=f"advance:diffusion:{message}")

    step = _step()
    receipts = dict(step.diffusion_replay_receipts)
    event_id, fingerprint = next(iter(receipts.items()))
    receipts[event_id] = ("diffusion-v1", fingerprint[1] + " ")
    object.__setattr__(step, "diffusion_replay_receipts", MappingProxyType(receipts))
    with pytest.raises(ValueError, match="not canonical"):
        _build(step, advance_ref="advance:diffusion:noncanonical")

    step = _step()
    receipts = dict(step.diffusion_replay_receipts)
    event_id = next(iter(receipts))
    receipts[event_id] = ("diffusion-v1", 1)  # type: ignore[assignment]
    object.__setattr__(step, "diffusion_replay_receipts", MappingProxyType(receipts))
    with pytest.raises(TypeError, match="canonical JSON text"):
        _build(step, advance_ref="advance:diffusion:not-text")


@dataclass(frozen=True)
class _TraceLookalike:
    event_type: str
    protocol_id: str
    target: str
    reason: str
    lineage: dict[str, Any]


def test_public_request_build_rejects_missing_budget_and_non_trace_sources() -> None:
    step = _step()
    object.__setattr__(step, "budget_state", None)
    with pytest.raises(GovernanceError, match="exact budget state"):
        _build(step, advance_ref="advance:no-budget")

    step = _step()
    event = next(item for item in step.trace_events if item.event_type == "explore")
    lookalike = _TraceLookalike(
        event.event_type,
        event.protocol_id,
        event.target,
        event.reason,
        dict(event.lineage),
    )
    object.__setattr__(
        step,
        "trace_events",
        tuple(lookalike if item is event else item for item in step.trace_events),
    )
    with pytest.raises(TypeError, match="exact TraceEvent"):
        _build(step, advance_ref="advance:trace-lookalike")

    step = _step()
    event = step.trace_events[0]
    object.__setattr__(
        step,
        "active_trails",
        (
            _TraceLookalike(
                event.event_type,
                event.protocol_id,
                event.target,
                event.reason,
                dict(event.lineage),
            ),
        ),
    )
    with pytest.raises(TypeError, match="trail must be exact PheromoneTrail"):
        _build(step, advance_ref="advance:trail-lookalike")


def test_public_request_build_rejects_unrooted_and_ambiguous_overlay_lineage() -> None:
    step = _step()
    overlay = RunScopedPolicyOverlay(
        dict(step.adjustment_overlay),
        source_ids=step.adjustment_overlay.source_ids,
        trace_event_ids=(*step.adjustment_overlay.trace_event_ids, "trace:missing"),
    )
    object.__setattr__(step, "adjustment_overlay", overlay)
    with pytest.raises(GovernanceError, match="no exact source trace root"):
        _build(step, advance_ref="advance:overlay:unrooted")

    step = _step()
    adjustment = next(
        item for item in step.trace_events if item.event_type == "policy_adjustment"
    )
    object.__setattr__(step, "trace_events", (*step.trace_events, adjustment))
    with pytest.raises(GovernanceError, match="trace id is ambiguous"):
        _build(step, advance_ref="advance:overlay:ambiguous")


def _issue_source(
    *,
    step: HybridCollectiveStep,
    manifest: ScopedProtocolManifestV2,
    topology: PheromoneNeighborhood,
    parent: HybridReplaySnapshotV2 | None = None,
    candidate_root: str | None = None,
    policy_root: str | None = None,
    topology_root: str | None = None,
    input_projection: dict[str, object] | None = None,
) -> VerifiedHybridSourceStepV2:
    policy = manifest.collective_decision_policy
    assert policy is not None
    candidates = {
        "candidates": [
            {
                "candidate_ref": item.id,
                "target_ref": item.target,
                "safe_fallback": item.safe_fallback,
            }
            for item in manifest.candidates
            if item.target == manifest.quorum_policy.target
        ],
        "fallback_candidate_ref": manifest.quorum_policy.fallback_candidate,
    }
    projected_policy = project_collective_policy_v2(policy)
    projected_topology = project_topology_v2(topology)
    input_value = input_projection or projected_policy
    return _issue_verified_hybrid_source_step_v2(
        domain_root=DOMAIN_ROOT,
        scope_ref="scope:test",
        run_ref="run:test",
        observed_epoch=3,
        step=step,
        manifest=manifest,
        topology=topology,
        input_policy_projection=input_value,
        candidate_projection_root=(
            candidate_root
            or _compute_root("hybrid-replay-candidate-projection", candidates)
        ),
        base_policy_projection_root=(
            policy_root
            or _compute_root("hybrid-replay-policy-projection", projected_policy)
        ),
        topology_projection_root=(
            topology_root
            or _compute_root("hybrid-replay-topology-projection", projected_topology)
        ),
        parent_snapshot=parent,
        current_step=1 if parent is None else parent.current_step + 1,
    )


def test_public_request_build_rejects_non_hybrid_and_cross_fallback_manifests() -> None:
    manifest, _, _, neighborhood = _fixture()
    payload = manifest.to_dict()
    payload["collective_decision_policy"]["mode"] = "quorum"  # type: ignore[index]
    non_hybrid = scoped_protocol_manifest_v2_from_dict(payload)
    source = _issue_source(
        step=_step(),
        manifest=non_hybrid,
        topology=neighborhood,
    )
    with pytest.raises(GovernanceError, match="no Hybrid policy"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:non-hybrid",
            source=source,
        )

    payload = manifest.to_dict()
    payload["candidates"][0]["safe_fallback"] = True  # type: ignore[index]
    payload["collective_decision_policy"]["fallback_candidate"] = payload[  # type: ignore[index]
        "candidates"
    ][0]["id"]
    cross_fallback = scoped_protocol_manifest_v2_from_dict(payload)
    source = _issue_source(
        step=_step(),
        manifest=cross_fallback,
        topology=neighborhood,
    )
    with pytest.raises(GovernanceError, match="fallbacks are mismatched"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:cross-fallback",
            source=source,
        )


@pytest.mark.parametrize(
    "root_name",
    ("candidate_root", "policy_root"),
)
def test_public_request_build_rejects_substituted_source_projection_roots(
    root_name: str,
) -> None:
    manifest, _, _, neighborhood = _fixture()
    kwargs = {root_name: "sha256:" + "f" * 64}
    source = _issue_source(
        step=_step(),
        manifest=manifest,
        topology=neighborhood,
        **kwargs,
    )
    with pytest.raises(GovernanceError, match="root changed"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref=f"advance:root:{root_name}",
            source=source,
        )


def test_public_request_build_rejects_substituted_input_policy() -> None:
    manifest, policy, _, neighborhood = _fixture()
    projected = project_collective_policy_v2(policy)
    projected["pheromone_positive_weight"] = float(1.75).hex()
    source = _issue_source(
        step=_step(),
        manifest=manifest,
        topology=neighborhood,
        input_projection=projected,
    )
    with pytest.raises(GovernanceError, match="input policy is mismatched"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:input-policy",
            source=source,
        )


def test_parent_binding_and_receipt_extension_fail_closed() -> None:
    first_step = _step()
    first = _request(first_step, advance_ref="advance:one", current_step=1)
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_id="trace:adjustment:second",
    )

    crossed_step = _step()
    crossed = build_hybrid_replay_advance_request_v2(
        domain_root=DOMAIN_ROOT,
        scope_ref="scope:test",
        run_ref="run:other",
        observed_epoch=3,
        advance_ref="advance:crossed-parent",
        source=_source(
            crossed_step,
            current_step=1,
            run_ref="run:other",
        ),
    ).snapshot
    with pytest.raises(GovernanceError, match="parent run_ref is cross-bound"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:cross-parent",
            source=_source(second_step, current_step=2, parent=crossed),
        )

    same_step = _with_snapshot_mutation(
        first,
        lambda snapshot: snapshot.__setitem__("current_step", 2),
    ).snapshot
    with pytest.raises(GovernanceError, match="current_step must advance"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:same-step",
            source=_source(second_step, current_step=2, parent=same_step),
        )

    changed_projection = _with_snapshot_mutation(
        first,
        lambda snapshot: snapshot["candidate_projection"]["candidates"][0].__setitem__(
            "safe_fallback",
            True,
        ),
    ).snapshot
    with pytest.raises(GovernanceError, match="candidate projection changed"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:projection-parent",
            source=_source(second_step, current_step=2, parent=changed_projection),
        )

    missing_receipt_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_id="trace:adjustment:missing-receipt",
    )
    historical_id = next(iter(first_step.deposit_replay_receipts))
    receipts = dict(missing_receipt_step.deposit_replay_receipts)
    receipts.pop(historical_id, None)
    object.__setattr__(
        missing_receipt_step,
        "deposit_replay_receipts",
        MappingProxyType(receipts),
    )
    object.__setattr__(
        missing_receipt_step,
        "processed_pheromone_event_ids",
        frozenset(
            item
            for item in missing_receipt_step.processed_pheromone_event_ids
            if item != historical_id
        ),
    )
    with pytest.raises(GovernanceError, match="historical receipt"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:deleted-receipt",
            source=_source(
                missing_receipt_step,
                current_step=2,
                parent=first.snapshot,
            ),
        )


def test_source_verification_rejects_wrong_request_and_committed_parent() -> None:
    step = _step()
    request = _request(step, advance_ref="advance:verify", current_step=1)
    with pytest.raises(TypeError, match="exact advance request"):
        verify_hybrid_replay_request_source_v2(
            object(),  # type: ignore[arg-type]
            source=_source(step, current_step=1),
            committed_parent_snapshot=None,
        )

    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(step),
        policy=step.effective_policy,
        adjustment_id="trace:adjustment:verify-second",
    )
    source = _source(second_step, current_step=2, parent=request.snapshot)
    with pytest.raises(GovernanceError, match="committed parent"):
        verify_hybrid_replay_request_source_v2(
            request,
            source=source,
            committed_parent_snapshot=None,
        )


def test_restore_requires_exact_snapshot() -> None:
    with pytest.raises(TypeError, match="exact snapshot"):
        restore_hybrid_replay_inputs_v2(object())  # type: ignore[arg-type]
