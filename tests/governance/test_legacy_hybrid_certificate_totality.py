from __future__ import annotations

from copy import copy
from dataclasses import fields, replace
from types import SimpleNamespace
from typing import Any

import pytest

from pheroos.conformance._commit_reference import (
    build_reference_portable_commit,
    build_reference_stable_commit,
    issue_reference_distributed_certificate,
)
from pheroos.governance._certificate import historical as certificate_historical
from pheroos.governance._certificate import invariants as certificate_invariants
from pheroos.governance._certificate import local as certificate_local
from pheroos.governance._certificate import outcome as certificate_outcome
from pheroos.governance._certificate import portable as certificate_portable
from pheroos.governance._certificate import records as certificate_records
from pheroos.governance._commit.common import AuthorityScope
from pheroos.governance._commit_state.records import DecisionOutcomeKind
from pheroos.governance._hybrid import attention as hybrid_attention
from pheroos.governance._hybrid import binding as hybrid_binding
from pheroos.governance._hybrid import commit as hybrid_commit
from pheroos.governance._hybrid import evaluation_records as hybrid_records
from pheroos.governance._hybrid import finality as hybrid_finality
from pheroos.governance._hybrid import output as hybrid_output
from pheroos.governance._hybrid import pipeline as hybrid_pipeline
from pheroos.governance._hybrid import preflight as hybrid_preflight
from pheroos.governance._hybrid import request as hybrid_request
from pheroos.governance._hybrid import trace as hybrid_trace
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    OutcomeCertificate,
    issue_outcome_certificate,
    output_payload_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.distributed_commit import (
    register_distributed_commit_certificate,
)
from pheroos.governance.hybrid_commit import evaluate_hybrid_commit_step
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    CertificatePolicy,
    CommitAssurance,
)
from tests.governance import test_commit_certificate as certificate_fixture
from tests.governance import test_commit_output_actions as outcome_fixture
from tests.governance import (
    test_hybrid_commit_total_evaluation as hybrid_fixture,
)


ROOT_A = "sha256:" + "a" * 64
ROOT_B = "sha256:" + "b" * 64


def _clone(value: object, **changes: object) -> Any:
    cloned = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(cloned, name, replacement)
    return cloned


def _reissue_hybrid_evaluation(
    evaluation: hybrid_records.HybridCommitEvaluation,
    **changes: object,
) -> hybrid_records.HybridCommitEvaluation:
    forged = _clone(evaluation, **changes)
    object.__setattr__(
        forged,
        "_issuance",
        (
            hybrid_commit._HYBRID_COMMIT_EVALUATION_ISSUANCE,
            hybrid_records.hybrid_commit_evaluation_fingerprint(forged),
        ),
    )
    return forged


def _stable_hybrid_request(
    stable: Any,
) -> hybrid_request.HybridCommitEvaluationRequest:
    scenario = stable.scenario
    step = stable.window.last_evaluated_step
    attention, directive = hybrid_fixture._attention(scenario, step=step)
    return hybrid_request.HybridCommitEvaluationRequest(
        request_version=hybrid_fixture.HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"legacy-totality:{scenario.run_id}:{step}",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=stable.assessments[-1],
        context=scenario.context,
        window_state=stable.window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        output_payload_fingerprint=stable.output_fingerprint,
        issuer_id="governance:legacy-totality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:legacy-totality:{scenario.run_id}",
        trace_event_id=f"trace:legacy-totality:{scenario.run_id}:{step}",
        local_receipt=stable.receipt,
        prior_trace_events=hybrid_fixture._authority_trace(scenario),
    )


@pytest.fixture(scope="module")
def local_bundle():
    scenario, assessment, window, output_ref = certificate_fixture._stable_scenario()
    receipt = certificate_fixture._receipt(
        scenario,
        assessment,
        window,
        output_ref,
    )
    return scenario, assessment, window, output_ref, receipt


@pytest.fixture(scope="module")
def portable_bundle():
    policy = hybrid_fixture._higher_assurance_policy(CommitAssurance.CERTIFIED)
    scenario = hybrid_fixture._scenario(
        commit_policy=policy,
        profile=hybrid_fixture.CERTIFIED_COMMIT_PROFILE_VERSION,
    )
    stable = build_reference_stable_commit(scenario, variant="legacy-totality")
    portable = build_reference_portable_commit(
        stable,
        variant="legacy-totality",
    )
    return stable, portable


@pytest.fixture(scope="module")
def outcome_bundle():
    scenario, window, outcome = outcome_fixture._nonready_outcome(
        DecisionOutcomeKind.SAFE_FALLBACK
    )
    output_ref = output_payload_fingerprint(
        {"kind": "safe_fallback", "totality": True},
        profile=outcome.profile,
    )
    certificate = issue_outcome_certificate(
        outcome,
        window,
        commit_policy=scenario.policy,
        output_payload_fingerprint=output_ref,
        certificate_id=f"outcome-certificate:{scenario.run_id}:totality",
        context=scenario.context,
        assessment=None,
        issuer_id="governance:legacy-totality",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=outcome.current_step,
        provenance=f"urn:test:legacy-totality:{scenario.run_id}",
        trace_event_id=f"trace:legacy-totality:{scenario.run_id}",
    )
    return scenario, window, outcome, output_ref, certificate


@pytest.fixture(scope="module")
def hybrid_bundle():
    request = hybrid_fixture._total_request(stable=False)
    evaluation = evaluate_hybrid_commit_step(request=request)
    assert evaluation.authoritative
    assert evaluation.binding_step is not None
    return request, evaluation


class _StringSubclass(str):
    pass


def test_certificate_invariant_totality_guards(local_bundle) -> None:
    scenario, _, _, _, receipt = local_bundle
    with pytest.raises(GovernanceError, match="mapping"):
        certificate_invariants.output_payload_fingerprint(  # type: ignore[arg-type]
            object(),
            profile=receipt.profile,
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        certificate_invariants._issue_typed_finality_verification(
            receipt,
            certificate_kind="local_commit_receipt",
            certificate_ref=ROOT_A,
            current_step=receipt.issued_at_step,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.AGENT,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:finality",
        )
    with pytest.raises(GovernanceError, match="future"):
        certificate_invariants._issue_typed_finality_verification(
            receipt,
            certificate_kind="local_commit_receipt",
            certificate_ref=ROOT_A,
            current_step=receipt.issued_at_step - 1,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:finality",
        )

    policy = scenario.policy
    certificate_invariants._validate_policy_binding(
        policy,
        profile=receipt.profile,
        assurance=receipt.assurance,
        target=receipt.target,
        commit_policy_root=receipt.commit_policy_root,
    )
    bad_policy = replace(
        policy,
        certificate=CertificatePolicy(
            mode=policy.certificate.mode,
            wire_version="unsupported-wire",
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=False,
            independent_verification_required=False,
        ),
    )
    invalid_bindings = (
        (object(), receipt.assurance, receipt.target, receipt.commit_policy_root),
        (policy, CommitAssurance.CERTIFIED, receipt.target, receipt.commit_policy_root),
        (policy, receipt.assurance, "decision:other", receipt.commit_policy_root),
        (policy, receipt.assurance, receipt.target, ROOT_A),
        (bad_policy, receipt.assurance, receipt.target, receipt.commit_policy_root),
    )
    for candidate, assurance, target, policy_root in invalid_bindings:
        with pytest.raises(GovernanceError):
            certificate_invariants._validate_policy_binding(
                candidate,  # type: ignore[arg-type]
                profile=receipt.profile,
                assurance=assurance,
                target=target,
                commit_policy_root=policy_root,
            )

    certificate_invariants._require_same_scope(receipt, receipt, "scope")
    with pytest.raises(GovernanceError, match="run_id mismatch"):
        certificate_invariants._require_same_scope(
            receipt,
            _clone(receipt, run_id="run:other"),
            "scope",
        )
    assert not certificate_invariants._attestations_match(
        ("attestation:one",),
        object(),  # type: ignore[arg-type]
        body_root=ROOT_A,
    )
    assert not certificate_invariants._attestations_match(
        ("attestation:one",),
        {},
        body_root=ROOT_A,
    )
    with pytest.raises(GovernanceError, match="do not bind"):
        certificate_invariants._require_attestation_bindings(
            ("attestation:one",),
            {"attestation:one": ROOT_B},
            body_root=ROOT_A,
            field_name="certificate",
        )


def test_certificate_wire_totality_guards(outcome_bundle) -> None:
    _, _, _, _, certificate = outcome_bundle
    payload = certificate_outcome.outcome_certificate_payload(certificate)
    with pytest.raises(GovernanceError, match="mapping"):
        certificate_invariants._strict_payload_values(
            object(),  # type: ignore[arg-type]
            OutcomeCertificate,
            field_name="outcome",
        )
    with pytest.raises(GovernanceError, match="keys mismatch"):
        certificate_invariants._strict_payload_values(
            {},
            OutcomeCertificate,
            field_name="outcome",
        )
    subclass_payload = {_StringSubclass(name): value for name, value in payload.items()}
    with pytest.raises(GovernanceError, match="keys must be strings"):
        certificate_invariants._strict_payload_values(
            subclass_payload,
            OutcomeCertificate,
            field_name="outcome",
        )
    with pytest.raises(GovernanceError, match="sequence"):
        certificate_invariants._require_sequence("not-a-sequence", "items")

    coercions = (
        (certificate_invariants._coerce_assurance, "invalid-assurance"),
        (certificate_invariants._coerce_authority_scope, "invalid-scope"),
        (certificate_invariants._coerce_outcome_kind, "invalid-outcome"),
        (certificate_invariants._coerce_authority, "invalid-authority"),
    )
    for coercion, value in coercions:
        with pytest.raises(GovernanceError):
            coercion(value)

    malformed = dict(payload)
    malformed["certificate_body_root"] = ROOT_A
    with pytest.raises(GovernanceError, match="payload is invalid"):
        certificate_outcome.outcome_certificate_from_payload(malformed)


def test_historical_certificate_expected_bindings(portable_bundle) -> None:
    _, portable = portable_bundle
    certificate = portable.certificate
    trusted = portable.trusted_issuer_attestations
    certificate_ref = certificate_historical.evidence_commit_certificate_fingerprint(
        certificate
    )
    assert certificate_historical.verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted,
        expected_certificate_ref=certificate_ref,
        expected_claim_fingerprint=certificate.claim_fingerprint,
        expected_output_payload_fingerprint=certificate.output_payload_fingerprint,
    )
    assert not certificate_historical.verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted,
        expected_certificate_ref=ROOT_A,
    )
    assert not certificate_historical.verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted,
        expected_claim_fingerprint=ROOT_A,
    )
    assert not certificate_historical.verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted,
        expected_output_payload_fingerprint=ROOT_A,
    )


