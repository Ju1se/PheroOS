from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
import importlib
import json

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    evidence_commit_certificate_payload,
    issue_outcome_certificate,
    local_commit_receipt_payload,
    outcome_certificate_payload,
    output_payload_fingerprint,
)
from pheroos.governance.commit_state import DecisionOutcomeKind
from pheroos.governance.output import (
    commit_output_authorization_payload,
    deliver_terminal_outcome,
)
from pheroos.governance.schema import commit_schema, validate_commit_wire_record
from pheroos.protocol.commit_wire import (
    canonical_commit_payload,
    commit_payload_fingerprint,
)
from pheroos.protocol.schema_validation import validate_json_schema
from tests.governance import test_commit_certificate as certificate_fixture
from tests.governance import test_commit_output_actions as output_fixture


_DIRECT_WIRE_DATACLASSES = {
    "pheroos-action-permission-v1": "pheroos.governance.permission:ActionPermission",
    "pheroos-candidate-commit-metrics-v1": "pheroos.governance.commit:CandidateCommitMetrics",
    "pheroos-challenge-attestation-v1": "pheroos.governance.challenge:ChallengeAttestation",
    "pheroos-challenge-coverage-v1": "pheroos.governance.challenge:ChallengeCoverage",
    "pheroos-commit-evaluation-context-v1": "pheroos.governance.commit:CommitEvaluationContext",
    "pheroos-commit-finality-verification-v1": "pheroos.governance.commit_state:CommitFinalityVerification",
    "pheroos-commit-liveness-input-v1": "pheroos.governance.commit_state:CommitLivenessInput",
    "pheroos-commit-output-authorization-v1": "pheroos.governance.output:CommitOutputAuthorization",
    "pheroos-commit-replay-receipt-v1": "pheroos.governance.commit_state:ReplayReceipt",
    "pheroos-commit-replay-state-v1": "pheroos.governance.commit_state:CommitReplayState",
    "pheroos-commit-threshold-snapshot-v1": "pheroos.governance.risk:CommitThresholdSnapshot",
    "pheroos-commit-window-state-v1": "pheroos.governance.commit_state:CommitWindowState",
    "pheroos-commit-window-seal-v1": "pheroos.governance.commit_state:CommitWindowSeal",
    "pheroos-counterevidence-disposition-v1": "pheroos.governance.observation:CounterevidenceDisposition",
    "pheroos-decision-outcome-v1": "pheroos.governance.commit_state:DecisionOutcome",
    "pheroos-decision-progress-v1": "pheroos.governance.commit_state:DecisionProgress",
    "pheroos-distributed-commit-certificate-v1": "pheroos.governance.distributed_commit:DistributedCommitCertificate",
    "pheroos-distributed-commit-proposal-v1": "pheroos.governance.distributed_commit:DistributedCommitProposal",
    "pheroos-distributed-commit-state-v1": "pheroos.governance.distributed_commit:DistributedCommitState",
    "pheroos-distributed-finality-decision-v1": "pheroos.governance.distributed_commit:DistributedFinalityDecision",
    "pheroos-eligible-membership-epoch-state-v1": "pheroos.governance.support_lease:EligibleMembershipEpochState",
    "pheroos-eligible-principal-snapshot-v1": "pheroos.governance.support_lease:EligiblePrincipalSnapshot",
    "pheroos-epoch-transition-certificate-v1": "pheroos.governance.distributed_commit:EpochTransitionCertificate",
    "pheroos-evidence-binding-authority-v1": "pheroos.governance.evidence_binding:EvidenceBinding",
    "pheroos-evidence-commit-certificate-v1": "pheroos.governance.certificate:EvidenceCommitCertificate",
    "pheroos-evidence-summary-v1": "pheroos.governance.evidence_binding:EvidenceSummary",
    "pheroos-hybrid-commit-evaluation-v1": "pheroos.governance.hybrid_commit_evaluation:HybridCommitEvaluation",
    "pheroos-local-commit-receipt-v1": "pheroos.governance.certificate:LocalCommitReceipt",
    "pheroos-observation-attestation-v1": "pheroos.governance.observation:ObservationAttestation",
    "pheroos-optimal-commit-assessment-v1": "pheroos.governance.commit:CommitAssessment",
    "pheroos-outcome-certificate-v1": "pheroos.governance.certificate:OutcomeCertificate",
    "pheroos-portable-membership-snapshot-v1": "pheroos.governance.distributed_commit:PortableMembershipSnapshot",
    "pheroos-principal-attestation-v1": "pheroos.governance.principal:PrincipalAttestation",
    "pheroos-principal-verification-v1": "pheroos.governance.principal:PrincipalVerification",
    "pheroos-quorum-witness-v1": "pheroos.governance.distributed_commit:QuorumWitness",
    "pheroos-risk-assessment-chain-state-v1": "pheroos.governance.risk:RiskAssessmentChainState",
    "pheroos-risk-assessment-v1": "pheroos.governance.risk:RiskAssessment",
    "pheroos-stop-resolution-verification-v1": "pheroos.governance.stop_signal:StopResolutionVerification",
    "pheroos-support-equivocation-finding-v1": "pheroos.governance.support_lease:SupportEquivocationFinding",
    "pheroos-support-lease-evaluation-v1": "pheroos.governance.support_lease:SupportLeaseEvaluation",
    "pheroos-support-lease-proposal-v1": "pheroos.governance.support_lease:SupportLeaseProposal",
    "pheroos-support-lease-replay-receipt-v1": "pheroos.governance.support_lease:SupportLeaseReplayReceipt",
    "pheroos-support-lease-replay-state-v1": "pheroos.governance.support_lease:SupportLeaseReplayState",
    "pheroos-support-lease-revocation-v1": "pheroos.governance.support_lease:SupportLeaseRevocation",
    "pheroos-support-lease-v1": "pheroos.governance.support_lease:SupportLease",
    "pheroos-verified-challenge-v1": "pheroos.governance.challenge:VerifiedChallenge",
    "pheroos-verified-observation-v1": "pheroos.governance.observation:VerifiedObservation",
    "pheroos-witness-replay-receipt-v1": "pheroos.governance.distributed_commit:WitnessReplayReceipt",
    "pheroos-witness-verification-v1": "pheroos.governance.distributed_commit:WitnessVerification",
}

