import { expect, test } from "@playwright/test";
import { PNG } from "pngjs";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const artifactDir = path.resolve(process.cwd(), "output/playwright/visual-regression");

test.beforeEach(async ({ page }) => {
  await installApiFixtures(page);
});

test("home compose surface keeps the dark AI-OS visual contract", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.locator("#api-status")).toHaveText("online");
  await expect(page.locator("#os-home")).toBeVisible();
  await expect(page.locator("#composer")).toBeVisible();
  await expect(page.locator("#task-input")).toBeVisible();

  await expectNoHorizontalOverflow(page);
  await expectComposerContract(page);
  await expectNoCriticalOverlap(page, [
    ["#os-home", "#composer"],
    [".app-header", "#composer"],
  ]);
  await expectNonBlankScreenshot(page, `home-${testInfo.project.name}`);
});

test("setup sheet exposes capabilities and selectable agent plugins without layout overflow", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.locator("#setup-button").click();
  await expect(page.locator("#setup-sheet")).toHaveAttribute("aria-hidden", "false");
  await expect(page.locator(".setup-panel")).toBeVisible();
  await expect(page.locator("#active-tenant")).toHaveText("default");
  await page.locator("#tenant-sandbox-button").click();
  await expect(page.locator("#active-tenant")).toContainText("sandbox-");
  await expect(page.locator("#auto-config-result")).toContainText("Fresh sandbox selected");
  await expect(page.locator("#auto-config-input")).toBeVisible();

  await page.locator('[data-setup-tab="agents"]').click();
  await expect(page.locator('#committee-member-list input[data-agent-plugin]')).toHaveCount(11);
  await expect(page.locator("#committee-member-list")).toContainText("Data Auditor");
  await expect(page.locator("#committee-member-list")).toContainText("Red Team");
  await expect(page.locator("#committee-member-list")).toContainText("Domain Workflow Agents");
  await expect(page.locator("#committee-member-list")).toContainText("Repo Scout");
  await expect(page.locator("#committee-member-list")).toContainText("DLP Privacy Auditor");
  await expect(page.locator("#committee-member-list")).toContainText("Citation Auditor");
  await expect(page.locator("#committee-member-list")).toContainText("can block");
  await expect(page.locator("#committee-member-list")).toContainText("Governance Actors");
  await expect(page.locator("#committee-member-list")).toContainText("Quorum Marshal");
  await expect(page.locator("#committee-member-list")).toContainText("Receiver Normalizer");

  await expectNoHorizontalOverflow(page);
  await expectPanelWithinViewport(page, ".setup-panel");
  await expectNonBlankScreenshot(page, `setup-agents-${testInfo.project.name}`);
});