def test_certificate_record_authority_invariants(
    portable_bundle,
    outcome_bundle,
) -> None:
    _, portable = portable_bundle
    evidence = portable.certificate
    _, _, _, _, outcome = outcome_bundle

    evidence_cases = (
        _clone(evidence, assurance=CommitAssurance.ADVISORY),
        _clone(evidence, authority_scope=AuthorityScope.NONE),
        _clone(evidence, issuer_attestation_refs=()),
        _clone(evidence, certificate_body_root=ROOT_A),
        _clone(evidence, certificate_root=ROOT_A),
    )
    for forged in evidence_cases:
        with pytest.raises(GovernanceError):
            certificate_records._validate_evidence_commit_certificate(forged)

    outcome_cases = (
        _clone(outcome, outcome_kind="safe_fallback"),
        _clone(outcome, authoritative_commit=1),
        _clone(outcome, epistemically_committed=0),
        _clone(outcome, authoritative_commit=True),
        _clone(outcome, commit_certificate_ref=ROOT_A),
        _clone(outcome, authority_scope=AuthorityScope.DENIAL),
        _clone(outcome, candidate_id="", claim_fingerprint=""),
        _clone(outcome, issuer_attestation_refs=("attestation:forged",)),
        _clone(outcome, certificate_body_root=ROOT_A),
        _clone(outcome, certificate_root=ROOT_A),
    )
    for forged in outcome_cases:
        with pytest.raises(GovernanceError):
            certificate_records._validate_outcome_certificate(forged)


def test_commit_outcome_record_authority_guards(portable_bundle) -> None:
    _, portable = portable_bundle
    evidence = portable.certificate
    values = {
        record.name: getattr(evidence, record.name)
        for record in fields(certificate_records.OutcomeCertificate)
        if record.init and hasattr(evidence, record.name)
    }
    values.update(
        {
            "outcome_kind": DecisionOutcomeKind.EVIDENCE_COMMIT,
            "outcome_ref": ROOT_A,
            "authoritative_commit": True,
            "epistemically_committed": True,
            "commit_certificate_ref": certificate_historical.evidence_commit_certificate_fingerprint(
                evidence
            ),
        }
    )
    commit_outcome = object.__new__(certificate_records.OutcomeCertificate)
    for record in fields(certificate_records.OutcomeCertificate):
        if record.init:
            object.__setattr__(commit_outcome, record.name, values[record.name])

    invalid = (
        _clone(commit_outcome, authoritative_commit=False),
        _clone(commit_outcome, assurance=CommitAssurance.ADVISORY),
        _clone(commit_outcome, authority_scope=AuthorityScope.NONE),
        _clone(commit_outcome, commit_certificate_ref=""),
    )
    for forged in invalid:
        with pytest.raises(GovernanceError):
            certificate_records._validate_commit_outcome_authority(forged)

    certificate_records._validate_outcome_authority(commit_outcome)


def test_local_certificate_helper_guards(local_bundle) -> None:
    scenario, assessment, window, output_ref, receipt = local_bundle
    with pytest.raises(GovernanceError, match="governance authority"):
        certificate_local.issue_local_commit_receipt(
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
            receipt_id="receipt:invalid-authority",
            issuer_id="issuer:invalid-authority",
            authority=AuthorityLevel.AGENT,
            current_step=receipt.issued_at_step,
            provenance="urn:test:invalid-authority",
            trace_event_id="trace:invalid-authority",
        )
    assert not certificate_local.local_commit_receipt_matches(
        None,
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
        current_step=receipt.issued_at_step,
    )
    assert not certificate_local.local_commit_receipt_matches(
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
        current_step=receipt.issued_at_step,
        expected_output_payload_fingerprint=ROOT_A,
    )
    with pytest.raises(GovernanceError, match="evidence-bound assurance"):
        certificate_local.verify_local_commit_finality(
            _clone(receipt, assurance=CommitAssurance.CERTIFIED),
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
            current_step=receipt.issued_at_step,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:local-finality",
        )
    with pytest.raises(GovernanceError, match="receipt step"):
        certificate_local.verify_local_commit_finality(
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
            current_step=receipt.issued_at_step + 1,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:local-finality",
        )


def test_local_certificate_lineage_validators(local_bundle) -> None:
    scenario, assessment, window, _, receipt = local_bundle
    heads = certificate_local._local_receipt_head_fingerprints(
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
    )
    certificate_local._validate_local_receipt_context_heads(
        scenario.context,
        assessment=assessment,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_head_fingerprints=heads,
    )
    bad_heads = dict(heads)
    bad_heads["risk_assessment_fingerprint"] = ROOT_A
    with pytest.raises(GovernanceError, match="lineage mismatch"):
        certificate_local._validate_local_receipt_context_heads(
            scenario.context,
            assessment=assessment,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            current_head_fingerprints=bad_heads,
        )
    with pytest.raises(GovernanceError, match="replay roots"):
        certificate_local._validate_local_receipt_context_heads(
            _clone(scenario.context, replay_receipt_root=ROOT_A),
            assessment=assessment,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            current_head_fingerprints=heads,
        )

    with pytest.raises(GovernanceError, match="profile lineage"):
        certificate_local._validate_local_receipt_window_lineage(
            _clone(scenario.context, profile="pheroos-other-profile"),
            assessment=assessment,
            window_state=window,
        )
    with pytest.raises(GovernanceError, match="window risk_chain_state_root"):
        certificate_local._validate_local_receipt_window_lineage(
            scenario.context,
            assessment=_clone(assessment, risk_chain_state_fingerprint=ROOT_A),
            window_state=window,
        )

    ready_cases = (
        _clone(assessment, context_fingerprint=ROOT_A),
        _clone(assessment, status=object()),
        _clone(assessment, unique_leader=False),
        _clone(assessment, blocker_references=("blocker:one",)),
    )
    for forged in ready_cases:
        with pytest.raises(GovernanceError):
            certificate_local._validate_local_receipt_ready_assessment(
                scenario.context,
                assessment=forged,
                window_state=window,
                current_step=receipt.issued_at_step,
            )
    with pytest.raises(GovernanceError, match="stable window head"):
        certificate_local._validate_local_receipt_ready_assessment(
            scenario.context,
            assessment=assessment,
            window_state=_clone(window, last_evaluated_step=receipt.issued_at_step + 1),
            current_step=receipt.issued_at_step,
        )

    claim, metrics = certificate_local._local_receipt_leader_bindings(
        scenario.context,
        assessment=assessment,
        window_state=window,
    )
    assert claim.claim_fingerprint == receipt.claim_fingerprint
    assert metrics.evidence_root == receipt.candidate_evidence_root
    with pytest.raises(GovernanceError, match="substantive declaration"):
        certificate_local._local_receipt_leader_bindings(
            _clone(scenario.context, candidate_claims=()),
            assessment=assessment,
            window_state=window,
        )
    with pytest.raises(GovernanceError, match="commit-ready"):
        certificate_local._local_receipt_leader_bindings(
            scenario.context,
            assessment=_clone(assessment, candidate_metrics=()),
            window_state=window,
        )
    with pytest.raises(GovernanceError, match="metric roots"):
        certificate_local._local_receipt_leader_bindings(
            scenario.context,
            assessment=assessment,
            window_state=_clone(window, candidate_evidence_root=ROOT_A),
        )


def test_local_certificate_external_head_guards(local_bundle) -> None:
    scenario, assessment, window, _, receipt = local_bundle
    common = {
        "commit_policy": scenario.policy,
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "replay_state": scenario.replay_state,
        "support_replay_state": scenario.support_replay_state,
        "current_step": receipt.issued_at_step,
    }
    invalid = (
        {"threshold_snapshot": object()},
        {"membership_snapshot": object()},
        {"support_replay_state": object()},
    )
    for changes in invalid:
        with pytest.raises(GovernanceError):
            certificate_local._validate_local_receipt_external_heads(
                scenario.context,
                **(common | changes),  # type: ignore[arg-type]
            )

    assert not certificate_local._current_authority_heads_match_receipt(
        receipt,
        context=scenario.context,
        assessment=assessment,
        window_state=window,
        **(common | {"current_step": receipt.issued_at_step - 1}),
    )
    current_invalid = (
        {"context": object()},
        {"threshold_snapshot": object()},
        {"membership_snapshot": object()},
        {"replay_state": object()},
        {"support_replay_state": object()},
    )
    for changes in current_invalid:
        arguments = {
            "context": scenario.context,
            "assessment": assessment,
            "window_state": window,
            **common,
            **changes,
        }
        assert not certificate_local._current_authority_heads_match_receipt(
            receipt,
            **arguments,  # type: ignore[arg-type]
        )


