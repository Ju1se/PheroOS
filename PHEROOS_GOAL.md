# PheroOS Goal

Goal: Incrementally upgrade the existing PheroOS Swarm Governance layer into a stronger insect-inspired multi-agent protocol system.

Context:
This repo is an AI-as-OS Agent Committee Platform. It already has:
- OS Kernel / RuntimeContext / LangGraph Runtime
- Capability Registry and Agent Registry
- Tool Registry, Model Gateway, Permission Policy
- WRDS-only investment workflow
- Data Gate
- PheroOS Swarm Governance layer under runtime/swarm
- PheromoneSignal types including constraint, permission, evidence, data_contract, progress, risk, negative, demand, quorum, capability, tool_health, model_route, crowding, stop_signal
- PheromoneFieldManager with reinforce / decay / snapshot / trace
- PatrollerGate
- Data Gate signalization
- Stop-Signal enforcement
- Agent Manifest swarm metadata
- Signal Verifier
- Response Threshold agent activation
- Agent Profile local JSON learning
- Quorum candidate decision
- /agents/run swarm fields
- /platform/swarm/signals, /platform/swarm/events, /platform/swarm/agent-profiles
- Dashboard Swarm Governance trace panel
- PheroOS governance caste manifests under `capabilities/value-investing-research/agents/`
- Receiver Normalizer, Evidence Steward, Tool Health Sentinel, Capability Sandbox Auditor, Outcome Memory Steward, Quorum Marshal, and Governance Actor trace modules

Do not rewrite the architecture. Build on the existing runtime/swarm modules and existing FastAPI / LangGraph / Dashboard structure.

Primary objective:
Add the next layer of insect-inspired protocol primitives to make PheroOS more robust:
1. Encounter-rate controller
2. Bottleneck recruitment / tremble-dance protocol
3. Arousal / risk-intensity controller
4. Lane scheduler
5. Social immunity / quarantine protocol
6. Trust badge / nestmate-recognition protocol
7. Worker-policing protocol
8. Independent-scout quorum adjustment
9. Homeostasis controller
10. Agent maturity lifecycle
11. Artifact cue extraction
12. Governance caste actors: scheduler, receiver, evidence steward, quorum marshal, social immunity, protocol police, tool health sentinel, outcome memory steward, capability sandbox auditor, independent scout

Implementation status:
- The original Phase 1-4 protocol primitives are implemented.
- The P0/P1 governance caste is implemented as local agent manifests plus deterministic runtime modules.
- Governance actors are exposed through `/agents/run` as `swarm_governance_trace` and through Dashboard Agent Plugins / Swarm Governance panels.
- Governance actors are intentionally not ordinary committee seats; the investment committee remains analyst-focused while PheroOS controls evidence, permissions, quarantine, tool health, quorum, and writer constraints.

Implementation requirements:

Phase 0 - Repo inspection
- First inspect the existing repo structure.
- Locate runtime/swarm, runtime/graph.py, runtime/state.py, runtime/data_gate.py, runtime/permission_policy.py, runtime/audit_log.py, app/routes/agents.py, app/routes/platform.py, static/app.js, static/index.html, static/styles.css, and existing tests.
- Summarize the existing swarm-related code before modifying anything.
- Preserve current behavior unless explicitly extending it.

Phase 1 - Extend signal taxonomy safely
- Extend the existing signal type system without breaking old signals.
- Add support for the following new signal types if the enum/model architecture allows it:
  - encounter_rate
  - bottleneck
  - arousal
  - lane_assignment
  - contamination
  - quarantine
  - trust_badge
  - policing
  - homeostasis
  - maturity
  - independence
  - artifact_cue
- If signal types are strict enums, update all validation and tests.
- If adding all signal types at once risks breaking compatibility, add them in a backwards-compatible way.

Phase 2 - Add protocol modules under runtime/swarm
Create or update these modules:

runtime/swarm/encounter_rate.py
- Compute recent local feedback rates from swarm events/signals.
- Track recent verified successes, rejected signals, blocked actions, tool failures, and verifier promotions.
- Output encounter_rate signals.
- Use this to influence agent activation or diagnostics, but do not yet make risky autonomous decisions.

