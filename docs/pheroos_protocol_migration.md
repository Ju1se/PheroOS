# PheroOS Protocol Migration Map

This map is the Phase 0 gate for `docs/pheroos_protocol_migration_plan.md`.
It records the current static-rule locations, why each is not yet generic, the
target replacement, risk, and tests needed before broad refactoring.

## Current-State Findings

### 1. OS Kernel Intent And Capability Inference

- Evidence: legacy keyword tuples for investment, compliance, evidence research,
  portfolio, document, data, code, and financial-data routing now live in
  `runtime/legacy_os_intents.py`, while `OSKernel.plan()` asks loaded capability
  protocol manifests for declared intents before falling back. Protocol intent
  matching uses declared intent strings, capability id/name, and
  target-declared keywords; manifests can expose those declarations through a
  full `protocol` block or `swarm.intents` plus existing swarm targets. Public
  web-research, compliance, evidence-research, code-development,
  document-writing, data-analysis, and value-investing portfolio review now
  declare first-class `protocol` blocks with targets, candidates, quorum,
  stop-signal, evidence, tool, and output policies where applicable, and
  code-development, compliance-workflow, evidence-research, document-writing,
  data-analysis, web-research, and value-investing declare protocol-owned
  `intent_keywords` and `required_capability_types` or per-intent requirement
  overrides for their OS routes. Protocol
  `protocol_required_capability_types()` adds the selected protocol
  capability's own types plus protocol-declared `required_capability_types`
  without editing the central static map. Value-investing now declares its WRDS
  data dependency through that protocol field, and can override dependencies
  with `required_capability_types_by_intent` so `portfolio_review` does not
  inherit WRDS/professional-database requirements. Cross-intent keyword matches
  are confidence-gated so one broad target keyword, such as `source`, cannot
  steal a task from a clearer fallback intent such as code development. If an
  explicit selected protocol declares an intent but no usable capability types
  or `required_capability_types`, the OS plan now suppresses legacy static
  requirement fallback, emits `os.required_capabilities.needs_capability`, and
  returns `needs_capability` instead of borrowing another capability's central
  defaults. If an explicit protocol is otherwise resolvable but declares no
  goal targets, the GoalRouter `protocol_targets_missing` result now makes the
  OS plan not runtime-ready instead of silently proceeding. OS plans now include
  `os_routing_trace` events that record the legacy inferred intent, whether it
  was used or superseded by protocol intent matching, and whether required
  capability types came from protocol declarations, missing protocol
  requirements, or the legacy static fallback, and `runtime/os_kernel.py` no
  longer owns the legacy intent vocabulary or static intent-to-requirement map.
- Why not fully generic yet: legacy heuristic intent inference and
  `required_capability_types()` remain as central compatibility fallbacks when
  no explicit protocol capability declares the intent, and protocol intent
  matching is keyword-based rather than a full declarative
  router with priorities/conflict resolution.
- Target replacement: make capability protocol intent declarations the primary
  router, with explicit hint/priority/conflict fields and legacy fallback only
  for old manifests.
- Risk: P1. Bad routing can select the wrong workflow or require unnecessary
  permissions.
- Tests added/needed: toy capability intent routes without editing
  `os_kernel.py`; target keyword declarations can route a new capability intent;
  compliance target keywords beat unrelated investment keyword overlap; unknown
  intent returns `needs_capability`; evidence research routes from
  first-class protocols; document, data-analysis, and portfolio routes avoid
  generated legacy protocol; multi-intent protocols can declare per-intent
  dependencies; legacy `swarm.intents` compatibility remains covered for old
  manifests; built-in code, compliance, evidence, document, data, web, and
  value protocols declare intent keywords and requirements; web, evidence, compliance, and code routes avoid generated legacy
  protocol; weak cross-intent keyword matches do not override a specific
  fallback; explicit protocols without requirement types do not inherit static
  capability defaults; explicit targetless protocols are not runtime-ready;
  legacy heuristics are traced when used; investment routing regressions.

### 2. Goal Router Default Targets

- Evidence: `runtime/swarm/goal_router.py` reads capability protocol targets
  first and normalizes them before falling back to default targets only when no
  explicit capability protocol is present; the remaining legacy defaults now
  live in `runtime/swarm/legacy_goal_targets.py` and are consumed through
  `legacy_default_targets_for_intent()`. The previous swarm-research keyword
  special case has been removed, and the old public-web research target
  supplement is gone; missing targets in an explicit protocol now return
  `needs_capability` instead of inheriting central defaults.
  Target declarations can also carry `compatible_intents`, and GoalRouter
  filters protocol target pressure by the selected intent before considering
  any legacy defaults.
- Why not generic: target declarations remain centralized in a compatibility
  module for old manifests and include default target sets, but built-in public
  web-research, compliance, evidence-research, code-development, and
  value-investing paths now expose target declarations through explicit
  protocol.
  `agent_selection_policy` required/optional roles plus declared
  trust/maturity requirements now drive activation; the legacy
  intent-to-agent-type preferred map has been removed, and built-in evidence,
  code, compliance, toy, and value-investing capabilities declare role policies.
- Target replacement: move all default targets into typed capability protocol
  manifests; keep `LEGACY_DEFAULT_TARGETS_BY_INTENT` only as a traced
  `legacy_goal_router_fallback` with `legacy_default_targets_by_intent`.
- Risk: P1. Target pressure drives agent activation and later stop/quorum logic.
- Tests needed: protocol-declared targets win; explicit protocol without
  targets does not use legacy defaults; new toy target routes without
  central default; legacy fallback trace exists; unknown intent does not inherit
  random defaults; evidence, compliance, code, and web research avoid both
  legacy goal-router fallback and generated legacy protocol when their manifests
  are present; protocol agent-selection roles can activate new-domain agents
  without central agent-type edits; target aliases canonicalize before policy
  checks.

### 3. Capability Manifest Loading

- Evidence: `runtime/capability_registry.py` loads
  `capabilities/*/capability.json` at lines 125-149 and stores a raw `swarm`
  dictionary on `CapabilityManifest` at lines 71 and 99. Protocol extraction now
  runs through typed schema/loader/validation modules under `runtime/swarm/`,
  including diagnostics for malformed target aliases, candidate target
  references, quorum candidate/fallback references, recovery target/failure
  references, stop-signal trigger target references, unknown per-intent
  dependency and target-compatible intent references, untrusted hard-block
  authority, raw-data output privilege, and writer fact creation.
- Why not generic: `swarm` compatibility remains loosely typed for legacy
  manifests, and validation diagnostics are surfaced rather than enforced as
  install-time capability rejection.
- Target replacement: add typed `CapabilityPheroOSProtocol` models, validation,
  and loader modules. Existing `capability.json` remains accepted, with legacy
  compatibility protocol generation when a full protocol or explicit
  `swarm.intents` declaration is absent. Empty normalized `protocol: {}` fields
  no longer mask `swarm.intents`.
- Risk: P1. Untyped policy data can silently fail or be interpreted differently
  by separate runtime modules.
- Tests added/needed: schema validation, alias validation, candidate/quorum/
  recovery reference validation, trust restrictions for blocking authority,
  default `raw_data_allowed_in_final=false`, existing manifests still load.

### 4. Capability Entrypoints

- Evidence: capability entrypoints are declared in capability manifests such as
  `capabilities/value-investing-research/capability.json` lines 33-39,
  `capabilities/evidence-research/capability.json` lines 42-47,
  `capabilities/code-development/capability.json` lines 49-54, and
  `capabilities/compliance-workflow/capability.json` lines 42-47.
  `runtime/capability_runtime.py` loads a fixed set of descriptor entrypoints at
  lines 11-17 and 35-70. `runtime/workflows/loader.py` exposes workflow
  descriptors at lines 10-18. `runtime/swarm/control_loop.py` now provides a
  deterministic generic control-loop host over protocol targets, allocation,
  recovery, quorum, and outcome feedback. `runtime/workflows/generic_swarm_workflow.py`
  now lets descriptor-declared graph modes such as `toy_review` run through the
  generic host via `runtime/workflows/domain_execution.py` without adding a
  `graph.py` branch, and executes safe capability-owned `node_entrypoints`
  through the same path validation used for descriptor entrypoints. Workflow
  descriptors also support capability-owned `plan_entrypoints`; value-investing
  declares a `wrds_company_financials` plan adapter and public web-research
  declares a `public_web_search` adapter, giving capabilities first chance to
  insert/normalize required tool steps before the graph falls back to legacy
  compatibility planning. Code-development, compliance-workflow, and
  evidence-research now declare `orchestration_entrypoint` hooks so
  `runtime/workflows/domain_execution.py` can invoke capability-owned plan/trace
  builders before using graph-mode compatibility branches. When multiple
  workflow descriptors are present, routing now ranks descriptors by active
  selected skills instead of relying on metadata insertion order. Capability
  runtime now enriches workflow descriptors with sibling `data_contract`,
  `evidence_adapter`, `output_contract`, and `runtime_support` descriptors when
  present, and routing/generic workflow traces preserve those contract bundles.
- Why not fully generic yet: descriptors and a generic workflow host exist, but
  the main LangGraph topology still owns the physical node graph for specialized
  paths. Descriptor entrypoints including `runtime_support` and contract bundles
  are now surfaced, and plan entrypoints can mutate orchestration plans, but
  support modules are exposed as metadata rather than executed dynamically by the
  graph host.
- Target replacement: standardize `CapabilityWorkflow` and workflow loader
  contracts, and make `runtime/graph.py` delegate arbitrary domain nodes through
  those contracts and the generic control loop.
- Risk: P1. Entrypoints can look declared while runtime behavior still follows
  central branches.
- Tests added: missing workflow entrypoint returns capability diagnostics
  instead of crashing; toy workflow runs through the generic host without
  `graph.py` edits; generic node entrypoints execute and cannot escape the
  capability directory; data/evidence/output/runtime-support contracts load;
  existing value-investing descriptor stays compatible; value-investing and
  web-research plan adapters insert their required tool steps and record adapter
  trace metadata; workflow routing prefers the selected capability descriptor
  when plan-only and graph-owning descriptors coexist.

### 5. `runtime/graph.py` Hardcoded Workflow

- Evidence: `_build_graph()` hardcodes a fixed LangGraph topology at
  `runtime/graph.py` lines 356-389. The orchestrator prompt now keeps a generic
  JSON planning contract and consumes workflow descriptor
  `orchestration_guidance`, ToolPolicy-declared source-mode guidance, or traced legacy
  compatibility guidance from `runtime/workflows/orchestration_guidance.py` and
  `runtime/workflows/legacy_orchestration_guidance.py`; investment/WRDS prompt
  wording is declared by the value-investing workflow descriptor and ToolPolicy. Node methods delegate some
  value-investing runtime nodes through central method names. Those graph node
  methods now prefer the active workflow descriptor's `node_entrypoints` for
  routable nodes such as Data Gate, research, quant, committee, critic, writer,
  and final judge before using compatibility fallbacks; evidence-research and
  compliance-workflow now declare capability-local `research_agent`
  entrypoints. `normalize_orchestration()` now delegates legacy agent-flag
  defaults, company-name/ticker investment promotion, committee expansion, and
  direct-answer collapse to `runtime/workflows/legacy_orchestration_defaults.py`.
  `runtime/swarm/control_loop.py` can run a non-investment toy protocol through
  target pressure, recovery, quorum, and process-only feedback.
  `runtime/workflows/domain_execution.py` now prefers descriptor-declared
  `orchestration_entrypoint` hooks for code, compliance, and evidence workflow
  plan construction and descriptor-declared `execution_entrypoint` hooks for
  post-executor domain node interpretation. Thin workflow descriptors naming
  real capabilities now backfill missing entrypoints from manifest workflow
  descriptors before graph-mode fallback dispatch. Unknown descriptor-declared graph
  modes now defer orchestration-time generic workflow execution into the
  LangGraph `workflow_host` node, which runs
  `runtime/workflows/generic_swarm_workflow.py` and can execute declared
  synchronous or awaitable node entrypoints through the async graph runtime
  path. Domain workflow gate status now bridges into capability-declared
  StopSignalPolicy by emitting typed stop-signals for blocked writer/final-judge
  actions. Legacy code/compliance/evidence graph-mode fallback maps and built-in
  graph-mode exclusions are now isolated in
  `runtime/workflows/legacy_dispatch.py`; the shared domain execution bridge and
  graph workflow-host gate only delegate to that compatibility resolver. Legacy
  compliance/evidence research-node fallback dispatch is now isolated in
  `runtime/workflows/legacy_node_dispatch.py`. Graph node dispatch applies the
  same manifest backfill before legacy research-node fallback, and explicit
  protocol-backed workflows that declare
  static specialist graph nodes now must provide their `node_entrypoints`
  entries instead of inheriting value-investing, generic domain-expert, or
  legacy compliance/evidence fallbacks. Code and evidence workflow trace
  guardrails now describe declared gates/roles instead of
  hardcoded guardrail agent names. Graph orchestration
  now receives the OS plan and suppresses ticker/company-name investment
  defaults when a protocol-backed OS plan does not declare committee or
  source-policy pressure, so protocol routing can override graph heuristics.
  Legacy graph task-type aliases, task inference hints, direct-answer
  complexity markers, and quant/domain analysis hints are isolated in
  `runtime/workflows/legacy_graph_routing.py`; `runtime/graph.py` delegates to
  that compatibility boundary instead of owning those tables.
  Legacy deterministic fallback plan bodies are isolated in
  `runtime/workflows/legacy_plan_defaults.py`, and graph runs now mark
  `legacy_deterministic_plan_fallback` when that no-plan compatibility path
  fills in source-policy, public-web, code-inspection, or direct-answer steps.
  Source-tool helper tables and logic for search/fetch tool names, auto-fetch,
  provider-search upgrade, result URL selection, execution failure summaries,
  and review source-grounding checks are isolated in
  `runtime/workflows/source_tool_helpers.py`; graph keeps compatibility wrappers
  and executor dispatch.
	  Orchestrator guidance lineage is recorded as `orchestration_guidance_trace`,
	  and a toy protocol-backed workflow receives no legacy investment prompt
	  guidance when its descriptor does not declare it.
	  Normalized graph run results now expose generic `agent_outputs` and
	  `agent_decision` mirrors, and Critic/Writer/Final Judge contexts consume
	  those generic fields with explicit `legacy_agent_outputs` /
	  `legacy_agent_decision` lineage instead of bare committee-state prompt keys.
	  `/agents/run` now declares those generic fields in its response model before
	  the legacy committee compatibility fields, so public API serialization keeps
	  generic agent state.
		  Capability runtime nodes now emit generic agent state too: value-investing
		  passes `agent_outputs` into governance helpers and mirrors final decisions
		  into `agent_decision`, while direct WRDS returns empty `agent_outputs` plus
		  a skipped `agent_decision` for retrieval-only runs. Value-investing support
		  helpers now read state-derived member work through generic `agent_outputs`
		  before legacy committee-output compatibility state when building prompts,
		  discussion pressure, fallback decisions, and scorecards. Graph/capability
		  helper dispatch now prefers generic `parse_agent_decision`,
		  `fallback_agent_decision`, `agent_decision_to_domain_analysis`, and
		  `summarize_agent_outputs_for_model`; committee-named helper functions remain
		  compatibility wrappers.
		  The graph now hosts
  arbitrary non-specialized capability workflow
  nodes through `workflow_host`, but it still does not dynamically expand the
  physical LangGraph topology per descriptor.
