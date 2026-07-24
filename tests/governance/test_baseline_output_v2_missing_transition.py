from __future__ import annotations

from hashlib import sha256

from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceFailureStageV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputRequestV2,
    baseline_verified_signal_proposal_root_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
)
from pheroos.protocol.authority_manifest_v2 import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)


def _root(label: str) -> str:
    return f"sha256:{sha256(label.encode('utf-8')).hexdigest()}"


def test_missing_verified_signal_transition_fails_closed_without_permission() -> None:
    scope_ref = "scope:baseline-output:missing-signal-transition"
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        issuer_ref="issuer:missing-transition-regression",
        grant_ref="grant:missing-transition-regression",
        grant_binding_ref=_root("missing-transition-binding"),
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        ),
        target_refs=("target:answer",),
        action_refs=("action:publish",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    store = InMemoryGovernanceStateStoreV2((domain,))
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant:activate:missing-transition",
        1,
    )
    assert activation.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:missing-transition",
        2,
    )

    signal_ref = "signal:committed"
    signal_transition_id = "transition:signal:committed"
    evidence_root = _root("evidence:committed")
    provenance_ref = _root("provenance:committed")
    source_ref = "source:independent"
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        run_ref="run:missing-transition",
        target_ref="target:answer",
        candidate_ref="candidate:accept",
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=source_ref,
    )
    signal_request = GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        run_ref="run:missing-transition",
        request_ref="request:signal:committed",
        transition_id=signal_transition_id,
        signal_ref=signal_ref,
        target_ref="target:answer",
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=2,
    )
    signal_session = open_governance_authority_session_v2(
        capability,
        signal_request,
    )
    signal_attempt = commit_verified_signal_v2(
        signal_request,
        authority_session=signal_session,
    )
    assert signal_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    manifest = scoped_protocol_manifest_v2_from_dict(
        {
            "protocol_version": PROTOCOL_VERSION_V2,
            "id": "protocol:baseline-output:missing-transition",
            "targets": [
                {
                    "id": "target:answer",
                    "description": "Provider-free regression target.",
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
                "decision_mode": "quorum",
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
    request = BaselineOutputRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        run_ref="run:missing-transition",
        request_ref="request:output:missing-transition",
        output_transition_id="transition:output:missing-transition",
        manifest=manifest,
        target_ref="target:answer",
        action_ref="action:publish",
        proposed_candidate_ref=None,
        verified_signals=(
            {
                "candidate_ref": "candidate:accept",
                "evidence_root": evidence_root,
                "provenance_ref": provenance_ref,
                "signal_ref": signal_ref,
                "signal_root": signal_root,
                "signal_transition_id": "transition:signal:does-not-exist",
                "source_ref": source_ref,
            },
        ),
        stop_resolutions=(
            {
                "action_ref": "action:publish",
                "blocked": False,
                "provenance_ref": _root("stop:clear"),
                "reason_ref": "reason:clear",
            },
        ),
        output_payload={"answer": "must-not-be-authorized"},
        observed_epoch=2,
    )
    permission_session = open_baseline_output_authority_session_v2(
        capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )

    attempt = issue_action_permission_v2(
        request,
        authority_session=permission_session,
    )

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.stream_ref == request.evidence_stream_ref
    assert attempt.transition_id == request.stage_transition_id("evidence")
    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert attempt.failure.path == "/verified_signals/0"
    assert attempt.failure.stage is GovernanceFailureStageV2.PRECONDITION
    for stream_ref in (
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        request.output_stream_ref,
    ):
        assert store.load_head_v2(request.scope_ref, stream_ref).revision == 0