test("run trace renders committee, swarm governance, diagnostics, and verifier promotion", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.locator("#task-input").fill("Analyze AAPL");
  await page.locator("#composer").evaluate((form) => form.requestSubmit());

  await expect(page.locator(".message.assistant .message-content")).toContainText("WATCH");
  await expect(page.locator("#run-label")).toContainText("visual-r");
  await page.locator("#trace-button").click();
  await expect(page.locator("#trace-drawer")).toHaveClass(/open/);
  await expect(page.locator("#value-research-box")).toContainText("WATCH");
  await expect(page.locator("#discussion-box")).toContainText("Data Auditor");
  await expect(page.locator("#swarm-box")).toContainText("PheroOS Governance Field");
  await expect(page.locator("#swarm-box")).toContainText("Decision Debugger");
  await expect(page.locator("#swarm-box")).toContainText("PheroOS Controller");
  await expect(page.locator("#swarm-box")).toContainText("Swarm Governance Caste");
  await expect(page.locator("#swarm-box")).toContainText("Quorum Marshal");
  await expect(page.locator("#swarm-box")).toContainText("Evidence Steward");
  await expect(page.locator("#swarm-box")).toContainText("Why Blocked");
  await expect(page.locator("#swarm-box")).toContainText("Evidence Graph");
  await expect(page.locator("#swarm-box")).toContainText("Tool Events");
  await expect(page.locator("#swarm-box")).toContainText("Permission Events");
  await expect(page.locator("#swarm-box")).toContainText("encounter");
  await expect(page.locator("#swarm-box")).toContainText("controller");
  await expect(page.locator("#swarm-box")).toContainText("homeostasis");
  await expect(page.locator("#swarm-box")).toContainText("formal_valuation");
  await expect(page.locator("#swarm-box")).toContainText("promoted");
  await expect(page.locator("#domain-workflow-box")).toContainText("code-development");
  await expect(page.locator("#domain-workflow-box")).toContainText("Graph");
  await expect(page.locator("#domain-workflow-box")).toContainText("Repo scout");
  await expect(page.locator("#domain-workflow-box")).toContainText("Regression Judge");
  await expect(page.locator(".evidence-node-button")).toHaveCount(3);
  await page.locator(".evidence-node-button", { hasText: "formal valuation" }).first().click();
  await expect(page.locator(".evidence-detail-drawer")).toContainText("decision:formal_valuation");
  await page.locator(".evidence-node-button", { hasText: "revenue" }).first().click();
  await expect(page.locator(".evidence-detail-drawer")).toContainText("metric:revenue");
  await expect(page.locator(".evidence-detail-drawer")).toContainText("[redacted]");

  await expectNoHorizontalOverflow(page);
  await expectPanelWithinViewport(page, "#trace-drawer");
  await page.locator("#swarm-box").scrollIntoViewIfNeeded();
  await expectNoElementOverflow(page, "#swarm-box .signal-row");
  await expectNonBlankScreenshot(page, `trace-swarm-${testInfo.project.name}`);
});

test("sandbox investment task stops at OS plan when WRDS connection is missing", async ({ page }) => {
  await page.route("**/platform/os/plan**", async (route) => {
    await route.fulfill({
      json: {
        intent: "investment_analysis",
        runtime_ready: false,
        missing_capabilities: [],
        connection_requirements: [{ capability_id: "wrds-financial-data", connection: "wrds", status: "missing" }],
        needs_confirmation: [],
      },
    });
  });
  let runCalled = false;
  await page.route("**/agents/run**", async (route) => {
    runCalled = true;
    await route.fulfill({ status: 500, json: { detail: "should not run" } });
  });

  await page.goto("/");
  await page.locator("#task-input").fill("分析 AAPL");
  await page.locator("#composer").evaluate((form) => form.requestSubmit());

  await expect(page.locator(".message.assistant .message-content")).toContainText("not runtime-ready");
  await expect(page.locator(".message.assistant .message-content")).toContainText("Missing connection: wrds");
  await expect(page.locator("#setup-sheet")).toHaveAttribute("aria-hidden", "false");
  await expect(page.locator("#os-plan-box")).toContainText("needs setup");
  expect(runCalled).toBe(false);
});

