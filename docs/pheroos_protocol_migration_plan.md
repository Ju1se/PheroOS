# PheroOS Protocol Migration Plan

## Goal

Convert this system from a PheroOS prototype with static rules into a true generic AI-as-OS plus PheroOS runtime driven by capability-declared protocols and a generic swarm control loop.

## Mode

- This is a long-horizon architecture migration.
- Work incrementally.
- Keep the system running after each milestone.
- Do not rewrite the whole project.
- Do not add more hardcoded special cases.
- Do not simply add more agents.
- The main goal is to move static behavior out of `runtime/graph.py`, `runtime/swarm/goal_router.py`, `quorum.py`, recovery nodes, and tool policy special cases into capability-declared protocol manifests and generic PheroOS runtime contracts.

## Current Known Architecture

AI-as-OS control plane exists:

- `runtime/os_kernel.py`
- `runtime/runtime_context.py`
- `runtime/connection_control.py`
- `runtime/capability_registry.py`
- `runtime/agent_registry.py`
- `runtime/permission_policy.py`
- `runtime/tool_registry.py`
- `runtime/model_gateway.py`

PheroOS swarm governance exists:

- `runtime/swarm/types.py`
- `runtime/swarm/contracts.py`
- `runtime/swarm/target_registry.py`
- `runtime/swarm/lifecycle.py`
- `runtime/swarm/authority.py`
- `runtime/swarm/signal_extractor.py`
- `runtime/swarm/stop_signal.py`
- `runtime/swarm/quorum.py`
- `runtime/swarm/evidence_graph.py`
- `runtime/swarm/trace_store.py`
- `runtime/writer_guardrails.py`
- `runtime/final_judge_guardrails.py`

Additional current-state notes:

- Capability plugins exist under `capabilities/*`.
- Agent plugins exist under `capabilities/*/agents/*.json`.
- `/agents/run` returns OS plan, data gate, agent outputs, pheromone trace, stop signals, quorum trace, evidence graph, policing trace, swarm governance trace, final output, and metrics.
- The current system supports `investment_analysis`, `evidence_research`, `code_development`, `compliance_workflow`, `financial_data_retrieval`, `web_research`, `general_chat`, or similar intents.
- The current system still likely contains static target mappings, static workflow branching, hardcoded investment candidates, hardcoded recovery agent names, and hardcoded tool policy sets. These are the things to remove or demote into compatibility fallbacks.

## High-Level Target Architecture

The final system should work like this:

```text
User input
-> AI-as-OS Kernel produces OSPlan
-> Capability Registry resolves capability protocol manifests
-> Runtime Materializer builds RuntimeContext
-> PheroOS initializes a typed pheromone field from declared targets, policies, constraints, permissions, tools, and evidence contracts
-> Generic Swarm Control Loop runs target-pressure-driven scheduling, tool/model execution, agent activation, signal extraction, verification, recovery, quorum, and guardrails
-> Capability workflow entrypoints provide domain-specific nodes/contracts/adapters/candidates/policies
-> Writer receives only committed candidates, verified/caveated claims, blocked claims, required caveats, and output policy
-> Final Judge enforces governance consistency
-> Trace Store explains why blocked, why committed, why agent activated, why evidence accepted/rejected
```

## Core Principle

Agent is not the authority. Protocol is the authority.

Agents may observe, propose, execute, challenge, and emit signals.

Only AI-as-OS plus PheroOS contracts may grant capability, verify facts, hard-block actions, resolve blocking signals, commit candidates, and authorize final output.

## Phase 0: Inspect Current Repo And Produce A Migration Map

First inspect the repo and produce a short migration map before editing.

Find and summarize:

1. Where OS Kernel infers intent and required capabilities.
2. Where `goal_router.py` maps intent to default targets.
3. Where capability manifests are loaded.
4. Where capability entrypoints are declared and whether they are actually used.
5. Where `runtime/graph.py` hardcodes workflows.
6. Where investment workflow is hardcoded.
7. Where quorum candidates are hardcoded.
8. Where evidence recovery hardcodes agent names.
9. Where tool policy uses hardcoded sets.
10. Where stop-signal policies are hardcoded.
11. Where writer/final judge guardrails enforce governance.
12. Where trace/Decision Debugger data is persisted and exposed.
13. Existing tests for Data Gate, Stop-Signal, Quorum, Evidence Graph, ToolRegistry, ModelGateway, Secret redaction.

Output a migration map:

- Static rule location
- Why it is not generic
- Target replacement
- Risk level
- Tests needed

Do not start major refactoring until this map is written into `docs/pheroos_protocol_migration.md`.

## Phase 1: Define Capability-Declared PheroOS Protocol Schema

Create a protocol schema that allows each capability to declare its own PheroOS behavior instead of relying on central hardcoded defaults.

Add or update files:

- `runtime/swarm/protocol_manifest.py`
- `runtime/swarm/protocol_schema.py`
- `runtime/swarm/protocol_loader.py`
- `runtime/swarm/protocol_validation.py`
- `docs/pheroos_protocol_manifest.md`

Define typed Pydantic/dataclass models for the following sections.

### TargetDeclaration

Fields:

- `target`
- `target_type`
- `description`
- `required`
- `default_pressure`
- `aliases`
- `source`
- `lifecycle_policy`
- `allowed_signal_types`

### CandidateDeclaration

Fields:

- `candidate`
- `description`
- `target`
- `compatible_intents`
- `blocked_by_targets`
- `required_evidence_targets`
- `required_permissions`
- `default_priority`
- `safe_fallback`

### QuorumPolicy

Fields:

- `candidates`
- `quorum_threshold`
- `min_independent_sources`
- `source_independence_weight`
- `source_quality_weight`
- `unresolved_risk_penalty`
- `stop_signal_penalty`
- `evidence_coverage_weight`
- `candidate_fallback`
- `force_fallback_when_blocked`

### StopSignalPolicy

Fields:

- `blocked_targets`
- `blocking_authority_required`
- `blocking_lifetime`
- `resolution_policy`
- `aliases`
- `action_effects`
- `action_markers`
- `applies_to_tools`
- `applies_to_writer`
- `applies_to_final_judge`
- `applies_to_candidates`

### RecoveryProtocol

Fields:

- `recovery_id`
- `trigger_targets`
- `trigger_signal_types`
- `max_rounds`
- `allowed_agent_roles`
- `allowed_capability_tags`
- `required_tools`
- `recovery_success_condition`
- `recovery_failure_candidate`
- `evidence_requirements`

### AgentSelectionPolicy

Fields:

- `target_affinity_weights`
- `required_roles`
- `optional_roles`
- `forbidden_roles`
- `activation_threshold`
- `utility_weights`
- `maturity_requirements`
- `trust_requirements`
- `fallback_strategy`

### EvidencePolicy

Fields:

- `claim_types`
- `evidence_node_types`
- `required_evidence_for_final_claims`
- `allow_caveated_claim_without_evidence`
- `source_independence_required`
- `citation_required`
- `raw_data_allowed_in_final`
- `raw_data_markers`
- `unsupported_claim_action`

### ToolPolicy

Fields:

- `allowed_tool_targets`
- `blocked_tool_targets`
- `tool_aliases`
- `required_permissions`
- `required_connections`
- `risk_level`
- `quarantine_external_outputs`
- `tool_failure_recovery`

### OutputPolicy

Fields:

- `allowed_output_modes`
- `blocked_phrases`
- `required_caveats`
- `final_claim_evidence_required`
- `defect_memo_on_block`
- `writer_can_create_facts`
- `final_judge_required_checks`

### SwarmLoopPolicy

Fields:

- `max_rounds`
- `target_pressure_threshold`
- `evidence_gap_threshold`
- `recovery_rounds`
- `quorum_check_frequency`
- `stop_signal_check_frequency`
- `tool_health_check_frequency`
- `arousal_signal_template`
- `social_immunity_arousal_signal_template`
- `social_immunity_recommendations`
- `homeostasis_signal_template`
- `homeostasis_recommendations`
- `lane_policy`
- `maturity_policy`
- `independent_scout_policy`
- `controller_action_policy`
- `encounter_rate_recommendations`
- `tool_health_recommendations`
- `outcome_feedback_enabled`

### CapabilityPheroOSProtocol

Fields:

- `capability_id`
- `version`
- `intents`
- `targets`
- `candidates`
- `quorum_policy`
- `stop_signal_policy`
- `recovery_protocols`
- `agent_selection_policy`
- `evidence_policy`
- `tool_policy`
- `output_policy`
- `swarm_loop_policy`
- `required_governance_actors`

### Schema Validation

Add schema validation:

- Canonical target required.
- Target aliases must map to canonical targets.
- Blocked candidates must reference declared targets.
- Recovery protocols must reference declared targets.
- No capability may declare hard-blocking authority unless trusted.
- Stop-signal policies from untrusted hard-blocking capabilities must be
  diagnosed and ignored by runtime policy consumers.
- Third-party capability defaults to unverified, non-blocking signals.
- Raw data allowed in final must default false.

### Backward Compatibility

- Existing `capability.json` should still load.
- If protocol section is absent, generate a compatibility protocol from current behavior but mark it as `generated_legacy_protocol` in trace.
- Existing tests must keep passing.

Implemented OS routing progress:

- `runtime/os_kernel.py` records the selected capability protocol for
  protocol-backed intents and resolves required capability types from that
  selected protocol instead of every manifest sharing the same intent.
- `capabilities/document-writing/capability.json` and
  `capabilities/data-analysis/capability.json` now declare first-class protocol
  intents, targets, candidates, quorum policy, and output/tool policy metadata,
  so those built-ins route through capability protocol declarations instead of
  OS-only static capability maps.
- `runtime/swarm/protocol_manifest.py` now supports
  `required_capability_types_by_intent`, and `runtime/os_kernel.py` uses that
  map when resolving multi-intent protocol dependencies. The value-investing
  protocol uses it to expose `portfolio_review` without inheriting WRDS or
  professional-financial-database requirements.
- `runtime/swarm/protocol_schema.py` and `runtime/swarm/goal_router.py` now
  support `targets[].compatible_intents`, allowing multi-intent protocols to
  expose intent-specific target pressure before any legacy GoalRouter fallback.
- `runtime/swarm/protocol_manifest.py` now supports protocol
  `intent_keywords`, and `runtime/os_kernel.py` uses them for OS intent
  matching. OS routing also filters target keywords through
  `targets[].compatible_intents`, so a multi-intent capability no longer lets
  one intent's target keywords activate another declared intent.
- The code-development, compliance-workflow, evidence-research,
  document-writing, data-analysis, web-research, and value-investing built-ins
  now declare first-class protocol `intent_keywords` and
  `required_capability_types` or per-intent requirement overrides, so their OS
  routes have protocol-owned vocabulary and dependencies before legacy static
  hint fallbacks.
- `runtime/swarm/protocol_validation.py` now reports undeclared intent
  references in `intent_keywords`, `required_capability_types_by_intent`, and
  `targets[].compatible_intents`.
- Generated-legacy protocol intent inference now uses the explicitly named
  `LEGACY_CAPABILITY_TYPE_INTENTS` map in
  `runtime/swarm/legacy_protocol_intents.py`; `runtime/swarm/protocol_loader.py`
  delegates through `legacy_intents_for_capability_types()` without importing
  the map, and explicit protocol declarations bypass the map.
- The old value-investing quorum field
  `force_insufficient_data_when_formal_valuation_blocked` now lives in
  `runtime/swarm/legacy_protocol_fields.py`; `runtime/swarm/protocol_schema.py`
  delegates to that compatibility boundary while normalized protocol output
  exposes only the generic `force_fallback_when_blocked` field.
- The remaining legacy OS intent keyword tuples and static
  intent-to-required-capability map now live in
  `runtime/legacy_os_intents.py`; `runtime/os_kernel.py` keeps compatibility
  helper names as thin delegates while protocol intent matching and selected
  protocol requirements remain the primary path.
- The remaining built-in skill-selection hint tables for legacy no-protocol
  skill matching now live in `runtime/legacy_skill_matching.py`;
  `runtime/skill_loader.py` remains the SKILL.md loader/scorer and delegates
  old inferred skill names through that compatibility boundary.
- Explicit selected protocols that declare an intent but no usable
  `capability_types` or `required_capability_types` now suppress legacy static
  requirement fallback, return OS-level `needs_capability`, emit
  `os.required_capabilities.needs_capability`, and keep GoalRouter from
  inheriting central target defaults.
- Explicit selected protocols with valid requirements but no declared goal
  targets now propagate GoalRouter `protocol_targets_missing` into OS-level
  `needs_capability` and `runtime_ready=false` once required connections are
  otherwise satisfied.
- `tests/test_os_kernel.py::test_explicit_protocol_without_requirement_types_does_not_use_static_capability_defaults`
  covers the malformed-protocol requirement gap.
- `tests/test_os_kernel.py::test_explicit_protocol_without_targets_is_not_runtime_ready_even_when_connections_exist`
  covers targetless explicit-protocol readiness.
- `tests/test_os_kernel.py::test_document_writing_uses_document_capability`,
  `tests/test_os_kernel.py::test_data_analysis_uses_data_analysis_capability`,
  and
  `tests/test_protocol_manifest.py::test_document_and_data_capabilities_declare_first_class_protocol_targets`
  cover document/data protocol-backed routing.
- `tests/test_os_kernel.py::test_portfolio_review_uses_specific_taxonomy_and_committee`,
  `tests/test_protocol_manifest.py::test_value_protocol_declares_portfolio_intent_without_wrds_dependency`,
  and
  `tests/swarm/test_goal_router_protocol_declared_targets.py::test_goal_router_filters_protocol_targets_by_compatible_intents`
  cover portfolio protocol routing, per-intent dependencies, and target
  filtering.
- `tests/test_protocol_manifest.py::test_protocol_validation_rejects_unknown_compatible_intents`
  covers validation for undeclared intent references.
- `tests/test_protocol_manifest.py::test_generated_legacy_intents_are_explicit_compatibility_map_only`
  covers generated-legacy intent map scope.
- `tests/test_architecture_boundaries.py::test_protocol_loader_does_not_own_generated_legacy_intent_map`
  prevents the generated-legacy capability-type intent map from moving back
  into `runtime/swarm/protocol_loader.py` as either a definition or direct
  imported symbol.
- `tests/test_protocol_manifest.py::test_legacy_quorum_force_fallback_field_loads_as_compatibility_alias`
  verifies the old value-investing quorum field still normalizes to
  `force_fallback_when_blocked`.
- `tests/test_architecture_boundaries.py::test_protocol_schema_delegates_legacy_quorum_field_aliases`
  prevents the generic protocol schema from re-owning legacy quorum field names.
- `tests/test_os_kernel.py::test_legacy_os_intent_compatibility_delegates_static_fallbacks`
  verifies legacy intent and requirement fallback behavior still works through
  the delegated compatibility boundary and can be suppressed.
- `tests/test_architecture_boundaries.py::test_os_kernel_does_not_own_legacy_intent_vocab_or_required_map`
  prevents legacy OS keyword vocabularies and static required-capability maps
  from moving back into `runtime/os_kernel.py`.
- `tests/test_architecture_boundaries.py::test_skill_loader_does_not_own_legacy_builtin_skill_matching_hints`
  prevents legacy built-in skill-selection hint tables from moving back into
  `runtime/skill_loader.py`.
- `tests/test_os_kernel.py::test_protocol_intent_matching_respects_target_compatible_intents`
  covers protocol intent keywords and compatible-intent target keyword
  filtering in OS routing.
- `tests/test_os_kernel.py::test_os_kernel_routes_protocol_intent_from_declared_intent_keywords`
  and
  `tests/test_protocol_manifest.py::test_builtin_workflow_capabilities_declare_intent_keywords_and_requirements`
  cover intent-keyword routing and built-in protocol-owned intent vocabularies.
- `tests/test_protocol_manifest.py::test_document_and_data_capabilities_declare_first_class_protocol_targets`
  and
  `tests/test_protocol_manifest.py::test_value_protocol_declares_portfolio_intent_without_wrds_dependency`
  also assert protocol-owned document/data/value intent vocabularies and
  dependencies.

## Phase 2: Move Default Targets From `goal_router.py` Into Capability Protocols

Current problem:

`runtime/swarm/goal_router.py` likely has `LEGACY_DEFAULT_TARGETS_BY_INTENT` or similar hardcoded mappings.

Refactor goal routing so that:

1. GoalRouter reads active capability protocol manifests.
2. Intent-to-target mapping is produced from capability-declared targets.
3. `LEGACY_DEFAULT_TARGETS_BY_INTENT` becomes only a compatibility fallback.
4. Fallback use is traced as `legacy_goal_router_fallback`.
5. New capabilities can define targets without editing `goal_router.py`.

Implement:

- `runtime/swarm/goal_router.py` refactor
- `runtime/swarm/target_registry.py` integration
- `runtime/swarm/protocol_loader.py` integration
- `tests/swarm/test_goal_router_protocol_declared_targets.py`

Required tests:

- `test_goal_router_uses_capability_declared_targets`
- `test_goal_router_does_not_require_legacy_default_targets_for_new_capability`
- `test_goal_router_marks_legacy_fallback_when_protocol_missing`
- `test_explicit_protocol_without_targets_does_not_use_legacy_defaults`
- `test_legacy_goal_router_fallback_does_not_emit_investment_candidate_targets`

Implemented goal-router progress:

- Built-in investment, web, evidence, compliance, code, document, data, and
  portfolio capabilities declare first-class protocol targets, so normal routing
  avoids `LEGACY_DEFAULT_TARGETS_BY_INTENT`.
- Explicit protocols without targets now return `needs_capability` instead of
  inheriting legacy defaults.
- The remaining legacy `investment_analysis` fallback no longer emits
  hardcoded investment candidate targets; candidates must come from declared
  candidate/quorum policy.
- `DEFAULT_TARGETS_BY_INTENT` was renamed to
  `LEGACY_DEFAULT_TARGETS_BY_INTENT`, the remaining map now lives in
  `runtime/swarm/legacy_goal_targets.py`, and the fallback trace type is still
  `legacy_default_targets_by_intent`, making the compatibility path explicit in
  source and runtime traces; `runtime/swarm/goal_router.py` now imports only the
  fallback helper, not the legacy map constant, keeping the router as the
  protocol-first consumer.
- GoalRouter allocation no longer uses a central intent-to-agent-type preferred
  map; agents are activated through protocol `agent_selection_policy` or generic
  target/focus scoring.
- `tests/test_architecture_boundaries.py::test_goal_router_does_not_own_legacy_default_targets`
  prevents the legacy default-target map or constant export from moving back
  into `runtime/swarm/goal_router.py`.
- `test_target_aliases_canonicalize_before_stop_signal`
- `test_unknown_intent_requests_capability_or_returns_needs_capability_not_random_defaults`

Acceptance:

A new toy capability added in tests should declare:

- Intent: `toy_review`
- Targets: `decision:toy_accept`, `gate:toy_evidence_gate`
- Candidates: `accept`, `reject`, `insufficient_evidence`

The system must route to those targets without editing `goal_router.py`.

## Phase 3: Generalize Capability Workflow Entrypoints

Current problem:

`runtime/graph.py` is still the core orchestration brain and may hardcode investment workflow.

Target:

`runtime/graph.py` becomes a generic execution host. Domain workflow logic moves into capability workflow entrypoints.

Implement:

- `runtime/capability_runtime.py`
- `runtime/workflows/base.py`
- `runtime/workflows/loader.py`
- `runtime/workflows/generic_swarm_workflow.py`
- `capabilities/value-investing-research/workflow.py` if missing or incomplete

Capability workflow entrypoint interface:

