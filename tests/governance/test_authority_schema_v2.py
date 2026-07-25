from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import pytest

from pheroos.governance.authority_schema_v2 import (
    AUTHORITY_SCHEMA_V2,
    AUTHORITY_SCHEMA_V2_ID,
    AuthorityWireValidationCodeV2,
    AuthorityWireValidationErrorV2,
    authority_schema_v2,
    loads_authority_wire_record_v2,
    read_authority_wire_record_v2,
    validate_authority_wire_record_v2,
)
from pheroos.governance.authority_session_v2 import (
    GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
    GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
    GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
    ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_DOMAIN_SCHEMA_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
    GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
    GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
    GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
    GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
    GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
    GOVERNANCE_FAILURE_SCHEMA_V2,
    GOVERNANCE_HEAD_SCHEMA_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
    AuthorityDomainV2,
    GovernanceHeadV2,
)
from pheroos.governance.baseline_output_v2 import (
    ACTION_PERMISSION_SCHEMA_V2,
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
    BASELINE_OUTPUT_RESULT_SCHEMA_V2,
    BaselineOutputRequestV2,
)
from pheroos.protocol.authority_manifest_v2 import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.authority_schema_v2 import (
    PROTOCOL_SCHEMA_V3_ID,
    protocol_schema_v3,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "schemas" / "authority-v2.schema.json"


def _root(character: str) -> str:
    return f"sha256:{character * 64}"


def _domain() -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:authority-schema-v2",
    )


def _grant(domain: AuthorityDomainV2) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:authority-schema-v2",
        grant_ref="grant:authority-schema-v2",
        grant_binding_ref=_root("1"),
        operations=(GovernanceIssuerOperationV2.VERIFY_SIGNAL,),
        target_refs=("target:answer",),
        action_refs=("action:publish",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=9,
        revocation_generation=0,
    )


