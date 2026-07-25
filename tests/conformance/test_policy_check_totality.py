from __future__ import annotations

import json
import ast
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pheroos.conformance.checks import (
    candidate_declaration,
    collective_policy,
    commit_authority_boundary,
    commit_numeric_contract,
    commit_policy_contract,
    domain_neutrality,
    driver_contract,
    driver_lifecycle_boundary,
    kernel_contract,
    kernel_import_boundary,
    layer_coordination_policy,
    output_contract,
    pheromone_behavior,
    pheromone_diffusion,
    pheromone_kind_profile,
    pheromone_policy,
    pheromone_reinforcement,
    pheromone_response_model,
    pheromone_subject_scoring,
    policy_adjustment_bounds,
    principal_attestation_contract,
    public_abi_boundary,
    quorum_policy,
    recovery_policy,
    safe_fallback_collective,
    score_breakdown_contract,
    trace_store_contract,
)
from pheroos.drivers import DriverDescriptor
from pheroos.governance import (
    Candidate,
    CandidateSet,
    LayerCoordinationState,
    PheromoneBatchResult,
    PheromoneDiffusionPolicy,
    PheromoneLifecycleRecord,
    PheromonePolicy,
    PheromoneTrail,
    layer_coordination_policy_from_collective,
    pheromone_policy_from_collective,
)
from pheroos.kernel import DriverExposure, OSPlan, ToolExposure
from pheroos.protocol import (
    DriverSpec,
    PheromoneKindProfile,
    RecoveryProtocol,
    load_capability_manifest,
)
from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.trace import InMemoryTraceStore, TraceRecord


ROOT = Path(__file__).resolve().parents[2]


def _manifest_with_policy(manifest, **updates):
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )


def _load_commit_manifest():
    payload = json.loads(
        (ROOT / "tests/fixtures/commit-integrity/v1/case-01.json").read_text(
            encoding="utf-8"
        )
    )
    return capability_manifest_from_dict(payload["manifest"])


def test_policy_and_authority_checkers_accept_declared_protocols() -> None:
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    commit_case = json.loads(
        (ROOT / "tests/fixtures/commit-integrity/v1/case-01.json").read_text(
            encoding="utf-8"
        )
    )
    commit = capability_manifest_from_dict(commit_case["manifest"])
    e2e = load_capability_manifest(ROOT / "examples/e2e-protocol/capability.json")

    manifest_checks = (
        (candidate_declaration, toy),
        (collective_policy, hybrid),
        (commit_authority_boundary, commit),
        (commit_numeric_contract, commit),
        (commit_policy_contract, commit),
        (driver_contract, e2e),
        (kernel_contract, toy),
        (layer_coordination_policy, hybrid),
        (output_contract, toy),
        (pheromone_behavior, hybrid),
        (pheromone_diffusion, hybrid),
        (pheromone_kind_profile, hybrid),
        (pheromone_policy, hybrid),
        (pheromone_reinforcement, hybrid),
        (pheromone_response_model, hybrid),
        (pheromone_subject_scoring, hybrid),
        (policy_adjustment_bounds, hybrid),
        (principal_attestation_contract, commit),
        (quorum_policy, toy),
        (recovery_policy, toy),
        (safe_fallback_collective, hybrid),
        (score_breakdown_contract, hybrid),
    )

    results = [module.check(manifest) for module, manifest in manifest_checks]
    standalone = (
        driver_lifecycle_boundary.check(),
        kernel_import_boundary.check(ROOT),
        public_abi_boundary.check(ROOT),
        trace_store_contract.check(),
        domain_neutrality.check_public_core(ROOT),
    )

    assert all(result.ok for result in (*results, *standalone)), {
        result.name: result.detail
        for result in (*results, *standalone)
        if not result.ok
    }


def test_manifest_declaration_checkers_report_each_authority_violation() -> None:
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = hybrid.protocol.collective_decision_policy
    assert policy is not None

    first = hybrid.protocol.candidates[0]
    duplicate_manifest = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            targets=(
                hybrid.protocol.targets[0],
                hybrid.protocol.targets[0],
            ),
            candidates=(
                first,
                first,
                replace(first, id="candidate:undeclared-target", target="missing"),
            ),
        ),
    )
    declaration = candidate_declaration.check(duplicate_manifest)
    assert declaration.ok is False
    assert first.id in declaration.detail
    assert hybrid.protocol.targets[0].id in declaration.detail
    assert "candidate:undeclared-target" in declaration.detail
    assert candidate_declaration.duplicate_values([1, 2, 1, 2]) == ["1", "2"]

    invalid_collective = collective_policy.check(
        _manifest_with_policy(
            hybrid,
            mode="unsupported",
            min_independent_scouts=0,
            quorum_threshold=0,
        )
    )
    assert invalid_collective.ok is False
    assert invalid_collective.detail == (
        "unsupported_mode, min_independent_scouts, quorum_threshold"
    )
    assert collective_policy.check(toy).ok is True

    fallback_id = hybrid.protocol.quorum_policy.fallback_candidate
    without_fallback = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            candidates=tuple(
                candidate
                for candidate in hybrid.protocol.candidates
                if candidate.id != fallback_id
            ),
        ),
    )
    assert quorum_policy.check(without_fallback).detail == "fallback_missing"
    unsafe_fallback = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            candidates=tuple(
                replace(candidate, safe_fallback=False)
                if candidate.id == fallback_id
                else candidate
                for candidate in hybrid.protocol.candidates
            ),
        ),
    )
    assert quorum_policy.check(unsafe_fallback).detail == "fallback_not_safe"
    wrong_target_fallback = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            candidates=tuple(
                replace(candidate, target="decision:other")
                if candidate.id == fallback_id
                else candidate
                for candidate in hybrid.protocol.candidates
            ),
        ),
    )
    assert quorum_policy.check(wrong_target_fallback).detail == (
        "fallback_target_mismatch"
    )
    assert safe_fallback_collective.check(without_fallback).ok is False
    assert safe_fallback_collective.check(toy).ok is True

    failure = hybrid.protocol.candidates[0]
    recovery_manifest = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            recovery_protocols=(
                RecoveryProtocol(
                    "recovery:missing",
                    ["decision:missing"],
                    failure_candidate="candidate:missing",
                ),
                RecoveryProtocol(
                    "recovery:wrong-target",
                    ["decision:missing"],
                    failure_candidate=failure.id,
                ),
            ),
        ),
    )
    recovery_result = recovery_policy.check(recovery_manifest)
    assert recovery_result.ok is False
    assert "decision:missing" in recovery_result.detail
    assert "candidate:missing" in recovery_result.detail
    assert f"{failure.id}:target" in recovery_result.detail


def test_driver_and_output_policy_checkers_reject_undeclared_authority() -> None:
    e2e = load_capability_manifest(ROOT / "examples/e2e-protocol/capability.json")
    bad_specs = (
        DriverSpec("", "tool", "1", ["invoke"], ["driver:invoke"]),
        DriverSpec("driver:bad", "", "1", ["invoke"], ["driver:invoke"]),
        DriverSpec("driver:bad", "tool", "", ["invoke"], ["driver:invoke"]),
        DriverSpec("driver:bad", "tool", "1", [], []),
    )
    result = driver_contract.check(replace(e2e, drivers=bad_specs))
    assert result.ok is False
    assert "0:identity" in result.detail
    assert "1:identity" in result.detail
    assert "2:identity" in result.detail
    assert "3:capabilities" in result.detail
    assert "3:permissions" in result.detail

    mapping = {
        "id": " driver:mapping ",
        "kind": " tool ",
        "version": " 1 ",
        "capabilities": [" invoke ", "", "  "],
        "permissions": [" driver:invoke "],
    }
    assert driver_contract.driver_id(mapping) == "driver:mapping"
    assert driver_contract.driver_kind(mapping) == "tool"
    assert driver_contract.driver_version(mapping) == "1"
    assert driver_contract.driver_capabilities(mapping) == ["invoke"]
    assert driver_contract.driver_permissions(mapping) == ["driver:invoke"]
    assert driver_contract.text_list("not-a-list") == []

    policy = replace(
        e2e.protocol.output_policy,
        writer_may_create_facts=True,
        requires_committed_candidate=False,
        requires_evidence_contract=False,
        requires_stop_resolution=False,
        requires_publication_permission=False,
    )
    invalid_policy = replace(
        e2e,
        protocol=replace(e2e.protocol, output_policy=policy),
    )
    output_result = output_contract.check(invalid_policy)
    assert output_result.ok is False
    assert output_result.detail == "writer_fact_creation, mandatory_gates"

    no_candidates = replace(
        invalid_policy,
        protocol=replace(invalid_policy.protocol, candidates=()),
    )
    no_candidate_result = output_contract.check(no_candidates)
    assert no_candidate_result.ok is False
    assert no_candidate_result.detail.endswith("active_target_candidates")