```python
class CapabilityWorkflow:
    capability_id: str

    def build_nodes(self, runtime_context, protocol_manifest): ...
    def initial_artifacts(self, input_envelope, runtime_context): ...
    def data_contract(self): ...
    def evidence_adapter(self): ...
    def output_contract(self): ...
    def declared_candidates(self): ...
    def declared_recovery_protocols(self): ...
```

Runtime behavior:

- OSPlan selects capability.
- RuntimeMaterializer loads capability workflow.
- `graph.py` delegates domain-specific nodes to capability workflow.
- Descriptor graph modes can be explicitly deferred from orchestration into the
  LangGraph `workflow_host` node, which runs the generic workflow host and
  capability-owned node entrypoints without adding a graph branch per capability;
  eligibility is now based on descriptor entrypoints plus explicit deferral for
  non-investment workflows rather than a central list of known mode names.
- `runtime/workflows/domain_execution.py` now treats code/compliance/evidence
  graph-mode handlers as traced `legacy_graph_mode_workflow_fallback` paths when
  no capability `orchestration_entrypoint` or `execution_entrypoint` is declared,
  so descriptor entrypoints remain the authority and compatibility fallback use
  is visible in runtime metadata.
- The legacy code/compliance/evidence graph-mode fallback maps now live in
  `runtime/workflows/legacy_dispatch.py`; `runtime/workflows/domain_execution.py`
  only delegates to that compatibility resolver instead of owning the static
  graph-mode map. Legacy built-in graph-mode exclusions also delegate to
  `runtime/workflows/legacy_dispatch.py`, so `domain_execution.py` and
  `graph.py` no longer own direct `investment_committee` graph-mode checks.
- Thin workflow descriptors that name a real capability by `capability_id`,
  `workflow_id`, or `id` are now backfilled from that capability's manifest
  workflow descriptor before graph-mode fallback dispatch, so known capabilities
  still use declared entrypoints even when runtime state carries a sparse
  workflow record.
- `runtime/graph.py` now treats no-entrypoint compliance/evidence
  `research_agent` node handlers as traced `legacy_graph_mode_node_fallback`
  paths instead of silent graph-mode branches.
- The legacy compliance/evidence `research_agent` node fallback map and trace
  helper now live in `runtime/workflows/legacy_node_dispatch.py`;
  `runtime/graph.py` only delegates to that compatibility resolver.
- Graph node dispatch now applies the same capability manifest workflow
  backfill before checking legacy research-node fallbacks, so a sparse known
  compliance/evidence workflow still resolves its declared `node_entrypoints`.
- Explicit protocol-backed workflows that declare static specialist graph nodes
  (`data_gate`, `research_agent`, `quant_agent`, `domain_expert`, and committee
  nodes) now fail with a capability entrypoint error when they omit the node
  entrypoint, instead of borrowing value-investing, generic domain-expert, or
  legacy compliance/evidence graph-mode fallbacks.
- Code-development and evidence-research workflow traces now describe declared
  gates/roles rather than naming specific guardrail agents in runtime text.
- Graph orchestration now receives the OS plan and suppresses company-name /
  ticker investment defaults when a protocol-backed OS plan does not declare
  committee or source-policy pressure. Legacy direct runs keep the old
  compatibility heuristic, while protocol-routed runs remain under OS/capability
  authority.
- The remaining legacy graph task-type aliases, task inference hints,
  direct-answer complexity markers, and quant/domain analysis hints now live in
  `runtime/workflows/legacy_graph_routing.py`; `runtime/graph.py` keeps thin
  wrappers for compatibility but no longer owns those routing heuristic tables.
- Legacy shorthand graph-node aliases such as `committee`,
  `deterministic_research`, and `executor_wrds` now live in
  `runtime/workflows/legacy_routing_aliases.py`; `runtime/workflows/routing.py`
  delegates alias normalization there while retaining the generic graph-shell
  routable node set. The descriptorless default graph node order and fallback
  trace source are now isolated in the same legacy helper, so routing summaries
  report `legacy_default_graph` instead of owning an unmarked default order.
- The remaining legacy deterministic fallback plan bodies for source-policy
  direct plans, public-web research, code workspace inspection, and direct
  no-tool answers now live in `runtime/workflows/legacy_plan_defaults.py`;
  `runtime/graph.py` delegates through a thin `deterministic_plan()` wrapper and
  records `legacy_deterministic_plan_fallback` when this compatibility path is
  used.
- Orchestrator domain prompt guidance now comes from capability workflow
  descriptor `orchestration_guidance`, ToolPolicy-declared source-mode guidance,
  or the traced
  `runtime/workflows/legacy_orchestration_guidance.py` compatibility fallback
  assembled by `runtime/workflows/orchestration_guidance.py`; `runtime/graph.py`
  keeps only the generic JSON orchestration contract and records
  `orchestration_guidance_trace`.
- Legacy skipped-analysis result reasons and the runtime-preflight blocked
  summary now live in `runtime/workflows/legacy_result_defaults.py`; the legacy
  memory-context metadata key list, including the old `investment_framework`
  key, is isolated there as well. `runtime/graph.py` delegates
  normalized-result, preflight-block, and memory-context defaults through that
  compatibility helper.
- Generic PheroOS loop remains capability-agnostic.
- Investment-specific nodes may exist inside `value-investing-research/workflow.py`.
- `graph.py` may keep thin compatibility wrappers but must not be the source of domain truth.

Required tests:

- `test_value_investing_workflow_loaded_from_capability_entrypoint`
- `test_toy_capability_workflow_runs_without_editing_graph`
- `test_toy_capability_orchestrator_runs_generic_workflow_host`
- `test_protocol_os_plan_suppresses_company_name_investment_heuristic`
- `test_protocol_source_policy_preserves_company_investment_defaults`
- `test_generic_workflow_host_runs_only_for_deferred_descriptor_workflows`
- `test_runtime_graph_does_not_require_investment_specific_candidate_constants`
- `test_capability_data_contract_loaded`
- `test_capability_evidence_adapter_loaded`
- `test_missing_workflow_entrypoint_returns_capability_error_not_crash`
- `test_protocol_research_graph_node_requires_declared_entrypoint_before_legacy_fallback`
- `test_protocol_specialist_graph_nodes_require_declared_entrypoints_before_static_fallback`
- `test_domain_execution_bridge_does_not_own_legacy_graph_mode_maps`
- `test_graph_does_not_own_legacy_research_node_fallbacks`
- `test_graph_does_not_own_legacy_routing_heuristic_tables`
- `test_workflow_routing_delegates_legacy_node_aliases`
- `test_graph_does_not_own_legacy_deterministic_plan_defaults`
- `test_graph_does_not_own_legacy_result_default_reasons`
- `test_graph_orchestrator_prompt_does_not_own_domain_guidance`
- `test_toy_capability_orchestrator_prompt_avoids_legacy_investment_guidance`

Acceptance:

A test capability can declare a simple workflow and run through generic PheroOS loop without adding new branches to `graph.py`.

## Phase 4: Build The Generic Swarm Control Loop

Current problem:

Pheromone Field is a governance state layer, but not yet a full iterative swarm control loop.

Implement:

- `runtime/swarm/control_loop.py`
- `runtime/swarm/target_pressure.py`
- `runtime/swarm/agent_allocator.py`
- `runtime/swarm/recruitment.py`
- `runtime/swarm/recovery_engine.py`
- `runtime/swarm/outcome_feedback.py`
- `runtime/swarm/execution_context.py`

Generic loop:

1. Initialize `InputEnvelope`.
2. Initialize `OSPlan`.
3. Load `CapabilityPheroOSProtocol`.
4. Initialize `PheromoneField`.
5. Initialize `TargetPressureMap`.
6. For each round in `max_rounds`:
   - Update target pressure from evidence gaps, unresolved risks, stop-signals, tool health, quorum uncertainty, artifact cues, user constraints, and recovery failures.
   - Allocate agents using agent manifest focus/tags/roles, target affinity, signal pressure, trust badge, maturity, required governance actors, and capability protocol `agent_selection_policy`.
   - Execute selected domain agents and governance actors.
   - Normalize outputs through Receiver Normalizer.
   - Extract signals.
   - Verify, police, and quarantine signals.
   - Update Evidence Graph.
   - Run recovery protocols if evidence gaps remain.
   - Run quorum checks.
   - Stop when a committed candidate exists and writer is allowed, a blocking defect memo is required, max rounds is reached, or an unrecoverable missing connection/permission exists.
   - Write trace events and outcome feedback.

Key requirement:

The control loop must not know investment-specific candidates or tool names except through protocol manifest and ToolRegistry metadata.

Required tests:

- `test_swarm_loop_recruits_agents_from_target_pressure`
- `test_swarm_loop_runs_recovery_before_blocking_when_recovery_declared`
- `test_swarm_loop_commits_after_recovery_success`
- `test_swarm_loop_blocks_after_recovery_failure`
- `test_swarm_loop_does_not_hardcode_investment_agents`
- `test_swarm_loop_uses_protocol_max_rounds`
- `test_swarm_loop_updates_outcome_feedback_without_storing_domain_conclusion`

Implemented allocation progress:

- `runtime/swarm/response_threshold.py` now derives committee task demand from
  agent manifest terms and `swarm.initial_thresholds` rather than static
  investment-agent name maps.
- `runtime/swarm/response_threshold.py` now also accepts manifest-declared
  `swarm.response_demand_profiles` / `swarm.demand_profiles` entries for
  task-type demand and reason text before falling back to legacy role-key
  heuristics.
- Legacy response-threshold role-key and known task-type demand fallbacks now
  live in `runtime/swarm/legacy_response_thresholds.py`; the scheduler core
  delegates there only after manifest demand profiles are absent.
- `runtime/swarm/response_threshold.py` now derives conclusion-review demand
  from generic Data Gate conclusion permission readiness rather than directly
  reading a formal-valuation-only flag.
- `runtime/swarm/response_threshold.py` now uses generic `agent_review`
  fallback task labels and `default agent participation` reasons for
  allocation/profile updates when no manifest-declared task type exists.
- `runtime/swarm/arousal.py` now raises pressure from generic blocked
  conclusion permissions and reports target-scoped `allowed_conclusion_targets`
  / `blocked_conclusion_targets` recommendations, while retaining
  `allow_formal_conclusion` as a compatibility recommendation field whose
  legacy formal-valuation target comes from
  `runtime/swarm/legacy_data_gate_permissions.py`.
- Dynamic committee mandatory retention now uses manifest metadata such as
  `can_block`, chair terms, and `must_follow_committed_candidate` instead of a
  hardcoded mandatory agent set.
- `runtime/swarm/controllers.py` now applies controller throttling/retention
  through the same manifest metadata and preserves member order through declared
  `order`, rather than a mandatory investment-agent set or a special
  `data_auditor_agent` sort override.
- `runtime/swarm/controllers.py` now carries generic
  `allowed_conclusion_targets` / `blocked_conclusion_targets` from arousal into
  the writer policy, while retaining `allow_formal_conclusion` as a
  compatibility field.
- `runtime/agent_registry.py` exposes shared `committee_capable` semantics for
  manifests and catalog dictionaries, so capability-local committee catalogs can
  use declared `committee_role`/committee-capable agent types instead of
  investment-only literals.
- `runtime/os_kernel.py` no longer gates committee planning on investment or
  portfolio intent names. It asks `runtime/agent_registry.py` for
  committee-capable manifests, and the registry now treats declared
  `committee_role` as committee membership while keeping legacy
  `investment_committee_member` agent types as compatibility input through
  `runtime/legacy_agent_registry.py`. Unknown legacy committee-member warning
  text now delegates to `runtime/legacy_os_intents.py`.
- `capabilities/value-investing-research/support.py` now normalizes committee
  catalogs through shared committee semantics and orders committee members only
  by declared manifest `order` instead of giving the data auditor a name-based
  priority.
- Runtime materialization now exposes a generic `metadata.agent_catalog` mirror
  of the active manifest agent list. Value-investing support and the generic
  swarm execution loop prefer `agent_catalog` before the legacy
  `committee_agent_catalog` compatibility key, whose metadata key construction
  and read fallback are isolated in `runtime/legacy_agent_registry.py`.
- User-selected agent metadata now prefers generic `selected_agent_ids` /
  `agent_ids` / `selected_agents` keys; old `committee_member_ids`,
  `committee_members`, and `selected_committee_members` metadata keys are
  normalized through `runtime/legacy_agent_registry.py` instead of being read
  directly by graph/runtime/capability nodes.
- `capabilities/value-investing-research/support.py` now loads fallback
  committee manifests from runtime `enabled_capabilities` / OS-plan
  `auto_enabled` metadata before using the legacy value-investing capability id,
  so non-investment capabilities with committee manifests can be selected
  without hardcoding their agent names.
- `runtime/swarm/trust_badge.py` and `runtime/swarm/lane_scheduler.py` now
  derive allowed lanes and preferred lane assignment from identity metadata,
  `swarm.allowed_lanes`, trust level, `can_block`, and role terms instead of
  static core-agent lane maps.
- `runtime/swarm/homeostasis.py` now measures token heat from generic
  `agent_outputs` through `runtime/swarm/agent_outputs.py`, which retains
  legacy `committee_outputs` only as a compatibility source.
- `runtime/swarm/receiver_normalizer.py` now normalizes generic `agent_outputs`
  through the same compatibility helper, emits `handoff:agent_claims`, and
  hands Evidence Steward / Governance Results generic agent-claim wording.
- `runtime/swarm/bottleneck_recruitment.py` now counts missing-data backlog
  from generic `agent_outputs` through the same compatibility helper and emits
  generic `agent_missing_data` evidence refs instead of committee-specific
  backlog labels.
- `runtime/swarm/independent_scout.py` now computes source-diversity and
  low-independence quorum pressure from generic `agent_outputs` through the
  same compatibility helper, and its governance contract declares
  `agent_outputs` instead of legacy committee output state.
- `runtime/swarm/quorum.py` now scores source independence and hard-veto
  unresolved risk from generic `agent_outputs` through the same compatibility
  helper instead of reading legacy committee output state directly.
- `runtime/state.py`, `runtime/swarm/agent_decisions.py`,
  `runtime/swarm/control_loop.py`, and `runtime/swarm/quorum.py` now type and
  consume generic `agent_decision` first. Legacy `committee_decision` remains
  readable only through the compatibility helper, and recovery fallback decisions
  are mirrored to the legacy field only when the incoming state already carried
  that field.
- `runtime/graph.py` now normalizes public run results with generic
  `agent_outputs` / `agent_decision` mirrors and feeds Critic, Writer, and Final
  Judge model contexts with generic agent state plus explicit
  `legacy_agent_outputs` / `legacy_agent_decision` lineage instead of bare
  committee-state prompt keys.
- `app/routes/agents.py::AgentRunResponse` now declares public
  `agent_outputs` and `agent_decision` fields before the legacy
  `committee_outputs` / `committee_decision` compatibility fields, so the
  FastAPI response model does not strip generic runtime state from `/agents/run`.
- `capabilities/value-investing-research/runtime_nodes.py` now passes
  capability agent work into generic governance helpers through `agent_outputs`
  while keeping `committee_outputs` as a compatibility mirror, and finalizes
  committee decisions into generic `agent_decision` before mirroring the legacy
  `committee_decision` payload.
- `capabilities/value-investing-research/support.py` now reads state-derived
  committee/member work through `runtime/swarm/agent_outputs.py` so prompts,
  discussion pressure, fallback decisions, and scorecard fallbacks prefer generic
  `agent_outputs` before legacy committee-output compatibility state.
- `runtime/graph.py` and the value-investing capability now expose generic
  `parse_agent_decision`, `fallback_agent_decision`,
  `agent_decision_to_domain_analysis`, and `summarize_agent_outputs_for_model`
  helper names first; committee-named helper functions remain compatibility
  wrappers instead of the primary graph/capability call path.
- `capabilities/wrds-financial-data/runtime_nodes.py` now returns generic
  `agent_outputs` and skipped `agent_decision` fields for direct WRDS retrieval
  instead of exposing only legacy committee compatibility fields.
- `runtime/swarm/social_immunity.py` now scans generic `agent_outputs` through
  a shared artifact helper; the helper still exposes legacy output artifacts as
  `legacy_agent_outputs` so global contamination/secret safety does not skip
  compatibility payloads.
- `runtime/audit_log.py` now summarizes generic `agent_outputs`, records
  `agent_output_source`, and preserves legacy compatibility lineage as
  `legacy_agent_outputs` through `runtime/swarm/agent_outputs.py` instead of
  writing audit summaries under `committee_outputs`.
- `runtime/audit_log.py` now also summarizes generic `agent_decision`, records
  `agent_decision_source`, and preserves legacy compatibility lineage as
  `legacy_agent_decision` through `runtime/swarm/agent_decisions.py` instead of
  writing audit summaries under `committee_decision`.
- `runtime/swarm/authority.py` now keeps fixed authority only for core
  modules/global actors and derives capability-agent authority plus blocker
  request eligibility from agent manifests, including `swarm.trust_level`,
  `swarm.signal_emit_permissions`, `swarm.can_block`, `committee_role`, and
  committee-capable `agent_type` semantics instead of an investment-only member
  type. Agent-emitted proposal signals now use generic `capability_agent`
  lineage; the old `committee_agent` source module remains isolated in
  `runtime/legacy_agent_registry.py` and recognized only as legacy
  self-assertion compatibility until a verifier/system module promotes a signal.
- `runtime/swarm/authority.py` now names authority level 3 `TRUSTED_AGENT`
  instead of `TRUSTED_COMMITTEE`; committee-capable manifest semantics still
  participate in scoring, but the core authority vocabulary is capability-agent
  generic.
- `capabilities/value-investing-research/evidence_adapter.py` now declares
  `capability_agent` as its proposal source instead of the legacy
  `committee_agent` source label.
- `runtime/swarm/outcome_feedback.py` and `runtime/swarm/outcome_memory.py`
  now express process-only learning boundaries as generic no-domain-conclusion
  constraints instead of investment/company-specific memory wording. Outcome
  Memory also consumes generic `agent_outputs`, uses `agent_review` as its
  fallback task label, and declares generic/legacy-agent-output excluded fields
  without storing domain conclusions.
- `runtime/swarm/outcome_feedback.py` now delegates old process-memory excluded
  decision field names such as `formal_decision` and `committee_decision` to
  `runtime/swarm/legacy_outcome_feedback.py`.
- `runtime/swarm/evidence_graph.py` now builds decision claims from generic
  `agent_decision`, records `decision_source`, and tags claims with explicit
  decision provenance or declared capability/workflow metadata from
  `metadata.os_plan.swarm_plan` and `domain_workflow`, keeping the legacy
  investment committee source only as an explicitly marked
  `legacy:investment_committee` no-protocol compatibility trace.
- `tests/test_swarm_governance.py::test_response_threshold_uses_manifest_terms_not_static_agent_maps`
  prevents reintroducing the old name-keyed response-threshold maps.
- `tests/test_swarm_governance.py::test_response_threshold_uses_manifest_declared_demand_profile`
  verifies manifest-declared response demand profiles drive allocation without
  core scheduler edits.
- `tests/test_swarm_governance.py::test_response_threshold_uses_generic_conclusion_permission_demand`
  verifies conclusion-review demand follows generic Data Gate permission
  readiness.
- `tests/test_swarm_governance.py::test_response_threshold_default_task_label_is_generic`
  and
  `tests/test_swarm_governance.py::test_response_threshold_profile_updates_default_to_generic_task_label`
  verify undeclared allocation/profile feedback falls back to generic
  `agent_review` labels rather than committee-specific task names.
- `tests/test_architecture_boundaries.py::test_response_threshold_core_does_not_own_legacy_role_term_fallbacks`
  prevents legacy response-threshold role-term and task-type demand fallbacks
  from moving back into the scheduler core.