runtime/swarm/bottleneck_recruitment.py
- Detect bottlenecks such as:
  - too many unverified evidence signals
  - too many unresolved risk signals
  - too many pending tool results
  - writer/final_judge backlog
- Emit bottleneck signals.
- Recommend receiver agents such as Data Auditor, Evidence Verifier, Risk Manager, Red Team, Writer, or Final Judge.

runtime/swarm/arousal.py
- Detect high-risk states:
  - formal valuation
  - report publication
  - trade/database/filesystem/write permissions
  - conflicting quorum
  - low evidence coverage
  - active stop_signals
- Emit arousal signals controlling verification intensity.
- Do not directly call models here. Just produce policy recommendations such as increased verifier strictness, lower writer temperature, or higher quorum threshold.

runtime/swarm/lane_scheduler.py
- Implement lane assignment:
  - inspection lane
  - execution lane
  - verification lane
  - synthesis lane
  - control lane
- Return lane_assignment signals for agents/actions.
- Enforce basic restrictions:
  - Writer should not enter execution/control lane.
  - Untrusted/third-party agents should default to inspection lane.
  - Data Gate / Permission Policy / Signal Verifier are control or verification lane.
  - Tool executor should not write final synthesis directly.

runtime/swarm/social_immunity.py
- Add contamination/quarantine logic for prompt injection, unsafe external content, raw secret-like text, fake evidence, and unsupported claims.
- Add a sanitizer helper or hook if a sanitizer abstraction already exists.
- Contaminated content must not enter Writer or Evidence Graph directly.
- Add secret-redaction checks consistent with existing pheromone_store/audit behavior.

runtime/swarm/trust_badge.py
- Implement trust levels:
  - core_system
  - trusted_first_party
  - user_installed
  - third_party_untrusted
  - external_content
- Map agents/tools/capabilities to trust levels using manifest metadata where possible.
- Enforce:
  - external_content cannot emit evidence directly
  - third_party_untrusted cannot emit blocking signals
  - user_installed agents emit unverified signals by default
  - only core_system / Data Gate / Permission Policy / Signal Verifier can create hard blocking facts

runtime/swarm/policing.py
- Detect protocol violations:
  - agent emits verified signal directly
  - agent emits blocking without permission
  - writer violates committed candidate
  - agent references its own unverified claim as evidence
  - agent repeatedly conflicts with Data Gate
  - raw WRDS data leaks toward final output
  - arbitrary web_search is attempted in WRDS-only mode
- Emit policing signals.
- Update diagnostics and optionally profile penalties if existing AgentProfile supports it.

runtime/swarm/homeostasis.py
- Compute global swarm state variables:
  - token_heat
  - latency_pressure
  - evidence_coverage
  - risk_pressure
  - verification_backlog
  - tool_failure_rate
  - crowding
- Emit homeostasis signals and recommendations.
- Keep this deterministic and explainable.

runtime/swarm/maturity.py
- Add maturity levels:
  - observer
  - worker
  - specialist
  - verifier
  - blocker
- Use Agent Profile / manifest metadata where possible.
- New or untrusted agents should start at observer or worker.
- Promotion criteria should be deterministic:
  - verified_signal_count
  - rejected_signal_rate
  - constraint_violation_count
  - accepted_quorum_participation
- Do not allow maturity to promote agents into hard-blocking authority without system-level trust.

runtime/swarm/independent_scout.py
- Adjust quorum support by source independence.
- Penalize correlated support from the same source, same evidence_ref, same agent family, same prompt trace, or same unverified claim.
- Add independence metadata to quorum_trace.
- Do not replace existing quorum.py; integrate carefully.

runtime/swarm/artifact_cues.py
- Extract artifact_cue signals from:
  - data_contract
  - metric_registry
  - data_gate
  - research_brief
  - quant_analysis
  - committee_decision
  - review
  - final