async function installApiFixtures(page) {
  await page.route("**/health", async (route) => {
    await route.fulfill({ json: { status: "ok" } });
  });
  await page.route("**/skills", async (route) => {
    await route.fulfill({ json: { data: [{ name: "value-investing-analysis", description: "Investment research", path: "" }] } });
  });
  await page.route("**/tools", async (route) => {
    await route.fulfill({ json: { data: [{ name: "wrds_company_financials" }, { name: "metric_registry.compute" }] } });
  });
  await page.route("**/platform/config**", async (route) => {
    await route.fulfill({
      json: {
        model_providers: [{ id: "glm", name: "GLM", provider: "zhipu", enabled: true, secrets: { api_key: { configured: true, last4: "jFd" } } }],
        data_sources: [{ id: "wrds", name: "WRDS", provider: "wrds", enabled: true, secrets: { username: { configured: true, last4: "sex" } } }],
      },
    });
  });
  await page.route(/\/platform\/capabilities(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { capabilities: ["investment.research", "valuation", "wrds"] } });
  });
  await page.route("**/platform/capability-catalog**", async (route) => {
    await route.fulfill({
      json: {
        capabilities: [
          {
            id: "value-investing-research",
            name: "Value Investing Research",
            capability_types: ["investment.research", "valuation", "wrds"],
            risk_level: "low",
            requires_confirmation: false,
          },
        ],
      },
    });
  });
  await page.route("**/platform/capabilities/active**", async (route) => {
    await route.fulfill({ json: { capabilities: [{ id: "value-investing-research", name: "Value Investing Research" }] } });
  });
  await page.route("**/platform/agents**", async (route) => {
    await route.fulfill({ json: { agents: [...committeeAgents(), ...domainWorkflowAgents(), ...governanceAgents()] } });
  });
  await page.route("**/platform/os/plan**", async (route) => {
    await route.fulfill({ json: osPlanFixture() });
  });
  await page.route("**/agents/run**", async (route) => {
    await route.fulfill({ json: runFixture() });
  });
  await page.route("**/platform/swarm/runs/*/timeline**", async (route) => {
    await route.fulfill({ json: { data: decisionTimelineFixture() } });
  });
  await page.route("**/platform/swarm/runs/*/why-blocked/**", async (route) => {
    await route.fulfill({ json: whyBlockedFixture() });
  });
  await page.route("**/platform/swarm/runs/*/why-committed**", async (route) => {
    await route.fulfill({ json: { status: "found", quorum_trace: runFixture().quorum_trace } });
  });
  await page.route("**/platform/swarm/runs/*/evidence-graph**", async (route) => {
    await route.fulfill({ json: evidenceGraphStoreFixture() });
  });
  await page.route("**/platform/swarm/runs/*/agent-allocation**", async (route) => {
    await route.fulfill({ json: { data: runFixture().agent_allocation_trace.map((payload) => ({ payload })) } });
  });
  await page.route("**/platform/swarm/runs/*/tool-events**", async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            tool: "wrds_company_financials",
            event_type: "tool.call.completed",
            payload: { args: { api_key: "sk-visual-secret" }, result: { ok: true }, summary: "WRDS fetch completed." },
          },
        ],
      },
    });
  });
  await page.route("**/platform/swarm/runs/*/permission-events**", async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            permission: "network:wrds",
            event_type: "permission.granted",
            payload: { summary: "WRDS network access granted by low-risk policy." },
          },
        ],
      },
    });
  });
}

function committeeAgents() {
  return [
    agent("data_auditor_agent", "Data Auditor", "DAT", "green", true, ["evidence", "data_contract", "risk", "stop_signal"]),
    agent("fundamental_analyst_agent", "Fundamental", "FND", "purple", false, ["evidence", "risk", "quorum"]),
    agent("quant_research_agent", "Quant Research", "QNT", "orange", false, ["evidence", "risk", "quorum"]),
    agent("industry_strategy_agent", "Industry", "IND", "teal", false, ["evidence", "risk", "quorum"]),
    agent("market_execution_agent", "Market", "MKT", "blue", false, ["risk", "quorum"]),
    agent("risk_manager_agent", "Risk", "RSK", "red", true, ["risk", "negative", "stop_signal", "quorum"]),
    agent("red_team_agent", "Red Team", "RED", "red", true, ["risk", "negative", "stop_signal", "quorum"]),
    agent("cio_agent", "CIO", "CIO", "blue", false, ["quorum", "progress"]),
  ];
}

function governanceAgents() {
  return [
    governanceAgent("swarm_scheduler_agent", "Swarm Scheduler", "SCH", "slate", "deterministic_scheduler", false),
    governanceAgent("receiver_normalizer_agent", "Receiver Normalizer", "RCV", "cyan", "intermediate_processor", false),
    governanceAgent("evidence_steward_agent", "Evidence Steward", "EVD", "emerald", "governance_verifier", false),
    governanceAgent("quorum_marshal_agent", "Quorum Marshal", "QRM", "blue", "deterministic_governance", true),
    governanceAgent("social_immunity_agent", "Social Immunity", "IMM", "rose", "security_governance", true),
    governanceAgent("protocol_police_agent", "Protocol Police", "POL", "red", "deterministic_governance", true),
    governanceAgent("tool_health_sentinel_agent", "Tool Health Sentinel", "TLS", "amber", "deterministic_monitor", true),
    governanceAgent("outcome_memory_steward_agent", "Outcome Memory Steward", "MEM", "zinc", "deterministic_learning", false),
    governanceAgent("capability_sandbox_auditor_agent", "Capability Sandbox Auditor", "SBX", "violet", "governance_security", true),
    governanceAgent("independent_scout_agent", "Independent Scout", "SCT", "indigo", "scout", false),
  ];
}