- Why not fully generic yet: graph topology and several specialized route
  decisions are still central runtime truth for compatibility paths.
- Target replacement: keep graph as a generic host; load workflow node order,
  node implementations, data contract, evidence adapter, and output contract from
  capability workflow entrypoints.
- Risk: P0/P1 depending on path. Graph branching can bypass protocol authority or
  route the wrong domain.
- Tests added/needed: toy workflow runs through the generic host without graph.py
  edits, async orchestrator dispatch defers generic descriptor execution to the
  `workflow_host` graph node, graph node methods can dispatch through capability
  workflow `node_entrypoints`, async descriptor node entrypoints are awaited, and
  missing workflow entrypoints do not crash; built-in evidence/compliance
  research nodes dispatch through descriptor `node_entrypoints`, and explicit
  protocol-backed static specialist nodes without declared entrypoints are
  rejected before value-investing/generic/legacy graph-mode fallback;
  descriptor-declared orchestration and execution hooks own code/compliance/
  evidence plan and post-executor traces; graph legacy routing heuristic tables
  stay outside graph core; still need investment flow regression coverage after
  replacing more specialized branches.

### 6. Investment Workflow Hardcoding

- Evidence: central graph code defines investment search/tool constants at
  `runtime/graph.py` lines 116-119, investment routing hints at lines 103-157,
  investment/WRDS data requirements at lines 1791-1905, and WRDS-only source mode
  at lines 1947-1995. Value-investing capability does own several runtime nodes
  via `capabilities/value-investing-research/runtime_nodes.py`, and its manifest
  now includes an explicit first-class `protocol` section declaring investment
  intents, targets, candidates, quorum, stop-signal policy, recovery,
  agent-selection policy, EvidencePolicy, ToolPolicy, OutputPolicy, and loop
  policy. The old `swarm` section remains for compatibility consumers, but the
  protocol loader no longer generates a legacy protocol for this capability.
- Why not generic: investment behavior is now declared in capability protocol,
  and graph plan filtering now delegates to the generic
  `runtime/swarm/tool_plan_policy.py` source/tool-policy filter. Effective
  WRDS-only source-mode derivation now honors explicit metadata or capability
  ToolPolicy `source_mode` and no longer infers WRDS-only from investment
  task-type alone; the graph records the selected `source_mode_decision` in run
  metadata. Web-tool disable checks and WRDS-only public-web skill blocking also
  live in that shared module. WRDS company-tool step insertion and shorthand
  argument normalization live in
  `runtime/wrds_company_planner.py`, and the value-investing workflow now invokes
  that planner through a descriptor-declared `plan_entrypoints` adapter. Public
  web-research step insertion lives in `runtime/web_research_planner.py`, and the
  web-research capability invokes it through a descriptor-declared
  `plan_entrypoints` adapter. Data Gate contract construction now consumes the
  selected capability workflow descriptor's `data_contract` bundle for source
  mode, source-mode verification/allowed-source policy, source timing rules,
  source timing/reconciliation/identity validation payloads, including official
  metric mismatch and ambiguous company-identity policy, Data Gate required-when policy,
  confidence ceiling, forbidden claims, and
  required contract packages; missing descriptor forbidden-claim policy is now
  marked as `legacy_forbidden_claims` from `runtime/legacy_data_gate_policy.py`
  instead of inline runtime text; missing descriptor non-GAAP/estimate metric
  groups are now marked as `legacy_gate_metric_group` instead of runtime-owned
  defaults; metric-registry usage, source-priority, and warning
  baselines now come from descriptor-backed `metric_registry_policy.usage_rules`
  `metric_registry_policy.source_priority`, and
  `metric_registry_policy.warning_rules` before the
  `legacy_metric_registry_policy` / `legacy_metric_registry_warning_rule`
  fallback;
  the legacy fallback policy tables and report-claim detector regexes themselves
  are now isolated in `runtime/legacy_data_gate_policy.py`;
  acquisition-intensive profile policy also comes from that descriptor for
  severity, reason text, identity markers, asset-ratio thresholds, required
  evidence, and valuation policy wording, financial-company,
  negative/non-meaningful-earnings, and package-gap profile policy now come
  from the same descriptor before
  `legacy_profile_policy`, package-gap evidence rows use descriptor-declared
  gap severity/code/message/blocking flags, and emitted profiles mark
  `data_contract_profile_policy` before fallback; forward-estimate evidence
  gaps use descriptor-declared `gate_policy.evidence_gap_rules` before
  `legacy_gate_evidence_gap_rule`; acquisition-intensive profile evidence gaps
  use descriptor-declared `gate_policy.profile_evidence_rules` before
  `legacy_profile_evidence_rule`; acquisition-heavy missing-non-GAAP warnings
  use descriptor-declared `gate_policy.profile_warning_rules` before
  `legacy_profile_warning_rule`; Data Gate metric normalization now consumes descriptor-backed
  `metric_aliases` before the `legacy_metric_aliases` fallback, and completeness
  scoring consumes the descriptor's required-metric list; descriptor-backed
  `source_mode_limitations` now owns WRDS-only report limitation boxes and Data
  Gate limitation items before the `legacy_wrds_only_limitations` fallback; and
  descriptor-backed `confidence_policy` now owns maximum confidence and
  downgrade reasons plus validation issue payloads before the
  `legacy_wrds_only_confidence_guardrail` fallback;
  and
  the descriptor's `claim_guardrails` now owns WRDS-only required claim-defect
  fixes and claim-defect memo shells; and the
  descriptor's `gate_policy` now owns estimate metric groups, non-GAAP metric
  groups, acquisition-profile evidence
  satisfaction rules, required-data validation issues, formula validation issues,
  margin-basis validation issues, Compustat standard-filter validation issues,
  balance-sheet jump validation issues, source validation issues, metric requirement validation issues, required-period validation issues, metric-registry formula annotations, Data Gate score
  penalties/period bonuses with emitted score-source lineage, defect memo title,
  intro, headings, required fixes, registry-warning fixes, Data Readiness memo
  shells, and named output effects for blocking errors,
  publication blockers, formal-valuation blockers,
  formal-valuation validation issues, and pass-through. Metric registry construction is now selected
  through a descriptor-declared `metric_registry_entrypoint` adapter that can
  delegate to the shared deterministic builder and records
  `metric_registry_entrypoint_trace`; invalid-entrypoint fallback warnings cite
  `legacy_metric_registry_entrypoint_warning`. WRDS execution-result collection is now
  declared by the WRDS capability runtime descriptor as a `wrds_result` result
  collector, with graph runtime dispatching through that descriptor when active.
  WRDS company-tool argument normalization is likewise declared by the WRDS
  runtime descriptor and dispatched through active capability metadata when
	  available. Direct WRDS route/bypass decisions and direct-WRDS orchestration
	  are declared by the WRDS runtime descriptor's routing entrypoints, with
	  deterministic graph fallback behavior isolated in
	  `runtime/workflows/legacy_wrds_routing.py`. Value-investing and direct WRDS
	  capability runtime outputs now expose generic `agent_outputs` /
	  `agent_decision` fields directly, with old committee fields kept only as
	  compatibility mirrors.
- Target replacement: keep the WRDS compatibility fallbacks only for invalid or
  missing descriptors while preserving global source-policy safety.
- Risk: P0 for WRDS raw-data leak and web-search-in-WRDS-only paths; P1 for
  routing regressions.
- Tests added/needed: explicit investment protocol does not use legacy swarm
  generation; WRDS-only blocks web tools through protocol/global policy; data
  gate blocks formal valuation; raw WRDS rows never reach final; existing
  investment safety tests; descriptor-declared WRDS and public-web plan adapters
  insert required tool steps and record trace metadata.

### 7. Quorum Candidates

- Evidence: `runtime/swarm/quorum.py` now consumes
  `runtime/swarm/candidate_registry.py`. Candidate declarations load from
  `swarm_plan.candidate_policy` or `swarm_plan.quorum_policy`; there is no
  runtime Buy/Watch/Avoid/Sell fallback. Candidate blocking and fallback
  commitment use declared `blocked_by_targets`, `safe_fallback`, and quorum
  fallback policy; explicit protocols do not infer fallback authority from
  labels such as "Insufficient Data". Candidate scores now expose
  policy-weighted evidence
  coverage, source independence, source quality, unresolved risk, stop-signal
  inputs, explicit candidate-targeted support/oppose signals, source-agent
  reliability, and candidate-specific verified EvidenceGraph support edges.
  Investment formal/report/data blockers live in the value-investing protocol,
  not in quorum control flow.
- Why not fully generic yet: scoring now consumes declared policy weights,
  typed support signals, agent reliability, candidate-specific verified
  evidence-graph support edges, and source-quality weights, but still needs
  deeper multi-hop evidence lineage and source-quality provenance across
  adapters.
- Target replacement: extend candidate scoring with richer multi-hop evidence
  lineage and source-quality provenance from EvidenceGraph adapters.
- Risk: P0/P1. Quorum is final candidate authority; wrong fallback can produce
  investment semantics in other capabilities.
- Tests added: toy approve/reject/insufficient candidates; investment candidates
  from declared capability policy; blocking target forces declared fallback;
  missing fallback declaration leaves a blocked explicit-protocol candidate
  uncommitted instead of treating an "Insufficient" label as fallback authority;
  formal-valuation stop signals do not block undeclared toy candidates;
  undeclared Buy labels and non-investment states without candidates do not
  inherit investment defaults.

### 8. Evidence Recovery

