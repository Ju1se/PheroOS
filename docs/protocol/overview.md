# Open Multi-Agent Protocol

Open Multi-Agent Protocol is the public protocol boundary for this runtime.
The runtime is not a prompt chain and agents are not final authority:

```text
Capability declares what is possible.
OSKernel decides what is available.
RuntimeMaterializer builds what is executable.
PheroOS governs what is allowed.
Quorum commits what is justified.
Writer expresses what is permitted.
FinalJudge verifies what can be published.
TraceStore explains why.
```

The core runtime must stay domain-neutral. WRDS, value investing, web
research, code development, document writing, data analysis, and compliance are
capabilities or reference examples. A third party should add a new capability
by editing a capability manifest and capability-owned adapters, not by editing
`runtime/graph.py`, `runtime/swarm/quorum.py`,
`runtime/swarm/recovery_engine.py`, `runtime/writer_guardrails.py`, or
`runtime/final_judge_guardrails.py`.

## Contract Map

- [Protocol spec v0.1](protocol-spec-v0.1.md)
- [Capability manifest](capability-manifest.md)
- [Tool contract](tool-contract.md)
- [Evidence contract](evidence-contract.md)
- [Quorum contract](quorum-contract.md)
- [Recovery contract](recovery-contract.md)
- [Output contract](output-contract.md)
- [Trace contract](trace-contract.md)
- [Migration from current PheroOS](migration-from-current-pheroos.md)
- [Minimal toy protocol example](examples/minimal-toy-protocol.md)
- [Generic research protocol example](examples/generic-research-protocol.md)
- [WRDS provider adapter example](examples/wrds-provider-adapter.md)
- [Value investing reference protocol](examples/value-investing-reference.md)

## Compatibility

Current runtime code still exposes legacy fields such as `wrds_result`,
`committee_outputs`, and `committee_decision` where existing clients depend on
them. New integrations should prefer generic fields such as
`data_source_results`, `provider_results`, `agent_outputs`, and
`agent_decision`. Legacy aliases are compatibility shims, not protocol
authority.