function domainWorkflowAgents() {
  return [
    domainAgent("repo_scout_agent", "Repo Scout", "RSC", "cyan", "code_development_member", "code-development", false),
    domainAgent("dlp_privacy_auditor_agent", "DLP Privacy Auditor", "DLP", "rose", "compliance_workflow_member", "compliance-workflow", true),
    domainAgent("citation_auditor_agent", "Citation Auditor", "CIT", "emerald", "evidence_research_member", "evidence-research", true),
  ];
}

function domainAgent(key, name, short, accent, agentType, capabilityId, canBlock) {
  return {
    key,
    name,
    short,
    accent,
    description: `${name} domain workflow agent`,
    agent_type: agentType,
    capability_id: capabilityId,
    default_enabled: true,
    tags: ["domain", capabilityId],
    risk_level: canBlock ? "medium" : "low",
    swarm: {
      can_block: canBlock,
      quorum_weight: canBlock ? 0.75 : 0.55,
      signal_emit_permissions: canBlock ? ["evidence", "risk", "stop_signal"] : ["evidence"],
    },
  };
}

function governanceAgent(key, name, short, accent, agentType, canBlock) {
  return {
    key,
    name,
    short,
    accent,
    description: `${name} OS governance actor`,
    agent_type: agentType,
    default_enabled: key !== "independent_scout_agent",
    tags: ["governance", "pheroos"],
    swarm: {
      can_block: canBlock,
      trust_level: canBlock ? "core_system" : "trusted_first_party",
      signal_emit_permissions: ["evidence", "risk", "quorum"],
    },
  };
}

function agent(key, name, short, accent, canBlock, signalPermissions) {
  return {
    key,
    name,
    short,
    accent,
    description: `${name} committee member`,
    agent_type: "investment_committee_member",
    default_enabled: true,
    tags: ["committee", "investment"],
    swarm: {
      can_block: canBlock,
      quorum_weight: canBlock ? 0.85 : 0.65,
      signal_emit_permissions: signalPermissions,
    },
  };
}

function osPlanFixture() {
  return {
    intent: "investment_research",
    task_type: "investment_research",
    runtime_ready: true,
    auto_enabled: ["value-investing-research"],
    missing_capabilities: [],
    connection_requirements: [],
    needs_confirmation: [],
    committee_plan: { required: true, members: committeeAgents().map(({ key, name }) => ({ key, name })) },
  };
}

function decisionTimelineFixture() {
  return [
    {
      record_type: "event",
      event_type: "data_gate.completed",
      canonical_target: "decision:formal_valuation",
      summary: "Data Gate blocked formal valuation.",
    },
    {
      record_type: "signal",
      type: "stop_signal",
      canonical_target: "decision:formal_valuation",
      summary: "Verified agent stop-signal proposal.",
    },
  ];
}

function whyBlockedFixture() {
  return {
    run_id: "visual-run-001",
    target: "formal_valuation",
    canonical_target: "decision:formal_valuation",
    blocked: true,
    blocking_signals: [
      {
        target: "decision:formal_valuation",
        canonical_target: "decision:formal_valuation",
        source_module: "data_gate",
        content: "Formal valuation blocked until deterministic metrics support it.",
      },
    ],
  };
}