- `tests/test_swarm_governance.py::test_arousal_uses_generic_blocked_conclusion_permissions`
  verifies arousal pressure reports allowed/blocked conclusion targets from
  declared Data Gate permissions.
- `tests/test_swarm_governance.py::test_lane_and_trust_badge_modules_use_manifest_lanes_not_static_agent_maps`
  prevents reintroducing the old static lane/trust maps.
- `tests/test_swarm_governance.py::test_homeostasis_token_heat_uses_generic_agent_outputs`
  verifies Homeostasis token pressure and recommendations work from generic
  agent outputs without requiring legacy committee output state.
- `tests/test_swarm_governance.py::test_receiver_normalizer_prefers_generic_agent_outputs`
  verifies normalized claim extraction prefers generic agent outputs over
  legacy committee-output compatibility state.
- `tests/test_swarm_governance.py::test_bottleneck_recruitment_prefers_generic_agent_outputs_for_missing_data`
  verifies bottleneck pressure prefers generic agent outputs for missing-data
  backlog accounting.
- `tests/test_swarm_governance.py::test_independent_scout_prefers_generic_agent_outputs_for_source_diversity`
  verifies source-diversity accounting prefers generic agent outputs over
  legacy committee-output compatibility state.
- `tests/swarm/test_protocol_declared_quorum.py::test_quorum_scores_prefer_generic_agent_outputs_for_source_independence`
  verifies quorum source-independence scoring prefers generic agent outputs.
- `tests/swarm/test_protocol_declared_quorum.py::test_quorum_risk_prefers_generic_agent_outputs_for_hard_veto`
  verifies quorum unresolved-risk scoring ignores legacy compatibility hard
  vetoes when generic agent outputs are present.
- `tests/test_swarm_governance.py::test_social_immunity_scans_generic_agent_outputs`
  verifies contamination scanning covers generic agent outputs.
- `tests/test_swarm_governance.py::test_social_immunity_still_scans_legacy_agent_output_compatibility_artifacts`
  verifies global safety still quarantines contaminated legacy compatibility
  payloads when generic outputs are present.
- `tests/test_swarm_governance.py::test_outcome_memory_prefers_generic_agent_outputs_for_process_updates`
  verifies Outcome Memory process updates prefer generic agent outputs and keep
  domain conclusions out of the serialized report.
- `tests/test_audit_log.py::test_audit_record_summarizes_generic_agent_outputs`
  verifies run audit summaries expose generic agent-output summaries without a
  legacy committee-output field.
- `tests/test_audit_log.py::test_audit_record_marks_legacy_agent_output_compatibility_source`
  verifies legacy output compatibility payloads are still summarized with
  explicit `legacy_agent_outputs` source lineage.
- `tests/test_audit_log.py::test_audit_record_summarizes_generic_agent_decision`
  and
  `tests/test_audit_log.py::test_audit_record_marks_legacy_agent_decision_compatibility_source`
  verify audit records expose generic agent-decision summaries and explicit
  legacy decision source lineage without a public `committee_decision` summary
  field.
- `tests/swarm/test_protocol_declared_quorum.py::test_quorum_prefers_generic_agent_decision_over_legacy_committee_decision`
  verifies quorum candidate commitment prefers generic `agent_decision` and
  records decision-source lineage.
- `tests/swarm/test_generic_control_loop.py::test_recovery_failure_writes_generic_agent_decision_without_legacy_state`
  and
  `tests/swarm/test_generic_control_loop.py::test_recovery_failure_mirrors_legacy_committee_decision_only_when_present`
  verify recovery fallback decisions write generic state without introducing
  legacy fields unless a compatibility payload was already present.
- `tests/test_architecture_boundaries.py::test_control_loop_and_quorum_use_generic_agent_decision_helper`
  prevents direct legacy decision reads from returning to quorum/control-loop
  code.
- `tests/test_evidence_contract.py::test_evidence_graph_prefers_generic_agent_decision_over_legacy_committee_decision`
  verifies EvidenceGraph decision claims prefer generic decision state and carry
  `decision_source` lineage.
- `tests/test_architecture_boundaries.py::test_evidence_graph_uses_generic_agent_decision_helper`
  prevents direct legacy decision reads from returning to EvidenceGraph.
- `tests/test_graph.py::test_normalized_run_result_exposes_generic_agent_state_with_legacy_mirror`
  verifies normalized run payloads expose generic agent state while preserving
  public legacy compatibility fields; graph normalization reads the legacy
  committee decision mirror only through `runtime/swarm/agent_decisions.py`.
- `tests/test_graph.py::test_model_contexts_use_generic_agent_state_and_explicit_legacy_lineage`
  verifies Critic/Writer/Final Judge contexts receive generic agent state and
  explicit legacy lineage rather than bare committee-state keys.
- `tests/test_architecture_boundaries.py::test_graph_model_contexts_use_generic_agent_state`
  prevents direct legacy `committee_decision` reads from returning to graph
  normalization or model context builders.
- `tests/test_architecture_boundaries.py::test_graph_model_contexts_use_generic_agent_state`
  prevents `committee_outputs` / `committee_decision` prompt keys from returning
  to the graph model contexts.
- `tests/test_api.py::test_agent_run_endpoint` and
  `tests/test_architecture_boundaries.py::test_agent_run_response_exposes_generic_agent_state`
  verify `/agents/run` exposes generic agent-output and decision fields while
  preserving legacy compatibility fields.
- `tests/test_architecture_boundaries.py::test_audit_log_uses_generic_agent_decision_summary`
  prevents direct legacy decision summaries from returning to run audit records.
- `tests/test_architecture_boundaries.py::test_capability_runtime_nodes_emit_generic_agent_state_fields`
  prevents value-investing and direct WRDS capability runtime nodes from
  returning to legacy-only committee output/decision fields.
- `tests/test_architecture_boundaries.py::test_graph_agent_decision_helpers_are_generic_with_legacy_wrappers`
  verifies graph/capability decision helper dispatch loads generic `agent_*`
  support functions while old committee names remain compatibility wrappers.
- `tests/test_graph.py::test_value_investing_support_prefers_generic_agent_outputs_over_legacy_state`
  and
  `tests/test_architecture_boundaries.py::test_value_investing_support_reads_generic_agent_outputs`
  verify value-investing support contexts, pressure, fallback decisions, and
  scorecards prefer generic agent outputs while preserving domain prompt labels.
- `tests/test_graph.py::test_explicit_wrds_request_bypasses_general_graph`
  verifies the direct WRDS path now exposes generic empty `agent_outputs` and a
  skipped `agent_decision` in the normalized run payload.
- `tests/test_swarm_governance.py::test_authority_uses_manifest_permissions_not_static_agent_maps`
  prevents reintroducing static agent authority/blocker maps or investment-only
  committee authority branches.
- `tests/test_architecture_boundaries.py::test_agent_signal_extractor_uses_generic_proposal_source`
  and `tests/test_capability_runtime.py::test_capability_data_contract_and_evidence_adapter_loaded`
  verify agent-emitted signal lineage and evidence-adapter proposal sources use
  `capability_agent` while `committee_agent` remains legacy compatibility only
  through `runtime/legacy_agent_registry.py`.
- `tests/test_architecture_boundaries.py::test_authority_levels_use_generic_trusted_agent_name`
  prevents the old `TRUSTED_COMMITTEE` authority-level name from returning.
- `tests/test_swarm_governance.py::test_swarm_controller_uses_manifest_metadata_not_static_mandatory_agents`
  prevents reintroducing controller mandatory-agent maps or name-based sort
  overrides.
- `tests/test_swarm_governance.py::test_swarm_controller_carries_generic_blocked_conclusion_targets`
  verifies controller writer policy preserves generic allowed/blocked
  conclusion targets from arousal.
- `tests/test_graph.py::test_committee_member_order_uses_declared_order_not_agent_name_special_case`
  prevents reintroducing capability-local name-based committee ordering.
- `tests/test_graph.py::test_committee_member_specs_prefer_generic_agent_catalog_over_legacy`,
  `tests/test_swarm_execution_loop.py::test_swarm_execution_loop_agent_manifest_index_reads_generic_agent_catalog`,
  and `tests/test_architecture_boundaries.py::test_runtime_metadata_prefers_generic_agent_catalog`
  verify runtime consumers prefer generic `agent_catalog` metadata while keeping
  the legacy committee catalog mirror available.
- `tests/test_graph.py::test_committee_member_specs_use_shared_manifest_committee_semantics`
  prevents reintroducing capability-local investment-only committee catalog
  filtering.
- `tests/test_graph.py::test_committee_member_specs_fallback_uses_enabled_capability_ids`
  prevents fallback committee manifest loading from being value-investing-only
  when runtime metadata identifies another enabled capability; the remaining
  legacy default value-investing capability id and graph fallback loader id are
  isolated in `runtime/legacy_value_investing_support.py`.
- `tests/test_agent_registry.py::test_agent_registry_committee_specs_use_manifest_committee_role`
  and
  `tests/test_os_kernel.py::test_protocol_capability_can_declare_non_investment_committee_plan`
  prevent reintroducing an investment-only committee planner.
- `tests/test_agent_registry.py::test_agent_registry_legacy_committee_agent_type_remains_compatibility_path`
  and
  `tests/test_architecture_boundaries.py::test_agent_registry_does_not_own_legacy_committee_agent_types`
  keep the old committee agent-type vocabulary as an explicit compatibility
  path rather than registry-owned domain truth.
- `tests/test_evidence_contract.py::test_decision_claim_source_comes_from_declared_capability_protocol`
  prevents Evidence Graph decision claims from silently inheriting
  investment-committee provenance when a capability protocol selected the
  workflow.
- `tests/test_evidence_contract.py::test_decision_claim_source_marks_legacy_committee_fallback`
  verifies no-protocol decision-claim provenance is visibly marked as legacy.
- `tests/test_swarm_governance.py::test_outcome_memory_updates_agent_reliability_not_company_conclusion`
  and
  `tests/swarm/test_generic_control_loop.py::test_swarm_loop_updates_outcome_feedback_without_storing_domain_conclusion`
  verify outcome feedback/memory keep process-only learning boundaries without
  investment-specific conclusion fields.
- `tests/test_architecture_boundaries.py::test_outcome_feedback_delegates_legacy_excluded_fields`
  prevents old decision-field names from moving back into the generic outcome
  feedback module.

Acceptance:

Evidence recovery must be driven by target pressure and protocol-declared allowed roles/tags, not hardcoded agent names.

## Phase 5: Make Evidence Recovery Generic

Current problem:

`evidence_recovery_node` likely names specific agents or handles specific target classes manually.

Target:

Evidence recovery is a generic `RecoveryProtocol` executed by RecoveryEngine.

Implement:

- `runtime/swarm/recovery_engine.py`
- `runtime/swarm/evidence_recovery.py` refactor if exists
- `tests/swarm/test_generic_recovery_engine.py`

Behavior:

- Find unresolved evidence gaps from EvidenceGraph and PheromoneField.
- Map evidence gaps to canonical targets.
- Look up recovery protocols declared by capability.
- Compute target pressure.
- Select agents by manifest tags, focus text, committee role, allowed signal types, target affinity, trust/maturity requirements, and recent reliability.
- Run recovery round.
- Re-evaluate evidence gate.
- Resolve stop-signal if recovery success condition is satisfied.
- If recovery fails, emit declared fallback candidate or block according to policy.

Required tests:

- `test_evidence_recovery_selects_agents_by_declared_roles_not_names`
- `test_evidence_recovery_works_for_toy_capability`
- `test_evidence_recovery_resolves_blocking_signal_after_success`
- `test_evidence_recovery_commits_fallback_after_failure`
- `test_evidence_recovery_trace_shows_target_pressure_agent_selection_and_outcome`

Implemented recovery progress:

- `runtime/workflows/evidence_research.py` no longer falls back to a hardcoded
  evidence-agent name list when no OS allocation is present. It loads the
  evidence-research capability protocol, reads the declared recovery protocol,
  loads capability agent manifests, and reuses the generic RecoveryEngine
  role/tag/target/trust/maturity scorer. The source-candidate-only required
  caveat delegates to `runtime/workflows/legacy_guardrails.py` until it is
  descriptor-declared.
- `tests/test_capability_runtime.py::test_evidence_research_executor_and_research_nodes_create_claim_evidence_outputs`
  now verifies the fallback source is `capability_agent_catalog_fallback`.
- `tests/test_capability_runtime.py::test_evidence_research_workflow_does_not_hardcode_legacy_recovery_agent_list`
  prevents reintroducing the legacy evidence-agent list in that workflow.
- `runtime/swarm/recovery_engine.py::build_recovery_trace` now records
  selected recovery protocol lineage (`capability_id`, source, and
  `protocol_source`) in the trace summary and recovery protocol/outcome events,
  including compatibility inference from the matching capability protocol bundle
  when older flattened recovery protocols omit `capability_id`.
- `runtime/swarm/recruitment.py::recruit_agents_for_recovery` now carries
  selected recovery protocol lineage into recruitment reports and recruited
  agent rows, so recovery staffing explanations identify the declaring
  capability protocol instead of only a flattened protocol id.
- `runtime/swarm/recovery_engine.py` now writes full selected-agent rows,
  selection reasons, and selected recovery protocol lineage into
  `recovery.agents_selected` events, so Decision Debugger recovery timelines do
  not have to infer why agents were selected from a separate trace summary.
- `runtime/swarm/control_loop.py::run_generic_swarm_control_loop` now accepts a
  `ToolRegistry` bridge and passes it into RecoveryEngine, and
  the graph runtime supplies its registry through the generic workflow host plus
  the domain workflow plan/execution bridges, so descriptor-native recovery can
  execute capability-declared recovery tools through the approved dispatch path
  instead of only selecting agents.
- `runtime/swarm/control_loop.py` now promotes RecoveryEngine trace items such
  as `recovery.protocol_selected`, `recovery.agents_selected`, and
  `recovery.tools_executed` into normalized control-loop events before the
  final `recovery.succeeded` / `recovery.failed` outcome event, so Decision
  Debugger recovery lineage can use explicit events instead of only nested trace
  payloads or derived fallback readers.
- `runtime/swarm/bottleneck_recruitment.py` now discovers agents from the
  manifest catalog when the run explicitly declares enabled capabilities and no
  agent registry/allocation payload is present. Runs without enabled capability
  metadata still emit `missing_agent_registry` instead of inventing central
  recovery agent names.
- `tests/swarm/test_generic_recovery_engine.py::test_evidence_recovery_trace_marks_selected_protocol_capability_lineage`
  locks down capability-source lineage for selected recovery protocols and
  recovery outcome events.
- `tests/swarm/test_generic_recovery_engine.py::test_evidence_recovery_trace_shows_target_pressure_agent_selection_and_outcome`
  now also verifies `recovery.agents_selected` events carry selected-agent
  reason rows plus the selected recovery protocol id.
- `tests/swarm/test_generic_control_loop.py::test_swarm_loop_recovery_recruitment_marks_protocol_capability_lineage`
  locks down capability-source lineage for recovery recruitment reports.
- `tests/swarm/test_generic_recovery_engine.py::test_bottleneck_recruitment_uses_enabled_capability_agent_catalog`
  verifies bottleneck recruitment can use a toy capability's agent manifests
  without falling back to value-investing agent names.
- `tests/swarm/test_generic_control_loop.py::test_swarm_loop_executes_declared_recovery_tools_through_registry`
  verifies the hosted generic loop runs declared recovery tools through
  `ToolRegistry` and records `recovery.tools_executed` lineage.
- `tests/swarm/test_generic_control_loop.py::test_swarm_loop_runs_recovery_before_blocking_when_recovery_declared`
  now verifies recovery protocol and agent-selection events are present in the
  control-loop event stream before recovery failure blocks candidates, and the
  recovery-tool test verifies `recovery.tools_executed` is emitted before the
  final success event.
- `tests/test_capability_runtime.py::test_domain_execution_bridge_passes_tool_registry_to_generic_recovery`
  verifies the domain workflow execution bridge passes `ToolRegistry` into the
  generic control loop, so non-`workflow_host` descriptor execution paths can run
  declared recovery tools as well.

## Phase 6: Make Quorum Candidates Capability-Declared

Current problem:

`quorum.py` may have fixed Buy / Watch / Avoid / Sell / Insufficient Data.

Target:

Quorum candidates come from capability protocol.

Implement:

- `runtime/swarm/quorum.py` refactor
- `runtime/swarm/candidate_registry.py`
- `tests/swarm/test_protocol_declared_quorum.py`

Behavior:

- Load candidates from `CapabilityPheroOSProtocol`.
- Candidate score computed from support signals, verified evidence, source independence, agent reliability, unresolved risk, stop-signal penalty, data/evidence gap, and policy-specific weights.
- Force fallback candidate when declared blocking targets are active and the fallback is declared by `candidate_fallback` or `safe_fallback`.
- Do not infer fallback authority from candidate labels such as "Insufficient Data" in explicit protocol traces; fallback-ish labels are legacy trace compatibility only.
- Do not know investment-specific candidate names except from protocol.

Required tests:

- `test_quorum_uses_declared_candidates`
- `test_quorum_toy_capability_accept_reject_insufficient_evidence`
- `test_investment_protocol_still_supports_buy_watch_avoid_sell_insufficient_data`
- `test_blocking_target_forces_declared_fallback_candidate`
- `test_source_independence_penalizes_correlated_support`
- `test_writer_receives_committed_candidate_from_generic_quorum`

Implemented quorum/fallback progress:

- `runtime/swarm/independent_scout.py` now uses the quorum trace or quorum
  policy's declared fallback candidate when low source independence forces a
  safer commit. It only treats fallback-ish labels as compatibility fallback
  for old quorum traces that lack candidate registry metadata.
- `runtime/swarm/controllers.py` now emits the generic
  `force_fallback_when_low_independence` policy key.
- `runtime/swarm/quorum_marshal.py` now reports `blocked_to_fallback` and
  explains the committed fallback candidate by label from the quorum trace,
  while preserving fallback-ish label detection only for legacy traces without
  candidate registry metadata.
- `runtime/swarm/quorum.py`, `runtime/swarm/quorum_marshal.py`,
  `runtime/swarm/governance_results.py`, and `runtime/audit_log.py` now carry generic
  `blocked_conclusion_targets` through quorum traces, marshal fallback
  explanations, Governance Results blocked targets, and run audit summaries.
  Quorum Marshal treats the generic target list as authoritative when present;
  the legacy formal/report booleans remain compatibility fields and only
  backfill missing generic targets.
- `runtime/swarm/quorum.py` now classifies publication-only blocked conclusion
  targets through the generic publish/publication target helper, so capability
  targets such as `decision:toy_publish` do not get scored as evidence-readiness
  defects merely because they are not the legacy report-publication target.
- The legacy quorum formal/report boolean backfill now lives in
  `runtime/swarm/legacy_quorum_targets.py`; quorum scoring, marshal reports,
  Governance Results, and audit summaries delegate to that compatibility
  boundary after generic `blocked_conclusion_targets` are checked.
- `runtime/swarm/candidate_registry.py` no longer marks fallback-ish labels as
  safe fallbacks for explicit protocols, and `runtime/swarm/quorum.py` leaves a
  blocked selected candidate uncommitted when no declared fallback exists.
- Generated legacy swarm protocols still preserve the old "insufficient"
  label fallback behavior, but the phrase marker now lives in
  `runtime/swarm/legacy_protocol_fields.py` behind
  `legacy_candidate_safe_fallback_value()`; explicit protocol candidates do not
  infer `safe_fallback` from labels.