- Evidence: `runtime/swarm/control_loop.py` composes target pressure,
  pressure-driven allocation, the deterministic execution loop, declared
  recovery protocols, generic quorum, and process-only outcome feedback.
  `runtime/swarm/target_pressure.py`, `runtime/swarm/agent_allocator.py`,
  `runtime/swarm/recruitment.py`, `runtime/swarm/execution_context.py`, and
  `runtime/swarm/outcome_feedback.py` provide the Phase 4 module surface.
  `runtime/swarm/outcome_feedback.py` and
  `runtime/swarm/outcome_memory.py` now describe excluded memory fields as
  generic no-domain-conclusion boundaries instead of investment/company-specific
  memory wording.
  `runtime/swarm/response_threshold.py` now derives agent response demand
  and mandatory retention from agent manifest terms, `swarm.initial_thresholds`,
  `can_block`, committed-candidate metadata, and generic `agent_review`
  fallback labels instead of static
  investment-agent name maps, and conclusion-review demand now follows generic
  Data Gate conclusion permission readiness instead of a formal-valuation-only
  flag. `runtime/swarm/arousal.py` likewise reports target-scoped allowed and
  blocked conclusion recommendations from generic Data Gate permissions, with
  the `allow_formal_conclusion` compatibility target delegated to
  `runtime/swarm/legacy_data_gate_permissions.py`, and
  `runtime/swarm/controllers.py` carries those targets into writer policy while
  applying controller throttling/retention through the same manifest metadata and declared `order`
  rather than a mandatory investment-agent set or special name-based sort
	  override. `runtime/agent_registry.py` now exposes shared committee-capable
	  manifest/catalog semantics, and
	  `capabilities/value-investing-research/support.py` uses those semantics while
	  ordering committee members only by manifest `order`, not a data-auditor name
	  special case; runtime materialization now exposes generic `agent_catalog`
	  metadata and value-investing support plus the swarm execution loop prefer it
	  before the legacy `committee_agent_catalog` mirror; fallback manifest loading now follows runtime
  `enabled_capabilities` / OS-plan `auto_enabled` metadata before the legacy
	  value-investing compatibility default. `runtime/os_kernel.py` now builds committee plans from
	  `runtime/agent_registry.py` committee-capable manifests instead of an
	  investment/portfolio intent whitelist; `committee_role` declares membership,
	  while legacy `investment_committee_member` agent types remain compatibility
	  input isolated in `runtime/legacy_agent_registry.py`. Agent-emitted signal
	  proposals now use generic `capability_agent` lineage, value-investing
		  evidence-adapter proposal sources declare `capability_agent`, and
		  `committee_agent` remains only a legacy self-assertion source supplied by
		  `runtime/legacy_agent_registry.py` and recognized by the authority
		  boundary. Authority level 3 is now named `TRUSTED_AGENT`
		  instead of `TRUSTED_COMMITTEE`, so the core authority vocabulary is generic
		  even when committee-capable manifest metadata contributes to scoring.
		  Independent Scout now forces the quorum trace or policy's declared
  fallback candidate when low source independence requires a safer commit, and
  Quorum Marshal reports `blocked_to_fallback` using the fallback candidate
  label from quorum data instead of a central Insufficient Data label check;
  fallback-ish labels remain compatibility fallback only for old traces without
  candidate registry metadata. `runtime/swarm/agent_decisions.py` now gives the
  control loop and quorum a generic `agent_decision` state helper, so recovery
  fallback decisions and quorum candidate selection prefer generic state while
  legacy `committee_decision` remains isolated compatibility input.
  `runtime/swarm/trust_badge.py` and
  `runtime/swarm/lane_scheduler.py` now infer allowed lanes and preferred lane
  assignment from identity metadata, `swarm.allowed_lanes`, trust level,
  `can_block`, and role terms instead of static core-agent lane maps.
  `runtime/swarm/authority.py` now keeps fixed authority only for core
  modules/global actors and derives capability-agent authority plus blocker
  request eligibility from agent manifests, including `swarm.trust_level`,
  `swarm.signal_emit_permissions`, `swarm.can_block`, `committee_role`, and
  committee-capable `agent_type` semantics rather than an investment-only member
  type. Blocking-capable committee agents can request blockers but remain
  proposal-level authorities unless a verifier/system module promotes the
  signal.
  Evidence-research also calls `runtime/swarm/recovery_engine.py` from its
  workflow recovery node, and `runtime/swarm/bottleneck_recruitment.py` selects
  recruits from available agent metadata and `agent_selection_policy`. If no
  agent registry/allocation payload is present but enabled capabilities are
  explicit, bottleneck recruitment loads the enabled capability's agent manifests;
  if no enabled capability metadata exists, it emits a missing-registry trace
  instead of inventing investment agent names. Evidence-research recovery no
  longer falls back to a hardcoded evidence-agent name list; when an OS
  allocation is absent, it loads the capability's declared recovery protocol
  plus agent manifests and reuses the generic recovery scorer. Recovery
  `agents_selected` events now carry full selected-agent rows, selection reasons,
  and selected-protocol lineage.
- Why not fully generic yet: RecoveryEngine selects agents by protocol roles,
  tags, tools, target affinity, allocation, trust requirements, and maturity
  requirements, and the generic control loop runs recovery before
  quorum/blocking. Declared `required_tools` can now execute through ToolRegistry
  when a registry is supplied, with success/failure folded into declared
  recovery conditions. Model-driven recovery rounds and richer workflow side
  effects are still deterministic/adapter-driven rather than fully delegated
  workflow execution.
- Target replacement: integrate `runtime/swarm/recovery_engine.py` into the
  graph/runtime workflow host so arbitrary capabilities execute recovery actions
  through declared workflow adapters and ToolRegistry calls.
- Risk: P1. Unresolved evidence gaps can either block too early or recover via
  missing or mismatched declared agents.
- Tests added: generic control loop recruits from target pressure, runs recovery
  before blocking, commits after recovery success, blocks after recovery failure,
  respects protocol max rounds, avoids investment agent names, stores only
  process outcome feedback, allocates and recovers agents by
  roles/tags/trust/maturity not names, executes declared recovery tools through
  ToolRegistry, preserves fallback on tool failure, resolves blockers only with
  authority, and emits recovery lineage.

### 9. Tool Policy

- Evidence: `runtime/tool_registry.py` remains the execution path. `runtime/graph.py`
  now calls `runtime/swarm/tool_policy_resolver.py` before explicit tool calls,
  search-provider fallback, and automatic source-fetch calls; blocked/denied
  decisions are recorded in structured tool results without invoking the
  registry. The resolver combines ToolRegistry manifest metadata, global
  permission/connection results, capability ToolPolicy, stop-signal policy, and
  social-immunity quarantine state. Graph plan filtering now delegates to
  `runtime/swarm/tool_plan_policy.py`, which derives effective WRDS-only source
  mode from explicit metadata, Data Gate source mode, or capability ToolPolicy,
  strips tool
  calls blocked by capability ToolPolicy, absent from a declared allowlist, or
  disallowed by WRDS-only source policy aliases such as `WRDS-FIRST`; it also
  partitions public web skills out of WRDS-only runs. Initial stop-signal seeding,
  worker-policing web-tool violation checks, patroller WRDS-source readiness, and
  web-tool stop-signal resolution now consume the same shared source-policy
  helper, including source-policy aliases, Data Gate source mode, capability
  ToolPolicy source mode, and explicit metadata source mode. Protocol Police's
  empty-target tool-policy fallback delegates the legacy web-search default to
  `runtime/swarm/legacy_tool_policy.py` instead of owning that tool name inline.
  The legacy `os_plan.wrds_only_mode` readiness flag is also read through that
  compatibility module. Source-tool names used by graph execution, web planning,
  and evidence-research helpers now come from
  `runtime/workflows/source_tool_helpers.py` constants instead of local string
  defaults.
  The old
  `investment_web_search_disabled` flag no longer drives source-policy blocking.
  Source-policy block messages and initial signals now describe the active
  source policy instead of hardcoding investment-analysis wording; Data Gate
  stop-signal seeding now enumerates blocked `conclusion_permissions` targets,
  Critic rejection stop-signals use the declared publication target, and those
  paths use generic governed-decision wording rather than downstream investment
  branches. Graph run outcome and post-writer routing now consume declared
  publication permissions directly and describe Data Gate publication blocks
  with generic publication wording. Data readiness memos, Data Gate failure
  signals, and Writer policy prompts now use generic publication/agent wording
  and expose declared publication targets instead of report/committee-specific
  wording. Homeostasis recommendations and signal text now come from
  `swarm_loop_policy.homeostasis_recommendations` and
  `swarm_loop_policy.homeostasis_signal_template` before legacy policy
  fallback, including legacy source-label delegation. Arousal Controller signal text
  now comes from `swarm_loop_policy.arousal_signal_template` before legacy
  policy fallback, including legacy template-source delegation. Social Immunity advisory text now comes from
  `swarm_loop_policy.social_immunity_recommendations` and
  `swarm_loop_policy.social_immunity_arousal_signal_template` before legacy
  policy fallback, including legacy source-label delegation, while quarantine
  detection remains a global safety rule.
  Tool Health Sentinel and Encounter Rate recommendations now come from
  `swarm_loop_policy.tool_health_recommendations` and
  `swarm_loop_policy.encounter_rate_recommendations` before legacy policy
  fallback, including legacy source-label delegation; the Tool Health signal fallback message is isolated in
  `runtime/swarm/legacy_tool_health_policy.py`. Lane Scheduler now consumes descriptor-backed
  `swarm_loop_policy.lane_policy` for lane preferences and assignment signal
  text before legacy lane-policy fallback, including legacy source-label
  delegation, while global lane safety still overrides capability policy for
  writer and third-party execution/control restrictions. Maturity Lifecycle now consumes descriptor-backed
  `swarm_loop_policy.maturity_policy` for lifecycle order, promotion/demotion
  thresholds, allowed actions, and signal text before legacy maturity-policy
  fallback, including legacy source-label delegation, while global maturity
  safety still caps untrusted/user-installed agents and controls blocker reach.
  Independent Scout source-family rules, low-independence/fallback wording, and
  signal text now come from `swarm_loop_policy.independent_scout_policy` before
  legacy scout-policy fallback, including legacy source-label delegation, with
  controller quorum-policy threshold/fallback overrides traced separately.
  Swarm Controller action wording, default action targets, homeostasis action
  rules, runtime-budget reasons, and quorum-policy signal text now come from
  `swarm_loop_policy.controller_action_policy` before legacy controller-policy
  fallback, including legacy source-label delegation; mandatory-member retention
  remains manifest-driven.
  WRDS planner investment default-package activation now delegates its
  task-type predicate to `runtime/legacy_wrds_planner_defaults.py` instead of
  owning the literal investment check in the core planner.
  Data Gate source-mode default policies now resolve through
  `runtime/legacy_data_gate_policy.py`, removing the inline WRDS allowed-source
  fallback from core contract building.
  Legacy formal-valuation stop-signal report wording now lives in
  `runtime/swarm/legacy_output_phrases.py`, with `stop_signal.py` only
  delegating the no-policy fallback body.
- Why not fully generic yet: execution, basic plan filtering, and tool trace
  rows are resolver/policy-aware; graph tool-call rows now carry normalized
  `tool.allowed`, `tool.allowed_with_quarantine`, `tool.blocked`, or
  `tool.denied` event types, and trace persistence stores the structured policy
  decision. WRDS company plus public web step insertion are now invoked by
  capability `plan_entrypoints` adapters, and capability ToolPolicy can declare
  source mode and source-policy-blocked tool targets; the legacy public-web tool
  fallback set is isolated in `runtime/swarm/legacy_tool_policy.py` and only
  used when ToolPolicy omits explicit blocked targets. The remaining legacy
  research/web/WRDS skill-name compatibility sets are isolated in
  `runtime/legacy_research_selection.py`, while `runtime/research_selection.py`
  delegates to them only after metadata and capability-type matching. Remaining
  work is making trace state the authoritative
  event-sourced record for broader governance transitions and richer policy
  lineage.
- Target replacement: event-sourced policy/governance trace authority while
  keeping ToolRegistry as the only execution path.
- Risk: P0 for direct high-risk execution or web_search under an active
  WRDS-only source policy.
- Tests added: permission policy overrides capability allow; stop-signal blocks
  tool aliases; quarantined output cannot feed EvidenceGraph/Writer; no direct
  tool execution outside registry; graph executor blocks undeclared tools before
  registry execution; automatic source fetches are resolver-gated; plan/skill
  filters apply source-policy aliases plus capability allow/block rules outside
  graph; source-policy blocked tool targets can be capability-declared for
  filtering, initial signals, policing, tool manifests, and resolution;
  WRDS-only source-policy signals and executor errors are capability-agnostic.

### 10. Stop-Signal Policy

- Evidence: `runtime/swarm/stop_policy.py` reads `swarm_plan.stop_signal_policy`
  and maps declared rules. `runtime/swarm/stop_signal_policy.py` now resolves
  action blocking through capability-declared policy, active stop-signals, and
  `runtime/swarm/action_policy.py` source-policy blocks. Source-policy action
  blocking reads explicit source mode metadata or capability ToolPolicy and no
  longer infers WRDS-only from investment task type. `runtime/swarm/resolution.py`
  supports declared resolution rules and authorities for custom targets, while
  preserving global deterministic Data Gate/web source resolutions.
  StopSignalPolicy now supports `action_markers`, allowing capabilities to map
  domain-specific output phrases to writer/final-judge actions without central
  phrase tables. Capability-agent stop-signal authority is now derived from
  agent manifests instead of static agent-name authority/blocker maps, while
  fixed core module/global actor authority remains as a global safety rule.
  Validation diagnostics for untrusted hard-blocking authority are enforced by
  the shared stop-policy accessor, which source-filters unsafe rules, action
  markers, and resolution rules before downstream runtime consumers use them.
  Top-level `blocked_actions` are normalized into source-attributed default
  rules before merge, so mixed policies can drop unsafe top-level blockers while
  preserving trusted declarations.
  Direct formal-valuation report enforcement now also reads declared
  `action_markers` before using the legacy no-policy recommendation regex.
- Why not fully generic yet: some signal inference, output wording, and legacy
  formal-recommendation fallback text remain central for no-protocol paths.
- Target replacement: typed StopSignalPolicy action effects, richer target
  aliases, resolution lineage, and generic writer/final-judge effects. Keep
  global safety non-weaken rules.
- Risk: P0/P1. Stop-signals are a hard blocking authority.
- Tests added: capability-declared stop-signal blocks a new tool/action; global
  source policy cannot be weakened; resolution requires declared authority;
  resolved blocker reopens candidate; untrusted hard-blocking policy is
  diagnosed but not enforced; trusted hard-blocking policy still blocks;
  mixed-policy unsafe top-level blockers are filtered; writer action markers are
  inferred from StopSignalPolicy.

### 11. Writer And Final Judge Guardrails