function evidenceGraphStoreFixture() {
  return {
    run_id: "visual-run-001",
    nodes: [
      {
        node_id: "metric:revenue:FY2025",
        kind: "metric",
        canonical_target: "metric:revenue",
        payload: {
          id: "metric:revenue:FY2025",
          kind: "metric",
          name: "revenue",
          period: "FY2025",
          value: 391035,
          source: "metric_registry",
          verification_state: "verified",
          authority_level: 4,
          metadata: { api_key: "sk-visual-secret" },
        },
      },
      {
        node_id: "permission:decision:formal_valuation",
        kind: "output_permission",
        canonical_target: "decision:formal_valuation",
        payload: {
          id: "permission:decision:formal_valuation",
          kind: "output_permission",
          label: "formal valuation",
          canonical_target: "decision:formal_valuation",
          allowed: false,
          status: "blocked",
          source_module: "data_gate",
          reason: "PASS_WRDS_ONLY",
        },
      },
      {
        node_id: "candidate:insufficient_data",
        kind: "candidate",
        canonical_target: "candidate:investment:insufficient_data",
        payload: {
          id: "candidate:insufficient_data",
          kind: "candidate",
          label: "Insufficient Data",
          committed: true,
          support_score: 1,
        },
      },
    ],
    edges: [
      {
        source: "permission:decision:formal_valuation",
        target: "candidate:insufficient_data",
        relation: "forces_candidate",
        payload: {
          source: "permission:decision:formal_valuation",
          target: "candidate:insufficient_data",
          relation: "forces_candidate",
        },
      },
    ],
  };
}