- Candidate Registry missing-policy compatibility reason text now also lives in
  `runtime/swarm/legacy_protocol_fields.py`; core candidate-registry traces
  call `legacy_candidate_registry_missing_policy_reason()` instead of owning the
  legacy investment-fallback wording.
- `runtime/swarm/target_registry.py` no longer canonicalizes plain labels such
  as Buy/Watch/Sell into investment candidate targets; candidate targets come
  from declared candidate IDs/policies.
- Legacy formal/report decision-target spellings such as `formal_valuation`,
  `valuation`, `report_publication`, and `final_report` now live in
  `runtime/swarm/legacy_target_aliases.py`; the target registry delegates only
  that compatibility lookup after checking generic gate/tool aliases, so the
  core registry no longer owns the investment/report alias table.
- The legacy source-mode target spelling `wrds_only` also lives in
  `runtime/swarm/legacy_target_aliases.py`; `runtime/swarm/target_registry.py`
  still canonicalizes generic `source_mode` / `data_source_policy` targets but
  delegates concrete WRDS-only target spelling through compatibility.
- Legacy bare web/fetch tool target spellings such as `web_search`,
  `provider_web_search`, `fetch_url`, and `approved_source_fetch` now live in
  `runtime/swarm/legacy_target_aliases.py`; generic `tool:*` targets still
  canonicalize by prefix in the target registry.
- Legacy formal/report target constants and target helper exports also moved
  out of `runtime/swarm/target_registry.py`; compatibility paths now use
  `legacy_formal_valuation_target()` and
  `legacy_report_publication_target()` from
  `runtime/swarm/legacy_target_aliases.py`.
- Value-investing formal-valuation phrase aliases such as `target price` and
  `investment recommendation` now live in the capability protocol target
  declaration; remaining legacy investment target-alias audit markers live in
  `runtime/swarm/legacy_target_aliases.py` and are no longer canonicalized for
  every runtime path.
- Code-development target aliases such as `tests_failed`,
  `public_api_changed`, and `accept_patch` now live in the code capability
  protocol target declarations; remaining legacy code target-alias audit
  markers and legacy code target constants live in
  `runtime/swarm/legacy_target_aliases.py` and are no longer canonicalized or
  exported for every runtime path.
- Compliance target aliases such as `approval_required`, `email_send`, and
  `records_retention` now live in the compliance capability protocol target
  declarations; remaining legacy compliance target-alias audit markers and
  target constants live in `runtime/swarm/legacy_target_aliases.py` and are no
  longer canonicalized or exported for every runtime path. Domain workflow
  events resolve target aliases via loaded capability protocol bundles before
  falling back to global canonical target handling.
- Research target aliases such as `fake_citation`, `claim_support`,
  `source_quality`, and `source_candidates` now live in the evidence/web
  research capability protocol target declarations; remaining legacy research
  target-alias audit markers and target constants live in
  `runtime/swarm/legacy_target_aliases.py` and are no longer canonicalized or
  exported for every runtime path.
- Investment candidate target constants are no longer exported from the shared
  target registry; remaining investment candidate IDs are explicitly scoped to
  the legacy GoalRouter fallback.
- `runtime/swarm/evidence_graph.py` now builds candidate decision node
  canonical targets from declared quorum candidate IDs rather than
  re-canonicalizing display labels.
- `tests/test_swarm_governance.py::test_independence_gate_forces_declared_fallback_on_low_source_diversity`
  verifies a non-investment fallback candidate can be forced without central
  label edits.
- `tests/swarm/test_protocol_declared_quorum.py::test_blocking_target_without_declared_fallback_does_not_infer_insufficient_label`,
  `tests/test_swarm_governance.py::test_independence_gate_does_not_infer_protocol_fallback_from_insufficient_label`,
  and
  `tests/test_swarm_governance.py::test_quorum_marshal_does_not_infer_protocol_fallback_from_insufficient_label`
  prevent explicit protocols from turning an "Insufficient" label into fallback
  authority.
- `tests/test_protocol_manifest.py::test_explicit_protocol_does_not_infer_safe_fallback_from_candidate_label`
  and
  `tests/test_architecture_boundaries.py::test_protocol_loader_delegates_legacy_safe_fallback_label_inference`
  keep label-inferred fallback authority limited to the named generated-legacy
  protocol compatibility boundary.
- `tests/test_swarm_governance.py::test_quorum_trace_records_generic_blocked_conclusion_targets`,
  `tests/test_swarm_governance.py::test_quorum_treats_declared_publish_target_as_publication_not_evidence_gap`,
  `tests/test_swarm_governance.py::test_quorum_marshal_explains_generic_stop_signal_override`,
  `tests/test_swarm_governance.py::test_quorum_marshal_generic_blocked_targets_override_legacy_booleans`,
  and
  `tests/test_swarm_governance.py::test_governance_results_use_generic_quorum_blocked_conclusion_targets`
  verify non-investment blocked conclusion targets survive quorum trace,
  marshal explanation, legacy compatibility booleans, and governance result
  normalization.
- `tests/test_architecture_boundaries.py::test_quorum_core_does_not_own_legacy_formal_report_boolean_backfill`
  prevents quorum, quorum marshal, and Governance Results from re-owning the
  legacy formal/report boolean target backfill.
- `tests/test_swarm_governance.py::test_target_registry_canonicalizes_decision_targets_without_inventing_candidate_labels`
  prevents the target registry from reintroducing plain-label investment
  candidate aliases or global investment phrase target aliases.
- `tests/test_architecture_boundaries.py::test_target_registry_does_not_own_legacy_domain_alias_audit_tables`
  prevents the legacy investment/code/compliance/research target-alias audit
  tables from moving back into `runtime/swarm/target_registry.py`.
- `tests/test_architecture_boundaries.py::test_target_registry_delegates_legacy_formal_report_aliases_to_compatibility`
  prevents legacy formal/report decision-target spellings from moving back into
  the core registry alias table.
- `tests/test_architecture_boundaries.py::test_target_registry_delegates_legacy_source_policy_aliases_to_compatibility`
  prevents concrete WRDS-only source-policy target spelling from moving back
  into the core registry alias table.
- `tests/test_architecture_boundaries.py::test_target_registry_does_not_export_legacy_web_tool_targets`
  and
  `tests/test_architecture_boundaries.py::test_target_registry_delegates_legacy_web_tool_aliases_to_compatibility`
  prevent concrete web/fetch tool constants and bare aliases from moving back
  into the core registry.
- `tests/test_architecture_boundaries.py::test_target_registry_does_not_export_legacy_formal_report_targets`
  prevents the core target registry from re-exporting legacy formal/report
  target constants or helper predicates.
- `tests/test_architecture_boundaries.py::test_target_registry_does_not_export_legacy_domain_target_constants`
  prevents the core target registry from re-exporting legacy code, compliance,
  or research target constants.
- `tests/test_protocol_manifest.py::test_value_investing_target_aliases_are_protocol_declared`
  verifies value-investing target aliases survive protocol normalization and
  populate the protocol bundle's `target_aliases`.
- `tests/test_protocol_manifest.py::test_code_development_target_aliases_are_protocol_declared`
  verifies code-development target aliases survive protocol normalization and
  populate the protocol bundle's `target_aliases`.
- `tests/test_protocol_manifest.py::test_compliance_target_aliases_are_protocol_declared`
  verifies compliance target aliases survive protocol normalization and
  populate the protocol bundle's `target_aliases`.
- `tests/test_protocol_manifest.py::test_research_target_aliases_are_protocol_declared`
  verifies evidence/web research target aliases survive protocol normalization
  and populate the protocol bundle's `target_aliases`.
- `tests/test_swarm_governance.py::test_evidence_graph_candidate_nodes_use_declared_candidate_ids`
  verifies Evidence Graph candidate nodes preserve protocol-declared candidate
  IDs.

Acceptance:

Adding a new capability with candidates `approve`, `reject`, and `escalate` must not require editing `quorum.py`.

## Phase 7: Make Stop-Signal Policy Capability-Declared

Current problem:

`stop_signal.py` and tool policy may contain hardcoded web/fetch/tool sets or investment-specific output blocking.

Target:

Stop-signal behavior is driven by declared policy, with security-critical defaults still enforced globally.

Implement:

- `runtime/swarm/stop_signal_policy.py`
- `runtime/swarm/action_policy.py`
- `runtime/swarm/resolution.py`
- `tests/swarm/test_protocol_declared_stop_signal.py`

Behavior:

- Capability declares targets that may block, actions affected, writer/final judge effects, tool aliases, candidate effects, and resolution policy.
- Runtime consumers source-filter stop-signal rules, action markers, and
  resolution rules when validation flags a capability as untrusted for
  hard-blocking authority.
- Top-level `blocked_actions` declarations are converted into source-attributed
  default rules before policy merge, so mixed safe/unsafe policies can strip the
  unsafe top-level contribution without losing trusted rules.
- Global core safety remains:
  - Secrets never exposed.
  - Direct tool/model bypass forbidden.
  - High-risk permission requires confirmation.
  - Raw sensitive data never allowed unless explicitly privileged and internal.
- Capability policy may add restrictions, but cannot weaken global security.

Add resolution:

- Blocking signal has `resolution_condition`.
- Resolution authority must be declared.
- After recovery or user approval, signal may become resolved.
- Trace lineages must preserve original block and resolution.

Required tests:

- `test_stop_signal_policy_loaded_from_capability`
- `test_untrusted_hard_blocking_stop_policy_is_diagnosed_but_not_enforced`
- `test_trusted_hard_blocking_stop_policy_still_blocks_declared_actions`
- `test_untrusted_top_level_stop_policy_is_filtered_in_mixed_policy`
- `test_web_search_block_in_investment_comes_from_protocol_or_global_source_policy`
- `test_initial_signals_use_shared_source_policy_aliases`
- `test_writer_action_markers_come_from_stop_signal_policy`
- `test_final_judge_action_markers_come_from_stop_signal_policy`
- `test_new_capability_blocks_declared_tool_without_editing_stop_signal_py`
- `test_global_security_cannot_be_weakened_by_capability`
- `test_blocking_signal_resolves_only_with_declared_authority`
- `test_resolved_stop_signal_reopens_candidate`

Implemented authority progress:

- Agent stop-signal authority is now manifest-derived in
  `runtime/swarm/authority.py`: capability agents with `can_block` and
  `stop_signal` permission can request blockers, investment committee members
  remain proposal-level authorities, and non-investment capability guardrail
  agents become verified-system authorities only through their manifest
  permissions.
- Core module/global actor authority remains fixed for global safety, so system
  verifiers and gates keep their deterministic authority without encoding
  capability agent names.
- `runtime/swarm/data_gate_permissions.py` centralizes generic Data Gate
  `conclusion_permissions` interpretation for verifier promotion, Evidence
  Graph output permissions, initial stop-signal seeding, Social Immunity
  arousal, and stop-signal resolution.
- Legacy top-level formal/report Data Gate permission field names now live in
  `runtime/swarm/legacy_data_gate_permissions.py`; the generic permission reader
  and Data Gate output construction delegate to that compatibility boundary when
  enumerating or emitting old `formal_valuation_allowed` /
  `report_publication_allowed` fields.
- `runtime/swarm/signal_extractor.py` now emits initial Data Gate stop-signals
  for every blocked conclusion permission target instead of hardcoding only
  formal valuation and legacy publication branches.
- `runtime/swarm/signal_verifier.py` now promotes agent stop-signal proposals
  from generic conclusion permissions for the proposed target instead of
  hardcoding only formal-valuation/report-publication support rules; legacy
  formal/report fields continue to work through the compatibility aliases.
- `runtime/swarm/resolution.py` now resolves target-scoped stop-signals from
  generic conclusion permissions when the Data Gate allows the target, while
  keeping critic rejection as a global publication blocker.
- `runtime/swarm/stop_signal.py::report_publication_blocked` now treats any
  active declared publish/publication decision target, such as
  `decision:toy_publish`, as a publication blocker instead of checking only the
  legacy report-publication target.
- Data Gate blocker resolution now uses
  `publication_conclusion_permission_target()` for the active declared
  publish/publication permission before falling back to the legacy
  report-publication compatibility target.
- `runtime/swarm/signal_extractor.py::review_signals` now uses the same
  declared publication target for Critic rejection stop-signals, so
  `REJECT_CONDITIONAL` / `REJECT_FATAL` remain global publication blockers
  without hardcoding the legacy report-publication target in the emitter.
- `runtime/swarm/resolution.py` now treats declared StopSignalPolicy
  `resolution_policy` rules as authoritative for matching targets before
  legacy Data Gate or web-tool auto-clear paths. A matching declared policy
  must satisfy its condition and resolution authority before the blocker clears,
  while critic rejection remains a global publication veto.
- `runtime/swarm/social_immunity.py` now raises arousal from generic blocked
  Data Gate conclusion permissions instead of only the formal-valuation
  compatibility flag.
- Web-research source-policy blocking now depends on explicit `source_mode`,
  Data Gate source mode, or capability ToolPolicy source mode. The legacy
  `investment_web_search_disabled` metadata flag is no longer written by
  `runtime/graph.py` or honored by `runtime/swarm/action_policy.py` and
  `runtime/swarm/tool_plan_policy.py`.
- WRDS-only source-mode alias recognition and canonical source-mode spelling now
  live in `runtime/swarm/source_policy_modes.py`; action policy, plan policy,
  Data Gate, graph execution, and orchestration guidance call the shared
  predicate/accessor instead of owning local `WRDS-FIRST` / `WRDS_FIRST`
  compatibility checks or duplicating the canonical `WRDS_ONLY` value.
- `runtime/swarm/tool_plan_policy.py::effective_source_mode_decision_for_orchestration`
  now treats Data Gate source mode as plan-filtering authority before
  capability ToolPolicy, so Data Gate WRDS-only state strips web tools before
  execution rather than relying only on late tool blocking.
- Patroller WRDS-source readiness checks now call the shared source-policy
  helper in `runtime/swarm/tool_plan_policy.py`, keeping legacy
  `os_plan.wrds_only_mode` interpretation out of `runtime/swarm/patroller_gate.py`;
  the remaining legacy flag lookup is isolated in `runtime/swarm/legacy_tool_policy.py`.
- Patroller WRDS-source readiness detail text now also delegates to
  `runtime/swarm/legacy_tool_policy.py`, keeping WRDS-only compatibility
  wording out of `runtime/swarm/patroller_gate.py`.
- `runtime/research_selection.py`, `runtime/web_research_planner.py`, and
  `runtime/swarm/tool_plan_policy.py` now recognize selected capability
  metadata such as `capability_types` and explicit web-research flags before
  falling back to legacy skill names when deciding whether to insert or
  source-policy-filter a public web research step.
- The remaining legacy research/web/WRDS skill-name, capability-type marker,
  and metadata-flag compatibility sets now live in
  `runtime/legacy_research_selection.py`; `runtime/research_selection.py`
  keeps generic metadata and capability-type matching as the primary path and
  delegates concrete built-in markers to that compatibility boundary.
- `runtime/graph.py` now uses those shared research selectors for deterministic
  web-search planning, provider-search upgrades, and auto-fetch decisions, so
  graph-level planner behavior can follow selected capability metadata instead
  of only the built-in `web-research` / `value-investing-research` names; the
  provider-search upgrade no longer follows investment task type or committee
  labels without selected research capability metadata.
- Shared source-tool identifiers now live in `runtime/tool_names.py`, so
  `ToolRegistry`, graph execution, web planning, and evidence-research adapters
  consume one catalog instead of repeating concrete web/fetch tool IDs.
- The graph's source-tool helper tables and helper logic for search/fetch tool
  groups, auto-fetch decisions, provider-search upgrade decisions, result URL
  selection, execution failure summarization, and review source-grounding checks
  now live in `runtime/workflows/source_tool_helpers.py`; `runtime/graph.py`
  keeps compatibility wrappers and executor dispatch only.
- The legacy source-grounding keyword auto-fetch heuristic now lives in
  `runtime/workflows/legacy_source_grounding.py`; source-tool helpers delegate
  to that compatibility boundary after selected capability metadata and
  known-entity research checks have had first chance to require source
  grounding.
- `runtime/web_research_planner.py` now consumes the shared
  `runtime/workflows/source_tool_helpers.py` search-tool table instead of
  owning a separate public-web tool-name set.
- `runtime/workflows/evidence_research.py` now consumes the same shared
  search/fetch tool tables instead of owning duplicate public-web source
  retrieval constants.
- `runtime/graph.py::normalize_orchestration` and `runtime/graph.py::infer_task_type`
  now use shared selected-capability metadata selectors for research, WRDS, and
  investment defaults instead of duplicating built-in skill-name checks in the
  graph planner.
- The remaining legacy graph orchestration default builder for agent flags,
  company-name/ticker investment promotion, committee expansion, and direct
  answer collapse now lives in
  `runtime/workflows/legacy_orchestration_defaults.py`; graph keeps a thin
  `normalize_orchestration()` wrapper that resolves task type and OS-plan
  suppression before delegating to this compatibility module.
- `runtime/research_selection.py` and `runtime/wrds_company_planner.py` now
  recognize selected capability metadata such as `investment.research`,
  `financial_fundamentals`, and explicit WRDS/company-financial flags before
  falling back to the legacy value-investing skill name when deciding whether a
  WRDS company-financials step is required; a bare investment/company task type
  no longer requires WRDS company-financials without an explicit WRDS agent,
  selected data-capability metadata, or recognizable company query.
- The remaining legacy known-company research markers, non-company query
  exclusions, ticker-code exclusions, CJK company suffix hints, and
  company-query intent markers now live in
  `runtime/legacy_wrds_company_planner.py`; `runtime/wrds_company_planner.py`,
  `runtime/graph.py`, and source-tool helpers consume them through
  `known_research_company_markers()` or legacy helper delegation instead of
  importing the tuples directly.
- `runtime/research_selection.py`, `runtime/graph.py`, and
  `capabilities/wrds-financial-data/runtime_nodes.py` now distinguish direct
  WRDS data-source capability metadata such as `professional_financial_database`
  from investment-research metadata, so renamed data-source capabilities can
  infer WRDS task type and route to WRDS without letting investment-research
  capabilities bypass the graph.
- `runtime/data_gate.py::data_gate_required_decision` now resolves the active
  data contract from state when no explicit contract is supplied, so
  `runtime/graph.py::should_run_data_gate` honors descriptor
  `gate_policy.required_when` as authoritative before legacy investment/WRDS
  fallback routing; descriptor-backed "not required" decisions suppress the
  legacy graph fallback instead of being overwritten by task type or WRDS tools.
- Legacy graph Data Gate trigger routing now lives in
  `runtime/workflows/legacy_data_gate_routing.py`; `runtime/graph.py` delegates
  through that compatibility module after `data_gate_required_decision()` and
  reads the legacy Data Gate tool-name set only through
  `legacy_data_gate_tool_names()`, while
  `tests/test_architecture_boundaries.py::test_graph_does_not_own_legacy_data_gate_routing_fallback`
  guards the boundary.
- Data Gate stop-signal seeding and graph run-outcome summaries now use
  capability-agnostic wording for failed gates and publication blocks instead
  of describing every block as downstream investment analysis; WRDS-only
  confidence and internal formula messages now use report/financial-analysis
  wording rather than investment-only wording.
- Data readiness memos, Data Gate failure signals, Writer policy prompts, and
  Homeostasis recommendations now use generic publication/agent wording and
  derive displayed publication targets from declared Data Gate permissions.
- WRDS-only formal-conclusion guardrails now read the Data Gate permission via
  `data_gate_conclusion_permission()` and the legacy formal target helper,
  so declared `conclusion_permissions` can block formal conclusion wording
  without requiring the old top-level `formal_valuation_allowed` field.
