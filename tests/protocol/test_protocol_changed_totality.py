from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

import pheroos.protocol._validation_collective_rules as collective_rules
import pheroos.protocol._validation_commit_finality_rules as finality_rules
import pheroos.protocol._validation_commit_risk_rules as risk_rules
import pheroos.protocol._validation_commit_rules as commit_rules
import pheroos.protocol._validation_hybrid_rules as hybrid_rules
import pheroos.protocol._validation_primitives as primitives
import pheroos.protocol.authority_manifest_v2 as authority_manifest
import pheroos.protocol.authority_v2 as authority_v2
import pheroos.protocol.commit_wire as commit_wire
import pheroos.protocol.manifest as manifest_codec
import pheroos.protocol.models as protocol_models
import pheroos.protocol.schema_document as schema_document
import pheroos.protocol.schema_validation as schema_validation
import pheroos.protocol.validation as validation
from pheroos.protocol import (
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_SCHEMA_V3,
    CollectiveCommitPolicy,
    DistributedCommitPolicy,
    PheromoneKindProfile,
    RecoveryProtocol,
    ScopedCapabilityManifestV2,
    TargetSpec,
    ValidationDiagnostic,
    load_capability_manifest,
    read_capability_manifest,
    validate_capability_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
SCOPED_EXAMPLE = ROOT / "examples/scoped-output-protocol/capability.json"
COMMIT_EXAMPLE = ROOT / "examples/hybrid-commit-protocol/capability.json"


def _commit_manifest():
    manifest = load_capability_manifest(COMMIT_EXAMPLE)
    assert type(manifest.protocol.collective_commit_policy) is CollectiveCommitPolicy
    return manifest


def _commit_policy() -> CollectiveCommitPolicy:
    policy = _commit_manifest().protocol.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return policy


def _scoped_payload() -> dict[str, object]:
    return json.loads(SCOPED_EXAMPLE.read_text(encoding="utf-8"))


def _codes(diagnostics: list[ValidationDiagnostic]) -> set[str]:
    return {item.code for item in diagnostics}


def _assert_code(
    diagnostics: list[ValidationDiagnostic], code: str, path: str | None = None
) -> None:
    matches = [item for item in diagnostics if item.code == code]
    assert matches, [item.code for item in diagnostics]
    if path is not None:
        assert any(item.path == path for item in matches)


def test_commit_component_type_guards_are_fail_closed() -> None:
    path = "protocol.collective_commit_policy"
    protocol = replace(
        _commit_manifest().protocol,
        collective_commit_policy=object(),  # type: ignore[arg-type]
    )

    _assert_code(
        commit_rules.validate_collective_commit_policy(protocol),
        "commit_policy_type_invalid",
        path,
    )
    _assert_code(
        commit_rules.validate_evidence_qualification_policy(
            object(), path=f"{path}.evidence_qualification"
        ),
        "commit_evidence_policy_type_invalid",
    )
    _assert_code(
        commit_rules.validate_support_lease_policy(
            object(), path=f"{path}.support_lease"
        ),
        "commit_support_policy_type_invalid",
    )
    _assert_code(
        commit_rules.validate_commit_window_policy(
            object(), path=f"{path}.commit_window"
        ),
        "commit_window_policy_type_invalid",
    )
    _assert_code(
        finality_rules.validate_terminal_outcome_policy(
            object(), assurance="evidence_bound", path=f"{path}.terminal_outcome"
        ),
        "commit_terminal_policy_type_invalid",
    )
    _assert_code(
        finality_rules.validate_certificate_policy(
            object(), assurance="evidence_bound", path=f"{path}.certificate"
        ),
        "commit_certificate_policy_type_invalid",
    )
    _assert_code(
        finality_rules.validate_distributed_commit_policy(
            object(), assurance="distributed", path=f"{path}.distributed"
        ),
        "commit_distributed_policy_required",
    )


def test_commit_identity_extensions_and_fallback_diagnostics_are_total() -> None:
    manifest = _commit_manifest()
    base = _commit_policy()
    invalid = replace(
        base,
        policy_version="future",
        model="future",
        assurance="future",
        target=" target:invalid",
        extensions={
            "plain": True,
            "x-critical-finality": True,
        },
        terminal_outcome=replace(
            base.terminal_outcome,
            safe_fallback_candidate="candidate:missing",
        ),
    )
    protocol = replace(
        manifest.protocol,
        collective_commit_policy=invalid,
        evidence_policy=replace(
            manifest.protocol.evidence_policy,
            require_provenance=False,
        ),
    )

    diagnostics = commit_rules.validate_collective_commit_policy(protocol)
    expected = {
        "commit_policy_version_unsupported",
        "commit_model_unsupported",
        "commit_assurance_unsupported",
        "commit_target_invalid",
        "commit_extension_namespace_invalid",
        "commit_unknown_critical_extension",
        "commit_target_missing",
        "commit_target_mismatch",
        "commit_fallback_quorum_mismatch",
        "commit_fallback_collective_mismatch",
        "commit_fallback_missing",
        "commit_manifest_provenance_required",
    }
    assert expected <= _codes(diagnostics)

    _assert_code(
        commit_rules.validate_commit_extensions(
            object(), path="protocol.collective_commit_policy.extensions"
        ),
        "commit_extensions_type_invalid",
    )


def test_commit_fallback_safety_binding_reports_declared_unsafe_candidate() -> None:
    manifest = _commit_manifest()
    base = _commit_policy()
    invalid = replace(
        base,
        terminal_outcome=replace(
            base.terminal_outcome,
            safe_fallback_candidate="candidate:alpha",
        ),
    )

    diagnostics = commit_rules.validate_collective_commit_policy(
        replace(manifest.protocol, collective_commit_policy=invalid)
    )

    assert {
        "commit_fallback_quorum_mismatch",
        "commit_fallback_collective_mismatch",
        "commit_fallback_not_safe",
    } <= _codes(diagnostics)

    noncanonical_terminal = replace(base, terminal_outcome=object())  # type: ignore[arg-type]
    assert (
        commit_rules._validate_commit_fallback_binding(
            manifest.protocol,
            noncanonical_terminal,
            "protocol.collective_commit_policy",
        )
        == []
    )


def test_evidence_support_and_window_boundaries_report_every_field() -> None:
    base = _commit_policy()
    evidence = replace(
        base.evidence_qualification,
        numeric_scale=7,
        minimum_quality_ppm=-1,
        minimum_relevance_ppm=-1,
        positive_group_cap=0,
        counter_group_cap=0,
        counter_weight_ppm=0,
        minimum_positive_evidence=0,
        maximum_counterevidence=-1,
        maximum_counterevidence_ratio_ppm=-1,
        domain_contribution_floor=0,
        minimum_source_diversity=0,
        required_challenge_categories=["duplicate", "duplicate"],
        observation_ttl_steps=0,
        require_provenance=False,
        require_trace=False,
    )
    evidence_diagnostics = commit_rules.validate_evidence_qualification_policy(
        evidence, path="policy.evidence"
    )
    assert (
        sum(
            item.code == "commit_evidence_numeric_invalid"
            for item in evidence_diagnostics
        )
        == 11
    )
    assert {
        "commit_numeric_scale_invalid",
        "commit_challenge_categories_invalid",
        "commit_evidence_provenance_required",
        "commit_evidence_trace_required",
    } <= _codes(evidence_diagnostics)

    support = replace(
        base.support_lease,
        minimum_support_clusters=0,
        support_ratio_ppm=0,
        lease_ttl_steps=0,
        membership_mode="future",
        switch_mode="future",
        equivocation_mode="future",
        evidence_reference_required=False,
        cluster_verification_required=False,
    )
    support_diagnostics = commit_rules.validate_support_lease_policy(
        support, path="policy.support"
    )
    assert (
        sum(
            item.code == "commit_support_numeric_invalid"
            for item in support_diagnostics
        )
        == 3
    )
    assert (
        sum(
            item.code == "commit_support_semantics_invalid"
            for item in support_diagnostics
        )
        == 3
    )
    assert {
        "commit_support_evidence_reference_required",
        "commit_support_cluster_verification_required",
    } <= _codes(support_diagnostics)

    numeric_window = replace(
        base.commit_window,
        minimum_stability_steps=0,
        deliberation_deadline_steps=0,
        maximum_leader_resets=-1,
        maximum_epoch_restarts=-1,
        run_deadline_steps=0,
        reset_rules=[],
    )
    numeric_diagnostics = commit_rules.validate_commit_window_policy(
        numeric_window, path="policy.window"
    )
    assert (
        sum(
            item.code == "commit_window_numeric_invalid" for item in numeric_diagnostics
        )
        == 5
    )
    _assert_code(numeric_diagnostics, "commit_window_reset_rules_invalid")

    ordered_window = replace(
        base.commit_window,
        minimum_stability_steps=9,
        deliberation_deadline_steps=8,
        run_deadline_steps=7,
    )
    ordered_diagnostics = commit_rules.validate_commit_window_policy(
        ordered_window, path="policy.window"
    )
    assert {
        "commit_window_unreachable",
        "commit_deadline_order_invalid",
    } <= _codes(ordered_diagnostics)


def test_terminal_and_certificate_closed_sets_are_enforced() -> None:
    base = _commit_policy()
    terminal = replace(
        base.terminal_outcome,
        safe_fallback_candidate=" candidate",
        deadline_outcome="future",
        policy_incomplete_outcome="advisory",
        finality_unavailable_outcome="invalid",
        deliverable_outcomes=["evidence_commit", "unsupported"],
        publishable_outcomes=["invalid", "unsupported"],
        executable_outcomes=["blocked", "unsupported"],
    )
    terminal_diagnostics = finality_rules.validate_terminal_outcome_policy(
        terminal,
        assurance="advisory",
        path="policy.terminal",
    )
    expected_terminal = {
        "commit_fallback_invalid",
        "commit_deadline_outcome_invalid",
        "commit_policy_incomplete_outcome_invalid",
        "commit_finality_outcome_invalid",
        "commit_terminal_outcomes_invalid",
        "commit_terminal_totality_incomplete",
        "commit_terminal_publication_unsafe",
        "commit_terminal_execution_unsafe",
        "commit_advisory_authority_invalid",
    }
    assert expected_terminal <= _codes(terminal_diagnostics)

    certificate = replace(
        base.certificate,
        mode="future",
        wire_version="future",
        canonicalization="future",
        hash_algorithm="future",
        issuer_attestation_required=True,
        independent_verification_required=True,
    )
    certificate_diagnostics = finality_rules.validate_certificate_policy(
        certificate,
        assurance="evidence_bound",
        path="policy.certificate",
    )
    assert {
        "commit_certificate_mode_invalid",
        "commit_certificate_assurance_mismatch",
        "commit_wire_version_unsupported",
        "commit_canonical_version_unsupported",
        "commit_hash_algorithm_unsupported",
        "commit_certificate_issuer_requirement_invalid",
        "commit_certificate_verification_requirement_invalid",
    } <= _codes(certificate_diagnostics)


def test_distributed_commit_numeric_and_topology_rules_are_total() -> None:
    base = DistributedCommitPolicy(
        fault_model="future",
        membership_mode="future",
        membership_size=0,
        max_byzantine_faults=-1,
        witness_quorum=0,
        witness_ttl_steps=0,
        minimum_failure_domain_diversity=0,
        epoch_transition_rule=" ",
        conflict_rule="future",
    )
    declaration_diagnostics = finality_rules.validate_distributed_commit_policy(
        base,
        assurance="distributed",
        path="policy.distributed",
    )
    assert {
        "commit_fault_model_invalid",
        "commit_membership_mode_invalid",
        "commit_conflict_rule_invalid",
        "commit_epoch_transition_rule_invalid",
        "commit_distributed_numeric_invalid",
    } <= _codes(declaration_diagnostics)

    topology = replace(
        base,
        fault_model="byzantine_static_v1",
        membership_mode="static_epoch_verified_clusters_v1",
        membership_size=1,
        max_byzantine_faults=1,
        witness_quorum=1,
        witness_ttl_steps=1,
        minimum_failure_domain_diversity=2,
        epoch_transition_rule="prior_quorum_certificate_v1",
        conflict_rule="freeze_v1",
    )
    topology_diagnostics = finality_rules.validate_distributed_commit_policy(
        topology,
        assurance="distributed",
        path="policy.distributed",
    )
    assert {
        "commit_byzantine_membership_invalid",
        "commit_witness_quorum_too_large",
        "commit_quorum_intersection_invalid",
        "commit_failure_domain_diversity_unreachable",
    } <= _codes(topology_diagnostics)

    non_integral = replace(topology, membership_size=True)  # type: ignore[arg-type]
    non_integral_diagnostics = finality_rules.validate_distributed_commit_policy(
        non_integral,
        assurance="distributed",
        path="policy.distributed",
    )
    _assert_code(non_integral_diagnostics, "commit_distributed_numeric_invalid")
    assert (
        finality_rules.validate_distributed_commit_policy(
            None,
            assurance="evidence_bound",
            path="policy.distributed",
        )
        == []
    )
    _assert_code(
        finality_rules.validate_distributed_commit_policy(
            topology,
            assurance="certified",
            path="policy.distributed",
        ),
        "commit_distributed_policy_inactive",
    )


def test_risk_bands_reject_shape_type_numeric_and_action_weakening() -> None:
    base = _commit_policy()
    object.__setattr__(base, "risk_bands", object())
    _assert_code(
        risk_rules.validate_risk_bands(base, path="policy.risk_bands"),
        "commit_risk_band_coverage_invalid",
    )

    base = _commit_policy()
    type_invalid = dict(base.risk_bands)
    type_invalid["LOW"] = object()  # type: ignore[assignment]
    object.__setattr__(base, "risk_bands", type_invalid)
    _assert_code(
        risk_rules.validate_risk_bands(base, path="policy.risk_bands"),
        "commit_risk_band_type_invalid",
    )

    base = _commit_policy()
    low = base.risk_bands["LOW"]
    invalid_low = replace(
        low,
        minimum_positive_evidence=0,
        maximum_counterevidence=-1,
        maximum_counterevidence_ratio_ppm=-1,
        minimum_support_clusters=0,
        minimum_support_ratio_ppm=0,
        minimum_source_diversity=0,
        minimum_margin=0,
        stability_steps=0,
        required_challenge_categories=["duplicate", "duplicate"],
        minimum_assurance="future",
        publishable_outcomes=["unsupported"],
        executable_outcomes=["unsupported"],
    )
    invalid_bands = dict(base.risk_bands)
    invalid_bands["LOW"] = invalid_low
    object.__setattr__(base, "risk_bands", invalid_bands)
    numeric_diagnostics = risk_rules.validate_risk_bands(base, path="policy.risk_bands")
    assert (
        sum(item.code == "commit_risk_numeric_invalid" for item in numeric_diagnostics)
        == 8
    )
    assert {
        "commit_risk_assurance_invalid",
        "commit_risk_challenges_invalid",
        "commit_risk_outcomes_invalid",
        "commit_risk_evidence_weakened",
        "commit_risk_support_weakened",
        "commit_risk_window_weakened",
        "commit_risk_action_ceiling_exceeded",
        "commit_risk_execution_unsafe",
    } <= _codes(numeric_diagnostics)

    base = _commit_policy()
    unreachable = replace(
        base.risk_bands["LOW"],
        stability_steps=base.commit_window.deliberation_deadline_steps + 1,
    )
    bands = dict(base.risk_bands)
    bands["LOW"] = unreachable
    object.__setattr__(base, "risk_bands", bands)
    _assert_code(
        risk_rules.validate_risk_bands(base, path="policy.risk_bands"),
        "commit_risk_window_unreachable",
    )

    base_without_window = _commit_policy()
    object.__setattr__(base_without_window, "commit_window", object())
    assert (
        risk_rules.validate_risk_bands(base_without_window, path="policy.risk_bands")
        == []
    )


@pytest.mark.parametrize(
    ("value", "require_nonempty", "expected"),
    [
        (42, False, False),
        ([], True, False),
        (["one", "one"], False, False),
        (["one", "two"], True, True),
    ],
)
def test_canonical_string_set_closed_shape(
    value: object, require_nonempty: bool, expected: bool
) -> None:
    assert (
        primitives.canonical_string_set(value, require_nonempty=require_nonempty)
        is expected
    )


def test_validation_primitives_cover_kind_and_adjustment_boundaries() -> None:
    policy = _commit_manifest().protocol.collective_decision_policy
    assert policy is not None

    for kind in ("positive", "negative", "cautionary", "alarm", "novelty", "stale"):
        assert primitives.collective_kind_weight(policy, kind) >= 0.0
    negative = replace(policy, pheromone_positive_weight=-1)
    assert primitives.collective_kind_weight(negative, "positive") == 0.0

    assert not primitives.valid_policy_adjustment_bound(object(), (0.0, 1.0), policy)
    assert not primitives.valid_policy_adjustment_bound(
        "pheromone_response_model", [], policy
    )
    assert primitives.valid_policy_adjustment_bound(
        "pheromone_response_model",
        {"allowed_values": ["linear", "threshold"]},
        policy,
    )
    assert not primitives.valid_policy_adjustment_bound(
        "pheromone_positive_weight", "invalid", policy
    )
    assert not primitives.valid_policy_adjustment_bound(
        "pheromone_cautionary_override_threshold",
        (0.0, 5.0),
        replace(policy, pheromone_max_strength=4.0),
    )
    assert primitives.valid_policy_adjustment_bound(
        "pheromone_cautionary_override_threshold",
        (0.0, 3.0),
        replace(policy, pheromone_max_strength=4.0),
    )
    assert not primitives.valid_policy_adjustment_bound(
        "layer_unknown_weight", (0.0, 1.0), policy
    )
    assert not primitives.valid_policy_adjustment_bound(
        "layer_learned_weight", (0.0, 2.0), policy
    )
    malformed_layer_bounds = replace(policy)
    object.__setattr__(
        malformed_layer_bounds,
        "layer_weight_bounds",
        {"learned": object()},
    )
    assert not primitives.valid_policy_adjustment_bound(
        "layer_learned_weight",
        (0.0, 1.0),
        malformed_layer_bounds,
    )
    assert primitives.valid_policy_adjustment_bound(
        "layer_learned_weight", (0.0, 1.0), policy
    )

    assert primitives.normalized_bounds((0, 1)) == (0.0, 1.0)
    assert primitives.normalized_bounds({"min": 0, "max": 1}) == (0.0, 1.0)
    with pytest.raises(ValueError, match="invalid bounds"):
        primitives.normalized_bounds(object())
    assert not primitives.valid_absolute_bounds(object(), 0, 1)
    assert primitives.valid_absolute_bounds((0, 1), 0, 1)
    assert primitives.valid_non_negative_bounds(0, 1)
    assert not primitives.valid_non_negative_bounds(2, 1)
    assert primitives.finite_in_range(0, 0, 1)
    assert not primitives.finite_in_range(0, 0, 1, lower_inclusive=False)


def test_collective_profile_and_fallback_redundant_guards_remain_alarmable() -> None:
    manifest = _commit_manifest()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    profiles = dict(policy.pheromone_kind_profiles)
    profiles["x-acme.invalid"] = object()  # type: ignore[assignment]
    invalid_profile_policy = replace(policy, pheromone_kind_profiles=profiles)

    diagnostics = collective_rules._validate_pheromone_profiles(invalid_profile_policy)
    _assert_code(diagnostics, "collective_pheromone_kind_profile_invalid")

    fallback = next(
        item
        for item in manifest.protocol.candidates
        if item.id == policy.fallback_candidate
    )
    second_target = TargetSpec(id="decision:secondary", description="Secondary")
    mismatched_fallback = replace(fallback, target=second_target.id)
    candidates = [
        mismatched_fallback if item.id == fallback.id else item
        for item in manifest.protocol.candidates
    ]
    mismatched_protocol = replace(
        manifest.protocol,
        targets=[*manifest.protocol.targets, second_target],
        candidates=candidates,
    )
    by_id = {item.id: item for item in candidates}
    fallback_diagnostics = hybrid_rules._validate_collective_fallback(
        mismatched_protocol,
        candidate_ids=frozenset(by_id),
        candidates_by_id=by_id,
        safe_candidates=frozenset(item.id for item in candidates if item.safe_fallback),
    )
    _assert_code(
        fallback_diagnostics,
        "collective_fallback_target_mismatch",
        "protocol.collective_decision_policy.fallback_candidate",
    )

    threshold_profiles = dict(policy.pheromone_kind_profiles)
    threshold_profiles["x-acme.threshold"] = PheromoneKindProfile(
        weight=1.0,
        evaporation_rate=0.1,
        ttl_steps=1,
        response_model="threshold",
        priority=1,
        can_suppress_positive=False,
        scored_subject_types=["candidate"],
    )
    for name in ("x-acme.invalid-threshold-a", "x-acme.invalid-threshold-b"):
        threshold_profiles[name] = PheromoneKindProfile(
            weight=-1.0,
            evaporation_rate=0.1,
            ttl_steps=1,
            response_model="threshold",
            priority=1,
            can_suppress_positive=False,
            scored_subject_types=["candidate"],
        )
    assert hybrid_rules._threshold_weights(
        replace(policy, pheromone_kind_profiles=threshold_profiles)
    )


def test_manifest_declaration_and_recovery_absence_rules_are_explicit() -> None:
    manifest = _commit_manifest()
    empty_protocol = replace(manifest.protocol, targets=[], candidates=[])
    diagnostics = validate_capability_manifest(
        replace(manifest, protocol=empty_protocol)
    )
    assert {"missing_targets", "missing_candidates"} <= _codes(diagnostics)

    recovery = RecoveryProtocol(
        id="recovery:mismatch",
        trigger_targets=[manifest.protocol.targets[0].id],
        allowed_roles=[],
        allowed_tags=[],
        required_tools=[],
        failure_candidate="candidate:safe_fallback",
    )
    foreign_target = TargetSpec(id="decision:foreign", description="Foreign")
    candidates = [
        replace(candidate, target=foreign_target.id)
        if candidate.id == recovery.failure_candidate
        else candidate
        for candidate in manifest.protocol.candidates
    ]
    protocol = replace(
        manifest.protocol,
        targets=[*manifest.protocol.targets, foreign_target],
        candidates=candidates,
        recovery_protocols=[recovery],
    )
    _assert_code(
        validate_capability_manifest(replace(manifest, protocol=protocol)),
        "recovery_failure_candidate_target_mismatch",
        "protocol.recovery_protocols",
    )


def test_authority_read_set_codec_rejects_encoding_and_json_edges() -> None:
    with pytest.raises(authority_v2.AuthorityV2ProtocolError, match="JSON is invalid"):
        authority_v2.loads_governance_authority_read_set_v2("{")
    with pytest.raises(authority_v2.AuthorityV2ProtocolError, match="encode as UTF-8"):
        authority_v2._require_canonical_stream_ref("authority:\ud800")
    with pytest.raises(authority_v2.AuthorityV2ProtocolError, match="BOM"):
        authority_v2.loads_governance_authority_read_set_v2("\ufeff{}")
    with pytest.raises(authority_v2.AuthorityV2ProtocolError, match="keys.*NFC"):
        authority_v2.loads_governance_authority_read_set_v2('{"e\\u0301":"value"}')


class _DuplicateItemsMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        if key == "duplicate":
            return 1
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(("duplicate",))

    def __len__(self) -> int:
        return 1

    def items(self):
        return (("duplicate", 1), ("duplicate", 2))


def test_commit_wire_exact_set_and_duplicate_mapping_guards() -> None:
    assert commit_wire._canonical_exact_value({"beta", "alpha"}, path="$") == (
        True,
        ["alpha", "beta"],
    )
    with pytest.raises(commit_wire.CommitWireError, match="duplicate keys"):
        commit_wire._canonical_mapping(_DuplicateItemsMapping(), path="$")


def test_manifest_parser_and_protocol_thaw_cover_changed_dispatches() -> None:
    policy = _commit_policy()
    distributed_payload = {
        "fault_model": "byzantine_static_v1",
        "membership_mode": "static_epoch_verified_clusters_v1",
        "membership_size": 4,
        "max_byzantine_faults": 1,
        "witness_quorum": 3,
        "witness_ttl_steps": 4,
        "minimum_failure_domain_diversity": 2,
        "epoch_transition_rule": "prior_quorum_certificate_v1",
        "conflict_rule": "freeze_v1",
    }
    parsed = manifest_codec.distributed_commit_policy_from_value(distributed_payload)
    assert type(parsed) is DistributedCommitPolicy
    assert parsed.witness_quorum == 3
    assert manifest_codec.distributed_commit_policy_from_value(None) is None

    assert validation._authority_integer(1)
    assert validation._authority_integer_in_range(1, 0, 1)
    assert validation.canonical_nonblank_text("canonical")
    assert validation.canonical_string_set(["one"])
    assert manifest_codec.strict_object_field({"policy": {}}, "policy") == {}
    with pytest.raises(ValueError, match="must be an object"):
        manifest_codec.strict_object_field({"policy": None}, "policy")
    with pytest.raises(ValueError, match="must be a boolean"):
        manifest_codec.strict_bool_field({"enabled": 1}, "enabled")
    assert protocol_models.thaw_protocol_value({"nested": ("value",)}) == {
        "nested": ["value"]
    }
    assert policy.target == "decision:collective"


def test_schema_validator_exercises_additional_allof_and_contains_bounds() -> None:
    schema = {
        "allOf": [
            {"type": "object", "required": ["known"]},
            "ignored-non-object",
            {"type": "object", "properties": {"known": {"type": "string"}}},
        ],
        "type": "object",
        "properties": {"known": {"type": "string"}},
        "additionalProperties": {"type": "integer"},
    }
    assert (
        schema_validation.validate_json_schema({"known": "yes", "extra": 3}, schema)
        == []
    )
    assert schema_validation.validate_json_schema(
        ["x", "x"],
        {
            "type": "array",
            "contains": {"const": "x"},
            "minContains": 1,
            "maxContains": 1,
        },
    ) == ["$: must contain at most 1 matching items"]


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        (
            lambda protocol: protocol.__setitem__("authority_policy", {}),
            "$.authority_policy",
        ),
        (
            lambda protocol: protocol.__setitem__("output_policy", None),
            "$.output_policy",
        ),
        (
            lambda protocol: protocol.__setitem__("protocol_version", "future"),
            "$.protocol_version",
        ),
    ],
)
def test_scoped_preflight_rejects_inexact_closed_selection(
    mutation: Any, expected_path: str
) -> None:
    protocol = deepcopy(_scoped_payload()["protocol"])
    assert isinstance(protocol, dict)
    mutation(protocol)

    with pytest.raises(schema_document.ProtocolSchemaVersionError) as exc:
        schema_document._preflight_scoped_selection(protocol, path="$")

    assert exc.value.code == "authority_profile_unsupported"
    assert exc.value.path == expected_path


