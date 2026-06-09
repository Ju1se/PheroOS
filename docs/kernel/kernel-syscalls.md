# PheroOS Kernel Syscalls

PheroOS syscalls are stable conceptual interfaces. They can be exposed through
Python APIs, CLI commands, HTTP/JSON-RPC, or event logs, but their inputs and
outputs should stay schema-versioned.

```text
pheroos.plan(input_envelope) -> OSPlan
pheroos.materialize(os_plan) -> RuntimeContext
pheroos.capability.resolve(intent) -> CapabilitySet
pheroos.agent.allocate(target_pressure) -> AgentAllocation
pheroos.signal.propose(signal) -> SignalReceipt
pheroos.signal.verify(signal_id) -> VerifiedSignal
pheroos.tool.invoke(tool_call) -> ToolResult
pheroos.evidence.attach(evidence) -> EvidenceNode
pheroos.stop.emit(target) -> StopSignal
pheroos.quorum.commit(target, candidates) -> QuorumDecision
pheroos.recovery.run(trigger) -> RecoveryTrace
pheroos.output.draft(contract) -> DraftArtifact
pheroos.output.publish(draft) -> PublishedArtifact
pheroos.trace.explain(run_id, query) -> Explanation
```

## Compatibility Rule

A capability is PheroOS-compatible when it can be loaded, planned,
permissioned, governed, traced, and judged through these interfaces without
editing kernel files such as `runtime/graph.py`, `runtime/swarm/quorum.py`,
`runtime/swarm/recovery_engine.py`, `runtime/writer_guardrails.py`, or
`runtime/final_judge_guardrails.py`.