- Evidence: `runtime/writer_guardrails.py` has generic sequencing and policy
  action checks, and now consumes `runtime/output_contract.py` for
  capability-declared blocked phrases, required caveats, allowed output modes,
  final-judge candidate checks, raw-data policy, citation requirements, and
  evidence-contract violations carried on `swarm_plan.output_policy` and
  `swarm_plan.evidence_policy`. OutputPolicy now also declares
  `committed_candidate_conflicts`, so value-investing's Insufficient Data vs.
  Buy/Sell/target-price conflict is capability data rather than a writer
  hardcode. Raw-sensitive data absence is now enforced by the shared output
  contract as a non-weakenable final-output rule; EvidencePolicy can declare
  `raw_data_markers` for capability-specific raw/sensitive output blocking, but
  `raw_data_allowed_in_final=true` no longer disables final marker detection.
  Writer fact creation is likewise non-weakenable:
  `output_policy.writer_can_create_facts=true` is preserved only as audit
  metadata, while the effective writer evidence contract keeps writer fact
  creation disabled.
  Value-investing now declares WRDS/Compustat raw markers in protocol data, and
  Protocol Police reports
  `capability_evidence_policy` versus `legacy_raw_data_marker_fallback` lineage
  for raw-data leak violations; the old no-policy WRDS/Compustat marker list
  and fallback source label are isolated in `runtime/legacy_output_contract.py`.
  OutputPolicy `defect_memo_on_block` now uses capability-declared
  StopSignalPolicy actions such as `writer:publish_report` and
  `final_judge:publish_report`, so publish-blocked outputs must be defect memos
  through the shared contract. Capability OutputPolicy can also declare
  `defect_memo_markers`, which are merged with global defect-report fallback
  markers for backward compatibility.
  Domain workflow gate failures can now reach Writer through protocol-declared
  stop-signal actions; writer guardrails can synthesize those generic
  stop-signal checks from `domain_workflow.gate_status` when a capability
  declares writer-blocking actions. Writer and Final Judge action inference now
  reads StopSignalPolicy `action_markers`, so capabilities can declare the
  phrases that map to blocked actor actions; code-development,
  compliance-workflow, and evidence-research now declare those markers in their
  protocols, and value-investing declares final-judge investment recommendation
  markers alongside writer formal-valuation markers. Central phrase cues only
  run as legacy fallback when the active stop-signal policy does not declare
  action markers. Generic publication blocker detection now treats any declared
  publish/publication decision target as a publication blocker before Writer or
  Final Judge routing continues, and Writer-node blocker metrics now use
  generic publication failure reasons instead of legacy report-publication
  lineage codes. The legacy formal-recommendation regex and formal-valuation
  phrase lists are isolated in `runtime/swarm/legacy_output_phrases.py` as
  fallback for no-protocol investment compatibility; the legacy
  formal-valuation writer action emitted by that fallback is isolated there as
  well. Writer guardrails now apply generic stop-action policy before
  the legacy swarm report policy, and the direct swarm report policy can block
  arbitrary declared `writer:<target>` markers through StopSignalPolicy rules.
  Direct code-development and evidence-research workflow result helpers now use
  the shared domain-gate stop-signal bridge when they create blocked gate
  status, and the remaining no-policy code/compliance/evidence fallback bodies
  are isolated in `runtime/workflows/legacy_guardrails.py` rather than owned by
  central Writer or Protocol Police modules.
  The old graph-mode-specific writer checks remain only as compatibility
  fallback when no declared writer stop policy is present. Writer and Final
  Judge prompts now use a generic base plus capability policy summaries instead
  of central investment/WRDS prompt instructions, and the shared
  `runtime/nodes/output_chain.py` fallback wording now uses governed-output
  language instead of investment committee/recommendation phrasing. Worker
  policing and Evidence Contract now read OutputPolicy
  `committed_candidate_conflicts` before using helper-delegated legacy conflict
  wording from `runtime/swarm/legacy_output_phrases.py`, and that no-policy
  compatibility fallback now keys off declared fallback candidate identity;
  fallback-ish Insufficient Data/Evidence labels carry fallback authority only
  in legacy quorum traces without candidate-registry metadata.
  Artifact Cues and Evidence Steward now match blocked Data Gate conclusion
  permissions to StopSignalPolicy `writer:<target>` action markers before the
  legacy formal-valuation regex fallback, with the legacy formal-valuation
  target itself delegated through `runtime/swarm/legacy_data_gate_permissions.py`.
  Data Gate evaluation still emits legacy top-level formal/publication
  permission fields for old consumers, but those field names now come from the
  same compatibility module.
  Evidence Steward/Governance Results now emit generic writer constraints for
  blocked claims and declared output permissions, including target-scoped
  allowed/blocked permission inventories, instead of investment-specific boundary wording. Evidence
  Steward emits the legacy `formal_valuation_allowed` writer field only when
  that Data Gate permission exists, obtains that field name from
  `runtime/swarm/legacy_data_gate_permissions.py`, and marks it as a legacy
  conclusion field.
  The old formal-valuation-blocked Data Gate output-effect key is isolated in
  `runtime/legacy_data_gate_policy.py`; Data Gate still uses it as a
  compatibility lookup when a descriptor does not provide a more generic
  output effect.
  Evidence
  Graph output-permission nodes now enumerate declared Data Gate
  `conclusion_permissions` instead of only the formal-valuation/report-publication
  pair, and no longer invent that pair when no conclusion permissions are
  declared. Final decision claims now use committed-candidate target permissions
  before legacy blocked-conclusion fallback, and protocol-backed Data Gates no
  longer silently inherit the legacy report-publication default when no
  conclusion permission is declared. Auxiliary decision evidence now uses
  declared publish/publication conclusion permissions before the compatibility
  report-publication target in `runtime/swarm/legacy_data_gate_permissions.py`.
  Generic publication target classification now relies on publish/publication
  naming patterns instead of carrying the legacy report-publication tail inline.
  Shared Evidence Graph and Signal Verifier surfaces now describe unverified
  signals as agent proposals instead of committee-specific proposals. Permission
  edges now link gate blockers to arbitrary blocked output permissions rather
  than special-casing formal/report targets. Evidence Graph writer contracts now derive forbidden
  phrases from blocked conclusion targets plus StopSignalPolicy `action_markers`
  and OutputPolicy `committed_candidate_conflicts` before falling back to legacy
  no-policy formal-valuation wording; their remaining no-policy committed-candidate
  mismatch reports now use the committed fallback candidate label. Evidence
  Graph decision claims now read generic `agent_decision`, record
  `decision_source`, and prefer explicit decision provenance or
  capability/workflow metadata from `domain_workflow` and
  `metadata.os_plan.swarm_plan`, keeping the legacy investment committee source
  only as an explicitly marked `legacy:investment_committee` no-protocol
  compatibility trace. Protocol Police stop-signals and Governance Results now
  preserve explicit decision targets on writer/raw-data violations before using
  declared publish/publication Data Gate permissions, with the legacy
  report-publication target retained only as compatibility fallback. Legacy
  writer action tails that imply report publication are isolated in
  `runtime/swarm/legacy_data_gate_permissions.py`, so worker policing delegates
  that no-protocol aliasing instead of owning the old publish/report spellings.
  The
  governance contract catalog now uses
  generic blocked-output/tool-policy enforcement surfaces instead of
  formal-valuation/report-publication/web-search defaults, while runtime
  violations provide precise target-scoped trace events.
  `runtime/final_judge_guardrails.py` now applies the shared output contract as
  `final_judge` before delegating to writer guardrails.
  Output-contract candidate consistency now reads quorum candidates or
  capability-declared candidate policy and no longer invents fallback labels, so
  Buy/Watch/Avoid/Sell labels are investment capability data rather than generic
  defaults.
- Why not fully generic yet: OutputPolicy and EvidencePolicy are first-class
  guardrail inputs, but several domain-specific phrase checks and no-protocol
  workflow compatibility checks remain central.
- Target replacement: expand `runtime/output_contract.py` into the generic
  OutputPolicy/EvidencePolicy consumer. Keep global redaction/raw-sensitive-data
  rules as non-weakenable safety defaults.
- Risk: P0 for WRDS raw data/secret leakage and unsupported final claims; P1 for
  non-investment output semantics.
- Tests added: writer cannot create unsupported claim; final judge rejects
  candidate mismatch; toy capability blocks custom phrase; investment formal
  valuation block still works; evidence policy blocks raw output, declared
  raw-data markers, missing required evidence, and missing citations.

### 12. Trace And Decision Debugger

- Evidence: `runtime/swarm/trace_store.py` persists run metadata, events,
  signals, quorum, evidence graph, agent allocation, tools, and permissions. It
  exposes timeline, why_blocked, why_committed, evidence_graph,
  agent_allocation, why_agent, tool_events, permission_events, snapshot,
  recovery_lineage, and capability_protocol. Decision Debugger responses now
  surface OS routing trace lineage, including legacy intent/static capability
  fallback decisions, alongside swarm routing trace and protocol bundles, and
  those OS routing decisions are persisted as normalized timeline events.
  Explicit runtime events from `swarm_protocol_trace` and
  `swarm_control_loop.events` are now persisted before derived governance
  fallback events, and the fallback detector uses the same explicit event
  collector so runtime-emitted target-pressure, candidate, claim,
  outcome-feedback, signal, recovery, and agent-allocation events remain the
  authoritative timeline records when present.
  Timeline reads now also suppress matching compatibility `pheromone_signals`
  rows when normalized `signal.*` events exist for the same signal, preventing
  stale side-table signal state from appearing beside the authoritative event.
  Agent allocation, why-agent, tool-events, and permission-events debugger
  readers now prefer normalized `swarm_events` records over compatibility side
  tables when `agent.*`, `tool.*`, or `permission.*` events exist.
  `why_blocked` likewise prefers target-scoped blocking `signal.*` events before
  falling back to persisted pheromone signal rows, so explicit event traces can
  explain a block without a separate signal snapshot.
  `evidence_graph` now merges normalized `claim.*`, `artifact.quarantined`, and
  blocking `signal.*` event nodes with compatibility evidence-table rows, using
  event records as the authoritative node state while retaining table-backed
  edges and detail-only nodes.
  Pheromone snapshot reconstruction now also prefers normalized `signal.*`
  events for the signal list itself and uses persisted `pheromone_signals` rows
  only as a compatibility fallback.
  Governance Results trace events now point at runtime blocked targets when
  present, while preserving static contract enforcement targets in payload
  lineage.
  When legacy Evidence Graph tables are empty, the evidence-graph endpoint now
  reconstructs minimal claim, artifact, and blocking-signal nodes from
  normalized governance events.
  Capability protocol bundles can now be reconstructed from normalized
  `capability.protocol.loaded` events when the stored run payload lacks a full
  `swarm_plan`, including target signals, top-level recovery protocols,
  nested capability protocols, and top-level candidate, quorum, stop-signal,
  evidence, tool, output, agent-selection, and swarm-loop policies. Lineage
  endpoints share that event-sourced protocol bundle.
  `runtime/swarm/events.py` now derives first-class governance events from
  completed run payloads for `input.received`, `os.plan.created`,
  `runtime.materialized`, `capability.protocol.loaded`,
  signal lifecycle transitions, `target.pressure.updated`,
  `candidate.created`, `candidate.committed`, `candidate.blocked`,
  `agent.allocated`/`agent.suppressed`, tool policy decisions, permission
  decisions, recovery traces when explicit recovery timeline events are not
  already present, `artifact.quarantined` from input preflight and Social
  Immunity reports, `claim.created`/`claim.verified`/`claim.blocked` from
  Receiver Normalizer and Evidence Steward reports,
  `writer.blocked`/`final_judge.rejected`/`output.published` from generic
  output lifecycle state, and
  `outcome_feedback.updated` from process-only feedback.
  Governance snapshots also include reconstructed target-pressure updates,
  blocked candidates, quarantined artifacts, claim lifecycle summaries, and
  output lifecycle summaries, core lifecycle summaries, registered candidates,
  and outcome-feedback updates. `why_blocked` now includes
  target-scoped protocol lineage with matching target signals, capability
  protocol declarations, stop-signal rules, and recovery protocols.
  `why_committed` now prefers the event-sourced `candidate.committed` record and
  falls back to the legacy quorum table only when that event is absent; it also
  returns committed-candidate protocol lineage with matching candidate policy,
  quorum fallback policy, fallback identity, and capability protocol
  declarations.
  `recovery_lineage` now also returns target-scoped protocol lineage, so the
  selected recovery protocol and recovery events can be traced back to the
  capability recovery rule for the blocked target.
  Recovery traces now also include selected-protocol `capability_id`, source,
  and `protocol_source` directly on the selected protocol and recovery
  protocol/outcome events, with compatibility inference from the matching
  capability protocol bundle. Recovery recruitment reports carry the same
  capability/source lineage into the recruited agent rows, and
  `recovery.agents_selected` events carry selected-agent reason rows directly.
  When no separate recovery trace payload is stored, `recovery_lineage` derives
  recovery status, target pressure, selected protocol, selected agents, and
  fallback candidate from normalized `recovery.*` events and preserves direct
  event-carried selected-protocol capability lineage.
  Detailed normalized `recovery.*` events now also win over stored recovery
  trace payloads when they carry selected-protocol, selected-agent,
  target-pressure, or embedded recovery-trace details; stored recovery traces
  remain compatibility detail fallback for sparse legacy timelines.
  `why_agent` now returns agent protocol lineage with matching target signals,
  top-level agent-selection policy, and capability-declared target/agent
  selection policy.
  `runtime/swarm/snapshot_builder.py` builds an event-derived
  `governance_snapshot` from normalized timeline records and the existing
  pheromone snapshot endpoint now includes that governance summary plus an
  event-first reconstructed signal list.
	  Run audit records now expose agent-output summaries under generic
	  `agent_outputs`, record `agent_output_source`, and keep old
	  `committee_outputs` payloads only as `legacy_agent_outputs` compatibility
	  lineage through the shared artifact helper. They also expose decision
	  summaries under generic `agent_decision`, record `agent_decision_source`,
	  and keep old `committee_decision` payloads only as
	  `legacy_agent_decision` compatibility lineage. Data Gate audit summaries
	  preserve the legacy publication-allowed field name through
	  `runtime/swarm/legacy_data_gate_permissions.py` instead of spelling that
	  compatibility field inside audit logging.
  API routes expose aggregate `/runs/{run_id}/trace` in `app/routes/runs.py`
  lines 16-61 and platform Decision Debugger routes for timeline,
  why-blocked, why-committed, why-agent, evidence-graph, recovery-lineage, and
  capability-protocol in `app/routes/platform.py`.
