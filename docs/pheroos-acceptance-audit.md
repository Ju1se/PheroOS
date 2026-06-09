可以。下面这份是**可直接粘贴给 Codex Peruse / Review / Custom Review Instructions** 的验收审计 prompt。它的定位不是让 Codex 改代码，而是让 Codex **只读审计、验收实现质量、指出阻塞问题、给出文件级证据和测试建议**。Codex 官方文档里 `/review` 支持自定义 review instructions，AGENTS.md 也可以放 repo-specific review guidance，所以这份 prompt 既可以直接用于一次性 review，也可以拆成 `code_review.md` 后在 `AGENTS.md` 中引用。([OpenAI开发者][1])

你的项目当前核心规则包括：OS Kernel 只做控制平面、Agent 不接触 secret、工具调用必须经过 Tool Registry、投资分析默认不使用 web_search、WRDS raw data 不能直接进入 final report、Data Gate 决定是否允许正式估值结论、Writer 不能绕过 Data Gate 编造事实。 下面的验收清单就是围绕这些硬约束，以及 PheroOS typed pheromone field、Stop-Signal、Signal Verifier、Response Threshold、Quorum、PatrollerGate、Trace/Dashboard 暴露等机制设计的。

---

```text
# PheroOS Swarm Governance Acceptance Audit
# Codex Peruse / Review Mode Prompt
# Mode: READ-ONLY REVIEW. Do not modify files.

You are reviewing a multi-agent AI-as-OS project called PheroOS / Swarm Governance.

Your job is NOT to implement fixes. Your job is to perform a deep technical acceptance audit of the current repository and report whether the implementation satisfies the intended architecture, safety boundaries, data-governance rules, and software engineering design principles.

You must inspect the actual code, not only docs or comments. For every finding, cite exact files, functions/classes, and line ranges when possible. Prefer concrete evidence over broad opinions.

============================================================
0. SYSTEM CONTEXT
============================================================

The project is intended to be an AI-as-OS Agent Committee Platform.

Expected high-level architecture:

- app/main.py
- app/routes/agents.py
- app/routes/platform.py
- runtime/os_kernel.py
- runtime/runtime_context.py
- runtime/graph.py
- runtime/capability_registry.py
- runtime/agent_registry.py
- runtime/connection_control.py
- runtime/secret_store.py
- runtime/permission_policy.py
- runtime/data_gate.py
- runtime/audit_log.py
- runtime/llm.py or model gateway equivalent
- runtime/swarm/*
- tools/wrds_tools.py
- capabilities/*/capability.json
- capabilities/value-investing-research/agents/*.json
- static/index.html
- static/app.js
- static/styles.css
- tests/*

The core product goal is:

PheroOS should not be a normal multi-agent chat workflow. It should be a swarm-governed multi-agent operating layer where agents emit structured signals, the system verifies those signals, and only verified / permitted / quorum-approved conclusions can reach final output.

Expected conceptual flow:

User task
→ OS Kernel plan
→ Capability / Agent Registry resolution
→ RuntimeContext materialization
→ Swarm Governance Layer
→ LangGraph Runtime
→ PatrollerGate
→ Tools / Data Gate / Committee Agents
→ Signal Verifier
→ Stop-Signal Gate
→ Quorum
→ Writer constrained by committed candidate
→ Final Judge
→ Final Output + Audit Trace

============================================================
1. ABSOLUTE REVIEW RULES
============================================================

- Do not modify code.
- Do not run destructive commands.
- Do not access external credentials.
- Do not print or expose secrets.
- Do not treat comments as proof of implementation.
- Verify behavior through code paths, tests, and route outputs.
- If a requirement is only partially implemented, mark it PARTIAL.
- If implementation exists but is not enforced, mark it FAIL.
- If enforcement depends only on prompt wording, mark it FAIL unless there is deterministic guard logic.
- If a safety rule is documented but not tested, mark it RISK.
- If a safety rule is tested but can be bypassed through another route, mark it FAIL.
- Distinguish:
  - PASS: implemented, enforced, tested or clearly testable
  - PARTIAL: present but incomplete or weakly integrated
  - FAIL: absent, bypassable, or only documented
  - RISK: technically works but design is fragile
  - N/A: not applicable to current scope

============================================================
2. OUTPUT FORMAT
============================================================

Return the review in this structure:

1. Executive Verdict
   - Overall status: PASS / PARTIAL / FAIL
   - Highest-risk issue in one sentence
   - Whether this is ready for demo, research prototype, or production-like usage

2. P0 Blockers
   - Security, data leakage, fabricated data, bypass of Data Gate, bypass of Tool Registry, or false final conclusions.
   - Each item:
     - Severity: P0
     - Finding
     - Evidence: file/function/line
     - Why it matters
     - Minimal fix direction
     - Suggested test

3. P1 Major Issues
   - Architectural drift, missing enforcement, fragile coupling, missing auditability, incomplete quorum/stop-signal behavior.

4. P2 Improvements
   - Refactors, naming, cohesion, test coverage, observability, dashboard UX.

5. Acceptance Checklist
   - Use the checklist sections below.
   - Mark each item PASS / PARTIAL / FAIL / RISK / N/A.

6. Regression Tests To Add
   - Provide concrete test names and short test descriptions.

7. Final Go/No-Go Recommendation
   - Give a direct decision:
     - GO for local demo
     - GO for research prototype
     - NO-GO until P0 fixed
     - NO-GO for production

============================================================
3. ARCHITECTURE ACCEPTANCE CHECKLIST
============================================================

Review whether the code preserves the intended AI-as-OS separation of concerns.

[ ] OS Kernel remains a control-plane component.
    It should plan capabilities, agents, route, and runtime needs.
    It must not perform company analysis, final investment reasoning, direct tool execution, or raw model calls.

[ ] Capability Registry owns capability discovery.
    capabilities/*/capability.json should be the extension boundary.
    Capability loading should not leak implementation details into OS Kernel.

[ ] Agent Registry owns agent manifest discovery.
    agents/*.json or capability agent manifests should be loaded consistently.
    Agent swarm metadata should be parsed centrally, not ad hoc in random nodes.

[ ] RuntimeContext is the hot materialization boundary.
    RuntimeContext should assemble tenant-scoped active connections, tools, model gateway, policies, and swarm managers.
    It should not contain business logic that belongs in Data Gate, Tool Registry, or Swarm Governance.

[ ] LangGraph Runtime orchestrates workflow but does not bypass governance.
    runtime/graph.py should call PatrollerGate, Data Gate, Stop-Signal checks, Signal Verifier, Quorum, Writer guardrails, and Final Judge in the right order.

[ ] Tool Registry is the only tool execution path.
    Agents must not directly call WRDS, web_search, shell, filesystem, database, email, or model provider APIs.

[ ] Model Gateway is the only runtime model-call path.
    Agents and runtime nodes should not directly instantiate OpenAI / GLM / MiniMax / Ollama / LM Studio clients except through the gateway abstraction.

[ ] Data Gate remains the formal valuation authority.
    No formal Buy/Sell/target-price/undervalued conclusion should appear if Data Gate forbids formal valuation.

[ ] Writer only expresses approved conclusions.
    Writer must not create new facts, bypass committed quorum candidate, override Data Gate, or remove required caveats.

[ ] Final Judge checks governance consistency, not just writing quality.
    It should check Data Gate, Stop-Signal, committed candidate, raw-data leakage, and unsupported claim risks.

============================================================
4. SWARM GOVERNANCE / PHEROOS CHECKLIST
============================================================

The intended PheroOS layer is a typed signal field, not generic memory.

[ ] PheromoneSignal model exists and is strongly structured.
    Required fields should include type, target, content, strength, confidence, decay_rate, priority, scope, verification_state, source_agent/source_module, evidence_ref, blocking, metadata or equivalent.

[ ] Signal types are explicit.
    Existing signal types should include at least:
    constraint, permission, evidence, data_contract, progress, risk, negative, demand, quorum, capability, tool_health, model_route, crowding, stop_signal.

[ ] Newly added protocol signal types are supported or safely extensible.
    Check for:
    encounter_rate, bottleneck, arousal, lane_assignment, contamination, quarantine, trust_badge, policing, homeostasis, maturity, independence, artifact_cue.

[ ] Signal verification states are enforced.
    unverified / verified / contested / rejected / blocking must not be cosmetic.
    Code must prevent unverified signals from becoming final facts.

[ ] PheromoneFieldManager handles signal lifecycle.
    It should support add/update, deduplication, reinforce, decay, snapshot, trace, blocking target extraction, stop-signal extraction, and constraint extraction.

[ ] Signal updates write back to AgentState.
    Expected state fields include:
    pheromone_field_snapshot,
    pheromone_trace,
    stop_signals,
    constraint_signals,
    quorum_trace,
    agent_allocation_trace,
    agent_signal_diagnostics,
    agent_signal_verification_trace,
    patroller_report,
    swarm_metrics.

[ ] Signal extraction from agent output is sanitized.
    Agent-emitted JSON signals should be schema-checked, permission-checked, and source-tagged.

[ ] Agent-emitted signals are not trusted by default.
    Agent proposals should enter as unverified or contested unless produced by system authority.

[ ] Signal Verifier deterministically promotes contested signals.
    Red Team / Risk Manager stop-signal proposals should only become verified blocking signals when supported by Data Gate, Critic, or existing system stop-signal evidence.

[ ] Stop-Signal is enforced, not just displayed.
    It must block tools, Writer claims, and final output where appropriate.

[ ] Stop-Signal cannot be bypassed by alternative target names.
    Audit target canonicalization:
    formal_valuation vs valuation vs decision:formal_valuation etc.

[ ] Data Gate signals are created correctly.
    Data Gate failure should produce stop_signal:data_gate.
    Formal valuation disallow should produce stop_signal:formal_valuation.
    Report publication disallow should produce stop_signal:report_publication.
    Data gaps and evidence gaps should produce risk signals.

[ ] Quorum is candidate-based.
    Committee output should converge into explicit candidates such as Buy, Watch, Avoid, Sell, Insufficient Data.

[ ] Quorum respects blocking signals.
    If formal_valuation/report_publication/data_gate is blocking, Buy/Watch/Sell/target-price candidates must be blocked or downgraded.

[ ] Quorum forced Insufficient Data behavior is correct.
    When Data Gate blocks formal valuation, Insufficient Data should be the committed candidate unless there is a clearly approved safe alternative.

[ ] Response Threshold activation works.
    Data gaps should increase Data Auditor demand.
    Formal valuation blocking should increase Risk / Red Team demand.
    Low market data should suppress Market Execution if applicable.
    User-selected agents should receive explicit priority without bypassing safety.

[ ] Agent allocation trace is explainable.
    The trace should explain why each agent was activated, suppressed, or force-included.

[ ] Agent Profile updates are safe.
    Profile learning should track reliability/thresholds, not memorize investment conclusions or company-specific claims across runs.

[ ] PatrollerGate runs before expensive or risky workflow nodes.
    It should check WRDS-only readiness, model provider availability, capability enablement, OS plan readiness, and blocking configuration gaps.

[ ] If PatrollerGate blocks, downstream committee should not fabricate an analysis.
    The system should produce defect memo or degraded output.

============================================================
5. NEW INSECT-INSPIRED PROTOCOL ACCEPTANCE CHECKLIST
============================================================

Audit whether the newly planned protocol primitives are implemented in a safe, deterministic, non-invasive way.

5.1 Encounter-Rate Controller

[ ] runtime/swarm/encounter_rate.py exists or equivalent logic exists.
[ ] It computes recent local feedback rates from signals/events.
[ ] It considers verified successes, rejected signals, blocked actions, tool failures, verifier promotions.
[ ] It emits encounter_rate diagnostics/signals.
[ ] It does not make high-risk autonomous decisions without governance.

5.2 Bottleneck Recruitment / Tremble-Dance Protocol

[ ] runtime/swarm/bottleneck_recruitment.py exists or equivalent logic exists.
[ ] It detects unverified evidence backlog, unresolved risk backlog, pending tool results, writer/final_judge bottlenecks.
[ ] It recommends receiver agents: Data Auditor, Evidence Verifier, Risk Manager, Red Team, Writer, Final Judge.
[ ] It emits bottleneck signals.
[ ] It does not create endless agent loops.

5.3 Arousal / Verification-Intensity Controller

[ ] runtime/swarm/arousal.py exists or equivalent logic exists.
[ ] It detects high-risk states:
    formal valuation,
    report publication,
    high-risk permissions,
    conflicting quorum,
    low evidence coverage,
    active stop-signals.
[ ] It emits arousal signals or policy recommendations.
[ ] It can raise quorum threshold, lower writer temperature, or increase verifier strictness through controlled policy hooks.
[ ] It does not call external model APIs directly.

5.4 Lane Scheduler / Traffic-Lane Protocol

[ ] runtime/swarm/lane_scheduler.py exists or equivalent logic exists.
[ ] It defines lanes:
    inspection, execution, verification, synthesis, control.
[ ] Writer is blocked from execution/control lane.
[ ] Tool executor cannot directly write final synthesis.
[ ] Untrusted/third-party agents default to inspection lane.
[ ] Data Gate / Permission Policy / Signal Verifier are verification/control lane.
[ ] Lane assignment appears in trace or diagnostics.

5.5 Social Immunity / Quarantine

[ ] runtime/swarm/social_immunity.py exists or equivalent logic exists.
[ ] It detects prompt injection-like text, unsafe external content, secret-like data, fake evidence, unsupported claims.
[ ] It emits contamination/quarantine signals.
[ ] Contaminated content cannot enter Writer or Evidence Graph directly.
[ ] Sanitization/redaction is consistent with audit log and pheromone store.
[ ] External web/user documents are treated as untrusted input.

5.6 Trust Badge / Nestmate Recognition

[ ] runtime/swarm/trust_badge.py exists or equivalent logic exists.
[ ] Trust levels exist:
    core_system,
    trusted_first_party,
    user_installed,
    third_party_untrusted,
    external_content.
[ ] Only core system / Data Gate / Permission Policy / Signal Verifier can create hard blocking facts.
[ ] Third-party untrusted agents cannot emit blocking signals.
[ ] External content cannot directly emit evidence.
[ ] Trust metadata is integrated with agent/capability manifests or default policy.

5.7 Worker Policing / Protocol Violation Control

[ ] runtime/swarm/policing.py exists or equivalent logic exists.
[ ] It detects:
    agent emits verified signal directly,
    agent emits blocking without permission,
    writer violates committed candidate,
    agent references own unverified claim as evidence,
    repeated conflict with Data Gate,
    raw WRDS data leak toward final output,
    web_search attempted in WRDS-only mode.
[ ] It emits policing signals.
[ ] It updates diagnostics and optionally profile penalties.
[ ] It cannot be bypassed by changing output wording.

5.8 Homeostasis Controller

[ ] runtime/swarm/homeostasis.py exists or equivalent logic exists.
[ ] It computes:
    token_heat,
    latency_pressure,
    evidence_coverage,
    risk_pressure,
    verification_backlog,
    tool_failure_rate,
    crowding.
[ ] It emits homeostasis signals and recommendations.
[ ] It is deterministic and explainable.
[ ] It does not silently suppress required safety agents.

5.9 Agent Maturity Lifecycle

[ ] runtime/swarm/maturity.py exists or equivalent logic exists.
[ ] Maturity levels exist:
    observer,
    worker,
    specialist,
    verifier,
    blocker.
[ ] New/untrusted agents start at observer or worker.
[ ] Promotion criteria are deterministic:
    verified_signal_count,
    rejected_signal_rate,
    constraint_violation_count,
    accepted_quorum_participation.
[ ] Maturity does not override system trust boundaries.

5.10 Independent Scout Quorum

[ ] runtime/swarm/independent_scout.py exists or equivalent logic exists.
[ ] Quorum support is adjusted by source independence.
[ ] Correlated support is penalized when from same evidence_ref, same source, same agent family, same prompt trace, or same unverified claim.
[ ] independence metadata appears in quorum_trace.
[ ] Correlated hallucinated consensus is not treated as strong quorum.

5.11 Artifact Cue Extraction

[ ] runtime/swarm/artifact_cues.py exists or equivalent logic exists.
[ ] It extracts artifact_cue signals from:
    data_contract,
    metric_registry,
    data_gate,
    research_brief,
    quant_analysis,
    committee_decision,
    review,
    final.
[ ] It detects:
    unsupported recommendation,
    missing metric,
    unresolved risk,
    final answer missing caveat,
    evidence gap.
[ ] Artifact cues influence diagnostics or guardrails without creating fake evidence.

============================================================
6. SECURITY AND DATA LEAKAGE AUDIT
============================================================

This section is critical. Treat any failure here as P0 unless clearly isolated.

[ ] Secrets never reach agents.
    Search for direct access to .local/secrets.json, secret_store internals, API keys, passwords, WRDS credentials, model provider keys inside agent prompts, agent state, logs, or frontend responses.

[ ] Secret redaction is applied before logs.
    Check logs/agent_runs.jsonl, logs/swarm_events.jsonl, logs/pheromone_signals.jsonl, audit_log, dashboard responses.

[ ] Secret-like fields are redacted recursively.
    Keys matching token, api_key, password, secret, credential, wrds, bearer, authorization must be redacted inside nested dict/list payloads.

[ ] Frontend never receives raw secrets.
    /platform/connections, /agents/run, /platform/swarm/* must not return credentials.

[ ] Agents never access SecretStore directly.
    Only Connection Control / RuntimeContext / Tool Registry should use secrets.

[ ] Raw WRDS data does not enter final report.
    Check Writer input, final output, trace, dashboard, and review artifacts.

[ ] Data summaries are safe.
    Raw table dumps, excessive row-level data, and unredacted identifiers should not be included in final output.

[ ] Logs do not contain raw WRDS credentials, model provider keys, or raw secrets.

[ ] Prompt injection from external content is quarantined.
    External content should not be able to instruct agents to ignore policies, reveal secrets, bypass Data Gate, or modify tool routing.

[ ] Dangerous permissions require confirmation.
    filesystem:write, shell:execute, network:arbitrary, email:send, trade:execute, database:write, credential:export must not be auto-allowed.

[ ] Arbitrary network access is blocked unless explicitly approved.
    WRDS-only mode must not allow web_search.

[ ] Tool results are sanitized before entering prompts.
    Tool output should be treated as data, not instructions.

[ ] Dashboard trace is safe to share.
    It should expose reasoning state and audit events without exposing secrets or raw sensitive data.

============================================================
7. INTERFACE MISUSE AUDIT
============================================================

Look for incorrect boundary usage and architectural violations.

[ ] Model providers are only called through runtime/llm.py or model gateway.
    Search for direct imports / clients:
    openai,
    zhipu,
    minimax,
    anthropic,
    ollama,
    requests to provider endpoints,
    httpx calls to model APIs.

[ ] Tools are only called through Tool Registry.
    Search for direct calls to WRDS tools, web_search, filesystem, shell, database, email, trade APIs outside approved execution layer.

[ ] Data Gate is not bypassed.
    Search for Writer/Committee/Final Judge making formal valuation decisions without referencing data_gate result.

[ ] Permission Policy is consulted before high-risk actions.
    Check all high-risk actions have policy checks.

[ ] RuntimeContext is not used as a global mutable dumping ground.
    It should be a dependency container, not a place for hidden business logic.

[ ] Agent manifests are loaded through Agent Registry.
    No direct hardcoded agent list should bypass registry except tests/fixtures.

[ ] Capability manifests are loaded through Capability Registry.
    No capability-specific special casing should leak into unrelated modules unless justified.

[ ] app/routes/* do not contain business logic that belongs in runtime.
    Routes should validate inputs, call runtime services, and shape responses.

[ ] static/app.js does not implement server-side policy decisions.
    Frontend may display state but must not be trusted for enforcement.

[ ] Pheromone signals are not constructed inconsistently.
    Search for raw dicts where typed constructors should be used.
    Ensure target names and signal types are canonical.

[ ] API response schemas are stable.
    /agents/run should continue returning old fields while adding new swarm diagnostics.

============================================================
8. FABRICATED DATA / HALLUCINATION AUDIT
============================================================

Treat fabricated financial data, unsupported evidence, or fake system state as P0/P1 depending on reachability.

[ ] No fake WRDS data is generated when WRDS fails.
    Missing data should produce degraded output, defect memo, or Insufficient Data.

[ ] No fabricated metric registry values.
    Metric values should come from deterministic tools, WRDS, or clearly labeled derived calculations.

[ ] No fake citations or fake evidence_refs.
    evidence_ref must point to actual tool output, data_contract, metric_registry, research_brief, or verified artifact.

[ ] Agent claims are not automatically treated as evidence.
    Agent outputs are proposals unless verified.

[ ] Writer cannot invent evidence.
    Writer should consume verified evidence, committed candidate, unresolved risks, and caveats.

[ ] Final answer cannot silently upgrade uncertainty.
    “Insufficient data” must not become “Buy”, “undervalued”, “target price”, or “strong recommendation.”

[ ] Numeric calculations are traceable.
    Derived metrics should show source fields or deterministic calculation path.

[ ] Deterministic research / quant modules do not use placeholders as real facts.
    Search for TODO, mock, sample, dummy, fallback hardcoded financial values.

[ ] Tests include negative cases for missing data.
    Data Gate failure should be tested.

[ ] Quorum cannot be won by repeated correlated unsupported claims.
    Independent-scout or equivalent source-diversity logic should penalize echo chambers.

============================================================
9. DATA GATE / INVESTMENT-SPECIFIC ACCEPTANCE
============================================================

[ ] Data Gate determines formal valuation allowance.
[ ] Data Gate failure emits stop_signal:data_gate.
[ ] Formal valuation disallow emits stop_signal:formal_valuation.
[ ] Report publication disallow emits stop_signal:report_publication.
[ ] Missing data emits risk signals.
[ ] Evidence gaps emit risk signals.
[ ] Writer receives Data Gate constraints.
[ ] Writer output is blocked or rewritten when Data Gate blocks formal valuation.
[ ] Final Judge detects any Data Gate bypass.
[ ] Quorum blocks Buy/Watch/Sell/target-price when formal valuation is blocked.
[ ] Insufficient Data candidate is committed when required.
[ ] WRDS-only path blocks web_search.
[ ] WRDS raw data does not appear in final.
[ ] Data Gate state appears in audit trace and dashboard.
[ ] Tests cover at least:
    - data_gate blocks formal valuation
    - writer cannot bypass formal valuation stop-signal
    - quorum forces insufficient data
    - web_search blocked in WRDS-only mode
    - final judge rejects unsupported valuation conclusion

============================================================
10. API ACCEPTANCE CHECKLIST
============================================================

Audit endpoint correctness, consistency, and security.

Required existing endpoints:

[ ] GET /health
[ ] GET /
[ ] POST /agents/run
[ ] GET /skills
[ ] GET /skills/{name}
[ ] GET /tools
[ ] GET /wrds/status
[ ] POST /wrds/query
[ ] POST /wrds/company/financials
[ ] POST /platform/connections/infer
[ ] POST /platform/connections/confirm
[ ] GET /platform/connections
[ ] POST /platform/connections/{id}/test
[ ] POST /platform/connections/{id}/discover
[ ] GET /platform/capability-catalog
[ ] GET /platform/capabilities
[ ] GET /platform/capabilities/active
[ ] POST /platform/capabilities/resolve
[ ] POST /platform/capabilities/enable
[ ] POST /platform/capabilities/{id}/disable
[ ] GET /platform/agents
[ ] POST /platform/os/plan
[ ] GET /platform/swarm/signals
[ ] GET /platform/swarm/events
[ ] GET /platform/swarm/agent-profiles

For each endpoint, check:

[ ] Input validation exists.
[ ] Tenant scoping is respected where applicable.
[ ] Secrets are redacted.
[ ] Error responses do not leak stack traces or credentials.
[ ] Endpoint does not enforce policy only on frontend.
[ ] Long-running agent run behavior is safe.
[ ] Response does not include raw WRDS data unless endpoint is explicitly raw-data endpoint and protected.
[ ] Swarm diagnostic fields are present and stable where expected.
[ ] Backward compatibility of /agents/run fields is preserved.

Expected /agents/run fields include old and swarm fields:

Old/main fields:
run_id,
task,
orchestration,
route,
wrds_result,
data_contract,
metric_registry,
data_gate,
research_brief,
quant_analysis,
committee_outputs,
discussion_transcript,
committee_decision,
review,
draft_final,
final,
agent_metrics,
run_status,
degraded_reasons.

Swarm fields:
pheromone_field_snapshot,
pheromone_trace,
stop_signals,
constraint_signals,
quorum_trace,
agent_allocation_trace,
agent_signal_diagnostics,
agent_signal_verification_trace,
patroller_report,
swarm_metrics.

============================================================
11. OBSERVABILITY / AUDITABILITY CHECKLIST
============================================================

[ ] Every run has run_id.
[ ] Every signal has run_id and tenant_id or equivalent scope.
[ ] Every signal has source_agent or source_module.
[ ] Every blocking action has trace evidence.
[ ] Every rejected agent signal records reason.
[ ] Every promoted signal records source support.
[ ] Every committed quorum candidate records supporting and blocking signals.
[ ] Every Writer guardrail intervention is recorded.
[ ] Every Final Judge correction is recorded.
[ ] Audit logs are append-only or at least not silently overwritten.
[ ] Logs are redacted.
[ ] Dashboard can show:
    signal count,
    stop-signal count,
    blocking count,
    Patroller status,
    quorum committed candidate,
    active constraints,
    active stop-signals,
    agent signal accepted/rejected diagnostics,
    verifier promoted signals,
    protocol diagnostics if implemented.
[ ] Trace can answer:
    Why was this agent activated?
    Why was this candidate committed?
    Why was this action blocked?
    Which evidence supported the final answer?
    Which risks remained unresolved?
    Which signals were rejected?

============================================================
12. SOFTWARE ENGINEERING DESIGN CHECKLIST
============================================================

12.1 High Cohesion

[ ] runtime/swarm modules each have a single clear responsibility.
[ ] stop_signal.py handles stop-signal policy, not unrelated quorum or UI logic.
[ ] quorum.py handles candidate commitment, not secret handling or frontend formatting.
[ ] signal_extractor.py parses/validates agent signals, not business decisions.
[ ] data_gate.py handles data sufficiency, not writer formatting.
[ ] permission_policy.py handles permission classification, not tool execution.
[ ] graph.py orchestrates, but does not become a giant policy dumping ground.
[ ] app/routes/* do HTTP concerns, not core policy logic.

12.2 Low Coupling

[ ] Swarm modules depend on typed state/models, not raw FastAPI request objects.
[ ] UI does not import runtime internals.
[ ] Runtime does not depend on static frontend code.
[ ] Capability plugins interact through registries and manifests.
[ ] Tool providers are behind Tool Registry.
[ ] Model providers are behind Model Gateway.
[ ] SecretStore is only used by approved runtime/control-plane modules.
[ ] Data Gate output is consumed through explicit result object, not string matching.

12.3 Dependency Direction

Expected dependency direction:

app/routes → runtime services
runtime/graph → runtime modules
runtime/swarm → state/models/policies
tools → external provider clients
capabilities → manifests/adapters/tools
static → API only

Flag violations where lower-level modules import app/routes or frontend code.

12.4 Interface Stability

[ ] Public API schemas are stable.
[ ] PheromoneSignal schema is backward compatible.
[ ] Agent manifest swarm fields have defaults.
[ ] Missing optional fields do not crash runtime.
[ ] Capability manifest schema changes are versioned or tolerant.
[ ] Tests cover old capabilities without new swarm metadata.

12.5 Error Handling

[ ] Tool failures become risk/negative/tool_health signals.
[ ] Missing WRDS becomes PatrollerGate/Data Gate issue, not crash.
[ ] Missing model provider produces degraded output or setup instruction.
[ ] Invalid agent-emitted JSON is rejected with diagnostics.
[ ] Invalid signal type is rejected or mapped safely.
[ ] Dashboard handles missing swarm fields gracefully.
[ ] No broad except clauses silently swallow governance failures.

12.6 Testability

[ ] Deterministic swarm modules have unit tests.
[ ] Graph integration has e2e tests for safety-critical paths.
[ ] Test fixtures do not contain real secrets.
[ ] Tests cover negative cases, not only happy paths.
[ ] Tests can run offline except explicitly marked integration tests.
[ ] External network tests are mocked or skipped unless credentials are configured.

12.7 Maintainability

[ ] Naming is consistent:
    DataGate, StopSignal, PheromoneSignal, Quorum, PatrollerGate, SignalVerifier.
[ ] Target names are canonicalized.
[ ] Magic strings are centralized.
[ ] Policy thresholds are configurable or documented.
[ ] No duplicated redaction logic with inconsistent behavior.
[ ] No duplicated permission lists with drift risk.
[ ] No hardcoded company-specific assumptions in generic runtime.
[ ] No large monolithic functions in runtime/graph.py that should be extracted.

============================================================
13. TEST ACCEPTANCE CHECKLIST
============================================================

Look for existing tests or recommend new ones.

Critical tests that should exist:

[ ] test_writer_cannot_bypass_formal_valuation_stop_signal
[ ] test_web_search_blocked_in_wrds_only_mode
[ ] test_agent_stop_signal_remains_contested_without_system_support
[ ] test_data_gate_stop_signal_promotes_to_blocking
[ ] test_quorum_forces_insufficient_data_when_formal_valuation_blocked
[ ] test_blocking_signal_can_be_resolved_after_data_gate_recheck if resolution exists
[ ] test_dynamic_committee_activates_data_auditor_on_data_gap
[ ] test_writer_uses_only_verified_evidence
[ ] test_event_log_reconstructs_pheromone_snapshot if event sourcing exists
[ ] test_signal_redaction_removes_secret_like_values
[ ] test_tool_registry_required_for_wrds_and_web_search
[ ] test_model_gateway_required_for_runtime_llm_calls
[ ] test_agent_cannot_emit_verified_signal_directly
[ ] test_third_party_agent_cannot_emit_blocking_signal
[ ] test_prompt_injection_content_quarantined
[ ] test_raw_wrds_data_not_in_final_or_dashboard
[ ] test_independent_scout_penalizes_correlated_quorum_support if implemented
[ ] test_lane_scheduler_blocks_writer_from_execution_lane if implemented
[ ] test_policing_detects_writer_violation_of_committed_candidate if implemented
[ ] test_homeostasis_reports_risk_and_verification_backlog if implemented
[ ] test_bottleneck_recruits_verifier_when_unverified_evidence_backlog_high if implemented

Run or identify the intended test command:
- pytest
- pytest tests/
- any project-specific test command in README / pyproject / package scripts

If tests cannot be run, say exactly why.

============================================================
14. STATIC SEARCHES TO PERFORM
============================================================

Perform these searches and report suspicious hits:

Secrets / leakage:
- api_key
- token
- password
- secret
- credential
- authorization
- bearer
- wrds
- .local/secrets
- secret_store
- print(
- logger.
- json.dump
- json.dumps

Interface misuse:
- openai
- zhipu
- minimax
- anthropic
- ollama
- requests.
- httpx.
- subprocess
- os.system
- shell
- web_search
- wrds
- ToolRegistry
- model_gateway
- runtime/llm

Fabricated data:
- mock
- dummy
- sample
- fake
- placeholder
- TODO
- hardcoded
- fallback
- estimated
- assumed
- synthetic

Governance bypass:
- formal_valuation
- target price
- undervalued
- Buy
- Sell
- recommendation
- data_gate
- stop_signal
- blocking
- committed_candidate
- final
- writer
- final_judge

Target drift:
- valuation
- formal valuation
- formal_valuation
- decision:formal_valuation
- report_publication
- report publication
- data_gate
- tool:web_search
- web_search

============================================================
15. SEVERITY RUBRIC
============================================================

P0 Blocker:
- Secret leakage to agent, logs, frontend, or final output.
- Raw WRDS data leakage into final output.
- Writer can bypass Data Gate.
- web_search can run in WRDS-only mode.
- Tool Registry can be bypassed.
- Model Gateway can be bypassed.
- Agent can directly mark fabricated/unsupported claim as verified.
- Final answer can contain formal valuation when Data Gate forbids it.
- High-risk permission executes without confirmation.

P1 Major:
- Stop-Signal exists but is not consistently enforced.
- Quorum exists but can be bypassed by Writer or Final Judge.
- Signal Verifier exists but agent-emitted blocking signals can slip through.
- Agent allocation trace missing or misleading.
- Dashboard exposes unsafe data.
- API lacks validation or leaks implementation details.
- Strong coupling makes safety logic fragile.
- Tests missing for safety-critical paths.

P2 Improvement:
- Poor naming, duplicated constants, weak docs, missing minor tests.
- Dashboard UX rough but safe.
- Trace incomplete but not safety-critical.
- Module responsibilities could be cleaner.

============================================================
16. FINAL DECISION CRITERIA
============================================================

Give one final verdict:

- PASS FOR DEMO:
  No P0 issues, P1 issues are manageable and documented.

- PASS FOR RESEARCH PROTOTYPE:
  No P0 issues, core Data Gate / Stop-Signal / Quorum / Trace behavior works, tests cover critical negative cases.

- NO-GO:
  Any P0 issue exists.

- NO-GO FOR PRODUCTION:
  If storage, tenant isolation, secret management, or audit trail is still local/prototype-grade, even if demo is safe.

Be blunt. Do not sugarcoat. The purpose of this review is to catch architecture drift, safety regressions, data leakage, fabricated data, interface misuse, and weak software design before the system is presented as a trustworthy swarm-governed multi-agent OS.
```

---

如果你想把它放进 repo 形成长期规范，我建议新建：

```text
docs/code_review_pheroos.md
```

然后在根目录 `AGENTS.md` 里加：

```text
## Review guidelines

When reviewing this repository, follow docs/code_review_pheroos.md.
Treat Data Gate bypass, secret leakage, Tool Registry bypass, Model Gateway bypass, WRDS raw data leakage, and Writer bypass of committed quorum candidate as P0 issues.
```

这样 Codex 后续每次 review 都能稳定按这套验收标准审计。Codex 文档也明确支持通过 AGENTS.md 提供项目级 review guidance。([OpenAI开发者][2])

[1]: https://developers.openai.com/codex/cli/features?utm_source=chatgpt.com "Codex CLI features"
[2]: https://developers.openai.com/codex/guides/agents-md?utm_source=chatgpt.com "Custom instructions with AGENTS.md – Codex"