def test_pheromone_policy_checker_reports_every_declaration_family() -> None:
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    assert pheromone_policy.check(toy).ok is True

    memory_result = pheromone_policy.check(
        _manifest_with_policy(
            hybrid,
            pheromone_evaporation_rate=2.0,
            pheromone_decay_model="unsupported",
            pheromone_min_strength=2.0,
            pheromone_max_strength=1.0,
            pheromone_positive_weight=-1.0,
            pheromone_negative_weight=-1.0,
            pheromone_cautionary_weight=-1.0,
            pheromone_novelty_weight=-1.0,
            pheromone_cautionary_override_threshold=-1.0,
            pheromone_per_source_cap=-1.0,
            pheromone_per_round_deposit_cap=-1.0,
            pheromone_min_source_diversity=0,
        )
    )
    assert memory_result.ok is False
    assert set(memory_result.detail.split(", ")) >= {
        "evaporation_rate",
        "decay_model",
        "strength_bounds",
        "weights",
        "cautionary_threshold",
        "caps",
        "min_source_diversity",
    }

    response_result = pheromone_policy.check(
        _manifest_with_policy(
            hybrid,
            pheromone_scored_subject_types=("evidence",),
            pheromone_response_model="unsupported",
            pheromone_competition_mode="unsupported",
            pheromone_activation_threshold=-1.0,
            pheromone_saturation_threshold=-1.0,
            pheromone_exploration_floor=-1.0,
            exploration_floor=-1.0,
            stale_route_reopen_threshold=-1.0,
            pheromone_diffusion_max_hops=-1,
            pheromone_diffusion_attenuation=2.0,
            novelty_decay_rate=2.0,
        )
    )
    assert response_result.ok is False
    assert set(response_result.detail.split(", ")) >= {
        "scored_subject_types",
        "response_model",
        "competition_mode",
        "thresholds",
        "diffusion",
        "novelty_decay",
    }

    invalid_profile = PheromoneKindProfile(
        weight=-1.0,
        evaporation_rate=2.0,
        ttl_steps=-1,
        response_model="unsupported",
        scored_subject_types=["evidence"],
    )
    profile_result = pheromone_policy.check(
        _manifest_with_policy(
            hybrid,
            pheromone_kind_profiles={"positive": invalid_profile},
        )
    )
    assert profile_result.ok is False
    assert profile_result.detail.endswith("kind_profiles")

    stale_result = pheromone_policy.check(
        _manifest_with_policy(
            hybrid,
            pheromone_kind_profiles={
                "stale": PheromoneKindProfile(
                    weight=1.0,
                    scored_subject_types=["candidate"],
                )
            },
        )
    )
    assert stale_result.ok is False
    assert stale_result.detail.endswith("stale_profile")


def test_source_boundary_checkers_fail_closed_on_real_source_trees(
    tmp_path: Path,
) -> None:
    missing_import_root = kernel_import_boundary.check(tmp_path)
    assert missing_import_root.ok is False
    assert missing_import_root.detail == "missing:pheroos"

    protocol_root = tmp_path / "pheroos/protocol"
    protocol_root.mkdir(parents=True)
    source = protocol_root / "boundary.py"
    source.write_text(
        "\n".join(
            (
                "import openai",
                "import json",
                "from pheroos import governance",
                "from pheroos._digest import value",
                "from .. import governance",
                "from .... import unresolved",
            )
        ),
        encoding="utf-8",
    )
    import_result = kernel_import_boundary.check(tmp_path)
    assert import_result.ok is False
    assert "pheroos/protocol/boundary.py:openai" in import_result.detail
    assert "pheroos/protocol/boundary.py:pheroos.governance" in import_result.detail
    assert "pheroos._digest" not in import_result.detail

    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    absolute = ast.parse("from pheroos import governance").body[0]
    relative = ast.parse("from . import local").body[0]
    assert isinstance(absolute, ast.ImportFrom)
    assert isinstance(relative, ast.ImportFrom)
    assert kernel_import_boundary.resolved_import_from_modules(
        tmp_path, outside, absolute
    ) == ("pheroos.governance",)
    assert kernel_import_boundary.resolved_import_from_modules(
        tmp_path, outside, relative
    ) == ("",)
    assert kernel_import_boundary.package_for_path(tmp_path, outside) == ""
    assert kernel_import_boundary.source_package_for(tmp_path, outside) == ""

    neutral_root = tmp_path / "neutral"
    neutral_protocol = neutral_root / "pheroos/protocol"
    neutral_protocol.mkdir(parents=True)
    (neutral_protocol / "ignored.txt").write_text(
        domain_neutrality.forbidden_terms()[0],
        encoding="utf-8",
    )
    assert domain_neutrality.check_public_core(neutral_root).ok is True
    offender = neutral_protocol / "offender.py"
    forbidden = domain_neutrality.forbidden_terms()[0]
    offender.write_text(f"value = {forbidden!r}\n", encoding="utf-8")
    neutrality = domain_neutrality.check_public_core(neutral_root)
    assert neutrality.ok is False
    assert f"pheroos/protocol/offender.py:{forbidden}" in neutrality.detail


def test_public_abi_artifacts_report_missing_invalid_and_drifted_state(
    tmp_path: Path,
) -> None:
    assert public_abi_boundary.public_inventory_problems(tmp_path) == [
        "inventory:artifact_missing"
    ]
    assert public_abi_boundary.public_lifecycle_problems(tmp_path) == [
        "lifecycle:artifact_missing"
    ]

    abi = tmp_path / "pheroos/conformance/abi"
    abi.mkdir(parents=True)
    inventory = abi / "public-python-api-v1.json"
    lifecycle = abi / "public-python-api-lifecycle-v1.json"
    inventory.write_text("{", encoding="utf-8")
    lifecycle.write_text("[]", encoding="utf-8")
    assert public_abi_boundary.public_inventory_problems(tmp_path) == [
        "inventory:artifact_invalid:JSONDecodeError"
    ]
    assert public_abi_boundary.public_lifecycle_problems(tmp_path) == [
        "lifecycle:artifact_invalid:ValueError"
    ]

    inventory.write_text("{}", encoding="utf-8")
    lifecycle.write_text("{}", encoding="utf-8")
    inventory_drift = public_abi_boundary.public_inventory_problems(tmp_path)
    lifecycle_drift = public_abi_boundary.public_lifecycle_problems(tmp_path)
    assert inventory_drift
    assert all(problem.startswith("inventory:") for problem in inventory_drift)
    assert lifecycle_drift
    assert all(problem.startswith("lifecycle:") for problem in lifecycle_drift)


class _BrokenTraceStore:
    def __init__(self) -> None:
        self._records: list[TraceRecord] = []

    def append(self, event):
        stored = TraceRecord(sequence=8, event=event)
        self._records.append(stored)
        return TraceRecord(sequence=9, event=event)

    @property
    def records(self):
        return tuple(self._records)


class _TraceAdapter:
    implementation_id = "test-trace-store"
    conformance_version = trace_store_contract.TRACE_STORE_CONFORMANCE_VERSION

    def __init__(self, stores) -> None:
        self._stores = iter(stores)

    def create_store(self):
        return next(self._stores)


@pytest.mark.parametrize("implementation_id", [1, "", " spaced "])
def test_trace_store_adapter_identity_is_canonical(implementation_id: object) -> None:
    adapter = SimpleNamespace(
        implementation_id=implementation_id,
        conformance_version=trace_store_contract.TRACE_STORE_CONFORMANCE_VERSION,
        create_store=InMemoryTraceStore,
    )
    result = trace_store_contract.run_trace_store_conformance(adapter)
    assert result.ok is False
    assert result.detail == "adapter_implementation_id"