def test_portable_certificate_totality_guards(local_bundle, portable_bundle) -> None:
    scenario, _, _, _, receipt = local_bundle
    stable, portable = portable_bundle
    certificate = portable.certificate
    with pytest.raises(GovernanceError, match="authoritative local receipt"):
        certificate_portable.issue_evidence_commit_certificate(
            object(),  # type: ignore[arg-type]
            commit_policy=stable.scenario.policy,
            certificate_id="certificate:bad",
            issuer_attestation_refs=("attestation:bad",),
            trusted_issuer_attestations={"attestation:bad": ROOT_A},
            issuer_id="issuer:bad",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=1,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )
    with pytest.raises(GovernanceError, match="certified or distributed"):
        certificate_portable.issue_evidence_commit_certificate(
            receipt,
            commit_policy=scenario.policy,
            certificate_id="certificate:bad-assurance",
            issuer_attestation_refs=("attestation:bad",),
            trusted_issuer_attestations={"attestation:bad": ROOT_A},
            issuer_id="issuer:bad",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=receipt.issued_at_step,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )

    certified_scenario = stable.scenario
    with pytest.raises(GovernanceError):
        certificate_portable.issue_evidence_commit_certificate(
            stable.receipt,
            commit_policy=replace(
                certified_scenario.policy,
                certificate=CertificatePolicy(
                    mode="local_receipt",
                    wire_version=COMMIT_WIRE_VERSION,
                    canonicalization=COMMIT_CANONICAL_VERSION,
                    hash_algorithm="sha256",
                    issuer_attestation_required=True,
                    independent_verification_required=True,
                ),
            ),
            certificate_id="certificate:bad-mode",
            issuer_attestation_refs=("attestation:bad",),
            trusted_issuer_attestations={"attestation:bad": ROOT_A},
            issuer_id="issuer:bad",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=stable.receipt.issued_at_step,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )

    finality_kwargs = {
        "commit_policy": certified_scenario.policy,
        "risk_chain_state": certified_scenario.risk_chain_state,
        "risk_assessment": certified_scenario.risk_assessment,
        "threshold_snapshot": certified_scenario.threshold,
        "membership_snapshot": certified_scenario.membership_snapshot,
        "membership_epoch_state": certified_scenario.membership_state,
        "replay_state": certified_scenario.replay_state,
        "support_replay_state": certified_scenario.support_replay_state,
        "trusted_issuer_attestations": portable.trusted_issuer_attestations,
        "current_step": stable.receipt.issued_at_step,
        "verifier_id": "verifier:portable",
        "authority": AuthorityLevel.GOVERNANCE,
        "provenance": "urn:test:portable",
        "trace_event_id": "trace:portable",
    }
    with pytest.raises(GovernanceError, match="certified assurance"):
        certificate_portable.verify_evidence_commit_finality(
            _clone(certificate, assurance=CommitAssurance.DISTRIBUTED),
            stable.receipt,
            certified_scenario.context,
            stable.assessments[-1],
            stable.window,
            **finality_kwargs,
        )
    with pytest.raises(GovernanceError, match="independently valid"):
        certificate_portable.verify_evidence_commit_finality(
            certificate,
            stable.receipt,
            certified_scenario.context,
            stable.assessments[-1],
            stable.window,
            **(
                finality_kwargs
                | {"trusted_issuer_attestations": {"attestation:bad": ROOT_A}}
            ),
        )
    with pytest.raises(GovernanceError, match="local receipt lineage"):
        certificate_portable.verify_evidence_commit_finality(
            certificate,
            receipt,
            certified_scenario.context,
            stable.assessments[-1],
            stable.window,
            **finality_kwargs,
        )


def test_hybrid_attention_totality_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    assessment = evaluation.commit_assessment
    with pytest.raises(GovernanceError, match="stage"):
        hybrid_attention._attention_channel_diagnostic(
            "unknown-stage",
            request=request,
        )
    diagnostic = hybrid_attention._attention_channel_diagnostic(
        "channel_binding",
        request=object(),
    )
    assert diagnostic.references == ()

    step, unavailable = hybrid_attention._bind_attention_channel(
        _clone(request, attention=object()),
        assessment=assessment,
    )
    assert step is None
    assert unavailable is not None
    step, unavailable = hybrid_attention._bind_attention_channel(
        _clone(request, exploration_directive=object()),
        assessment=assessment,
    )
    assert step is None
    assert unavailable is not None
    step, unavailable = hybrid_attention._bind_attention_channel(
        request,
        assessment=object(),  # type: ignore[arg-type]
    )
    assert step is None
    assert unavailable is not None

    retained = hybrid_records._diagnostic(
        "retained",
        "test",
        "retained diagnostic",
        fatal=False,
    )
    stages = (
        (object(), "channel_binding"),
        (_clone(request, attention=object()), "attention"),
        (
            _clone(request, exploration_directive=object()),
            "exploration_directive",
        ),
    )
    for candidate, expected_stage in stages:
        result = hybrid_attention._with_exact_attention_channel_diagnostic(
            (diagnostic, retained),
            request=candidate,
        )
        assert tuple(item.code for item in result) == (
            "retained",
            "attention_channel_unavailable",
        )
        assert result[-1].stage == expected_stage


