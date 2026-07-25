"""Provider-free preconstructed requests used by the Runtime Integration TCK."""

from __future__ import annotations

from hashlib import sha256

from pheroos.conformance._runtime_compatibility_evaluation import (
    create_runtime_compatibility_claim_v1,
)
from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityClaimV1,
)
from pheroos.conformance._runtime_compatibility_catalog import (
    build_runtime_compatibility_manifest_v1,
)
from pheroos.drivers import DriverInvocationRequestV2, DriverInvocationResultV2
from pheroos.governance import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    CommitDecisionOutcomeKindV2,
    CommitDecisionOutcomeV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputRequestV2,
    baseline_verified_signal_proposal_root_v2,
)
from pheroos.kernel import RuntimeScope
from pheroos.protocol import (
    AUTHORITY_CANONICAL_VERSION_V2,
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    PROTOCOL_VERSION_V2,
    BaselineOutputActionPolicyV2,
    BaselineOutputPolicyV2,
    CandidateSpec,
    DriverSpec,
    EvidencePolicy,
    QuorumPolicy,
    ScopedAuthorityPolicyV2,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    TargetSpec,
    TracePolicy,
)

from pheroos.conformance._runtime_integration_contracts import (
    RuntimeCommitObservationV1,
    RuntimeControlInputV1,
    RuntimeTranscriptRequestV1,
)
from pheroos.conformance._runtime_integration_certificate import (
    build_certificate_observation_material_v1,
)


_PROTOCOL = "protocol:support-v2-conformance"
_RUN = "run:support-v2-conformance"
_TARGET = "decision:support-v2"
_CANDIDATE = "candidate:support-v2:accept"
_FALLBACK = "candidate:runtime-safe-fallback"
_ACTION = "action:runtime-output"
_DRIVER = "driver:runtime-fixture"
_DRIVER_VERSION = "1.0.0"
_DRIVER_CAPABILITY = "runtime:observe"
_BASELINE_TRACE_EVENTS = (
    "block",
    "baseline_action_permission_issued",
    "baseline_decision_evaluated",
    "baseline_evidence_qualified",
    "baseline_manifest_activated",
    "baseline_output_committed",
    "baseline_stop_resolved",
    "commit",
    "output",
    "recovery",
)
_OPERATIONS = (
    GovernanceIssuerOperationV2.VERIFY_SIGNAL,
    GovernanceIssuerOperationV2.EVALUATE_QUORUM,
    GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
    GovernanceIssuerOperationV2.RESOLVE_STOP,
    GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
)


def build_runtime_integration_request_v1(
    scenario_id: str,
    *,
    terminal: str = "evidence_commit",
    effect: str = "publish",
    control: RuntimeControlInputV1 | None = None,
) -> RuntimeTranscriptRequestV1:
    """Construct deterministic input facts without embedding an expected result."""

    selected_control = control or RuntimeControlInputV1()
    scope = RuntimeScope(
        tenant_id=f"tenant-{_slug(scenario_id)}",
        run_id=_RUN,
        request_id=f"request:{scenario_id}",
    )
    threshold = 2 if terminal == "safe_fallback" else 1
    capability = _capability(scenario_id, threshold=threshold, effect=effect)
    domain = _domain(scope.scope_ref)
    grant = _grant(domain, scenario_id)
    driver_request = DriverInvocationRequestV2(
        scope_ref=scope.scope_ref,
        driver_id=_DRIVER,
        invocation_id=f"invocation:{scenario_id}",
        operation="runtime.observe",
        capability=_DRIVER_CAPABILITY,
        idempotency_key=f"idempotency:{scenario_id}",
        payload={"scenario_id": scenario_id, "observation": "provider-free"},
    )
    driver_result = DriverInvocationResultV2.for_request(
        driver_request,
        ok=True,
        payload={"candidate_ref": _CANDIDATE, "confidence": 1},
        provenance=f"fixture:runtime-integration:{scenario_id}",
    )
    signal, proposal = _signal(domain, scope, scenario_id, driver_result)
    baseline = None
    commit_observation = None
    successor = None
    contender = None
    if terminal == "advisory":
        commit_observation = RuntimeCommitObservationV1(outcome=_advisory(scenario_id))
    else:
        baseline = _baseline_request(
            domain,
            scope,
            capability,
            scenario_id,
            proposal,
            blocked=terminal == "blocked",
        )
        if terminal in {"certificate_current", "certificate_stale"}:
            commit_observation = _certificate_observation(
                scenario_id,
                scope,
                capability,
                with_successor=terminal == "certificate_stale",
            )
        if selected_control.inject_cas_conflict:
            contender = _baseline_request(
                domain,
                scope,
                capability,
                f"{scenario_id}:contender",
                proposal,
                blocked=False,
                output_transition_id=baseline.output_transition_id,
            )
        if selected_control.supersede_before_recovery:
            successor = _baseline_request(
                domain,
                scope,
                capability,
                f"{scenario_id}:successor",
                proposal,
                blocked=False,
            )
    return RuntimeTranscriptRequestV1(
        scenario_id=scenario_id,
        scope=scope,
        compatibility_claim=_compatibility_claim(),
        capability=capability,
        authority_domain=domain,
        issuer_grant=grant,
        driver_request=driver_request,
        driver_result=driver_result,
        verified_signal_requests=(signal,),
        baseline_request=baseline,
        commit_observation=commit_observation,
        control=selected_control,
        successor_request=successor,
        contender_request=contender,
    )