- WRDS planner legacy investment default-package activation now delegates the
  investment-task predicate to `runtime/legacy_wrds_planner_defaults.py`; the
  core deterministic WRDS planner no longer owns that literal task-type check.
- Data Gate source-mode default policies now resolve through
  `runtime/legacy_data_gate_policy.py`; core contract building no longer owns
  the inline WRDS allowed-source fallback.
- Legacy formal-valuation stop-signal report wording now lives in
  `runtime/swarm/legacy_output_phrases.py`; `runtime/swarm/stop_signal.py`
  delegates the no-policy formal-valuation fallback body through that boundary.
- `tests/swarm/test_tool_plan_policy.py::test_source_policy_no_longer_uses_investment_web_search_flag`
  prevents reintroducing the investment-specific web-disable switch.
- `tests/test_web_research_planner.py::test_web_research_planner_uses_capability_metadata_not_only_legacy_skill_names`
  prevents web-search insertion from depending only on the built-in web/value
  research skill names.
- `tests/test_graph.py::test_deterministic_plan_uses_capability_metadata_for_research_selection`
  verifies graph deterministic planning follows selected capability metadata and
  does not treat investment research as a public-web-only plan.
- `tests/test_graph.py::test_provider_search_upgrade_uses_capability_metadata_not_legacy_names`
  prevents provider-search upgrade routing from depending on built-in skill
  names or investment/committee task labels alone.
- `tests/test_architecture_boundaries.py::test_graph_does_not_own_source_tool_helper_tables`
  prevents source-tool helper tables and source-grounding keyword lists from
  moving back into graph core or the web-research planner, and keeps graph
  execution, web planning, evidence-research, and ToolRegistry source-tool
  names on the shared `runtime/tool_names.py` constants.
- `tests/test_graph.py::test_selected_investment_capability_metadata_routes_to_committee_without_legacy_skill_name`
  verifies graph orchestration can select investment committee defaults from
  capability metadata rather than the built-in value-investing skill name.
- `tests/swarm/test_tool_plan_policy.py::test_source_policy_blocks_public_web_capability_metadata_in_wrds_only_mode`
  prevents WRDS-only skill partitioning from depending only on the built-in
  `web-research` skill name.
- `tests/test_swarm_governance.py::test_protocol_police_tool_policy_violation_target_fallback_is_compatibility_default`
  and
  `tests/test_architecture_boundaries.py::test_policing_delegates_legacy_default_tool_policy_violation_target`
  keep Protocol Police's empty tool-policy violation fallback behavior while
  isolating the legacy web-search target in `runtime/swarm/legacy_tool_policy.py`.
- `tests/test_research_selection.py::test_research_selection_uses_capability_metadata_before_legacy_skill_names`
  and
  `tests/test_research_selection.py::test_research_selection_keeps_legacy_skill_names_as_compatibility`
  verify renamed capabilities route by metadata while old skill names remain
  explicit compatibility.
- `tests/test_architecture_boundaries.py::test_research_selection_core_does_not_own_legacy_skill_name_sets`
  prevents the legacy research/web/WRDS skill-name sets from moving back into
  the main selector.
- `tests/test_architecture_boundaries.py::test_wrds_company_planner_does_not_own_legacy_company_detection_markers`
  prevents legacy known-company, non-company, and company-query detection marker
  tables from moving back into the WRDS company planner, graph, or source-tool
  helpers.
- `tests/test_wrds_company_planner.py::test_wrds_company_requirement_uses_capability_metadata_not_only_legacy_skill_name`
  prevents WRDS company-financials planning from depending only on the built-in
  value-investing skill name.
- `tests/test_wrds_company_planner.py::test_wrds_company_requirement_does_not_follow_task_type_without_data_signal`
  prevents WRDS company-financials planning from following investment task
  labels alone.
- `tests/test_graph.py::test_wrds_routing_uses_capability_runtime_entrypoints`
  verifies direct WRDS routing can follow data-source capability metadata while
  keeping investment-research capabilities on the normal graph path.
- `tests/test_graph.py::test_wrds_routing_legacy_fallback_is_separate_compatibility_path`
  verifies the old metadata/SQL/legacy-skill WRDS routing path still works only
  through the named compatibility fallback when descriptor routing is absent,
  with the built-in WRDS capability id isolated behind
  `legacy_wrds_financial_data_capability_id()`.
- `tests/test_graph.py::test_selected_direct_wrds_capability_metadata_infers_wrds_without_legacy_skill_name`
  verifies direct WRDS task-type inference does not depend on the legacy
  `wrds-data` skill name.
- `tests/test_graph.py::test_data_gate_graph_routing_uses_data_contract_required_policy`
  verifies graph Data Gate routing consumes descriptor `gate_policy.required_when`
  instead of depending on investment task labels.
- `tests/test_graph.py::test_publication_block_sets_blocked_run_outcome`
  verifies run outcome summaries use generic publication wording for Data Gate
  publication blocks.
- `tests/test_graph.py::test_declared_publication_permission_block_sets_blocked_run_outcome`
  and
  `tests/test_graph.py::test_declared_publication_permission_block_stops_before_final_judge`
  verify graph outcome and post-writer routing consume declared publication
  permissions before relying on stop-signal materialization or legacy
  top-level report fields.
- `tests/swarm/test_protocol_declared_stop_signal.py::test_declared_resolution_policy_prevents_data_gate_auto_clear_without_authority`
  and
  `tests/swarm/test_protocol_declared_stop_signal.py::test_declared_resolution_policy_prevents_web_tool_auto_clear_without_authority`
  verify protocol-declared resolution authority wins over legacy Data Gate and
  web-tool auto-clear behavior.

Acceptance:

The investment `web_search` block should still work, but the mechanism and trace wording should be protocol-driven or source-policy-driven, not an isolated hardcoded branch.

## Phase 8: Make Tool Policy Capability-Declared But Globally Safe

Target:

Tool access combines:

- Global PermissionPolicy
- ToolRegistry metadata
- Capability ToolPolicy
- PheroOS stop-signal / quarantine state

Implement:

- `runtime/tool_policy_resolver.py` or `runtime/swarm/tool_policy_resolver.py`
- Integrate with ToolRegistry
- `tests/test_tool_policy_resolver.py`

Rules:

- ToolRegistry remains the only execution path.
- ModelGateway remains the only model-call path.
- Capability may declare allowed/blocked tool targets.
- Global PermissionPolicy always wins over capability policy.
- Stop-signal can block tool.
- Quarantine can block tool output from EvidenceGraph/Writer.
- Tool aliases are canonicalized.

Required tests:

- `test_tool_policy_uses_capability_allowed_tools`
- `test_permission_policy_overrides_capability_allowed_tool`
- `test_stop_signal_blocks_declared_tool_aliases`
- `test_tool_output_quarantined_when_social_immunity_flags`
- `test_no_direct_tool_execution_outside_registry`

Implemented tool-policy progress:

- `runtime/swarm/policing.py` now evaluates execution-log tool calls through
  the shared ToolPolicy resolver, so Protocol Police can flag capability
  blocked-tool and allowlist violations for non-web tools instead of only
  checking the legacy WRDS-only web-tool set.
- The existing WRDS-only web/search source-policy violation keeps its
  source-policy wording, while capability ToolPolicy violations include the
  underlying `tool_policy_decision` for trace/debugger lineage.
- ToolPolicy now supports `source_policy_blocked_tool_targets`, allowing a
  capability to declare which tool targets a source mode suppresses.
  `runtime/swarm/action_policy.py`, `runtime/swarm/tool_plan_policy.py`,
  `runtime/swarm/signal_extractor.py`, `runtime/swarm/policing.py`,
  `runtime/swarm/resolution.py`, and graph tool-manifest filtering consume that
  declaration before falling back to the legacy public-web tool set.
- ToolPolicy can also declare `source_policy_block_message` and
  `source_policy_constraint_message`; source-policy stop signals and initial
  pheromone signals render those templates before falling back to legacy
  source-policy message templates in `runtime/swarm/legacy_tool_policy.py`.
- Graph WRDS-only blocked-skill reasons and blocked-tool result detail text now
  also delegate to `runtime/swarm/legacy_tool_policy.py` instead of owning
  source-policy wording inline.
- Legacy source-policy ToolPolicy field aliases such as
  `source_policy_blocking_tool_targets`, `source_mode_blocked_tool_targets`,
  and `web_research_tool_targets` now live in
  `runtime/swarm/legacy_tool_policy.py`; `runtime/swarm/protocol_schema.py` and
  `runtime/swarm/action_policy.py` delegate to that compatibility helper while
  normalized protocol/runtime output uses `source_policy_blocked_tool_targets`.
- The remaining legacy public-web tool fallback set now lives in
  `runtime/swarm/legacy_tool_policy.py`; source-policy core readers delegate to
  that compatibility boundary only when ToolPolicy does not declare
  `source_policy_blocked_tool_targets`, and `runtime/swarm/tool_plan_policy.py`
  no longer builds its own derived `WEB_RESEARCH_TOOL_NAMES` table.
- `tests/swarm/test_tool_plan_policy.py::test_policing_uses_capability_tool_policy_for_non_web_tools`
  verifies non-web tool violations come from capability ToolPolicy declarations.
- `tests/swarm/test_tool_plan_policy.py::test_effective_source_mode_uses_data_gate_before_plan_filtering`
  verifies Data Gate source mode feeds the source-mode decision and plan filter.
- `tests/swarm/test_tool_plan_policy.py::test_wrds_source_requirement_uses_source_policy_helper`
  and
  `tests/test_architecture_boundaries.py::test_patroller_uses_source_policy_helper_for_wrds_source_requirements`
  verify Patroller source-readiness checks delegate source-policy/legacy
  WRDS-only interpretation instead of owning it.
- `tests/test_architecture_boundaries.py::test_source_policy_modules_use_shared_source_mode_aliases`
  prevents source-policy action, plan, graph, and orchestration-guidance modules
  from re-owning WRDS-only source-mode alias tables, predicates, or canonical
  source-mode spelling.
- `tests/swarm/test_tool_plan_policy.py::test_source_policy_filter_uses_declared_blocked_tool_targets`,
  `tests/swarm/test_tool_plan_policy.py::test_source_policy_uses_declared_targets_before_legacy_web_tool_compatibility`,
  `tests/swarm/test_tool_plan_policy.py::test_initial_signals_use_declared_source_policy_blocked_tool_targets`,
  and
  `tests/swarm/test_tool_plan_policy.py::test_policing_uses_declared_source_policy_blocked_tool_targets`
  verify source-policy filtering, initial stop-signals, and Protocol Police
  use capability-declared blocked tool targets instead of only the legacy web
  set.
- `tests/swarm/test_tool_plan_policy.py::test_source_policy_accepts_legacy_blocked_tool_target_field_alias`
  and
  `tests/test_protocol_manifest.py::test_legacy_tool_policy_blocked_target_field_loads_as_compatibility_alias`
  verify old source-policy blocked-tool field names still normalize through the
  compatibility helper.
- `tests/test_architecture_boundaries.py::test_source_policy_delegates_legacy_tool_policy_field_aliases`
  prevents source-policy runtime/schema modules from re-owning the legacy
  ToolPolicy field names.
- `tests/test_architecture_boundaries.py::test_source_policy_core_modules_do_not_own_legacy_web_tool_set`
  prevents source-policy core modules from re-owning the static public-web tool
  compatibility set.
- `tests/test_graph.py::test_tool_manifest_filters_declared_source_policy_blocked_targets`
  verifies graph tool manifests hide declared source-policy-blocked targets.
- `tests/swarm/test_protocol_declared_stop_signal.py::test_source_policy_resolution_supports_declared_blocked_tool_targets`
  verifies source-policy stop-signals resolve for custom declared tool targets
  when the source policy no longer blocks them.

## Phase 9: Make Writer And Final Judge Generic Output Contract Consumers

Current problem:

Writer/final guardrails may contain investment-specific phrases and rules.

Target:

Writer and Final Judge consume OutputPolicy and EvidencePolicy from capability protocol.

Implement:

- `runtime/output_contract.py`
- `runtime/writer_guardrails.py` refactor
- `runtime/final_judge_guardrails.py` refactor
- `tests/test_generic_output_policy.py`

Writer input must be:

- `committed_candidate`
- `verified_claims`
- `caveated_claims`
- `blocked_claims`
- `required_caveats`
- `allowed_metrics/sources`
- `forbidden_output_patterns`
- Output mode
- Evidence graph references

Writer cannot:

- Create facts.
- Output blocked candidate.
- Remove required caveats.
- Include blocked claim.
- Include raw sensitive data.
- Output final conclusion when output policy requires defect memo.

Final Judge must check:

- Committed candidate consistency.
- Evidence graph consistency.
- Blocked claim absence.
- Required caveat presence.
- Raw data / secret absence.
- Output policy compliance.

Required tests:

- `test_writer_uses_capability_output_policy`
- `test_writer_cannot_create_unsupported_claim`
- `test_final_judge_rejects_output_inconsistent_with_committed_candidate`
- `test_investment_formal_valuation_block_still_works`
- `test_toy_capability_output_policy_blocks_custom_phrase`
- `test_writer_action_markers_come_from_stop_signal_policy`
- `test_final_judge_action_markers_come_from_stop_signal_policy`

Implemented output-policy progress:

- Code-development, compliance-workflow, and evidence-research now declare
  StopSignalPolicy `action_markers` for their writer/final-judge blocked
  actions instead of relying on central phrase tables.
- Value-investing now declares `final_judge:investment_recommendation`
  StopSignalPolicy `action_markers` alongside its writer formal-valuation
  markers, so final-judge investment recommendation detection is protocol data
  rather than an implicit central regex fallback.
- `runtime/writer_guardrails.py` now treats central writer phrase detection as
  legacy fallback only when the active stop-signal policy does not declare
  action markers.
- `runtime/writer_guardrails.py` now applies generic stop-action policy before
  the legacy swarm report policy, so declared writer actions are blocked through
  StopSignalPolicy rules instead of being preempted by investment-specific
  report checks.
- `runtime/swarm/stop_signal.py::apply_swarm_report_policy` now also supports
  arbitrary declared `writer:<target>` action markers mapped to active
  stop-signals, while retaining the formal-recommendation regex only as
  no-marker compatibility fallback isolated in
  `runtime/swarm/legacy_output_phrases.py`.
- `runtime/graph.py::next_after_writer` now uses the generic publication
  blocker helper so declared publication stop-signals stop before Final Judge.
- `runtime/swarm/policing.py` now reads OutputPolicy
  `committed_candidate_conflicts` for writer/quorum conflict checks before
  using legacy Insufficient Data wording fallback.
- `runtime/output_contract.py` and `runtime/swarm/policing.py` now read
  EvidencePolicy `raw_data_markers` for capability-specific raw/sensitive final
  output blocking. Value-investing declares WRDS/Compustat markers in its
  protocol, Protocol Police records `capability_evidence_policy` lineage for
  declared marker violations, and the old WRDS/raw-row marker list and fallback
  source label live in `runtime/legacy_output_contract.py` as
  `legacy_raw_data_marker_fallback` for no-policy compatibility plus global
  raw-row safety.
- Protocol Police and Evidence Contract now identify fallback committed
  candidates from declared `safe_fallback` or quorum `fallback_candidate`
  identity first, and only treat fallback-ish labels such as insufficient
  evidence/data as fallback authority in legacy quorum traces without
  candidate-registry metadata.
- `runtime/swarm/conclusion_claims.py`, `runtime/swarm/artifact_cues.py`, and
  `runtime/swarm/evidence_steward.py` now detect blocked writer claims by
  matching blocked Data Gate conclusion permissions to StopSignalPolicy
  `writer:<target>` action markers. The legacy investment phrase regex remains
  only as a no-marker compatibility fallback for `decision:formal_valuation`
  and now lives in `runtime/swarm/legacy_output_phrases.py`; the legacy formal
  valuation target used by Conclusion Claims, Evidence Contract, Evidence
  Steward, and Arousal is delegated through
  `runtime/swarm/legacy_data_gate_permissions.py`.
  Artifact Cue and Evidence Steward records now carry
  `blocked_target_source`/`writer_action` lineage so declared marker matches
  are distinguishable from `legacy_formal_valuation_phrase_fallback`.
- `runtime/swarm/evidence_steward.py` and
  `runtime/swarm/governance_results.py` now emit/normalize generic writer
  constraint keys for blocked claims and declared output permissions, including
  target-scoped allowed/blocked permission inventories, instead of
  investment-specific writer constraint wording.
- Evidence Steward now emits the legacy `formal_valuation_allowed` writer
  constraint only when the Data Gate actually provides that formal valuation
  permission, obtains the field name from
  `runtime/swarm/legacy_data_gate_permissions.py`, and marks it under
  `legacy_conclusion_permission_fields`.
  Generic-only conclusion permissions no longer receive an unrelated
  formal-valuation compatibility field.
- `runtime/swarm/evidence_graph.py` now turns every declared Data Gate
  `conclusion_permissions` entry into an output-permission node and writer
  contract blocker. It no longer invents a formal-valuation/report-publication
  permission pair when a Data Gate has no declared conclusion permissions;
  legacy investment runs still expose those permissions through their top-level
  compatibility flags.
- `runtime/swarm/evidence_graph.py` now gates decision/final-decision claims by
  the committed candidate's target-scoped output permission, falling back to
  the active blocked conclusion target when legacy decisions lack explicit
  target metadata. Protocol-backed Data Gates without declared conclusion
  permissions no longer inherit the legacy report-publication default for
  decision-claim output allowance.
- Auxiliary decision evidence now uses
  `publication_conclusion_permission_target()` to prefer declared
  publish/publication conclusion permissions such as `decision:toy_publish`
  before the legacy report-publication target, which is isolated in
  `runtime/swarm/legacy_data_gate_permissions.py`.
- Evidence Graph writer contracts and Signal Verifier promoted stop-signals now
  use generic agent-proposal wording instead of committee-specific proposal
  language in shared swarm modules.
- Evidence Graph permission edges now link gate blockers to any blocked output
  permission instead of treating only formal-valuation/report-publication
  permissions as globally blocked.
- `runtime/swarm/evidence_contract.py` now builds writer forbidden phrases from
  blocked Data Gate conclusion targets plus StopSignalPolicy `action_markers`
  and OutputPolicy `committed_candidate_conflicts` before using legacy no-policy
  formal-valuation wording delegated through `runtime/swarm/legacy_output_phrases.py`
  helper functions, and its remaining no-policy committed-candidate mismatch
  fallback reports the committed fallback candidate's own label instead of a
  literal investment label.
- `runtime/swarm/stop_signal.py` now applies the same marker-first detection to
  formal-valuation stop-signal report guardrails, so declared marker policies
  suppress unrelated legacy Buy/Sell wording.
- `runtime/nodes/output_chain.py` now keeps shared Critic/Writer/Final Judge
  fallback wording capability-agnostic, using governed-output language for
  committed decisions and final reports; the architecture boundary test guards
  against central investment committee/recommendation wording returning to the
  shared runtime node layer.
- Writer node metrics now use generic publication-block failure reasons
  (`data_gate_publication_blocked`, `swarm_publication_blocked`) so
  Decision Debugger lineage does not reintroduce legacy report-publication
  terminology after the generic publication blocker has fired.
- `runtime/swarm/policing.py` now enforces declared domain workflow gate actions
  from StopSignalPolicy before using graph-mode-specific compatibility checks;
  the remaining code/compliance/evidence compatibility violation bodies now live
  in `runtime/workflows/legacy_guardrails.py` instead of core Protocol Police.