def test_hybrid_attention_exact_type_guard_survives_an_injected_authority_bypass(
    hybrid_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, evaluation = hybrid_bundle
    monkeypatch.setattr(
        hybrid_attention,
        "exploration_directive_is_authoritative",
        lambda *_args, **_kwargs: True,
    )

    step, diagnostic = hybrid_attention._bind_attention_channel(
        _clone(request, exploration_directive=object()),
        assessment=evaluation.commit_assessment,
    )

    assert step is None
    assert diagnostic is not None
    assert diagnostic.stage == "exploration_directive"


def test_hybrid_binding_input_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    assessment = evaluation.commit_assessment
    with pytest.raises(GovernanceError, match="attention breakdown"):
        hybrid_binding.bind_hybrid_commit_channels(
            attention=object(),  # type: ignore[arg-type]
            exploration_directive=request.exploration_directive,
            commit_assessment=assessment,
        )
    with pytest.raises(GovernanceError, match="exploration directive"):
        hybrid_binding.bind_hybrid_commit_channels(
            attention=request.attention,
            exploration_directive=object(),  # type: ignore[arg-type]
            commit_assessment=assessment,
        )
    with pytest.raises(GovernanceError, match="CommitAssessment"):
        hybrid_binding.bind_hybrid_commit_channels(
            attention=request.attention,
            exploration_directive=request.exploration_directive,
            commit_assessment=object(),  # type: ignore[arg-type]
        )

    other_request = hybrid_fixture._total_request(stable=False)
    stable_other = hybrid_fixture._total_request(
        stable=True,
        scenario=hybrid_fixture._scenario(),
    )
    with pytest.raises(GovernanceError, match="evaluation step"):
        hybrid_binding.bind_hybrid_commit_channels(
            attention=other_request.attention,
            exploration_directive=other_request.exploration_directive,
            commit_assessment=stable_other.commit_assessment,
        )

    with pytest.raises(GovernanceError, match="canonical"):
        hybrid_binding.hybrid_commit_step_payload(object())  # type: ignore[arg-type]
    assert not hybrid_binding.hybrid_commit_step_is_authoritative(object())
    with pytest.raises(GovernanceError, match="authoritative step"):
        hybrid_binding.hybrid_commit_truth_projection(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="authoritative step"):
        hybrid_binding.hybrid_attention_projection(object())  # type: ignore[arg-type]


def test_hybrid_binding_rejects_an_injected_uncovered_leader(
    hybrid_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, evaluation = hybrid_bundle
    assessment = _clone(
        evaluation.commit_assessment,
        leader_candidate_id="candidate:injected-uncovered-leader",
    )
    monkeypatch.setattr(
        hybrid_binding,
        "commit_assessment_is_authoritative",
        lambda _assessment: True,
    )

    with pytest.raises(GovernanceError, match="cover the assessed leader"):
        hybrid_binding.bind_hybrid_commit_channels(
            attention=request.attention,
            exploration_directive=request.exploration_directive,
            commit_assessment=assessment,
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("protocol_id", "protocol:injected-cross-scope"),
        ("target", "decision:injected-cross-scope"),
        ("current_step", 1_000_000),
    ),
)
def test_hybrid_evaluation_rejects_injected_directive_scope_drift(
    hybrid_bundle,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    replacement: object,
) -> None:
    _, evaluation = hybrid_bundle
    directive = _clone(
        evaluation.exploration_directive,
        **{field_name: replacement},
    )
    forged = _reissue_hybrid_evaluation(
        evaluation,
        exploration_directive=directive,
        exploration_directive_ref=(
            hybrid_commit.exploration_directive_fingerprint(directive)
        ),
    )
    monkeypatch.setattr(
        hybrid_commit,
        "exploration_directive_is_authoritative",
        lambda _directive: True,
    )

    assert hybrid_commit.hybrid_commit_evaluation_is_authoritative(forged) is False


@pytest.mark.parametrize(
    ("name", "replacement"),
    (
        ("binding_profile", "unsupported"),
        ("profile", ""),
        ("assurance", "certified"),
        ("protocol_id", " protocol:bad"),
        ("run_id", ""),
        ("target", "target:bad "),
        ("epoch", True),
        ("current_step", -1),
        ("leader_margin", -1),
        ("commit_authority_source", "agent"),
        ("attention_authority_scope", "governance"),
        ("attention_commit_authority", True),
        ("assessment_status", "ready"),
        ("unique_leader", 1),
        ("leader_ready_for_stability", 1),
        ("leader_candidate_id", ""),
        ("commit_assessment_fingerprint", "not-a-root"),
        ("commit_truth_root", ROOT_A),
        ("commit_assessment", object()),
        ("attention", object()),
        ("exploration_directive", object()),
    ),
)
def test_hybrid_binding_shape_is_total(
    hybrid_bundle,
    name: str,
    replacement: object,
) -> None:
    _, evaluation = hybrid_bundle
    step = _clone(evaluation.binding_step, **{name: replacement})
    with pytest.raises(GovernanceError):
        hybrid_binding._validate_hybrid_commit_step_shape(step)


def test_hybrid_binding_nonunique_and_source_guards(hybrid_bundle) -> None:
    _, evaluation = hybrid_bundle
    step = evaluation.binding_step
    with pytest.raises(GovernanceError, match="non-unique"):
        hybrid_binding._validate_hybrid_commit_step_shape(
            _clone(step, unique_leader=False)
        )
    with pytest.raises(GovernanceError, match="sha256"):
        hybrid_binding._require_sha256(object(), "root")
    hybrid_binding._validate_hybrid_commit_step_shape(
        _clone(step, unique_leader=False, leader_candidate_id="")
    )

    forged = _clone(step, run_id="run:forged")
    object.__setattr__(
        forged,
        "_issuance",
        (
            hybrid_binding._HYBRID_COMMIT_STEP_ISSUANCE,
            hybrid_binding.hybrid_commit_step_fingerprint(forged),
        ),
    )
    assert not hybrid_binding.hybrid_commit_step_is_authoritative(forged)

    missing_issuance = _clone(step)
    object.__delattr__(missing_issuance, "_issuance")
    assert not hybrid_binding.hybrid_commit_step_is_authoritative(missing_issuance)

    for name in (
        "commit_assessment",
        "attention",
        "exploration_directive",
    ):
        nested = _clone(getattr(step, name))
        object.__setattr__(nested, "_issuance", (object(), ROOT_A))
        candidate = _clone(step, **{name: nested})
        object.__setattr__(
            candidate,
            "_issuance",
            (
                hybrid_binding._HYBRID_COMMIT_STEP_ISSUANCE,
                hybrid_binding.hybrid_commit_step_fingerprint(candidate),
            ),
        )
        assert not hybrid_binding.hybrid_commit_step_is_authoritative(candidate)


@pytest.mark.parametrize(
    ("name", "replacement"),
    (
        ("evaluation_version", "unsupported"),
        ("status", "progress"),
        ("attention_status", "verified"),
        ("authoritative", 1),
        ("terminal", 1),
        ("assurance_downgraded", True),
        ("assurance", "evidence_bound"),
        ("profile", "pheroos-certified-commit-v1"),
        ("diagnostics", (object(),)),
    ),
)
def test_hybrid_evaluation_shape_scalar_guards(
    hybrid_bundle,
    name: str,
    replacement: object,
) -> None:
    _, evaluation = hybrid_bundle
    forged = _clone(evaluation, **{name: replacement})
    with pytest.raises(GovernanceError):
        hybrid_records._validate_hybrid_commit_evaluation_shape(forged)


def test_hybrid_evaluation_envelope_guards(hybrid_bundle) -> None:
    _, evaluation = hybrid_bundle
    diagnostic = hybrid_attention._attention_channel_diagnostic(
        "attention",
        request=object(),
    )
    invalid = (
        _clone(evaluation, binding_step_ref=""),
        _clone(evaluation, diagnostics=(diagnostic,)),
        _clone(
            evaluation,
            attention_status=hybrid_records.HybridCommitAttentionStatus.UNAVAILABLE,
            binding_step_ref="",
            attention_ref="",
            exploration_directive_ref="",
            diagnostics=(),
        ),
        _clone(
            evaluation,
            attention_status=hybrid_records.HybridCommitAttentionStatus.UNAVAILABLE,
            diagnostics=(diagnostic,),
        ),
        _clone(evaluation, assessment_ref=""),
        _clone(evaluation, terminal=True),
        _clone(
            evaluation,
            status=hybrid_records.HybridCommitEvaluationStatus.OUTCOME,
        ),
        _clone(
            evaluation,
            authoritative=False,
            status=hybrid_records.HybridCommitEvaluationStatus.PROGRESS,
        ),
        _clone(evaluation, trace_event_ids=()),
    )
    for forged in invalid:
        with pytest.raises(GovernanceError):
            hybrid_records._validate_hybrid_commit_evaluation_shape(forged)

    assert not hybrid_records._has_exact_attention_channel_diagnostic(())
    assert not hybrid_records._has_exact_attention_channel_diagnostic(
        (diagnostic, diagnostic)
    )
    assert not hybrid_records._has_exact_attention_channel_diagnostic(
        (_clone(diagnostic, message="forged"),)
    )
    with pytest.raises(GovernanceError, match="canonical"):
        hybrid_records.hybrid_commit_diagnostic_payload(object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="canonical"):
        hybrid_records.hybrid_commit_evaluation_payload(object())  # type: ignore[arg-type]


def test_hybrid_diagnostic_shape_guards() -> None:
    with pytest.raises(GovernanceError, match="severity"):
        hybrid_records.HybridCommitDiagnostic(
            code="invalid",
            severity="error",  # type: ignore[arg-type]
            stage="test",
            message="invalid severity",
            fatal=True,
        )
    with pytest.raises(GovernanceError, match="boolean"):
        hybrid_records.HybridCommitDiagnostic(
            code="invalid",
            severity=hybrid_records.HybridCommitDiagnosticSeverity.ERROR,
            stage="test",
            message="invalid fatal",
            fatal=1,  # type: ignore[arg-type]
        )
    diagnostic = hybrid_records._diagnostic_from_exception(
        "exception",
        "test",
        RuntimeError(),
        fatal=True,
    )
    assert diagnostic.message == "RuntimeError"


def test_hybrid_request_shape_and_fallback_refs(hybrid_bundle) -> None:
    request, _ = hybrid_bundle
    with pytest.raises(GovernanceError, match="version"):
        replace(request, request_version="unsupported")
    with pytest.raises(GovernanceError, match="governance authority"):
        replace(request, authority=AuthorityLevel.AGENT)
    with pytest.raises(GovernanceError, match="must be a mapping"):
        replace(request, trusted_issuer_attestations=object())  # type: ignore[arg-type]
    with pytest.raises(GovernanceError, match="canonical TraceEvent"):
        replace(request, prior_trace_events=(object(),))
    with pytest.raises(GovernanceError, match="canonical"):
        hybrid_request.hybrid_commit_evaluation_request_payload(object())  # type: ignore[arg-type]

    assert hybrid_request._attention_input_status(None) == "missing"
    assert hybrid_request._attention_input_status(object()) == "provided_invalid"
    assert (
        hybrid_request._exploration_directive_input_status(None, attention=None)
        == "missing"
    )
    assert (
        hybrid_request._exploration_directive_input_status(
            request.exploration_directive,
            attention=object(),
        )
        == "provided_invalid"
    )
    assert hybrid_request._safe_fingerprint(object(), lambda _: 1 / 0) == ""

    diagnostic = hybrid_records._diagnostic(
        "malformed_request",
        "request",
        "malformed request",
        fatal=True,
    )
    malformed = _clone(
        request,
        commit_policy=object(),
        prior_trace_events=(object(),),
        request_version=object(),
        request_id=object(),
        current_step=True,
        output_payload_fingerprint=object(),
        issuer_id=object(),
        authority=object(),
        provenance=object(),
        trace_event_id=object(),
    )
    fallback_ref = hybrid_request._issued_request_ref(
        malformed,
        (diagnostic,),
        profile=request.commit_assessment.profile,
    )
    assert fallback_ref.startswith("sha256:")
    invalid_trace = _clone(
        request.prior_trace_events[0],
        protocol_id="protocol:forged",
    )
    assert hybrid_request._issued_request_ref(
        _clone(request, prior_trace_events=(invalid_trace,)),
        (diagnostic,),
        profile=request.commit_assessment.profile,
    ).startswith("sha256:")
    assert hybrid_request._runtime_type_label(object()) == "builtins.object"
    with pytest.raises(GovernanceError, match="canonical"):
        hybrid_request._strict_trace_event_id(object())
    assert (
        hybrid_request._request_profile(_clone(request, commit_assessment=object()))
        == "pheroos-commit-integrity-v1"
    )
    assert (
        hybrid_request._request_profile(
            _clone(
                request,
                commit_assessment=_clone(
                    request.commit_assessment,
                    profile="invalid",
                ),
            )
        )
        == "pheroos-commit-integrity-v1"
    )
    assert (
        hybrid_request._safe_declared_assurance(object(), object())
        is CommitAssurance.ADVISORY
    )
    assert (
        hybrid_request._safe_declared_assurance(
            SimpleNamespace(assurance="not-valid"),
            SimpleNamespace(assurance="not-valid"),
        )
        is CommitAssurance.ADVISORY
    )
    assert (
        hybrid_request._safe_declared_assurance(
            _clone(request.commit_policy, assurance="not-valid"),
            request.commit_assessment,
        )
        is request.commit_assessment.assurance
    )
    assert (
        hybrid_request._safe_diagnostic_profile(
            object(),
            assurance=CommitAssurance.EVIDENCE_BOUND,
        )
        in hybrid_request.COMMIT_PROFILES_BY_ASSURANCE["evidence_bound"]
    )
    assert hybrid_request._safe_diagnostic_text(object(), "fallback") == "fallback"
    assert hybrid_request._safe_diagnostic_step(object()) == 0


def test_hybrid_preflight_authority_type_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    fields_to_break = (
        "commit_assessment",
        "context",
        "window_state",
        "replay_state",
        "commit_policy",
    )
    for name in fields_to_break:
        with pytest.raises(GovernanceError):
            hybrid_preflight._establish_authority_envelope(
                _clone(request, **{name: object()})
            )
    with pytest.raises(GovernanceError, match="precedes"):
        hybrid_preflight._establish_authority_envelope(
            _clone(
                request,
                current_step=evaluation.commit_window_state.last_evaluated_step - 1,
            )
        )

    other_request = hybrid_fixture._total_request(stable=False)
    with pytest.raises(GovernanceError, match="context"):
        hybrid_preflight._establish_authority_envelope(
            _clone(request, context=other_request.context)
        )
    with pytest.raises(GovernanceError, match="window"):
        hybrid_preflight._establish_authority_envelope(
            _clone(request, window_state=other_request.window_state)
        )
    with pytest.raises(GovernanceError, match="replay"):
        hybrid_preflight._establish_authority_envelope(
            _clone(request, replay_state=other_request.replay_state)
        )


def test_hybrid_preflight_head_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    assessment = evaluation.commit_assessment
    fields_to_break = (
        "risk_chain_state",
        "risk_assessment",
        "threshold_snapshot",
        "membership_snapshot",
        "membership_epoch_state",
        "support_replay_state",
    )
    for name in fields_to_break:
        with pytest.raises(GovernanceError):
            hybrid_preflight._validate_authority_heads(
                _clone(request, **{name: object()}),
                assessment=assessment,
            )
    other_request = hybrid_fixture._total_request(stable=False)
    with pytest.raises(GovernanceError, match="does not match"):
        hybrid_preflight._validate_authority_heads(
            _clone(request, risk_assessment=other_request.risk_assessment),
            assessment=assessment,
        )

    with pytest.raises(GovernanceError, match="requires prior"):
        hybrid_preflight._validated_prior_trace(
            _clone(request, prior_trace_events=()),
            assessment=assessment,
        )
    with pytest.raises(GovernanceError, match="identity"):
        hybrid_preflight._validated_prior_trace(
            _clone(request, prior_trace_events=other_request.prior_trace_events),
            assessment=assessment,
        )
    with pytest.raises(GovernanceError, match="required authority lineage"):
        hybrid_preflight._validated_prior_trace(
            _clone(request, prior_trace_events=(request.prior_trace_events[0],)),
            assessment=assessment,
        )


def test_outcome_certificate_public_failure_paths(outcome_bundle) -> None:
    scenario, window, outcome, output_ref, certificate = outcome_bundle
    with pytest.raises(GovernanceError, match="portable attestations"):
        issue_outcome_certificate(
            outcome,
            window,
            commit_policy=scenario.policy,
            output_payload_fingerprint=output_ref,
            certificate_id=f"outcome-certificate:{scenario.run_id}:bad-attestation",
            context=scenario.context,
            assessment=None,
            issuer_attestation_refs=("attestation:forged",),
            trusted_issuer_attestations={"attestation:forged": ROOT_A},
            issuer_id="governance:totality",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=outcome.current_step,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:outcome",
        )
    assert not certificate_outcome.outcome_certificate_is_authoritative(object())
    assert not certificate_outcome.outcome_certificate_is_authoritative(
        _clone(certificate, profile=object())
    )

    payload = certificate_outcome.outcome_certificate_payload(certificate)
    decoded = certificate_outcome.outcome_certificate_from_payload(payload)
    assert not certificate_outcome.verify_outcome_certificate(decoded)
    assert not certificate_outcome.verify_outcome_certificate(
        certificate,
        expected_certificate_ref=ROOT_A,
    )
    assert not certificate_outcome.verify_outcome_certificate(
        certificate,
        expected_output_payload_fingerprint=ROOT_A,
    )


def test_outcome_certificate_body_guards(outcome_bundle) -> None:
    scenario, window, outcome, output_ref, _ = outcome_bundle
    body_kwargs = {
        "commit_policy": scenario.policy,
        "output_fingerprint": output_ref,
        "certificate_id": "outcome-certificate:body-totality",
        "context": scenario.context,
        "assessment": None,
        "issuer_id": "governance:totality",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": outcome.current_step,
        "provenance": "urn:test:totality",
        "trace_event_id": "trace:totality:outcome-body",
    }
    invalid_inputs = (
        (object(), window, {}),
        (outcome, object(), {}),
        (outcome, window, {"authority": AuthorityLevel.AGENT}),
    )
    for candidate_outcome, candidate_window, changes in invalid_inputs:
        with pytest.raises(GovernanceError):
            certificate_outcome._outcome_certificate_body(
                candidate_outcome,  # type: ignore[arg-type]
                candidate_window,  # type: ignore[arg-type]
                **(body_kwargs | changes),
            )

    with pytest.raises(GovernanceError, match="window profile mismatch"):
        certificate_outcome._validate_outcome_certificate_window(
            _clone(outcome, profile="pheroos-other-profile"),
            window,
        )
    with pytest.raises(GovernanceError, match="window lineage mismatch"):
        certificate_outcome._validate_outcome_certificate_window(
            _clone(outcome, window_state_ref=ROOT_A),
            window,
        )
    with pytest.raises(GovernanceError, match="risk_chain_state_root lineage"):
        certificate_outcome._validate_outcome_certificate_window(
            _clone(outcome, risk_chain_state_root=ROOT_A),
            window,
        )

    with pytest.raises(GovernanceError, match="not authoritative"):
        certificate_outcome._outcome_certificate_context(outcome, object())
    with pytest.raises(GovernanceError, match="context ref mismatch"):
        certificate_outcome._outcome_certificate_context(
            _clone(outcome, context_ref=ROOT_A),
            scenario.context,
        )
    with pytest.raises(GovernanceError, match="undeclared"):
        certificate_outcome._outcome_certificate_context(
            _clone(outcome, candidate_id="candidate:undeclared"),
            scenario.context,
        )
    with pytest.raises(GovernanceError, match="claim-bound context"):
        certificate_outcome._outcome_certificate_context(outcome, None)
    with pytest.raises(GovernanceError, match="predate"):
        certificate_outcome._require_outcome_certificate_issue_step(
            outcome.current_step - 1,
            outcome=outcome,
        )


def test_outcome_certificate_assessment_guards() -> None:
    (
        scenario,
        assessment,
        _,
        _,
        _,
        outcome,
    ) = outcome_fixture._evidence_commit_outcome()
    with pytest.raises(GovernanceError, match="not authoritative"):
        certificate_outcome._outcome_certificate_assessment(outcome, None)
    with pytest.raises(GovernanceError, match="assessment ref mismatch"):
        certificate_outcome._outcome_certificate_assessment(
            _clone(outcome, assessment_ref=ROOT_A),
            assessment,
        )
    with pytest.raises(GovernanceError, match="assessment context mismatch"):
        certificate_outcome._outcome_certificate_assessment(
            _clone(outcome, context_ref=ROOT_A),
            assessment,
        )
    with pytest.raises(GovernanceError, match="risk_chain_state_root"):
        certificate_outcome._outcome_certificate_assessment(
            _clone(outcome, risk_chain_state_root=ROOT_A),
            assessment,
        )

    _, _, fallback = outcome_fixture._nonready_outcome(
        DecisionOutcomeKind.SAFE_FALLBACK
    )
    with pytest.raises(GovernanceError, match="unbound assessment"):
        certificate_outcome._outcome_certificate_assessment(
            fallback,
            assessment,
        )
    assert scenario.context.protocol_id == outcome.protocol_id


def test_certificate_remaining_record_guards(portable_bundle, outcome_bundle) -> None:
    _, portable = portable_bundle
    evidence = portable.certificate
    with pytest.raises(GovernanceError, match="certified or distributed"):
        certificate_records._validate_evidence_commit_certificate(
            _clone(
                evidence,
                assurance=CommitAssurance.EVIDENCE_BOUND,
                profile="pheroos-commit-integrity-v1",
            )
        )

    _, _, _, _, fallback = outcome_bundle
    with pytest.raises(GovernanceError, match="portable outcome"):
        certificate_records._validate_outcome_attestations(
            _clone(
                fallback,
                assurance=CommitAssurance.CERTIFIED,
                profile=hybrid_fixture.CERTIFIED_COMMIT_PROFILE_VERSION,
                issuer_attestation_refs=(),
            )
        )


def test_local_and_portable_remaining_totality(
    local_bundle,
    portable_bundle,
) -> None:
    scenario, assessment, window, _, receipt = local_bundle
    other_window = outcome_fixture._initial_window(
        certificate_fixture.engine_fixture._scenario()
    )
    with pytest.raises(GovernanceError, match="current receipt seal"):
        certificate_local.verify_local_commit_finality(
            receipt,
            scenario.context,
            assessment,
            other_window,
            commit_policy=scenario.policy,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            current_step=receipt.issued_at_step,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:seal",
        )
    with pytest.raises(GovernanceError, match="does not verify"):
        certificate_local.verify_local_commit_finality(
            receipt,
            object(),  # type: ignore[arg-type]
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
            current_step=receipt.issued_at_step,
            verifier_id="verifier:totality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:heads",
        )
    with pytest.raises(GovernanceError, match="window state"):
        certificate_local._validate_local_receipt_authority(
            scenario.context,
            assessment=assessment,
            window_state=object(),  # type: ignore[arg-type]
            commit_policy=scenario.policy,
        )
    assert not certificate_local._current_authority_heads_match_receipt(
        object(),  # type: ignore[arg-type]
        context=scenario.context,
        assessment=assessment,
        window_state=window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=receipt.issued_at_step,
    )

    stable, portable = portable_bundle
    with pytest.raises(GovernanceError, match="authoritative local receipt"):
        certificate_portable._evidence_certificate_body_from_receipt(
            object(),  # type: ignore[arg-type]
            certificate_id="certificate:bad",
            issuer_id="issuer:bad",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=1,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )
    with pytest.raises(GovernanceError, match="certified or distributed"):
        certificate_portable._evidence_certificate_body_from_receipt(
            receipt,
            certificate_id="certificate:bad",
            issuer_id="issuer:bad",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=receipt.issued_at_step,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        certificate_portable._evidence_certificate_body_from_receipt(
            stable.receipt,
            certificate_id="certificate:bad",
            issuer_id="issuer:bad",
            authority=AuthorityLevel.AGENT,
            issued_at_step=stable.receipt.issued_at_step,
            provenance="urn:test:bad",
            trace_event_id="trace:bad",
        )
    finality_kwargs = {
        "commit_policy": stable.scenario.policy,
        "risk_chain_state": stable.scenario.risk_chain_state,
        "risk_assessment": stable.scenario.risk_assessment,
        "threshold_snapshot": stable.scenario.threshold,
        "membership_snapshot": stable.scenario.membership_snapshot,
        "membership_epoch_state": stable.scenario.membership_state,
        "replay_state": stable.scenario.replay_state,
        "support_replay_state": stable.scenario.support_replay_state,
        "trusted_issuer_attestations": portable.trusted_issuer_attestations,
        "current_step": stable.receipt.issued_at_step - 1,
        "verifier_id": "verifier:portable",
        "authority": AuthorityLevel.GOVERNANCE,
        "provenance": "urn:test:portable",
        "trace_event_id": "trace:portable:stale",
    }
    with pytest.raises(GovernanceError, match="current authority heads"):
        certificate_portable.verify_evidence_commit_finality(
            portable.certificate,
            stable.receipt,
            stable.scenario.context,
            stable.assessments[-1],
            stable.window,
            **finality_kwargs,
        )


def test_hybrid_authority_prefix_guards(hybrid_bundle) -> None:
    _, evaluation = hybrid_bundle
    assessment = evaluation.commit_assessment
    window = evaluation.commit_window_state
    replay = evaluation.commit_replay_state
    invalid = (
        {"commit_assessment": object()},
        {"commit_assessment": _clone(assessment, reason_codes=("forged",))},
        {"assessment_ref": ROOT_A},
        {"commit_window_state": _clone(window, reset_reason="forged")},
        {"window_state_ref": ROOT_A},
        {"window_root": ROOT_A},
        {"commit_replay_state": _clone(replay, receipt_root=ROOT_A)},
        {"replay_state_ref": ROOT_A},
        {"replay_root": ROOT_A},
    )
    for changes in invalid:
        forged = _reissue_hybrid_evaluation(evaluation, **changes)
        assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(forged), (
            changes
        )


def test_hybrid_authority_attention_guards(hybrid_bundle) -> None:
    _, evaluation = hybrid_bundle
    step = evaluation.binding_step
    attention = evaluation.attention
    directive = evaluation.exploration_directive
    invalid = (
        {"binding_step": object()},
        {"binding_step": _clone(step, run_id="run:forged")},
        {"binding_step_ref": ROOT_A},
        {"attention": object()},
        {"attention": _clone(attention, memory_root=ROOT_A)},
        {"attention_ref": ROOT_A},
        {"exploration_directive": object()},
        {"exploration_directive_ref": ROOT_A},
        {
            "exploration_directive": _clone(
                directive,
                source_attention_fingerprint=ROOT_A,
            )
        },
        {
            "exploration_directive": _clone(
                directive,
                protocol_id="protocol:forged",
            )
        },
        {
            "exploration_directive": _clone(
                directive,
                target="decision:forged",
            )
        },
        {
            "exploration_directive": _clone(
                directive,
                current_step=directive.current_step + 1,
            )
        },
    )
    for changes in invalid:
        forged = _reissue_hybrid_evaluation(evaluation, **changes)
        assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(forged), (
            changes
        )

    unavailable = evaluate_hybrid_commit_step(
        request=_clone(
            hybrid_fixture._total_request(stable=False),
            attention=object(),
            exploration_directive=object(),
        )
    )
    assert unavailable.authoritative
    injected = _reissue_hybrid_evaluation(
        unavailable,
        binding_step=step,
    )
    assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(injected)

    other = evaluate_hybrid_commit_step(
        request=hybrid_fixture._total_request(stable=False)
    )
    cross_directive = _reissue_hybrid_evaluation(
        evaluation,
        exploration_directive=other.exploration_directive,
        exploration_directive_ref=other.exploration_directive_ref,
    )
    assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(cross_directive)


def test_hybrid_authority_decision_and_optional_guards(hybrid_bundle) -> None:
    _, progress_evaluation = hybrid_bundle
    invalid_progress = (
        {"decision_progress": object()},
        {"progress_ref": ROOT_A},
        {"decision_outcome": object()},
        {"local_receipt": object()},
        {"deliver_authorization_ref": ROOT_A},
        {"deliver_authorization": object(), "deliver_authorization_ref": ROOT_A},
        {"trace_root": ROOT_A},
    )
    for changes in invalid_progress:
        forged = _reissue_hybrid_evaluation(progress_evaluation, **changes)
        assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(forged)

    terminal_request = hybrid_fixture._total_request(stable=True)
    terminal = evaluate_hybrid_commit_step(request=terminal_request)
    assert terminal.authoritative
    invalid_terminal = (
        {"decision_outcome": object()},
        {"outcome_ref": ROOT_A},
        {"decision_progress": object()},
        {
            "deliver_authorization": None,
            "deliver_authorization_ref": "",
        },
    )
    for changes in invalid_terminal:
        forged = _reissue_hybrid_evaluation(terminal, **changes)
        assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(forged)

    deliver = terminal.deliver_authorization
    progress_with_output = _reissue_hybrid_evaluation(
        progress_evaluation,
        deliver_authorization=deliver,
        deliver_authorization_ref=terminal.deliver_authorization_ref,
    )
    assert not hybrid_commit.hybrid_commit_evaluation_is_authoritative(
        progress_with_output
    )


def test_hybrid_optional_record_and_distributed_totality(hybrid_bundle) -> None:
    _, evaluation = hybrid_bundle
    assert hybrid_commit._optional_record_matches(
        None,
        "",
        expected_type=object,
        fingerprint=lambda _: ROOT_A,
    )
    assert not hybrid_commit._optional_record_matches(
        None,
        ROOT_A,
        expected_type=object,
        fingerprint=lambda _: ROOT_A,
    )
    assert not hybrid_commit._optional_record_matches(
        object(),
        "",
        expected_type=str,
        fingerprint=lambda _: ROOT_A,
    )
    assert not hybrid_commit._optional_record_matches(
        evaluation.commit_window_state,
        ROOT_A,
        expected_type=type(evaluation.commit_window_state),
        fingerprint=lambda _: ROOT_A,
        authoritative=lambda _: False,
    )
    assert not hybrid_commit._distributed_certificate_registered_final(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )


def test_hybrid_window_transition_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    with pytest.raises(GovernanceError, match="current-step assessment"):
        hybrid_commit._advance_window_if_required(
            _clone(request, current_step=request.current_step + 1),
            assessment=evaluation.commit_assessment,
            window_state=evaluation.commit_window_state,
            commit_policy=request.commit_policy,
        )
    other = evaluate_hybrid_commit_step(
        request=hybrid_fixture._total_request(stable=False)
    )
    with pytest.raises(GovernanceError, match="window head"):
        hybrid_commit._advance_window_if_required(
            request,
            assessment=other.commit_assessment,
            window_state=evaluation.commit_window_state,
            commit_policy=request.commit_policy,
        )


def test_hybrid_finality_advisory_and_local_guards(
    hybrid_bundle,
    local_bundle,
) -> None:
    request, evaluation = hybrid_bundle
    scenario, assessment, window, _, receipt = local_bundle
    common = {
        "context": scenario.context,
        "assessment": assessment,
        "window_state": window,
        "replay_state": scenario.replay_state,
        "commit_policy": scenario.policy,
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "support_replay_state": scenario.support_replay_state,
    }
    advisory_assessment = _clone(
        evaluation.commit_assessment,
        assurance=CommitAssurance.ADVISORY,
    )
    with pytest.raises(GovernanceError, match="advisory assurance"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, local_receipt=object()),
            **(
                common
                | {
                    "context": evaluation.commit_assessment
                    and evaluation.commit_window_state
                    and request.context,
                    "assessment": advisory_assessment,
                    "window_state": evaluation.commit_window_state,
                    "replay_state": evaluation.commit_replay_state,
                    "commit_policy": request.commit_policy,
                    "risk_chain_state": request.risk_chain_state,
                    "risk_assessment": request.risk_assessment,
                    "threshold_snapshot": request.threshold_snapshot,
                    "membership_snapshot": request.membership_snapshot,
                    "membership_epoch_state": request.membership_epoch_state,
                    "support_replay_state": request.support_replay_state,
                }
            ),
        )
    result = hybrid_finality._resolve_declared_finality(
        request,
        **(
            common
            | {
                "context": request.context,
                "assessment": advisory_assessment,
                "window_state": evaluation.commit_window_state,
                "replay_state": evaluation.commit_replay_state,
                "commit_policy": request.commit_policy,
                "risk_chain_state": request.risk_chain_state,
                "risk_assessment": request.risk_assessment,
                "threshold_snapshot": request.threshold_snapshot,
                "membership_snapshot": request.membership_snapshot,
                "membership_epoch_state": request.membership_epoch_state,
                "support_replay_state": request.support_replay_state,
            }
        ),
    )
    assert result[5].value == "not_required"

    with pytest.raises(GovernanceError, match="malformed or forged"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, local_receipt=object()),
            **(
                common
                | {
                    "context": request.context,
                    "assessment": evaluation.commit_assessment,
                    "window_state": evaluation.commit_window_state,
                    "replay_state": evaluation.commit_replay_state,
                    "commit_policy": request.commit_policy,
                    "risk_chain_state": request.risk_chain_state,
                    "risk_assessment": request.risk_assessment,
                    "threshold_snapshot": request.threshold_snapshot,
                    "membership_snapshot": request.membership_snapshot,
                    "membership_epoch_state": request.membership_epoch_state,
                    "support_replay_state": request.support_replay_state,
                }
            ),
        )
    with pytest.raises(GovernanceError, match="lacks a local receipt"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, evidence_certificate=object()),
            **(
                common
                | {
                    "context": request.context,
                    "assessment": evaluation.commit_assessment,
                    "window_state": evaluation.commit_window_state,
                    "replay_state": evaluation.commit_replay_state,
                    "commit_policy": request.commit_policy,
                    "risk_chain_state": request.risk_chain_state,
                    "risk_assessment": request.risk_assessment,
                    "threshold_snapshot": request.threshold_snapshot,
                    "membership_snapshot": request.membership_snapshot,
                    "membership_epoch_state": request.membership_epoch_state,
                    "support_replay_state": request.support_replay_state,
                }
            ),
        )

    stable_request = _clone(
        request,
        commit_assessment=assessment,
        context=scenario.context,
        window_state=window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=receipt.issued_at_step,
        output_payload_fingerprint=receipt.output_payload_fingerprint,
        local_receipt=receipt,
        evidence_certificate=object(),
    )
    with pytest.raises(GovernanceError, match="higher proof"):
        hybrid_finality._resolve_declared_finality(
            stable_request,
            **common,
        )