function runFixture() {
  return {
    run_id: "visual-run-001",
    task: "Analyze AAPL",
    metadata: { os_plan: osPlanFixture(), enabled_capabilities: [{ id: "value-investing-research" }] },
    route: "investment_committee",
    domain_workflow: {
      workflow_id: "code-development",
      graph_mode: "code_development",
      domain_nodes: ["repo_scout", "architecture_mapper", "patch_planner", "test_runner", "regression_judge"],
      graph_nodes: ["memory_agent", "executor", "critic", "writer", "final_judge"],
      required_gates: ["diff_gate", "test_gate", "interface_gate"],
      agents: [
        { key: "repo_scout_agent", name: "Repo Scout", short: "RSC", accent: "cyan", capability_id: "code-development" },
        { key: "regression_judge_agent", name: "Regression Judge", short: "JDG", accent: "blue", capability_id: "code-development" },
      ],
      execution_plan: [
        { id: "repo-scout", title: "Repo scout", action: "Inspect repository structure.", tool_calls: [{ name: "list_files" }] },
        { id: "regression-judge", title: "Regression Judge", action: "Accept, revise, or reject patch from gate evidence.", tool_calls: [] },
      ],
      guardrails: ["Coder cannot mutate before patch plan.", "Writer cannot claim success when tests fail."],
      writer_policy: "Writer may summarize only patch, diff, and test evidence accepted by regression_judge.",
    },
    translated_task: "Analyze AAPL",
    search_query: "",
    english_search_query: "",
    orchestration: { task_type: "investment", committee: true },
    selected_skills: [],
    plan: [{ id: "1", title: "Build WRDS metric registry", action: "Fetch deterministic financial data", tool_calls: [{ name: "wrds_company_financials", args: { ticker: "AAPL" } }] }],
    execution_log: [{ step_id: "1", title: "WRDS", status: "completed", tool_calls: [{ name: "wrds_company_financials", args: { ticker: "AAPL" }, result: { ok: true } }] }],
    wrds_result: { ok: true },
    data_gate: { status: "PASS_WRDS_ONLY", formal_valuation_allowed: false, report_publication_allowed: true, confidence: "medium" },
    research_brief: { status: "completed_wrds_only" },
    quant_analysis: { status: "completed_wrds_only" },
    domain_analysis: { status: "skipped" },
    committee_outputs: {
      data_auditor_agent: { status: "completed", thesis: "WRDS-only data is internally coherent but formal valuation is limited.", score: 52, confidence: "medium", risks: ["No official reconciliation"], hard_veto: false },
      red_team_agent: { status: "completed", thesis: "Do not publish a target price without verified valuation inputs.", score: 35, confidence: "medium", risks: ["Overclaim risk"], hard_veto: true },
      cio_agent: { status: "completed", thesis: "WATCH pending stronger valuation evidence.", score: 50, confidence: "medium", risks: [] },
    },
    discussion_transcript: [
      { round: 0, speaker: "Data Auditor", claim: "WRDS-only pass with caveats.", score: 52, confidence: "medium" },
      { round: 1, speaker: "Red Team", target: "CIO", challenge: "Formal valuation should remain blocked.", response: "Accepted as a caveat." },
    ],
    committee_decision: {
      decision: "WATCH",
      final_decision: "WATCH",
      conviction: "Medium",
      core_thesis: "Quality remains high, but formal valuation is blocked by data gate caveats.",
      scorecard: [
        { agent: "data_auditor_agent", score: 52 },
        { agent: "red_team_agent", score: 35 },
        { agent: "cio_agent", score: 50 },
      ],
    },
    pheromone_field_snapshot: {
      signal_count: 2,
      blocking_targets: ["formal_valuation"],
      signals: [],
    },
    pheromone_trace: [],
    stop_signals: [
      {
        type: "stop_signal",
        target: "formal_valuation",
        source_module: "swarm_signal_verifier",
        verification_state: "blocking",
        blocking: true,
        strength: 1,
        content: "Verified agent stop-signal proposal: Formal valuation should wait for deterministic registry coverage.",
      },
    ],
    constraint_signals: [
      {
        type: "constraint",
        target: "data_source_policy",
        source_module: "os_kernel",
        verification_state: "verified",
        blocking: false,
        strength: 1,
        content: "The active source policy uses the WRDS/metric-registry path.",
      },
    ],
    quorum_trace: {
      committed_candidate: { label: "Insufficient Data", committed: true },
      candidates: [
        { label: "Buy", support_score: 0.25, blocked: true },
        { label: "Watch", support_score: 0.66, blocked: true },
        { label: "Insufficient Data", support_score: 1, committed: true },
      ],
    },
    evidence_graph: {
      schema_version: "pheroos.evidence_graph.v1",
      metrics: [
        {
          id: "metric:revenue:FY2025",
          kind: "metric",
          name: "revenue",
          period: "FY2025",
          value: 391035,
          source: "metric_registry",
          verification_state: "verified",
        },
      ],
      output_permissions: [
        {
          id: "permission:decision:formal_valuation",
          kind: "output_permission",
          label: "formal valuation",
          canonical_target: "decision:formal_valuation",
          allowed: false,
          status: "blocked",
          source_module: "data_gate",
        },
      ],
      candidate_decisions: [
        {
          id: "candidate:insufficient_data",
          kind: "candidate",
          label: "Insufficient Data",
          committed: true,
          support_score: 1,
        },
      ],
      edges: [{ source: "permission:decision:formal_valuation", target: "candidate:insufficient_data", relation: "forces_candidate" }],
      summary: {
        fact_count: 1,
        proposal_count: 1,
        blocker_count: 1,
        candidate_count: 3,
        committed_candidate: "Insufficient Data",
        blocked_outputs: ["decision:formal_valuation"],
        allowed_outputs: ["decision:report_publication"],
      },
      writer_contract: {
        rule: "Writer may express only Data Gate / Evidence Graph allowed conclusions and must not promote proposals into facts.",
        allowed_outputs: ["decision:report_publication"],
        blocked_outputs: ["decision:formal_valuation"],
      },
    },
    agent_allocation_trace: [
      { agent: "data_auditor_agent", activated: true, demand_strength: 0.9, reason: "data gate caveats" },
      { agent: "red_team_agent", activated: true, demand_strength: 0.8, reason: "overclaim pressure" },
    ],
    agent_signal_diagnostics: [
      { agent: "red_team_agent", status: "accepted", type: "stop_signal", target: "formal_valuation", reason: "accepted as a contested committee signal proposal", proposed_blocking: true },
      { agent: "fundamental_analyst_agent", status: "rejected", type: "stop_signal", target: null, reason: "agent is not allowed to propose stop_signals" },
    ],
    agent_signal_verification_trace: [
      { signal_id: "sig-red", target: "formal_valuation", status: "promoted", reason: "Data Gate already blocks formal valuation." },
    ],
    patroller_report: { status: "pass" },
    encounter_rate_report: { status: "healthy", rate: 0.75, success_events: 3, attempts: 4 },
    bottleneck_report: { status: "bottleneck_detected", pending_evidence: 3, verified_evidence: 1, bottlenecks: [] },
    arousal_report: { status: "elevated", arousal_level: 0.8, triggers: ["formal valuation"] },
    lane_assignment_report: { status: "assigned", assignments: [{ agent: "data_auditor_agent", lane: "verification" }] },
    social_immunity_report: { status: "heightened", quarantine_count: 0, arousal_level: 0.62 },
    policing_trace: { status: "violations_detected", violations: [{ agent: "fundamental_analyst_agent" }], warnings: [] },
    homeostasis_report: { status: "strained", variables: { risk_pressure: 0.62 }, recommendations: ["increase verifier strictness"] },
    maturity_report: { status: "evaluated", agents: [{ agent: "data_auditor_agent", maturity: "worker" }] },
    independence_report: { status: "evaluated", source_diversity: 0.67, correlation_penalty: 0.33 },
    swarm_controller_report: {
      status: "controlling",
      actions: [
        { action: "recruit", agent: "data_auditor_agent", reason: "Evidence backlog exceeds verifier capacity." },
        { action: "raise_verification_policy", target: "critic_and_final_judge", reason: "formal valuation" },
      ],
      agent_overrides: {
        data_auditor_agent: { recruit: true, throttle: false, priority_delta: 0.2, activation_bias: 0.15 },
        fundamental_analyst_agent: { recruit: false, throttle: true, priority_delta: -0.15, activation_bias: -0.2 },
      },
      verification_policy: { strictness: "high" },
      writer_policy: { temperature_cap: 0, allow_formal_conclusion: false },
      quorum_policy: { threshold_delta: 0.15, min_independence_score: 0.5, force_insufficient_data_when_low_independence: true },
      lane_policy: { status: "assigned", assignments: [{ agent: "data_auditor_agent", lane: "verification" }], violations: [] },
      runtime_budget: { mode: "conservative", recommendation: "prioritize verifier feedback" },
    },
    signal_resolution_report: {
      status: "open_blockers",
      resolved: [],
      open_blockers: [{ id: "sig-red", target: "decision:formal_valuation", reason: "Data Gate still blocks formal valuation." }],
    },
    artifact_cue_report: { status: "cues_detected", cue_count: 1, cues: [{ code: "missing_caveat" }] },
    receiver_normalizer_report: {
      status: "backlog_detected",
      claim_count: 3,
      risk_count: 2,
      unsupported_claims: [{ agent: "red_team_agent", id: "claim:red_team_agent:thesis" }],
    },
    evidence_steward_report: {
      status: "unsupported_claims",
      linked_claim_count: 2,
      unsupported_claim_count: 1,
      blocked_claim_count: 1,
    },
    tool_health_sentinel_report: {
      status: "healthy",
      attempts: 1,
      failures: 0,
      failure_rate: 0,
    },
    capability_sandbox_auditor_report: {
      status: "clear",
      capability_count: 1,
      high_risk_count: 0,
      findings: [],
    },
    outcome_memory_steward_report: {
      status: "update_profiles",
      profile_updates: [{ agent: "data_auditor_agent" }, { agent: "red_team_agent" }],
      memory_boundary: "does_not_store_company_specific_investment_conclusions",
    },
    quorum_marshal_report: {
      status: "blocked_to_insufficient_data",
      committed_candidate: { label: "Insufficient Data" },
      why_committed: "Stop-signal override forced Insufficient Data.",
    },
    swarm_governance_trace: governanceAgents().map((agent) => ({
      agent: agent.key,
      caste: agent.agent_type,
      deterministic: true,
      can_block: Boolean(agent.swarm.can_block),
      report_key: `${agent.key.replace("_agent", "")}_report`,
      status: agent.key === "independent_scout_agent" ? "evaluated" : "clear",
      summary: agent.key === "quorum_marshal_agent" ? "committed candidate: Insufficient Data" : `${agent.name} completed`,
    })),
    swarm_metrics: { signal_count: 2, stop_signal_count: 1, blocking_signal_count: 1 },
    review: { status: "ACCEPT_WITH_MINOR_EDITS", issues: [{ severity: "medium", issue: "Keep WRDS-only caveat visible." }], summary: "Caveated report is acceptable." },
    agent_metrics: [
      { agent: "data_auditor_agent", model: "mock", status: "completed", duration_seconds: 0.1 },
      { agent: "red_team_agent", model: "mock", status: "completed", duration_seconds: 0.1 },
      { agent: "cio_agent", model: "mock", status: "completed", duration_seconds: 0.1 },
      { agent: "final_judge", model: "mock", status: "completed", duration_seconds: 0.1 },
    ],
    run_status: "completed",
    degraded_reasons: [],
    final: "Decision: WATCH. Formal valuation remains blocked; treat this as a WRDS-only preliminary view.",
  };
}

