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
    driver_payload = manifest.drivers[0]
    descriptor = declare(
        DriverDescriptor(
            id=driver_payload.id,
            kind=driver_payload.kind,
            version=driver_payload.version,
            capabilities=list(driver_payload.capabilities),
            permissions=list(driver_payload.permissions),
            config_ref=driver_payload.config_ref,
            extensions=driver_payload.extensions,
        )
    )
    registration = register(descriptor)
    probe_result = probe(registration)

    envelope = InputEnvelope(
        request="review provider free evidence",
        tenant_id="tenant-a",
        metadata={"request_id": "req-e2e"},
    )
    plan = OSKernel().plan(
        envelope,
        [manifest],
        driver_probe_snapshots=[probe_result],
    )
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

    exposure = context.driver_exposures[0]
    assert exposure.driver_id == driver_payload.id
    assert exposure.permissions == driver_payload.permissions
    assert exposure.capabilities == driver_payload.capabilities
    binding = bind(
        registration,
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        permissions=list(driver_payload.permissions),
    )
    handle = expose(binding)

    assert validate(descriptor) is True
    assert probe_result.available is True
    assert handle.exposed is True
    assert handle.binding.scope_ref == context.scope_ref
    assert handle.binding.capabilities == exposure.capabilities

    operation = driver_payload.permissions[0]
    capability = driver_payload.capabilities[0]
    invocation_id = "invoke:req-e2e:evidence"
    idempotency_key = "idempotency:req-e2e:evidence"
    invoke_payload = {
        "request": envelope.normalized_request(),
        "candidate": "candidate:approve",
        "content": "provider-free evidence",
    }
    request = DriverInvokeRequest(
        driver_id=descriptor.id,
        scope_ref=context.scope_ref,
        invocation_id=invocation_id,
        operation=operation,
        capability=capability,
        idempotency_key=idempotency_key,
        payload=invoke_payload,
    )
    driver_result = invoke(
        handle,
        payload=invoke_payload,
        provenance=descriptor.id,
        operation=operation,
        capability=capability,
        invocation_id=invocation_id,
        idempotency_key=idempotency_key,
    )
    reply = KernelSyscalls().invoke_driver(context, request, driver_result)
    assert reply.result.scope_ref == context.scope_ref
    assert reply.result.invocation_id == request.invocation_id
    assert reply.result.operation == request.operation
    assert reply.result.request_digest == request.request_digest
    trace.append(
        TraceEvent(
            event_type="invoke",
            protocol_id=protocol.id,
            target=target,
            reason="driver returned deterministic evidence",
            lineage={
                "driver": reply.result.driver_id,
                "provenance": reply.result.provenance,
                "scope_ref": reply.result.scope_ref,
                "invocation_id": reply.result.invocation_id,
                "operation": reply.result.operation,
                "capability": reply.request.capability,
                "request_digest": reply.result.request_digest,
            },
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
            lineage={
                "target": target,
                "candidate_id": decision.candidate_id,
                "decision_reason": decision.reason,
                "upstream_score_lineage": ["signal:governance"],
            },
        )
    )

    contract = OutputContract(
        committed_candidate_required=protocol.output_policy.requires_committed_candidate,
        evidence_required=protocol.output_policy.requires_evidence_contract,
        stop_resolution_required=protocol.output_policy.requires_stop_resolution,
        publication_permission_required=protocol.output_policy.requires_publication_permission,
    )
    authorized = output_authorized(
        contract,
        decision,
        evidence,
        [stop_resolution],
        publication_permission=True,
        candidate_set=candidates,
    )
    trace.append(
        TraceEvent(
            event_type="output",
            protocol_id=protocol.id,
            target=target,
            reason="output authorized by contract",
            lineage={
                "committed_candidate": decision.committed,
                "evidence_provenance": evidence.has_evidence() and evidence.has_provenance(),
                "stop_resolution": not stop_resolution.blocked,
                "publication_permission": True,
                "authorized": authorized,
            },
        )
    )

    assert authorized is True
    actual_required = set(protocol.trace_policy.required_events) - {"recovery"}
    assert trace.require_events(actual_required) == []
    assert "recovery" not in {event.event_type for event in trace.events}
