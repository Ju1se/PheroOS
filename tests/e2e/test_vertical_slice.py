from pheroos.drivers import (
    DriverDescriptor,
    bind,
    declare,
    expose,
    invoke,
    probe,
    register,
    validate,
)
from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    OutputContract,
    RecoveryTrace,
    Signal,
    SignalStatus,
    StopResolution,
    commit_candidate,
    output_authorized,
)
from pheroos.kernel import DriverInvokeRequest, InputEnvelope, KernelSyscalls, OSKernel, RuntimeMaterializer
from pheroos.protocol import load_capability_manifest, validate_capability_manifest
from pheroos.trace import InMemoryTraceStore, TraceEvent


def test_provider_free_governed_vertical_slice() -> None:
    manifest = load_capability_manifest("examples/e2e-protocol/capability.json")
    protocol = manifest.protocol
    target = protocol.quorum_policy.target
    trace = InMemoryTraceStore()

    assert validate_capability_manifest(manifest) == []

    envelope = InputEnvelope(
        request="review provider free evidence",
        tenant_id="tenant-a",
        metadata={"request_id": "req-e2e"},
    )
    plan = OSKernel().plan(envelope, [manifest])
    trace.append(
        TraceEvent(
            event_type="plan",
            protocol_id=protocol.id,
            target=target,
            reason="kernel planned available capability",
            lineage={"request_id": plan.request_id, "capability": manifest.id},
        )
    )
    trace.append(
        TraceEvent(
            event_type="grant",
            protocol_id=protocol.id,
            target=target,
            reason="kernel granted declared permissions",
            lineage={"permissions": [grant.permission for grant in plan.permission_grants]},
        )
    )
    trace.append(
        TraceEvent(
            event_type="expose",
            protocol_id=protocol.id,
            target=target,
            reason="kernel exposed declared driver",
            lineage={"drivers": [exposure.driver_id for exposure in plan.driver_exposures]},
        )
    )

    context = RuntimeMaterializer().materialize(plan)
    assert context.ready is True

    driver_payload = manifest.drivers[0]
    descriptor = declare(
        DriverDescriptor(
            id=driver_payload.id,
            kind=driver_payload.kind,
            version=driver_payload.version,
            capabilities=list(driver_payload.capabilities),
        )
    )
    registration = register(descriptor)
    probe_result = probe(registration)
    binding = bind(
        registration,
        tenant_id=context.tenant_id,
        permissions=list(driver_payload.permissions),
    )
    handle = expose(binding)

    assert validate(descriptor) is True
    assert probe_result.available is True
    assert handle.exposed is True

    request = DriverInvokeRequest(
        driver_id=descriptor.id,
        payload={"request": envelope.normalized_request()},
    )
    driver_result = invoke(
        handle,
        payload={"candidate": "candidate:approve", "content": "provider-free evidence"},
        provenance=descriptor.id,
    )
    reply = KernelSyscalls().invoke_driver(context, request, driver_result)
    trace.append(
        TraceEvent(
            event_type="invoke",
            protocol_id=protocol.id,
            target=target,
            reason="driver returned deterministic evidence",
            lineage={"driver": reply.result.driver_id, "provenance": reply.result.provenance},
        )
    )

    evidence = EvidenceGraph(
        nodes=[
            EvidenceNode(
                id="evidence:driver",
                content=str(reply.result.payload["content"]),
                provenance=reply.result.provenance,
            )
        ]
    )
    trace.append(
        TraceEvent(
            event_type="evidence",
            protocol_id=protocol.id,
            target=target,
            reason="evidence provenance recorded",
            lineage={"evidence": "evidence:driver"},
        )
    )

    agent_signal = Signal(
        target=target,
        type="proposal",
        source="agent",
        authority=AuthorityLevel.AGENT,
    ).verified()
    governance_signal = Signal(
        target=target,
        type="proposal",
        source="governance",
        authority=AuthorityLevel.GOVERNANCE,
    ).verified()
    trace.append(
        TraceEvent(
            event_type="signal",
            protocol_id=protocol.id,
            target=target,
            reason="governance verified proposal signal",
            lineage={"source": governance_signal.source},
        )
    )

    assert agent_signal.status == SignalStatus.REJECTED
    assert governance_signal.status == SignalStatus.VERIFIED

    stop_resolution = StopResolution(
        target=target,
        action="publish",
        blocked=False,
        reason="no blocking stop signal",
    )
    trace.append(
        TraceEvent(
            event_type="block",
            protocol_id=protocol.id,
            target=target,
            reason="stop resolution permits target action",
            lineage={"blocked": stop_resolution.blocked, "action": stop_resolution.action},
        )
    )

    candidates = CandidateSet(
        [
            Candidate(id=candidate.id, target=candidate.target, safe_fallback=candidate.safe_fallback)
            for candidate in protocol.candidates
        ]
    )
    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:approve",
        target=target,
        stop_resolutions=[stop_resolution],
    )
    trace.append(
        TraceEvent(
            event_type="commit",
            protocol_id=protocol.id,
            target=target,
            reason=decision.reason,
            lineage={"candidate": decision.candidate_id},
        )
    )

    recovery_protocol = protocol.recovery_protocols[0]
    recovery = RecoveryTrace(
        protocol_id=recovery_protocol.id,
        trigger_target=target,
        selected_roles=recovery_protocol.allowed_roles,
        selected_tags=recovery_protocol.allowed_tags,
        selected_tools=recovery_protocol.required_tools,
        success=True,
        failure_candidate=recovery_protocol.failure_candidate,
    )
    trace.append(
        TraceEvent(
            event_type="recovery",
            protocol_id=protocol.id,
            target=target,
            reason="declared recovery path available",
            lineage={"recovery": recovery.protocol_id, "failure_candidate": recovery.failure_candidate},
        )
    )

    contract = OutputContract(
        committed_candidate_required=protocol.output_policy.requires_committed_candidate,
        evidence_required=protocol.output_policy.requires_evidence_contract,
        publication_permission_required=protocol.output_policy.requires_publication_permission,
    )
    authorized = output_authorized(
        contract,
        decision,
        evidence,
        [stop_resolution],
        publication_permission=True,
    )
    trace.append(
        TraceEvent(
            event_type="output",
            protocol_id=protocol.id,
            target=target,
            reason="output authorized by contract",
            lineage={"authorized": authorized},
        )
    )

    assert authorized is True
    assert trace.require_events(protocol.trace_policy.required_events) == []