- Why not fully generic yet: the planned Decision Debugger endpoint surface is
  present and protocol-aware, explicit protocol/control-loop events are
  persisted first, and several core governance decisions are now normalized into
  the timeline, but trace events are not yet the authoritative source for every
  governance transition.
- Target replacement: complete the event-sourced trace authority so every
  governance transition is emitted through one normalized event source.
- Risk: P1. Without lineage, governance decisions can become opaque or
  unverifiable.
- Tests added: event log reconstructs snapshot; explicit runtime events persist
  before derived fallbacks; event-first agent/tool/permission readers;
  event-first why-blocked signal lineage; why-blocked returns signal and
  capability protocol lineage; why-agent returns target pressure and policy;
  recovery lineage explains success/failure and derives event-only recovery
  traces; event-sourced protocol bundles restore top-level protocol surfaces
  without stored `swarm_plan`; event-derived evidence graph nodes; capability
  protocol bundle is returned; trace redacts secrets before persisting.

### 13. Toy Generic Capability

- Evidence: `capabilities/toy-review/` now includes a first-party reviewed
  protocol manifest, workflow descriptor, and `toy_scout_agent`,
  `toy_evidence_agent`, and `toy_reviewer_agent`. It declares `toy_review`
  intent, `gate:toy_evidence_gate` and `decision:toy_publish` targets,
  approve/reject/insufficient-evidence candidates, recovery, quorum,
  stop-signal, evidence, output, and agent-selection policies. Toy workflow
  tests now exercise OS planning, direct generic workflow host execution, and
  the async `AgentRuntime._orchestrator` path that defers generic descriptor
  execution into the LangGraph `workflow_host` node without adding a
  `toy_review` branch to `graph.py`.
- Why not fully generic yet: the toy proof exercises the async orchestrator,
  `workflow_host`, and generic PheroOS runtime components, but specialized
  built-in graph paths still retain compatibility wrappers.
- Target replacement: continue reducing specialized compatibility wrappers while
  keeping arbitrary capability workflow descriptors hosted without
  mode-specific branches.
- Risk: P1. Without a non-investment proof fixture, regressions can silently
  reintroduce investment-only behavior.
- Tests added: built-in toy capability declarations, OS planning without
  `graph.py` edits, async orchestrator generic workflow execution, generic
  recovery, generic quorum, workflow descriptor load, and generic output policy.

### 14. Existing Test Coverage

- Data Gate: `tests/test_data_gate.py` covers critical failures,
  WRDS-only claim policy, publication blocking, evidence gaps, conclusion
  permissions, descriptor-provided completeness requirements, profile policy,
  score policy source lineage, and output effects.
- Stop-Signal / governance: `tests/test_swarm_governance.py`,
  `tests/test_domain_workflow_guardrails.py`, and selected `tests/test_graph.py`
  cases cover active blockers, writer guardrails, and investment web-search
  blocking.
- Quorum: `tests/test_graph.py` and `tests/test_swarm_governance.py` cover
  Insufficient Data override and independent-scout adjustments; dedicated
  protocol-declared candidate coverage is still missing.
- Evidence Graph: `tests/test_evidence_contract.py`,
  `tests/test_swarm_trace_store.py`, and `tests/test_swarm_governance.py` cover
  writer contracts, graph persistence, and claim blocking.
- ToolRegistry: `tests/test_extensibility.py`, `tests/test_safe_tools.py`,
  `tests/test_web_tools.py`, `tests/test_model_gateway.py`, and
  `tests/test_graph.py` cover registry permissions, URL safety, provider search,
  and WRDS-only tool blocking.
- ModelGateway: `tests/test_architecture_boundaries.py`,
  `tests/test_model_gateway.py`, and `tests/test_redaction.py` cover gateway-only
  imports, provider search, fallback, and sanitized errors.
- Secret redaction: `tests/test_input_envelope.py`, `tests/test_audit_log.py`,
  `tests/test_api.py`, `tests/test_connection_control.py`,
  `tests/test_platform_config.py`, and `tests/test_secret_store.py` cover prompt,
  trace/API/audit, connection, and storage redaction.
- Protocol manifest coverage: tests exercise typed schema loading, adjacent
  `pheroos_protocol.json`, explicit value-investing protocol loading without
  legacy generation, loose legacy `swarm` compatibility bundles, and
  execution-loop protocol metadata.

## Migration Table