- `runtime/workflows/code_development.py` and
  `runtime/workflows/evidence_research.py` now run the shared
  `attach_domain_workflow_stop_signals` bridge when direct workflow result
  helpers build a blocked `domain_workflow.gate_status`, matching the
  graph-level execution wrapper's declared stop-policy path.
- `runtime/swarm/policing.py` and `runtime/swarm/governance_results.py` now
  preserve explicit decision targets on Protocol Police writer/raw-data
  violations before using declared publish/publication Data Gate permissions,
  with the legacy report-publication block retained only as the final
  compatibility target.
- `runtime/swarm/governance_contracts.py` now declares catalog enforcement
  targets as generic governance surfaces such as `decision:blocked_output` and
  `tool:policy` instead of formal-valuation/report-publication/web-search
  defaults. Runtime Governance Results still emit the precise blocked target
  for each violation.
- `runtime/writer_guardrails.py` now delegates no-policy
  code/compliance/evidence workflow writer fallback checks to
  `runtime/workflows/legacy_guardrails.py`; any compatibility guardrail report
  includes `legacy_graph_mode_writer_fallback` through the legacy source helper,
  while declared StopSignalPolicy actions still suppress that fallback.
- `runtime/swarm/policing.py` now delegates no-policy code/compliance/evidence
  workflow violation fallbacks to `runtime/workflows/legacy_guardrails.py`; any
  compatibility violation includes `legacy_graph_mode_policing_fallback`
  through the legacy source helper, while declared domain workflow gate actions
  still suppress that fallback.
- `tests/test_generic_output_policy.py::test_declared_action_markers_disable_unrelated_legacy_writer_cues`
  prevents central fallback cues from overriding declared capability markers.
- `tests/test_generic_output_policy.py::test_legacy_writer_recommendation_fallback_action_is_preserved`
  keeps the no-policy formal-recommendation fallback behavior while isolating
  the legacy writer action in `runtime/swarm/legacy_output_phrases.py`.
- `tests/test_architecture_boundaries.py::test_core_writer_modules_do_not_own_legacy_formal_valuation_phrase_tables`
  keeps legacy formal-valuation/recommendation phrase regexes outside core
  writer/stop-signal modules, including the writer action implied by that
  fallback.
- `tests/test_swarm_governance.py::test_protocol_police_candidate_conflicts_come_from_output_policy`
  verifies policing candidate-conflict violations can be declared by a
  non-investment OutputPolicy.
- `tests/test_swarm_governance.py::test_protocol_police_preserves_declared_writer_violation_target`
  verifies Protocol Police stop-signals and Governance Results preserve a
  declared decision target before using the report-publication fallback.
- `tests/test_swarm_governance.py::test_protocol_police_raw_data_fallback_uses_declared_publication_target`
  verifies raw-data policing stop-signals and Governance Results use a
  capability-declared publication target before the legacy report-publication
  compatibility target.
- `tests/test_swarm_governance.py::test_protocol_police_writer_action_output_target_uses_publication_compatibility_alias`
  and
  `tests/test_architecture_boundaries.py::test_policing_delegates_legacy_publication_writer_action_aliases`
  keep legacy publish/report writer-action aliases isolated in
  `runtime/swarm/legacy_data_gate_permissions.py`.
- `tests/test_swarm_governance.py::test_publication_target_classifier_uses_generic_publish_suffixes`
  and the Data Gate permission boundary guard verify publication targets stay
  pattern-based without reintroducing the legacy report-publication tail in the
  generic classifier.
- `tests/test_swarm_governance.py::test_governance_contract_catalog_declares_enforcement_targets`
  verifies governance actor catalog enforcement targets stay generic rather
  than formal/report/web-search-specific.
- `tests/test_generic_output_policy.py::test_writer_raw_data_markers_come_from_capability_evidence_policy`
  and
  `tests/test_swarm_governance.py::test_policing_raw_data_markers_come_from_evidence_policy`
  verify Writer and Protocol Police raw-data checks consume
  capability-declared EvidencePolicy markers.
- `tests/test_swarm_governance.py::test_policing_legacy_fallback_uses_safe_fallback_candidate_identity`
  verifies the compatibility fallback is not tied to the Insufficient Data
  label.
- `tests/test_swarm_governance.py::test_formal_claim_detection_prefers_declared_action_markers`
  verifies artifact/evidence formal-claim detection follows declared action
  markers when present and records declared-marker lineage instead of legacy
  phrase-fallback lineage.
- `tests/test_swarm_governance.py::test_data_gate_signals_emit_generic_conclusion_permission_blocks`
  verifies Data Gate initial stop-signal seeding emits a non-investment
  conclusion target from declared permissions.
- `tests/test_data_gate.py::test_data_readiness_memo_uses_declared_publication_permission`
  verifies readiness memos display declared publication targets without legacy
  report-publication or committee wording.
- `tests/test_data_gate.py::test_wrds_only_formal_valuation_guardrail_uses_declared_conclusion_permission`
  verifies WRDS-only formal conclusion guardrails consume declared Data Gate
  conclusion permissions before legacy top-level permission fields.
- `tests/test_swarm_governance.py::test_review_rejection_signal_uses_declared_publication_target`
  verifies Critic rejection stop-signal seeding blocks the declared publication
  target instead of directly emitting the legacy report-publication target.
- `tests/test_architecture_boundaries.py::test_data_gate_permissions_do_not_own_legacy_top_level_fields`
  prevents the legacy top-level formal/report permission field map from moving
  back into the generic Data Gate permission reader.
- `tests/test_swarm_governance.py::test_social_immunity_arousal_uses_generic_blocked_conclusion_permissions`
  verifies Social Immunity arousal consumes generic blocked conclusion
  permissions.
- `tests/test_swarm_governance.py::test_claim_and_artifact_blocks_generic_conclusion_permission_markers`
  verifies artifact cues, Evidence Steward, and steward signals block a
  non-investment Data Gate conclusion permission through declared
  `writer:<target>` markers while preserving target-scoped allowed/blocked
  writer permission inventories, declared-marker lineage, and avoiding
  unrelated formal-valuation compatibility fields.
- `tests/test_swarm_governance.py::test_governance_results_normalize_actor_reports_to_runtime_contract`
  verifies normalized governance writer constraints avoid investment-specific
  boundary wording.
- `tests/test_swarm_governance.py::test_governance_results_respect_generic_blocked_output_permissions`
  verifies Governance Results treats generic declared output permissions as
  writer constraints and normalizes non-investment blocked targets.
- `tests/test_evidence_contract.py::test_writer_contract_formal_block_uses_declared_action_markers`
  and
  `tests/test_evidence_contract.py::test_writer_contract_candidate_conflicts_come_from_output_policy`
  verify the Evidence Graph writer contract follows protocol-declared phrases
  instead of investment defaults.
- `tests/test_evidence_contract.py::test_writer_contract_uses_generic_blocked_conclusion_action_markers`
  verifies the writer evidence contract derives forbidden phrases for arbitrary
  blocked Data Gate conclusion permissions through StopSignalPolicy markers.
- `tests/test_swarm_governance.py::test_swarm_report_policy_blocks_generic_declared_writer_action_marker`
  verifies the direct swarm report policy can block a non-investment writer
  action marker through a capability-declared stop-signal rule.
- `tests/test_evidence_contract.py::test_evidence_graph_outputs_all_declared_conclusion_permissions`
  verifies generic Data Gate conclusion permissions become target-scoped
  Evidence Graph output permissions and writer-contract blocked outputs.
- `tests/test_evidence_contract.py::test_evidence_graph_does_not_invent_legacy_output_permissions_without_declarations`
  verifies protocol-backed runs without Data Gate conclusion declarations do
  not receive invented formal/report output permissions.
- `tests/test_evidence_contract.py::test_decision_claim_output_permission_uses_committed_candidate_target`
  verifies final decision claims consume the committed candidate's declared
  output target instead of a formal-valuation-only permission.
- `tests/test_evidence_contract.py::test_protocol_decision_claim_does_not_inherit_legacy_publication_default`
  and
  `tests/test_evidence_contract.py::test_declared_target_permission_allows_protocol_decision_claim_without_report_default`
  verify protocol-backed decision claims require declared target or publication
  permissions instead of silently inheriting the legacy report-publication
  default.
- `tests/test_evidence_contract.py::test_key_evidence_uses_declared_publish_permission_without_report_default`
  verifies key-evidence claims can use a capability-declared publish target
  without direct Evidence Graph dependence on legacy publication defaults.
- `tests/test_evidence_contract.py::test_evidence_graph_links_gate_blocker_to_declared_output_permission`
  verifies gate blockers explain arbitrary declared blocked output permissions.
- `tests/test_evidence_contract.py::test_writer_contract_legacy_mismatch_uses_fallback_candidate_identity`
  verifies the compatibility mismatch report uses the committed fallback
  candidate identity.
- `tests/test_swarm_governance.py::test_protocol_police_does_not_infer_protocol_fallback_from_insufficient_label`
  and
  `tests/test_swarm_governance.py::test_protocol_police_uses_declared_fallback_candidate_identity`
  verify Protocol Police treats insufficient-data/evidence labels as fallback
  authority only for legacy traces or declared fallback candidates.
- `tests/test_evidence_contract.py::test_writer_contract_does_not_infer_protocol_fallback_from_insufficient_label`
  and
  `tests/test_evidence_contract.py::test_writer_contract_uses_declared_fallback_candidate_identity`
  verify the writer evidence contract follows the same declared fallback
  boundary.
- `tests/test_swarm_governance.py::test_swarm_report_policy_prefers_declared_action_markers`
  verifies direct swarm report policy enforcement also follows declared action
  markers before legacy wording.
- `tests/test_swarm_governance.py::test_protocol_police_domain_workflow_uses_declared_stop_policy_actions`
  verifies Protocol Police follows declared workflow gate actions and suppresses
  unrelated graph-mode fallback phrases when a writer stop policy is declared.
- `tests/test_domain_workflow_guardrails.py::test_builtin_workflow_guardrails_use_manifest_declared_stop_policy_before_legacy_fallback`
  verifies the real built-in code/compliance/evidence manifests drive Writer
  and Protocol Police through declared workflow gate stop policies before
  legacy fallback reports.
- `tests/test_architecture_boundaries.py::test_core_writer_and_policing_do_not_own_domain_workflow_fallback_bodies`
  prevents the legacy code/compliance/evidence fallback maps and handler bodies
  from moving back into central Writer or Protocol Police modules.
- `tests/test_protocol_manifest.py::test_builtin_workflow_capabilities_declare_stop_action_markers`
  verifies the built-in workflow protocols ship their writer/final-judge action
  markers.
- `tests/test_generic_output_policy.py::test_investment_final_judge_recommendation_marker_comes_from_protocol`
  verifies value-investing final-judge recommendation text is inferred from
  protocol-declared markers and blocked by the declared StopSignalPolicy rule.

## Phase 10: Event-Sourced Trace And Decision Debugger Lineage

Target:

Every important governance transition becomes an event.

Implement or harden:

- `runtime/swarm/trace_store.py`
- `runtime/swarm/events.py`
- `runtime/swarm/snapshot_builder.py`
- `app/routes/platform.py` endpoints

Events:

- `input.received`
- `os.plan.created`
- `capability.protocol.loaded`
- `runtime.materialized`
- `signal.created`
- `signal.verified`
- `signal.rejected`
- `signal.promoted_to_blocking`
- `signal.resolved`
- `target.pressure.updated`
- `agent.allocated`
- `agent.suppressed`
- `recovery.started`
- `recovery.succeeded`
- `recovery.failed`
- `candidate.created`
- `candidate.blocked`
- `candidate.committed`
- `tool.allowed`
- `tool.blocked`
- `artifact.quarantined`
- `claim.created`
- `claim.verified`
- `claim.blocked`
- `writer.blocked`
- `final_judge.rejected`
- `output.published`
- `outcome_feedback.updated`

Decision Debugger endpoints:

- `/platform/swarm/runs/{run_id}/timeline`
- `/platform/swarm/runs/{run_id}/why-blocked/{target}`
- `/platform/swarm/runs/{run_id}/why-committed`
- `/platform/swarm/runs/{run_id}/why-agent/{agent_id}`
- `/platform/swarm/runs/{run_id}/evidence-graph`
- `/platform/swarm/runs/{run_id}/recovery-lineage/{target}`
- `/platform/swarm/runs/{run_id}/capability-protocol`

Required tests:

- `test_event_log_reconstructs_swarm_snapshot`
- `test_why_blocked_returns_signal_lineage`
- `test_why_blocked_returns_capability_protocol_lineage`
- `test_why_committed_returns_candidate_protocol_lineage`
- `test_why_agent_returns_target_pressure_and_policy`
- `test_recovery_lineage_explains_success_or_failure`
- `test_trace_redacts_secrets_before_persisting`

Implemented Decision Debugger progress:

- `runtime/swarm/trace_store.py::why_committed` now returns
  `protocol_lineage` for the committed candidate, matching the candidate
  against top-level candidate/quorum policy and capability-declared candidate
  protocols by id, label, canonical target, or short label.
- The lineage records protocol source, intent, candidate source, committed
  candidate, matching candidate declarations, matching quorum fallback policy,
  fallback candidate identity, and matching capability protocol declarations.
- `runtime/swarm/trace_store.py::recovery_lineage` now returns target-scoped
  `protocol_lineage`, so recovery explanations include matching top-level and
  capability-declared recovery protocols for the blocked target.
- `runtime/swarm/trace_store.py::recovery_lineage` now also derives a minimal
  recovery trace from normalized `recovery.*` events when no separate recovery
  trace payload exists, preserving event-sourced status, target pressure,
  selected protocol, selected agents, and fallback candidate.
- `runtime/swarm/trace_store.py::recovery_lineage` now prefers detailed
  normalized `recovery.*` event traces over stored recovery trace payloads when
  the events carry selected protocol, selected agents, target pressure, or an
  embedded recovery trace; stored recovery traces remain a compatibility detail
  fallback for sparse legacy recovery timelines.
- Event-derived recovery traces now merge direct `protocol_id`,
  `capability_id`, source, and `protocol_source` fields into
  `selected_protocol`, so event-only debugger explanations preserve the same
  selected-protocol lineage as stored recovery traces.
- `runtime/swarm/trace_store.py::why_agent` now returns agent
  `protocol_lineage`, matching the agent's target pressure to target signals,
  top-level agent-selection policy, and capability-declared target/agent
  selection policy.
- `runtime/swarm/trace_store.py` now persists explicit runtime events from
  `swarm_protocol_trace` and `swarm_control_loop.events` before deriving
  fallback governance events; `runtime/swarm/events.py` uses the same explicit
  event collector to avoid deriving duplicate target-pressure, candidate,
  claim, outcome-feedback, signal, recovery, and agent-allocation events when
  the runtime already emitted them.
- `runtime/swarm/trace_store.py::timeline` now suppresses matching
  compatibility `pheromone_signals` timeline rows when normalized `signal.*`
  events already exist for the same signal, so stale signal side-table state
  cannot appear beside authoritative signal lifecycle events.
- `runtime/audit_log.py` now includes generic
  `swarm_governance.blocked_conclusion_targets` in run audit summaries, while
  preserving legacy formal/report blocked booleans through
  `runtime/swarm/legacy_quorum_targets.py` for compatibility.
- `runtime/audit_log.py` now preserves the legacy Data Gate publication-allowed
  audit field name through `runtime/swarm/legacy_data_gate_permissions.py`
  rather than owning that top-level field spelling.
- `runtime/audit_log.py` also exposes agent-output audit summaries as generic
  `agent_outputs`, records `agent_output_source`, and preserves old
  `committee_outputs` payloads only as `legacy_agent_outputs` compatibility
  lineage through `runtime/swarm/agent_outputs.py`.
- `runtime/audit_log.py` exposes agent-decision audit summaries as generic
  `agent_decision`, records `agent_decision_source`, and preserves old
  `committee_decision` payloads only as `legacy_agent_decision` compatibility
  lineage through `runtime/swarm/agent_decisions.py`.
- `runtime/swarm/trace_store.py` now reconstructs capability protocol bundles
  from normalized `capability.protocol.loaded` events when the stored run
  payload lacks a complete `swarm_plan`; the event-sourced bundle now restores
  target signals, top-level recovery protocols, candidate, quorum, stop-signal,
  evidence, tool, output, agent-selection, and swarm-loop policies, plus nested
  capability protocols. Why-blocked, why-committed, why-agent,
  recovery-lineage, and capability-protocol share that event-sourced bundle for
  protocol lineage.
- `runtime/swarm/trace_store.py` now also makes `agent_allocation`,
  `why_agent`, `tool_events`, and `permission_events` prefer normalized
  `swarm_events` records over compatibility side tables when explicit or
  derived `agent.*`, `tool.*`, and `permission.*` events exist.
- `runtime/swarm/control_loop.py` now writes detailed recovery trace milestones
  into `swarm_control_loop.events`, so recovery-lineage readers can consume
  normalized `recovery.protocol_selected`, `recovery.agents_selected`, and
  `recovery.tools_executed` events before falling back to stored nested
  recovery traces.
- `runtime/swarm/trace_store.py::evidence_graph` now merges normalized
  `claim.*`, `artifact.quarantined`, and blocking `signal.*` event nodes with
  compatibility evidence-table rows; matching event nodes override stale table
  node state while table edges and detail-only nodes remain available.
- `runtime/swarm/trace_store.py::why_blocked` now prefers normalized blocking
  `signal.*` events for the requested target before falling back to persisted
  pheromone signal rows, so explicit runtime signal lifecycle events can explain
  a block even without a separate signal snapshot row.
- `runtime/swarm/trace_store.py::reconstruct_pheromone_snapshot` now also
  prefers normalized `signal.*` events when rebuilding the pheromone signal
  list, deduping lifecycle events by signal id and using persisted
  `pheromone_signals` rows only as a compatibility fallback.
- `runtime/swarm/governance_results.py` now points governance trace events at
  runtime blocked targets when present, while preserving generic static
  contract enforcement targets in the event payload for catalog lineage.
- `runtime/swarm/governance_results.py` now records
  `blocked_target_source` in governance trace payloads. Runtime
  `blocked_conclusion_targets` stay authoritative, and legacy
  formal/report boolean fallback is marked as
  `legacy_quorum_boolean_fallback` while preserving every legacy blocked
  target instead of only the first one; the formal/report boolean target
  mapping itself is isolated in `runtime/swarm/legacy_quorum_targets.py`.
- `runtime/swarm/events.py` treats explicit `tool.*` and `permission.*` events
  as authoritative, so execution-log and permission-grant fallback events are
  not duplicated when the runtime already emitted policy events.
- `runtime/swarm/events.py` now derives normalized `signal.created`,
  `signal.verified`, `signal.rejected`, `signal.promoted_to_blocking`, and
  `signal.resolved` lifecycle events from stored pheromone signals when a run
  has not already emitted normalized signal events.
- `runtime/swarm/events.py` now also derives normalized
  `target.pressure.updated` events from generic control-loop target-pressure
  reports, explicit run target-pressure payloads, or the current run state when
  explicit target-pressure events are absent.
- `runtime/swarm/events.py` derives normalized `candidate.blocked` events from
  quorum candidate state and `outcome_feedback.updated` events from process-only
  outcome feedback when explicit timeline events are absent.
- `runtime/swarm/events.py` derives core lifecycle events
  (`input.received`, `os.plan.created`, `runtime.materialized`) from input
  envelope, OS plan, and runtime materialization metadata, and derives
  `candidate.created` from declared candidate policy/quorum/protocol data when
  explicit timeline events are absent.
- `runtime/swarm/events.py` derives normalized `artifact.quarantined`,
  `claim.created`, `claim.verified`, and `claim.blocked` events from input
  preflight, Social Immunity, Receiver Normalizer, and Evidence Steward reports
  when explicit timeline events are absent.
