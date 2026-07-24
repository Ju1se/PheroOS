from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import inspect

import pytest

from pheroos.governance._baseline_output_v2.contracts import (
    ACTION_PERMISSION_SCHEMA_V2,
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputRequestV2,
    BaselineOutputTerminalStatusV2,
)
from pheroos.governance._baseline_output_v2.operations import (
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
)
from pheroos.protocol.authority_manifest_v2 import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    ScopedProtocolManifestV2,
    scoped_protocol_manifest_v2_from_dict,
)


def _root(digit: str) -> str:
    return f"sha256:{digit * 64}"


def _manifest(
    *,
    decision_mode: str = "direct_governance",
    threshold: int = 2,
    allowed_outcomes: tuple[str, ...] = ("evidence_commit", "safe_fallback"),
    authority_profile: str = "pheroos-scoped-authority-local-v2",
) -> ScopedProtocolManifestV2:
    return scoped_protocol_manifest_v2_from_dict(
        {
            "protocol_version": PROTOCOL_VERSION_V2,
            "id": "protocol:baseline-output-contract",
            "targets": [
                {
                    "id": "target:answer",
                    "description": "Provider-free baseline output target.",
                }
            ],
            "signals": [],
            "candidates": [
                {
                    "id": "candidate:accept",
                    "target": "target:answer",
                    "label": "Accept",
                },
                {
                    "id": "candidate:fallback",
                    "target": "target:answer",
                    "label": "Fallback",
                    "safe_fallback": True,
                },
            ],
            "quorum_policy": {
                "target": "target:answer",
                "fallback_candidate": "candidate:fallback",
                "commit_threshold": threshold,
            },
            "authority_policy": {
                "policy_version": "pheroos-scoped-authority-policy-v2",
                "profile": authority_profile,
                "wire_version": "pheroos-authority-wire-v2",
                "canonical_version": "pheroos-authority-canonical-v2",
                "ledger_version": "pheroos-governance-authority-ledger-v2",
                "state_store_version": "pheroos-governance-state-store-v2",
                "trace_batch_version": "pheroos-governance-trace-batch-v2",
                "read_set_version": "pheroos-governance-authority-read-set-v2",
            },
            "recovery_protocols": [],
            "evidence_policy": {
                "require_provenance": True,
                "allow_agent_fact_creation": False,
            },
            "output_policy": {
                "policy_version": BASELINE_OUTPUT_POLICY_VERSION_V2,
                "decision_mode": decision_mode,
                "actions": [
                    {
                        "action_ref": "action:publish",
                        "effect": "publish",
                        "target": "target:answer",
                        "allowed_outcomes": list(allowed_outcomes),
                    }
                ],
            },
            "trace_policy": {
                "required_events": [
                    "baseline_action_permission_issued",
                    "baseline_decision_evaluated",
                    "baseline_evidence_qualified",
                    "baseline_manifest_activated",
                    "baseline_output_committed",
                    "baseline_stop_resolved",
                ]
            },
        }
    )


def _request(**changes: object) -> BaselineOutputRequestV2:
    values: dict[str, object] = {
        "domain_root": _root("a"),
        "scope_ref": "scope:baseline-output-contract",
        "run_ref": "run:one",
        "request_ref": "request:one",
        "output_transition_id": "transition:output:one",
        "manifest": _manifest(),
        "target_ref": "target:answer",
        "action_ref": "action:publish",
        "proposed_candidate_ref": "candidate:accept",
        "verified_signals": (),
        "stop_resolutions": (
            {
                "action_ref": "action:publish",
                "blocked": False,
                "provenance_ref": _root("b"),
                "reason_ref": "reason:clear",
            },
        ),
        "output_payload": {"answer": "deterministic"},
        "observed_epoch": 2,
    }
    values.update(changes)
    return BaselineOutputRequestV2(**values)  # type: ignore[arg-type]


def _permission(request: BaselineOutputRequestV2) -> ActionPermissionV2:
    return ActionPermissionV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        permission_transition_id=request.permission_transition_id,
        permission_stream_ref=request.permission_stream_ref,
        manifest_root=request.manifest.manifest_root,
        output_policy_root=request.output_policy_root,
        evidence_root=_root("c"),
        stop_root=_root("d"),
        decision_root=_root("e"),
        target_ref=request.target_ref,
        candidate_ref="candidate:accept",
        action_ref=request.action_ref,
        effect="publish",
        terminal_status=BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
        output_payload_root=request.output_payload_root,
        disposition=ActionPermissionDispositionV2.AUTHORIZED,
        issued_epoch=2,
        expires_at_epoch=3,
        grant_ref="grant:issuer",
        grant_root=_root("f"),
        grant_binding_ref=_root("1"),
    )