def test_trace_store_conformance_reports_external_backend_contract_failures() -> None:
    protocol_failure = trace_store_contract.run_trace_store_conformance(object())
    assert protocol_failure.detail == "adapter_protocol"

    bad_version = SimpleNamespace(
        implementation_id="test-trace-store",
        conformance_version="unsupported",
        create_store=InMemoryTraceStore,
    )
    assert trace_store_contract.run_trace_store_conformance(bad_version).detail == (
        "adapter_version"
    )

    non_store = _TraceAdapter([object()])
    assert trace_store_contract.run_trace_store_conformance(non_store).detail == (
        "store_protocol"
    )

    bad_fresh = _TraceAdapter([InMemoryTraceStore(), object()])
    fresh_result = trace_store_contract.run_trace_store_conformance(bad_fresh)
    assert fresh_result.ok is False
    assert fresh_result.detail == "fresh_store_protocol"

    prepopulated = InMemoryTraceStore()
    prepopulated.append(
        trace_store_contract.TraceEvent(
            event_type="x-test.preexisting",
            protocol_id="protocol:test",
            target="decision:test",
            reason="preexisting record",
        )
    )
    isolated = _TraceAdapter([InMemoryTraceStore(), prepopulated])
    isolation_result = trace_store_contract.run_trace_store_conformance(isolated)
    assert isolation_result.ok is False
    assert isolation_result.detail == "fresh_store_isolation"

    broken = _TraceAdapter([_BrokenTraceStore(), _BrokenTraceStore()])
    broken_result = trace_store_contract.run_trace_store_conformance(broken)
    assert broken_result.ok is False
    assert set(broken_result.detail.split(", ")) >= {
        "first_record_binding",
        "first_record_snapshot",
        "input_snapshot_isolation",
        "output_snapshot_isolation",
        "invalid_event_accepted",
        "invalid_event_mutated_store",
        "chronological_sequence",
        "record_order",
    }

    exhausted = _TraceAdapter([])
    exception_result = trace_store_contract.run_trace_store_conformance(exhausted)
    assert exception_result.ok is False
    assert exception_result.detail.startswith("adapter_exception:StopIteration")


def test_kernel_and_driver_self_checks_expose_malformed_public_inputs() -> None:
    plan = OSPlan(
        tenant_id="tenant:test",
        request_id="request:test",
        runtime_ready=False,
        driver_exposures=(
            DriverExposure(
                driver_id="driver:test",
                capability_id="capability:test",
            ),
        ),
        tool_exposures=(
            ToolExposure(
                tool_id="tool:test",
                capability_id="capability:test",
            ),
        ),
    )
    assert kernel_contract.plan_authority_problems(plan) == [
        "plan:not_ready",
        "plan:unpermissioned_driver_exposure",
        "plan:uncapable_driver_exposure",
        "plan:unpermissioned_tool_exposure",
    ]
    assert kernel_contract.raises_kernel_error(lambda: None) is False
    assert driver_lifecycle_boundary.rejects(lambda: None) is False

    descriptor = DriverDescriptor(
        id="driver:test",
        kind="tool",
        version="1",
        capabilities=["invoke"],
    )

    class MutableRegistry:
        descriptors = {"driver:test": descriptor}

        @staticmethod
        def get(_descriptor_id: str) -> DriverDescriptor:
            return DriverDescriptor(
                id="driver:other",
                kind="tool",
                version="1",
            )

    problems: list[str] = []
    driver_lifecycle_boundary._registry_view_problems(
        MutableRegistry(),
        "driver:test",
        problems,
    )
    assert problems == ["registry_mutable_view", "registry_view_alias"]


def test_policy_adjustment_checker_exercises_every_owned_effective_field() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = hybrid.protocol.collective_decision_policy
    assert policy is not None
    bounds = {
        "pheromone_evaporation_rate": (0.0, 1.0),
        "pheromone_positive_weight": (0.0, 10.0),
        "pheromone_negative_weight": (0.0, 10.0),
        "pheromone_cautionary_weight": (0.0, 10.0),
        "pheromone_alarm_weight": (0.0, 10.0),
        "pheromone_novelty_weight": (0.0, 10.0),
        "pheromone_response_model": {
            "allowed_values": [
                "linear",
                "saturating",
                "threshold",
                "competitive",
            ]
        },
        "pheromone_exploration_floor": (0.0, 1.0),
        "pheromone_cautionary_override_threshold": (
            0.0,
            policy.pheromone_max_strength,
        ),
        "layer_emergency_override_threshold": (0.0, 1.0),
        "layer_learned_weight": policy.layer_weight_bounds["learned"],
        "layer_evolutionary_weight": policy.layer_weight_bounds["evolutionary"],
        "layer_metacognitive_weight": policy.layer_weight_bounds["metacognitive"],
    }
    all_bounds = _manifest_with_policy(
        hybrid,
        policy_adjustment_bounds=bounds,
    )
    result = policy_adjustment_bounds.check(all_bounds)
    assert result.ok is True, result.detail

    assert policy_adjustment_bounds.accepted_value_for([1.0, 2.0]) == 1.0
    assert policy_adjustment_bounds.accepted_value_for((1.0, 2.0)) == 1.0
    assert (
        policy_adjustment_bounds.accepted_value_for(
            {"allowed_values": ["linear", "threshold"]}
        )
        == "linear"
    )
    assert policy_adjustment_bounds.accepted_value_for({"min": 0.25}) == 0.25
    assert policy_adjustment_bounds.accepted_value_for(object()) == 0
    assert policy_adjustment_bounds.rejected_value_for([1.0, 2.0]) == 3.0
    assert (
        policy_adjustment_bounds.rejected_value_for({"allowed_values": ["linear"]})
        == "unsupported"
    )
    assert policy_adjustment_bounds.rejected_value_for({"max": 2.0}) == 3.0
    assert type(policy_adjustment_bounds.rejected_value_for(object())) is object

    effective = all_bounds.protocol.collective_decision_policy
    assert effective is not None
    expected_values = {
        "pheromone_evaporation_rate": effective.pheromone_evaporation_rate,
        "pheromone_response_model": effective.pheromone_response_model,
        "pheromone_exploration_floor": effective.pheromone_exploration_floor,
        "pheromone_cautionary_override_threshold": (
            effective.pheromone_cautionary_override_threshold
        ),
        "layer_emergency_override_threshold": (
            effective.layer_emergency_override_threshold
        ),
        "pheromone_positive_weight": effective.pheromone_positive_weight,
        "pheromone_negative_weight": effective.pheromone_negative_weight,
        "pheromone_cautionary_weight": effective.pheromone_cautionary_weight,
        "pheromone_alarm_weight": effective.pheromone_kind_profiles["alarm"].weight,
        "pheromone_novelty_weight": effective.pheromone_novelty_weight,
        "layer_learned_weight": effective.layer_default_weights["learned"],
        "layer_evolutionary_weight": effective.layer_default_weights["evolutionary"],
        "layer_metacognitive_weight": effective.layer_default_weights["metacognitive"],
    }
    normalized_effective = replace(
        effective,
        pheromone_kind_profiles={
            kind: replace(
                profile,
                evaporation_rate=effective.pheromone_evaporation_rate,
                response_model=effective.pheromone_response_model,
                weight=(
                    effective.pheromone_cautionary_weight
                    if kind == "cautionary"
                    else profile.weight
                ),
            )
            for kind, profile in effective.pheromone_kind_profiles.items()
        },
    )
    assert all(
        policy_adjustment_bounds.effective_adjustment_applied(
            normalized_effective,
            key,
            value,
        )
        for key, value in expected_values.items()
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            effective,
            "unsupported",
            0,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            effective,
            "pheromone_evaporation_rate",
            -1.0,
        )
        is False
    )
    without_positive = replace(
        effective,
        pheromone_kind_profiles={
            kind: profile
            for kind, profile in effective.pheromone_kind_profiles.items()
            if kind != "positive"
        },
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            without_positive,
            "pheromone_positive_weight",
            effective.pheromone_positive_weight,
        )
        is False
    )

    undeclared = policy_adjustment_bounds.check(
        _manifest_with_policy(hybrid, policy_adjustment_bounds={})
    )
    assert undeclared.ok is True
    unsafe = policy_adjustment_bounds.check(
        _manifest_with_policy(
            hybrid,
            policy_adjustment_bounds={"fallback_candidate": (0.0, 1.0)},
        )
    )
    assert unsafe.ok is False
    assert "unsafe:fallback_candidate" in unsafe.detail
    assert "bounded_rejected:fallback_candidate" in unsafe.detail

    malformed = policy_adjustment_bounds._bounded_adjustment_problems(
        effective,
        "unsupported",
        object(),
    )
    assert "bounded_rejected:unsupported" in malformed