- `runtime/swarm/events.py` derives generic output lifecycle events:
  `writer.blocked` from guardrail-report drafts, `final_judge.rejected` from
  final-judge guardrail reports, and `output.published` from publishable final
  text when explicit timeline events are absent.
- `runtime/swarm/snapshot_builder.py` now includes reconstructed
  `target_pressure_updates`, `blocked_candidates`, and
  `outcome_feedback_updates`, plus quarantined artifacts and claim lifecycle
  summaries, writer/final-judge output blocks, and published-output summaries,
  core lifecycle summaries, and registered candidates, in the governance
  snapshot.
- `tests/test_swarm_trace_store.py::test_why_committed_returns_candidate_protocol_lineage`
  and
  `tests/test_api.py::test_swarm_run_decision_debugger_endpoints` verify the
  store and platform endpoint expose committed-candidate protocol provenance.
- `tests/test_swarm_trace_store.py::test_recovery_lineage_explains_success_or_failure`
  verifies recovery lineage also carries the capability protocol that declared
  the recovery rule.
- `tests/test_swarm_trace_store.py::test_recovery_lineage_derives_trace_from_recovery_events`
  verifies recovery status and selected recovery details can be reconstructed
  from normalized recovery events alone.
- `tests/test_swarm_trace_store.py::test_recovery_lineage_prefers_detailed_recovery_events_over_stored_trace`
  verifies detailed normalized recovery events override stale stored recovery
  trace payloads while preserving target-scoped recovery protocol lineage.
- `tests/test_swarm_trace_store.py::test_protocol_lineage_can_be_reconstructed_from_protocol_loaded_events`
  verifies protocol bundles, blocked-target lineage, and committed-candidate
  lineage can be reconstructed from `capability.protocol.loaded` events without
  a stored `swarm_plan`.
- `tests/test_swarm_trace_store.py::test_evidence_graph_derives_nodes_from_governance_events_when_table_empty`
  verifies the evidence graph debugger endpoint can reconstruct claim,
  artifact, and blocking-signal nodes from normalized governance events alone.
- `tests/test_swarm_trace_store.py::test_evidence_graph_prefers_governance_events_over_stale_table_nodes`
  verifies normalized governance event nodes override stale compatibility
  evidence-table nodes while retaining table-backed edges and redaction.