def test_hybrid_finality_portable_guards(portable_bundle) -> None:
    stable, portable = portable_bundle
    request = _stable_hybrid_request(stable)
    scenario = stable.scenario
    common = {
        "context": scenario.context,
        "assessment": stable.assessments[-1],
        "window_state": stable.window,
        "replay_state": scenario.replay_state,
        "commit_policy": scenario.policy,
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "support_replay_state": scenario.support_replay_state,
    }
    pending = hybrid_finality._resolve_declared_finality(request, **common)
    assert pending[5].value == "provisional"
    assert pending[-1] == ("evidence_commit_certificate",)
    with pytest.raises(GovernanceError):
        hybrid_finality._resolve_declared_finality(
            _clone(
                request,
                issuer_attestation_refs=portable.certificate.issuer_attestation_refs,
                trusted_issuer_attestations=portable.trusted_issuer_attestations,
            ),
            **common,
        )

    with pytest.raises(GovernanceError, match="not canonical"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, evidence_certificate=object()),
            **common,
        )
    with pytest.raises(GovernanceError, match="verification failed"):
        hybrid_finality._resolve_declared_finality(
            _clone(
                request,
                evidence_certificate=portable.certificate,
                trusted_issuer_attestations={},
            ),
            **common,
        )
    with pytest.raises(GovernanceError, match="distributed finality"):
        hybrid_finality._resolve_declared_finality(
            _clone(
                request,
                evidence_certificate=portable.certificate,
                trusted_issuer_attestations=portable.trusted_issuer_attestations,
                distributed_state=object(),
            ),
            **common,
        )