- Examples:
  - unsupported recommendation node
  - missing metric
  - unresolved risk
  - final answer missing caveat
  - evidence graph gap if an evidence graph exists

Phase 3 - Integrate into graph/runtime state
- Add new swarm output fields to runtime/state.py only if needed.
- Prefer grouping under existing swarm_metrics, pheromone_trace, agent_allocation_trace, agent_signal_diagnostics, and quorum_trace instead of creating too many top-level fields.
- Integrate the new modules at safe points:
  - after PatrollerGate
  - after Data Gate
  - after committee agent outputs
  - before quorum decision
  - before writer
  - before final_judge
- Do not create circular dependencies.
- Do not let these modules call external APIs.
- Do not expose secrets in traces.

Phase 4 - API and Dashboard
- Extend /agents/run response with summarized outputs from:
  - encounter_rate
  - bottleneck
  - arousal
  - lane_assignment
  - quarantine/contamination
  - policing
  - homeostasis
  - maturity
  - independence
  - artifact_cue
- Extend /platform/swarm endpoints if useful, but avoid breaking existing endpoints.
- Update Dashboard Swarm Governance panel to show:
  - protocol diagnostics
  - active bottlenecks
  - contamination/quarantine warnings
  - lane assignments
  - policing events
  - independent scout score
  - homeostasis summary
- Keep frontend simple: tables / collapsible sections are enough.

Phase 5 - Tests
Add tests for the new protocol modules. At minimum:
- test_encounter_rate_counts_recent_verified_and_failed_events
- test_bottleneck_recruits_verifier_when_unverified_evidence_backlog_high
- test_arousal_increases_when_stop_signal_and_low_evidence_coverage_exist
- test_lane_scheduler_blocks_writer_from_execution_lane
- test_social_immunity_quarantines_prompt_injection_like_content
- test_trust_badge_prevents_third_party_blocking_signal
- test_policing_rejects_agent_direct_verified_signal
- test_policing_detects_writer_violation_of_committed_candidate
- test_homeostasis_reports_risk_and_verification_backlog
- test_maturity_does_not_promote_untrusted_agent_to_blocker
- test_independent_scout_penalizes_correlated_quorum_support
- test_artifact_cues_detect_missing_caveat_or_unsupported_recommendation

Also run existing tests to ensure no regression.

Engineering constraints:
- Preserve backward compatibility.
- Keep deterministic modules deterministic.
- Do not let LLM agents directly mark signals as verified or blocking.
- Do not let Writer bypass Data Gate, Stop-Signal, or committed quorum candidate.
- Do not let tools bypass Tool Registry.
- Do not let agent code access secrets directly.
- Do not introduce heavy dependencies unless absolutely necessary.
- Prefer small, typed, testable functions.
- Use existing Pydantic/dataclass conventions in the repo.
- Keep all new logs redacted.
- If a module cannot be fully integrated safely, implement it as diagnostics-only first and document the integration point.

Definition of done:
- New protocol modules exist under runtime/swarm.
- Existing PheroOS behavior still works.
- Data Gate stop_signal behavior still blocks formal valuation/report publication correctly.
- WRDS-only web_search blocking still works.
- Writer still cannot bypass committed candidate or stop_signals.
- New protocol diagnostics are returned in /agents/run or existing swarm trace fields.
- Dashboard shows the new diagnostics without breaking existing UI.
- Tests pass.
- Add or update docs explaining the insect-inspired mapping:
  - encounter rate = local feedback activation
  - tremble dance = bottleneck recruitment
  - shaking/arousal = verification intensity
  - lane formation = traffic control
  - social immunity = contamination/quarantine
  - nestmate recognition = trust badges
  - worker policing = protocol violation control
  - independent scouts = anti-correlated quorum
  - homeostasis = global swarm stability
  - maturity lifecycle = staged agent authority

Output expected:
- Implement code changes.
- Add tests.
- Run tests.
- Provide a final concise summary:
  1. files changed
  2. new modules added
  3. new protocol behavior
  4. tests run and results
  5. any incomplete items or safe follow-up tasks
