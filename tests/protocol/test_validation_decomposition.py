from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import inspect
import json

from pheroos.protocol import (
    CapabilityManifest,
    EvidencePolicy,
    OutputPolicy,
    PheromoneKindProfile,
    QuorumPolicy,
    RecoveryProtocol,
    SignalSpec,
    TracePolicy,
    load_capability_manifest,
)
from pheroos.protocol.validation import (
    _validate_capability_manifest_v1,
    canonical_nonblank_text,
)
import pheroos.protocol.validation as validation


def _cross_rule_invalid_manifest() -> CapabilityManifest:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    assert policy is not None
    invalid_policy = replace(
        policy,
        mode="unsupported",
        min_independent_scouts=0,
        quorum_threshold=True,
        pheromone_evaporation_rate=2,
        pheromone_decay_model="adaptive",
        pheromone_min_strength=5,
        pheromone_max_strength=1,
        pheromone_positive_weight=-1,
        pheromone_negative_weight=-1,
        pheromone_cautionary_weight=-1,
        pheromone_novelty_weight=-1,
        pheromone_cautionary_override_threshold=-1,
        pheromone_per_source_cap=-1,
        pheromone_per_round_deposit_cap=-1,
        pheromone_min_source_diversity=0,
        pheromone_require_provenance=False,
        pheromone_require_trace=False,
        pheromone_scored_subject_types=("unsupported",),
        pheromone_kind_profiles={
            "stale": PheromoneKindProfile(
                weight=1,
                scored_subject_types=["candidate"],
            ),
            "x-bad": PheromoneKindProfile(
                weight=-1,
                evaporation_rate=2,
                ttl_steps=-1,
                response_model="adaptive",
                priority=-1,
                can_suppress_positive="yes",
                scored_subject_types=["unsupported"],
            ),
        },
        pheromone_response_model="adaptive",
        pheromone_activation_threshold=-1,
        pheromone_saturation_threshold=-1,
        pheromone_competition_mode="global",
        pheromone_exploration_floor=2,
        pheromone_diffusion_enabled=False,
        pheromone_diffusion_max_hops=2,
        pheromone_diffusion_attenuation=2,
        pheromone_feedback_enabled=True,
        exploration_floor=-1,
        novelty_decay_rate=2,
        stale_route_reopen_threshold=-1,
        layer_coordination_enabled=True,
        layer_weight_bounds={"learned": (2, 1), "unknown": (0, 1)},
        layer_default_weights={"learned": 3, "unknown": -1},
        layer_confidence_thresholds={"unknown": 2},
        layer_conflict_threshold=2,
        layer_emergency_override_threshold=-1,
        layer_min_provenance=0,
        layer_fallback_on_unresolved_conflict=False,
        policy_adjustment_bounds={
            "pheromone_require_trace": (0, 1),
            "unknown": (0, 1),
            "pheromone_evaporation_rate": (1, 0),
        },
        fallback_candidate="candidate:missing",
    )
    invalid_protocol = replace(
        protocol,
        protocol_version="pheroos.protocol.unsupported",
        targets=(protocol.targets[0], protocol.targets[0]),
        candidates=(
            replace(protocol.candidates[0], target="decision:missing"),
            protocol.candidates[2],
            protocol.candidates[2],
        ),
        quorum_policy=QuorumPolicy(
            target="decision:missing",
            fallback_candidate="candidate:missing",
            commit_threshold=0,
        ),
        signals=(SignalSpec(type="bad", target="decision:missing"),),
        collective_decision_policy=invalid_policy,
        recovery_protocols=(
            RecoveryProtocol(
                id="bad",
                trigger_targets=["decision:missing"],
                failure_candidate="candidate:missing",
            ),
        ),
        output_policy=OutputPolicy(
            writer_may_create_facts=True,
            requires_committed_candidate=False,
            requires_evidence_contract=False,
            requires_stop_resolution=False,
            requires_publication_permission=False,
        ),
        evidence_policy=EvidencePolicy(
            require_provenance=False,
            allow_agent_fact_creation=True,
        ),
        trace_policy=TracePolicy(required_events=[]),
    )
    return replace(
        manifest,
        protocol=invalid_protocol,
        extensions={"x-runtime": {"token": "secret"}},
    )


def test_legacy_validator_owner_and_signature_remain_exact() -> None:
    assert _validate_capability_manifest_v1.__module__ == (
        "pheroos.protocol.validation"
    )


def test_decomposed_commit_validator_owners_and_signatures_remain_exact() -> None:
    signatures = {
        "validate_collective_commit_policy": (
            "(protocol: 'ProtocolManifest') -> 'list[ValidationDiagnostic]'"
        ),
        "validate_commit_extensions": (
            "(extensions: 'object', *, path: 'str') -> 'list[ValidationDiagnostic]'"
        ),
        "validate_evidence_qualification_policy": (
            "(policy: 'object', *, path: 'str') -> 'list[ValidationDiagnostic]'"
        ),
        "validate_support_lease_policy": (
            "(policy: 'object', *, path: 'str') -> 'list[ValidationDiagnostic]'"
        ),
        "validate_commit_window_policy": (
            "(policy: 'object', *, path: 'str') -> 'list[ValidationDiagnostic]'"
        ),
        "validate_terminal_outcome_policy": (
            "(policy: 'object', *, assurance: 'object', path: 'str') "
            "-> 'list[ValidationDiagnostic]'"
        ),
        "validate_certificate_policy": (
            "(policy: 'object', *, assurance: 'object', path: 'str') "
            "-> 'list[ValidationDiagnostic]'"
        ),
        "validate_distributed_commit_policy": (
            "(policy: 'object', *, assurance: 'object', path: 'str') "
            "-> 'list[ValidationDiagnostic]'"
        ),
        "validate_risk_bands": (
            "(policy: 'CollectiveCommitPolicy', *, path: 'str') "
            "-> 'list[ValidationDiagnostic]'"
        ),
    }

    for name, expected_signature in signatures.items():
        validator = getattr(validation, name)
        assert validator.__module__ == "pheroos.protocol.validation"
        assert str(inspect.signature(validator)) == expected_signature


def test_canonical_text_wrapper_retains_unicode_normalization_dependency() -> None:
    assert canonical_nonblank_text("é") is True
    assert canonical_nonblank_text("e\u0301") is False
    assert str(inspect.signature(_validate_capability_manifest_v1)) == (
        "(manifest: 'CapabilityManifest') -> 'list[ValidationDiagnostic]'"
    )


def test_legacy_validator_cross_rule_diagnostic_payload_and_order_snapshot() -> None:
    payload = [
        item.to_dict()
        for item in _validate_capability_manifest_v1(_cross_rule_invalid_manifest())
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert len(payload) == 67
    assert sha256(canonical).hexdigest() == (
        "2d207d4381904dd01d9276dca69268f89a5388abf1f47ea92182e72c67b73d5b"
    )