def test_schema_document_wraps_scoped_constructor_and_semantic_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _scoped_payload()
    protocol_payload = payload["protocol"]
    assert isinstance(protocol_payload, dict)

    malformed = deepcopy(payload)
    malformed["protocol"] = []
    with pytest.raises(schema_document.ProtocolSchemaVersionError) as exc:
        read_capability_manifest(malformed, schema_version=CAPABILITY_SCHEMA_V3)
    assert exc.value.path == "$.protocol"

    monkeypatch.setattr(
        schema_document,
        "scoped_protocol_manifest_v2_from_dict",
        lambda _value: (_ for _ in ()).throw(ValueError("constructor alarm")),
    )
    with pytest.raises(
        schema_document.ProtocolSchemaVersionError, match="constructor alarm"
    ):
        schema_document.read_protocol_manifest(
            protocol_payload,
            schema_version=PROTOCOL_SCHEMA_V3,
        )

    scoped = authority_manifest.scoped_protocol_manifest_v2_from_dict(protocol_payload)
    monkeypatch.setattr(
        schema_document,
        "_scoped_protocol_semantic_diagnostics",
        lambda _protocol: [
            ValidationDiagnostic(
                code="semantic_alarm",
                message="semantic alarm",
                path="protocol",
            )
        ],
    )
    with pytest.raises(ValueError, match="semantic_alarm@protocol"):
        schema_document._require_scoped_semantics(scoped)