def test_hybrid_finality_distributed_guards() -> None:
    bundle = hybrid_fixture._distributed_fixture(
        witness_count=0,
        variant="legacy-totality-finality",
    )
    request = hybrid_fixture._distributed_request(
        bundle,
        suffix="legacy-totality-finality",
    )
    stable = bundle.portable.stable
    scenario = stable.scenario
    common = {
        "context": scenario.context,
        "assessment": stable.assessments[-1],
        "window_state": stable.window,
        "replay_state": scenario.replay_state,
        "commit_policy": scenario.policy,
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "support_replay_state": scenario.support_replay_state,
    }
    no_state = hybrid_finality._resolve_declared_finality(
        _clone(request, distributed_state=None),
        **common,
    )
    assert no_state[-1] == ("distributed_commit_state",)
    with pytest.raises(GovernanceError, match="lacks its state"):
        hybrid_finality._resolve_declared_finality(
            _clone(
                request,
                distributed_state=None,
                distributed_certificate=object(),
            ),
            **common,
        )
    with pytest.raises(GovernanceError, match="malformed, forged, or stale"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, distributed_state=object()),
            **common,
        )
    provisional = hybrid_finality._resolve_declared_finality(request, **common)
    assert provisional[-1] == ("distributed_commit_certificate",)
    with pytest.raises(GovernanceError, match="not canonical"):
        hybrid_finality._resolve_declared_finality(
            _clone(request, distributed_certificate=object()),
            **common,
        )
    with pytest.raises(GovernanceError, match="lacks its portable proof"):
        hybrid_finality._resolve_declared_finality(
            _clone(
                request,
                evidence_certificate=None,
                issuer_attestation_refs=(),
                distributed_certificate=object(),
            ),
            **common,
        )


