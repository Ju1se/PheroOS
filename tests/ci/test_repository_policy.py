from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_repository_policy import (
    GITHUB_ACTIONS_INTEGRATION_ID,
    IMMUTABLE_RELEASES_POLICY_PATH,
    IMMUTABLE_RELEASES_PROPOSAL_SCHEMA,
    REPOSITORY_SETTINGS_PATH,
    SCENARIOS_PATH,
    TAG_POLICY_PATH,
    audit_repository_policy,
    evaluate_immutable_releases_observation,
    evaluate_repository_change,
    load_policy,
    load_scenarios,
    validate_immutable_releases_policy,
    validate_tag_policy,
    validate_repository_settings,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / ".github" / "rulesets" / "main-proposed.json"
CODEOWNERS_PATH = ROOT / ".github" / "CODEOWNERS"


def _check(
    result: str, *, integration_id: int = GITHUB_ACTIONS_INTEGRATION_ID
) -> dict[str, object]:
    return {
        "quality-gate": {
            "integration_id": integration_id,
            "result": result,
        }
    }


def test_checked_in_repository_policy_is_canonical_and_proposed() -> None:
    assert audit_repository_policy(POLICY_PATH, CODEOWNERS_PATH) == []
    policy = load_policy(POLICY_PATH)

    assert policy["enforcement"] == "disabled"
    assert policy["target"] == "branch"
    assert policy["conditions"] == {
        "ref_name": {
            "exclude": [],
            "include": ["refs/heads/main"],
        }
    }
    assert policy["bypass_actors"] == []
    assert not ({"schema", "state", "repository"} & set(policy))


def test_checked_in_v_tag_policy_is_immutable_but_not_remotely_active() -> None:
    policy = load_policy(TAG_POLICY_PATH)

    assert validate_tag_policy(policy) == []
    assert policy == {
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "exclude": [],
                "include": ["refs/tags/v*"],
            }
        },
        "enforcement": "disabled",
        "name": "release-tag-immutability",
        "rules": [
            {"type": "deletion"},
            {"type": "update"},
        ],
        "target": "tag",
    }


def test_repository_settings_propose_automatic_merged_branch_deletion() -> None:
    settings = load_policy(REPOSITORY_SETTINGS_PATH)

    assert settings == {"delete_branch_on_merge": True}
    assert validate_repository_settings(settings) == []
    assert validate_repository_settings({"delete_branch_on_merge": False}) == [
        "repository settings proposal must enable only delete_branch_on_merge"
    ]
    assert validate_repository_settings({"delete_branch_on_merge": 1}) == [
        "repository settings proposal must enable only delete_branch_on_merge"
    ]


def test_immutable_releases_policy_is_exact_inert_and_owner_neutral() -> None:
    policy = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)

    assert validate_immutable_releases_policy(policy) == []
    assert policy == {
        "activation": {
            "accept": "application/vnd.github+json",
            "api_version": "2026-03-10",
            "api_version_header": "X-GitHub-Api-Version",
            "authenticated_repository_permission": "Administration: write",
            "method": "PUT",
            "path": "/repos/{owner}/{repo}/immutable-releases",
            "request_body": "absent",
            "success_status": 204,
        },
        "authorization": "wp-13-explicit-remote-authorization-required",
        "desired_state": {"enabled": True},
        "schema": IMMUTABLE_RELEASES_PROPOSAL_SCHEMA,
        "verification": {
            "accept": "application/vnd.github+json",
            "api_version": "2026-03-10",
            "api_version_header": "X-GitHub-Api-Version",
            "authenticated_repository_permission": "Administration: read",
            "method": "GET",
            "path": "/repos/{owner}/{repo}/immutable-releases",
            "required_response_subset": {"enabled": True},
            "success_status": 200,
        },
    }
    serialized = IMMUTABLE_RELEASES_POLICY_PATH.read_text(encoding="utf-8")
    assert "Ju1se" not in serialized
    assert "PheroOS" not in serialized
    assert "token" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert '"method": "DELETE"' not in serialized


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("activation", "accept"), "application/json"),
        (("activation", "api_version"), "2022-11-28"),
        (("activation", "api_version_header"), "X-API-Version"),
        (
            ("activation", "authenticated_repository_permission"),
            "Contents: write",
        ),
        (("activation", "method"), "POST"),
        (("activation", "path"), "/repos/{owner}/{repo}/releases"),
        (("activation", "request_body"), "{}"),
        (("activation", "success_status"), 200),
        (("authorization",), "authorized"),
        (("desired_state", "enabled"), False),
        (("desired_state", "enabled"), 1),
        (("schema",), "unversioned"),
        (("verification", "accept"), "application/json"),
        (("verification", "api_version"), "2022-11-28"),
        (("verification", "api_version_header"), "X-API-Version"),
        (
            ("verification", "authenticated_repository_permission"),
            "Contents: read",
        ),
        (("verification", "method"), "PUT"),
        (("verification", "path"), "/repos/{owner}/{repo}/releases"),
        (("verification", "required_response_subset", "enabled"), False),
        (("verification", "required_response_subset", "enabled"), 1),
        (("verification", "success_status"), 204),
    ],
)
def test_immutable_releases_policy_rejects_contract_mutations(
    path: tuple[str, ...],
    value: object,
) -> None:
    policy = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    current: dict[str, object] = policy
    for key in path[:-1]:
        nested = current[key]
        assert isinstance(nested, dict)
        current = nested
    current[path[-1]] = value

    assert validate_immutable_releases_policy(policy)