def test_pheromone_subject_scoring_helpers_cover_active_and_metadata_paths() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)

    problems = pheromone_subject_scoring._subject_score_problems(
        {
            "route": (0.0, True),
            "tool": (1.0, False),
        },
        competitive_singleton=False,
    )
    assert problems == [
        "declared_route_subject_no_score",
        "declared_tool_unexpected_score",
    ]
    assert (
        pheromone_subject_scoring._subject_score_problems(
            {"route": (0.0, True)},
            competitive_singleton=True,
        )
        == []
    )

    assert pheromone_subject_scoring.legacy_kind_weight("positive", policy) == (
        policy.positive_weight
    )
    assert pheromone_subject_scoring.legacy_kind_weight("negative", policy) == (
        policy.negative_weight
    )
    assert pheromone_subject_scoring.legacy_kind_weight("alarm", policy) == (
        policy.cautionary_weight
    )
    assert pheromone_subject_scoring.legacy_kind_weight("novelty", policy) == (
        policy.novelty_weight
    )
    assert pheromone_subject_scoring.legacy_kind_weight("x-test", policy) == 0.0

    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "stale",
            policy.kind_profiles["stale"],
            policy,
        )
        is False
    )
    novelty_disabled = replace(policy, exploration_enabled=False)
    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "novelty",
            novelty_disabled.kind_profiles["novelty"],
            novelty_disabled,
        )
        is False
    )
    zero_strength = replace(policy, max_strength=0.0)
    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "positive",
            zero_strength.kind_profiles["positive"],
            zero_strength,
        )
        is False
    )
    threshold_profile = replace(
        policy.kind_profiles["positive"],
        response_model="threshold",
    )
    high_threshold = replace(policy, activation_threshold=policy.max_strength * 2)
    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "positive",
            threshold_profile,
            high_threshold,
        )
        is False
    )
    saturating_profile = replace(
        policy.kind_profiles["positive"],
        response_model="saturating",
    )
    no_saturation = replace(policy, saturation_threshold=0.0)
    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "positive",
            saturating_profile,
            no_saturation,
        )
        is False
    )
    assert pheromone_subject_scoring.no_score_probe_kind("candidate", policy) != "stale"
    assert pheromone_subject_scoring.fixture_error(Exception()) == (
        "fixture_error:Exception"
    )

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_subject_scoring.check(toy).ok is True
    assert pheromone_subject_scoring.check_hybrid(toy).detail == "collective_policy"
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert pheromone_subject_scoring.check_hybrid(without_candidates).detail == (
        "active_target_candidates"
    )
    malformed = pheromone_subject_scoring.check(
        _manifest_with_policy(
            hybrid,
            pheromone_min_source_diversity="invalid",
        )
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("fixture_error:GovernanceError")


def test_diffusion_checker_diagnoses_record_and_materialization_contracts() -> None:
    missing, should_continue = pheromone_diffusion._diffusion_hop_problems(
        record=None,
        observed=None,
        requested=1.0,
        applied=1.0,
        attenuation=0.5,
        hop=1,
    )
    assert missing == ["diffusion_record_missing:1"]
    assert should_continue is False

    bad_record = SimpleNamespace(
        action="diffuse_applied",
        requested_strength=9.0,
        applied_strength=9.0,
        attenuation=9.0,
    )
    materialized = PheromoneTrail(
        candidate_id="candidate:alpha",
        strength=9.0,
    )
    rejected, should_continue = pheromone_diffusion._diffusion_hop_problems(
        record=bad_record,
        observed=materialized,
        requested=1.0,
        applied=0.0,
        attenuation=0.5,
        hop=2,
    )
    assert set(rejected) == {
        "attenuation:2",
        "budget_application:2",
        "recorded_attenuation:2",
        "rejected_diffusion_materialized:2",
    }
    assert should_continue is False

    absent, should_continue = pheromone_diffusion._diffusion_hop_problems(
        record=bad_record,
        observed=None,
        requested=1.0,
        applied=1.0,
        attenuation=0.5,
        hop=3,
    )
    assert "declared_hop_not_applied:3" in absent
    assert should_continue is False

    wrong_strength, should_continue = pheromone_diffusion._diffusion_hop_problems(
        record=SimpleNamespace(
            action="diffuse_applied",
            requested_strength=1.0,
            applied_strength=1.0,
            attenuation=0.5,
        ),
        observed=materialized,
        requested=1.0,
        applied=1.0,
        attenuation=0.5,
        hop=4,
    )
    assert wrong_strength == ["diffused_strength:4"]
    assert should_continue is True

    derived = replace(
        materialized,
        subject_type="candidate",
        subject_id="candidate:alpha",
        diffusion_hop=1,
    )
    over_hop = SimpleNamespace(hop=1)
    result = PheromoneBatchResult(
        trails=(derived,),
        records=(over_hop,),
    )
    problems = pheromone_diffusion.expected_diffusion_problems(
        result,
        candidate_id="candidate:alpha",
        source_strength=1.0,
        policy=PheromonePolicy(
            min_strength=0.0,
            max_strength=1.0,
            per_source_cap=1.0,
            per_round_deposit_cap=1.0,
        ),
        diffusion_policy=PheromoneDiffusionPolicy(
            enabled=False,
            max_hops=0,
            attenuation=0.0,
        ),
    )
    assert problems == [
        "exceeded_declared_hops:1",
        "record_exceeded_max_hops",
    ]

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_diffusion.check(toy).ok is True
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert pheromone_diffusion.diffusion_problems(without_candidates) == [
        "active_target_candidates"
    ]
    assert pheromone_diffusion.diffusion_problems(
        replace(
            toy,
            protocol=replace(
                toy.protocol,
                collective_decision_policy=None,
            ),
        )
    ) == ["collective_policy"]
    malformed = pheromone_diffusion.check(
        _manifest_with_policy(hybrid, pheromone_max_strength="invalid")
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("exercise:ValueError")


def test_reinforcement_checker_reports_budget_order_and_lineage_failures() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_reinforcement.candidate_set(hybrid)
    target = pheromone_reinforcement.active_target(hybrid)
    candidate_id = pheromone_reinforcement.exercise_candidate_id(hybrid)
    assert candidate_id is not None
    neighborhood = pheromone_reinforcement._feedback_neighborhood(
        candidate_id,
        target,
    )
    feedback = [
        pheromone_reinforcement.item(
            candidate_id,
            target=target,
            outcome="success",
            delta=1.0,
            trace="trace:feedback",
        )
    ]
    oversized = [
        PheromoneTrail(candidate_id, policy.per_round_deposit_cap + 1, kind="positive")
    ]
    problems = pheromone_reinforcement._reinforcement_result_problems(
        feedback=feedback,
        trails=oversized,
        isolated=[],
        probe_strength=policy.max_strength,
        policy=policy,
        candidates=candidates,
        target=target,
        neighborhood=neighborhood,
    )
    assert set(problems) == {"round_cap", "permutation_sensitive", "congested_kind"}

    valid_feedback = pheromone_reinforcement.item(
        candidate_id,
        target=target,
        outcome="success",
        delta=1.0,
        trace="trace:valid-feedback",
    )
    assert (
        pheromone_reinforcement._feedback_rejected(
            valid_feedback,
            policy,
            candidates,
            target=target,
            neighborhood=neighborhood,
        )
        is False
    )
    single = CandidateSet((Candidate(candidate_id, target),))
    assert (
        pheromone_reinforcement._wrong_subject_binding_rejected(
            candidate_id=candidate_id,
            target=target,
            probe_strength=1.0,
            policy=policy,
            candidates=single,
            neighborhood=neighborhood,
        )
        is True
    )
    contract_problems = pheromone_reinforcement._feedback_contract_problems(
        candidate_id=candidate_id,
        target=target,
        probe_strength=1.0,
        policy=policy,
        candidates=candidates,
        neighborhood=neighborhood,
        rejects_missing_lineage=False,
    )
    assert contract_problems == ["lineage_required"]

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_reinforcement.check(toy).ok is True
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert pheromone_reinforcement.check(without_candidates).detail == (
        "active_target_candidates"
    )


def test_layer_coordination_helpers_report_malformed_state_and_policy() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = layer_coordination_policy_from_collective(collective)
    candidates = layer_coordination_policy.candidate_set(hybrid)
    target = layer_coordination_policy.active_target(hybrid)
    primary = layer_coordination_policy.exercise_candidate_id(hybrid)
    assert primary is not None
    fallback_id = hybrid.protocol.quorum_policy.fallback_candidate

    proposal = layer_coordination_policy.action_proposal(
        "support",
        layer_id="learned",
        candidate_id=primary,
        target=target,
        policy=policy,
    )
    bad_positive = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": -1.0}},
    )
    assert layer_coordination_policy._action_state_problems(
        action="support",
        layer_id="learned",
        effect="wrong-effect",
        expected_effect="candidate_preference",
        expected_sign="positive",
        primary=primary,
        item=proposal,
        state=bad_positive,
    ) == [
        "action_effect:support",
        "action_lineage:support",
        "action_score:support",
    ]

    bad_negative = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": 1.0}},
        trace_lineage=[proposal.trace_event_id],
        action_effects={proposal.trace_event_id: "candidate_risk_pressure"},
    )
    assert layer_coordination_policy._action_state_problems(
        action="risk",
        layer_id="learned",
        effect="candidate_risk_pressure",
        expected_effect="candidate_risk_pressure",
        expected_sign="negative",
        primary=primary,
        item=proposal,
        state=bad_negative,
    ) == ["action_score:risk"]

    bad_zero = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": 1.0}},
        trace_lineage=[proposal.trace_event_id],
        action_effects={proposal.trace_event_id: "scouting_required"},
    )
    assert layer_coordination_policy._action_state_problems(
        action="request_scouting",
        layer_id="learned",
        effect="scouting_required",
        expected_effect="scouting_required",
        expected_sign="zero",
        primary=primary,
        item=proposal,
        state=bad_zero,
    ) == ["action_score:request_scouting"]

    interaction_expectations = {
        "request_scouting": "action_conflict:request_scouting",
        "fallback_pressure": "action_conflict:fallback_pressure",
        "alarm": "action_conflict:alarm",
        "cautionary": "action_conflict:cautionary",
        "confirm_trace_coverage": ("action_confirmation:confirm_trace_coverage"),
    }
    for action, marker in interaction_expectations.items():
        item = layer_coordination_policy.action_proposal(
            action,
            layer_id=(
                "metacognitive" if action == "confirm_trace_coverage" else "reactive"
            ),
            candidate_id=primary,
            target=target,
            policy=policy,
        )
        problems = layer_coordination_policy._action_interaction_problems(
            action=action,
            primary=primary,
            item=item,
            state=LayerCoordinationState(),
            candidates=candidates,
            target=target,
            policy=policy,
        )
        assert marker in problems

    proposed = layer_coordination_policy.action_proposal(
        "propose_pheromone",
        layer_id="evolutionary",
        candidate_id=primary,
        target=target,
        policy=policy,
        collective_policy=None,
    )
    assert proposed.proposed_pheromone_kind == "positive"
    assert proposed.proposed_strength == 1.0
    assert (
        layer_coordination_policy._action_interaction_problems(
            action="propose_pheromone",
            primary=primary,
            item=proposed,
            state=LayerCoordinationState(),
            candidates=candidates,
            target=target,
            policy=policy,
        )
        == []
    )

    no_secondary = layer_coordination_policy.coordination_interaction_problems(
        policy=policy,
        candidates=candidates,
        target=target,
        primary=primary,
        secondary=None,
        fallback_id=fallback_id,
    )
    assert no_secondary == []

    invalid_declared = replace(
        collective,
        layer_min_provenance=0,
        layer_conflict_threshold=-1.0,
        layer_emergency_override_threshold=-1.0,
        layer_default_weights={"unknown": -1.0},
        layer_weight_bounds={"unknown": (-1.0, -2.0)},
    )
    assert set(
        layer_coordination_policy.declared_policy_problems(invalid_declared)
    ) == {
        "bounds",
        "layer_id",
        "min_layer_provenance",
        "thresholds",
        "weights",
    }

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert layer_coordination_policy.check(toy).ok is True
    assert layer_coordination_policy.layer_coordination_problems(toy) == [
        "collective_policy"
    ]
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert layer_coordination_policy.layer_coordination_problems(
        without_candidates
    ) == ["active_target_candidates"]
    malformed = layer_coordination_policy.check(
        _manifest_with_policy(hybrid, layer_min_provenance="invalid")
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("exercise:TypeError")


def test_kind_profile_helpers_cover_no_score_priority_and_response_edges() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_kind_profile.candidate_set(hybrid)
    target = pheromone_kind_profile.active_target(hybrid)
    candidate_id = pheromone_kind_profile.exercise_candidate_id(hybrid)
    assert candidate_id is not None

    no_subject_policy = replace(policy, scored_subject_types=())
    positive = replace(
        no_subject_policy.kind_profiles["positive"],
        scored_subject_types=(),
        ttl_steps=None,
    )
    no_subject = pheromone_kind_profile._declared_kind_problems(
        kind="positive",
        profile=positive,
        candidates=candidates,
        candidate_id=candidate_id,
        target=target,
        policy=no_subject_policy,
        strength=1.0,
    )
    assert no_subject == ["positive_no_scored_subjects"]

    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=replace(policy, min_source_diversity=1),
        )
        == []
    )
    single = CandidateSet((Candidate(candidate_id, target),))
    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=single,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
        == []
    )
    no_emergency_profiles = replace(
        policy,
        kind_profiles={
            "positive": policy.kind_profiles["positive"],
        },
    )
    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=no_emergency_profiles,
        )
        == []
    )
    assert (
        pheromone_kind_profile.same_source_priority_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=no_emergency_profiles,
        )
        == []
    )
    only_alarm = replace(
        policy,
        kind_profiles={"alarm": policy.kind_profiles["alarm"]},
    )
    assert (
        pheromone_kind_profile.same_source_priority_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=only_alarm,
        )
        == []
    )
    cap_incompatible = replace(
        policy,
        per_source_cap=2.0,
        per_round_deposit_cap=1.0,
    )
    assert (
        pheromone_kind_profile.same_source_priority_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=cap_incompatible,
        )
        == []
    )
    no_positive_subjects = replace(
        policy,
        scored_subject_types=(),
        kind_profiles={
            kind: replace(profile, scored_subject_types=())
            for kind, profile in policy.kind_profiles.items()
        },
    )
    assert (
        pheromone_kind_profile.kind_suppression_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=no_positive_subjects,
        )
        == []
    )
    suppression_disabled = replace(
        policy,
        kind_profiles={
            **dict(policy.kind_profiles),
            "alarm": replace(
                policy.kind_profiles["alarm"],
                can_suppress_positive=False,
            ),
        },
    )
    assert (
        pheromone_kind_profile.kind_suppression_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=suppression_disabled,
        )
        == []
    )

    assert (
        pheromone_kind_profile.kind_response_magnitude("stale", 1.0, 1.0, policy) == 0.0
    )
    assert (
        pheromone_kind_profile.kind_response_magnitude(
            "novelty",
            1.0,
            1.0,
            replace(policy, exploration_enabled=False),
        )
        == 0.0
    )
    threshold_policy = replace(
        policy,
        activation_threshold=2.0,
        kind_profiles={
            **dict(policy.kind_profiles),
            "positive": replace(
                policy.kind_profiles["positive"],
                response_model="threshold",
            ),
        },
    )
    assert (
        pheromone_kind_profile.kind_response_magnitude(
            "positive",
            1.0,
            1.0,
            threshold_policy,
        )
        == 0.0
    )
    zero_saturation = replace(
        policy,
        saturation_threshold=0.0,
        kind_profiles={
            **dict(policy.kind_profiles),
            "positive": replace(
                policy.kind_profiles["positive"],
                response_model="saturating",
            ),
        },
    )
    assert (
        pheromone_kind_profile.kind_response_magnitude(
            "positive",
            1.0,
            1.0,
            zero_saturation,
        )
        == 0.0
    )

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_kind_profile.check(toy).ok is True
    assert pheromone_kind_profile.kind_profile_problems(toy) == ["collective_policy"]
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert pheromone_kind_profile.kind_profile_problems(without_candidates) == [
        "active_target_candidates"
    ]
    malformed = pheromone_kind_profile.check(
        _manifest_with_policy(hybrid, pheromone_max_strength="invalid")
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("exercise:ValueError")


def test_response_model_helpers_cover_numeric_and_exploration_boundaries() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_response_model.candidate_set(hybrid)
    target = pheromone_response_model.active_target(hybrid)
    alpha = pheromone_response_model.exercise_candidate_id(hybrid)
    assert alpha is not None
    candidate_ids = [candidate.id for candidate in candidates.candidates]
    forward = {candidate_id: 1.0 for candidate_id in candidate_ids}
    reverse = {candidate_id: 2.0 for candidate_id in candidate_ids}
    forward[alpha] = float("nan")
    threshold_policy = replace(
        policy,
        response_model="competitive",
        activation_threshold=1.0,
        min_strength=0.0,
    )
    threshold_problems = pheromone_response_model._basic_response_problems(
        candidates=candidates,
        alpha=alpha,
        target=target,
        policy=threshold_policy,
        response_model="threshold",
        forward=forward,
        reverse=reverse,
        baseline={candidate_id: 99.0 for candidate_id in candidate_ids},
    )
    assert set(threshold_problems) == {
        "permutation_sensitive",
        "non_finite",
        "threshold",
        "competitive_normalize",
    }

    saturating_problems = pheromone_response_model._basic_response_problems(
        candidates=candidates,
        alpha=alpha,
        target=target,
        policy=replace(policy, saturation_threshold=0.5, competition_mode="none"),
        response_model="saturating",
        forward={candidate_id: 10.0 for candidate_id in candidate_ids},
        reverse={candidate_id: 10.0 for candidate_id in candidate_ids},
        baseline={candidate_id: 0.0 for candidate_id in candidate_ids},
    )
    assert saturating_problems == ["saturating"]

    below, below_expected = pheromone_response_model._stale_route_reopen_probes(
        candidate_id=alpha,
        target=target,
        minimum=1.0,
        maximum=2.0,
        reopen_threshold=0.5,
    )
    assert len(below) == 1
    assert set(below_expected.values()) == {False}
    above, above_expected = pheromone_response_model._stale_route_reopen_probes(
        candidate_id=alpha,
        target=target,
        minimum=1.0,
        maximum=2.0,
        reopen_threshold=3.0,
    )
    assert len(above) == 1
    assert set(above_expected.values()) == {True}

    disabled = pheromone_response_model.exploration_policy_problems(
        candidates=candidates,
        candidate_id=alpha,
        target=target,
        policy=replace(policy, exploration_enabled=False),
    )
    assert disabled == []
    zero_pressure = pheromone_response_model.exploration_policy_problems(
        candidates=candidates,
        candidate_id=alpha,
        target=target,
        policy=replace(policy, novelty_decay_rate=1.0),
    )
    assert zero_pressure == []
    assert (
        pheromone_response_model._response_floor_problems(
            candidates=candidates,
            target=target,
            policy=replace(
                policy,
                response_exploration_floor=0.0,
                exploration_enabled=False,
                exploration_floor=0.0,
            ),
        )
        == []
    )

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_response_model.check(toy).ok is True
    assert pheromone_response_model.response_model_problems(toy) == [
        "collective_policy"
    ]
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert pheromone_response_model.response_model_problems(without_candidates) == [
        "active_target_candidates"
    ]
    malformed = pheromone_response_model.check(
        _manifest_with_policy(hybrid, pheromone_max_strength="invalid")
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("exercise:TypeError")


def test_pheromone_behavior_totality_and_optional_lineage_contracts() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_behavior.candidate_set(hybrid)
    target = pheromone_behavior.active_target(hybrid)
    candidate_id = pheromone_behavior.exercise_candidate_id(hybrid)
    assert candidate_id is not None

    optional_lineage = replace(
        policy,
        enabled=False,
        require_provenance=False,
        require_trace=False,
    )
    assert (
        pheromone_behavior.rejects_missing_provenance(
            candidate_id,
            target,
            optional_lineage,
            candidates,
        )
        is False
    )
    assert (
        pheromone_behavior.rejects_missing_trace(
            candidate_id,
            target,
            optional_lineage,
            candidates,
        )
        is False
    )
    assert (
        pheromone_behavior.empty_trail_cannot_satisfy_source_diversity(
            candidate_id,
            target,
            candidates,
            replace(policy, min_strength=0.5),
        )
        is True
    )
    assert (
        pheromone_behavior.clips_pheromone(
            candidate_id,
            target,
            replace(
                policy,
                enabled=False,
                min_strength=0.5,
                per_source_cap=0.25,
                per_round_deposit_cap=0.25,
            ),
            candidates,
        )
        is True
    )
    assert pheromone_behavior.fixture_error(Exception()) == "fixture_error:Exception"

    fallback_id = hybrid.protocol.quorum_policy.fallback_candidate
    no_fallback = replace(
        hybrid,
        protocol=replace(
            hybrid.protocol,
            candidates=tuple(
                candidate
                for candidate in hybrid.protocol.candidates
                if candidate.id != fallback_id
            ),
        ),
    )
    assert pheromone_behavior.check_enabled(no_fallback, collective).detail == (
        "safe_fallback"
    )
    assert (
        pheromone_behavior._has_declared_safe_fallback(
            candidates,
            "candidate:missing",
            target,
        )
        is False
    )
    unsafe_candidates = CandidateSet(
        (
            Candidate(
                fallback_id,
                target,
                safe_fallback=False,
            ),
        )
    )
    assert (
        pheromone_behavior._has_declared_safe_fallback(
            unsafe_candidates,
            fallback_id,
            target,
        )
        is False
    )

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert pheromone_behavior.check(toy).ok is True
    malformed = pheromone_behavior.check(
        _manifest_with_policy(
            hybrid,
            pheromone_min_source_diversity="invalid",
        )
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("fixture_error:GovernanceError")


def test_score_breakdown_checker_handles_absent_and_malformed_swarm_fixtures() -> None:
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert score_breakdown_contract.check(toy).ok is True
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    missing = score_breakdown_contract.check(without_candidates)
    assert missing.ok is False
    assert missing.detail == "target_candidates"
    malformed = score_breakdown_contract.check(
        _manifest_with_policy(
            hybrid,
            pheromone_min_source_diversity="invalid",
        )
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("fixture_error:TypeError")
    assert score_breakdown_contract.fixture_error(Exception()) == (
        "fixture_error:Exception"
    )


def test_commit_policy_checker_reports_binding_profile_and_digest_contracts() -> None:
    commit = _load_commit_manifest()
    policy = commit.protocol.collective_commit_policy
    assert policy is not None
    fallback_id = policy.terminal_outcome.safe_fallback_candidate

    fully_unbound = replace(
        commit,
        protocol=replace(
            commit.protocol,
            targets=(),
            candidates=(),
            quorum_policy=replace(
                commit.protocol.quorum_policy,
                target="decision:other",
                fallback_candidate="candidate:other",
            ),
            collective_decision_policy=replace(
                commit.protocol.collective_decision_policy,
                fallback_candidate="candidate:other",
            ),
        ),
    )
    assert set(
        commit_policy_contract._target_and_fallback_problems(
            fully_unbound,
            policy,
        )
    ) == {
        "collective_fallback_binding",
        "declared_fallback",
        "declared_target",
        "quorum_fallback_binding",
        "quorum_target_binding",
    }

    unsafe = replace(
        commit,
        protocol=replace(
            commit.protocol,
            candidates=tuple(
                replace(candidate, safe_fallback=False)
                if candidate.id == fallback_id
                else candidate
                for candidate in commit.protocol.candidates
            ),
        ),
    )
    assert commit_policy_contract._target_and_fallback_problems(
        unsafe,
        policy,
    ) == ["safe_fallback_marker"]

    wrong_target = replace(
        commit,
        protocol=replace(
            commit.protocol,
            candidates=tuple(
                replace(candidate, target="decision:other")
                if candidate.id == fallback_id
                else candidate
                for candidate in commit.protocol.candidates
            ),
        ),
    )
    assert commit_policy_contract._target_and_fallback_problems(
        wrong_target,
        policy,
    ) == ["fallback_target_binding"]

    expected_profiles = {
        "distributed": "pheroos-distributed-commit-v1",
        "certified": "pheroos-certified-commit-v1",
        "evidence_bound": "pheroos-hybrid-commit-v1",
        "advisory": "pheroos-commit-integrity-v1",
    }
    for assurance, expected in expected_profiles.items():
        assert (
            commit_policy_contract._expected_profile_version(
                commit,
                replace(policy, assurance=assurance),
            )
            == expected
        )
    nonhybrid = replace(
        commit,
        protocol=replace(commit.protocol, collective_decision_policy=None),
    )
    assert (
        commit_policy_contract._expected_profile_version(
            nonhybrid,
            replace(policy, assurance="evidence_bound"),
        )
        == "pheroos-commit-integrity-v1"
    )

    invalid_profile_policy = replace(policy, assurance="unsupported")
    profile_problems, selected = commit_policy_contract._profile_contract_problems(
        replace(
            commit,
            protocol=replace(
                commit.protocol,
                collective_commit_policy=invalid_profile_policy,
            ),
        ),
        invalid_profile_policy,
    )
    assert selected is None
    assert profile_problems[0].startswith("profile_selection:ValueError")

    assert commit_policy_contract._is_sha256_root("sha256:" + "a" * 64) is True
    assert commit_policy_contract._is_sha256_root(None) is False
    assert commit_policy_contract._is_sha256_root("md5:" + "a" * 64) is False
    assert commit_policy_contract._is_sha256_root("sha256:short") is False
    assert commit_policy_contract._is_sha256_root("sha256:" + "g" * 64) is False
    deduplicated = commit_policy_contract._result(["b", "a", "b"])
    assert deduplicated.ok is False
    assert deduplicated.detail == "a, b"

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert commit_policy_contract.check(toy).ok is True
    invalid_result = commit_policy_contract.check(
        replace(
            commit,
            protocol=replace(
                commit.protocol,
                collective_commit_policy=replace(
                    policy,
                    evidence_qualification=replace(
                        policy.evidence_qualification,
                        numeric_scale=1,
                    ),
                ),
            ),
        )
    )
    assert invalid_result.ok is False
    assert "diagnostic:" in invalid_result.detail


def test_commit_authority_numeric_and_principal_total_function_edges() -> None:
    commit = _load_commit_manifest()
    context = commit_authority_boundary.active_commit_context(commit)
    assert context is not None
    decision_ref = commit_authority_boundary._decision_ref(context)

    assert (
        commit_authority_boundary._permission_issuance_rejected(
            context,
            decision_ref=decision_ref,
            authority=commit_authority_boundary.AuthorityLevel.GOVERNANCE,
            allowed=True,
            trace_event_id="trace:permission:valid",
        )
        is False
    )
    assert (
        commit_authority_boundary._stop_issuance_rejected(
            context,
            decision_ref=decision_ref,
            authority=commit_authority_boundary.AuthorityLevel.GOVERNANCE,
            blocked=False,
            trace_event_id="trace:stop:valid",
        )
        is False
    )
    attestation = principal_attestation_contract._attestation()
    assert (
        principal_attestation_contract._issuance_rejected(
            context,
            attestation,
            authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
            current_step=5,
            trace_event_id="trace:principal:valid",
        )
        is False
    )

    assert commit_numeric_contract._rejects_with_governance_error(lambda: None) is False

    def wrong_exception() -> None:
        raise RuntimeError("not a governance rejection")

    assert (
        commit_numeric_contract._rejects_with_governance_error(wrong_exception) is False
    )

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert commit_authority_boundary.check(toy).ok is True
    assert commit_numeric_contract.check(toy).ok is True
    assert principal_attestation_contract.check(toy).ok is True


def test_policy_adjustment_negative_probes_reach_owned_mismatch_paths() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = hybrid.protocol.collective_decision_policy
    assert policy is not None
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert policy_adjustment_bounds.check(toy).ok is True
    assert (
        policy_adjustment_bounds._proposal_rejected(
            policy_adjustment_bounds.proposal(
                {"pheromone_evaporation_rate": policy.pheromone_evaporation_rate}
            ),
            policy,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            policy,
            "pheromone_cautionary_weight",
            policy.pheromone_kind_profiles["cautionary"].weight,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            policy,
            "layer_learned_weight",
            -1.0,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            policy,
            "pheromone_evaporation_rate",
            policy.pheromone_evaporation_rate,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            policy,
            "pheromone_response_model",
            policy.pheromone_response_model,
        )
        is False
    )


def test_trace_store_probe_detects_nonempty_first_store() -> None:
    store = InMemoryTraceStore()
    store.append(
        trace_store_contract.TraceEvent(
            event_type="x-test.preexisting-first",
            protocol_id="protocol:test",
            target="decision:test",
            reason="preexisting first record",
        )
    )
    problems: list[str] = []
    trace_store_contract._exercise_first_append(store, problems)
    assert "fresh_store_not_empty" in problems
    assert "first_record_binding" in problems
    assert "first_record_snapshot" in problems


def test_noncanonical_commit_policy_subclass_fails_closed() -> None:
    commit = _load_commit_manifest()
    policy = commit.protocol.collective_commit_policy
    assert policy is not None
    derived_type = type(
        "DerivedCollectiveCommitPolicy",
        (type(policy),),
        {},
    )
    derived = derived_type(
        **{field.name: getattr(policy, field.name) for field in fields(policy)}
    )
    result = commit_policy_contract.check(
        replace(
            commit,
            protocol=replace(
                commit.protocol,
                collective_commit_policy=derived,
            ),
        )
    )
    assert result.ok is False
    assert "canonical_policy_type" in result.detail


def test_principal_contract_helper_detects_real_cross_scope_verifications() -> None:
    commit = _load_commit_manifest()
    context = principal_attestation_contract.active_commit_context(commit)
    assert context is not None
    attestation = principal_attestation_contract._attestation()
    valid = principal_attestation_contract._issue_verification(
        context,
        attestation,
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        trace_event_id="trace:principal:issued",
    )
    forged = replace(valid)
    assert principal_attestation_contract._issued_verification_problems(
        forged,
        context,
    ) == [
        "issued_verification_not_authoritative",
        "issued_verification_does_not_match",
    ]

    cross_target = principal_attestation_contract._issue_verification(
        replace(context, target=f"{context.target}:cross-scope"),
        attestation,
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        trace_event_id="trace:principal:cross-target",
    )
    assert "cross_target_replay_accepted" in (
        principal_attestation_contract._scope_replay_problems(
            cross_target,
            context,
        )
    )

    cross_run = principal_attestation_contract._issue_verification(
        replace(context, run_id=f"{context.run_id}:cross-scope"),
        attestation,
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        trace_event_id="trace:principal:cross-run",
    )
    assert "cross_run_replay_accepted" in (
        principal_attestation_contract._scope_replay_problems(
            cross_run,
            context,
        )
    )

    cross_epoch = principal_attestation_contract._issue_verification(
        replace(context, epoch=context.epoch + 1),
        attestation,
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        trace_event_id="trace:principal:cross-epoch",
    )
    assert "cross_epoch_replay_accepted" in (
        principal_attestation_contract._scope_replay_problems(
            cross_epoch,
            context,
        )
    )

    cross_cluster = principal_attestation_contract.verify_principal_attestation(
        attestation,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        cluster_id="cluster:cross-scope",
        failure_domain="failure-domain:conformance:east",
        verifier_id="governance:conformance:identity",
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance="urn:pheroos:conformance:principal-verification",
        trace_event_id="trace:principal:cross-cluster",
    )
    assert "cross_cluster_replay_accepted" in (
        principal_attestation_contract._scope_replay_problems(
            cross_cluster,
            context,
        )
    )

    long_lived = replace(attestation, expires_at_step=10)
    unexpired_at_probe = principal_attestation_contract._issue_verification(
        context,
        long_lived,
        authority=principal_attestation_contract.AuthorityLevel.GOVERNANCE,
        current_step=5,
        trace_event_id="trace:principal:long-lived",
    )
    assert "expired_verification_accepted" in (
        principal_attestation_contract._scope_replay_problems(
            unexpired_at_probe,
            context,
        )
    )


def test_kind_profile_post_cap_and_singleton_sign_paths() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = replace(
        pheromone_policy_from_collective(collective),
        min_source_diversity=2,
    )
    candidates = pheromone_kind_profile.candidate_set(hybrid)
    target = pheromone_kind_profile.active_target(hybrid)
    candidate_id = pheromone_kind_profile.exercise_candidate_id(hybrid)
    assert candidate_id is not None
    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
        == []
    )
    single = CandidateSet((Candidate(candidate_id, target),))
    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=single,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
        == []
    )
    without_alarm = replace(
        policy,
        kind_profiles={"positive": policy.kind_profiles["positive"]},
    )
    assert (
        pheromone_kind_profile.post_cap_source_diversity_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=without_alarm,
        )
        == []
    )

    singleton_policy = replace(policy, competition_mode="normalize")
    positive_problem = pheromone_kind_profile._kind_subject_score_problems(
        kind="positive",
        profile=singleton_policy.kind_profiles["positive"],
        subject_type="candidate",
        subject_types=("candidate",),
        competitive_singleton=False,
        candidates=single,
        candidate_id=candidate_id,
        target=target,
        policy=singleton_policy,
        strength=1.0,
    )
    assert positive_problem == []
    negative_problem = pheromone_kind_profile._kind_subject_score_problems(
        kind="negative",
        profile=singleton_policy.kind_profiles["negative"],
        subject_type="candidate",
        subject_types=("candidate",),
        competitive_singleton=False,
        candidates=single,
        candidate_id=candidate_id,
        target=target,
        policy=singleton_policy,
        strength=1.0,
    )
    assert negative_problem == []

    no_global_subjects = replace(
        policy,
        scored_subject_types=(),
        kind_profiles={
            "positive": replace(
                policy.kind_profiles["positive"],
                scored_subject_types=("candidate",),
            ),
            "alarm": replace(
                policy.kind_profiles["alarm"],
                scored_subject_types=(),
            ),
        },
    )
    assert (
        pheromone_kind_profile.kind_suppression_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=no_global_subjects,
        )
        == []
    )