def _compatibility_claim() -> RuntimeCompatibilityClaimV1:
    manifest = build_runtime_compatibility_manifest_v1()
    versions = {
        item.component_id: item.version_id
        for item in manifest.required_profile.requirements
    }
    return create_runtime_compatibility_claim_v1(
        versions,
        critical_components=tuple(sorted(versions)),
    )


def _capability(
    scenario_id: str,
    *,
    threshold: int,
    effect: str,
) -> ScopedCapabilityManifestV2:
    protocol = ScopedProtocolManifestV2(
        protocol_version=PROTOCOL_VERSION_V2,
        id=_PROTOCOL,
        targets=(TargetSpec(id=_TARGET, description="runtime transcript output"),),
        candidates=(
            CandidateSpec(id=_CANDIDATE, target=_TARGET),
            CandidateSpec(id=_FALLBACK, target=_TARGET, safe_fallback=True),
        ),
        quorum_policy=QuorumPolicy(
            target=_TARGET,
            fallback_candidate=_FALLBACK,
            commit_threshold=threshold,
        ),
        authority_policy=ScopedAuthorityPolicyV2(
            policy_version=AUTHORITY_POLICY_VERSION_V2,
            profile=AUTHORITY_LOCAL_PROFILE_V2,
            wire_version=AUTHORITY_WIRE_VERSION_V2,
            canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
            ledger_version=AUTHORITY_LEDGER_VERSION_V2,
            state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
            trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
            read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        ),
        output_policy=BaselineOutputPolicyV2(
            policy_version=BASELINE_OUTPUT_POLICY_VERSION_V2,
            decision_mode="quorum",
            actions=(
                BaselineOutputActionPolicyV2(
                    action_ref=_ACTION,
                    effect=effect,
                    target=_TARGET,
                    allowed_outcomes=("evidence_commit", "safe_fallback"),
                ),
            ),
        ),
        trace_policy=TracePolicy(required_events=list(_BASELINE_TRACE_EVENTS)),
        evidence_policy=EvidencePolicy(
            require_provenance=True,
            allow_agent_fact_creation=False,
        ),
    )
    return ScopedCapabilityManifestV2(
        id=f"capability:runtime-integration:{scenario_id}",
        name="Runtime Integration transcript fixture",
        version="1.0.0",
        protocol=protocol,
        permissions=("runtime.invoke",),
        drivers=(
            DriverSpec(
                id=_DRIVER,
                kind="fixture",
                version=_DRIVER_VERSION,
                capabilities=[_DRIVER_CAPABILITY],
                permissions=["runtime.invoke"],
            ),
        ),
    )


