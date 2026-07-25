from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from pheroos.conformance.runtime_integration import (
    build_runtime_integration_request_v1,
)
from pheroos.conformance.schema_catalog import validate_schema_wire
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import (
    CommitAssurance,
    commit_replay_state_payload,
    initialize_commit_replay_state,
)
from pheroos.protocol import canonical_commit_payload
from pheroos.protocol.loader import (
    parse_finite_json_float,
    reject_duplicate_json_object_keys,
    reject_non_finite_json_constant,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads(
    (ROOT / "tests/fixtures/schema-parity-v1/cases.json").read_text(encoding="utf-8")
)


def _strict_json(raw: str) -> object:
    return json.loads(
        raw,
        parse_constant=reject_non_finite_json_constant,
        parse_float=parse_finite_json_float,
        object_pairs_hook=reject_duplicate_json_object_keys,
    )


def _capability() -> dict[str, Any]:
    return build_runtime_integration_request_v1(
        "schema-parity-capability"
    ).capability.to_dict()


def _commit_record() -> dict[str, Any]:
    state = initialize_commit_replay_state(
        profile="pheroos-certified-commit-v1",
        assurance=CommitAssurance.CERTIFIED,
        manifest_root="sha256:" + "1" * 64,
        commit_policy_root="sha256:" + "2" * 64,
        protocol_id="protocol:schema-parity",
        run_id="run:schema-parity",
        current_step=0,
        issuer_id="governance:schema-parity",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:schema-parity",
        trace_event_id="trace:schema-parity",
    )
    return json.loads(
        canonical_commit_payload(
            commit_replay_state_payload(state),
            schema="pheroos-commit-replay-state-v1",
            profile=state.profile,
        )
    )


def _case_payload(case_id: str) -> tuple[str, object]:
    if case_id == "duplicate-json-key":
        return (
            "runtime-scope-v1",
            '{"scope_version":"v","scope_version":"v2"}',
        )
    if case_id == "raw-nonfinite-number":
        return ("runtime-scope-v1", '{"value":NaN}')
    if case_id in {
        "required-field-removal",
        "unknown-critical-field",
        "wrong-discriminator",
        "wrong-container-type",
        "bool-as-integer",
    }:
        return ("capability-v3", _capability_case_payload(case_id))
    if case_id in {
        "fingerprint-mutation",
        "critical-extension",
        "noncritical-extension",
    }:
        return ("commit", _commit_case_payload(case_id))
    raise AssertionError(case_id)


def _capability_case_payload(case_id: str) -> dict[str, Any]:
    payload = _capability()
    if case_id == "required-field-removal":
        del payload["protocol"]
    elif case_id == "unknown-critical-field":
        payload["authority_override"] = True
    elif case_id == "wrong-discriminator":
        payload["protocol"]["protocol_version"] = "pheroos.protocol.v1"
    elif case_id == "wrong-container-type":
        payload["drivers"] = {}
    elif case_id == "bool-as-integer":
        payload["protocol"]["quorum_policy"]["commit_threshold"] = True
    return payload


def _commit_case_payload(case_id: str) -> dict[str, Any]:
    payload = _commit_record()
    if case_id == "fingerprint-mutation":
        payload["payload"]["receipt_root"] = "sha256:" + "f" * 64
    elif case_id == "critical-extension":
        payload["authority_override"] = True
    elif case_id == "noncritical-extension":
        payload["x-schema-parity"] = {"source": "test"}
    return payload


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda item: item["id"])
def test_schema_parity_corpus_rejects_at_the_declared_layer(
    case: dict[str, object],
) -> None:
    case_id = str(case["id"])
    surface, candidate = _case_payload(case_id)
    assert surface == case["surface"]
    if case["expected_layer"] == "strict_loader":
        assert isinstance(candidate, str)
        with pytest.raises(ValueError):
            _strict_json(candidate)
        return

    payload = deepcopy(candidate)
    if case["accepted"]:
        validate_schema_wire(surface, payload, f"case:{case_id}")
        return
    with pytest.raises((TypeError, ValueError)):
        validate_schema_wire(surface, payload, f"case:{case_id}")


def test_duplicate_keys_are_loader_owned_not_json_schema_claims() -> None:
    raw = '{"scope_version":"v1","scope_version":"v2"}'
    ordinary_parser_value = json.loads(raw)

    assert ordinary_parser_value == {"scope_version": "v2"}
    with pytest.raises(ValueError, match="duplicate"):
        _strict_json(raw)