def test_layer_provenance_padding_and_declared_short_circuit() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    invalid = replace(collective, layer_min_provenance=0)
    invalid_manifest = _manifest_with_policy(
        hybrid,
        layer_min_provenance=0,
    )
    assert layer_coordination_policy.layer_coordination_problems(
        invalid_manifest
    ) == layer_coordination_policy.declared_policy_problems(invalid)

    policy = replace(
        layer_coordination_policy_from_collective(collective),
        min_layer_provenance=4,
    )
    candidates = layer_coordination_policy.candidate_set(hybrid)
    target = layer_coordination_policy.active_target(hybrid)
    fallback_id = hybrid.protocol.quorum_policy.fallback_candidate
    primary = layer_coordination_policy.exercise_candidate_id(hybrid)
    assert primary is not None
    secondary = next(
        candidate.id
        for candidate in candidates.candidates
        if candidate.id not in {primary, fallback_id}
    )
    assert (
        layer_coordination_policy.coordination_interaction_problems(
            policy=policy,
            candidates=candidates,
            target=target,
            primary=primary,
            secondary=secondary,
            fallback_id=fallback_id,
        )
        == []
    )


def test_diffusion_minimum_strength_stops_the_frontier() -> None:
    record = PheromoneLifecycleRecord(
        action="diffuse_rejected",
        target="decision:test",
        candidate_id="candidate:test",
        subject_type="candidate",
        subject_id="candidate:test",
        kind="positive",
        source_kind="positive",
        source_id="agent:test",
        provenance="test",
        source_trace_event_id="trace:source",
        trace_event_id="trace:derived",
        old_strength=0.0,
        new_strength=0.0,
        requested_strength=0.5,
        applied_strength=0.0,
        hop=1,
        attenuation=0.5,
    )
    problems = pheromone_diffusion.expected_diffusion_problems(
        PheromoneBatchResult(records=(record,)),
        candidate_id="candidate:test",
        source_strength=1.0,
        policy=PheromonePolicy(
            min_strength=0.75,
            max_strength=1.0,
            per_source_cap=1.0,
            per_round_deposit_cap=1.0,
        ),
        diffusion_policy=PheromoneDiffusionPolicy(
            enabled=True,
            max_hops=1,
            attenuation=0.5,
        ),
    )
    assert problems == []

    missing_record = pheromone_diffusion.expected_diffusion_problems(
        PheromoneBatchResult(),
        candidate_id="candidate:test",
        source_strength=1.0,
        policy=PheromonePolicy(
            min_strength=0.0,
            max_strength=1.0,
            per_source_cap=1.0,
            per_round_deposit_cap=1.0,
        ),
        diffusion_policy=PheromoneDiffusionPolicy(
            enabled=True,
            max_hops=1,
            attenuation=0.5,
        ),
    )
    assert missing_record == ["diffusion_record_missing:1"]