| Static rule location | Why it is not generic | Target replacement | Risk | Tests needed |
| --- | --- | --- | --- | --- |
| `runtime/os_kernel.py`, `runtime/legacy_os_intents.py` intent hints and `required_capability_types()` | Protocol intents, protocol `intent_keywords`, and compatible target keywords work, including first-class web/evidence/compliance/code/document/data/portfolio protocol declarations, built-in code/compliance/evidence/document/data/web/value protocol intent vocabularies and requirements, legacy `swarm.intents` compatibility declarations, and weak cross-intent keyword gating; OS intent matching now filters target keywords through `targets[].compatible_intents` so multi-intent protocols do not bleed one intent's target markers into another; selected protocol-backed intents now use the selected capability's declaring types plus global or per-intent `required_capability_types` before static fallback, explicit selected protocols with missing requirement types return `needs_capability` instead of borrowing static capability defaults, explicit targetless protocols keep OS runtime readiness false, and OS plans trace whether legacy intent/capability fallback was used; legacy OS keyword vocabularies and static intent-to-requirement maps are isolated in `runtime/legacy_os_intents.py`, while `runtime/os_kernel.py` delegates to them only as a compatibility boundary for old/non-protocol intents | Capability-declared intent hints/priority/conflict policy, with legacy fallback kept only for old manifests | P1 | Toy intent, target-keyword intent, intent keywords, built-in intent vocabularies, compatible-intent keyword filter, compliance overlap, built-in explicit protocols, document/data/portfolio protocol routes, legacy `swarm.intents` compatibility, protocol dependency, per-intent protocol dependency, weak keyword guard, malformed protocol requirement gap, explicit targetless readiness, legacy routing trace, OS legacy boundary guard, unknown intent, investment regression |
| `runtime/skill_loader.py`, `runtime/legacy_skill_matching.py` legacy skill inference | `SkillLoader` still supports old inferred skill names for no-protocol compatibility, but the built-in web/value/WRDS/document/data hint tables now live in `runtime/legacy_skill_matching.py`; `runtime/skill_loader.py` lists, loads, scores, and explicit-selects `SKILL.md` files while delegating legacy inferred names, and legacy OS intent fallback imports those helpers from the same compatibility module | Capability protocol `intent_keywords` and explicit skill selection first, with legacy inferred skill names isolated as compatibility | P1 | Skill loader inference regressions, legacy skill matching boundary guard, OS legacy fallback import guard |
| `runtime/swarm/goal_router.py`, `runtime/swarm/legacy_goal_targets.py` default targets and agent allocation | Several built-ins now declare targets in first-class protocol, compatible-intent target filtering lets multi-intent protocols expose intent-specific target sets, built-in reviewed capabilities declare agent-selection roles, the central intent-to-agent-type preferred map is gone, the swarm-research/public-web supplement branches are gone, explicit protocols with no targets now return `needs_capability` instead of defaulting to central target maps, and the remaining legacy investment fallback no longer emits investment candidate targets; old-manifest default target maps are isolated in `runtime/swarm/legacy_goal_targets.py`, are not imported/exported as a router surface, and remain explicitly legacy central fallbacks traced with `legacy_default_targets_by_intent` | Protocol-declared TargetDeclaration and AgentSelectionPolicy, legacy target fallback traced | P1 | Declared targets, compatible-intent filtering, explicit targetless protocol, protocol role allocation, alias canonicalization, fallback trace, built-in no-fallback routes, no fallback candidate targets, no intent type map, legacy target boundary guard |
| Raw `CapabilityManifest.swarm` plus `runtime/swarm/protocol.py`, `runtime/swarm/protocol_loader.py`, `runtime/swarm/protocol_schema.py`, `runtime/swarm/legacy_protocol_intents.py`, and `runtime/swarm/legacy_protocol_fields.py` | Typed schema/loader/validation exists and `swarm.intents` can be promoted to explicit protocol data; generated legacy protocol intent inference now uses the explicitly named `LEGACY_CAPABILITY_TYPE_INTENTS` compatibility map isolated in `runtime/swarm/legacy_protocol_intents.py`, with `runtime/swarm/protocol_loader.py` importing only the helper, and explicit `protocol`/`pheroos_protocol` declarations bypass that map; the old value-investing quorum field `force_insufficient_data_when_formal_valuation_blocked` and generated-legacy "insufficient label means safe fallback" behavior are isolated in `runtime/swarm/legacy_protocol_fields.py`, while explicit protocol candidates must declare `safe_fallback` or a quorum fallback; validation covers target aliases, intent-scoped dependency/target references, candidate/quorum/recovery/stop-signal references, trust-gated hard-block authority, raw-data output privilege, and writer fact creation, but loose dict compatibility remains | Install-time typed protocol validation plus traced legacy compatibility rejection/acceptance policy | P1 | Schema validation, reference diagnostics, compatible-intent diagnostics, compatibility load, `swarm.intents` explicit load, legacy capability-type intent map scope, protocol-loader legacy-intent boundary guard, protocol-schema legacy field boundary guard, legacy candidate fallback-label boundary |
| `runtime/swarm/control_loop.py`, `runtime/swarm/controllers.py`, `runtime/swarm/independent_scout.py`, `runtime/swarm/quorum.py`, `runtime/swarm/quorum_marshal.py`, `runtime/swarm/response_threshold.py`, `runtime/swarm/legacy_response_thresholds.py`, `runtime/swarm/legacy_outcome_feedback.py`, `runtime/os_kernel.py`, `runtime/agent_registry.py`, `runtime/legacy_agent_registry.py`, `runtime/legacy_value_investing_support.py`, `capabilities/value-investing-research/support.py`, and related Phase 4/6 modules | Generic deterministic loop exists and descriptor fallback uses it; target-pressure allocation honors declared trust/maturity requirements, response thresholds and controller retention now derive demand/mandatory behavior from agent manifest metadata instead of investment-agent name maps, manifest-declared `swarm.response_demand_profiles`/`demand_profiles` can provide task-type demand and reason text before legacy role-key fallbacks, undeclared response-threshold/profile feedback falls back to generic `agent_review` labels, legacy response-threshold role-term and known task-type demand fallbacks are isolated in `runtime/swarm/legacy_response_thresholds.py`, OS committee planning now uses agent manifest committee capability instead of an investment/portfolio intent whitelist, legacy committee agent-type vocabulary is isolated in `runtime/legacy_agent_registry.py` while `committee_role` remains the primary membership declaration, legacy unknown-committee-member warning text is isolated in `runtime/legacy_os_intents.py`, runtime metadata now exposes generic `agent_catalog` before legacy `committee_agent_catalog`, and the legacy catalog metadata key construction/read fallback plus old selected-agent metadata keys are isolated in `runtime/legacy_agent_registry.py`; controller and investment-support ordering use declared `order`, Arousal Controller and Swarm Controller writer policy carry generic allowed/blocked conclusion targets instead of relying only on the formal-valuation compatibility flag, fallback committee manifest loading follows runtime enabled-capability metadata before the legacy value-investing default isolated in `runtime/legacy_value_investing_support.py`, low-independence fallback commits and quorum-marshal stop-signal explanations use declared fallback candidate data and generic blocked conclusion targets instead of literal investment labels, trust badges and lane assignment infer lanes from manifest identity/swarm metadata instead of static core-agent maps, Homeostasis token pressure, Receiver Normalizer claim extraction, bottleneck missing-data accounting, Independent Scout source-diversity scoring, Quorum source/risk scoring, quorum candidate selection, recovery fallback decisions, graph normalization/model contexts, value-investing support prompts/pressure/fallbacks, and Outcome Memory / Outcome Feedback process learning consume generic `agent_outputs`/`agent_decision` through legacy compatibility helpers, with old excluded decision field names isolated in `runtime/swarm/legacy_outcome_feedback.py`, and descriptor-native generic recovery now executes declared recovery tools through the graph runtime's ToolRegistry across workflow-host and domain execution bridge paths; direct non-runtime recovery calls remain registry-optional | Integrate control loop with capability workflow execution and richer recovery actions | P1 | Target pressure allocation, manifest response thresholds, manifest response demand profiles, generic agent catalog, manifest controller retention/order, generic conclusion recommendation targets, generic support helper output reads, legacy committee-agent type boundary, legacy response-threshold boundary, graph generic agent-state guard, legacy outcome-feedback boundary, capability-local manifest order/enabled-capability fallback, manifest lane/trust metadata, declared fallback candidate, trust/maturity allocation, recovery-before-blocking, max rounds, process-only feedback, recovery tool execution |
| `runtime/swarm/authority.py`, `runtime/swarm/signal_extractor.py`, `runtime/swarm/signal_verifier.py`, `runtime/swarm/resolution.py`, `runtime/swarm/social_immunity.py`, `runtime/swarm/data_gate_permissions.py`, and `runtime/swarm/legacy_data_gate_permissions.py` | Core module/global actor authority remains fixed for global safety, but capability-agent authority and blocker request eligibility now come from agent manifests (`trust_level`, `signal_emit_permissions`, `can_block`, `committee_role`, and committee-capable `agent_type`) instead of static agent-name maps or investment-only member branches; agent-only or committee/execution-loop self-asserted signals are now explicitly barred from creating verified facts or hard blockers, so EvidenceGraph keeps them as proposals until a verifier/system module promotes them; initial Data Gate stop-signal seeding, Social Immunity arousal, verifier promotion, and stop-signal resolution now read generic Data Gate `conclusion_permissions` for the target instead of hardcoding only formal-valuation/report-publication targets, Social Immunity scans generic `agent_outputs` artifacts while legacy output compatibility payloads are isolated behind `runtime/swarm/agent_outputs.py`, Data Gate blocker resolution and Critic rejection stop-signals use declared publish/publication permissions before the legacy report-publication target, legacy top-level formal/report Data Gate fields are isolated in `runtime/swarm/legacy_data_gate_permissions.py`, declared StopSignalPolicy `resolution_policy` rules win over legacy auto-clear paths for matching targets, and critic rejection remains a global publication blocker | Manifest-declared agent request authority plus immutable global safety authority and verifier-only fact/blocker creation | P0/P1 | Manifest-derived blocker request authority, generic conclusion-permission seeding/promotion/resolution, no agent self-verification, verifier-promoted blocker, static authority-map source guard, legacy Data Gate permission boundary |
| `runtime/graph.py::_build_graph()` fixed topology, `runtime/workflows/domain_execution.py`, `runtime/workflows/legacy_dispatch.py`, `runtime/workflows/legacy_node_dispatch.py`, and `runtime/workflows/generic_swarm_workflow.py` fallback | Descriptor modes can now explicitly defer orchestration-time generic execution to the `workflow_host` graph node, which hosts safe sync/async node entrypoints; `workflow_host` eligibility no longer rejects code/compliance/evidence descriptors by static graph-mode name when they are explicitly deferred, while ordinary planned descriptor traces stay on their declared graph-node path; known graph node methods prefer active workflow `node_entrypoints`, evidence/compliance research nodes now declare descriptor entrypoints, descriptor-declared `orchestration_entrypoint` hooks now build code/compliance/evidence plans before graph-mode compatibility fallback, descriptor-declared `execution_entrypoint` hooks interpret code/compliance/evidence executor results, and graph/domain execution bridges pass the graph runtime's ToolRegistry into generic workflow execution and accepted declared entrypoints; thin descriptors naming real capabilities backfill missing entrypoints from manifest workflow descriptors before fallback dispatch, legacy code/compliance/evidence graph-mode fallback maps and built-in graph-mode exclusions are isolated in `runtime/workflows/legacy_dispatch.py`, legacy compliance/evidence research-node fallback dispatch is isolated in `runtime/workflows/legacy_node_dispatch.py`, and graph/domain execution bridges only delegate to those compatibility resolvers; graph node dispatch uses manifest backfill before legacy research-node fallback, explicit protocol-backed static specialist nodes without declared node entrypoints are rejected before value-investing/generic/legacy graph-mode fallback, no-entrypoint code/compliance/evidence compatibility handlers now emit `legacy_graph_mode_workflow_fallback` orchestration/execution traces, and old no-entrypoint compliance/evidence research-node handlers emit `legacy_graph_mode_node_fallback` traces instead of silently acting as domain truth; descriptor routing now prefers selected skills over metadata order, domain workflow gate status can emit protocol stop-signals, workflow trace guardrails avoid hardcoded guardrail-agent names, graph orchestration suppresses ticker/company-name investment defaults for protocol-backed OS plans without declared committee/source-policy pressure, workflow descriptors carry data/evidence/output/runtime-support contract bundles, normalized graph run results expose generic `agent_outputs`/`agent_decision`, and Critic/Writer/Final Judge contexts use those generic fields plus explicit legacy lineage; the core LangGraph shell is still fixed and specialized compatibility paths remain | Descriptor-native graph host with reduced specialized compatibility branches | P0/P1 | Toy workflow, graph node descriptor dispatch, built-in research node dispatch, orchestration entrypoint dispatch, execution entrypoint dispatch, async entrypoint dispatch, manifest backfill before legacy fallback, legacy fallback trace, legacy node fallback trace, generic workflow-host routing, explicit built-in descriptor deferral, missing workflow error, protocol node entrypoint requirement, node escape block, workflow stop-signal bridge, workflow contract bundle, OS-plan heuristic suppression, graph node legacy boundary guard, investment regression |
| `runtime/workflows/legacy_graph_routing.py` and `runtime/workflows/legacy_routing_aliases.py` legacy graph routing heuristics | Legacy task-type aliases, task inference hints, direct-answer complexity markers, quant/domain analysis hint tables, shorthand graph-node aliases, and descriptorless default workflow node order/source are isolated outside `runtime/graph.py` and generic workflow routing; graph and workflow routing keep compatibility wrapper/helper calls but no longer own those static heuristic, alias, or fallback-order tables, and descriptorless routing summaries trace `legacy_default_graph` | Capability-declared intent/workflow routing first, with legacy graph heuristics kept as an explicit compatibility boundary | P1 | Graph legacy routing heuristic boundary guard, workflow node-alias/default-order boundary guard, default fallback trace regression, task-type routing regressions |
| `runtime/workflows/legacy_orchestration_defaults.py` legacy graph orchestration defaults | Legacy fixed graph agent flags, company-name/ticker investment promotion, investment/WRDS committee defaults, direct-answer collapse, and default WRDS data-package/research-question normalization are isolated outside `runtime/graph.py`; graph resolves task type plus OS-plan suppression and delegates the default construction through a thin wrapper | Capability workflow descriptors and OS plan first, with legacy orchestration defaults kept as an explicit compatibility boundary | P1 | Graph orchestration default boundary guard, OS-plan heuristic suppression, investment/default orchestration regressions |
| `runtime/workflows/legacy_result_defaults.py` legacy graph result defaults | Legacy skipped-analysis reason text for normalized outputs, runtime preflight blocks, preflight-block review summaries, and memory-context metadata keys is isolated outside `runtime/graph.py`; graph still builds generic skipped-analysis payloads and memory context but no longer owns the compatibility reason/summary/key catalog | Capability workflow/result descriptors for default output fields, with legacy result reasons kept as an explicit compatibility boundary | P1 | Graph legacy result-default boundary guard, normalized-result/preflight regression |
| `runtime/wrds_planner.py`, `runtime/legacy_wrds_planner_defaults.py` deterministic WRDS package defaults | `runtime/wrds_planner.py` remains the public deterministic WRDS planning API, but the legacy account availability profile, package catalog, default investment research questions, semiconductor package expansion, and OptionMetrics market-risk heuristics are isolated in `runtime/legacy_wrds_planner_defaults.py` instead of owned by the planner façade | Descriptor-declared data-plan adapters and data-contract packages first, with deterministic WRDS package defaults kept as explicit compatibility data | P1 | WRDS planner regression, WRDS company planner regression, WRDS planner legacy-default boundary guard |
| `runtime/wrds_company_planner.py`, `runtime/legacy_wrds_company_planner.py`, `runtime/graph.py`, and `runtime/workflows/source_tool_helpers.py` WRDS company detection hints | WRDS company-financials planning still recognizes selected capability metadata before compatibility hints, but legacy known-company research markers, non-company query exclusions, ticker-code exclusions, CJK company suffix hints, and company-query intent markers are isolated in `runtime/legacy_wrds_company_planner.py`; graph and source-tool helpers call `known_research_company_markers()` instead of importing marker tuples | Capability/data-contract signals first, with legacy company-detection hints only as compatibility query inference | P1 | WRDS company marker boundary guard, WRDS company planner regression, graph/source helper marker regression |
| `runtime/workflows/legacy_plan_defaults.py` legacy deterministic fallback plans | Legacy no-plan fallbacks for WRDS/source-policy direct plans, public-web research, code workspace inspection, and direct no-tool answers are isolated outside `runtime/graph.py`; graph delegates through a thin `deterministic_plan()` wrapper and records `legacy_deterministic_plan_fallback` when this compatibility path runs | Capability workflow `plan_entrypoints` and model plans first, with deterministic fallback plans kept as explicit compatibility paths | P1 | Deterministic plan metadata regression, graph legacy plan boundary guard, plan fallback trace |
| `runtime/tool_names.py`, `runtime/workflows/source_tool_helpers.py`, and `runtime/workflows/legacy_source_grounding.py` source-tool helper boundary | Concrete web/fetch source-tool identifiers are centralized in `runtime/tool_names.py`, while search/fetch/WRDS company tool-name sets, provider-search upgrade decisions, search-result URL ranking, execution failure summarization, and review source-grounding helpers are isolated outside graph core; the old keyword-triggered auto-fetch heuristic is isolated in `runtime/workflows/legacy_source_grounding.py` and consulted only after selected capability metadata and known-entity checks; `ToolRegistry`, `runtime/web_research_planner.py`, and `runtime/workflows/evidence_research.py` consume the shared identifiers/tables instead of owning duplicate public-web source-retrieval constants; `runtime/graph.py` keeps compatibility wrappers plus ToolRegistry dispatch | Capability ToolPolicy/source policy plus workflow plan entrypoints first, with shared source-tool helper logic outside graph core and keyword auto-fetch as explicit compatibility | P1 | Source-tool helper boundary guard, legacy source-grounding boundary guard, tool-name catalog guard, auto-fetch/provider-search/source-grounding regressions |
| `runtime/workflows/wrds_payload_safety.py` WRDS public/model/audit payload safety | Raw WRDS row key tables, recursive public API/trace redaction, WRDS execution-log redaction, model-context WRDS result summaries, and audit-log WRDS summaries are isolated outside `runtime/graph.py` and `runtime/audit_log.py`; graph normalization and audit logging call these shared safety helpers instead of owning WRDS raw-data payload rules | Global no-raw-sensitive-data safety boundary with graph/audit as callers only | P0 | Normalized run raw-WRDS row redaction, audit WRDS row redaction, graph/audit WRDS payload safety boundary guard |
| `runtime/workflows/legacy_data_gate_routing.py` legacy graph Data Gate trigger fallback | Old graph-level `require_data_gate`, WRDS-tool, investment-task, committee, and required-WRDS-agent trigger fallback is isolated outside `runtime/graph.py`; `runtime/graph.py::should_run_data_gate` honors workflow-node and descriptor Data Gate decisions first, reads legacy Data Gate tool names only through `legacy_data_gate_tool_names()`, and descriptor-backed not-required decisions suppress this compatibility fallback | Descriptor `gate_policy.required_when` first, with legacy graph trigger routing only after no descriptor authority applies | P1 | Graph Data Gate routing boundary guard, descriptor suppresses legacy fallback regression |
| `runtime/workflows/legacy_wrds_routing.py` legacy direct-WRDS graph routing fallback | Old graph-level WRDS SQL/action metadata, direct SQL text, legacy WRDS skill, direct-WRDS orchestration defaults, and the direct-WRDS one-step plan scaffold are isolated outside `runtime/graph.py`; graph wrappers resolve WRDS capability runtime routing entrypoints first and use this compatibility path only when descriptor routing is missing or invalid | WRDS capability `runtime_nodes.routing` first, with legacy direct-WRDS routing as a traced compatibility fallback | P1 | Graph direct WRDS routing boundary guard, WRDS runtime routing entrypoint regression, legacy WRDS routing fallback regression |
| `runtime/graph.py`, `runtime/legacy_value_investing_support.py`, and `runtime/workflows/legacy_wrds_routing.py` graph compatibility capability IDs | Graph fallback loaders no longer inline the built-in value-investing or WRDS capability IDs; they obtain those IDs through `legacy_value_investing_capability_id()` and `legacy_wrds_financial_data_capability_id()` while descriptor-backed entrypoints remain preferred | Capability runtime descriptors first, with built-in capability IDs isolated as compatibility values | P1 | Graph capability-ID boundary guard, value/WRDS runtime loader regression |
| `runtime/workflows/orchestration_guidance.py`, `runtime/workflows/legacy_orchestration_guidance.py`, workflow descriptor `orchestration_guidance`, and ToolPolicy `source_mode_guidance` | The graph orchestrator prompt now owns only the generic JSON planning contract; investment/WRDS prompt instructions come from the value-investing workflow descriptor, WRDS-only source-mode guidance comes from ToolPolicy when declared, no-guidance source-mode templates and old no-descriptor investment/model-role wording are isolated as traced legacy guidance, and source-mode traces distinguish declared blocked-tool targets from legacy public-web target fallback | Capability-declared orchestration guidance plus ToolPolicy source-mode guidance, with legacy prompt wording only for compatibility paths | P1 | Graph prompt guidance boundary guard, source-mode guidance lineage, toy protocol prompt avoids investment guidance, value workflow declares guidance |
| `runtime/graph.py`, `runtime/factory.py`, `runtime/ports.py`, and FastAPI runtime assembly model dependency | Graph model calls now go through an explicit `model_gateway` attribute typed by the generic `ChatModelClient` runtime port, runtime assembly can pass `model_gateway=` directly, and the old `llm` constructor field remains only as compatibility input for existing tests/adapters | ModelGateway as the graph's first-class model-call boundary | P0 | Graph ModelGateway boundary guard, graph port-typed dependency guard, model-gateway constructor regression |
| `runtime/graph.py`, `runtime/data_gate.py`, `runtime/legacy_data_gate_policy.py` investment source-mode/tool/Data Gate branches | Investment protocol now declares ToolPolicy/OutputPolicy/EvidencePolicy; source-mode/tool/skill checks delegate to reusable modules; capability ToolPolicy can declare source mode; WRDS company plus public web step insertion are invoked through capability workflow `plan_entrypoints` adapters; data contract construction, graph Data Gate routing, source-mode policies, source rules, source validation rules, Data Gate required-when policy, Data Gate required-data validation-rule policy, formula validation-rule policy, margin-basis validation-rule policy, Compustat standard-filter policy, balance-sheet jump policy, Data Gate defect memo policy, Data Readiness memo policy, metric-registry policy, metric-registry warning rules, completeness metrics, metric aliases, source-mode limitations, confidence policy, forbidden-claim policy, acquisition/financial/earnings/package-gap profile policy, estimate/non-GAAP metric groups, profile evidence rules, acquisition-intensive profile evidence rules, profile warning rules, forward-estimate evidence-gap rules, Data Gate score policy, Data Gate output effects, WRDS-only claim guardrails, WRDS-only claim defect memo policy, WRDS-only confidence policy, WRDS-only confidence validation-rule policy, WRDS-only metric requirement policy, WRDS-only metric requirement validation-rule policy, WRDS-only output-effect policy, WRDS-only required-period policy, WRDS-only required-period validation-rule policy, metric-registry adapter selection, WRDS result collection, WRDS company-tool argument normalization, direct WRDS routing, and WRDS public/model/audit payload safety consume selected descriptors or shared helper modules; task-type alone and the removed `investment_web_search_disabled` flag no longer create WRDS-only source authority, metric-registry usage rules and source-priority baselines cite descriptor-backed `metric_registry_policy` before `legacy_metric_registry_policy` fallback, metric-registry large-margin warning payloads cite descriptor-backed `metric_registry_policy.warning_rules` before `legacy_metric_registry_warning_rule` fallback, acquisition/financial/earnings/package-gap profile detection marks `data_contract_profile_policy` before `legacy_profile_policy` fallback, Data Gate forward-estimate evidence gaps cite descriptor-backed `gate_policy.evidence_gap_rules` before `legacy_gate_evidence_gap_rule`, acquisition-intensive profile evidence gaps cite descriptor-backed `gate_policy.profile_evidence_rules` before `legacy_profile_evidence_rule`, acquisition-heavy missing-non-GAAP warnings cite descriptor-backed `gate_policy.profile_warning_rules` before `legacy_profile_warning_rule`, Data Gate mandatory trigger policy and graph Data Gate routing cite descriptor-backed `gate_policy.required_when` before compatibility fallback, required-data blockers cite descriptor-backed `gate_policy.required_data_rules` before `legacy_data_gate_required_policy` fallback, internal formula validation errors cite descriptor-backed `gate_policy.formula_validation_rules` before `legacy_formula_validation_rule` fallback, high-depreciation margin-basis errors cite descriptor-backed `gate_policy.margin_basis_rules` before `legacy_margin_basis_rule` fallback, Compustat standard-filter warnings cite descriptor-backed `gate_policy.compustat_standard_filter_rules` before `legacy_compustat_standard_filter_rule` fallback, material balance-sheet jump blockers cite descriptor-backed `gate_policy.balance_sheet_jump_rules` before `legacy_balance_sheet_jump_rule` fallback, legacy graph Data Gate routing fallback is isolated in `runtime/workflows/legacy_data_gate_routing.py`, legacy direct-WRDS routing fallback is isolated in `runtime/workflows/legacy_wrds_routing.py`, WRDS raw-row public/model/audit payload safety is isolated in `runtime/workflows/wrds_payload_safety.py`, Data Gate source-mode verification level and allowed sources cite descriptor-backed `source_mode_policies` before `legacy_source_mode_policy` fallback, Data Gate source timing rules cite descriptor-backed `source_rules` and source timing, reconciliation, and identity validation payloads cite descriptor-backed `source_validation_rules` before `legacy_source_rules` fallback, Data Gate forbidden claims cite descriptor-backed `forbidden_claims` before `legacy_forbidden_claims` fallback, Data Gate non-GAAP/estimate groups cite descriptor-backed `gate_policy` before `legacy_gate_metric_group` fallback, legacy Data Gate policy tables are isolated in `runtime/legacy_data_gate_policy.py`, Data Gate defect memos cite descriptor-backed `gate_policy.defect_memo` before `legacy_data_defect_memo_policy` fallback, Data Readiness memos cite descriptor-backed `gate_policy.readiness_memo` before `legacy_data_readiness_memo_policy` fallback, WRDS-only report claim blockers now come from `claim_guardrails.wrds_only_disallowed_claims` before `legacy_wrds_only_claim_guardrail` fallback, WRDS-only claim defect memo required fixes come from `claim_guardrails.wrds_only_required_fixes` before `legacy_wrds_only_claim_guardrail` fallback, WRDS-only claim defect memo shells cite descriptor-backed `claim_guardrails.wrds_only_defect_memo` before `legacy_wrds_only_claim_defect_memo_policy` fallback, WRDS-only limitation boxes and Data Gate limitation items come from `source_mode_limitations` before `legacy_wrds_only_limitations` fallback, Data Gate metric normalization cites `data_contract_metric_aliases` before `legacy_metric_aliases` fallback, high-confidence blockers cite `data_contract_confidence_policy` plus `confidence_policy.validation_issue` payloads only when the contract's confidence policy is source-marked as descriptor-backed before `legacy_wrds_only_confidence_guardrail` fallback, non-GAAP source blockers cite `data_contract_metric_requirement` plus `gate_policy.metric_requirement_rules` validation payloads before `legacy_wrds_only_metric_requirement` fallback, formal-valuation conclusion blockers read declared Data Gate conclusion permissions before legacy top-level permission fields and cite `gate_policy.output_effects` including `validation_issue` payloads before `legacy_wrds_only_output_effect` fallback, and quarterly-trigger blockers cite `data_contract_required_period_policy` plus `gate_policy.required_period_rules` validation payloads before `legacy_wrds_only_required_period_policy` fallback | Keep deterministic compatibility fallbacks only for invalid or missing descriptors plus global source policy | P0 | Explicit investment protocol, WRDS-only web block, raw WRDS final block, WRDS/web planner regression, descriptor data contract/profile/gate/required-when/required-data-rule/formula-validation-rule/margin-basis-rule/compustat-standard-filter-rule/balance-sheet-jump-rule/defect-memo-policy/readiness-memo-policy/claim-defect-memo-policy/source-mode-policy/source-rules/source-validation-rule/metric-registry-policy/metric-registry-warning-rule/profile-policy/profile-evidence-rule/profile-warning-rule/claim-guardrail/forbidden-claim/gate-evidence-gap-rule/gate-metric-group/metric-requirement-rule/required-period-rule/confidence-rule/confidence/metric/alias/source-mode-limitations/output-effect/period policy, Data Gate legacy policy boundary, graph Data Gate routing boundary guard, graph direct WRDS routing boundary guard, graph/audit WRDS payload safety boundary guard, metric-registry entrypoint trace, WRDS result collector trace, WRDS argument normalizer dispatch, WRDS routing entrypoint |
| `runtime/data_gate.py` Data Gate compatibility helper boundary | Legacy `LEGACY_*` fallback values remain in `runtime/legacy_data_gate_policy.py`; `runtime/data_gate.py` now calls lower-case compatibility helpers for those values and the boundary test asserts it contains no direct `LEGACY_` references | Descriptor-backed `data_contract` and `gate_policy` declarations first, with helper-only legacy fallback for missing descriptors | P1 | Data Gate legacy policy boundary, WRDS-only guardrail fallback regression |
| `runtime/swarm/tool_policy_resolver.py`, `runtime/swarm/tool_plan_policy.py`, `runtime/swarm/action_policy.py`, `runtime/swarm/source_policy_modes.py`, `runtime/swarm/legacy_tool_policy.py`, `runtime/swarm/events.py`, `runtime/swarm/snapshot_builder.py`, `runtime/wrds_company_planner.py`, `runtime/web_research_planner.py`, `runtime/research_selection.py`, `runtime/legacy_research_selection.py`, `app/routes/wrds.py`, plus graph/source-policy branches | Execution, source-mode derivation, plan/skill filtering, initial stop-signal seeding, worker-policing web-tool checks, patroller readiness, web-tool stop-signal resolution, WRDS company step planning, web-search insertion, and authenticated platform WRDS API routes are reusable registry-backed modules; WRDS and web planning now have capability-declared adapters, web-search insertion, graph-level deterministic web planning/provider-search upgrade/auto-fetch/orchestration-default decisions, WRDS-only public-web skill partitioning, WRDS company-financials planning can recognize selected capability metadata such as `capability_types`/web-research/company-financial flags before legacy skill-name compatibility, the remaining legacy research/web/WRDS skill-name, capability-type marker, and metadata-flag sets are isolated in `runtime/legacy_research_selection.py`, and WRDS company-financials planning no longer follows task type alone without an explicit WRDS/data signal; provider-search upgrades require selected research capability metadata instead of investment/committee labels alone, and direct WRDS task inference/routing can use data-source markers such as `professional_financial_database` while investment-research markers remain non-bypass; source mode can come from explicit metadata, Data Gate, or ToolPolicy before plan filtering, WRDS-only source-mode aliases and canonical source-mode spelling are centralized in `runtime/swarm/source_policy_modes.py`, source-mode provenance is recorded as `source_mode_decision`, ToolPolicy can declare `source_policy_blocked_tool_targets` consumed by plan filtering, graph tool manifests, initial stop-signals, policing, and stop-signal resolution before legacy public-web fallback, ToolPolicy can declare `source_policy_block_message` and `source_policy_constraint_message` consumed by source-policy stop signals and initial pheromone signals before legacy source-policy message templates, graph blocked-skill reasons and blocked-tool result detail text now also delegate to `runtime/swarm/legacy_tool_policy.py`, legacy blocked-tool field aliases such as `source_policy_blocking_tool_targets` and `web_research_tool_targets` are isolated in `runtime/swarm/legacy_tool_policy.py` and normalize to `source_policy_blocked_tool_targets`, Patroller WRDS-source readiness delegates to the shared source-policy helper and legacy readiness-detail helper instead of reading legacy OS-plan flags or owning WRDS wording directly, the legacy public-web tool fallback set and legacy source-policy message templates are isolated in `runtime/swarm/legacy_tool_policy.py`, source-policy block traces use capability-agnostic wording, legacy investment web-disable flags are ignored, Protocol Police evaluates execution-log tools through the shared ToolPolicy resolver for non-web capability block/allowlist violations, platform WRDS routes dispatch through `ToolRegistry`, and tool results/traces carry normalized allow/block/deny/quarantine policy events with structured decisions; completed runs now persist explicit protocol/control-loop events before deriving fallback timeline events for capability protocol loading, candidate commits, agent allocation, tools, permissions, and recovery traces; explicit `tool.*` and `permission.*` events suppress derived fallback duplicates, and the debugger snapshot summarizes those events | Event-sourced policy/governance trace authority with richer source-policy lineage | P0/P1 | Permission override, stop-signal alias block, quarantine, graph execution block, auto-fetch block, platform WRDS route registry dispatch, tool policy trace events, source/tool plan and skill filters, Data Gate source-mode plan filter, WRDS and web planning, generic source-policy wording, source-policy message lineage, patroller source-policy helper boundary, source-mode alias/canonical-value boundary, non-web policing via ToolPolicy, declared source-policy blocked tool targets, legacy ToolPolicy field alias boundary, research-selection compatibility boundary |
| `runtime/swarm/candidate_registry.py`, `runtime/swarm/quorum.py`, `runtime/swarm/target_registry.py`, `runtime/swarm/evidence_graph.py`, `runtime/swarm/independent_scout.py`, `runtime/swarm/quorum_marshal.py`, `runtime/swarm/legacy_quorum_targets.py`, and `runtime/swarm/legacy_target_aliases.py` | Candidate registry now requires declared candidate/quorum policy; investment labels do not create candidates without the value-investing protocol, fallback-ish labels no longer become safe fallbacks for explicit protocols without `candidate_fallback` or `safe_fallback`, and the missing-policy compatibility reason delegates to `runtime/swarm/legacy_protocol_fields.py`; target canonicalization no longer maps plain labels such as Buy/Watch/Sell into investment candidate targets and no longer exports investment candidate constants outside the legacy GoalRouter fallback; value-investing phrase aliases such as `target price` and `investment recommendation` now come from protocol target declarations and survive protocol bundle normalization, while legacy target-alias audit markers, formal/report decision-target spellings such as `formal_valuation`, `valuation`, `report_publication`, and `final_report`, concrete WRDS-only source-policy target spelling, bare web/fetch tool target spellings such as `web_search` and `approved_source_fetch`, legacy formal/report target constants/helpers, and legacy code/compliance/research target constants live in `runtime/swarm/legacy_target_aliases.py` instead of the core registry alias table or exports; generic `tool:*` targets still canonicalize by prefix; code-development phrase aliases such as `tests_failed`, `public_api_changed`, and `accept_patch` likewise come from protocol target declarations, with legacy code target-alias audit markers isolated in `runtime/swarm/legacy_target_aliases.py`; compliance phrase aliases such as `approval_required`, `email_send`, and `records_retention` come from protocol target declarations, with legacy compliance target-alias audit markers isolated there too; research phrase aliases such as `fake_citation`, `claim_support`, and `source_candidates` come from evidence/web research protocol target declarations, with legacy research target-alias audit markers isolated there too; domain workflow events resolve target aliases through capability protocol bundles before global canonical fallback; EvidenceGraph candidate nodes use declared quorum candidate IDs, decision claims read generic `agent_decision` with `decision_source` lineage, and fallback provenance is marked `legacy:investment_committee`; quorum scoring uses declared evidence/source/risk/stop-signal/source-quality weights, explicit support/oppose signals, agent reliability, candidate-specific verified EvidenceGraph support edges, generic blocked conclusion targets, and generic publication-target classification so declared publish targets do not masquerade as evidence-readiness defects; low-independence fallback and marshal stop-signal explanations use declared fallback candidate data plus authoritative `blocked_conclusion_targets`, with legacy formal/report booleans only backfilling through `runtime/swarm/legacy_quorum_targets.py` when generic targets are absent and fallback-ish label detection retained only for legacy traces without candidate registry metadata | Richer multi-hop evidence lineage and source-quality provenance from EvidenceGraph adapters | P0/P1 | Toy candidates, declared fallback, no inferred fallback label, investment declaration, policy-weighted scoring, support-signal/reliability scoring, evidence-graph/source-quality scoring, generic blocked conclusion targets, generic publication classification, low-independence declared fallback, generic target over legacy booleans, legacy quorum boolean boundary, legacy target-alias boundary, formal/report alias delegation boundary, source-policy alias delegation boundary, web-tool alias delegation boundary, formal/report target export boundary, legacy domain target export boundary, missing-candidate no-default, undeclared Buy no-op, no plain-label, investment-phrase, code-phrase, compliance-phrase, or research-phrase global aliases |
| `runtime/llm.py`, `runtime/runtime_context.py`, `runtime/legacy_model_roles.py`, `runtime/legacy_runtime_validation.py`, and manifest `model_attr` selection | Existing static model fields remain as compatibility aliases, but scoped provider overrides now support arbitrary manifest `model_attr` names through `ModelConfig.agent_model_overrides` and `ModelConfig.model_for(...)`; legacy scoped model-role aliases and single/mixed-provider compatibility role maps are isolated in `runtime/legacy_model_roles.py`; RuntimeContext legacy WRDS capability/tool validation payloads and graph preflight legacy WRDS issue-code classification are isolated in `runtime/legacy_runtime_validation.py`; value-investing committee member execution uses the generic resolver instead of direct dataclass-field lookup | Capability/agent-manifest model routing with compatibility aliases for old fields | P1 | Arbitrary manifest model attr override, compatibility scoped provider override, scoped alias regression, committee model resolver source guard, legacy model-role boundary guard, legacy runtime validation boundary guard |
| `runtime/swarm/recovery_engine.py`, `runtime/swarm/control_loop.py`, `runtime/workflows/domain_execution.py`, `runtime/workflows/generic_swarm_workflow.py`, `runtime/workflows/evidence_research.py`, and `runtime/swarm/bottleneck_recruitment.py` | Recovery and bottleneck selection are protocol-aware, recovery selection honors declared trust/maturity requirements, required tools can execute through ToolRegistry, the generic control loop now passes a hosted ToolRegistry into RecoveryEngine when available from workflow-host or domain execution bridge paths, bottleneck recruitment can discover agents from explicitly enabled capability manifests, evidence-research fallback recruitment now comes from capability protocol plus agent catalog metadata instead of a hardcoded agent-name list, and control-loop `recovery.protocol_selected`/`recovery.agents_selected`/`recovery.tools_executed` events carry selected-protocol, selected-agent, and tool lineage before the final recovery outcome event; direct model/workflow recovery rounds outside the hosted runtime bridge remain adapter-driven | RecoveryEngine and control loop integrated into workflow host with richer capability-declared recovery actions | P1 | Select by role/tag/trust/maturity, toy recovery, ToolRegistry success/failure, selection event lineage, resolution, fallback, no hardcoded names |
| `runtime/swarm/stop_signal_policy.py`, `runtime/swarm/action_policy.py`, `runtime/swarm/resolution.py`, `runtime/swarm/stop_signal.py`, and `runtime/swarm/legacy_output_phrases.py` | Action blocking and custom resolution are protocol-aware, declared resolution policies win over legacy Data Gate and web-tool auto-clear paths for matching targets, source-policy blocks no longer infer from investment task type, publish-report output effects can be enforced through protocol actions, domain workflow blockers can be emitted as stop-signals, and StopSignalPolicy `action_markers` now declare built-in code/compliance/evidence phrases that imply writer/final-judge actions; direct formal-valuation report enforcement also uses action markers before legacy no-policy wording, and old formal-recommendation phrase regexes are isolated in `runtime/swarm/legacy_output_phrases.py` | StopSignalPolicy action effects and generic writer/final-judge effects | P0/P1 | Policy block, global safety cannot weaken, resolution authority, resolved candidate, workflow gate bridge, action marker inference, marker-first report block, legacy output phrase boundary |
| `runtime/output_contract.py`, `runtime/legacy_output_contract.py`, `runtime/writer_guardrails.py`, `runtime/final_judge_guardrails.py`, `runtime/swarm/policing.py`, `runtime/swarm/legacy_output_phrases.py`, `runtime/workflows/legacy_guardrails.py`, `runtime/swarm/conclusion_claims.py`, `runtime/swarm/artifact_cues.py`, `runtime/swarm/evidence_steward.py`, `runtime/swarm/governance_results.py`, `runtime/swarm/evidence_graph.py`, and `runtime/swarm/evidence_contract.py` | OutputPolicy/EvidencePolicy contract checks are protocol-aware, candidate consistency reads quorum or capability candidate policy without invented defaults, committed-candidate conflict phrases are capability-declared and worker policing plus Evidence Graph writer contracts now consume those rules, policing and Evidence Contract no-policy compatibility fallbacks use declared fallback-candidate identity instead of a literal investment label, fallback-ish labels only retain fallback authority for legacy quorum traces without candidate-registry metadata, Evidence Graph output-permission nodes enumerate declared Data Gate `conclusion_permissions` instead of only formal/report permissions and no longer invent formal/report permissions when none are declared, Evidence Graph decision-claim output allowance uses declared target/publication permissions instead of silently inheriting legacy report-publication defaults for protocol-backed gates, Artifact Cue/Evidence Steward/Evidence Contract blocked-claim detection matches blocked conclusion permissions to StopSignalPolicy `writer:<target>` markers before no-marker legacy formal-valuation fallback, old formal-valuation/recommendation phrase regexes and fallback conflict phrase lists are isolated in `runtime/swarm/legacy_output_phrases.py`, Artifact Cue/Evidence Steward blocked-claim records carry `blocked_target_source` and `writer_action` lineage for declared marker versus legacy formal-valuation fallback, writer guardrails run generic stop-action policy before legacy swarm-report fallback, direct swarm report policy can consume arbitrary declared writer action markers, Evidence Steward/Governance Results emit generic blocked-claim/output-permission writer constraints with target-scoped allowed/blocked permission inventories, Evidence Steward emits formal-valuation compatibility fields only when that Data Gate permission exists and marks them as legacy conclusion fields, Protocol Police stop-signals and Governance Results preserve explicit violation decision targets and otherwise use declared publish/publication permissions before the legacy report-publication fallback, governance contract catalog defaults are generic blocked-output/tool-policy surfaces rather than formal/report/web-search defaults, raw-data absence is a shared contract default, capability-specific raw-data leak markers can be declared through EvidencePolicy with Protocol Police lineage before `legacy_raw_data_marker_fallback`, with that legacy marker fallback isolated in `runtime/legacy_output_contract.py`, `defect_memo_on_block` enforces protocol-declared publish-report blockers, defect-memo markers can be capability-declared, prompts summarize capability policies instead of hardcoding investment wording, protocol-backed domain workflow gates use declared stop-signal actions, Protocol Police also consumes declared workflow gate actions before legacy fallback dispatch, Writer/Final Judge action detection consumes StopSignalPolicy `action_markers`, and direct code/evidence workflow result helpers emit declared gate stop-signals; central phrase cues are now no-marker legacy fallback, no-policy workflow writer/policing fallback bodies and the source-candidate-only required caveat are isolated in `runtime/workflows/legacy_guardrails.py` with `legacy_graph_mode_writer_fallback` and `legacy_graph_mode_policing_fallback` source markers, and central Writer/Protocol Police modules only delegate to those compatibility boundaries | Keep generic contract consumers and migrate remaining no-protocol workflow fallback effects into capability protocols | P0/P1 | Unsupported claims, custom blocked phrase, required caveat, final judge consistency, raw/citation/evidence policy, declared output permissions, declared raw-data marker, legacy raw-data marker boundary, defect memo on block, workflow action block, legacy writer fallback source, legacy policing fallback source, legacy output phrase boundary, policy prompt, protocol workflow gate action, declared defect marker, declared action marker, policing/evidence-contract candidate conflict, generic governance constraints, target-scoped artifact/evidence/contract detection |
| `capabilities/toy-review/` | Toy proof now covers OS planning, direct generic workflow host execution, async orchestrator deferral into the `workflow_host` graph node, recovery, quorum, stop-signal, and output policy; the core graph shell remains fixed | Reduce remaining specialized graph compatibility paths while keeping arbitrary capability workflow execution descriptor-hosted | P1 | Toy declaration, OS plan, orchestrator generic workflow deferral/execution, recovery, quorum, output policy |
| `runtime/swarm/trace_store.py`, `runtime/swarm/governance_results.py`, `runtime/swarm/legacy_quorum_targets.py`, `runtime/audit_log.py`, and API routes | Debugger endpoints exist; explicit runtime events from `swarm_protocol_trace` and `swarm_control_loop.events` persist before derived fallback governance events; matching signal timeline rows from compatibility `pheromone_signals` are suppressed when normalized `signal.*` events exist; governance trace events prefer runtime blocked targets while retaining generic static contract targets and `blocked_target_source` payload lineage, so legacy formal/report boolean fallback is explicit, delegated through `runtime/swarm/legacy_quorum_targets.py`, and generic `blocked_conclusion_targets` remain authoritative; `capability.protocol.loaded` events can reconstruct a missing protocol bundle for lineage; audit summaries now preserve generic `blocked_conclusion_targets` alongside legacy formal/report booleans while delegating those legacy boolean names through `runtime/swarm/legacy_quorum_targets.py`; audit summaries also expose generic `agent_outputs` plus `agent_output_source`/`legacy_agent_outputs` lineage while old `committee_outputs` payloads remain compatibility input behind `runtime/swarm/agent_outputs.py`, and expose generic `agent_decision` plus `agent_decision_source`/`legacy_agent_decision` lineage while old `committee_decision` payloads remain compatibility input behind `runtime/swarm/agent_decisions.py`; `/agents/run` exposes generic `agent_outputs`/`agent_decision` in its public response model before legacy committee compatibility fields; evidence-graph can derive minimal claim/artifact/signal nodes from governance events and now prefers normalized governance event nodes over stale evidence-table nodes while retaining table edges and detail-only nodes; pheromone snapshot reconstruction now prefers normalized `signal.*` events for the signal list before compatibility `pheromone_signals` rows; agent-allocation, why-agent, tool-events, permission-events, target-scoped why-blocked signal explanations, event-only recovery-lineage details, and detailed recovery-lineage event traces prefer normalized event records over compatibility side tables/payloads; selected recovery protocol summaries, recovery recruitment reports, and recovery events carry `capability_id`/source/protocol-source lineage, with control-loop recovery protocol/agent/tool milestones emitted directly as normalized events; `why_blocked` and `recovery_lineage` include target-scoped capability protocol lineage, `why_committed` includes committed-candidate protocol lineage, and `why_agent` includes target/agent-selection protocol lineage, but not every governance transition is event-authoritative yet | Complete normalized event authority for all governance transitions | P1 | Snapshot reconstruction, explicit runtime events, event-sourced protocol bundle, event-first signal timeline, event-first evidence graph, event-first agent/tool/permission/why-blocked/recovery readers, target-scoped governance trace events, selected recovery protocol lineage, recovery recruitment lineage, legacy quorum boolean boundary, generic audit decision lineage, generic API agent state, why-blocked protocol lineage, why-committed protocol lineage, recovery protocol lineage, why-agent protocol lineage, protocol endpoints, redaction |

## First Safe Implementation Slice

1. Add typed protocol schema modules while preserving existing `swarm` manifests.
2. Add a compatibility loader that can read a full `protocol` section, an
   external `pheroos_protocol.json`, or legacy `swarm` data.
3. Add validation for canonical targets, aliases, candidate target references,
   recovery references, trust-gated blocking authority, and raw-data defaults.
4. Update `runtime/swarm/protocol.py` to use the loader as the source of
   normalized protocol bundles, keeping output shape compatible with current
   `goal_router.py`.
5. Add focused tests before changing graph/quorum/recovery behavior.

This slice moves the system toward protocol-declared authority without changing
the main graph runtime yet.
