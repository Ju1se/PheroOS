from __future__ import annotations

from dataclasses import fields, replace
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    evidence_commit_certificate_body_root,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
    issue_local_commit_receipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    output_payload_fingerprint,
    verify_evidence_commit_certificate,
)
from pheroos.governance.commit import assess_optimal_commit
from pheroos.governance.commit_state import (
    ReplayNamespace,
    ReplayReceipt,
    advance_commit_window_state,
    commit_window_ready,
    commit_window_seal_for_state,
    commit_window_seal_matches_receipt,
    initialize_commit_window_state,
    record_commit_replay_receipts,
    commit_finality_verification_fingerprint,
    commit_finality_verification_is_authoritative,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    CertificatePolicy,
    CommitAssurance,
)
from tests.governance import test_commit_engine as engine_fixture


def _fingerprint(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _assess_at(scenario, step: int):
    return assess_optimal_commit(
        scenario.context,
        manifest=scenario.manifest,
        candidate_inputs=scenario.candidate_inputs,
        leases=scenario.leases,
        revocations=(),
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        stop_resolution=scenario.stop_resolution,
        commit_permission=scenario.permission,
        assessment_id=f"assessment:{scenario.run_id}:certificate:{step}",
        issuer_id="governance:commit-certificate-test",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:test:assessment:certificate:{scenario.run_id}:{step}",
        trace_event_id=f"trace:assessment:certificate:{scenario.run_id}:{step}",
    )


def _stable_scenario():
    scenario = engine_fixture._scenario()
    window = initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=scenario.context.profile,
        assurance=scenario.context.assurance,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=scenario.context.protocol_id,
        run_id=scenario.context.run_id,
        target=scenario.context.target,
        epoch=scenario.context.epoch,
        risk_assessment_root=scenario.context.risk_assessment_fingerprint,
        membership_root=scenario.context.membership_root,
        threshold_snapshot=scenario.threshold,
        current_step=4,
        issuer_id="governance:window",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:window:{scenario.run_id}",
        trace_event_id=f"trace:window:{scenario.run_id}",
    )
    first = _assess_at(scenario, 5)
    window = advance_commit_window_state(
        window,
        assessment=first,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    second = _assess_at(scenario, 6)
    window = advance_commit_window_state(
        window,
        assessment=second,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=6,
    )
    assert commit_window_ready(window)
    output_ref = output_payload_fingerprint(
        {"candidate": scenario.leader_id, "result": "declared-output"},
        profile=scenario.context.profile,
    )
    return scenario, second, window, output_ref


def _receipt(scenario, assessment, window, output_ref: str) -> LocalCommitReceipt:
    return issue_local_commit_receipt(
        scenario.context,
        assessment,
        window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        output_payload_fingerprint=output_ref,
        receipt_id=f"receipt:{scenario.run_id}",
        issuer_id="governance:receipt",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=6,
        provenance=f"urn:test:receipt:{scenario.run_id}",
        trace_event_id=f"trace:receipt:{scenario.run_id}",
    )


def _certified_scenario(monkeypatch: pytest.MonkeyPatch):
    original_policy = engine_fixture._policy

    def certified_policy(**kwargs):
        policy = original_policy(**kwargs)
        risk_bands = {
            name: replace(band, minimum_assurance="certified")
            for name, band in policy.risk_bands.items()
        }
        return replace(
            policy,
            assurance="certified",
            risk_bands=risk_bands,
            certificate=CertificatePolicy(
                mode="portable",
                wire_version=COMMIT_WIRE_VERSION,
                canonicalization=COMMIT_CANONICAL_VERSION,
                hash_algorithm="sha256",
                issuer_attestation_required=True,
                independent_verification_required=True,
            ),
        )

    monkeypatch.setattr(
        engine_fixture,
        "PROFILE",
        CERTIFIED_COMMIT_PROFILE_VERSION,
    )
    monkeypatch.setattr(
        engine_fixture,
        "ASSURANCE",
        CommitAssurance.CERTIFIED,
    )
    monkeypatch.setattr(engine_fixture, "_policy", certified_policy)
    return _stable_scenario()


def _evidence_certificate(monkeypatch: pytest.MonkeyPatch):
    scenario, assessment, window, output_ref = _certified_scenario(monkeypatch)
    receipt = _receipt(scenario, assessment, window, output_ref)
    metadata = {
        "certificate_id": f"certificate:{scenario.run_id}",
        "issuer_id": "governance:portable-certificate",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 6,
        "provenance": f"urn:test:certificate:{scenario.run_id}",
        "trace_event_id": f"trace:certificate:{scenario.run_id}",
    }
    body_root = evidence_commit_certificate_body_root(receipt, **metadata)
    refs = ("attestation:portable:primary", "attestation:portable:backup")
    trusted = {item: body_root for item in refs}
    certificate = issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=tuple(reversed(refs)),
        trusted_issuer_attestations=trusted,
        **metadata,
    )
    return scenario, receipt, certificate, trusted, output_ref, metadata