def test_validation_facade_dispatch_and_wrappers_are_all_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsupported = validation.validate_capability_manifest(object())  # type: ignore[arg-type]
    _assert_code(unsupported, "capability_manifest_type_unsupported", "$")

    scoped = read_capability_manifest(
        _scoped_payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(scoped) is ScopedCapabilityManifestV2
    monkeypatch.setattr(
        validation,
        "scoped_capability_manifest_v2_from_dict",
        lambda _payload: (_ for _ in ()).throw(ValueError("round-trip alarm")),
    )
    _assert_code(
        validation._validate_scoped_capability_manifest_v2(scoped),
        "scoped_capability_manifest_invalid",
        "$",
    )

    policy = _commit_policy()
    assert validation.validate_commit_extensions({}, path="policy") == []
    assert (
        validation.validate_evidence_qualification_policy(
            policy.evidence_qualification, path="policy.evidence"
        )
        == []
    )
    assert (
        validation.validate_support_lease_policy(
            policy.support_lease, path="policy.support"
        )
        == []
    )
    assert (
        validation.validate_commit_window_policy(
            policy.commit_window, path="policy.window"
        )
        == []
    )
    assert (
        validation.validate_terminal_outcome_policy(
            policy.terminal_outcome,
            assurance=policy.assurance,
            path="policy.terminal",
        )
        == []
    )
    assert (
        validation.validate_certificate_policy(
            policy.certificate,
            assurance=policy.assurance,
            path="policy.certificate",
        )
        == []
    )
    assert (
        validation.validate_distributed_commit_policy(
            None,
            assurance=policy.assurance,
            path="policy.distributed",
        )
        == []
    )
    assert validation.validate_risk_bands(policy, path="policy.risk") == []

    assert validation.authority_integer(1)
    assert validation.authority_integer_in_range(1, 0, 1)
    assert validation.duplicate_values(["x", "x"]) == ["x"]
    collective = _commit_manifest().protocol.collective_decision_policy
    assert collective is not None
    assert validation.collective_kind_weight(collective, "positive") == 1.0
    assert validation.valid_policy_adjustment_bound(
        "pheromone_positive_weight", (0, 1), collective
    )
    assert validation.normalized_bounds((0, 1)) == (0.0, 1.0)
    assert validation.valid_absolute_bounds((0, 1), 0, 1)
    assert validation.valid_non_negative_bounds(0, 1)
    assert validation.finite_number(1)
    assert validation.finite_non_negative(0)
    assert validation.finite_in_range(1, 0, 1)
    assert validation.positive_integer(1)
    assert validation.non_negative_integer(0)
    assert validation.error("alarm", "message", "path").code == "alarm"
    assert validation.validate_ok(_commit_manifest())


def test_abstract_scoped_declaration_body_is_an_inert_protocol_contract() -> None:
    assert authority_manifest._CanonicalDeclarationV2.to_dict(object()) is None
