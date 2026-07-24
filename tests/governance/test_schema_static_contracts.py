from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from pheroos.governance import schema as public_schema
from pheroos.governance._schema import (
    COMMIT_WIRE_CONTRACTS,
    COMMIT_WIRE_CONTRACTS_BY_SCHEMA,
)
from pheroos.governance._schema.common import CommitWireContract
from pheroos.protocol.commit_wire import canonical_commit_payload


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PROFILE = "pheroos-commit-authority-v1"


def _principal_attestation_record() -> dict[str, object]:
    payload = {
        "attestation_ref": "attestation:principal:a",
        "expires_at_step": 20,
        "issued_at_step": 10,
        "issuer_id": "issuer:a",
        "method": "deterministic-test",
        "nonce": "nonce:a",
        "principal_id": "principal:a",
        "provenance": "urn:test:principal:a",
        "trace_event_id": "trace:principal:a",
    }
    return json.loads(
        canonical_commit_payload(
            payload,
            schema="pheroos-principal-attestation-v1",
            profile=AUTHORITY_PROFILE,
        )
    )


def test_static_contract_registry_covers_every_wire_branch_exactly_once() -> None:
    names = tuple(contract.schema_name for contract in COMMIT_WIRE_CONTRACTS)
    schema_names = tuple(
        branch["properties"]["schema"]["const"]
        for branch in public_schema.commit_schema()["oneOf"]
    )

    assert isinstance(COMMIT_WIRE_CONTRACTS, tuple)
    assert len(COMMIT_WIRE_CONTRACTS) == 51
    assert len(names) == len(set(names))
    assert names == schema_names
    assert isinstance(COMMIT_WIRE_CONTRACTS_BY_SCHEMA, MappingProxyType)
    assert tuple(COMMIT_WIRE_CONTRACTS_BY_SCHEMA) == names
    assert all(
        isinstance(contract, CommitWireContract) for contract in COMMIT_WIRE_CONTRACTS
    )
    assert all(callable(contract.payload_schema) for contract in COMMIT_WIRE_CONTRACTS)
    assert all(callable(contract.validator) for contract in COMMIT_WIRE_CONTRACTS)
    assert all(
        not hasattr(contract, "validators") for contract in COMMIT_WIRE_CONTRACTS
    )

    with pytest.raises(TypeError):
        COMMIT_WIRE_CONTRACTS_BY_SCHEMA["forged"] = COMMIT_WIRE_CONTRACTS[0]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        COMMIT_WIRE_CONTRACTS[0].schema_name = "forged"  # type: ignore[misc]


def test_static_contract_schema_is_byte_identical_to_checked_in_v1_artifact() -> None:
    rendered = (
        json.dumps(
            public_schema.commit_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    assert (
        rendered.encode("utf-8") == (ROOT / "schemas/commit.schema.json").read_bytes()
    )


def test_noncritical_extension_round_trips_without_entering_authority_dispatch() -> (
    None
):
    baseline = _principal_attestation_record()
    extended = {
        **baseline,
        "ext.acme.note": {
            "provider_hint": "informational-only",
            "score": 0.25,
        },
    }

    assert public_schema.validate_commit_wire_record(baseline) == []
    assert public_schema.validate_commit_wire_record(extended) == []
    assert extended["payload"] == baseline["payload"]
    assert "ext.acme.note" not in COMMIT_WIRE_CONTRACTS_BY_SCHEMA

    critical = {**baseline, "ext.critical.commit": {"authorized": True}}
    assert public_schema.validate_commit_wire_record(critical)


def test_public_owner_and_call_signatures_remain_stable() -> None:
    assert public_schema.commit_schema.__module__ == "pheroos.governance.schema"
    assert public_schema.validate_commit_wire_record.__module__ == (
        "pheroos.governance.schema"
    )
    assert str(inspect.signature(public_schema.commit_schema)) == (
        "() -> 'dict[str, Any]'"
    )
    assert str(inspect.signature(public_schema.validate_commit_wire_record)) == (
        "(record: 'object') -> 'list[str]'"
    )
