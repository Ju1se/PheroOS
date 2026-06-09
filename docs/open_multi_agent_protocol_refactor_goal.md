# Open Multi-Agent Protocol Runtime Refactor Goal

> Source: pasted Codex goal text converted to Markdown.


You are working in this repository for a local protocol-governed multi-agent runtime. Pursue the following goal until the repository becomes meaningfully more protocol-first, less domain-specific, and more suitable as the foundation for an open-source multi-agent protocol.


## Goal

Convert the current AI-as-OS / PheroOS multi-agent runtime from a mostly application-specific implementation into a clean, protocol-first open multi-agent runtime. The final architecture must make the protocol the source of authority, while WRDS, value investing, web research, code development, and compliance remain optional capabilities or reference adapters rather than concepts embedded in core runtime logic.


## Core principle

Agents are not authority. Protocol is authority.
Agents may propose observations, actions, evidence, risks, candidates, tool calls, and output drafts. Only the protocol/governance layer may validate, commit, block, route, escalate, recover, publish, or explain final decisions.


## Non-negotiable architectural constraints

1. The core runtime must not contain hard-coded knowledge of WRDS, value investing, Buy/Sell/Watch/Avoid, formal valuation, specific financial metrics, or any other domain-specific workflow.
2. WRDS must become a reference data-provider adapter under a capability or extension boundary, not a first-class core runtime concept.
3. Any existing WRDS/value-investing functionality that works today should remain functional through compatibility wrappers or optional capabilities.
4. Do not remove useful domain examples. Instead, relocate or reframe them as examples:
   - WRDS = example data provider capability / adapter.
   - value investing = example decision protocol capability.
   - web research = example evidence-gathering capability.
   - code development = example implementation workflow capability.
   - compliance = example policy-gated workflow capability.
5. `runtime/graph.py` should remain a stable execution shell and compatibility bridge, not the place where new domain behavior is added.
6. `runtime/swarm/quorum.py` must not hard-code domain candidates. Candidates must be declared by protocol manifests.
7. `runtime/swarm/recovery_engine.py` must not hard-code agent names or domain-specific rescue paths. Recovery must be driven by protocol declarations.
8. Writer and Final Judge must enforce output contracts, evidence policy, stop signals, and conclusion permissions. They must not contain domain-specific phrases except through protocol-provided labels/caveats/templates.
9. Tools must be invoked through ToolRegistry or an equivalent protocol-aware tool bus. Agents must not directly instantiate or bypass tools.
10. The final result should be open-source friendly: clear spec docs, schemas, examples, tests, and compatibility notes.


## Existing context to inspect first