def _baseline_request(domain: AuthorityDomainV2) -> BaselineOutputRequestV2:
    manifest = scoped_protocol_manifest_v2_from_dict(
        {
            "protocol_version": PROTOCOL_VERSION_V2,
            "id": "protocol:authority-schema-v2",
            "targets": [
                {
                    "id": "target:answer",
                    "description": "Provider-free schema parity target.",
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
                "commit_threshold": 1,
            },
            "authority_policy": {
                "policy_version": AUTHORITY_POLICY_VERSION_V2,
                "profile": AUTHORITY_LOCAL_PROFILE_V2,
                "wire_version": AUTHORITY_WIRE_VERSION_V2,
                "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
                "ledger_version": AUTHORITY_LEDGER_VERSION_V2,
                "state_store_version": GOVERNANCE_STATE_STORE_VERSION_V2,
                "trace_batch_version": GOVERNANCE_TRACE_BATCH_VERSION_V2,
                "read_set_version": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
            },
            "recovery_protocols": [],
            "evidence_policy": {
                "require_provenance": True,
                "allow_agent_fact_creation": False,
            },
            "output_policy": {
                "policy_version": BASELINE_OUTPUT_POLICY_VERSION_V2,
                "decision_mode": "direct_governance",
                "actions": [
                    {
                        "action_ref": "action:publish",
                        "effect": "publish",
                        "target": "target:answer",
                        "allowed_outcomes": [
                            "evidence_commit",
                            "safe_fallback",
                        ],
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
    return BaselineOutputRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref="run:authority-schema-v2",
        request_ref="request:authority-schema-v2",
        output_transition_id="transition:authority-schema-v2",
        manifest=manifest,
        target_ref="target:answer",
        action_ref="action:publish",
        proposed_candidate_ref="candidate:accept",
        verified_signals=(),
        stop_resolutions=(
            {
                "action_ref": "action:publish",
                "blocked": False,
                "provenance_ref": _root("2"),
                "reason_ref": "reason:clear",
            },
        ),
        output_payload={"answer": "deterministic"},
        observed_epoch=2,
    )


def _rendered(factory_value: object) -> bytes:
    return (json.dumps(factory_value, indent=2, sort_keys=True) + "\n").encode()


def test_authority_schema_id_selector_and_checked_artifact_are_exact() -> None:
    schema = authority_schema_v2()

    Draft202012Validator.check_schema(schema)
    assert AUTHORITY_SCHEMA_V2 == "pheroos-authority-schema-v2"
    assert AUTHORITY_SCHEMA_V2_ID == (
        "https://pheroos.dev/schemas/authority-v2.schema.json"
    )
    assert schema["$id"] == AUTHORITY_SCHEMA_V2_ID
    assert ARTIFACT.read_bytes() == _rendered(schema)


def test_union_covers_every_current_portable_state_session_and_output_record() -> None:
    expected = {
        GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        AUTHORITY_DOMAIN_SCHEMA_V2,
        GOVERNANCE_HEAD_SCHEMA_V2,
        PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2,
        GOVERNANCE_TRACE_BATCH_VERSION_V2,
        GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
        GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
        GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
        GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
        GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
        GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
        GOVERNANCE_FAILURE_SCHEMA_V2,
        GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
        GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
        GOVERNANCE_ISSUER_GRANT_SCHEMA_V2,
        ISSUER_GRANT_VERIFICATION_SCHEMA_V2,
        GOVERNANCE_VERIFIED_SIGNAL_REQUEST_SCHEMA_V2,
        GOVERNANCE_DOMAIN_RETIREMENT_REQUEST_SCHEMA_V2,
        BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
        ACTION_PERMISSION_SCHEMA_V2,
        BASELINE_OUTPUT_RESULT_SCHEMA_V2,
    }
    schema = authority_schema_v2()
    observed = {
        definition["properties"]["schema"]["const"]
        for definition in schema["$defs"].values()
        if isinstance(definition, dict)
        and isinstance(definition.get("properties"), dict)
        and "schema" in definition["properties"]
    }

    assert observed == expected
    assert len(schema["oneOf"]) == len(expected) == 21
    for definition in schema["$defs"].values():
        if not isinstance(definition, dict) or definition.get("type") != "object":
            continue
        if "properties" in definition and "required" in definition:
            assert set(definition["required"]) == set(definition["properties"])
            assert definition["additionalProperties"] is False


def test_typed_reader_round_trips_records_from_each_implemented_owner() -> None:
    domain = _domain()
    grant = _grant(domain)
    request = _baseline_request(domain)

    assert read_authority_wire_record_v2(domain.to_dict()) == domain
    assert read_authority_wire_record_v2(grant.to_dict()) == grant
    assert read_authority_wire_record_v2(request.to_dict()) == request
    validate_authority_wire_record_v2(domain.to_dict())
    assert loads_authority_wire_record_v2(domain.canonical_bytes()) == domain

    registry = Registry().with_resource(
        PROTOCOL_SCHEMA_V3_ID,
        Resource.from_contents(protocol_schema_v3()),
    )
    validator = Draft202012Validator(authority_schema_v2(), registry=registry)
    assert validator.is_valid(request.to_dict()) is True


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: {key: item for key, item in value.items() if key != "schema"},
            AuthorityWireValidationCodeV2.SCHEMA_MISSING,
        ),
        (
            lambda value: {**value, "schema": "pheroos-authority-wire-v999"},
            AuthorityWireValidationCodeV2.SCHEMA_UNSUPPORTED,
        ),
        (
            lambda value: {**value, "unexpected": True},
            AuthorityWireValidationCodeV2.RECORD_INVALID,
        ),
    ],
)
def test_reader_fails_closed_on_missing_unknown_or_extended_discriminated_records(
    mutation,
    code: AuthorityWireValidationCodeV2,
) -> None:
    with pytest.raises(AuthorityWireValidationErrorV2) as captured:
        read_authority_wire_record_v2(mutation(_domain().to_dict()))

    assert captured.value.code is code


def test_json_schema_and_typed_reader_agree_on_structural_negative_corpus() -> None:
    domain = _domain()
    head = GovernanceHeadV2.genesis(domain, "stream:authority-schema-v2")
    schema = authority_schema_v2()
    validator = Draft202012Validator(schema)
    cases = []

    missing = deepcopy(domain.to_dict())
    missing.pop("scope_ref")
    cases.append(missing)
    cases.append({**domain.to_dict(), "unknown": "field"})
    cases.append({**domain.to_dict(), "schema": "pheroos-authority-wire-v999"})
    cases.append({**head.to_dict(), "revision": True})
    cases.append({**head.to_dict(), "revision": float("nan")})

    for payload in cases:
        assert validator.is_valid(payload) is False
        with pytest.raises(AuthorityWireValidationErrorV2):
            read_authority_wire_record_v2(payload)


def test_strict_json_loader_rejects_duplicate_keys_nonfinite_and_bom() -> None:
    wire = json.dumps(_domain().to_dict(), sort_keys=True)
    duplicate = wire[:-1] + ',"schema":"pheroos-governance-authority-domain-v2"}'
    nonfinite = wire.replace('"scope_ref":', '"extra_number":NaN,"scope_ref":')

    for value in (
        duplicate,
        nonfinite,
        "\ufeff" + wire,
        b"\xef\xbb\xbf" + wire.encode(),
    ):
        with pytest.raises(AuthorityWireValidationErrorV2) as captured:
            loads_authority_wire_record_v2(value)
        assert captured.value.code is AuthorityWireValidationCodeV2.INVALID_JSON


def test_factory_and_artifact_are_deterministic_from_an_external_cwd(
    tmp_path: Path,
) -> None:
    code = """
import hashlib, json
from pheroos.governance.authority_schema_v2 import authority_schema_v2
raw=(json.dumps(authority_schema_v2(),indent=2,sort_keys=True)+'\\n').encode()
print(hashlib.sha256(raw).hexdigest())
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == sha256(ARTIFACT.read_bytes()).hexdigest()