def test_request_is_exact_frozen_canonical_and_round_trips() -> None:
    request = _request()

    assert request.schema == BASELINE_OUTPUT_REQUEST_SCHEMA_V2
    assert request.root() == request.request_root
    assert (
        request.canonical_bytes()
        == BaselineOutputRequestV2.from_dict(request.to_dict()).canonical_bytes()
    )
    assert BaselineOutputRequestV2.from_dict(request.to_dict()) == request
    assert not hasattr(request, "__dict__")
    with pytest.raises(FrozenInstanceError):
        request.request_ref = "request:changed"  # type: ignore[misc]


def test_request_rejects_in_memory_manifest_decision_mode_corruption() -> None:
    manifest = _manifest()
    object.__setattr__(manifest.output_policy, "decision_mode", "unsupported")

    with pytest.raises(ValueError, match="decision mode is unsupported"):
        _request(manifest=manifest)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("request_root", _root("9")),
        ("output_payload_root", _root("8")),
        ("manifest_stream_ref", "authority:substituted"),
        ("evidence_stream_ref", "authority:substituted"),
        ("permission_stream_ref", "authority:substituted"),
        ("output_stream_ref", "authority:substituted"),
    ],
)
def test_request_reader_rejects_derived_root_or_stream_substitution(
    field_name: str,
    replacement: str,
) -> None:
    wire = _request().to_dict()

    with pytest.raises(ValueError, match="mismatch"):
        BaselineOutputRequestV2.from_dict({**wire, field_name: replacement})


@pytest.mark.parametrize(
    "injected", ["publication_permission", "allowed", "decision", "permission"]
)
def test_request_reader_rejects_caller_authority_substitutes(injected: str) -> None:
    wire = _request().to_dict()

    with pytest.raises(ValueError, match="fields"):
        BaselineOutputRequestV2.from_dict({**wire, injected: True})


def test_request_reader_requires_exact_wire_container_shapes() -> None:
    wire = _request().to_dict()
    missing = dict(wire)
    missing.pop("output_payload")

    with pytest.raises(ValueError, match="fields"):
        BaselineOutputRequestV2.from_dict(missing)
    with pytest.raises(TypeError, match="wire value must be an array"):
        BaselineOutputRequestV2.from_dict({**wire, "verified_signals": ()})
    with pytest.raises(TypeError, match="entries must be exact objects"):
        BaselineOutputRequestV2.from_dict(
            {**wire, "stop_resolutions": [dict(wire["stop_resolutions"][0]), object()]}
        )


def test_action_permission_is_portable_but_not_a_caller_input() -> None:
    request = _request()
    permission = _permission(request)

    assert permission.schema == ACTION_PERMISSION_SCHEMA_V2
    assert permission.root() == permission.permission_root
    assert ActionPermissionV2.from_dict(permission.to_dict()) == permission
    assert (
        ActionPermissionV2.from_dict(permission.to_dict()).canonical_bytes()
        == permission.canonical_bytes()
    )
    with pytest.raises(ValueError, match="mismatched"):
        ActionPermissionV2.from_dict(
            {**permission.to_dict(), "permission_root": _root("7")}
        )


def test_v2_operation_signatures_expose_no_boolean_permission_or_decision_lane() -> (
    None
):
    request = _request()
    request_fields = {item.name for item in fields(BaselineOutputRequestV2)}
    issue = inspect.signature(issue_action_permission_v2)
    commit = inspect.signature(evaluate_and_commit_baseline_output_v2)

    assert request_fields.isdisjoint(
        {"publication_permission", "allowed", "permission", "decision"}
    )
    assert tuple(issue.parameters) == ("request", "authority_session")
    assert issue.parameters["authority_session"].kind is inspect.Parameter.KEYWORD_ONLY
    assert tuple(commit.parameters) == ("request", "authority_session")
    assert commit.parameters["authority_session"].kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        issue_action_permission_v2(request, _permission(request))  # type: ignore[misc]
    with pytest.raises(TypeError):
        issue_action_permission_v2(request, permission=True)  # type: ignore[call-arg]