def test_local_receipt_requires_ready_authoritative_stable_window() -> None:
    scenario, assessment, window, output_ref = _stable_scenario()
    receipt = _receipt(scenario, assessment, window, output_ref)

    assert local_commit_receipt_is_authoritative(receipt)
    assert receipt.candidate_id == scenario.leader_id
    assert receipt.claim_fingerprint == next(
        item.claim_fingerprint
        for item in scenario.context.candidate_claims
        if item.candidate_id == scenario.leader_id
    )
    assert receipt.output_payload_fingerprint == output_ref
    assert receipt.assessment_root == window.last_assessment_ref
    assert receipt.window_root == window.window_root
    assert receipt.evidence_root == assessment.collective_evidence_root
    assert receipt.challenge_root == assessment.collective_challenge_root
    assert receipt.lease_root == assessment.collective_lease_root
    seal = commit_window_seal_for_state(window)
    assert seal is not None
    assert commit_window_seal_matches_receipt(window, receipt)
    assert seal.receipt_ref == local_commit_receipt_fingerprint(receipt)
    assert seal.claim_fingerprint == receipt.claim_fingerprint
    assert seal.output_payload_fingerprint == output_ref

    forged = replace(receipt, candidate_id=scenario.other_id)
    assert not local_commit_receipt_is_authoritative(forged)

    # Exact replay is idempotent, while one id cannot name two bodies.
    assert _receipt(scenario, assessment, window, output_ref) is receipt
    with pytest.raises(GovernanceError, match="different body"):
        _receipt(
            scenario,
            assessment,
            window,
            output_payload_fingerprint(
                {"candidate": scenario.leader_id, "result": "conflicting-output"},
                profile=scenario.context.profile,
            ),
        )


def test_every_local_receipt_leaf_mutation_loses_authority() -> None:
    scenario, assessment, window, output_ref = _stable_scenario()
    receipt = _receipt(scenario, assessment, window, output_ref)
    for record in fields(LocalCommitReceipt):
        if not record.init:
            continue
        try:
            forged = replace(
                receipt,
                **{
                    record.name: _mutated_leaf(
                        record.name,
                        getattr(receipt, record.name),
                    )
                },
            )
        except (GovernanceError, TypeError, ValueError):
            continue
        assert not local_commit_receipt_is_authoritative(forged), record.name


def test_local_receipt_id_and_window_seal_are_concurrently_idempotent() -> None:
    scenario, assessment, window, output_ref = _stable_scenario()

    def issue() -> LocalCommitReceipt:
        return _receipt(scenario, assessment, window, output_ref)

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = tuple(executor.map(lambda _: issue(), range(24)))

    assert all(receipt is receipts[0] for receipt in receipts)
    assert local_commit_receipt_is_authoritative(receipts[0])
    assert commit_window_seal_matches_receipt(window, receipts[0])
    seal = commit_window_seal_for_state(window)
    assert seal is not None
    assert seal.receipt_ref == local_commit_receipt_fingerprint(receipts[0])