Start by auditing these areas before changing code:
- app/routes/agents.py
- app/routes/dependencies.py
- app/routes/wrds.py
- runtime/factory.py
- runtime/graph.py
- runtime/state.py
- runtime/os_kernel.py
- runtime/runtime_context.py
- runtime/capability_registry.py
- runtime/capability_runtime.py
- runtime/tool_registry.py
- runtime/data_gate.py
- runtime/nodes/output_chain.py
- runtime/writer_guardrails.py
- runtime/final_judge_guardrails.py
- runtime/output_contract.py
- runtime/swarm/protocol_schema.py
- runtime/swarm/protocol_loader.py
- runtime/swarm/protocol_manifest.py
- runtime/swarm/protocol_validation.py
- runtime/swarm/control_loop.py
- runtime/swarm/target_pressure.py
- runtime/swarm/agent_allocator.py
- runtime/swarm/quorum.py
- runtime/swarm/candidate_registry.py
- runtime/swarm/stop_signal.py
- runtime/swarm/recovery_engine.py
- runtime/swarm/evidence_graph.py
- runtime/swarm/evidence_contract.py
- runtime/swarm/trace_store.py
- runtime/workflows/*
- capabilities/*
- tools/wrds_tools.py
- tools/public_financial_tools.py
- docs/*


## Target public abstraction

Introduce or strengthen a neutral public protocol layer. Use a neutral name unless the repo already has a better one. Suggested names:
- Open Multi-Agent Protocol
- MAP, Multi-Agent Protocol
- Agent Governance Protocol
- Capability Governance Protocol

Prefer a structure like:
- protocol/
  - __init__.py
  - schema.py
  - manifest.py
  - validation.py
  - loader.py
  - compatibility.py
  - errors.py
  - json_schema.py
- docs/protocol/
  - overview.md
  - protocol-spec-v0.1.md
  - capability-manifest.md
  - tool-contract.md
  - evidence-contract.md
  - quorum-contract.md
  - recovery-contract.md
  - output-contract.md
  - trace-contract.md
  - migration-from-current-pheroos.md
  - examples/
- capabilities/examples/
  - toy-review/
  - generic-research/
  - financial-data-wrds/
  - value-investing-reference/

Do not blindly create these exact paths if the repo already has better structure. Reuse and evolve the existing runtime/swarm protocol files where appropriate. The important outcome is a coherent public spec boundary.


## Protocol spec requirements

Define a versioned protocol manifest that can express at least:

1. Identity and versioning
   - protocol_version
   - id
   - name
   - description
   - maturity
   - compatibility
   - extensions

2. Intent and capability matching
   - intents
   - required_capability_types
   - optional_capability_types
   - required_connections
   - permission_requirements
   - runtime_requirements

3. Agent role model
   - agent_roles
   - allowed_roles
   - trust_requirements
   - maturity_requirements
   - authority_level
   - activation_policy
   - deactivation_policy

4. Tool contracts
   - tool_id
   - provider_id
   - capability_scope
   - input_schema
   - output_schema
   - permissions
   - safety_class
   - source_policy
   - failure_modes
   - retry_policy
   - provenance requirements

5. Data source contracts
   - provider_id
   - source_kind
   - dataset_kind
   - coverage
   - freshness
   - provenance
   - license metadata
   - reliability level
   - adapter entrypoint
   - normalized result schema

6. Evidence contract
   - evidence types
   - minimum support requirements
   - independence requirements
   - citation/provenance requirements
   - contradiction handling
   - evidence gap handling
   - source quality policy
   - raw-data safety policy

7. Signal lifecycle
   - signal types
   - proposal vs verified status
   - authority required for verification
   - canonical target mapping
   - confidence/strength semantics
   - contamination and conflict rules

8. Stop signal policy
   - canonical targets
   - blocking strength
   - blocked actions
   - required resolution
   - expiration or recovery rules
   - explainability fields

9. Candidate and quorum policy
   - declared candidate set
   - candidate labels
   - candidate eligibility rules
   - quorum threshold
   - supporting evidence requirement
   - challenging evidence requirement
   - independence requirement
   - fallback candidate
   - insufficient-data candidate
   - commit trace requirements

10. Recovery protocols
   - trigger targets
   - allowed agent roles
   - allowed capability tags
   - required tools
   - success condition
   - failure condition
   - recovery failure candidate
   - recovery trace requirements

11. Output contract
   - allowed output modes
   - prohibited claims
   - required caveats
   - required evidence display
   - publication permissions
   - degraded output modes
   - defect memo templates
   - readiness memo templates
   - final judge checks

12. Trace and debugger contract
   - run events
   - tool events
   - permission events
   - signal events
   - quorum events
   - recovery events
   - evidence graph events
   - blocked target explanations
   - committed candidate explanations
   - agent activation explanations


## WRDS/domain refactor requirements

Search the repo for:
- wrds
- WRDS
- wrds_result
- wrds_agent
- wrds_tools
- value-investing
- value_investing
- formal_valuation
- peer_valuation
- Buy
- Sell
- Watch
- Avoid
- investment_committee
- financials
- financial_data

For each occurrence, classify it as:
A. core runtime domain leak,
B. protocol-declared domain example,
C. compatibility alias,
D. test fixture,
E. documentation/example.

Then refactor as follows:
1. Core runtime should use generic terms:
   - data_source_result or provider_result instead of wrds_result
   - data_provider_agent or source_agent instead of wrds_agent where used generically
   - data_contract instead of financial/WRDS-specific contract when possible
   - candidate registry instead of investment decision labels
   - decision target instead of formal valuation target unless declared by a capability

2. Keep WRDS-specific code only in:
   - tools/wrds_tools.py or a provider adapter module
   - capabilities/wrds-financial-data/
   - capabilities/examples/financial-data-wrds/
   - app/routes/wrds.py only if explicitly marked as compatibility/extension API
   - docs/examples or migration docs

3. Add a generic provider abstraction:
   - DataProviderDescriptor
   - DataSourceResult
   - DataSourceRegistry or provider registry if not already available
   - provider_id
   - source_kind
   - dataset_kind
   - normalized_payload
   - provenance
   - coverage
   - freshness
   - license
   - adapter_metadata

4. Make WRDS implement the generic abstraction:
   - WRDS adapter returns DataSourceResult.
   - Old wrds_result can be maintained as a backward-compatible alias derived from DataSourceResult.
   - No core node should require WRDS as a special case unless inside a legacy compatibility shim.

5. Replace direct WRDS routing with protocol-driven routing:
   - OSKernel should infer required data-source capability types.
   - RuntimeMaterializer should materialize provider tools based on active capability + active connection + permission grants.
   - ToolRegistry should expose only tools allowed by the active protocol/tool policy.
   - Capability runtime descriptors should decide whether a WRDS provider is useful for a given task.

6. Preserve behavior:
   - Existing WRDS workflows should still pass current tests.
   - If tests do not exist, add regression tests showing WRDS still works as a reference provider capability.
   - Any public response fields that currently include wrds_result may remain for compatibility, but also add generic fields such as data_source_results/provider_results and mark wrds_result as legacy or provider-specific.


## Protocol-driven runtime requirements

1. Protocol loading:
   - Load protocol declarations from capability manifests.
   - Validate protocol manifests against Pydantic models and/or JSON Schema.
   - Produce clear validation errors with protocol id, field path, and remediation.

2. Protocol composition:
   - If multiple capabilities are active, define how protocols compose.
   - Detect conflicting candidates, stop targets, tool policies, output policies, or evidence requirements.
   - Add deterministic conflict resolution or explicit blocked/degraded status.

3. Target canonicalization:
   - Centralize canonical target names and alias resolution.
   - Do not let domain-specific target aliases leak into core logic.
   - Target examples should be generic:
     - decision:*
     - tool:*
     - gate:*
     - artifact:*
     - output:*
     - evidence:*
     - provider:*

4. Quorum:
   - Reject or ignore candidates not declared by the active protocol.
   - Always include protocol lineage in quorum trace.
   - Support insufficient-data/degraded candidates declared by protocol.
   - Do not hard-code finance candidates in quorum logic.

5. Recovery:
   - Recovery must be selected by trigger targets, allowed roles, required tools, and success conditions from the active protocol.
   - No hard-coded agent name should be required for recovery.
   - Include recovery lineage in trace.

6. Output:
   - Writer must generate only outputs allowed by the active output contract.
   - Final Judge must check evidence, stop signals, candidate commitment, and publication permission.
   - If output is blocked, generate a protocol-compliant defect/readiness memo rather than a normal final answer.
   - Domain wording must come from protocol labels/templates/caveats, not from core writer code.

7. Trace:
   - All governance decisions should include protocol_source/protocol_id/protocol_version.
   - TraceStore and decision debugger should be able to answer:
     - why was this target blocked?
     - why was this candidate committed?
     - why was this agent activated?
     - what evidence supported/challenged the output?
     - which protocol rule caused this behavior?


## Open-source readiness requirements

### Add or improve documentation

1. README section explaining the project as a protocol-first multi-agent runtime.
2. docs/protocol/protocol-spec-v0.1.md describing the manifest.
3. docs/protocol/capability-manifest.md explaining how to add a capability.
4. docs/protocol/tool-contract.md explaining provider/tool boundaries.
5. docs/protocol/evidence-contract.md explaining evidence graph and citation/provenance requirements.
6. docs/protocol/quorum-contract.md explaining candidate commitment.
7. docs/protocol/recovery-contract.md explaining recovery without hard-coded agents.
8. docs/protocol/output-contract.md explaining writer/final judge constraints.
9. docs/protocol/migration-from-current-pheroos.md explaining compatibility.
10. docs/examples showing:
    - a minimal toy protocol,
    - a generic research protocol,
    - WRDS as a provider adapter example,
    - value investing as a reference decision protocol.

### Add public examples

1. Minimal protocol manifest that runs without external connections.
2. Tool provider example that uses a mock tool.
3. Data provider example that normalizes data into DataSourceResult.
4. Quorum example with declared candidates.
5. Stop signal example that blocks an output action.
6. Recovery example that recruits an agent role by protocol, not by name.


## Testing requirements

Add or update tests so these conditions are verified:
1. Protocol manifest validation succeeds for valid examples.
2. Protocol manifest validation fails clearly for invalid examples.
3. Core protocol loader can load capability protocol fields.
4. CandidateRegistry rejects candidates not declared in active protocol.
5. Quorum commits only protocol-declared candidates.
6. Recovery engine chooses recovery from protocol declarations rather than hard-coded agent names.
7. Writer respects output policy and conclusion permissions.
8. Final Judge respects stop signals and evidence policy.
9. ToolRegistry exposes only protocol-allowed tools.
10. WRDS remains available only as an optional provider/capability adapter.
11. Core runtime can run a toy protocol with no WRDS, no finance, and no domain-specific assumptions.
12. Grep-style guard test: core protocol/runtime files should not contain WRDS/value-investing-specific strings except in explicitly allowed compatibility files or examples.
13. Existing tests continue to pass.


## Validation loop

At the beginning:
1. Inspect repository structure.
2. Run the existing test suite.
3. Record current failures separately from failures introduced by your changes.

During implementation:
1. Keep changes scoped by milestone.
2. After each major milestone, run relevant tests.
3. If a test fails, fix the failure before moving on unless the test was already failing before the change.
4. Update docs alongside code changes.
5. Prefer additive compatibility over breaking changes.


## Suggested milestones


### Milestone 1: Architecture audit and plan

- Produce a short internal implementation plan in docs or a temporary plan file if appropriate.
- Identify domain leaks in core runtime.
- Identify current protocol schema gaps.
- Identify WRDS/value-investing compatibility requirements.


### Milestone 2: Public protocol schema

- Strengthen or introduce versioned protocol models.
- Add JSON schema generation or documented schema examples.
- Add manifest validation tests.
- Add minimal valid and invalid example protocols.


### Milestone 3: Generic data provider abstraction

- Introduce DataProviderDescriptor/DataSourceResult or equivalent.
- Make WRDS a provider adapter.
- Keep wrds_result as compatibility alias if needed.
- Add tests for generic provider result and WRDS adapter behavior.


### Milestone 4: Protocol-driven candidate/quorum/recovery

- Ensure candidates are protocol-declared.
- Ensure recovery protocols are not hard-coded by agent name.
- Ensure stop signals operate on canonical targets.
- Add tests for these behaviors.


### Milestone 5: Protocol-driven output enforcement

- Ensure Writer and Final Judge consume output/evidence/stop/conclusion permissions from protocol/data gate/evidence contract.
- Remove or isolate domain-specific output logic.
- Add tests for blocked, degraded, and successful outputs.


### Milestone 6: Capability examples and docs

- Add minimal toy protocol.
- Add generic research protocol.
- Move or document WRDS/value-investing as reference examples.
- Add open-source-oriented docs and migration notes.


### Milestone 7: Final validation and cleanup

- Run full test suite.
- Run grep checks for forbidden domain leaks in core files.
- Update README.
- Summarize changed architecture and compatibility notes.


## Definition of done

The task is complete only when:
1. There is a clear, versioned, documented multi-agent protocol manifest.
2. Protocol fields govern capabilities, tools, data sources, evidence, signals, stop signals, quorum, recovery, output, and trace.
3. WRDS and value-investing are optional/reference capabilities, not core runtime assumptions.
4. The system can run at least one non-finance, non-WRDS example protocol.
5. Existing WRDS/value-investing behavior is preserved through capability/adapter compatibility where practical.
6. Tests prove protocol validation, candidate enforcement, recovery enforcement, output enforcement, and WRDS isolation.
7. Documentation explains how third parties can create a new capability without editing graph.py, quorum.py, recovery_engine.py, writer_guardrails.py, or final_judge_guardrails.py.
8. The final summary clearly lists:
   - files changed,
   - new protocol abstractions,
   - removed or isolated domain leaks,
   - compatibility behavior,
   - tests run and results,
   - remaining limitations.


## Important coding style

- Prefer small, composable abstractions over a large rewrite.
- Preserve backward compatibility unless it directly violates protocol authority.
- Use explicit dataclasses/Pydantic models for protocol contracts.
- Make validation errors actionable.
- Keep naming neutral and open-source friendly.
- Do not hide domain-specific behavior under generic names unless the abstraction is genuinely generic.
- Do not implement fake behavior merely to satisfy tests.
- Do not overfit the protocol to WRDS or finance.
- When unsure, create a generic extension point and keep the existing domain implementation as an example adapter.