- `tests/test_swarm_trace_store.py::test_why_agent_returns_target_pressure_and_policy`
  verifies agent activation explanations carry capability protocol lineage.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_persists_timeline_blockers_and_quorum`
  and
  `tests/test_swarm_trace_store.py::test_swarm_trace_store_reconstructs_pheromone_snapshot_without_secret_leak`
  verify normalized signal lifecycle events appear in the timeline and
  governance snapshot without leaking sensitive signal metadata.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_derives_target_pressure_events_from_control_loop_report`
  verifies generic control-loop target pressure becomes event-sourced timeline
  and governance snapshot data with nested redaction.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_derives_candidate_block_and_outcome_feedback_events`
  verifies blocked candidates and process-only feedback become event-sourced
  governance data without storing a domain conclusion.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_derives_artifact_and_claim_lifecycle_events`
  verifies artifact quarantine and claim lifecycle reports become event-sourced
  governance data with nested redaction.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_derives_output_lifecycle_events`
  verifies writer/final-judge guardrail reports and publishable final output
  become event-sourced governance data with redacted previews.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_derives_core_lifecycle_and_candidate_created_events`
  verifies input, OS plan, runtime materialization, and candidate registration
  become event-sourced governance data without leaking secret-like input.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_persists_explicit_runtime_events_before_deriving_fallbacks`
  verifies `swarm_protocol_trace` and `swarm_control_loop.events` are persisted
  as authoritative timeline records, redacted, and not duplicated by derived
  fallback events.
- `tests/test_swarm_trace_store.py::test_timeline_prefers_signal_events_over_stale_signal_rows`
  verifies normalized signal lifecycle events suppress stale compatibility
  signal rows in debugger timelines.
- `tests/test_swarm_trace_store.py::test_swarm_trace_store_debugger_readers_prefer_event_sourced_policy_records`
  verifies the debugger's agent, tool, and permission readers prefer
  event-sourced records over compatibility side-table records.
- `tests/test_swarm_trace_store.py::test_why_blocked_prefers_event_sourced_blocking_signals`
  verifies `why_blocked` can explain a target block from a normalized
  `signal.promoted_to_blocking` event alone, while keeping redaction and
  protocol lineage intact; it also verifies the same event-only blocker appears
  in reconstructed pheromone snapshots.
- `tests/test_swarm_governance.py::test_protocol_police_preserves_declared_writer_violation_target`
  and
  `tests/test_swarm_governance.py::test_governance_results_respect_generic_blocked_output_permissions`
  verify governance trace events use runtime blocked targets while retaining
  generic static contract enforcement targets in payload lineage.
- `tests/test_swarm_governance.py::test_governance_results_use_generic_quorum_blocked_conclusion_targets`
  and
  `tests/test_swarm_governance.py::test_governance_results_marks_legacy_quorum_boolean_target_fallback`
  verify Governance Results marks generic versus legacy blocked-target lineage
  and keeps generic targets authoritative over formal/report booleans.
- `tests/test_architecture_boundaries.py::test_quorum_core_does_not_own_legacy_formal_report_boolean_backfill`
  guards the legacy quorum boolean compatibility boundary.
- `tests/test_audit_log.py::test_build_audit_record_includes_generic_blocked_conclusion_targets`
  verifies audit summaries preserve generic blocked conclusion target lineage.
- `tests/test_audit_log.py::test_audit_record_preserves_legacy_publication_allowed_field`
  and
  `tests/test_architecture_boundaries.py::test_audit_log_delegates_legacy_data_gate_permission_fields`
  verify audit summaries keep the legacy publication-allowed field only through
  the Data Gate compatibility helper.
- `tests/test_audit_log.py::test_audit_record_summarizes_generic_agent_outputs`
  and
  `tests/test_audit_log.py::test_audit_record_marks_legacy_agent_output_compatibility_source`
  verify audit records expose generic agent-output summaries and explicit legacy
  output source lineage without a public `committee_outputs` summary field.
- `tests/test_audit_log.py::test_audit_record_summarizes_generic_agent_decision`
  and
  `tests/test_audit_log.py::test_audit_record_marks_legacy_agent_decision_compatibility_source`
  verify audit records expose generic agent-decision summaries and explicit
  legacy decision source lineage without a public `committee_decision` summary
  field.

## Phase 11: Add A Toy Generic Capability To Prove Generality

Create a minimal test capability:

- `capabilities/toy-review/`

It should declare:

- Intent: `toy_review`
- Targets:
  - `gate:toy_evidence_gate`
  - `decision:toy_publish`
- Candidates:
  - `candidate:toy:approve`
  - `candidate:toy:reject`
  - `candidate:toy:insufficient_evidence`
- Quorum policy
- Stop-signal policy
- Recovery protocol
- Output policy
- Evidence policy
- Minimal agents:
  - `toy_scout_agent`
  - `toy_evidence_agent`
  - `toy_reviewer_agent`

The test capability should run through:

```text
Input
-> OSPlan
-> Capability protocol load
-> Generic Swarm Loop
-> Evidence recovery if needed
-> Quorum
-> Writer
-> Final Judge
```

Required tests:

- `test_toy_capability_declares_targets_and_candidates`
- `test_toy_capability_runs_without_graph_py_changes`
- `test_toy_capability_workflow_runs_through_generic_host`
- `test_toy_capability_orchestrator_runs_generic_workflow_host`
- `test_toy_capability_evidence_recovery_generic`
- `test_toy_capability_quorum_generic`
- `test_toy_capability_stop_signal_generic`
- `test_toy_capability_output_policy_generic`

Acceptance:

This toy capability proves the system is not investment-hardcoded.

## Phase 12: Preserve Investment Workflow As One Capability, Not The Core System

Move or wrap existing investment behavior into:

- `capabilities/value-investing-research/workflow.py`
- `capabilities/value-investing-research/data_contract.py`
- `capabilities/value-investing-research/evidence_adapter.py`
- `capabilities/value-investing-research/pheroos_protocol.json` or protocol section in `capability.json`
- `capabilities/value-investing-research/ui.schema.json`

Investment protocol should declare:

- Intents:
  - `investment_analysis`
  - `financial_data_retrieval`
- Targets:
  - `decision:formal_valuation`
  - `decision:report_publication`
  - `tool:web_search`
  - `gate:data_gate`
  - `evidence:financial_metrics`
- Candidates:
  - `candidate:investment:buy`
  - `candidate:investment:watch`
  - `candidate:investment:avoid`
  - `candidate:investment:sell`
  - `candidate:investment:insufficient_data`
- Stop-signal policies:
  - Formal valuation block
  - Publication block
  - `web_search` block in WRDS-only mode
  - Raw WRDS data leak block
- Evidence policies:
  - Final financial claims must map to metric registry / evidence graph.
  - Raw WRDS rows not allowed in final.
- Output policies:
  - Required caveats
  - Blocked phrases when formal valuation blocked
- Recovery protocols:
  - `approved_source_fetch`
  - `evidence_recovery`
  - `data_gap_recovery` when allowed

Implemented migration progress:

- `capabilities/value-investing-research/workflow.py` declares the investment
  workflow nodes, node entrypoints, WRDS planning adapter, and required
  protocols.
- `capabilities/value-investing-research/data_contract.py` declares source
  mode, source-mode policies, source rules, source validation rules,
  required packages, completeness metrics,
  acquisition/financial/earnings/package-gap profile policy, metric aliases,
  metric-registry policy and warning rules, confidence policy,
  forbidden-claim policy, claim guardrails, WRDS-only claim defect memo policy,
  estimate/non-GAAP metric groups, Data Gate required-when policy,
  required-data validation rules, formula validation rules, margin-basis
  validation rules, Compustat standard-filter rules, balance-sheet jump
  validation rules, Data Gate score policy, Data Gate
  defect memo policy, Data Readiness memo policy, profile evidence rules, acquisition-intensive profile evidence
  rules, profile warning rules,
  forward-estimate evidence-gap rules, and Data Gate output effects.
- The remaining legacy Data Gate fallback policy tables, WRDS-only claim rules,
  WRDS-only claim default message,
  no-descriptor WRDS-only claim defect memo policy,
  no-descriptor forbidden claims, no-descriptor non-GAAP/estimate metric
  groups, metric aliases, completeness defaults, source-mode/source-rule
  defaults, source-validation-rule defaults, metric-registry defaults,
  no-descriptor metric-registry entrypoint fallback warning defaults,
  no-descriptor metric-registry warning defaults, no-descriptor
  metric-registry annotation defaults,
  no-descriptor formula-validation-rule defaults, no-descriptor margin-basis
  validation-rule defaults, no-descriptor Compustat standard-filter defaults,
  no-descriptor balance-sheet jump defaults,
  no-descriptor defect memo policy defaults, no-descriptor readiness memo policy defaults,
  no-descriptor profile-policy defaults,
  no-descriptor profile evidence-rule defaults, no-descriptor profile warning-rule
  defaults, no-descriptor score-policy defaults, no-descriptor required-data validation-rule defaults,
  no-descriptor evidence-gap rule defaults, and report-claim detector regexes
  now live in `runtime/legacy_data_gate_policy.py`;
  `runtime/data_gate.py` delegates to lower-case compatibility helpers only
  after descriptor-backed policy is unavailable and no longer imports or reads
  the legacy `LEGACY_*` tables directly.
- Metric-registry usage rules and source-priority baselines now consume
  descriptor-backed `metric_registry_policy.usage_rules` and
  `metric_registry_policy.source_priority`; missing descriptor policy falls
  back to `legacy_metric_registry_policy`.
- Metric-registry large-margin warning payloads now consume descriptor-backed
  `metric_registry_policy.warning_rules.large_margin_gap` for severity, issue
  text, instruction text, and policy source; missing descriptor warning rules
  fall back to `legacy_metric_registry_warning_rule`.
- Metric-registry formula notes for filing-like gross margin candidates now
  consume descriptor-backed `metric_registry_policy.metric_annotations`; missing
  descriptor annotations fall back to `legacy_metric_registry_annotation`, and
  emitted metrics record `formula_policy_source` lineage.
- Data Gate score penalties and period bonuses now consume descriptor-backed
  `gate_policy.score_policy` merged over legacy score defaults; missing
  descriptor score sections fall back to `legacy_gate_score_policy`, and emitted
  Data Gate score fields record `*_score_source` lineage.
- Data Gate defect memo title, intro, headings, required fixes, and
  registry-warning fix now consume descriptor-backed `gate_policy.defect_memo`;
  missing descriptor memo policy falls back to `legacy_data_defect_memo_policy`.
- Data Readiness memo title, intro, headings, no-blocker text, and required
  next steps now consume descriptor-backed `gate_policy.readiness_memo`; missing
  descriptor readiness memo policy falls back to
  `legacy_data_readiness_memo_policy`.
- Data Gate mandatory trigger policy now consumes
  `gate_policy.required_when`; missing descriptor policy falls back to
  `legacy_data_gate_required_policy`, whose investment/WRDS compatibility
  matches now live behind `legacy_data_gate_required_matches`.
- Data Gate required-data blocking now consumes descriptor-backed
  `gate_policy.required_data_rules.company_financials` for severity, code, and
  message; missing descriptor rule payload falls back to
  `legacy_data_gate_required_policy`.
- Data Gate internal formula validation now consumes descriptor-backed
  `gate_policy.formula_validation_rules` for severity, code, message, and
  policy source; missing descriptor formula rules fall back to
  `legacy_formula_validation_rule`.
- Data Gate high-depreciation margin-basis validation now consumes
  descriptor-backed `gate_policy.margin_basis_rules` for severity, code,
  message, and policy source; missing descriptor margin-basis rules fall back
  to `legacy_margin_basis_rule`.
- Data Gate Compustat standard-filter validation now consumes descriptor-backed
  `gate_policy.compustat_standard_filter_rules` for allowed values, warning
  payload, and policy source; missing descriptor standard-filter rules fall back
  to `legacy_compustat_standard_filter_rule`.
- Data Gate material balance-sheet jump validation now consumes
  descriptor-backed `gate_policy.balance_sheet_jump_rules` for thresholds,
  issue templates, blocking flags, and policy source; missing descriptor
  balance-sheet jump rules fall back to `legacy_balance_sheet_jump_rule`.
- Data Gate source-mode verification level and allowed sources now consume
  descriptor-backed `source_mode_policies`; missing descriptor policy falls
  back to `legacy_source_mode_policy`.
- Data Gate source timing rules now consume descriptor-backed `source_rules`,
  and source timing/reconciliation/identity validation payloads now consume
  descriptor-backed `source_validation_rules`, including official metric
  mismatch and ambiguous company-identity payloads; missing descriptor rules or
  validation payloads fall back to `legacy_source_rules`.
- Data Gate forbidden-claim policy now consumes descriptor-backed
  `forbidden_claims` and records `data_contract_forbidden_claims`; missing
  descriptor claim policy falls back to `legacy_forbidden_claims` instead of an
  inline runtime default.
- Data Gate non-GAAP and estimate metric-group policy now consumes
  descriptor-backed `gate_policy.non_gaap_metrics` /
  `gate_policy.estimate_metrics`; missing descriptor metric groups fall back to
  `legacy_gate_metric_group`, and Data Gate outputs record
  `non_gaap_metric_group_source` / `estimate_metric_group_source`.
- Data Gate forward-estimate evidence-gap policy now consumes descriptor-backed
  `gate_policy.evidence_gap_rules.forward_estimates_missing`; missing
  descriptor rules fall back to `legacy_gate_evidence_gap_rule`, and emitted
  gaps record `policy_source`.
- Acquisition-intensive profile evidence gaps now consume descriptor-backed
  `gate_policy.profile_evidence_rules.acquisition_intensive` for severity, gap
  code, message, blocking, and valuation-scope policy; missing descriptor rules
  fall back to `legacy_profile_evidence_rule`, and emitted gaps record
  `policy_source`.
- Acquisition-heavy missing-non-GAAP warnings now consume descriptor-backed
  `gate_policy.profile_warning_rules.acquisition_intensive_missing_non_gaap`
  for severity, code, message, and blocking policy; missing descriptor rules
  fall back to `legacy_profile_warning_rule`, and emitted warnings record
  `policy_source`.
- Acquisition-intensive profile detection now marks descriptor-backed
  `data_contract_profile_policy` versus `legacy_profile_policy` fallback when
  severity, reason text, identity markers, thresholds, evidence requirements,
  or valuation wording are absent from the descriptor.
- Financial-company and negative/non-meaningful-earnings profile records now
  likewise read descriptor-backed `profile_policies` for severity, reason text,
  required evidence, and writer policy before falling back to
  `legacy_profile_policy`; the legacy profile-policy text lives in
  `runtime/legacy_data_gate_policy.py` instead of `runtime/data_gate.py`.
- Segment, CRSP market-data, and peer-comparison package-gap profile records
  and their evidence-gap rows also read descriptor-backed `profile_policies`
  for severity, reason text, required evidence, writer policy,
  gap code/message, and blocking flags before falling back to
  `legacy_profile_policy`; their legacy policy text lives in
  `runtime/legacy_data_gate_policy.py`.
- Data Gate metric normalization now consumes descriptor-backed
  `metric_aliases` and records `data_contract_metric_aliases`; missing
  descriptor aliases fall back to `legacy_metric_aliases`.
- WRDS-only report limitation boxes and structured Data Gate limitation items
  now come from descriptor-backed `source_mode_limitations`; missing descriptor
  limitation policy falls back to `legacy_wrds_only_limitations`.
- `capabilities/value-investing-research/data_contract.py` now declares
  `claim_guardrails.wrds_only_disallowed_claims`; `runtime/data_gate.py` uses
  those data-contract rules for WRDS-only report claim blocking and only falls
  back to `legacy_wrds_only_claim_guardrail` when no contract rules are present.
- WRDS-only claim defect memo required fixes now come from
  `claim_guardrails.wrds_only_required_fixes`; missing descriptor fixes fall
  back to `legacy_wrds_only_claim_guardrail`.
- WRDS-only claim defect memo title, intro, and headings now come from
  `claim_guardrails.wrds_only_defect_memo`; missing descriptor memo policy
  falls back to `legacy_wrds_only_claim_defect_memo_policy`.
- WRDS-only claim guardrail fallback default text now lives behind
  `legacy_wrds_only_claim_guardrail_default_message`, so malformed
  compatibility claim rules do not inject domain text from `runtime/data_gate.py`.
- WRDS-only high-confidence report blocking now cites descriptor-backed
  `data_contract_confidence_policy` only when the built contract marks the
  confidence policy source as descriptor-backed; maximum-confidence limits and
  validation issue payloads come from `confidence_policy`, while missing
  descriptor confidence policy falls back to
  `legacy_wrds_only_confidence_guardrail`.
- WRDS-only non-GAAP source blocking now cites descriptor-backed
  `data_contract_metric_requirement` from `gate_policy.non_gaap_metrics` and
  descriptor-backed `gate_policy.metric_requirement_rules`; missing descriptor
  metric policy or validation issue payload falls back to
  `legacy_wrds_only_metric_requirement`.
- WRDS-only formal-valuation conclusion blocking now cites descriptor-backed
  `data_contract_output_effect` from `gate_policy.output_effects`; missing
  descriptor output effects fall back to `legacy_wrds_only_output_effect`, and
  the old blocking-errors, publication-blocked, formal-valuation-blocked, and
  passed next-action / valuation-scope defaults are isolated in
  `runtime/legacy_data_gate_policy.py`.
- WRDS-only quarterly-trigger blocking now cites descriptor-backed
  `data_contract_required_period_policy` from the WRDS data plan's required
  actual periods and descriptor-backed `gate_policy.required_period_rules`;
  missing descriptor period policy or validation issue payload falls back to
  `legacy_wrds_only_required_period_policy`.
- Deterministic WRDS data planning still exposes `runtime/wrds_planner.py` as
  the planner API, but the legacy account package availability profile,
  package catalog, default investment research questions, semiconductor
  package expansion, and OptionMetrics market-risk heuristics now live in
  `runtime/legacy_wrds_planner_defaults.py`.
- Metric-registry construction is selected through the value-investing
  workflow's descriptor-declared `metric_registry_entrypoint`, with a traceable
  deterministic runtime fallback; invalid-entrypoint fallback warnings now cite
  `legacy_metric_registry_entrypoint_warning`.
- Metric-registry formula annotations for filing-like gross margin candidates
  are descriptor-backed through `metric_registry_policy.metric_annotations`,
  with no-descriptor compatibility isolated in
  `legacy_metric_registry_annotation`.
- WRDS execution-result collection is declared by the WRDS capability runtime
  descriptor as a `wrds_result` result collector and dispatched by the graph
  runtime when active.
- WRDS company-tool argument normalization is declared by the WRDS capability
  runtime descriptor and dispatched by the graph runtime when active.
- Direct WRDS route/bypass decisions and direct-WRDS orchestration are declared
  by the WRDS capability runtime descriptor's routing entrypoints, with
  deterministic compatibility fallbacks for invalid or missing descriptors
  isolated in `runtime/workflows/legacy_wrds_routing.py` instead of owned by
  `runtime/graph.py`; the legacy direct-WRDS one-step plan scaffold also lives
  in that compatibility module.
- Descriptor graph modes can now explicitly defer generic workflow execution
  from orchestration into the LangGraph `workflow_host` node, so arbitrary
  capability workflow node entrypoints are hosted by a descriptor-native graph
  node instead of running only as an orchestration augmentation. `workflow_host`
  routing no longer rejects code/compliance/evidence descriptors by static
  graph-mode name when they are explicitly deferred; ordinary planned traces
  still stay on their declared graph-node path.
- Legacy graph task-type aliases, task inference hints, direct-answer
  complexity markers, and quant/domain analysis hints are isolated in
  `runtime/workflows/legacy_graph_routing.py`, leaving `runtime/graph.py` as a
  compatibility wrapper rather than the owner of those heuristic tables.
- Legacy descriptorless workflow node order and fallback trace source are
  isolated in `runtime/workflows/legacy_routing_aliases.py`, leaving
  `runtime/workflows/routing.py` to prefer capability workflow descriptors and
  report `legacy_default_graph` only when the compatibility order is used.
- Investment/WRDS orchestration prompt guidance is declared by the
  value-investing workflow descriptor's `orchestration_guidance`; the graph
  prompt consumes descriptor/ToolPolicy source-mode guidance through
  `runtime/workflows/orchestration_guidance.py`, with old no-descriptor prompt
  wording and no-guidance source-mode templates isolated in
  `runtime/workflows/legacy_orchestration_guidance.py`.
- Tool Health Sentinel recommendations now consume descriptor-backed
  `swarm_loop_policy.tool_health_recommendations`; missing recommendations fall
  back to `runtime/swarm/legacy_tool_health_policy.py`, which also owns the
  legacy failure-hint catalog, source label, and default signal content used
  when no recommendation is present.
- Encounter Rate scheduler recommendations now consume descriptor-backed
  `swarm_loop_policy.encounter_rate_recommendations`; missing recommendations
  fall back to `runtime/swarm/legacy_encounter_rate_policy.py`, including the
  legacy source label.
- Arousal Controller signal text now consumes descriptor-backed
  `swarm_loop_policy.arousal_signal_template`; missing templates fall back to
  `runtime/swarm/legacy_arousal_policy.py`, including the legacy template source
  label.
- Social Immunity recommendation and arousal-signal wording now consume
  descriptor-backed `swarm_loop_policy.social_immunity_recommendations` and
  `swarm_loop_policy.social_immunity_arousal_signal_template`; missing
  entries and source labels fall back to
  `runtime/swarm/legacy_social_immunity_policy.py`, while
  prompt-injection/secret-like artifact detection remains fixed global safety
  behavior.
- Homeostasis recommendation and signal wording now consume descriptor-backed
  `swarm_loop_policy.homeostasis_recommendations` and
  `swarm_loop_policy.homeostasis_signal_template`; missing entries fall back to
  `runtime/swarm/legacy_homeostasis_policy.py`, including legacy source labels,
  deterministic threshold defaults, and recommendation trigger rules, while
  pressure variable calculation remains runtime control logic.
- Lane Scheduler now consumes descriptor-backed
  `swarm_loop_policy.lane_policy` for preferred lanes, term/lane preferences,
  fallback order, and assignment signal text; missing lane policy falls back to
  `runtime/swarm/legacy_lane_policy.py`, including legacy source labels, while
  immutable writer and third-party lane restrictions live in
  `runtime/swarm/global_lane_safety_policy.py` and override capability policy.
- Maturity Lifecycle now consumes descriptor-backed
  `swarm_loop_policy.maturity_policy` for maturity order, promotion/demotion
  thresholds, allowed actions, and maturity signal text; missing policy falls
  back to `runtime/swarm/legacy_maturity_policy.py`, including legacy source
  labels, while immutable untrusted/user-installed maturity caps and blocker
  reach live in
  `runtime/swarm/global_maturity_safety_policy.py` and override capability
  policy.
- Independent Scout now consumes descriptor-backed
  `swarm_loop_policy.independent_scout_policy` for source-family rules,
  independence threshold defaults, low-independence/fallback reason text, and
  independence signal wording; missing policy falls back to
  `runtime/swarm/legacy_independent_scout_policy.py`, including legacy source
  labels and quorum-controller threshold/fallback override field names, while
  those overrides remain traced.
- Swarm Controller action wording and default action targets now consume
  descriptor-backed `swarm_loop_policy.controller_action_policy`; missing
  action policy falls back to
  `runtime/swarm/legacy_swarm_controller_policy.py`, including the legacy source
  label, while mandatory-member retention still uses manifest metadata and
  global scheduling safety.
- The shared Data Gate still performs deterministic safety evaluation, but it
  now reads score penalties, period bonuses, defect/readiness memo policy,
  profile evidence satisfaction, and output-effect names from the selected
  capability data contract or traced legacy compatibility policy.
- Remaining migration work in this phase is limited to reducing specialized
  graph/source-policy compatibility fallbacks after older descriptor shapes are
  no longer supported.

Required tests:

- `test_existing_investment_flow_still_works`
- `test_wrds_only_blocks_web_search`
- `test_data_gate_blocks_formal_valuation`
- `test_quorum_forces_insufficient_data_when_blocked`
- `test_writer_cannot_write_target_price_when_formal_valuation_blocked`
- `test_raw_wrds_rows_not_in_final`
- `test_investment_flow_uses_protocol_manifest_not_core_hardcode`
- `test_data_gate_does_not_own_legacy_policy_tables`
- `test_wrds_planner_does_not_own_legacy_investment_package_defaults`
- `test_data_contract_forbidden_claims_legacy_fallback_when_descriptor_omits_policy`
- `test_data_gate_metric_groups_legacy_fallback_when_descriptor_omits_policy`

## Phase 13: Security And Non-Regression Requirements

Do not break existing safety properties.

Hard invariants:

1. Secret must not enter prompt, frontend, trace, or logs.
2. Tool calls must go through ToolRegistry.
3. Model calls must go through ModelGateway.
4. High-risk permission requires confirmation.
5. Agent-emitted signal cannot directly become verified/blocking unless authority and verifier allow it.
6. Capability cannot weaken global safety policy.
7. Writer cannot create facts.
8. Final claim must be backed by EvidenceGraph or caveated/blocked.
9. Stop-signals must actually block relevant tools/writer/final/candidates.
10. Outcome Memory must store process reliability only, not domain conclusions.

Required tests:

- `test_secret_not_in_prompt_frontend_trace`
- `test_no_direct_model_calls_outside_gateway`
- `test_no_direct_tool_calls_outside_registry`
- `test_agent_cannot_emit_verified_signal_directly`
- `test_agent_cannot_emit_blocking_without_authority`
- `test_external_content_cannot_directly_become_evidence`
- `test_prompt_injection_artifact_quarantined`
- `test_outcome_memory_does_not_store_domain_conclusion`
- `test_capability_cannot_weaken_global_security_policy`

Implemented security progress:

- `runtime/swarm/authority.py` now separates an agent's manifest permission to
  request a blocker from authority to create a verified fact or hard blocker.
  Signals with `metadata.agent_emitted`, `capability_agent`, legacy
  `committee_agent`, `swarm_execution_loop`, no `source_module`, or an
  agent-equivalent `source_module` are treated as agent self-assertions and
  cannot satisfy `can_create_fact` or `can_create_blocker`.
- EvidenceGraph therefore keeps even high-trust agent-authored
  `verification_state=blocking` signals as proposals until a verifier/system
  module, such as `swarm_signal_verifier`, emits the promoted signal.
- `tests/test_swarm_governance.py::test_domain_blocking_agents_can_request_but_not_self_verify_blockers`
  and
  `tests/test_swarm_governance.py::test_evidence_graph_keeps_agent_self_verified_signal_as_proposal`
  cover the no-agent-self-verification invariant.
- `tests/test_swarm_governance.py::test_agent_stop_signal_promotion_uses_generic_conclusion_permission`
  and
  `tests/test_swarm_governance.py::test_agent_stop_signal_stays_contested_when_generic_permission_allows_target`
  cover generic Data Gate permission-backed promotion for non-formal decision
  targets.
- `tests/test_swarm_governance.py::test_stop_signal_resolution_uses_generic_conclusion_permission`
  and
  `tests/test_swarm_governance.py::test_data_gate_stop_signal_resolution_uses_declared_publication_permission`
  cover generic permission-backed stop-signal resolution for target-scoped
  blockers and Data Gate blockers with declared publication permissions.
- `tests/test_swarm_governance.py::test_stop_signal_resolution_keeps_publication_block_when_review_rejects`
  covers the global publication review override.
- `runtime/output_contract.py` now treats final-output raw-data blocking as a
  global non-weakenable safety rule: capability EvidencePolicy can declare
  additional `raw_data_markers`, but `raw_data_allowed_in_final=true` no longer
  disables marker detection for final text.
- Legacy no-policy raw-data marker fallback values and the
  `legacy_raw_data_marker_fallback` source label are isolated in
  `runtime/legacy_output_contract.py`; `runtime/output_contract.py` owns only
  global raw-row safety markers and delegates old WRDS/Compustat markers through
  that compatibility boundary.
- WRDS public API/trace and model-context payload redaction now lives in
  `runtime/workflows/wrds_payload_safety.py`; graph normalization calls this
  shared safety helper instead of owning the raw-row key table or recursive
  sanitizer, and audit logging uses the same helper for WRDS result summaries
  instead of owning a separate raw-data summary path.
- `runtime/writer_guardrails.py` and `runtime/swarm/evidence_contract.py` now
  expose that same rule to the model-facing writer prompt and writer evidence
  contract, while preserving the declared attempted allowance for audit
  diagnostics.
- `tests/test_generic_output_policy.py::test_capability_cannot_allow_raw_data_in_final_output`
  and
  `tests/test_evidence_contract.py::test_writer_contract_raw_data_policy_cannot_be_weakened`
  cover the no-raw-sensitive-final-output invariant.
- `runtime/swarm/evidence_contract.py` now treats
  `output_policy.writer_can_create_facts=true` as audit metadata only; the
  effective writer evidence contract always keeps `writer_can_create_facts`
  false and continues blocking unsupported strong claims.
- `tests/test_generic_output_policy.py::test_capability_cannot_allow_writer_to_create_facts`
  and
  `tests/test_evidence_contract.py::test_writer_contract_fact_creation_policy_cannot_be_weakened`
  cover the no-writer-fact-creation invariant.
- `app/routes/wrds.py` now dispatches authenticated platform WRDS API requests
  through `ToolRegistry` instead of constructing `WRDSTools` directly, keeping
  user/API-triggered WRDS execution on the same registry boundary as runtime
  tool execution.
- `tests/test_architecture_boundaries.py::test_platform_wrds_routes_dispatch_through_tool_registry`
  covers that route-level ToolRegistry boundary.
- `tests/test_architecture_boundaries.py::test_tool_implementations_are_instantiated_only_at_registry_boundaries`
  now guards concrete tool implementation construction so runtime/app/capability
  code cannot quietly instantiate `WorkspaceTools`, `WebTools`, `WRDSTools`, or
  public financial tools outside the ToolRegistry or the narrow WRDS
  connection-control adapter.

Implemented model-routing progress:

- `runtime/llm.py` now supports generic `agent_model_overrides` plus
  `ModelConfig.model_for(...)`, so capability agent manifests can use arbitrary
  `model_attr` values without adding new dataclass fields for each agent name.
- `runtime/runtime_context.py` preserves scoped model-provider overrides for
  unknown manifest model attributes instead of discarding them.
- Legacy scoped model-role aliases and single/mixed-provider compatibility
  role maps now live in `runtime/legacy_model_roles.py`; runtime materialization
  delegates there instead of enumerating value-investing model fields inline.
- RuntimeContext legacy WRDS capability validation issue payloads now live in
  `runtime/legacy_runtime_validation.py`; the generic validator delegates the
  WRDS capability/tool-name compatibility details instead of owning the blocking
  messages inline, and the graph preflight fatal-issue classifier delegates the
  old WRDS validation issue-code list to the same compatibility module.
- Value-investing committee member execution now resolves manifest model
  attributes through `ModelConfig.model_for(...)` while retaining existing
  compatibility fields and fallbacks.
- `runtime/graph.py` now stores the model dependency as `model_gateway`, and
  `_chat_with_fallback()` plus provider-native web search call that boundary
  explicitly; the old `llm` constructor keyword remains only as a compatibility
  alias for existing tests and adapters.
- `runtime/graph.py` now types that model dependency through the generic
  `runtime/ports.py::ChatModelClient` port rather than the direct
  `runtime/llm.py::LLMClient` protocol, so graph construction depends on the
  ModelGateway boundary contract instead of the concrete model-client module.
- `runtime/factory.py` and FastAPI runtime assembly now prefer
  `model_gateway=` so new runtime construction follows the ModelGateway boundary
  vocabulary instead of passing model clients as graph-owned LLMs.
- `tests/test_runtime_materializer.py::test_model_config_scopes_provider_to_arbitrary_manifest_model_attr`
  and `tests/test_graph.py::test_committee_member_model_lookup_uses_manifest_model_resolver`
  cover generic manifest model routing.
- `tests/test_runtime_materializer.py::test_model_config_scoped_provider_uses_legacy_agent_scope_alias`
  and
  `tests/test_architecture_boundaries.py::test_runtime_context_does_not_own_legacy_model_role_alias_tables`
  cover the legacy model-role compatibility boundary.
- `tests/test_architecture_boundaries.py::test_runtime_context_delegates_legacy_wrds_validation_details`
  covers the legacy RuntimeContext WRDS validation boundary.
- `tests/test_graph.py::test_runtime_model_gateway_keyword_is_chat_boundary`
  and
  `tests/test_architecture_boundaries.py::test_graph_model_calls_use_model_gateway_boundary`
  cover the graph ModelGateway call boundary and prevent `self.llm.chat(...)`
  from reappearing in the runtime graph.
- `tests/test_architecture_boundaries.py::test_graph_model_dependency_is_typed_as_runtime_port`
  prevents the graph from re-importing the direct LLM client protocol as its
  model dependency type.

## Phase 14: Documentation And Migration Notes

Update docs:

- `docs/pheroos_protocol_manifest.md`
- `docs/pheroos_swarm_loop.md`
- `docs/capability_runtime.md`
- `docs/decision_debugger.md`
- `docs/migration_from_static_rules.md`
- `AGENTS.md` if present

Docs must explain:

1. Difference between static prototype and protocol-declared PheroOS.
2. How a capability declares targets/candidates/recovery/quorum/stop-signal/output policy.
3. How GoalRouter uses capability declarations.
4. How Generic Swarm Control Loop works.
5. How evidence recovery selects agents dynamically.
6. How to add a new capability without editing `graph.py`/`quorum.py`/`goal_router.py`.
7. How global safety policies override capability policies.
8. How Decision Debugger traces why blocked/why committed/why agent.

Implemented documentation progress:

- `docs/pheroos_protocol_manifest.md` documents protocol locations,
  StopSignalPolicy `action_markers`, OutputPolicy defect memos, validation, and
  compatibility loading.
- `docs/pheroos_swarm_loop.md` documents the generic target-pressure loop,
  recovery, quorum, stop signals, output contracts, and trace flow.
- `docs/capability_runtime.md` documents capability entrypoints, workflow
  descriptors, protocol authority, and adding a capability without core router
  edits.
- `docs/decision_debugger.md` documents persisted trace data, debugger
  endpoints, and why-blocked/why-committed/why-agent/recovery/protocol lineage.
- `docs/migration_from_static_rules.md` documents the static-to-protocol
  migration rules, required evidence, and remaining compatibility fallbacks.
- `AGENTS.md` records protocol migration rules for future repository work.

## Final Acceptance Criteria

The goal is complete only when:

1. A new capability can declare targets, candidates, recovery protocols, quorum policy, stop-signal policy, evidence policy, output policy, and agent selection policy without editing core router/quorum/graph code.
2. `goal_router.py` no longer depends on `LEGACY_DEFAULT_TARGETS_BY_INTENT` as the primary mechanism. Any fallback is legacy-only and traced.
3. `runtime/graph.py` is no longer the source of domain truth. It hosts or delegates to capability workflow entrypoints.
4. Evidence recovery selects agents dynamically by target pressure, tags, roles, affinity, trust, maturity, and capability protocol. It must not hardcode agent names.
5. Quorum candidates come from capability protocols. Buy/Watch/Avoid/Sell remain valid only because the investment capability declares them.
6. Stop-signal policies come from capability protocols plus global security defaults. Tool aliases are canonicalized.
7. Writer and Final Judge consume generic OutputPolicy/EvidencePolicy, not investment-only rules.
8. Generic Swarm Control Loop can run at least one non-investment toy capability end to end.
9. Investment workflow still passes existing safety tests.
10. Decision Debugger can explain:
    - Why target was blocked.
    - Why candidate was committed.
    - Why agent was activated.
    - How recovery ran.
    - Which capability protocol produced the rule.
11. Security invariants are preserved:
    - No secrets in prompt/frontend/log/trace.
    - No raw WRDS rows in final.
    - No direct model/tool calls outside gateways.
    - No agent self-verification.
    - No capability weakening global policy.
12. Tests pass:
    - Existing tests.
    - New protocol manifest tests.
    - Generic swarm loop tests.
    - Toy capability tests.
    - Investment non-regression tests.
    - Security tests.

When done, provide:

- Files changed
- Architectural changes
- Remaining static fallbacks, if any
- Tests run and results
- Known limitations
- Next recommended refactors

## Important

Do not claim the system is fully generic if any of these remain primary mechanisms:

- `LEGACY_DEFAULT_TARGETS_BY_INTENT` as the main source of target routing
- Investment candidates hardcoded in quorum core
- Evidence recovery hardcoding agent names
- `graph.py` hardcoding all domain workflows
- Tool policy relying only on hardcoded sets without protocol declaration
- Writer/final judge using only investment-specific checks without generic output policy
