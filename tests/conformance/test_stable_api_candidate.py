from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from pheroos.conformance.public_api_inventory import build_public_api_inventory
from pheroos.conformance.stable_api_candidate import (
    build_stable_api_candidate,
    load_stable_api_candidate,
    promotion_candidate_differences,
    promotion_candidate_public_inventory_differences,
    stable_api_breaking_differences,
    stable_api_candidate_problems,
    stable_public_inventory_breaking_differences,
)
from pheroos.conformance.stable_api_roots import (
    STABLE_API_CURRENT_ROOT_TARGET,
    STABLE_API_FORBIDDEN_BINDINGS,
)


ROOT = Path(__file__).resolve().parents[2]


def _entries(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    packages = candidate["packages"]
    assert isinstance(packages, dict)
    return [
        entry
        for package in packages.values()
        if isinstance(package, dict)
        for entry in package["exports"]
        if isinstance(entry, dict)
    ]


def _formally_stable(candidate: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(candidate)
    value["lifecycle"] = {
        "formal_stable": True,
        "stability": "stable",
        "status": "promoted",
    }
    return value


def test_checked_candidate_is_draft_type_closed_and_within_budgets() -> None:
    checked = load_stable_api_candidate(ROOT)
    observed = build_stable_api_candidate(ROOT)

    assert checked == observed
    assert stable_api_candidate_problems(checked) == []
    assert checked["lifecycle"] == {
        "formal_stable": False,
        "stability": "draft",
        "status": "promotion_candidate",
    }
    summary = checked["summary"]
    budgets = checked["budgets"]
    assert summary["root_count"] <= budgets["roots"]
    assert summary["closure_count"] <= budgets["closure"]
    assert summary["governance_root_count"] <= budgets["governance_roots"]
    assert summary["governance_closure_count"] <= budgets["governance_closure"]
    assert summary["root_count"] <= STABLE_API_CURRENT_ROOT_TARGET
    assert checked["review_targets"] == {"roots": STABLE_API_CURRENT_ROOT_TARGET}
    assert checked["surface_diagnostics"] == []


def test_constructor_and_store_protocol_types_are_in_the_closure() -> None:
    candidate = build_stable_api_candidate(ROOT)
    bindings = {item["binding"] for item in _entries(candidate)}

    assert {
        "pheroos.protocol.AuthorityDiagnosticCodeV2",
        "pheroos.protocol.AuthorityV2ProtocolError",
        "pheroos.protocol.GovernanceAuthorityReadSetV2",
        "pheroos.governance.ActionPermissionV2",
        "pheroos.governance.GovernanceCommitInclusionProofV2",
        "pheroos.governance.GovernanceCommittedTransitionV2",
        "pheroos.governance.GovernanceFailureStageV2",
        "pheroos.governance.PreparedGovernanceTransitionV2",
        "pheroos.kernel.KernelPlanVersionError",
        "pheroos.drivers.DriverInvocationStoreErrorV2",
        "pheroos.drivers.DriverInvocationWireErrorV2",
        "pheroos.governance.GovernanceAuthorityBindingErrorV2",
    } <= bindings


def test_exception_and_constant_dependencies_are_explicit_and_closed() -> None:
    candidate = build_stable_api_candidate(ROOT)
    entries = {item["binding"]: item for item in _entries(candidate)}
    constants = {item["binding"]: item for item in candidate["constant_dependencies"]}

    assert entries["pheroos.kernel.os_plan_from_dict"]["exception_references"] == [
        "pheroos.kernel.KernelPlanVersionError"
    ]
    assert entries["pheroos.drivers.DriverInvocationStoreV2"][
        "exception_references"
    ] == [
        "pheroos.drivers.DriverInvocationStoreErrorV2",
        "pheroos.drivers.DriverInvocationWireErrorV2",
    ]
    assert entries["pheroos.kernel.RuntimeScope"]["constant_dependencies"] == [
        "pheroos.kernel.RUNTIME_SCOPE_VERSION"
    ]
    assert constants["pheroos.kernel.RUNTIME_SCOPE_VERSION"]["shape"] == {
        "attribute": "RUNTIME_SCOPE_VERSION",
        "binding_owner": "pheroos.kernel.run_scope",
        "constant": {
            "type": "builtins:str",
            "value": "pheroos-runtime-scope-v1",
        },
        "kind": "constant",
        "name": "RUNTIME_SCOPE_VERSION",
    }
    assert candidate["summary"]["constant_dependency_count"] == len(constants)


def test_opaque_nonportable_authority_cannot_enter_candidate() -> None:
    candidate = build_stable_api_candidate(
        ROOT,
        roots={"pheroos.governance": ("GovernanceAuthoritySessionV2",)},
    )

    assert (
        "surface:nonportable_opaque:pheroos.governance.GovernanceAuthoritySessionV2"
        in stable_api_candidate_problems(candidate)
    )
    selected = {item["binding"] for item in _entries(build_stable_api_candidate(ROOT))}
    assert selected.isdisjoint(STABLE_API_FORBIDDEN_BINDINGS)


@pytest.mark.parametrize(
    ("package_name", "binding", "expected_problem"),
    (
        (
            "pheroos.governance",
            "GovernanceAuthoritySessionV2",
            (
                "surface:nonportable_opaque:"
                "pheroos.governance.GovernanceAuthoritySessionV2"
            ),
        ),
    ),
)
def test_candidate_negative_membership_matrix(
    package_name: str,
    binding: str,
    expected_problem: str,
) -> None:
    candidate = build_stable_api_candidate(
        ROOT,
        roots={package_name: (binding,)},
    )

    assert expected_problem in stable_api_candidate_problems(candidate)


def test_governance_roots_use_portable_recovery_not_an_opaque_session_path() -> None:
    candidate = build_stable_api_candidate(ROOT)
    roots = set(candidate["packages"]["pheroos.governance"]["roots"])

    assert {
        "BaselineOutputRequestV2",
        "BaselineOutputResultV2",
        "GovernanceIssuerGrantV2",
        "GovernanceStateStoreV2",
        "IssuerGrantVerifierV2",
        "activate_governance_issuer_grant_v2",
        "baseline_verified_signal_proposal_root_v2",
        "evaluate_and_commit_governed_baseline_output_v2",
        "recover_baseline_output_result_v2",
        "revoke_governance_issuer_grant_v2",
    } <= roots
    assert {
        "GovernanceAuthoritySessionV2",
        "bind_governance_issuer_capability_v2",
        "evaluate_and_commit_baseline_output_v2",
        "open_baseline_output_authority_session_v2",
    }.isdisjoint(roots)


def test_internal_owner_and_missing_constant_dependency_are_reported() -> None:
    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["shape"]["binding_owner"] = "pheroos.protocol._private"
    assert (
        f"internal_owner:{entry['binding']}:binding_owner"
        in stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    source = next(item for item in _entries(candidate) if item["constant_dependencies"])
    missing = source["constant_dependencies"][0]
    candidate["constant_dependencies"] = [
        item
        for item in candidate["constant_dependencies"]
        if item["binding"] != missing
    ]
    assert (
        f"constant_dependency_missing:{source['binding']}:{missing}"
        in stable_api_candidate_problems(candidate)
    )


def test_constant_value_drift_is_candidate_drift() -> None:
    expected = build_stable_api_candidate(ROOT)
    observed = deepcopy(expected)
    observed["constant_dependencies"][0]["shape"]["constant"]["value"] = (
        "synthetic-drift"
    )

    assert promotion_candidate_differences(expected, observed)


def test_missing_transitive_type_is_reported() -> None:
    candidate = build_stable_api_candidate(ROOT)
    entries = _entries(candidate)
    source = next(item for item in entries if item["references"])
    missing = source["references"][0]
    package_name = missing.rsplit(".", 1)[0]
    package = candidate["packages"][package_name]
    package["exports"] = [
        item for item in package["exports"] if item["binding"] != missing
    ]

    assert any(
        problem == f"closure_missing:{source['binding']}:{missing}"
        for problem in stable_api_candidate_problems(candidate)
    )


def test_duplicate_canonical_owner_is_reported() -> None:
    candidate = build_stable_api_candidate(ROOT)
    package = candidate["packages"]["pheroos.protocol"]
    original = next(
        item for item in package["exports"] if item["shape"].get("identity") is not None
    )
    duplicate = deepcopy(original)
    duplicate["binding"] = "pheroos.protocol.SyntheticOwnerAlias"
    duplicate["canonical_binding"] = duplicate["binding"]
    duplicate["membership"] = "dependency"
    package["exports"].append(duplicate)

    assert any(
        problem.startswith("canonical_owner_duplicate:")
        for problem in stable_api_candidate_problems(candidate)
    )


def test_noncanonical_public_alias_cannot_be_selected_as_a_root() -> None:
    candidate = build_stable_api_candidate(
        ROOT,
        roots={"pheroos.governance": ("AuthorityDiagnosticCodeV2",)},
    )

    assert (
        "non_canonical_owner:pheroos.governance.AuthorityDiagnosticCodeV2"
        in stable_api_candidate_problems(candidate)
    )


def test_deprecated_or_compatibility_binding_cannot_enter_candidate() -> None:
    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["lifecycle_stability"] = "deprecated"

    assert f"deprecated:{entry['binding']}" in stable_api_candidate_problems(candidate)


def test_draft_candidate_drift_is_not_formal_stable_breakage() -> None:
    expected = build_stable_api_candidate(ROOT)
    observed = deepcopy(expected)
    _entries(observed)[0]["shape"]["signature"] = {"synthetic": "draft-change"}

    assert promotion_candidate_differences(expected, observed)
    assert stable_api_breaking_differences(expected, observed) == []


def test_draft_public_inventory_diff_projects_only_candidate_closure() -> None:
    candidate = build_stable_api_candidate(ROOT)
    expected = build_public_api_inventory()
    observed = deepcopy(expected)
    selected = {item["binding"] for item in _entries(candidate)} | {
        item["binding"] for item in candidate["constant_dependencies"]
    }
    package_name, draft = next(
        (name, item)
        for name, package in observed["packages"].items()
        for item in package["exports"]
        if f"{name}.{item['name']}" not in selected
    )
    draft["signature"] = {"synthetic": "expert-draft-change"}

    assert package_name.startswith("pheroos.")
    assert (
        promotion_candidate_public_inventory_differences(
            candidate,
            expected,
            observed,
        )
        == []
    )

    candidate_binding = next(iter(selected))
    candidate_package, candidate_name = candidate_binding.rsplit(".", 1)
    candidate_shape = next(
        item
        for item in observed["packages"][candidate_package]["exports"]
        if item["name"] == candidate_name
    )
    candidate_shape["signature"] = {"synthetic": "candidate-change"}
    assert promotion_candidate_public_inventory_differences(
        candidate,
        expected,
        observed,
    )


def test_same_compatibility_major_formal_stable_breakage_is_reported() -> None:
    expected = _formally_stable(build_stable_api_candidate(ROOT))
    observed = deepcopy(expected)
    _entries(observed)[0]["shape"]["signature"] = {"synthetic": "breaking"}

    assert stable_api_breaking_differences(expected, observed)
    observed["compatibility_major"] = expected["compatibility_major"] + 1
    assert stable_api_breaking_differences(expected, observed) == []


def test_full_inventory_draft_changes_outside_stable_closure_are_ignored() -> None:
    stable = _formally_stable(build_stable_api_candidate(ROOT))
    expected = build_public_api_inventory()
    observed = deepcopy(expected)
    closure = {item["binding"] for item in _entries(stable)}
    draft = next(
        (package_name, item)
        for package_name, package in observed["packages"].items()
        for item in package["exports"]
        if f"{package_name}.{item['name']}" not in closure
    )
    draft[1]["signature"] = {"synthetic": "expert-draft-change"}

    assert (
        stable_public_inventory_breaking_differences(
            stable,
            expected,
            observed,
            observed_compatibility_major=stable["compatibility_major"],
        )
        == []
    )

    selected = next(iter(closure))
    package_name, name = selected.rsplit(".", 1)
    selected_shape = next(
        item
        for item in observed["packages"][package_name]["exports"]
        if item["name"] == name
    )
    selected_shape["signature"] = {"synthetic": "stable-breaking"}
    assert stable_public_inventory_breaking_differences(
        stable,
        expected,
        observed,
        observed_compatibility_major=stable["compatibility_major"],
    )


def test_candidate_rejects_closed_top_level_metadata_and_diagnostics() -> None:
    mutations: tuple[tuple[str, object, str], ...] = (
        ("artifact_version", "pheroos-stable-api-candidate-v999", "artifact_version"),
        ("compatibility_major", 999, "compatibility_major"),
        ("lifecycle", {"stability": "stable"}, "lifecycle"),
        ("closure_policy", {}, "closure_policy"),
        ("review_targets", {"roots": 10_000}, "review_targets"),
        ("resolution_diagnostics", ["unresolved:synthetic"], "resolution_diagnostics"),
        ("surface_diagnostics", {"unexpected": True}, "surface_diagnostics"),
    )
    for field, value, expected in mutations:
        candidate = build_stable_api_candidate(ROOT)
        candidate[field] = value
        assert expected in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    candidate["packages"] = {}
    assert "packages" in stable_api_candidate_problems(candidate)


def test_candidate_rejects_malformed_package_and_entry_contracts() -> None:
    candidate = build_stable_api_candidate(ROOT)
    package = candidate["packages"]["pheroos.trace"]
    package["exports"] = tuple(package["exports"])
    assert "package:pheroos.trace" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    package = candidate["packages"]["pheroos.trace"]
    package["roots"] = []
    package["root_count"] = -1
    problems = stable_api_candidate_problems(candidate)
    assert "roots:pheroos.trace" in problems
    assert "root_count:pheroos.trace" in problems

    candidate = build_stable_api_candidate(ROOT)
    package = candidate["packages"]["pheroos.trace"]
    package["exports"].append(None)
    assert "entry:pheroos.trace:invalid" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["binding"] = "cross.package.Binding"
    assert f"entry:{entry['canonical_binding'].rsplit('.', 1)[0]}:binding" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["membership"] = "transient"
    assert f"membership:{entry['binding']}" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    package = candidate["packages"]["pheroos.trace"]
    duplicate = deepcopy(package["exports"][0])
    package["exports"].append(duplicate)
    assert f"duplicate_binding:{duplicate['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["lifecycle_stability"] = "experimental"
    assert f"lifecycle_stability:{entry['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["shape"] = None
    assert f"shape:{entry['binding']}" in stable_api_candidate_problems(candidate)


def test_candidate_rejects_noncanonical_reference_fields_and_open_closure() -> None:
    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["references"] = "not-an-array"
    assert f"references:{entry['binding']}" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    entry = next(item for item in _entries(candidate) if item["references"])
    entry["references"] = [entry["references"][0], entry["references"][0]]
    assert f"references_order:{entry['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["exception_references"] = ["pheroos.protocol.SyntheticException"]
    assert f"exception_reference_not_closed:{entry['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["public_bases"] = ["pheroos.protocol.SyntheticBase"]
    assert f"public_base_not_closed:{entry['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    entry = _entries(candidate)[0]
    entry["shape"]["identity"] = 7
    assert not any(
        problem.startswith("canonical_owner_duplicate:")
        for problem in stable_api_candidate_problems(candidate)
    )


def test_candidate_rejects_malformed_constant_dependency_contracts() -> None:
    candidate = build_stable_api_candidate(ROOT)
    candidate["constant_dependencies"] = {}
    assert "constant_dependencies" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    candidate["constant_dependencies"].append({})
    assert "constant_dependency:binding" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    duplicate = deepcopy(candidate["constant_dependencies"][0])
    candidate["constant_dependencies"].append(duplicate)
    assert f"constant_dependency_duplicate:{duplicate['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    candidate["constant_dependencies"].reverse()
    assert "constant_dependency_order" in stable_api_candidate_problems(candidate)

    mutations: tuple[tuple[str, object, str], ...] = (
        ("lifecycle_stability", "deprecated", "constant_deprecated:"),
        ("lifecycle_stability", "experimental", "constant_lifecycle_stability:"),
        ("lifecycle_group", "compatibility", "constant_compatibility:"),
        ("shape", {}, "constant_shape:"),
    )
    for field, value, prefix in mutations:
        candidate = build_stable_api_candidate(ROOT)
        constant = candidate["constant_dependencies"][0]
        constant[field] = value
        assert f"{prefix}{constant['binding']}" in stable_api_candidate_problems(
            candidate
        )

    candidate = build_stable_api_candidate(ROOT)
    constant = candidate["constant_dependencies"][0]
    constant["shape"]["kind"] = "callable"
    assert f"constant_kind:{constant['binding']}" in stable_api_candidate_problems(
        candidate
    )

    candidate = build_stable_api_candidate(ROOT)
    constant = candidate["constant_dependencies"][0]
    constant["shape"]["binding_owner"] = "pheroos.kernel._private"
    assert f"constant_internal_owner:{constant['binding']}" in (
        stable_api_candidate_problems(candidate)
    )

    candidate = build_stable_api_candidate(ROOT)
    constant = candidate["constant_dependencies"][0]
    constant["shape"]["constant"] = "mutable-runtime-value"
    assert f"constant_value:{constant['binding']}" in stable_api_candidate_problems(
        candidate
    )


def test_candidate_enforces_budget_shape_and_root_review_bound() -> None:
    candidate = build_stable_api_candidate(ROOT)
    candidate["budgets"] = []
    assert "budgets" in stable_api_candidate_problems(candidate)

    candidate = build_stable_api_candidate(ROOT)
    for package in candidate["packages"].values():
        for entry in package["exports"]:
            entry["membership"] = "root"
        package["roots"] = sorted(
            entry["binding"].rsplit(".", 1)[1] for entry in package["exports"]
        )
        package["root_count"] = len(package["roots"])
    problems = stable_api_candidate_problems(candidate)
    assert "review_target:roots" in problems
    assert "budget:roots" in problems


def test_inventory_projection_rejects_malformed_or_duplicate_exports() -> None:
    candidate = build_stable_api_candidate(ROOT)
    inventory = build_public_api_inventory()

    missing_packages = deepcopy(inventory)
    missing_packages["packages"] = []
    with pytest.raises(ValueError, match="packages must be an object"):
        promotion_candidate_public_inventory_differences(
            candidate,
            missing_packages,
            inventory,
        )

    invalid_package = deepcopy(inventory)
    invalid_package["packages"]["pheroos.trace"]["exports"] = ()
    with pytest.raises(ValueError, match="package is invalid"):
        promotion_candidate_public_inventory_differences(
            candidate,
            invalid_package,
            inventory,
        )

    invalid_export = deepcopy(inventory)
    invalid_export["packages"]["pheroos.trace"]["exports"].append(None)
    with pytest.raises(ValueError, match="export is invalid"):
        promotion_candidate_public_inventory_differences(
            candidate,
            invalid_export,
            inventory,
        )

    duplicate_export = deepcopy(inventory)
    exports = duplicate_export["packages"]["pheroos.trace"]["exports"]
    exports.append(deepcopy(exports[0]))
    with pytest.raises(ValueError, match="export is duplicated"):
        promotion_candidate_public_inventory_differences(
            candidate,
            duplicate_export,
            inventory,
        )


def test_projection_handles_absent_candidate_binding_collections() -> None:
    inventory = build_public_api_inventory()
    candidate = build_stable_api_candidate(ROOT)
    candidate["packages"] = None
    candidate["constant_dependencies"] = None

    assert (
        promotion_candidate_public_inventory_differences(
            candidate,
            inventory,
            inventory,
        )
        == []
    )


def test_formal_stable_inventory_allows_declared_major_transition() -> None:
    stable = _formally_stable(build_stable_api_candidate(ROOT))
    inventory = build_public_api_inventory()

    assert (
        stable_public_inventory_breaking_differences(
            stable,
            inventory,
            inventory,
            observed_compatibility_major=stable["compatibility_major"] + 1,
        )
        == []
    )


def test_candidate_generator_check_mode_is_external_cwd_safe(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_stable_api_candidate.py"),
            "--check",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
