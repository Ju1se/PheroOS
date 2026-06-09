# Migration From Static Rules

This repository is moving from a static prototype to a protocol-declared
PheroOS runtime. The target state is that capabilities declare governance
contracts and the core runtime hosts those contracts generically.

## Static Prototype

The old shape relied on central code for domain behavior:

- intent hints in `runtime/os_kernel.py`
- default targets in `runtime/swarm/goal_router.py`
- workflow branches in `runtime/graph.py`
- candidate defaults in quorum code
- tool/source policy sets in graph and swarm helpers
- writer/final-judge phrase checks

Those mechanisms may remain as traced legacy fallbacks, but they must not be the
primary source of domain truth for protocol-backed capabilities.

## Protocol-Declared Runtime

A capability should declare:

- intents and required capability types
- targets and aliases
- candidates and quorum policy
- recovery protocols
- stop-signal policy, including action markers
- evidence policy
- output policy
- tool policy
- agent selection policy
- workflow and runtime entrypoints when executable behavior is needed

The runtime then builds an OS plan, initializes swarm target pressure, runs
recovery/quorum/guardrails, and records trace lineage without adding a new core
branch for the capability.

## Adding New Behavior

Use this rule of thumb:

- New target or candidate: add it to a capability protocol.
- New recovery behavior: add a RecoveryProtocol and capability entrypoint.
- New writer/final-judge constraint: add OutputPolicy, EvidencePolicy, or
  StopSignalPolicy action markers.
- New tool access rule: add ToolPolicy and permissions.
- New graph behavior: add workflow descriptors and node entrypoints.
- New global security invariant: add it to core policy and make it
  non-weakenable.

## Required Evidence

Migration work is not complete just because tests pass. Each slice should leave
evidence in tests or trace output that proves:

- core routers did not need a new domain branch
- protocol declarations were loaded and used
- legacy fallbacks, if used, were traced
- no tool or model bypass was introduced
- final output obeyed committed candidate, evidence, caveat, and raw-data rules
- Decision Debugger can explain the decision lineage

## Remaining Compatibility Fallbacks

The current runtime still keeps some compatibility mechanisms for old or missing
descriptors, including legacy OS intent heuristics, default goal-router targets,
the fixed LangGraph shell for specialized paths, some deterministic Data Gate
and source-policy fallbacks, and no-protocol writer workflow checks. These must
continue shrinking until protocol declarations are the normal path and fallback
usage is exceptional and auditable.