def test_subject_scoring_falls_back_to_declared_no_score_kind() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    zero_profiles = {
        kind: replace(profile, weight=0.0)
        for kind, profile in policy.kind_profiles.items()
    }
    zero_policy = replace(
        policy,
        positive_weight=0.0,
        negative_weight=0.0,
        cautionary_weight=0.0,
        novelty_weight=0.0,
        kind_profiles=zero_profiles,
    )
    assert pheromone_subject_scoring._scoring_kind_for_subject(
        "candidate",
        zero_policy,
    ) == pheromone_subject_scoring.no_score_probe_kind("candidate", zero_policy)
    assert (
        pheromone_subject_scoring.kind_response_can_score(
            "positive",
            None,
            policy,
        )
        is True
    )


def test_kernel_context_filters_unpermissioned_plan_exposures() -> None:
    plan = OSPlan(
        tenant_id="tenant:test",
        request_id="request:test",
        driver_exposures=(
            DriverExposure(
                driver_id="driver:test",
                capability_id="capability:test",
                capabilities=("evidence:read",),
            ),
        ),
    )
    assert kernel_contract.manifest_context_problems(plan) == [
        "manifest_plan:driver_exposure_binding_mismatch"
    ]


def test_package_for_path_handles_package_initializers(tmp_path: Path) -> None:
    initializer = tmp_path / "pheroos/protocol/__init__.py"
    initializer.parent.mkdir(parents=True)
    initializer.write_text("", encoding="utf-8")
    assert kernel_import_boundary.package_for_path(tmp_path, initializer) == (
        "pheroos.protocol"
    )