def _domain(scope_ref: str) -> AuthorityDomainV2:
    return AuthorityDomainV2(
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


def _grant(domain: AuthorityDomainV2, scenario_id: str) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:runtime-integration-host",
        grant_ref=f"grant:{scenario_id}",
        grant_binding_ref=_root(f"grant-binding:{scenario_id}"),
        operations=_OPERATIONS,
        target_refs=(_TARGET,),
        action_refs=(_ACTION,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )


def _signal(
    domain: AuthorityDomainV2,
    scope: RuntimeScope,
    scenario_id: str,
    result: DriverInvocationResultV2,
) -> tuple[GovernanceVerifiedSignalRequestV2, dict[str, str]]:
    signal_ref = f"signal:{scenario_id}"
    source_ref = result.provenance
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        target_ref=_TARGET,
        candidate_ref=_CANDIDATE,
        signal_ref=signal_ref,
        evidence_root=result.result_digest,
        provenance_ref=result.result_digest,
        source_ref=source_ref,
    )
    request = GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        request_ref=f"request:signal:{scenario_id}",
        transition_id=f"transition:signal:{scenario_id}",
        signal_ref=signal_ref,
        target_ref=_TARGET,
        signal_root=signal_root,
        evidence_root=result.result_digest,
        status="verified",
        observed_epoch=2,
    )
    proposal = {
        "candidate_ref": _CANDIDATE,
        "evidence_root": result.result_digest,
        "provenance_ref": result.result_digest,
        "signal_ref": signal_ref,
        "signal_root": signal_root,
        "signal_transition_id": request.transition_id,
        "source_ref": source_ref,
    }
    return request, proposal


def _baseline_request(
    domain: AuthorityDomainV2,
    scope: RuntimeScope,
    capability: ScopedCapabilityManifestV2,
    label: str,
    proposal: dict[str, str],
    *,
    blocked: bool,
    output_transition_id: str | None = None,
) -> BaselineOutputRequestV2:
    return BaselineOutputRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        request_ref=f"request:output:{label}",
        output_transition_id=output_transition_id or f"transition:output:{label}",
        manifest=capability.protocol,
        target_ref=_TARGET,
        action_ref=_ACTION,
        proposed_candidate_ref=None,
        verified_signals=(proposal,),
        stop_resolutions=(
            {
                "action_ref": _ACTION,
                "blocked": blocked,
                "provenance_ref": proposal["provenance_ref"],
                "reason_ref": "reason:blocked" if blocked else "reason:clear",
            },
        ),
        output_payload={"answer": label, "source": "provider-free-fixture"},
        observed_epoch=2,
    )


def _advisory(label: str) -> CommitDecisionOutcomeV2:
    return CommitDecisionOutcomeV2(
        kind=CommitDecisionOutcomeKindV2.ADVISORY,
        candidate_ref="",
        claim_root="",
        output_contract_root="",
        output_payload_root="",
        finality_root="",
        epistemically_committed=False,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=("deadline:advisory",),
        current_step=4,
        evidence_deadline_step=4,
        finality_deadline_step=8,
        window_root=_root(f"window:{label}"),
        seal_root="",
        frozen_dependency_root=_root(f"dependencies:{label}"),
    )


def _certificate_observation(
    label: str,
    scope: RuntimeScope,
    capability: ScopedCapabilityManifestV2,
    *,
    with_successor: bool,
) -> RuntimeCommitObservationV1:
    observed, successor, body = build_certificate_observation_material_v1(
        label=label,
        scope_ref=scope.scope_ref,
        with_successor=with_successor,
    )
    if (
        body.scope_ref != scope.scope_ref
        or body.protocol_ref != capability.protocol.id
        or body.run_ref != scope.run_id
        or body.target_ref != _TARGET
        or body.candidate_ref != _CANDIDATE
    ):
        raise RuntimeError("Certificate fixture is not bound to the transcript")
    outcome = CommitDecisionOutcomeV2(
        kind=CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT,
        candidate_ref=body.candidate_ref,
        claim_root=body.claim_root,
        output_contract_root=body.output_contract_root,
        output_payload_root=body.output_payload_root,
        finality_root=observed.projection_root,
        epistemically_committed=True,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=("finality:certificate",),
        current_step=observed.verified_at_step,
        evidence_deadline_step=4,
        finality_deadline_step=observed.verified_at_step + 1,
        window_root=body.window_root,
        seal_root=body.seal_root,
        frozen_dependency_root=body.frozen_dependency_root,
    )
    return RuntimeCommitObservationV1(
        outcome=outcome,
        observed_finality=observed,
        successor_finality=successor,
    )


def _root(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


__all__ = ["build_runtime_integration_request_v1"]