async function expectNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(overflow.scrollWidth, `horizontal overflow: ${JSON.stringify(overflow)}`).toBeLessThanOrEqual(overflow.width + 2);
}

async function expectComposerContract(page) {
  const box = await page.locator("#composer").boundingBox();
  const viewport = page.viewportSize();
  expect(box).toBeTruthy();
  expect(box.width).toBeGreaterThan(Math.min(320, viewport.width - 32));
  expect(box.height).toBeGreaterThan(58);
  const composerCenter = box.x + box.width / 2;
  expect(Math.abs(composerCenter - viewport.width / 2)).toBeLessThan(Math.max(100, viewport.width * 0.15));
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 8);
}

async function expectPanelWithinViewport(page, selector) {
  await expect
    .poll(
      async () => {
        const box = await page.locator(selector).boundingBox();
        const viewport = page.viewportSize();
        if (!box || !viewport) return { ok: false, box, viewport };
        return {
          ok:
            box.x >= -1 &&
            box.y >= -1 &&
            box.x + box.width <= viewport.width + 1 &&
            box.y + Math.min(box.height, viewport.height) <= viewport.height + 1,
          box,
          viewport,
        };
      },
      { message: `${selector} should settle inside viewport` },
    )
    .toMatchObject({ ok: true });
}