def test_local_receipt_rejects_unstable_and_forged_inputs() -> None:
    scenario = engine_fixture._scenario()
    window = initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=scenario.context.profile,
        assurance=scenario.context.assurance,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=scenario.context.protocol_id,
        run_id=scenario.context.run_id,
        target=scenario.context.target,
        epoch=scenario.context.epoch,
        risk_assessment_root=scenario.context.risk_assessment_fingerprint,
        membership_root=scenario.context.membership_root,
        threshold_snapshot=scenario.threshold,
        current_step=4,
        issuer_id="governance:window",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:window:unstable",
        trace_event_id="trace:window:unstable",
    )
    assessment = _assess_at(scenario, 5)
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    output_ref = output_payload_fingerprint(
        {"result": "not-stable"},
        profile=scenario.context.profile,
    )
    with pytest.raises(GovernanceError, match="stable ready window"):
        _receipt(scenario, assessment, window, output_ref)

    forged_assessment = replace(assessment, reason_codes=("forged",))
    with pytest.raises(GovernanceError, match="authoritative assessment"):
        issue_local_commit_receipt(
            scenario.context,
            forged_assessment,
            window,
            commit_policy=scenario.policy,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            output_payload_fingerprint=output_ref,
            receipt_id="receipt:forged",
            issuer_id="governance:receipt",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=5,
            provenance="urn:test:receipt:forged",
            trace_event_id="trace:receipt:forged",
        )


def test_local_receipt_rejects_stale_authority_head_after_assessment() -> None:
    scenario, assessment, window, output_ref = _stable_scenario()
    record_commit_replay_receipts(
        scenario.replay_state,
        current_step=7,
        receipts=(
            ReplayReceipt(
                namespace=ReplayNamespace.WITNESS,
                record_id=f"witness:{scenario.run_id}:new-head",
                nonce=f"nonce:witness:{scenario.run_id}:new-head",
                payload_fingerprint=_fingerprint(
                    f"witness:{scenario.run_id}:new-head"
                ),
                target=scenario.context.target,
                candidate_id=scenario.leader_id,
                epoch=scenario.context.epoch,
                principal_id="witness:new-head",
            ),
        ),
    )

    with pytest.raises(GovernanceError, match="commit replay head is stale"):
        _receipt(scenario, assessment, window, output_ref)


def test_portable_evidence_certificate_rebuilds_without_process_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, receipt, certificate, trusted, output_ref, metadata = _evidence_certificate(monkeypatch)
    payload = evidence_commit_certificate_payload(certificate)
    ref = evidence_commit_certificate_fingerprint(certificate)

    assert verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted,
        expected_certificate_ref=ref,
        expected_claim_fingerprint=certificate.claim_fingerprint,
        expected_output_payload_fingerprint=output_ref,
    )
    assert verify_evidence_commit_certificate(
        dict(reversed(tuple(payload.items()))),
        trusted_issuer_attestations=trusted,
        expected_certificate_ref=ref,
    )
    assert not verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations={},
    )
    assert not verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations={
            key: _fingerprint("forged-body") for key in trusted
        },
    )
    assert issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=certificate.issuer_attestation_refs,
        trusted_issuer_attestations=trusted,
        **metadata,
    ) is certificate

    conflicting_metadata = {
        **metadata,
        "provenance": f"{metadata['provenance']}:conflict",
    }
    conflicting_body = evidence_commit_certificate_body_root(
        receipt,
        **conflicting_metadata,
    )
    conflicting_trust = {
        item: conflicting_body for item in certificate.issuer_attestation_refs
    }
    with pytest.raises(GovernanceError, match="different body"):
        issue_evidence_commit_certificate(
            receipt,
            commit_policy=scenario.policy,
            issuer_attestation_refs=certificate.issuer_attestation_refs,
            trusted_issuer_attestations=conflicting_trust,
            **conflicting_metadata,
        )

    predating_metadata = {
        **metadata,
        "certificate_id": f"certificate:predating:{scenario.run_id}",
        "issued_at_step": receipt.issued_at_step - 1,
    }
    with pytest.raises(GovernanceError, match="cannot predate"):
        evidence_commit_certificate_body_root(
            receipt,
            **predating_metadata,
        )