def test_hybrid_distributed_finality_and_trace_are_total() -> None:
    bundle = hybrid_fixture._distributed_fixture(
        witness_count=3,
        variant="legacy-totality-final",
    )
    stable = bundle.portable.stable
    scenario = stable.scenario
    certificate = issue_reference_distributed_certificate(
        bundle,
        witness_count=scenario.policy.distributed.witness_quorum,
        variant="legacy-totality-final",
    )
    unregistered_request = hybrid_fixture._distributed_request(
        bundle,
        distributed_state=bundle.state,
        distributed_certificate=certificate,
        suffix="legacy-totality-final",
    )
    common = {
        "context": scenario.context,
        "assessment": stable.assessments[-1],
        "window_state": stable.window,
        "replay_state": scenario.replay_state,
        "commit_policy": scenario.policy,
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "support_replay_state": scenario.support_replay_state,
    }
    with pytest.raises(GovernanceError, match="verification failed"):
        hybrid_finality._resolve_declared_finality(
            _clone(unregistered_request, trusted_witness_attestations={}),
            **common,
        )
    with pytest.raises(GovernanceError, match="not current"):
        hybrid_finality._resolve_declared_finality(
            unregistered_request,
            **common,
        )

    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=scenario.policy,
        portable_certificate=bundle.portable.certificate,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    request = hybrid_fixture._distributed_request(
        bundle,
        distributed_state=registered,
        distributed_certificate=certificate,
        suffix="legacy-totality-final",
    )
    result = evaluate_hybrid_commit_step(request=request)
    assert result.authoritative
    assert result.terminal
    assert result.distributed_certificate is certificate


def test_hybrid_outcome_certificate_resolution(
    outcome_bundle,
    portable_bundle,
) -> None:
    scenario, window, outcome, output_ref, certificate = outcome_bundle
    stable, _ = portable_bundle
    request = _stable_hybrid_request(stable)
    with pytest.raises(GovernanceError, match="not canonical"):
        hybrid_finality._resolve_outcome_certificate(
            _clone(request, outcome_certificate=object()),
            outcome=outcome,
            window_state=window,
            context=scenario.context,
            assessment=stable.assessments[-1],
            commit_policy=scenario.policy,
        )
    with pytest.raises(GovernanceError, match="verification failed"):
        hybrid_finality._resolve_outcome_certificate(
            _clone(request, outcome_certificate=certificate),
            outcome=_clone(outcome, outcome_ref=ROOT_A),
            window_state=window,
            context=scenario.context,
            assessment=stable.assessments[-1],
            commit_policy=scenario.policy,
        )
    supplied = hybrid_finality._resolve_outcome_certificate(
        _clone(
            request,
            outcome_certificate=certificate,
            output_payload_fingerprint=output_ref,
        ),
        outcome=outcome,
        window_state=window,
        context=scenario.context,
        assessment=stable.assessments[-1],
        commit_policy=scenario.policy,
    )
    assert supplied is certificate
    with pytest.raises(GovernanceError):
        hybrid_finality._resolve_outcome_certificate(
            _clone(request, output_payload_fingerprint=output_ref),
            outcome=outcome,
            window_state=window,
            context=scenario.context,
            assessment=stable.assessments[-1],
            commit_policy=scenario.policy,
        )
    assert (
        hybrid_finality._resolve_outcome_certificate(
            request,
            outcome=outcome,
            window_state=window,
            context=scenario.context,
            assessment=stable.assessments[-1],
            commit_policy=stable.scenario.policy,
        )
        is None
    )


def test_hybrid_pipeline_failure_conversions(hybrid_bundle, outcome_bundle) -> None:
    request, _ = hybrid_bundle
    invalid_window = evaluate_hybrid_commit_step(
        request=_clone(request, current_step=request.current_step + 1)
    )
    assert any(
        item.code == "invalid_window_transition" for item in invalid_window.diagnostics
    )

    other = evaluate_hybrid_commit_step(
        request=hybrid_fixture._total_request(stable=False)
    )
    invalid_liveness = evaluate_hybrid_commit_step(
        request=_clone(request, previous_progress=other.decision_progress)
    )
    assert any(
        item.code == "liveness_authority_unavailable"
        for item in invalid_liveness.diagnostics
    )

    scenario, window, outcome, _, _ = outcome_bundle
    deadline = _clone(
        request,
        request_id=f"{request.request_id}:deadline-totality",
        current_step=request.window_state.absolute_deadline_step,
        outcome_certificate=object(),
        trace_event_id=f"{request.trace_event_id}:deadline-totality",
    )
    outcome_failure = evaluate_hybrid_commit_step(request=deadline)
    assert any(
        item.code == "outcome_certificate_unavailable"
        for item in outcome_failure.diagnostics
    )
    assert scenario.context.protocol_id == outcome.protocol_id
    assert window.window_root == outcome.window_root

    foreign_trace = (_clone(other.trace_events[0], protocol_id="protocol:forged"),)
    self_check = hybrid_pipeline.evaluate_hybrid_commit_step(
        request=request,
        _trace_builder=lambda *args, **kwargs: foreign_trace,
    )
    assert not self_check.authoritative
    assert any(
        item.code == "issued_evaluation_self_verification_failed"
        for item in self_check.diagnostics
    )

    def failed_trace(*args, **kwargs):
        raise GovernanceError("forced trace failure")

    fail_closed = hybrid_pipeline.evaluate_hybrid_commit_step(
        request=request,
        _trace_builder=failed_trace,
    )
    assert any(
        item.code == "fail_closed_outcome_unavailable"
        for item in fail_closed.diagnostics
    )


def test_hybrid_preflight_remaining_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    changed_terminal = replace(
        request.commit_policy.terminal_outcome,
        deliverable_outcomes=["invalid"],
    )
    changed_policy = replace(
        request.commit_policy,
        terminal_outcome=changed_terminal,
    )
    with pytest.raises(GovernanceError, match="policy root"):
        hybrid_preflight._establish_authority_envelope(
            _clone(request, commit_policy=changed_policy)
        )

    terminal_request = hybrid_fixture._total_request(stable=True)
    terminal = evaluate_hybrid_commit_step(request=terminal_request)
    with pytest.raises(GovernanceError, match="terminal result"):
        hybrid_preflight._validated_prior_trace(
            _clone(
                terminal_request,
                prior_trace_events=terminal.trace_events,
            ),
            assessment=terminal.commit_assessment,
        )
    with pytest.raises(GovernanceError, match="future logical step"):
        hybrid_preflight._validated_prior_trace(
            _clone(
                request,
                prior_trace_events=evaluation.trace_events,
                current_step=0,
            ),
            assessment=evaluation.commit_assessment,
        )
    other = hybrid_fixture._total_request(stable=False)
    with pytest.raises(GovernanceError, match="current authority head"):
        hybrid_preflight._validated_prior_trace(
            _clone(request, risk_assessment=other.risk_assessment),
            assessment=evaluation.commit_assessment,
        )
    metrics = evaluation.commit_assessment.candidate_metrics
    uncovered_metric = _clone(
        metrics[0],
        evidence_binding_fingerprint=ROOT_A,
    )
    with pytest.raises(GovernanceError, match="does not cover"):
        hybrid_preflight._validated_prior_trace(
            request,
            assessment=_clone(
                evaluation.commit_assessment,
                candidate_metrics=(*metrics, uncovered_metric),
            ),
        )