def test_immutable_releases_policy_rejects_missing_or_unknown_fields() -> None:
    missing = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    del missing["authorization"]
    unknown = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    unknown["repository"] = "owner/repo"
    nested_missing = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    del nested_missing["verification"]["method"]
    nested_unknown = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    nested_unknown["activation"]["credential"] = "external"

    assert validate_immutable_releases_policy(missing)
    assert validate_immutable_releases_policy(unknown)
    assert validate_immutable_releases_policy(nested_missing)
    assert validate_immutable_releases_policy(nested_unknown)


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        (
            '{"schema":"first","schema":"second"}\n',
            "duplicate JSON key",
        ),
        (
            '{"schema":"pheroos-github-immutable-releases-proposal-v1"}\n',
            "exact inert WP-13",
        ),
    ],
)
def test_repository_audit_rejects_malformed_immutable_release_proposals(
    tmp_path: Path,
    contents: str,
    expected: str,
) -> None:
    proposal = tmp_path / "immutable-releases-proposed.json"
    proposal.write_text(contents, encoding="utf-8")

    failures = audit_repository_policy(
        immutable_releases_policy_path=proposal,
    )

    assert any(expected in failure for failure in failures)


def test_repository_audit_rejects_noncanonical_immutable_release_proposal(
    tmp_path: Path,
) -> None:
    proposal = tmp_path / "immutable-releases-proposed.json"
    policy = load_policy(IMMUTABLE_RELEASES_POLICY_PATH)
    proposal.write_text(
        json.dumps(policy, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    failures = audit_repository_policy(
        immutable_releases_policy_path=proposal,
    )

    assert any("not canonical" in failure for failure in failures)


def test_repository_audit_rejects_nested_duplicate_policy_keys(
    tmp_path: Path,
) -> None:
    proposal = tmp_path / "immutable-releases-proposed.json"
    contents = IMMUTABLE_RELEASES_POLICY_PATH.read_text(encoding="utf-8").replace(
        '    "method": "PUT",',
        '    "method": "PUT",\n    "method": "POST",',
        1,
    )
    proposal.write_text(contents, encoding="utf-8")

    failures = audit_repository_policy(
        immutable_releases_policy_path=proposal,
    )

    assert any("duplicate JSON key: method" in failure for failure in failures)


@pytest.mark.parametrize(
    ("status_code", "payload", "allowed"),
    [
        (200, {"enabled": True}, True),
        (200, {"enabled": True, "enforced_by_owner": False}, True),
        (200, {"enabled": True, "enforced_by_owner": True}, True),
        (200, {"enabled": False}, False),
        (200, {"enabled": 1}, False),
        (200, {}, False),
        (200, [], False),
        (404, {}, False),
        (401, {}, False),
        (500, {"enabled": True}, False),
    ],
)
def test_immutable_releases_observation_fails_closed(
    status_code: int,
    payload: object,
    allowed: bool,
) -> None:
    failures = evaluate_immutable_releases_observation(
        status_code=status_code,
        payload=payload,
    )

    assert (failures == []) is allowed


def test_v_tag_policy_rejects_checked_in_remote_activation_or_bypass() -> None:
    active = load_policy(TAG_POLICY_PATH)
    active["enforcement"] = "active"
    bypassed = load_policy(TAG_POLICY_PATH)
    bypassed["bypass_actors"] = [{"actor_id": 1, "actor_type": "Team"}]

    assert any("enforcement" in failure for failure in validate_tag_policy(active))
    assert any("bypass_actors" in failure for failure in validate_tag_policy(bypassed))


def test_checked_in_policy_scenarios_prove_merge_and_denial_paths() -> None:
    policy = load_policy(POLICY_PATH)
    scenarios = load_scenarios(SCENARIOS_PATH)

    assert {case["id"] for case in scenarios} == {
        "delete-denied",
        "direct-push-denied",
        "force-push-denied",
        "gate-cancelled-denied",
        "gate-failure-denied",
        "gate-missing-denied",
        "gate-pending-denied",
        "gate-skipped-denied",
        "gate-wrong-integration-denied",
        "pull-request-gate-success",
    }
    for case in scenarios:
        failures = evaluate_repository_change(
            policy,
            operation=case["operation"],
            via_pull_request=case["via_pull_request"],
            status_checks=case["status_checks"],
        )
        assert (failures == []) is case["allowed"], case["id"]


def test_policy_accepts_a_pull_request_with_the_fixed_successful_gate() -> None:
    policy = load_policy(POLICY_PATH)

    errors = evaluate_repository_change(
        policy,
        operation="merge",
        via_pull_request=True,
        status_checks=_check("success"),
    )

    assert errors == []


@pytest.mark.parametrize("result", [None, "failure", "pending", "skipped", "cancelled"])
def test_policy_rejects_missing_or_non_successful_quality_gate(
    result: str | None,
) -> None:
    policy = load_policy(POLICY_PATH)
    checks = {} if result is None else _check(result)

    errors = evaluate_repository_change(
        policy,
        operation="merge",
        via_pull_request=True,
        status_checks=checks,
    )

    assert any("quality-gate" in error for error in errors)


def test_policy_rejects_direct_push_force_push_and_deletion() -> None:
    policy = load_policy(POLICY_PATH)

    direct = evaluate_repository_change(
        policy,
        operation="push",
        via_pull_request=False,
        status_checks={},
    )
    forced = evaluate_repository_change(
        policy,
        operation="force_push",
        via_pull_request=False,
        status_checks={},
    )
    deleted = evaluate_repository_change(
        policy,
        operation="delete",
        via_pull_request=False,
        status_checks={},
    )

    assert any("pull request" in error for error in direct)
    assert any("force-push" in error for error in forced)
    assert any("deletion" in error for error in deleted)


def test_policy_rejects_a_same_name_check_from_the_wrong_integration() -> None:
    policy = load_policy(POLICY_PATH)

    errors = evaluate_repository_change(
        policy,
        operation="merge",
        via_pull_request=True,
        status_checks=_check("success", integration_id=1),
    )

    assert any("integration" in error for error in errors)


def test_policy_keeps_single_maintainer_review_requirements_non_blocking() -> None:
    policy = load_policy(POLICY_PATH)
    rules = {rule["type"]: rule for rule in policy["rules"]}
    pull_request = rules["pull_request"]["parameters"]

    assert pull_request["required_approving_review_count"] == 0
    assert pull_request["require_code_owner_review"] is False
    assert pull_request["require_last_push_approval"] is False
    assert pull_request["required_review_thread_resolution"] is True


def test_required_check_is_an_api_compatible_strict_ruleset_rule() -> None:
    policy = load_policy(POLICY_PATH)
    rules = {rule["type"]: rule for rule in policy["rules"]}
    required = rules["required_status_checks"]

    assert required == {
        "parameters": {
            "do_not_enforce_on_create": False,
            "required_status_checks": [
                {
                    "context": "quality-gate",
                    "integration_id": GITHUB_ACTIONS_INTEGRATION_ID,
                }
            ],
            "strict_required_status_checks_policy": True,
        },
        "type": "required_status_checks",
    }


def test_codeowners_covers_the_entire_repository_without_enforcing_review() -> None:
    active_lines = [
        line.strip()
        for line in CODEOWNERS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert "* @Ju1se" in active_lines


def test_policy_validator_rejects_an_active_checked_in_payload() -> None:
    policy = load_policy(POLICY_PATH)
    policy["enforcement"] = "active"

    errors = evaluate_repository_change(
        policy,
        operation="merge",
        via_pull_request=True,
        status_checks=_check("success"),
    )

    assert any("disabled" in error for error in errors)