def test_local_and_portable_certificate_issue_typed_finality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.governance.certificate import (
        verify_evidence_commit_finality,
        verify_local_commit_finality,
    )

    local_scenario, local_assessment, local_window, local_output = _stable_scenario()
    local_receipt = _receipt(
        local_scenario,
        local_assessment,
        local_window,
        local_output,
    )
    local_finality = verify_local_commit_finality(
        local_receipt,
        local_scenario.context,
        local_assessment,
        local_window,
        commit_policy=local_scenario.policy,
        risk_chain_state=local_scenario.risk_chain_state,
        risk_assessment=local_scenario.risk_assessment,
        threshold_snapshot=local_scenario.threshold,
        membership_snapshot=local_scenario.membership_snapshot,
        membership_epoch_state=local_scenario.membership_state,
        replay_state=local_scenario.replay_state,
        support_replay_state=local_scenario.support_replay_state,
        current_step=6,
        verifier_id="governance:local-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:local-finality",
        trace_event_id="trace:local-finality",
    )
    assert commit_finality_verification_is_authoritative(local_finality)
    assert local_finality.certificate_ref == local_commit_receipt_fingerprint(
        local_receipt
    )

    scenario, assessment, window, output_ref = _certified_scenario(monkeypatch)
    receipt = _receipt(scenario, assessment, window, output_ref)
    metadata = {
        "certificate_id": f"certificate:typed-finality:{scenario.run_id}",
        "issuer_id": "governance:portable-certificate",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 6,
        "provenance": f"urn:test:certificate:{scenario.run_id}",
        "trace_event_id": f"trace:certificate:{scenario.run_id}",
    }
    body_root = evidence_commit_certificate_body_root(receipt, **metadata)
    attestations = {"attestation:portable:typed": body_root}
    certificate = issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=tuple(attestations),
        trusted_issuer_attestations=attestations,
        **metadata,
    )
    portable_finality = verify_evidence_commit_finality(
        certificate,
        receipt,
        scenario.context,
        assessment,
        window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        trusted_issuer_attestations=attestations,
        current_step=6,
        verifier_id="governance:portable-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:portable-finality",
        trace_event_id="trace:portable-finality",
    )
    assert commit_finality_verification_is_authoritative(portable_finality)
    assert portable_finality.certificate_ref == evidence_commit_certificate_fingerprint(
        certificate
    )
    assert commit_finality_verification_fingerprint(portable_finality).startswith(
        "sha256:"
    )


def _mutated_leaf(name: str, value: object) -> object:
    if name == "issuer_attestation_refs":
        return (*tuple(value), "attestation:portable:forged")  # type: ignore[arg-type]
    if isinstance(value, Enum):
        if name == "assurance":
            return CommitAssurance.DISTRIBUTED
        if name == "authority_scope":
            return "distributed"
        if name == "authority":
            return AuthorityLevel.KERNEL
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        if value.startswith("sha256:"):
            return _fingerprint(f"mutation:{name}")
        return f"{value}:mutation"
    raise AssertionError(f"unsupported mutation leaf: {name}")


def test_every_portable_certificate_leaf_mutation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, certificate, trusted, _, _ = _evidence_certificate(monkeypatch)
    payload = evidence_commit_certificate_payload(certificate)

    for record in fields(EvidenceCommitCertificate):
        if not record.init:
            continue
        mutated = dict(payload)
        mutated[record.name] = _mutated_leaf(record.name, mutated[record.name])
        assert not verify_evidence_commit_certificate(
            mutated,
            trusted_issuer_attestations=trusted,
        ), record.name