def test_public_lifecycle_boundary_totalizes_structural_and_source_failures(
    tmp_path: Path,
) -> None:
    source_artifact = (
        ROOT / "pheroos/conformance/abi/public-python-api-lifecycle-v1.json"
    )
    lifecycle = json.loads(source_artifact.read_text(encoding="utf-8"))
    lifecycle["diagnostic_codes"][0]["package"] = []
    abi = tmp_path / "structural/pheroos/conformance/abi"
    abi.mkdir(parents=True)
    (abi / "public-python-api-lifecycle-v1.json").write_text(
        json.dumps(lifecycle),
        encoding="utf-8",
    )
    structural = public_abi_boundary.public_lifecycle_problems(tmp_path / "structural")
    assert structural == ["lifecycle:inspection_failed:TypeError"]

    source_root = tmp_path / "source"
    source_abi = source_root / "pheroos/conformance/abi"
    source_abi.mkdir(parents=True)
    (source_abi / "public-python-api-lifecycle-v1.json").write_text(
        source_artifact.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    protocol = source_root / "pheroos/protocol"
    protocol.mkdir(parents=True)
    (protocol / "validation.py").write_text("this is not valid ???", encoding="utf-8")
    source_failure = public_abi_boundary.public_lifecycle_problems(source_root)
    assert "lifecycle:inspection_failed:SyntaxError" in source_failure


def test_disabled_exploration_rejects_nonexploration_score_input() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_response_model.candidate_set(hybrid)
    target = pheromone_response_model.active_target(hybrid)
    candidate_id = pheromone_response_model.exercise_candidate_id(hybrid)
    assert candidate_id is not None
    positive = pheromone_response_model.trail(
        candidate_id,
        1.0,
        target=target,
        source="agent:positive",
    )
    problems = pheromone_response_model.disabled_exploration_problems(
        candidates=candidates,
        policy=policy,
        target=target,
        trails=[positive],
        current_step=0,
    )
    assert problems == ["exploration_disabled_novelty_score"]
