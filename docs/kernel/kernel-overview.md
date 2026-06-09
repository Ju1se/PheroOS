# PheroOS Kernel Overview

PheroOS Kernel is the control-plane boundary for governed multi-agent
runtimes. It does not analyze domains, author conclusions, bypass tools, or
grant agents final authority. It plans, materializes, gates, validates, and
explains.

## Kernel Contract

```text
input envelope
-> OSPlan
-> RuntimeContext
-> mounted capabilities
-> exposed tools/drivers
-> governed swarm execution
-> output/trace contract
```

Kernel-mode actors can verify, block, commit, publish, and explain only through
declared protocol rules. User-mode agents can propose observations, tool calls,
evidence, risks, drafts, and candidates. Driver-mode adapters can return
structured results but cannot author conclusions.

## Modes

```text
Kernel mode:
  OSKernel
  RuntimeMaterializer
  PermissionPolicy
  ToolRegistry
  SignalVerifier
  DataGate
  QuorumMarshal
  StopSignalResolver
  FinalJudgeGuardrails
  TraceStore

User mode:
  normal agents
  third-party agents
  capability workflows
  model-generated plans
  model-generated evidence proposals
  model-generated drafts

Driver mode:
  model provider drivers
  tool drivers
  data provider drivers
  storage drivers
  secret-store drivers
```

## Kernel Services

Governance actors are kernel services, not ordinary agents. Examples include
scheduler, receiver normalizer, evidence steward, quorum marshal, social
immunity, protocol police, tool health sentinel, outcome memory steward,
capability sandbox auditor, and independent scout.

They enforce protocol invariants and write traceable governance decisions.
