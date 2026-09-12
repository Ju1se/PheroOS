from __future__ import annotations

import ast
from dataclasses import replace
import json
from pathlib import Path

import pytest

from pheroos.conformance import runner
from pheroos.conformance.checks import hybrid_authority_boundary
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
    output_contract,
    quorum_policy,
    recovery_policy,
    safe_fallback_collective,
)
from pheroos.conformance.report import ConformanceReport
from pheroos.drivers import DriverDescriptor
from pheroos.kernel import DriverExposure, OSPlan, ToolExposure
from pheroos.protocol import DriverSpec, RecoveryProtocol, load_capability_manifest
from pheroos.protocol.manifest import capability_manifest_from_dict


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_runner_reports_a_declared_check_without_an_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = ROOT / "examples/toy-protocol/capability.json"
    manifest = load_capability_manifest(manifest_path)
    required = next(
        name
        for name in runner.profile_for_manifest(manifest).required_checks
        if name != "manifest_schema"
    )
    monkeypatch.setattr(
        runner,
        "MANIFEST_CHECKS",
        {
            name: check
            for name, check in runner.MANIFEST_CHECKS.items()
            if name != required
        },
    )

    report = runner.run_conformance(manifest_path)

    check = next(item for item in report.checks if item.name == required)
    assert check.ok is False
    assert check.detail == "check implementation is not registered"


def test_conformance_report_rejects_noncanonical_check_values() -> None:
    with pytest.raises(
        TypeError,
        match="conformance report checks must be canonical CheckResult values",
    ):
        ConformanceReport(
            target="target",
            checks=(object(),),  # type: ignore[arg-type]
            profile="profile",
            artifact_digest="sha256:" + ("0" * 64),
        )


def test_hybrid_authority_checker_reports_an_absent_exercise_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    monkeypatch.setattr(
        hybrid_authority_boundary,
        "exercise_candidate_id",
        lambda _manifest: None,
    )

    result = hybrid_authority_boundary.check(manifest)

    assert result.ok is False
    assert result.detail == "active_target_candidates"


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


@pytest.mark.parametrize(
    ("operation", "faulty_result", "expected"),
    [
        (
            "action_permission_is_authoritative",
            False,
            {"issued_permission_not_authoritative"},
        ),
        (
            "action_permission_is_authoritative",
            True,
            {"direct_permission_forgery_accepted", "tampered_permission_accepted"},
        ),
        ("action_permission_matches", False, {"issued_permission_does_not_match"}),
        (
            "action_permission_matches",
            True,
            {
                "permission_cross_target_replay_accepted",
                "permission_cross_run_replay_accepted",
                "permission_cross_action_replay_accepted",
                "expired_permission_accepted",
            },
        ),
        (
            "stop_resolution_verification_is_authoritative",
            False,
            {"issued_stop_verification_not_authoritative"},
        ),
        (
            "stop_resolution_verification_is_authoritative",
            True,
            {
                "direct_stop_verification_forgery_accepted",
                "tampered_stop_verification_accepted",
            },
        ),
        (
            "stop_resolution_verification_matches",
            False,
            {
                "issued_stop_verification_does_not_match",
                "blocked_stop_denial_not_verifiable",
            },
        ),
        (
            "stop_resolution_verification_matches",
            True,
            {
                "stop_cross_target_replay_accepted",
                "stop_cross_action_replay_accepted",
                "expired_stop_verification_accepted",
                "blocked_stop_authorized_action",
            },
        ),
    ],
)
def test_commit_authority_checker_detects_broken_authenticity_and_scope_predicates(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    faulty_result: bool,
    expected: set[str],
) -> None:
    # These are deliberately faulty predicate implementations, not changed
    # expected decisions. Each checker must reject both fail-open and fail-closed
    # implementations rather than silently certifying an unusable contract.
    monkeypatch.setattr(
        commit_authority_boundary, operation, lambda *args, **kwargs: faulty_result
    )
    result = commit_authority_boundary.check(_load_commit_manifest())
    assert result.ok is False
    assert expected <= set(result.detail.split("; "))


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("issue_action_permission", "agent_permission_authority_accepted"),
        ("verify_stop_resolution", "agent_stop_verification_authority_accepted"),
    ],
)
def test_commit_authority_checker_detects_issuer_privilege_escalation(
    monkeypatch: pytest.MonkeyPatch, operation: str, expected: str
) -> None:
    original = getattr(commit_authority_boundary, operation)

    def unchecked_issuer(*args, **kwargs):
        kwargs["authority"] = commit_authority_boundary.AuthorityLevel.GOVERNANCE
        return original(*args, **kwargs)

    monkeypatch.setattr(commit_authority_boundary, operation, unchecked_issuer)
    result = commit_authority_boundary.check(_load_commit_manifest())
    assert result.ok is False
    assert expected in result.detail.split("; ")


@pytest.mark.parametrize(
    ("operation", "faulty_result", "expected"),
    [
        (
            "canonical_commit_payload",
            "not-canonical",
            {
                "canonical_reference_vector",
                "canonical_object_key_order",
                "rejection:float_canonical_payload",
                "rejection:canonical_integer_overflow",
            },
        ),
        (
            "commit_payload_fingerprint",
            "sha256:" + "0" * 64,
            {"fingerprint_reference_vector"},
        ),
        (
            "canonical_commit_set",
            (),
            {"canonical_set_order", "rejection:duplicate_canonical_set"},
        ),
        (
            "checked_add",
            0,
            {"numeric_vector:checked_add", "rejection:addition_overflow"},
        ),
    ],
)
def test_commit_numeric_checker_detects_broken_canonical_and_integer_implementations(
    monkeypatch: pytest.MonkeyPatch, operation: str, faulty_result, expected: set[str]
) -> None:
    monkeypatch.setattr(
        commit_numeric_contract, operation, lambda *args, **kwargs: faulty_result
    )
    result = commit_numeric_contract.check(_load_commit_manifest())
    assert result.ok is False
    assert expected <= set(result.detail.split(", "))


def test_commit_numeric_checker_rejects_wrong_scale_and_unrelated_exceptions() -> None:
    commit = _load_commit_manifest()
    policy = commit.protocol.collective_commit_policy
    assert policy is not None
    wrong_scale = replace(
        commit,
        protocol=replace(
            commit.protocol,
            collective_commit_policy=replace(
                policy,
                evidence_qualification=replace(
                    policy.evidence_qualification, numeric_scale=1
                ),
            ),
        ),
    )
    result = commit_numeric_contract.check(wrong_scale)
    assert result.ok is False
    assert result.detail == "manifest_numeric_scale"
    assert (
        commit_numeric_contract._rejects_with_governance_error(lambda: 1 / 0) is False
    )
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert commit_numeric_contract.check(toy).ok is True
    assert commit_authority_boundary.check(toy).ok is True


def test_hybrid_authority_checker_detects_proposal_to_authority_bypasses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert hybrid_authority_boundary.check(toy).ok is True
    assert hybrid_authority_boundary.check(hybrid).ok is True

    monkeypatch.setattr(
        hybrid_authority_boundary, "evaluate_collective_decision", lambda **kwargs: None
    )
    monkeypatch.setattr(
        hybrid_authority_boundary, "output_authorized", lambda *args, **kwargs: True
    )
    result = hybrid_authority_boundary.check(hybrid)
    assert result.ok is False
    assert result.detail == "forged_layer_state, proposal_direct_output"
