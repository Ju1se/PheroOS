# Runtime Integration Contract

PheroOS protocol-core defines the ABI boundary for external multi-agent runtimes.

It does not implement the runtime.

## Integration Shape

External runtimes should compose PheroOS in this order:

```text
manifest
-> protocol validation
-> kernel plan
-> external runtime binds adapters
-> agents produce scout reports, evidence, and signals
-> governance evaluates decision
-> trace records lineage
-> output authorization checks authority boundary
-> conformance proves compatibility
```

## Protocol-Core Responsibilities

Protocol-core owns:

- capability and protocol manifest objects
- structural validation
- kernel planning contracts
- provider-neutral driver declarations
- generic driver lifecycle objects
- governance reference semantics
- collective decision and pheromone reference behavior
- trace event ABI
- conformance checks

Protocol-core does not own:

- agent loops
- model calls
- tool calls
- provider adapters
- database persistence
- vector stores
- memory backends
- queues
- scheduling
- servers
- dashboards
- secret management

## External Runtime Responsibilities

An external runtime may implement:

- agent scheduling
- model-provider calls
- tool invocation
- database or memory persistence
- queueing
- credential loading
- provider-specific adapters
- application-specific workflows

Those implementations must stay outside protocol-core.

When a runtime needs to connect provider-specific configuration, it should use an external configuration reference, not inline secrets in a PheroOS manifest.

## Driver Declarations

Driver declarations are provider-neutral.

They describe what a capability exposes, not how a provider is called.

`config_ref` is an opaque external reference. Protocol-core must not resolve it, read secrets from it, or treat it as authority.

## Extensions

Manifest extensions are metadata.

Extensions may describe external runtime behavior when they are namespaced, traceable, and provider-neutral.

Extensions must not:

- contain API keys, tokens, passwords, credentials, or secrets
- create facts
- commit candidates
- authorize output
- bypass governance
- force baseline protocols to become swarm protocols

Unknown extension metadata is preserved for external runtimes, but protocol-core does not give it authority by default.

## Trace Extensions

Trace events use canonical built-in event types or namespaced extension event types.

Namespaced trace events are useful for external runtime lineage, but they remain trace records only. They do not become evidence, permission, quorum, or output authority.

## Pheromone Workflow

Pheromone is bounded collective memory.

External runtimes may store pheromone history outside protocol-core, then pass current trails into governance reference functions.

When evaluating a step, runtimes should apply deterministic evaporation and TTL expiry before scoring and consensus. The step-level governance helper exists to make that order explicit without adding a runtime loop or storage layer.

Pheromone remains:

- not evidence
- not truth
- not permission
- not quorum
- not output authority

## Compatibility

Baseline protocols do not need swarm behavior.

Swarm-specific validation and conformance apply only when a manifest declares a swarm collective mode.

External runtimes should use conformance to prove that their manifests and ABI usage remain compatible with protocol-core.
