from __future__ import annotations

from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

import pytest

import pheroos.governance as governance
from pheroos.governance._public_api import (
    PUBLIC_API,
    PUBLIC_API_ORDER_SHA256,
)


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PUBLIC_API_COUNT = 911
EXPECTED_PUBLIC_API_ORDER_SHA256 = (
    "bc2cf49d2b6e68807ecddc3eef11491e0299b5157859ae999c781305c8eb51c4"
)
REMOVED_PRE_ACTIVATION_EXPORT = "commit_replay_receipt_v2_from_v1"
V2_FACADES = (
    "authority_store_v2",
    "authority_session_v2",
    "baseline_output_v2",
    "hybrid_replay_v2",
    "commit_state_v2",
    "risk_v2",
    "support_v2",
    "commit_gate_v2",
    "commit_evidence_v2",
    "commit_certificate_v2",
    "commit_decision_v2",
    "distributed_commit_v2",
    "commit_finality_v2",
)
V2_CONTRACTS = (
    "authority_store_v2_contract",
    "authority_session_v2_contract",
    "baseline_output_v2_contract",
    "hybrid_replay_v2_contract",
    "commit_replay_v2_contract",
    "risk_v2_contract",
    "support_v2_contract",
    "commit_gate_v2_contract",
    "commit_evidence_v2_contract",
    "commit_certificate_v2_contract",
    "commit_decision_v2_contract",
    "distributed_commit_v2_contract",
    "commit_finality_v2_contract",
)
REGISTRY_MODULE = "pheroos.governance._legacy.authority_registry"


def _v2_public_names() -> tuple[str, ...]:
    result: list[str] = []
    for facade_name in V2_FACADES:
        facade = import_module(f"pheroos.governance.{facade_name}")
        for name in facade.__all__:
            if name not in result:
                result.append(name)
    return tuple(result)


def _run_child(source: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def test_wp05_governance_aggregate_has_frozen_order_and_complete_v2_identity() -> None:
    names = _v2_public_names()

    assert tuple(governance.__all__) == tuple(PUBLIC_API)
    assert len(PUBLIC_API) == len(set(PUBLIC_API)) == EXPECTED_PUBLIC_API_COUNT
    assert PUBLIC_API_ORDER_SHA256 == EXPECTED_PUBLIC_API_ORDER_SHA256
    assert sha256("\n".join(PUBLIC_API).encode()).hexdigest() == (
        EXPECTED_PUBLIC_API_ORDER_SHA256
    )
    assert len(names) == len(set(names)) == 543
    assert governance.recover_baseline_output_result_v2 is (
        import_module(
            "pheroos.governance.baseline_output_v2"
        ).recover_baseline_output_result_v2
    )
    for facade_name in V2_FACADES:
        facade = import_module(f"pheroos.governance.{facade_name}")
        for name in facade.__all__:
            assert getattr(governance, name) is getattr(facade, name)
            binding_owner, _ = PUBLIC_API[name]
            assert not any(
                part.startswith("_") for part in binding_owner.split(".")[2:]
            )


def test_wp05_v2_facades_contracts_and_tck_are_registry_free_in_a_fresh_process() -> (
    None
):
    result = _run_child(
        f"""
import importlib
import json
import sys

import pheroos.governance as governance

facades = {V2_FACADES!r}
contracts = {V2_CONTRACTS!r}
names = []
for facade_name in facades:
    facade = importlib.import_module("pheroos.governance." + facade_name)
    for name in facade.__all__:
        if name not in names:
            names.append(name)
        assert getattr(governance, name) is getattr(facade, name)
for contract_name in contracts:
    importlib.import_module("pheroos.conformance.checks." + contract_name)
importlib.import_module("pheroos.conformance.commit_tck_v2")
print(json.dumps({{
    "facade_count": len(facades),
    "contract_count": len(contracts),
    "name_count": len(names),
    "registry_loaded": {REGISTRY_MODULE!r} in sys.modules,
}}))
"""
    )

    assert result == {
        "facade_count": 13,
        "contract_count": 13,
        "name_count": 543,
        "registry_loaded": False,
    }


def test_wp05_shared_vocabulary_uses_registry_free_root_bindings() -> None:
    result = _run_child(
        f"""
import json
import sys
import pheroos.governance as governance

names = (
    "RiskBand",
    "ReplayNamespace",
    "EvidenceCommitCertificate",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "verify_evidence_commit_certificate",
    "select_terminal_outcome_kind",
)
for name in names:
    getattr(governance, name)
print(json.dumps({{
    "owners": {{name: governance._PUBLIC_API[name][0] for name in names}},
    "registry_loaded": {REGISTRY_MODULE!r} in sys.modules,
}}))
"""
    )

    assert result == {
        "owners": {
            "RiskBand": "pheroos.governance.risk_v2",
            "ReplayNamespace": "pheroos.governance.commit_state_v2",
            "EvidenceCommitCertificate": ("pheroos.governance.historical_certificate"),
            "evidence_commit_certificate_fingerprint": (
                "pheroos.governance.historical_certificate"
            ),
            "evidence_commit_certificate_from_payload": (
                "pheroos.governance.historical_certificate"
            ),
            "evidence_commit_certificate_payload": (
                "pheroos.governance.historical_certificate"
            ),
            "verify_evidence_commit_certificate": (
                "pheroos.governance.historical_certificate"
            ),
            "select_terminal_outcome_kind": ("pheroos.governance.commit_semantics"),
        },
        "registry_loaded": False,
    }


def test_unreleased_v1_conversion_helper_is_absent_after_activation() -> None:
    assert REMOVED_PRE_ACTIVATION_EXPORT not in PUBLIC_API
    assert REMOVED_PRE_ACTIVATION_EXPORT not in governance.__all__
    assert REMOVED_PRE_ACTIVATION_EXPORT not in dir(governance)
    with pytest.raises(AttributeError, match=REMOVED_PRE_ACTIVATION_EXPORT):
        getattr(governance, REMOVED_PRE_ACTIVATION_EXPORT)


__all__: tuple[str, ...] = ()