def test_portable_finality_adapter_accepts_late_certificate_without_head_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.governance.certificate import verify_evidence_commit_finality

    scenario, assessment, window, output_ref = _certified_scenario(monkeypatch)
    receipt = _receipt(scenario, assessment, window, output_ref)
    metadata = {
        "certificate_id": f"certificate:late:{scenario.run_id}",
        "issuer_id": "governance:portable-late",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 7,
        "provenance": f"urn:test:portable-late:{scenario.run_id}",
        "trace_event_id": f"trace:portable-late:{scenario.run_id}",
    }
    body_root = evidence_commit_certificate_body_root(receipt, **metadata)
    trust = {"attestation:portable:late": body_root}
    certificate = issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=tuple(trust),
        trusted_issuer_attestations=trust,
        **metadata,
    )
    finality = verify_evidence_commit_finality(
        certificate,
        receipt,
        scenario.context,
        assessment,
        window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        trusted_issuer_attestations=trust,
        current_step=7,
        verifier_id="governance:portable-late-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:portable-late-finality",
        trace_event_id="trace:portable-late-finality",
    )
    assert commit_finality_verification_is_authoritative(finality)
    assert finality.verified_at_step == 7
    assert finality.certificate_ref == evidence_commit_certificate_fingerprint(
        certificate
    )

    for forged_head in (
        {"context": replace(scenario.context)},
        {"assessment": replace(assessment)},
        {"window_state": replace(window)},
    ):
        arguments = {
            "context": scenario.context,
            "assessment": assessment,
            "window_state": window,
            **forged_head,
        }
        with pytest.raises(
            GovernanceError,
            match=(
                "current sealed receipt|sealed receipt does not rebuild|"
                "authority heads changed"
            ),
        ):
            verify_evidence_commit_finality(
                certificate,
                receipt,
                arguments["context"],
                arguments["assessment"],
                arguments["window_state"],
                commit_policy=scenario.policy,
                risk_chain_state=scenario.risk_chain_state,
                risk_assessment=scenario.risk_assessment,
                threshold_snapshot=scenario.threshold,
                membership_snapshot=scenario.membership_snapshot,
                membership_epoch_state=scenario.membership_state,
                replay_state=scenario.replay_state,
                support_replay_state=scenario.support_replay_state,
                trusted_issuer_attestations=trust,
                current_step=7,
                verifier_id="governance:portable-forged-head",
                authority=AuthorityLevel.GOVERNANCE,
                provenance="urn:test:portable-forged-head",
                trace_event_id="trace:portable-forged-head",
            )

    record_commit_replay_receipts(
        scenario.replay_state,
        current_step=8,
        receipts=(
            ReplayReceipt(
                namespace=ReplayNamespace.WITNESS,
                record_id=f"witness:{scenario.run_id}:post-seal",
                nonce=f"nonce:witness:{scenario.run_id}:post-seal",
                payload_fingerprint=_fingerprint(
                    f"witness:{scenario.run_id}:post-seal"
                ),
                target=scenario.context.target,
                candidate_id=scenario.leader_id,
                epoch=scenario.context.epoch,
                principal_id="witness:post-seal",
            ),
        ),
    )
    with pytest.raises(
        GovernanceError,
        match="sealed receipt does not rebuild|authority heads changed",
    ):
        verify_evidence_commit_finality(
            certificate,
            receipt,
            scenario.context,
            assessment,
            window,
            commit_policy=scenario.policy,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            trusted_issuer_attestations=trust,
            current_step=8,
            verifier_id="governance:portable-stale-head",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:portable-stale-head",
            trace_event_id="trace:portable-stale-head",
        )


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def test_portable_certificate_is_cwd_and_hash_seed_stable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, certificate, trusted, _, _ = _evidence_certificate(monkeypatch)
    payload = _json_value(evidence_commit_certificate_payload(certificate))
    request = json.dumps({"payload": payload, "trusted": trusted}, sort_keys=True)
    script = """
import json, sys
from pheroos.governance.certificate import (
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    verify_evidence_commit_certificate,
)
request = json.loads(sys.stdin.read())
certificate = evidence_commit_certificate_from_payload(request["payload"])
assert verify_evidence_commit_certificate(
    request["payload"], trusted_issuer_attestations=request["trusted"]
)
print(evidence_commit_certificate_fingerprint(certificate))
"""
    root = Path(__file__).resolve().parents[2]
    observed = []
    for seed in ("1", "92741"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(root)
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=request,
            text=True,
            capture_output=True,
            cwd=tmp_path,
            env=env,
            check=True,
        )
        observed.append(result.stdout.strip())
    assert observed == [
        evidence_commit_certificate_fingerprint(certificate),
        evidence_commit_certificate_fingerprint(certificate),
    ]