_NON_PAYLOAD_DATACLASS_FIELDS = {
    "pheroos-hybrid-commit-evaluation-v1": {
        "attention",
        "binding_step",
        "commit_assessment",
        "commit_replay_state",
        "commit_window_state",
        "decision_outcome",
        "decision_progress",
        "deliver_authorization",
        "distributed_certificate",
        "distributed_state",
        "evidence_certificate",
        "execute_authorization",
        "exploration_directive",
        "finality_verification",
        "local_receipt",
        "outcome_certificate",
        "publish_authorization",
        "trace_events",
    }
}

_DERIVED_PAYLOAD_FIELDS = {
    "pheroos-challenge-coverage-v1": {"complete"},
    "pheroos-decision-outcome-v1": {"terminal"},
    "pheroos-decision-progress-v1": {"terminal"},
    "pheroos-evidence-summary-v1": {
        "counter_limit_satisfied",
        "counter_ratio_satisfied",
        "critical_counterevidence_clear",
        "evidence_gates_satisfied",
        "maximum_counterevidence",
        "maximum_counterevidence_ratio_ppm",
        "minimum_positive_evidence",
        "minimum_source_diversity",
        "positive_threshold_satisfied",
        "source_diversity_satisfied",
    },
}


def _branches() -> dict[str, dict[str, object]]:
    return {
        branch["properties"]["schema"]["const"]: branch
        for branch in commit_schema()["oneOf"]
    }


def _envelope(
    payload: dict[str, object],
    *,
    schema: str,
    profile: str,
) -> dict[str, object]:
    return json.loads(canonical_commit_payload(payload, schema=schema, profile=profile))


def _public_init_fields(locator: str) -> set[str]:
    module_name, class_name = locator.split(":", 1)
    record_type = getattr(importlib.import_module(module_name), class_name)
    return {
        item.name
        for item in fields(record_type)
        if item.init and not item.name.startswith("_")
    }


def test_commit_wire_direct_payload_schemas_track_every_dataclass_leaf() -> None:
    branches = _branches()
    assert set(branches) == {
        *_DIRECT_WIRE_DATACLASSES,
        "pheroos-distributed-commit-value-v1",
        "pheroos-hybrid-commit-step-v1",
    }
    for schema_name, locator in _DIRECT_WIRE_DATACLASSES.items():
        payload_schema = branches[schema_name]["properties"]["payload"]
        expected = (
            _public_init_fields(locator)
            - _NON_PAYLOAD_DATACLASS_FIELDS.get(schema_name, set())
        ) | _DERIVED_PAYLOAD_FIELDS.get(schema_name, set())
        assert set(payload_schema["properties"]) == expected, schema_name
        assert set(payload_schema["required"]) == set(payload_schema["properties"])
        assert payload_schema["additionalProperties"] is False


