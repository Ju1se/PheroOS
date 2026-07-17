from __future__ import annotations

import json

from pheroos.conformance.report import CheckResult
from pheroos.drivers import DriverDescriptor, bind, register
from pheroos.governance import (
    GovernanceCommitBatch,
    InMemoryGovernanceStateStore,
    PreparedGovernanceTransition,
)
from pheroos.kernel import InputEnvelope, OSKernel, RuntimeMaterializer
from pheroos.trace import ScopedTraceEvent, TraceEvent


def check() -> CheckResult:
    problems: list[str] = []
    tenant_id = "tenant:scope-contract"
    run_id = "run:scope-contract"
    plan = OSKernel().plan(
        InputEnvelope(
            request="scope contract",
            tenant_id=tenant_id,
            metadata={"request_id": "request:scope-contract", "run_id": run_id},
        ),
        [],
    )
    context = RuntimeMaterializer().materialize(plan)
    if context.scope_ref != plan.scope_ref:
        problems.append("kernel_context_scope")

    registration = register(
        DriverDescriptor(
            id="driver:scope-contract",
            kind="tool",
            version="1",
        )
    )
    binding = bind(
        registration,
        tenant_id=tenant_id,
        run_id=run_id,
        permissions=["driver:invoke"],
    )
    if binding.scope_ref != context.scope_ref:
        problems.append("kernel_driver_scope")

    store = InMemoryGovernanceStateStore()
    head = store.load_head(context.scope_ref, "commit")
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id="transition:scope-contract",
        state_records={"candidate": "candidate:one"},
    )
    scoped_trace = ScopedTraceEvent(
        scope_ref=context.scope_ref,
        stream="commit",
        transition_id=transition.transition_id,
        trace_id="trace:scope-contract",
        event=TraceEvent(
            event_type="plan",
            protocol_id="protocol:scope-contract",
            target="decision:scope-contract",
            reason="cross-surface scope proof",
        ),
    )
    batch = GovernanceCommitBatch(transition, [scoped_trace.to_dict()])
    receipt = store.atomic_commit(batch)
    if not receipt.matches(batch):
        problems.append("governance_receipt_scope")
    stored = store.trace_records(context.scope_ref, "commit")
    if not stored or stored[0]["scope_ref"] != context.scope_ref:
        problems.append("trace_store_scope")

    portable = scoped_trace.to_dict()
    encoded = json.dumps(portable, sort_keys=True)
    if tenant_id in encoded or run_id in encoded:
        problems.append("raw_scope_identity_leak")
    foreign = OSKernel().plan(
        InputEnvelope(
            request="foreign scope",
            tenant_id="tenant:foreign",
            metadata={"request_id": "request:scope-contract", "run_id": run_id},
        ),
        [],
    )
    portable["scope_ref"] = foreign.scope_ref
    try:
        ScopedTraceEvent.from_dict(portable)
    except ValueError:
        pass
    else:
        problems.append("trace_scope_rebinding")

    return CheckResult("runtime_scope_contract", not problems, ", ".join(problems))


__all__ = ["check"]
