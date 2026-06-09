# Kernel, User, and Driver Boundaries

PheroOS separates authority by runtime mode. This is the public contract that
keeps PheroOS from becoming a prompt chain or a domain-specific agent app.

## Kernel Mode

Kernel-mode actors verify, block, commit, publish, and explain.

```text
OSKernel
RuntimeMaterializer
PermissionPolicy
ToolRegistry
SignalVerifier
DataGate
QuorumMarshal
StopSignalResolver
WriterGuardrails
FinalJudgeGuardrails
TraceStore
```

Kernel mode owns:

- capability planning and runtime materialization;
- permission grants and connection readiness;
- tool exposure and structured tool dispatch;
- signal verification and contamination handling;
- evidence policy, stop-signal policy, quorum commit, and recovery outcome;
- output permission and trace explanation.

Kernel mode must not perform domain reasoning. Domain behavior enters through
capability manifests, protocol declarations, drivers, adapters, examples, or
explicit legacy compatibility shims.

## User Mode

User-mode actors propose. They do not hold authority.

```text
normal agents
third-party agents
capability workflows
model-generated plans
model-generated evidence proposals
model-generated drafts
```

User-mode agents can propose observations, evidence, tool calls, risks,
candidates, recovery actions, and drafts. They cannot directly create verified
facts, hard blockers, committed candidates, publication permission, or final
authority.

## Driver Mode

Driver-mode adapters expose structured provider capabilities to the kernel.
They return data or services, but they do not author conclusions.

```text
ModelDriver
ToolDriver
DataProviderDriver
StorageDriver
SecretStoreDriver
SandboxDriver
```

Driver mode owns:

- provider-specific authentication requirements;
- structured input and output schemas;
- provenance, license, freshness, and coverage metadata;
- side-effect classification and safety policy;
- storage, trace, or artifact persistence boundaries.

WRDS is a reference `DataProviderDriver` under
`capabilities/wrds-financial-data/` and `tools/wrds_tools.py`. WRDS is not a
kernel concept. Web research, value investing, code development, compliance,
and financial research are reference capabilities or examples, not core
runtime assumptions.

## Governance Services

Governance actors are kernel services, not normal agents and not committee
seats. They enforce protocol invariants without consuming user-mode decision
authority.

```text
pheroosd-scheduler
pheroosd-receiver
pheroosd-evidence
pheroosd-quorum
pheroosd-immunity
pheroosd-police
pheroosd-tool-health
pheroosd-memory
pheroosd-sandbox
pheroosd-scout
```

They may normalize signals, link evidence, check tool health, audit capability
sandbox policy, police protocol violations, marshal quorum, and record trace
lineage. They may not invent domain conclusions.

## Compatibility Bridge

`runtime/graph.py` remains a reference runtime shell and compatibility bridge.
New domain behavior should be expressed through protocol declarations,
capability entrypoints, or driver adapters instead of adding branches to the
graph shell.

The developer path is:

```text
author capability or driver
-> declare manifest and protocol block
-> run pheroos validate
-> run pheroos-conformance
-> mount through OSKernel / RuntimeMaterializer
-> inspect trace explanation
```

If a change requires editing `runtime/graph.py`, quorum, recovery, writer, or
final judge core modules, treat that as a protocol design smell unless the
change is explicitly a compatibility shim.