async function expectNoCriticalOverlap(page, selectorPairs) {
  const boxes = await page.evaluate((pairs) => {
    function rect(selector) {
      const element = document.querySelector(selector);
      if (!element) return null;
      const { x, y, width, height } = element.getBoundingClientRect();
      return { selector, x, y, width, height };
    }
    return pairs.map(([a, b]) => [rect(a), rect(b)]);
  }, selectorPairs);
  for (const [a, b] of boxes) {
    expect(a, `missing ${a?.selector}`).toBeTruthy();
    expect(b, `missing ${b?.selector}`).toBeTruthy();
    const overlapX = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
    const overlapY = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
    expect(overlapX * overlapY, `${a.selector} overlaps ${b.selector}`).toBeLessThan(2);
  }
}

async function expectNoElementOverflow(page, selector) {
  const overflow = await page.locator(selector).evaluateAll((nodes) =>
    nodes.map((node) => ({
      text: node.textContent?.trim().slice(0, 80) || "",
      width: node.clientWidth,
      scrollWidth: node.scrollWidth,
      height: node.clientHeight,
      scrollHeight: node.scrollHeight,
    })),
  );
  expect(overflow.length).toBeGreaterThan(0);
  for (const item of overflow) {
    expect(item.scrollWidth, `horizontal element overflow: ${JSON.stringify(item)}`).toBeLessThanOrEqual(item.width + 2);
    expect(item.scrollHeight, `vertical element overflow: ${JSON.stringify(item)}`).toBeLessThanOrEqual(item.height + 2);
  }
}

async function expectNonBlankScreenshot(page, name) {
  await mkdir(artifactDir, { recursive: true });
  const filePath = path.join(artifactDir, `${name}.png`);
  const buffer = await page.screenshot({ path: filePath, fullPage: true, animations: "disabled" });
  const image = PNG.sync.read(buffer);
  const sampleStep = Math.max(1, Math.floor((image.width * image.height) / 20_000));
  let sampled = 0;
  let minLuma = 255;
  let maxLuma = 0;
  for (let pixel = 0; pixel < image.width * image.height; pixel += sampleStep) {
    const offset = pixel * 4;
    const r = image.data[offset];
    const g = image.data[offset + 1];
    const b = image.data[offset + 2];
    const luma = Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b);
    minLuma = Math.min(minLuma, luma);
    maxLuma = Math.max(maxLuma, luma);
    sampled += 1;
  }
  expect(sampled).toBeGreaterThan(100);
  expect(maxLuma - minLuma, `screenshot appears blank: ${filePath}`).toBeGreaterThan(24);
}