def test_hybrid_trace_distributed_provisional_paths() -> None:
    zero_bundle = hybrid_fixture._distributed_fixture(
        witness_count=0,
        variant="legacy-totality-trace-zero",
    )
    zero_request = hybrid_fixture._distributed_request(
        zero_bundle,
        suffix="legacy-totality-trace-zero",
    )
    zero_result = evaluate_hybrid_commit_step(request=zero_request)
    window_event = next(
        event
        for event in zero_result.trace_events
        if event.event_type in {"commit_window_advanced", "commit_window_reset"}
    )
    portable_event = hybrid_trace._certificate_trace_event(
        zero_request,
        certificate=zero_bundle.portable.certificate,
        certificate_kind="evidence_commit",
        final=False,
        previous=(window_event,),
    )
    with pytest.raises(GovernanceError, match="portable certificate event"):
        hybrid_trace._append_distributed_witness_trace(
            zero_request,
            events=[window_event],
            window_event=window_event,
            portable_certificate_event=None,
            distributed_state=zero_bundle.state,
            distributed_certificate=None,
        )
    events = [window_event, portable_event]
    lineage = hybrid_trace._append_distributed_witness_trace(
        zero_request,
        events=events,
        window_event=window_event,
        portable_certificate_event=portable_event,
        distributed_state=zero_bundle.state,
        distributed_certificate=None,
    )
    assert lineage[-1].event_type == "commit_provisional"
    assert (
        hybrid_trace._append_distributed_witness_trace(
            zero_request,
            events=events,
            window_event=window_event,
            portable_certificate_event=portable_event,
            distributed_state=zero_bundle.state,
            distributed_certificate=None,
        )
        == lineage
    )

    witness_bundle = hybrid_fixture._distributed_fixture(
        witness_count=1,
        variant="legacy-totality-trace-witness",
    )
    witness_request = hybrid_fixture._distributed_request(
        witness_bundle,
        suffix="legacy-totality-trace-witness",
    )
    witness_result = evaluate_hybrid_commit_step(request=witness_request)
    witness_window = next(
        event
        for event in witness_result.trace_events
        if event.event_type in {"commit_window_advanced", "commit_window_reset"}
    )
    witness_portable = hybrid_trace._certificate_trace_event(
        witness_request,
        certificate=witness_bundle.portable.certificate,
        certificate_kind="evidence_commit",
        final=False,
        previous=(witness_window,),
    )
    witness_events = [witness_window, witness_portable]
    witness_lineage = hybrid_trace._append_distributed_witness_trace(
        witness_request,
        events=witness_events,
        window_event=witness_window,
        portable_certificate_event=witness_portable,
        distributed_state=witness_bundle.state,
        distributed_certificate=None,
    )
    assert {item.event_type for item in witness_lineage} == {
        "quorum_witness",
        "commit_provisional",
    }
    assert (
        hybrid_trace._append_distributed_witness_trace(
            witness_request,
            events=witness_events,
            window_event=witness_window,
            portable_certificate_event=witness_portable,
            distributed_state=witness_bundle.state,
            distributed_certificate=None,
        )
        == witness_lineage
    )

    invalid_verification = _clone(
        witness_bundle.verifications[0],
        trace_event_id="trace:forged-witness-verification",
    )
    with pytest.raises(GovernanceError, match="not authoritative"):
        hybrid_trace._append_distributed_witness_trace(
            witness_request,
            events=[witness_window, witness_portable],
            window_event=witness_window,
            portable_certificate_event=witness_portable,
            distributed_state=_clone(
                witness_bundle.state,
                witness_verifications=(invalid_verification,),
            ),
            distributed_certificate=None,
        )

    conflicting_bundle = hybrid_fixture._distributed_fixture(
        witness_count=1,
        variant="legacy-totality-trace-conflict",
    )
    with pytest.raises(GovernanceError, match="conflicting commit values"):
        hybrid_trace._append_distributed_witness_trace(
            witness_request,
            events=[witness_window, witness_portable],
            window_event=witness_window,
            portable_certificate_event=witness_portable,
            distributed_state=_clone(
                witness_bundle.state,
                witness_verifications=(
                    witness_bundle.verifications[0],
                    conflicting_bundle.verifications[0],
                ),
            ),
            distributed_certificate=None,
        )
    frozen_conflict = hybrid_trace._append_distributed_witness_trace(
        witness_request,
        events=[witness_window, witness_portable],
        window_event=witness_window,
        portable_certificate_event=witness_portable,
        distributed_state=_clone(
            witness_bundle.state,
            frozen=True,
            witness_verifications=(
                witness_bundle.verifications[0],
                conflicting_bundle.verifications[0],
            ),
        ),
        distributed_certificate=None,
    )
    assert all(item.event_type == "quorum_witness" for item in frozen_conflict)


def test_hybrid_trace_totality_guards(hybrid_bundle) -> None:
    request, evaluation = hybrid_bundle
    with pytest.raises(GovernanceError, match="policy is not canonical"):
        hybrid_trace._build_evaluation_trace(
            _clone(request, commit_policy=object()),
            prior_trace=(),
            assessment=evaluation.commit_assessment,
            window_state=evaluation.commit_window_state,
            progress=evaluation.decision_progress,
            outcome=None,
            local_receipt=None,
            evidence_certificate=None,
            distributed_state=None,
            distributed_certificate=None,
            outcome_certificate=None,
            deliver=None,
            publish=None,
            execute=None,
            invalid_path=False,
        )
    with pytest.raises(GovernanceError, match="lacks outcome or delivery"):
        hybrid_trace._build_evaluation_trace(
            request,
            prior_trace=(),
            assessment=evaluation.commit_assessment,
            window_state=evaluation.commit_window_state,
            progress=None,
            outcome=None,
            local_receipt=None,
            evidence_certificate=None,
            distributed_state=None,
            distributed_certificate=None,
            outcome_certificate=None,
            deliver=None,
            publish=None,
            execute=None,
            invalid_path=True,
        )
    with pytest.raises(GovernanceError, match="lacks outcome or delivery"):
        hybrid_trace._build_evaluation_trace(
            request,
            prior_trace=(),
            assessment=evaluation.commit_assessment,
            window_state=evaluation.commit_window_state,
            progress=None,
            outcome=None,
            local_receipt=None,
            evidence_certificate=None,
            distributed_state=None,
            distributed_certificate=None,
            outcome_certificate=None,
            deliver=None,
            publish=None,
            execute=None,
            invalid_path=False,
        )
    assert (
        hybrid_trace._build_evaluation_trace(
            request,
            prior_trace=evaluation.trace_events,
            assessment=evaluation.commit_assessment,
            window_state=evaluation.commit_window_state,
            progress=evaluation.decision_progress,
            outcome=None,
            local_receipt=None,
            evidence_certificate=None,
            distributed_state=None,
            distributed_certificate=None,
            outcome_certificate=None,
            deliver=None,
            publish=None,
            execute=None,
            invalid_path=False,
        )
        == evaluation.trace_events
    )
    with pytest.raises(GovernanceError, match="not canonical"):
        hybrid_trace._certificate_trace_event(
            request,
            certificate=object(),
            certificate_kind="invalid",
            final=False,
            previous=(),
        )
    with pytest.raises(GovernanceError, match="not canonical"):
        hybrid_trace._certificate_fingerprint(object())


def test_hybrid_trace_action_and_output_branches() -> None:
    request = hybrid_fixture._total_request(stable=True)
    result = evaluate_hybrid_commit_step(request=request)
    outcome = result.decision_outcome
    outcome_event = hybrid_trace._decision_outcome_trace_event(
        request,
        outcome,
        previous=(),
    )
    _, _, _, _, _, evidence_outcome = outcome_fixture._evidence_commit_outcome()
    assert (
        hybrid_trace._decision_outcome_trace_event(
            request,
            evidence_outcome,
            previous=(),
        ).lineage["assessment_ref"]
        == evidence_outcome.assessment_ref
    )
    publish_stop, publish_permission = hybrid_fixture._action_facts(
        result,
        action=hybrid_fixture.CommitAction.PUBLISH,
        suffix="legacy-totality-trace",
    )
    forged_stop = _clone(
        publish_stop,
        trace_event_id="trace:forged-stop",
    )
    forged_permission = _clone(
        publish_permission,
        trace_event_id="trace:forged-permission",
    )
    assert (
        hybrid_trace._append_current_action_authority_trace(
            _clone(
                request,
                publish_stop_resolution=forged_stop,
                publish_permission=forged_permission,
            ),
            events=[outcome_event],
            outcome_event=outcome_event,
        )
        == ()
    )
    duplicate_request = _clone(
        request,
        publish_stop_resolution=publish_stop,
        publish_permission=publish_permission,
        execute_stop_resolution=publish_stop,
        execute_permission=publish_permission,
    )
    dependencies = hybrid_trace._append_current_action_authority_trace(
        duplicate_request,
        events=[outcome_event],
        outcome_event=outcome_event,
    )
    assert len({item.lineage["event_id"] for item in dependencies}) == len(dependencies)

    broken_fact = _clone(request.publish_stop_resolution)
    object.__delattr__(broken_fact, "profile")
    assert not hybrid_trace._action_fact_matches_trace_identity(
        broken_fact,
        request=request,
        outcome_event=outcome_event,
    )

    without_actions = hybrid_trace._output_trace_event(
        request,
        outcome=outcome,
        deliver=result.deliver_authorization,
        publish=None,
        execute=None,
        certificate=None,
        distributed_state=None,
        previous=(outcome_event,),
    )
    with_actions = hybrid_trace._output_trace_event(
        request,
        outcome=outcome,
        deliver=result.deliver_authorization,
        publish=result.publish_authorization,
        execute=result.execute_authorization,
        certificate=result.local_receipt,
        distributed_state=None,
        previous=(outcome_event,),
    )
    assert without_actions.event_type == with_actions.event_type == "output_decided"
    assert (
        hybrid_output._certificate_for_outcome(
            _clone(outcome, assurance=CommitAssurance.ADVISORY),
            local_receipt=result.local_receipt,
            evidence_certificate=result.evidence_certificate,
            distributed_certificate=result.distributed_certificate,
            outcome_certificate=result.outcome_certificate,
        )
        is None
    )