def test_hybrid_wire_contains_only_exact_commit_and_attention_roots() -> None:
    payload = _branches()["pheroos-hybrid-commit-step-v1"]["properties"]["payload"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "AttentionBreakdown" not in serialized
    assert "ExplorationDirective" not in serialized
    assert '"type": "number"' not in serialized
    assert set(payload["properties"]) == {
        "attention",
        "binding_profile",
        "commit",
        "composition_root",
    }
    assert payload["properties"]["attention"]["properties"] == {
        "attention_fingerprint": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "authority_scope": {"const": "none"},
        "commit_authority": {"const": False},
        "exploration_directive_fingerprint": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
        "memory_root": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "replay_root": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "source_step_root": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "trace_root": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    }


def test_total_hybrid_evaluation_wire_is_strict_total_and_no_downgrade() -> None:
    profile = "pheroos-hybrid-commit-v1"
    root = "sha256:" + ("a" * 64)
    payload: dict[str, object] = {
        "evaluation_version": "pheroos-hybrid-commit-evaluation-v1",
        "request_ref": root,
        "status": "progress",
        "authoritative": True,
        "terminal": False,
        "assurance_downgraded": False,
        "profile": profile,
        "assurance": "evidence_bound",
        "protocol_id": "protocol:schema-total",
        "run_id": "run:schema-total",
        "target": "target:schema-total",
        "epoch": 1,
        "current_step": 4,
        "attention_status": "verified",
        "binding_step_ref": root,
        "attention_ref": root,
        "exploration_directive_ref": root,
        "assessment_ref": root,
        "context_ref": root,
        "window_state_ref": root,
        "window_root": root,
        "replay_state_ref": root,
        "replay_root": root,
        "progress_ref": root,
        "outcome_ref": "",
        "local_receipt_ref": "",
        "evidence_certificate_ref": "",
        "distributed_state_ref": "",
        "distributed_certificate_ref": "",
        "outcome_certificate_ref": "",
        "finality_verification_ref": "",
        "deliver_authorization_ref": "",
        "publish_authorization_ref": "",
        "execute_authorization_ref": "",
        "trace_event_ids": [root],
        "trace_root": root,
        "diagnostics": [],
    }

    def record_for(**changes: object) -> dict[str, object]:
        candidate = {**payload, **changes}
        candidate["trace_root"] = commit_payload_fingerprint(
            {"event_ids": tuple(candidate["trace_event_ids"])},
            schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
            profile=profile,
        )
        candidate["evaluation_root"] = commit_payload_fingerprint(
            candidate,
            schema="pheroos-hybrid-commit-evaluation-v1",
            profile=profile,
        )
        return _envelope(
            candidate,
            schema="pheroos-hybrid-commit-evaluation-v1",
            profile=profile,
        )

    valid = record_for()
    assert validate_commit_wire_record(valid) == []
    chronological_trace_ids = ["sha256:" + ("b" * 64), root]
    assert (
        validate_commit_wire_record(record_for(trace_event_ids=chronological_trace_ids))
        == []
    )
    assert set(valid["payload"]) == set(
        _branches()["pheroos-hybrid-commit-evaluation-v1"]["properties"]["payload"][
            "properties"
        ]
    )
    for changes in (
        {"assurance_downgraded": True},
        {"terminal": True},
        {"progress_ref": ""},
        {"outcome_ref": root},
        {"assessment_ref": ""},
        {"context_ref": ""},
        {"window_state_ref": ""},
        {"replay_state_ref": ""},
        {"authoritative": False, "status": "progress"},
        {
            "diagnostics": [
                {
                    "code": "schema_order",
                    "severity": "warning",
                    "stage": "wire",
                    "message": "diagnostic references remain canonical",
                    "fatal": False,
                    "references": chronological_trace_ids,
                }
            ]
        },
    ):
        assert validate_commit_wire_record(record_for(**changes)), changes
    assert (
        validate_commit_wire_record(
            record_for(
                status="outcome",
                terminal=True,
                progress_ref="",
                outcome_ref=root,
                deliver_authorization_ref=root,
            )
        )
        == []
    )
    assert (
        validate_commit_wire_record(
            record_for(
                attention_status="unavailable",
                binding_step_ref="",
                attention_ref="",
                exploration_directive_ref="",
                diagnostics=[
                    {
                        "code": "attention_channel_unavailable",
                        "severity": "warning",
                        "stage": "attention",
                        "message": (
                            "Hybrid attention input is missing or non-authoritative"
                        ),
                        "fatal": False,
                        "references": [],
                    }
                ],
            )
        )
        == []
    )
    assert (
        validate_commit_wire_record(
            record_for(
                authoritative=False,
                status="invalid",
                terminal=True,
                attention_status="unavailable",
                binding_step_ref="",
                attention_ref="",
                exploration_directive_ref="",
                assessment_ref="",
                context_ref="",
                window_state_ref="",
                replay_state_ref="",
                progress_ref="",
                outcome_ref="",
                trace_event_ids=[],
                diagnostics=[
                    {
                        "code": "attention_channel_unavailable",
                        "severity": "warning",
                        "stage": "channel_binding",
                        "message": (
                            "Hybrid attention cannot be bound to the authoritative "
                            "CommitAssessment"
                        ),
                        "fatal": False,
                        "references": [],
                    }
                ],
            )
        )
        == []
    )


def test_every_commit_envelope_has_an_exact_discriminator_and_strict_payload() -> None:
    schema = commit_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["discriminator"] == {"propertyName": "schema"}
    assert len(schema["oneOf"]) == len(_branches())
    for branch in schema["oneOf"]:
        assert branch["additionalProperties"] is False
        assert branch["properties"]["schema"].keys() == {"const"}
        assert branch["properties"]["version"] == {"const": "pheroos-commit-wire-v1"}
        assert branch["properties"]["payload"]["additionalProperties"] is False


def test_h_certificate_and_output_payloads_validate_and_delete_each_leaf_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.governance.commit_state import (
        CommitFinalityStatus,
        commit_finality_verification_payload,
        commit_liveness_input_payload,
        commit_window_seal_for_state,
        commit_window_seal_payload,
        commit_window_state_payload,
        decision_outcome_payload,
        decision_progress_payload,
        issue_commit_liveness_input,
        reduce_commit_liveness,
    )
    from pheroos.governance.certificate import (
        evidence_commit_certificate_body_root,
        issue_evidence_commit_certificate,
        verify_evidence_commit_finality,
    )

    with monkeypatch.context() as certified_patch:
        scenario, assessment, receipt_window, output_ref = (
            certificate_fixture._certified_scenario(certified_patch)
        )
        receipt = certificate_fixture._receipt(
            scenario,
            assessment,
            receipt_window,
            output_ref,
        )
        certificate_metadata = {
            "certificate_id": "certificate:schema-full",
            "issuer_id": "governance:schema-certificate",
            "authority": AuthorityLevel.GOVERNANCE,
            "issued_at_step": 6,
            "provenance": "urn:test:certificate:schema-full",
            "trace_event_id": "trace:certificate:schema-full",
        }
        body_root = evidence_commit_certificate_body_root(
            receipt,
            **certificate_metadata,
        )
        trusted = {"attestation:schema-full": body_root}
        evidence_certificate = issue_evidence_commit_certificate(
            receipt,
            commit_policy=scenario.policy,
            issuer_attestation_refs=tuple(trusted),
            trusted_issuer_attestations=trusted,
            **certificate_metadata,
        )
        finality = verify_evidence_commit_finality(
            evidence_certificate,
            receipt,
            scenario.context,
            assessment,
            receipt_window,
            commit_policy=scenario.policy,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.replay_state,
            support_replay_state=scenario.support_replay_state,
            trusted_issuer_attestations=trusted,
            current_step=6,
            verifier_id="governance:schema-finality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:finality:schema-full",
            trace_event_id="trace:finality:schema-full",
        )
        seal = commit_window_seal_for_state(receipt_window)
        assert seal is not None
        liveness = issue_commit_liveness_input(
            receipt_window,
            assessment=assessment,
            replay_state=scenario.replay_state,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            support_replay_state=scenario.support_replay_state,
            commit_policy=scenario.policy,
            current_step=6,
            finality_status=CommitFinalityStatus.PENDING,
            input_id="liveness:schema-full",
            issuer_id="governance:schema-liveness",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:liveness:schema-full",
            trace_event_id="trace:liveness:schema-full",
        )
        progress = reduce_commit_liveness(
            receipt_window,
            commit_policy=scenario.policy,
            liveness_input=liveness,
        )
    outcome_scenario, outcome_window, outcome = output_fixture._nonready_outcome(
        DecisionOutcomeKind.SAFE_FALLBACK
    )
    outcome_output_ref = output_payload_fingerprint(
        {"kind": "safe_fallback", "schema_test": True},
        profile=outcome.profile,
    )
    outcome_certificate = issue_outcome_certificate(
        outcome,
        outcome_window,
        commit_policy=outcome_scenario.policy,
        output_payload_fingerprint=outcome_output_ref,
        certificate_id="outcome-certificate:schema-full",
        context=outcome_scenario.context,
        assessment=None,
        issuer_id="governance:schema",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=outcome.current_step,
        provenance="urn:test:outcome-certificate:schema-full",
        trace_event_id="trace:outcome-certificate:schema-full",
    )
    output = deliver_terminal_outcome(
        outcome,
        output_payload_fingerprint=outcome_output_ref,
    )
    records = (
        _envelope(
            commit_window_state_payload(receipt_window),
            schema="pheroos-commit-window-state-v1",
            profile=receipt_window.profile,
        ),
        _envelope(
            commit_window_seal_payload(seal),
            schema="pheroos-commit-window-seal-v1",
            profile=seal.profile,
        ),
        _envelope(
            commit_liveness_input_payload(liveness),
            schema="pheroos-commit-liveness-input-v1",
            profile=liveness.profile,
        ),
        _envelope(
            commit_finality_verification_payload(finality),
            schema="pheroos-commit-finality-verification-v1",
            profile=finality.profile,
        ),
        _envelope(
            decision_progress_payload(progress),
            schema="pheroos-decision-progress-v1",
            profile=progress.profile,
        ),
        _envelope(
            local_commit_receipt_payload(receipt),
            schema="pheroos-local-commit-receipt-v1",
            profile=receipt.profile,
        ),
        _envelope(
            evidence_commit_certificate_payload(evidence_certificate),
            schema="pheroos-evidence-commit-certificate-v1",
            profile=evidence_certificate.profile,
        ),
        _envelope(
            outcome_certificate_payload(outcome_certificate),
            schema="pheroos-outcome-certificate-v1",
            profile=outcome_certificate.profile,
        ),
        _envelope(
            decision_outcome_payload(outcome),
            schema="pheroos-decision-outcome-v1",
            profile=outcome.profile,
        ),
        _envelope(
            commit_output_authorization_payload(output),
            schema="pheroos-commit-output-authorization-v1",
            profile=output.profile,
        ),
    )
    assert scenario.context.profile == evidence_certificate.profile
    assert output_ref == evidence_certificate.output_payload_fingerprint
    for record in records:
        assert validate_commit_wire_record(record) == [], record["schema"]
        for leaf in tuple(record["payload"]):
            missing = deepcopy(record)
            del missing["payload"][leaf]
            assert validate_commit_wire_record(missing), (record["schema"], leaf)
        unknown = deepcopy(record)
        unknown["payload"]["undeclared_authority_leaf"] = "forged"
        assert validate_commit_wire_record(unknown)


def test_certificate_root_mutations_and_cross_discriminator_reuse_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, certificate, _, _, _ = certificate_fixture._evidence_certificate(monkeypatch)
    evidence = _envelope(
        evidence_commit_certificate_payload(certificate),
        schema="pheroos-evidence-commit-certificate-v1",
        profile=certificate.profile,
    )
    mutated = deepcopy(evidence)
    mutated["payload"]["certificate_body_root"] = "sha256:" + ("f" * 64)
    assert validate_commit_wire_record(mutated)

    wrong_discriminator = deepcopy(evidence)
    wrong_discriminator["payload"]["schema_discriminator"] = "outcome_certificate"
    assert validate_commit_wire_record(wrong_discriminator)


def test_distributed_authority_records_all_validate_through_commit_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.governance.distributed_commit import (
        distributed_commit_certificate_payload,
        distributed_commit_proposal_payload,
        distributed_commit_state_payload,
        distributed_finality_decision_payload,
        evaluate_distributed_finality,
        portable_membership_snapshot_payload,
        quorum_witness_payload,
        register_distributed_commit_certificate,
        witness_replay_receipt,
        witness_replay_receipt_payload,
        witness_verification_payload,
    )
    from tests.governance import test_distributed_commit as distributed_fixture

    bundle = distributed_fixture._distributed_scenario(monkeypatch)
    certificate = distributed_fixture._certificate(
        bundle,
        bundle.verifications[:3],
        suffix="schema-wire",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    finality = evaluate_distributed_finality(
        registered,
        bundle.receipt,
        certificate=certificate,
        current_step=6,
    )
    verification = bundle.verifications[0]
    records = (
        (
            "pheroos-portable-membership-snapshot-v1",
            portable_membership_snapshot_payload(registered.membership_snapshot),
        ),
        (
            "pheroos-distributed-commit-proposal-v1",
            distributed_commit_proposal_payload(bundle.proposal),
        ),
        ("pheroos-quorum-witness-v1", quorum_witness_payload(verification.witness)),
        (
            "pheroos-witness-verification-v1",
            witness_verification_payload(verification),
        ),
        (
            "pheroos-witness-replay-receipt-v1",
            witness_replay_receipt_payload(witness_replay_receipt(verification)),
        ),
        (
            "pheroos-distributed-commit-state-v1",
            distributed_commit_state_payload(registered),
        ),
        (
            "pheroos-distributed-commit-certificate-v1",
            distributed_commit_certificate_payload(certificate),
        ),
        (
            "pheroos-distributed-finality-decision-v1",
            distributed_finality_decision_payload(finality),
        ),
    )
    for schema_name, payload in records:
        record = _envelope(
            payload,
            schema=schema_name,
            profile=bundle.proposal.profile,
        )
        assert validate_commit_wire_record(record) == [], schema_name


def test_optimal_engine_and_hybrid_composition_records_validate_through_wire() -> None:
    from pheroos.governance.attention import evaluate_hybrid_attention_step
    from pheroos.governance.candidate import Candidate, CandidateSet
    from pheroos.governance.commit import (
        candidate_commit_metrics_payload,
        commit_assessment_payload,
        commit_evaluation_context_payload,
    )
    from pheroos.governance.hybrid_commit import (
        bind_hybrid_commit_channels,
        hybrid_commit_step_payload,
    )
    from pheroos.protocol import load_capability_manifest
    from tests.governance import test_commit_engine as engine_fixture
    from tests.swarm.test_hybrid_pheromone_vertical_slice import (
        deposits,
        feedback,
        layer_proposals,
        topology,
        verified_inhibition,
        verified_recruitment,
        verified_scout,
    )

    scenario = engine_fixture._scenario()
    assessment = engine_fixture._assess(
        scenario,
        assessment_suffix="schema-wire",
    )
    template = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        template.protocol.collective_decision_policy,
        fallback_candidate="candidate:fallback",
    )
    candidates = CandidateSet(
        [
            Candidate(item.id, item.target, item.safe_fallback)
            for item in scenario.manifest.protocol.candidates
        ]
    )
    target = scenario.context.target
    attention, directive = evaluate_hybrid_attention_step(
        protocol_id=scenario.manifest.protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=scenario.context.issued_at_step,
        scout_reports=[
            verified_scout("attention-scout:a", "candidate:alpha", target),
        ],
        recruitment_signals=[
            verified_recruitment(
                "attention-recruit:a",
                "candidate:alpha",
                target,
                1.0,
            )
        ],
        inhibition_signals=[
            verified_inhibition(
                "attention-inhibit:b",
                "candidate:beta",
                target,
                0.5,
            )
        ],
        deposits=deposits(target),
        topology=topology(target),
        feedback=[
            replace(item, step=scenario.context.issued_at_step)
            for item in feedback(target)
        ],
        layer_proposals=layer_proposals(target),
        fallback_candidate_id="candidate:fallback",
    )
    hybrid_step = bind_hybrid_commit_channels(
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
    )
    records = [
        (
            "pheroos-commit-evaluation-context-v1",
            commit_evaluation_context_payload(scenario.context),
        ),
        *(
            (
                "pheroos-candidate-commit-metrics-v1",
                candidate_commit_metrics_payload(metric),
            )
            for metric in assessment.candidate_metrics
        ),
        (
            "pheroos-optimal-commit-assessment-v1",
            commit_assessment_payload(assessment),
        ),
        (
            "pheroos-hybrid-commit-step-v1",
            hybrid_commit_step_payload(hybrid_step),
        ),
    ]
    for schema_name, payload in records:
        record = _envelope(
            payload,
            schema=schema_name,
            profile=assessment.profile,
        )
        assert validate_commit_wire_record(record) == [], schema_name


def test_noncritical_envelope_metadata_is_compatible_but_never_authoritative() -> None:
    scenario, assessment, window, output_ref = certificate_fixture._stable_scenario()
    receipt = certificate_fixture._receipt(scenario, assessment, window, output_ref)
    record = _envelope(
        local_commit_receipt_payload(receipt),
        schema="pheroos-local-commit-receipt-v1",
        profile=receipt.profile,
    )
    authority_root = commit_payload_fingerprint(
        record["payload"],
        schema=record["schema"],
        profile=record["profile"],
        version=record["version"],
    )
    record["x-vendor.note"] = {"display": "debug-only", "weight": 0.5}
    record["ext.observer"] = {"request_id": "outside-authority-root"}
    assert validate_commit_wire_record(record) == []
    assert (
        commit_payload_fingerprint(
            record["payload"],
            schema=record["schema"],
            profile=record["profile"],
            version=record["version"],
        )
        == authority_root
    )

    for critical_name in (
        "x-critical",
        "x-critical.vendor",
        "x-CRITICAL-finality",
        "ext.critical",
    ):
        critical = deepcopy(record)
        critical[critical_name] = {"attempt": "authority-smuggling"}
        assert validate_commit_wire_record(critical)

    for invalid_metadata in (float("nan"), object(), 2**63):
        malformed = deepcopy(record)
        malformed["x-vendor.invalid"] = invalid_metadata
        assert validate_commit_wire_record(malformed)


def test_all_authority_integer_leaves_reject_coercion_and_bounds() -> None:
    for schema_name, branch in _branches().items():
        payload = branch["properties"]["payload"]
        for leaf, leaf_schema in payload["properties"].items():
            if leaf_schema.get("x-pheroos-exact-integer") is not True:
                continue
            invalid_values: list[object] = [True, 1.0]
            if "minimum" in leaf_schema:
                invalid_values.append(leaf_schema["minimum"] - 1)
            if "maximum" in leaf_schema:
                invalid_values.append(leaf_schema["maximum"] + 1)
            if "enum" in leaf_schema:
                invalid_values.append(max(leaf_schema["enum"]) + 1)
            for invalid in invalid_values:
                assert validate_json_schema(invalid, leaf_schema), (
                    schema_name,
                    leaf,
                    invalid,
                )


def test_every_nested_commit_numeric_schema_is_exact_integer_only() -> None:
    for path, node in _schema_nodes(commit_schema()):
        assert node.get("type") != "number", path
        if node.get("type") != "integer":
            continue
        assert node.get("x-pheroos-exact-integer") is True, path
        if "enum" not in node:
            assert "minimum" in node and "maximum" in node, path


def test_commit_context_and_assessment_semantic_mutations_fail_closed() -> None:
    from pheroos.governance.commit import (
        candidate_commit_metrics_payload,
        commit_assessment_payload,
        commit_evaluation_context_payload,
    )
    from tests.governance import test_commit_engine as engine_fixture

    scenario = engine_fixture._scenario()
    assessment = engine_fixture._assess(
        scenario,
        assessment_suffix="schema-semantic-adversarial",
    )
    context = _envelope(
        commit_evaluation_context_payload(scenario.context),
        schema="pheroos-commit-evaluation-context-v1",
        profile=scenario.context.profile,
    )
    assessment_record = _envelope(
        commit_assessment_payload(assessment),
        schema="pheroos-optimal-commit-assessment-v1",
        profile=assessment.profile,
    )
    metric_records = [
        _envelope(
            candidate_commit_metrics_payload(metric),
            schema="pheroos-candidate-commit-metrics-v1",
            profile=assessment.profile,
        )
        for metric in assessment.candidate_metrics
    ]
    assert validate_commit_wire_record(context) == []
    assert validate_commit_wire_record(assessment_record) == []
    assert all(validate_commit_wire_record(record) == [] for record in metric_records)

    context_mutations: tuple[tuple[str, object], ...] = (
        ("candidate_claims", list(reversed(context["payload"]["candidate_claims"]))),
        (
            "candidate_claims",
            [
                context["payload"]["candidate_claims"][0],
                context["payload"]["candidate_claims"][0],
            ],
        ),
        (
            "fallback_candidate_id",
            context["payload"]["substantive_candidate_ids"][0],
        ),
        ("substantive_candidate_ids", []),
    )
    for field, value in context_mutations:
        malformed = deepcopy(context)
        malformed["payload"][field] = deepcopy(value)
        assert validate_commit_wire_record(malformed), field

    malformed = deepcopy(assessment_record)
    malformed["payload"]["candidate_metrics"] = list(
        reversed(malformed["payload"]["candidate_metrics"])
    )
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(assessment_record)
    malformed["payload"]["candidate_metrics"] = [
        malformed["payload"]["candidate_metrics"][0],
        malformed["payload"]["candidate_metrics"][0],
    ]
    assert validate_commit_wire_record(malformed)

    for root_name in (
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
    ):
        malformed = deepcopy(assessment_record)
        malformed["payload"][root_name] = "sha256:" + "f" * 64
        assert validate_commit_wire_record(malformed), root_name

    metric_mutations: tuple[tuple[str, object], ...] = (
        (
            "ready_for_stability",
            not metric_records[0]["payload"]["ready_for_stability"],
        ),
        (
            "support_cluster_satisfied",
            not metric_records[0]["payload"]["support_cluster_satisfied"],
        ),
    )
    for field, value in metric_mutations:
        malformed = deepcopy(metric_records[0])
        malformed["payload"][field] = value
        assert validate_commit_wire_record(malformed), field

    for field, value in (
        (
            "margin",
            assessment_record["payload"]["candidate_metrics"][0]["margin"] + 1,
        ),
        (
            "unique_leader",
            not assessment_record["payload"]["candidate_metrics"][0]["unique_leader"],
        ),
    ):
        malformed = deepcopy(assessment_record)
        malformed["payload"]["candidate_metrics"][0][field] = value
        assert validate_commit_wire_record(malformed), field

    assessment_mutations: tuple[tuple[str, object], ...] = (
        ("leader_candidate_id", "candidate:forged"),
        ("tied_candidate_ids", ["candidate:forged"]),
        ("unique_leader", not assessment_record["payload"]["unique_leader"]),
        ("leader_margin", assessment_record["payload"]["leader_margin"] + 1),
        (
            "leader_ready_for_stability",
            not assessment_record["payload"]["leader_ready_for_stability"],
        ),
    )
    for field, value in assessment_mutations:
        malformed = deepcopy(assessment_record)
        malformed["payload"][field] = value
        assert validate_commit_wire_record(malformed), field

    malformed = deepcopy(assessment_record)
    malformed["payload"]["status"] = "ready"
    malformed["payload"]["candidate_metrics"][0]["ready_for_stability"] = False
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(assessment_record)
    malformed["payload"]["status"] = "safety_violation"
    malformed["payload"]["equivocation_finding_ids"] = []
    malformed["payload"]["replay_conflict_references"] = []
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(context)
    malformed["payload"]["candidate_claims"][1]["candidate_id"] = malformed["payload"][
        "candidate_claims"
    ][0]["candidate_id"]
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(assessment_record)
    malformed["payload"]["candidate_metrics"][1]["candidate_id"] = malformed["payload"][
        "candidate_metrics"
    ][0]["candidate_id"]
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(assessment_record)
    malformed["payload"]["candidate_metrics"][1]["net_evidence"] = malformed["payload"][
        "candidate_metrics"
    ][0]["net_evidence"]
    assert validate_commit_wire_record(malformed)


def test_commit_window_semantic_mutations_fail_closed() -> None:
    from pheroos.governance.commit_state import commit_window_state_payload

    scenario, _assessment, window, _output_ref = certificate_fixture._stable_scenario()
    record = _envelope(
        commit_window_state_payload(window),
        schema="pheroos-commit-window-state-v1",
        profile=window.profile,
    )
    assert scenario.context.run_id == window.run_id
    assert validate_commit_wire_record(record) == []

    mutations: tuple[tuple[str, object], ...] = (
        ("chain_id", "sha256:" + "f" * 64),
        ("window_root", "sha256:" + "f" * 64),
        ("previous_state_fingerprint", ""),
        ("last_evaluated_step", record["payload"]["initialized_at_step"] - 1),
        ("last_evaluated_step", record["payload"]["absolute_deadline_step"]),
        (
            "absolute_deadline_step",
            record["payload"]["absolute_run_deadline_step"] + 1,
        ),
        ("absolute_deadline_step", record["payload"]["initialized_at_step"]),
        ("last_assessment_status", ""),
        ("assessment_replay_state_ref", ""),
        ("assessment_replay_root", ""),
        ("leader_candidate_id", ""),
        ("window_count", record["payload"]["window_count"] + 1),
        ("reset_budget_exhausted", True),
    )
    for field, value in mutations:
        malformed = deepcopy(record)
        malformed["payload"][field] = value
        assert validate_commit_wire_record(malformed), field

    malformed = deepcopy(record)
    malformed["payload"]["revision"] = 0
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(record)
    malformed["payload"]["last_assessment_ref"] = ""
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(record)
    malformed["payload"]["ordered_assessment_refs"] = [
        malformed["payload"]["ordered_assessment_refs"][0]
    ]
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(record)
    malformed["payload"]["last_ready"] = False
    assert validate_commit_wire_record(malformed)


def test_commit_replay_liveness_and_seal_semantic_mutations_fail_closed() -> None:
    from pheroos.governance.commit_state import (
        CommitAssurance,
        CommitFinalityStatus,
        commit_liveness_input_payload,
        commit_replay_state_payload,
        commit_window_seal_for_state,
        commit_window_seal_payload,
        initialize_commit_replay_state,
        issue_commit_liveness_input,
        record_commit_replay_receipts,
    )
    from tests.governance import test_commit_schema as schema_fixture

    first_receipt = schema_fixture.replay_receipt()
    second_receipt = replace(
        first_receipt,
        record_id="observation:beta",
        nonce="nonce:observation:beta",
        payload_fingerprint="sha256:" + "9" * 64,
        candidate_id="candidate:beta",
    )
    replay = initialize_commit_replay_state(
        profile=schema_fixture.PROFILE,
        assurance=CommitAssurance.CERTIFIED,
        manifest_root=schema_fixture.MANIFEST_ROOT,
        commit_policy_root=schema_fixture.COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:schema-semantic",
        current_step=1,
        issuer_id="governance:replay-schema",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:replay-schema",
        trace_event_id="trace:replay-schema",
    )
    replay = record_commit_replay_receipts(
        replay,
        current_step=2,
        receipts=(second_receipt, first_receipt),
    )
    replay_record = _envelope(
        commit_replay_state_payload(replay),
        schema="pheroos-commit-replay-state-v1",
        profile=replay.profile,
    )
    assert validate_commit_wire_record(replay_record) == []

    for field, value in (
        ("chain_id", "sha256:" + "f" * 64),
        ("current_step", 0),
        ("previous_state_fingerprint", ""),
        ("receipts", []),
    ):
        malformed = deepcopy(replay_record)
        malformed["payload"][field] = value
        assert validate_commit_wire_record(malformed), field

    malformed = deepcopy(replay_record)
    malformed["payload"]["receipts"] = list(reversed(malformed["payload"]["receipts"]))
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(replay_record)
    malformed["payload"]["revision"] = 0
    assert validate_commit_wire_record(malformed)

    scenario, assessment, window, output_ref = certificate_fixture._stable_scenario()
    liveness = issue_commit_liveness_input(
        window,
        assessment=assessment,
        replay_state=scenario.replay_state,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        current_step=6,
        finality_status=CommitFinalityStatus.PENDING,
        input_id="liveness:schema-semantic",
        issuer_id="governance:schema-semantic",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:liveness:schema-semantic",
        trace_event_id="trace:liveness:schema-semantic",
    )
    liveness_record = _envelope(
        commit_liveness_input_payload(liveness),
        schema="pheroos-commit-liveness-input-v1",
        profile=liveness.profile,
    )
    assert validate_commit_wire_record(liveness_record) == []

    malformed = deepcopy(liveness_record)
    malformed["payload"]["assessment_status"] = ""
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(liveness_record)
    malformed["payload"]["assessment_ref"] = ""
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(liveness_record)
    malformed["payload"]["leader_ready_for_stability"] = True
    malformed["payload"]["leader_candidate_id"] = ""
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(liveness_record)
    malformed["payload"]["finality_status"] = "verified"
    malformed["payload"]["certificate_ref"] = ""
    malformed["payload"]["finality_verification_ref"] = ""
    malformed["payload"]["sealed_window"] = False
    malformed["payload"]["heartbeat_continuous"] = False
    assert validate_commit_wire_record(malformed)

    malformed = deepcopy(liveness_record)
    malformed["payload"]["certificate_ref"] = "sha256:" + "a" * 64
    malformed["payload"]["finality_verification_ref"] = "sha256:" + "b" * 64
    assert validate_commit_wire_record(malformed)

    certificate_fixture._receipt(scenario, assessment, window, output_ref)
    seal = commit_window_seal_for_state(window)
    assert seal is not None
    seal_record = _envelope(
        commit_window_seal_payload(seal),
        schema="pheroos-commit-window-seal-v1",
        profile=seal.profile,
    )
    malformed = deepcopy(seal_record)
    malformed["payload"]["assurance"] = "certified"
    assert validate_commit_wire_record(malformed)


def _schema_nodes(
    value: object,
    path: tuple[object, ...] = (),
):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from _schema_nodes(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _schema_nodes(item, (*path, index))
