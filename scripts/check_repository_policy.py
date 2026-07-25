#!/usr/bin/env python3
"""Offline validation for proposed GitHub repository governance policies."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / ".github" / "rulesets" / "main-proposed.json"
TAG_POLICY_PATH = ROOT / ".github" / "rulesets" / "tags-v-proposed.json"
REPOSITORY_SETTINGS_PATH = ROOT / ".github" / "repository-settings-proposed.json"
IMMUTABLE_RELEASES_POLICY_PATH = ROOT / ".github" / "immutable-releases-proposed.json"
CODEOWNERS_PATH = ROOT / ".github" / "CODEOWNERS"
SCENARIOS_PATH = (
    ROOT / "tests" / "fixtures" / "ci" / "repository-policy-scenarios-v1.json"
)
SCENARIO_SCHEMA = "pheroos-repository-policy-scenarios-v1"
IMMUTABLE_RELEASES_PROPOSAL_SCHEMA = "pheroos-github-immutable-releases-proposal-v1"
GITHUB_ACTIONS_INTEGRATION_ID = 15368


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise ValueError("repository policy must be a JSON object")
    return value


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict) or set(value) != {"cases", "schema"}:
        raise ValueError("repository policy scenarios must contain cases and schema")
    if value["schema"] != SCENARIO_SCHEMA:
        raise ValueError(
            f"repository policy scenario schema must be {SCENARIO_SCHEMA!r}"
        )
    cases = value["cases"]
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("repository policy cases must be a list of objects")
    expected_keys = {
        "allowed",
        "id",
        "operation",
        "status_checks",
        "via_pull_request",
    }
    identifiers: set[str] = set()
    for case in cases:
        _validate_scenario(case, expected_keys=expected_keys, identifiers=identifiers)
    return cases


def _validate_scenario(
    case: dict[str, Any],
    *,
    expected_keys: set[str],
    identifiers: set[str],
) -> None:
    if set(case) != expected_keys:
        raise ValueError("repository policy case keys differ from the v1 schema")
    identifier = case["id"]
    if not isinstance(identifier, str) or not identifier or identifier in identifiers:
        raise ValueError("repository policy case ids must be unique non-empty strings")
    identifiers.add(identifier)
    if case["operation"] not in {"merge", "push", "force_push", "delete"}:
        raise ValueError(f"unsupported repository policy operation in {identifier}")
    if not isinstance(case["via_pull_request"], bool) or not isinstance(
        case["allowed"], bool
    ):
        raise ValueError(f"repository policy case booleans are invalid in {identifier}")
    checks = case["status_checks"]
    if not isinstance(checks, dict):
        raise ValueError(f"repository policy status checks are invalid in {identifier}")
    for context, status in checks.items():
        _validate_scenario_status(identifier, context, status)


def _validate_scenario_status(
    identifier: str,
    context: object,
    status: object,
) -> None:
    if (
        not isinstance(context, str)
        or not isinstance(status, dict)
        or set(status) != {"integration_id", "result"}
        or type(status["integration_id"]) is not int
        or not isinstance(status["result"], str)
    ):
        raise ValueError(f"repository policy status checks are invalid in {identifier}")


def _keys_failure(
    value: object,
    expected: set[str],
    *,
    label: str,
) -> str | None:
    if not isinstance(value, dict):
        return f"{label} must be an object"
    observed = set(value)
    if observed != expected:
        return (
            f"{label} keys differ: missing={sorted(expected - observed)}, "
            f"unknown={sorted(observed - expected)}"
        )
    return None


def _matches_exact_json_contract(value: object, expected: object) -> bool:
    if isinstance(expected, dict):
        if not isinstance(value, Mapping) or set(value) != set(expected):
            return False
        return all(
            _matches_exact_json_contract(value[key], expected_item)
            for key, expected_item in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(value, list)
            and len(value) == len(expected)
            and all(
                _matches_exact_json_contract(item, expected_item)
                for item, expected_item in zip(value, expected, strict=True)
            )
        )
    return type(value) is type(expected) and value == expected


def _validate_policy_header(policy: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    top_failure = _keys_failure(
        policy,
        {"bypass_actors", "conditions", "enforcement", "name", "rules", "target"},
        label="policy",
    )
    if top_failure:
        failures.append(top_failure)
    if policy.get("name") != "main-protection":
        failures.append("policy name must be 'main-protection'")
    if policy.get("target") != "branch":
        failures.append("policy target must be the GitHub branch ruleset target")
    if policy.get("enforcement") != "disabled":
        failures.append(
            "checked-in ruleset payload must remain disabled until authorized activation"
        )
    if policy.get("bypass_actors") != []:
        failures.append("proposed main ruleset must not declare bypass actors")
    return failures


def _validate_policy_target(policy: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    conditions = policy.get("conditions")
    if conditions != {
        "ref_name": {
            "exclude": [],
            "include": ["refs/heads/main"],
        }
    }:
        failures.append(
            "policy conditions must select only refs/heads/main with no exclusions"
        )
    return failures


def _rule_map(policy: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    rules = policy.get("rules")
    if not isinstance(rules, list):
        return {}, ["policy.rules must be a GitHub ruleset rule array"]
    mapped: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            failures.append(f"policy.rules[{index}] must be an object")
            continue
        rule_type = rule.get("type")
        if not isinstance(rule_type, str) or not rule_type:
            failures.append(f"policy.rules[{index}].type must be a non-empty string")
            continue
        if rule_type in mapped:
            failures.append(f"duplicate policy rule type: {rule_type}")
        mapped[rule_type] = rule
    expected = {
        "deletion",
        "non_fast_forward",
        "pull_request",
        "required_status_checks",
    }
    if set(mapped) != expected:
        failures.append(
            "policy rule types differ: "
            f"missing={sorted(expected - set(mapped))}, "
            f"unknown={sorted(set(mapped) - expected)}"
        )
    return mapped, failures


def _validate_policy_rules(policy: Mapping[str, Any]) -> list[str]:
    rules, failures = _rule_map(policy)
    if failures:
        return failures

    if rules["deletion"] != {"type": "deletion"}:
        failures.append("deletion rule must be an API-compatible GitHub rule")
    if rules["non_fast_forward"] != {"type": "non_fast_forward"}:
        failures.append("non-fast-forward rule must be an API-compatible GitHub rule")
    if rules["pull_request"] != {
        "parameters": {
            "allowed_merge_methods": ["merge", "squash", "rebase"],
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_approving_review_count": 0,
            "required_review_thread_resolution": True,
        },
        "type": "pull_request",
    }:
        failures.append(
            "pull-request rule must require PR flow and resolved threads without "
            "locking a single maintainer"
        )
    if rules["required_status_checks"] != {
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
    }:
        failures.append(
            "required-status-check rule must contain only strict quality-gate"
        )
    return failures


def validate_policy(policy: Mapping[str, Any]) -> list[str]:
    failures = _validate_policy_header(policy)
    failures.extend(_validate_policy_target(policy))
    failures.extend(_validate_policy_rules(policy))
    return failures


def validate_tag_policy(policy: Mapping[str, Any]) -> list[str]:
    """Validate the disabled v* tag-immutability proposal for WP-11."""

    failures: list[str] = []
    top_failure = _keys_failure(
        policy,
        {"bypass_actors", "conditions", "enforcement", "name", "rules", "target"},
        label="tag policy",
    )
    if top_failure:
        failures.append(top_failure)
    expected_header = {
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "exclude": [],
                "include": ["refs/tags/v*"],
            }
        },
        "enforcement": "disabled",
        "name": "release-tag-immutability",
        "target": "tag",
    }
    for key, expected in expected_header.items():
        if policy.get(key) != expected:
            failures.append(f"tag policy {key} differs from the proposed contract")
    if policy.get("rules") != [
        {"type": "deletion"},
        {"type": "update"},
    ]:
        failures.append("tag policy must reject both deletion and update")
    return failures


def validate_repository_settings(settings: Mapping[str, Any]) -> list[str]:
    """Validate the exact API payload proposed for repository-level settings."""

    if not _matches_exact_json_contract(
        settings,
        {"delete_branch_on_merge": True},
    ):
        return ["repository settings proposal must enable only delete_branch_on_merge"]
    return []


def validate_immutable_releases_policy(
    policy: Mapping[str, Any],
) -> list[str]:
    """Validate the inert repository immutable-releases activation contract."""

    expected = {
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
    if not _matches_exact_json_contract(policy, expected):
        return [
            "immutable releases proposal must match the exact inert WP-13 "
            "activation and verification contract"
        ]
    return []


def evaluate_immutable_releases_observation(
    *,
    status_code: int,
    payload: object,
) -> list[str]:
    """Evaluate a read-only GitHub observation without performing activation."""

    if status_code == 404:
        return ["immutable releases are not enabled for the repository"]
    if status_code != 200:
        return [
            "immutable releases verification must return HTTP 200, "
            f"observed {status_code}"
        ]
    if not isinstance(payload, Mapping) or payload.get("enabled") is not True:
        return ["immutable releases verification must report enabled=true"]
    return []


def evaluate_repository_change(
    policy: Mapping[str, Any],
    *,
    operation: str,
    via_pull_request: bool,
    status_checks: Mapping[str, object],
) -> list[str]:
    """Evaluate local policy scenarios without claiming GitHub enforcement."""

    failures = validate_policy(policy)
    if failures:
        return [f"invalid repository policy: {failure}" for failure in failures]
    rules, rule_failures = _rule_map(policy)
    if rule_failures:
        return [f"invalid repository policy: {failure}" for failure in rule_failures]
    if operation == "delete" and "deletion" in rules:
        return ["branch deletion is forbidden"]
    if operation == "force_push" and "non_fast_forward" in rules:
        return ["force-push is forbidden"]
    if operation not in {"merge", "push", "force_push", "delete"}:
        return [f"unsupported repository operation: {operation!r}"]
    if not via_pull_request and "pull_request" in rules:
        return ["changes to main must arrive through a pull request"]

    required_checks = rules["required_status_checks"]["parameters"][
        "required_status_checks"
    ]
    for required in required_checks:
        context = required["context"]
        status = status_checks.get(context)
        result = status.get("result") if isinstance(status, Mapping) else None
        if result != "success":
            failures.append(
                f"required status check {context!r} must be success, observed {result!r}"
            )
        expected_integration = required.get("integration_id")
        observed_integration = (
            status.get("integration_id") if isinstance(status, Mapping) else None
        )
        if observed_integration != expected_integration:
            failures.append(
                f"required status check {context!r} must originate from integration "
                f"{expected_integration}, observed {observed_integration!r}"
            )
    return failures


def _canonical_policy_failures(
    policy: dict[str, Any],
    policy_path: Path,
) -> list[str]:
    canonical = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    if policy_path.read_text(encoding="utf-8") == canonical:
        return []
    return ["proposed repository policy JSON is not canonical"]


def _tag_policy_failures(tag_policy_path: Path) -> list[str]:
    try:
        policy = load_policy(tag_policy_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load proposed tag policy: {error}"]
    failures = validate_tag_policy(policy)
    canonical = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    if tag_policy_path.read_text(encoding="utf-8") != canonical:
        failures.append("proposed tag policy JSON is not canonical")
    return failures


def _repository_settings_failures(settings_path: Path) -> list[str]:
    try:
        settings = load_policy(settings_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load proposed repository settings: {error}"]
    failures = validate_repository_settings(settings)
    canonical = json.dumps(settings, indent=2, sort_keys=True) + "\n"
    if settings_path.read_text(encoding="utf-8") != canonical:
        failures.append("proposed repository settings JSON is not canonical")
    return failures


def _immutable_releases_policy_failures(policy_path: Path) -> list[str]:
    try:
        policy = load_policy(policy_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load proposed immutable releases policy: {error}"]
    failures = validate_immutable_releases_policy(policy)
    canonical = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    if policy_path.read_text(encoding="utf-8") != canonical:
        failures.append("proposed immutable releases policy JSON is not canonical")
    return failures


def _codeowners_failures(codeowners_path: Path) -> list[str]:
    try:
        codeowners = codeowners_path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"cannot load CODEOWNERS: {error}"]
    active_lines = {
        line.strip()
        for line in codeowners.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if "* @Ju1se" in active_lines:
        return []
    return ["CODEOWNERS must cover the complete repository with * @Ju1se"]


def _scenario_failures(
    policy: Mapping[str, Any],
    scenarios_path: Path,
) -> list[str]:
    failures: list[str] = []
    try:
        scenarios = load_scenarios(scenarios_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load repository policy scenarios: {error}"]
    scenario_payload = {
        "cases": scenarios,
        "schema": SCENARIO_SCHEMA,
    }
    canonical_scenarios = (
        json.dumps(
            scenario_payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if scenarios_path.read_text(encoding="utf-8") != canonical_scenarios:
        failures.append("repository policy scenario JSON is not canonical")
    for case in scenarios:
        observed = evaluate_repository_change(
            policy,
            operation=case["operation"],
            via_pull_request=case["via_pull_request"],
            status_checks=case["status_checks"],
        )
        if (observed == []) is not case["allowed"]:
            failures.append(
                f"repository policy scenario {case['id']!r} has the wrong decision"
            )
    return failures


def audit_repository_policy(
    policy_path: Path = POLICY_PATH,
    codeowners_path: Path = CODEOWNERS_PATH,
    scenarios_path: Path = SCENARIOS_PATH,
    tag_policy_path: Path = TAG_POLICY_PATH,
    settings_path: Path = REPOSITORY_SETTINGS_PATH,
    immutable_releases_policy_path: Path = IMMUTABLE_RELEASES_POLICY_PATH,
) -> list[str]:
    try:
        policy = load_policy(policy_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load proposed repository policy: {error}"]
    failures = validate_policy(policy)
    failures.extend(_canonical_policy_failures(policy, policy_path))
    failures.extend(_codeowners_failures(codeowners_path))
    failures.extend(_scenario_failures(policy, scenarios_path))
    failures.extend(_tag_policy_failures(tag_policy_path))
    failures.extend(_repository_settings_failures(settings_path))
    failures.extend(_immutable_releases_policy_failures(immutable_releases_policy_path))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = audit_repository_policy()
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1 if args.check else 0
    print("proposed repository policy verified (not active)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
