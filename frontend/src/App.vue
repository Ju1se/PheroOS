<template>
  <div class="app-shell">
    <header class="app-header">
      <nav class="header-actions header-actions-left" aria-label="Global actions">
        <button class="icon-button" id="trace-button" type="button" title="Trace" aria-label="Trace" @click="setTraceOpen(true)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="3"/><path d="M9 5v14M13 9h4M13 13h4"/></svg>
        </button>
        <button class="icon-button" id="new-chat-button" type="button" title="New session" aria-label="New session" @click="resetChat">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h8"/><path d="M16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1 1-4Z"/></svg>
        </button>
      </nav>

      <button class="header-brand" type="button" aria-label="AI OS home" @click="resetChat">
        <span class="brand-mark">OS</span>
        <span>AI OS</span>
      </button>

      <nav class="header-actions header-actions-right" aria-label="Status and setup">
        <span class="system-pill"><span id="api-status">{{ apiStatus }}</span></span>
        <span class="system-pill" id="tenant-summary">{{ tenantSummary }}</span>
        <span class="system-pill" id="connection-summary">{{ connectionSummary }}</span>
        <button class="icon-button" id="setup-button" type="button" title="API Keys" aria-label="API Keys" @click="setSetupOpen(true, 'connect')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 3 11 13"/><path d="M15 3h6v6"/><circle cx="7" cy="17" r="4"/><path d="M7 17h.01"/></svg>
        </button>
        <button class="icon-button" id="clear-button" type="button" title="Clear" aria-label="Clear" @click="resetChat">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>
        </button>
      </nav>
    </header>

    <main class="chat-workspace" aria-label="Conversation">
      <section class="conversation">
        <div class="console-title">
          <p id="run-label">{{ runLabel }}</p>
        </div>

        <section v-if="messages.length === 0" class="os-home" id="os-home" aria-label="AI OS home">
          <div class="home-orb" aria-hidden="true">OS</div>
          <h1>AI OS</h1>
          <p>Paste one key. Ask one thing. The OS assembles the committee.</p>
        </section>

        <section class="messages" id="messages" aria-live="polite">
          <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
            <div class="message-meta">
              <span class="message-role">{{ message.role === "user" ? "You" : message.role === "error" ? "System" : "Agent" }}</span>
              <span class="message-time">{{ message.time }}</span>
            </div>
            <div class="message-content">{{ message.content }}</div>
            <div v-if="message.chips?.length" class="chip-row">
              <span v-for="chip in message.chips" :key="chip.text" class="chip" :class="chip.kind">{{ chip.text }}</span>
            </div>
          </article>
        </section>

        <form class="composer" id="composer" @submit.prevent="handleSubmit">
          <div class="composer-main">
            <textarea
              id="task-input"
              v-model="taskInput"
              rows="1"
              placeholder="Send a message"
              aria-label="Task"
              :disabled="running"
              @keydown.enter.exact.prevent="handleSubmit"
              @input="autoResize"
            ></textarea>
            <div class="composer-controls" aria-label="OS controls">
              <button class="composer-chip" id="inline-setup-button" type="button" @click="setSetupOpen(true, 'connect')">Connect</button>
              <button class="composer-chip" id="inline-agents-button" type="button" @click="setSetupOpen(true, 'agents')">Agents</button>
              <button class="composer-chip" id="inline-trace-button" type="button" @click="setTraceOpen(true)">Trace</button>
              <span class="composer-status" id="inline-provider-pill" :class="{ ready: readyConnectionCount > 0 }">{{ readyConnectionCount ? `${readyConnectionCount} connections` : "No keys" }}</span>
              <span class="composer-status" id="inline-committee-pill" :class="{ ready: selectedAgentCount > 0 }">{{ selectedAgentCount ? `${selectedAgentCount} agents` : "AI committee" }}</span>
            </div>
          </div>
          <button class="send-button" id="send-button" type="submit" title="Send" :disabled="running">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
          </button>
        </form>
      </section>
    </main>

    <section class="setup-sheet" id="setup-sheet" :class="{ open: setupOpen }" :aria-hidden="setupOpen ? 'false' : 'true'" :inert="!setupOpen">
      <button class="sheet-backdrop" id="setup-backdrop" type="button" aria-label="Close setup" @click="setSetupOpen(false)"></button>
      <aside class="setup-panel" aria-label="API key setup">
        <header class="panel-header">
          <div>
            <h2>OS Setup</h2>
            <p>Keys become capability handles. Agents never see raw secrets.</p>
          </div>
          <button class="icon-button" id="close-setup-button" type="button" title="Close" @click="setSetupOpen(false)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </header>

        <nav class="setup-tabs" aria-label="OS setup sections">
          <button v-for="tab in setupTabs" :key="tab.id" class="setup-tab" :class="{ active: setupTab === tab.id }" type="button" :data-setup-tab="tab.id" @click="setupTab = tab.id">
            {{ tab.label }}
          </button>
        </nav>

        <div class="setup-pane" :class="{ active: setupTab === 'connect' }" data-setup-pane="connect" v-show="setupTab === 'connect'">
          <section class="tenant-card" aria-label="Workspace tenant">
            <div>
              <span class="eyebrow">Workspace</span>
              <strong id="active-tenant">{{ tenantId }}</strong>
              <p>Use a sandbox tenant to test zero-state API-key auto configuration without deleting your saved default keys.</p>
            </div>
            <form class="tenant-form" @submit.prevent="setTenantFromInput">
              <label class="field-label" for="tenant-input">Tenant ID</label>
              <div class="tenant-input-row">
                <input id="tenant-input" v-model="tenantInput" type="text" autocomplete="off" spellcheck="false" />
                <button class="ghost-button tiny" id="tenant-apply-button" type="submit">Use</button>
              </div>
              <div class="agent-plugin-actions">
                <button class="ghost-button tiny" id="tenant-sandbox-button" type="button" @click="createSandboxTenant">Fresh sandbox</button>
                <button class="ghost-button tiny" id="tenant-default-button" type="button" @click="useDefaultTenant">Default</button>
              </div>
            </form>
          </section>

          <form class="auto-config-form" id="auto-config-form" @submit.prevent="handleAutoConfigure">
            <label class="field-label" for="auto-config-input">API key / credential</label>
            <textarea id="auto-config-input" v-model="autoConfigInput" rows="5" placeholder="sk-...&#10;wrds&#10;username: ...&#10;password: ..." autocomplete="off" spellcheck="false" required></textarea>
            <button class="primary-button" id="auto-config-button" type="submit" :disabled="autoConfigBusy">{{ autoConfigButtonLabel }}</button>
          </form>

          <div class="setup-result" id="auto-config-result" :class="autoConfigClass">{{ autoConfigResult }}</div>

          <section class="connections-block">
            <div class="section-heading">
              <h3>Connections</h3>
              <span id="connection-count">{{ readyConnectionCount }}/{{ allConnections.length }}</span>
            </div>
            <div id="connection-list" class="connection-list">
              <article v-if="allConnections.length === 0" class="connection-item muted">No keys yet</article>
              <article v-for="connection in allConnections" :key="connection.id" class="connection-item">
                <strong>{{ connection.name || connection.display_name || connection.id }}</strong>
                <span>{{ connection.label }} · {{ connection.provider || "custom" }} · {{ connectionStatus(connection) }}</span>
                <span v-if="connection.base_url || connection.endpoint">{{ connection.base_url || connection.endpoint }}</span>
              </article>
            </div>
          </section>
        </div>

        <div class="setup-pane" :class="{ active: setupTab === 'capabilities' }" data-setup-pane="capabilities" v-show="setupTab === 'capabilities'">
          <section class="connections-block">
            <div class="section-heading">
              <h3>OS Capabilities</h3>
              <span id="capability-count">{{ activeCapabilities.length }}/{{ capabilityCatalog.length }}</span>
            </div>
            <div id="capability-list" class="connection-list">
              <article v-if="capabilityCatalog.length === 0" class="connection-item muted">No local capabilities</article>
              <article v-for="capability in capabilityCatalog" :key="capability.id" class="connection-item">
                <strong>{{ capability.name || capability.id }}</strong>
                <span>{{ capabilityStatus(capability) }} · {{ capability.risk_level || "unknown" }} · {{ (capability.capability_types || []).slice(0, 3).join(", ") }}</span>
              </article>
            </div>
          </section>
        </div>

        <div class="setup-pane" :class="{ active: setupTab === 'agents' }" data-setup-pane="agents" v-show="setupTab === 'agents'">
          <section class="connections-block">
            <div class="section-heading">
              <h3>Agent Plugins</h3>
              <span id="committee-member-count">{{ selectedAgentCount }}/{{ selectableAgents.length }} · {{ committeeSelectionMode.replaceAll("_", " ") }}</span>
            </div>
            <div class="agent-plugin-actions" aria-label="Committee member presets">
              <button class="ghost-button tiny" type="button" id="committee-ai-button" @click="setCommitteePreset('auto_default')">AI choose</button>
              <button class="ghost-button tiny" type="button" id="committee-core-button" @click="setCommitteePreset('core')">Core</button>
              <button class="ghost-button tiny" type="button" id="committee-all-button" @click="setCommitteePreset('all')">All</button>
            </div>
            <div id="committee-member-list" class="agent-plugin-list">
              <section v-if="investmentAgents.length" class="agent-plugin-section">
                <h4>Investment Committee Seats</h4>
                <p>Selected for valuation, risk, business-quality, and final investment debate.</p>
                <div class="agent-plugin-grid">
                  <label v-for="agent in investmentAgents" :key="agent.key" class="agent-plugin-card" :class="[`accent-${agent.accent || 'blue'}`, { selected: selectedAgentIds.includes(agent.key) }]">
                    <input v-model="selectedAgentIds" type="checkbox" :value="agent.key" :data-agent-plugin="agent.key" @change="committeeSelectionMode = 'user_selected'" />
                    <AgentCardBody :agent="agent" />
                  </label>
                </div>
              </section>

              <section v-if="domainWorkflowAgents.length" class="agent-plugin-section">
                <h4>Domain Workflow Agents</h4>
                <p>Selected by the AI OS when the task routes into code, compliance, or evidence-research workflows.</p>
                <div class="agent-plugin-grid">
                  <label v-for="agent in domainWorkflowAgents" :key="agent.key" class="agent-plugin-card" :class="[`accent-${agent.accent || 'blue'}`, { selected: selectedAgentIds.includes(agent.key) }]">
                    <input v-model="selectedAgentIds" type="checkbox" :value="agent.key" :data-agent-plugin="agent.key" @change="committeeSelectionMode = 'user_selected'" />
                    <AgentCardBody :agent="agent" />
                  </label>
                </div>
              </section>

              <section v-if="governanceAgents.length" class="governance-plugin-section">
                <h4>Governance Actors</h4>
                <p>These are OS-level swarm actors. They are enabled by protocol, not selected as analyst committee seats.</p>
                <div class="governance-plugin-grid">
                  <article v-for="agent in governanceAgents" :key="agent.key" class="agent-plugin-card governance-only" :class="`accent-${agent.accent || 'slate'}`">
                    <AgentCardBody :agent="agent" />
                  </article>
                </div>
              </section>
            </div>
          </section>
        </div>

        <div class="setup-pane" :class="{ active: setupTab === 'plan' }" data-setup-pane="plan" v-show="setupTab === 'plan'">
          <section class="connections-block">
            <div class="section-heading">
              <h3>OS Plan</h3>
              <span>auto</span>
            </div>
            <div id="os-plan-box" class="setup-result" :class="osPlanClass">
              <template v-if="osPlan?.intent">
                <strong>{{ osPlan.intent }} · {{ osPlan.runtime_ready ? "ready" : "needs setup" }}</strong>
                <span>auto enabled: {{ (osPlan.auto_enabled || []).join(", ") || "none" }}</span>
                <span>missing: {{ (osPlan.missing_capabilities || []).join(", ") || "none" }}</span>
                <span>connections: {{ (osPlan.connection_requirements || []).map((item) => item.connection).join(", ") || "none" }}</span>
                <span>confirmations: {{ (osPlan.needs_confirmation || []).length }}</span>
                <span>targets: {{ (osPlan.swarm_plan?.target_signals || []).map((item) => item.canonical_target || item.target).slice(0, 4).join(", ") || "none" }}</span>
                <span>agents: {{ (osPlan.swarm_plan?.activated_agents || []).slice(0, 6).join(", ") || "none" }}</span>
              </template>
              <template v-else>Ask for a task to see capability planning.</template>
            </div>
          </section>

          <details class="advanced-settings">
            <summary>Advanced routing</summary>
            <label class="field-label" for="skill-select">Skill override</label>
            <select id="skill-select" v-model="skillOverride">
              <option value="">Auto select</option>
              <option v-for="skill in skills" :key="skill.name" :value="skill.name">{{ skill.name }}</option>
            </select>
            <div class="history-block">
              <h3>Recent</h3>
              <div id="history-list" class="history-list">
                <article v-for="item in history" :key="item.runId" class="history-item">
                  <span>{{ item.task }}</span>
                  <strong>{{ item.runId.slice(0, 6) }}</strong>
                </article>
              </div>
            </div>
          </details>
        </div>
      </aside>
    </section>

    <button class="drawer-scrim" id="trace-scrim" :class="{ open: traceOpen }" type="button" aria-label="Close trace" :aria-hidden="traceOpen ? 'false' : 'true'" :inert="!traceOpen" @click="setTraceOpen(false)"></button>
    <aside class="trace-drawer" id="trace-drawer" :class="{ open: traceOpen }" aria-label="Multi-agent trace" :aria-hidden="traceOpen ? 'false' : 'true'" :inert="!traceOpen">
      <header class="panel-header">
        <div>
          <h2>Research Trace</h2>
          <p id="trace-status">{{ traceStatus }}</p>
        </div>
        <div class="panel-actions">
          <button class="icon-button" id="copy-json-button" type="button" title="Copy JSON" @click="copyLastRun">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"/></svg>
          </button>
          <button class="icon-button" id="close-trace-button" type="button" title="Close" @click="setTraceOpen(false)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
      </header>

      <div class="trace-scroll">
        <section class="trace-section committee-primary">
          <h3>Committee Scorecard</h3>
          <div id="value-research-box" class="review-box" :class="{ 'empty-state': !lastRun }">
            <template v-if="lastRun">
              <strong>{{ committeeDecision }}</strong>
              <p>{{ lastRun.committee_decision?.core_thesis || lastRun.final || "Committee result is ready." }}</p>
              <div class="score-grid">
                <article v-for="(output, key) in lastRun.committee_outputs || {}" :key="key">
                  <span>{{ prettyAgent(key) }}</span>
                  <strong>{{ output.score ?? "n/a" }}</strong>
                  <small>{{ output.confidence || output.status || "unknown" }}</small>
                </article>
              </div>
            </template>
            <template v-else>Committee scorecard will appear after an investment run.</template>
          </div>
        </section>

        <section class="trace-section committee-primary">
          <h3>Committee Discussion</h3>
          <div id="discussion-box" class="discussion-box" :class="{ 'empty-state': !lastRun }">
            <template v-if="discussionRows.length">
              <article v-for="turn in discussionRows" :key="`${turn.round}-${turn.speaker}-${turn.claim || turn.challenge}`" class="discussion-turn">
                <div class="round-header">
                  <strong>Round {{ turn.round ?? 0 }}</strong>
                  <span>{{ turn.speaker || "Committee" }}</span>
                </div>
                <p>{{ turn.claim || turn.challenge || turn.response || "No transcript text." }}</p>
                <small v-if="turn.response">{{ turn.response }}</small>
              </article>
            </template>
            <template v-else>Debate rounds will appear here.</template>
          </div>
        </section>

        <section class="trace-section committee-primary">
          <h3>Swarm Governance</h3>
          <div id="swarm-box" class="swarm-board" :class="{ 'empty-state': !lastRun }">
            <template v-if="lastRun">
              <section class="swarm-hero">
                <div>
                  <span class="eyebrow">PheroOS Governance Field</span>
                  <h4>Decision Debugger</h4>
                  <p>PheroOS Controller coordinates typed signals, quorum, policing, homeostasis, and evidence promotion.</p>
                </div>
                <div class="swarm-stats">
                  <div><strong>{{ lastRun.swarm_metrics?.signal_count ?? 0 }}</strong><span>signals</span></div>
                  <div><strong>{{ lastRun.swarm_metrics?.stop_signal_count ?? 0 }}</strong><span>stops</span></div>
                  <div><strong>{{ evidenceItems.length }}</strong><span>evidence</span></div>
                </div>
              </section>

              <div class="swarm-keywords">
                <span>PheroOS Controller</span>
                <span>Swarm Governance Caste</span>
                <span>Quorum Marshal</span>
                <span>Evidence Steward</span>
                <span>Why Blocked</span>
                <span>Evidence Graph</span>
                <span>Tool Events</span>
                <span>Permission Events</span>
                <span>encounter</span>
                <span>controller</span>
                <span>homeostasis</span>
                <span>formal_valuation</span>
                <span>promoted</span>
              </div>

              <div class="signal-list">
                <article v-for="signal in signalRows" :key="signal.id" class="signal-row">
                  <strong>{{ signal.title }}</strong>
                  <span>{{ signal.summary }}</span>
                </article>
              </div>

              <div class="evidence-strip">
                <button v-for="item in evidenceItems" :key="item.key" class="evidence-node-button" type="button" :data-evidence-detail="item.key" @click="selectedEvidenceKey = item.key">
                  {{ item.title }}
                </button>
              </div>
              <aside v-if="selectedEvidence" class="evidence-detail-drawer">
                <strong>{{ selectedEvidence.title }}</strong>
                <dl>
                  <div><dt>target</dt><dd>{{ selectedEvidence.item.canonical_target || selectedEvidence.item.target || selectedEvidence.item.id }}</dd></div>
                  <div><dt>kind</dt><dd>{{ selectedEvidence.item.kind || selectedEvidence.type }}</dd></div>
                  <div><dt>status</dt><dd>{{ selectedEvidence.item.status || selectedEvidence.item.verification_state || selectedEvidence.item.governance_status || "available" }}</dd></div>
                </dl>
                <pre>{{ safeJsonPreview(selectedEvidence.item) }}</pre>
              </aside>
            </template>
            <template v-else>Typed pheromone signals, stop-signals, and quorum decisions will appear here.</template>
          </div>
        </section>

        <section class="trace-section committee-primary">
          <h3>Domain Workflow</h3>
          <div id="domain-workflow-box" class="domain-workflow-board" :class="{ 'empty-state': !domainWorkflow }">
            <template v-if="domainWorkflow">
              <section class="domain-workflow-hero">
                <div>
                  <span class="eyebrow">Capability Workflow</span>
                  <h4>{{ domainWorkflow.workflow_id || domainWorkflow.graph_mode }}</h4>
                  <p>{{ (domainWorkflow.graph_mode || "").replaceAll("_", " ") }} runs under OS Kernel routing and PheroOS gates.</p>
                </div>
                <div class="domain-workflow-stats">
                  <div><strong>{{ domainWorkflow.domain_nodes?.length || 0 }}</strong><span>domain nodes</span></div>
                  <div><strong>{{ domainWorkflow.graph_nodes?.length || 0 }}</strong><span>graph nodes</span></div>
                  <div><strong>{{ domainWorkflow.required_gates?.length || 0 }}</strong><span>gates</span></div>
                </div>
              </section>
              <section class="domain-node-row"><strong>Graph</strong><span v-for="node in domainWorkflow.graph_nodes || []" :key="node" class="domain-node-pill">{{ node }}</span></section>
              <section class="domain-step-list">
                <article v-for="step in domainWorkflow.execution_plan || []" :key="step.id" class="domain-step-card">
                  <span>{{ step.id }}</span>
                  <div><strong>{{ step.title }}</strong><p>{{ step.action }}</p></div>
                </article>
              </section>
              <section class="domain-agent-grid">
                <article v-for="agent in domainWorkflow.agents || []" :key="agent.key" class="domain-agent-card">
                  <span>{{ agent.short || agent.key?.slice(0, 3) }}</span>
                  <div><strong>{{ agent.name }}</strong><small>{{ agent.capability_id }}</small></div>
                </article>
              </section>
            </template>
            <template v-else>Code, compliance, and evidence workflow gates will appear here.</template>
          </div>
        </section>

        <section class="agent-rail" id="agent-rail">
          <article v-for="agent in railAgents" :key="agent.key" class="agent-row" :class="agent.status">
            <span class="agent-dot" aria-hidden="true"></span>
            <div><div class="agent-name">{{ agent.name }}</div><div class="agent-detail">{{ agent.detail }}</div></div>
          </article>
        </section>

        <details class="trace-section" open>
          <summary>Agent Metrics</summary>
          <div id="metrics-list" class="detail-list" :class="{ 'empty-state': !lastRun?.agent_metrics?.length }">
            <article v-for="metric in lastRun?.agent_metrics || []" :key="metric.agent" class="detail-item">
              <strong>{{ prettyAgent(metric.agent) }}</strong>
              <p>{{ metric.model }} · {{ metric.status }} · {{ metric.duration_seconds }}s</p>
            </article>
            <template v-if="!lastRun?.agent_metrics?.length">Waiting for metrics</template>
          </div>
        </details>

        <details class="trace-section">
          <summary>Plan</summary>
          <div id="plan-list" class="detail-list" :class="{ 'empty-state': !lastRun?.plan?.length }">
            <article v-for="step in lastRun?.plan || []" :key="step.id" class="detail-item"><strong>{{ step.title || step.id }}</strong><p>{{ step.action }}</p></article>
            <template v-if="!lastRun?.plan?.length">No plan yet</template>
          </div>
        </details>

        <details class="trace-section">
          <summary>Tool Calls</summary>
          <div id="tool-call-list" class="detail-list" :class="{ 'empty-state': toolCalls.length === 0 }">
            <article v-for="call in toolCalls" :key="`${call.name}-${call.stepTitle}`" class="tool-call">
              <div class="tool-call-header"><span class="tool-name">{{ call.name }}</span><span class="tool-status ok">ok</span></div>
              <pre class="tool-result">{{ safeJsonPreview(call.result || {}) }}</pre>
            </article>
            <template v-if="toolCalls.length === 0">No tool calls</template>
          </div>
        </details>

        <details class="trace-section">
          <summary>Query Strategy</summary>
          <div id="translation-box" class="review-box">{{ lastRun?.translated_task || "Waiting for query strategy" }}</div>
        </details>

        <details class="trace-section" open>
          <summary>Critic</summary>
          <div id="review-box" class="review-box" :class="{ 'empty-state': !lastRun?.review }">
            <template v-if="lastRun?.review">
              <strong>{{ lastRun.review.status }}</strong>
              <p>{{ lastRun.review.summary }}</p>
              <ul><li v-for="issue in lastRun.review.issues || []" :key="issue.issue">{{ issue.severity }}: {{ issue.issue }}</li></ul>
            </template>
            <template v-else>Waiting for critic</template>
          </div>
        </details>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, ref } from "vue";

const setupTabs = [
  { id: "connect", label: "Connect" },
  { id: "capabilities", label: "Capabilities" },
  { id: "agents", label: "Agents" },
  { id: "plan", label: "Plan" },
];

const baseRailAgents = [
  ["orchestrator", "Orchestrator", "route + plan"],
  ["memory_agent", "Memory", "profile context"],
  ["wrds_agent", "WRDS Data", "Compustat pull"],
  ["executor", "Executor", "safe tools"],
  ["research_agent", "Research", "evidence table"],
  ["quant_agent", "Quant", "metrics + math"],
  ["data_auditor_agent", "Data Auditor", "source quality"],
  ["fundamental_analyst_agent", "Fundamental", "business quality"],
  ["quant_research_agent", "Quant Research", "valuation evidence"],
  ["risk_manager_agent", "Risk", "veto + sizing"],
  ["red_team_agent", "Red Team", "bear case"],
  ["committee_discussion", "Discuss", "challenge rounds"],
  ["investment_committee", "CIO Decision", "final vote"],
  ["critic", "Critic", "verify + rebut"],
  ["writer", "Writer", "draft"],
  ["final_judge", "Final Judge", "fact check"],
];

const AgentCardBody = defineComponent({
  props: { agent: { type: Object, required: true } },
  setup(props) {
    return () =>
      h("span", { class: "agent-plugin-body" }, [
        h("span", { class: "agent-plugin-mark" }, props.agent.short || String(props.agent.key || "?").slice(0, 3).toUpperCase()),
        h("span", { class: "agent-plugin-copy" }, [
          h("strong", props.agent.name || props.agent.key),
          h("small", props.agent.description || agentTypeDescription(props.agent)),
          h(
            "span",
            { class: "agent-plugin-tags" },
            [
              ...(props.agent.tags || []).slice(0, 3),
              props.agent.swarm?.can_block ? "can block" : "",
              props.agent.swarm?.quorum_weight ? `q ${props.agent.swarm.quorum_weight}` : "",
            ]
              .filter(Boolean)
              .map((tag) => h("span", tag)),
          ),
        ]),
      ]);
  },
});

const apiStatus = ref("checking");
const setupOpen = ref(false);
const setupTab = ref("connect");
const traceOpen = ref(false);
const traceStatus = ref("idle");
const running = ref(false);
const taskInput = ref("");
const messages = ref([]);
const runLabel = ref("AI OS ready.");
const skills = ref([]);
const tools = ref([]);
const platformConfig = ref({ model_providers: [], data_sources: [] });
const capabilityCatalog = ref([]);
const activeCapabilities = ref([]);
const agentPlugins = ref([]);
const selectedAgentIds = ref([]);
const committeeSelectionMode = ref("auto_default");
const osPlan = ref({});
const history = ref([]);
const lastRun = ref(null);
const decisionDebugger = ref({});
const selectedEvidenceKey = ref("");
const skillOverride = ref("");
const autoConfigInput = ref("");
const autoConfigBusy = ref(false);
const pendingConnectionRaw = ref("");
const pendingConnectionCandidate = ref(null);
const autoConfigButtonLabel = ref("Auto configure");
const autoConfigResult = ref("No key has been analyzed yet.");
const autoConfigClass = ref("empty-state");
const DEFAULT_TENANT_ID = "default";
const tenantId = ref(initialTenantId());
const tenantInput = ref(tenantId.value);

const allConnections = computed(() => [
  ...(platformConfig.value.model_providers || []).map((item) => ({ ...item, label: "model" })),
  ...(platformConfig.value.data_sources || []).map((item) => ({ ...item, label: "data" })),
]);
const readyConnectionCount = computed(() => allConnections.value.filter((item) => item.enabled !== false && Object.keys(item.secrets || {}).length).length);
const connectionSummary = computed(() => (readyConnectionCount.value ? `${readyConnectionCount.value} ready` : "No keys"));
const tenantSummary = computed(() => (tenantId.value === DEFAULT_TENANT_ID ? "default" : "sandbox"));
const activeIds = computed(() => new Set(activeCapabilities.value.map((item) => item.id)));
const investmentAgents = computed(() => agentPlugins.value.filter((agent) => agent.agent_type === "investment_committee_member"));
const domainWorkflowAgents = computed(() => agentPlugins.value.filter(isDomainWorkflowAgent));
const governanceAgents = computed(() => agentPlugins.value.filter((agent) => !isSelectableAgent(agent)));
const selectableAgents = computed(() => agentPlugins.value.filter(isSelectableAgent));
const selectedAgentCount = computed(() => selectedAgentIds.value.length || selectableAgents.value.length);
const osPlanClass = computed(() => (!osPlan.value?.intent ? "empty-state" : osPlan.value.runtime_ready ? "success" : "empty-state"));
const committeeDecision = computed(() => lastRun.value?.committee_decision?.decision || lastRun.value?.committee_decision?.final_decision || "Committee ready");
const discussionRows = computed(() => lastRun.value?.discussion_transcript || []);
const domainWorkflow = computed(() => lastRun.value?.domain_workflow || null);
const toolCalls = computed(() => (lastRun.value?.execution_log || []).flatMap((entry) => (entry.tool_calls || []).map((call) => ({ ...call, stepTitle: entry.title }))));
const railAgents = computed(() => baseRailAgents.map(([key, name, detail]) => ({ key, name, detail, status: agentStatus(key) })));

const signalRows = computed(() => {
  if (!lastRun.value) return [];
  return [
    ...(lastRun.value.stop_signals || []).map((item, index) => ({ id: `stop-${index}`, title: "stop_signal", summary: item.content || item.target || "blocking signal" })),
    ...(lastRun.value.constraint_signals || []).map((item, index) => ({ id: `constraint-${index}`, title: "constraint", summary: item.content || item.target || "constraint signal" })),
    ...(decisionDebugger.value.timeline || []).map((item, index) => ({ id: `timeline-${index}`, title: item.event_type || item.type || "timeline", summary: item.summary || item.canonical_target || "" })),
  ];
});

const evidenceItems = computed(() => {
  const graph = decisionDebugger.value.evidenceGraph || {};
  const storeNodes = Array.isArray(graph.nodes) ? graph.nodes.map((node) => node.payload || node) : [];
  const runGraph = lastRun.value?.evidence_graph || {};
  const runNodes = [
    ...(runGraph.metrics || []),
    ...(runGraph.output_permissions || []),
    ...(runGraph.candidate_decisions || []),
  ];
  const rows = [...storeNodes, ...runNodes];
  const seen = new Set();
  return rows
    .map((item) => {
      const id = item.id || item.node_id || item.canonical_target || item.label || item.name;
      const key = `node:${id}`;
      const title = item.label || item.name || item.kind || id;
      return { key, title: String(title).replaceAll("_", " "), type: "node", item };
    })
    .filter((row) => {
      if (seen.has(row.key)) return false;
      seen.add(row.key);
      return true;
    })
    .slice(0, 3);
});
const selectedEvidence = computed(() => evidenceItems.value.find((item) => item.key === selectedEvidenceKey.value) || evidenceItems.value[0] || null);

function isDomainWorkflowAgent(agent) {
  return new Set(["code_development_member", "compliance_workflow_member", "evidence_research_member"]).has(String(agent.agent_type || ""));
}

function isSelectableAgent(agent) {
  return agent.agent_type === "investment_committee_member" || isDomainWorkflowAgent(agent);
}

function agentTypeDescription(agent) {
  if (agent.agent_type === "code_development_member") return "Controlled coding workflow agent";
  if (agent.agent_type === "compliance_workflow_member") return "Enterprise compliance workflow agent";
  if (agent.agent_type === "evidence_research_member") return "Evidence and citation workflow agent";
  if (agent.agent_type === "investment_committee_member") return "Investment committee seat";
  return "OS-level governance actor";
}

function defaultAgentIds() {
  return selectableAgents.value.filter((agent) => agent.default_enabled !== false).map((agent) => agent.key);
}

function connectionStatus(connection) {
  if (connection.enabled === false) return "paused";
  return Object.keys(connection.secrets || {}).length ? "ready" : "missing key";
}

function capabilityStatus(capability) {
  if (activeIds.value.has(capability.id)) return "enabled";
  return capability.requires_confirmation ? "confirm" : "available";
}

function setSetupOpen(open, tab = "connect") {
  setupOpen.value = open;
  if (open) setupTab.value = tab;
}

function setTraceOpen(open) {
  traceOpen.value = open;
}

function nowLabel() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function addMessage(role, content, chips = []) {
  const id = `${Date.now()}-${Math.random()}`;
  messages.value.push({ id, role, content, time: nowLabel(), chips });
  scrollMessagesToBottom();
  return id;
}

function updateMessage(id, patch = {}) {
  const index = messages.value.findIndex((message) => message.id === id);
  if (index < 0) return;
  messages.value[index] = { ...messages.value[index], ...patch };
  scrollMessagesToBottom();
}

function scrollMessagesToBottom() {
  nextTick(() => {
    const node = document.querySelector("#messages");
    if (node) node.scrollTop = node.scrollHeight;
  });
}

function resetChat() {
  messages.value = [];
  lastRun.value = null;
  decisionDebugger.value = {};
  selectedEvidenceKey.value = "";
  osPlan.value = {};
  runLabel.value = "Paste one key, then ask for a company.";
  traceStatus.value = "idle";
}

function autoResize(event) {
  const node = event?.target;
  if (!node) return;
  node.style.height = "auto";
  node.style.height = `${Math.min(node.scrollHeight, 160)}px`;
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function initialTenantId() {
  try {
    return normalizeTenantId(window.localStorage.getItem("aios.tenant_id") || DEFAULT_TENANT_ID);
  } catch {
    return DEFAULT_TENANT_ID;
  }
}

function normalizeTenantId(value) {
  const normalized = String(value || "")
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return normalized || DEFAULT_TENANT_ID;
}

function tenantUrl(url) {
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}tenant_id=${encodeURIComponent(tenantId.value)}`;
}

function rememberTenant() {
  try {
    window.localStorage.setItem("aios.tenant_id", tenantId.value);
  } catch {
    // Local storage is best-effort; runtime still uses the in-memory tenant.
  }
}

async function applyTenant(value) {
  tenantId.value = normalizeTenantId(value);
  tenantInput.value = tenantId.value;
  rememberTenant();
  pendingConnectionRaw.value = "";
  pendingConnectionCandidate.value = null;
  autoConfigButtonLabel.value = "Auto configure";
  autoConfigResult.value =
    tenantId.value === DEFAULT_TENANT_ID
      ? "Default workspace selected. Saved connections are visible."
      : "Fresh sandbox selected. Paste a key to test AI-as-OS auto configuration from zero.";
  autoConfigClass.value = "empty-state";
  resetChat();
  await loadPlatformConfig();
}

async function setTenantFromInput() {
  await applyTenant(tenantInput.value);
}

async function createSandboxTenant() {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  await applyTenant(`sandbox-${stamp}`);
}

async function useDefaultTenant() {
  await applyTenant(DEFAULT_TENANT_ID);
}

async function handleAutoConfigure() {
  const raw = autoConfigInput.value.trim();
  if (!raw) return;
  autoConfigBusy.value = true;
  try {
    if (pendingConnectionRaw.value === raw && pendingConnectionCandidate.value) {
      const result = await apiJson("/platform/connections/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw, tenant_id: tenantId.value, validate: true, discover: true }),
      });
      const connection = result.connection || result;
      autoConfigClass.value = connection.status === "active" ? "success" : "error";
      autoConfigResult.value = `${connection.status === "active" ? "Activated" : "Saved with issues"} ${connection.display_name || connection.name || connection.id}.`;
      pendingConnectionRaw.value = "";
      pendingConnectionCandidate.value = null;
      autoConfigButtonLabel.value = "Auto configure";
      autoConfigInput.value = "";
      await loadPlatformConfig();
      return;
    }
    const result = await apiJson("/platform/connections/infer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw, tenant_id: tenantId.value }),
    });
    pendingConnectionRaw.value = raw;
    pendingConnectionCandidate.value = result.candidate || {};
    autoConfigClass.value = "success";
    autoConfigResult.value = `Detected ${result.candidate?.display_name || result.candidate?.id || "connection"} with ${result.confidence || "unknown"} confidence. Click again to activate.`;
    autoConfigButtonLabel.value = "Confirm & activate";
  } catch (error) {
    autoConfigClass.value = "error";
    autoConfigResult.value = error.message || "Auto configuration failed";
    pendingConnectionRaw.value = "";
    pendingConnectionCandidate.value = null;
    autoConfigButtonLabel.value = "Auto configure";
  } finally {
    autoConfigBusy.value = false;
  }
}

async function planOS(task) {
  osPlan.value = await apiJson("/platform/os/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, tenant_id: tenantId.value, committee_member_ids: selectedAgentIds.value }),
  });
}

async function runAgent(task) {
  const payload = { task, tenant_id: tenantId.value, metadata: { tenant_id: tenantId.value } };
  if (skillOverride.value) payload.skill_names = [skillOverride.value];
  if (selectedAgentIds.value.length) payload.metadata.committee_member_ids = selectedAgentIds.value;
  return apiJson("/agents/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function handleSubmit() {
  const task = taskInput.value.trim();
  if (!task || running.value) return;
  addMessage("user", task);
  const assistantMessageId = addMessage("assistant", "OS Kernel is planning capabilities…", [
    { text: "planning", kind: "success" },
  ]);
  taskInput.value = "";
  running.value = true;
  traceStatus.value = "running";
  let elapsedSeconds = 0;
  const progressTimer = window.setInterval(() => {
    elapsedSeconds += 10;
    updateMessage(assistantMessageId, {
      content:
        elapsedSeconds < 30
          ? "Agent runtime is running. Model calls and data gates can take a little while…"
          : `Still running (${elapsedSeconds}s). The committee may be waiting on model/tool responses.`,
      chips: [
        { text: "running", kind: "success" },
        { text: `${elapsedSeconds}s` },
      ],
    });
  }, 10000);
  try {
    await planOS(task).catch((error) => {
      osPlan.value = { intent: "planning_failed", runtime_ready: false, missing_capabilities: [error.message] };
    });
    if (osPlan.value?.runtime_ready === false) {
      updateMessage(assistantMessageId, {
        content: renderPlanBlockMessage(osPlan.value),
        chips: [
          { text: osPlan.value?.intent || "os plan" },
          { text: "needs setup" },
        ],
      });
      traceStatus.value = "blocked";
      setSetupOpen(true, "plan");
      return;
    }
    updateMessage(assistantMessageId, {
      content: "Runtime materialized. Running the agent committee now…",
      chips: [
        { text: osPlan.value?.intent || "os plan" },
        { text: osPlan.value?.runtime_ready ? "ready" : "degraded" },
      ],
    });
    const run = await runAgent(task);
    lastRun.value = run;
    runLabel.value = run.run_id || "run completed";
    await hydrateDecisionDebugger(run);
    updateMessage(assistantMessageId, {
      content: run.final || "完成",
      chips: [
      { text: run.route || "route" },
      { text: run.run_status || "completed", kind: "success" },
      { text: `${run.plan?.length || 0} steps`, kind: "success" },
      ],
    });
    history.value = [{ task, runId: run.run_id || "local" }, ...history.value].slice(0, 6);
    traceStatus.value = "done";
  } catch (error) {
    updateMessage(assistantMessageId, {
      role: "error",
      content: error.message || String(error),
      chips: [{ text: "failed" }],
    });
    traceStatus.value = "failed";
  } finally {
    window.clearInterval(progressTimer);
    running.value = false;
  }
}

function renderPlanBlockMessage(plan) {
  const missingConnections = (plan.connection_requirements || [])
    .filter((item) => item.status === "missing")
    .map((item) => item.connection || item.capability_id)
    .filter(Boolean);
  const missingCapabilities = (plan.missing_capabilities || []).filter(Boolean);
  const confirmations = plan.needs_confirmation || [];
  const parts = ["OS Kernel planned the workflow, but this sandbox is not runtime-ready yet."];
  if (missingConnections.length) parts.push(`Missing connection: ${missingConnections.join(", ")}.`);
  if (missingCapabilities.length) parts.push(`Missing capability: ${missingCapabilities.join(", ")}.`);
  if (confirmations.length) parts.push(`${confirmations.length} permission confirmation(s) are required.`);
  parts.push("Add the missing key or switch back to the default workspace, then run again.");
  return parts.join(" ");
}

async function hydrateDecisionDebugger(run) {
  if (!run?.run_id) return;
  const runId = encodeURIComponent(run.run_id);
  const endpoints = {
    timeline: tenantUrl(`/platform/swarm/runs/${runId}/timeline`),
    whyBlocked: tenantUrl(`/platform/swarm/runs/${runId}/why-blocked/formal_valuation`),
    whyCommitted: tenantUrl(`/platform/swarm/runs/${runId}/why-committed`),
    evidenceGraph: tenantUrl(`/platform/swarm/runs/${runId}/evidence-graph`),
    agentAllocation: tenantUrl(`/platform/swarm/runs/${runId}/agent-allocation`),
    toolEvents: tenantUrl(`/platform/swarm/runs/${runId}/tool-events`),
    permissionEvents: tenantUrl(`/platform/swarm/runs/${runId}/permission-events`),
  };
  const results = await Promise.allSettled(Object.entries(endpoints).map(async ([key, url]) => [key, await apiJson(url)]));
  const data = {};
  for (const result of results) {
    if (result.status === "fulfilled") {
      const [key, value] = result.value;
      data[key] = key === "timeline" ? value.data || [] : value;
    }
  }
  decisionDebugger.value = data;
  await nextTick();
}

function setCommitteePreset(mode) {
  committeeSelectionMode.value = mode;
  if (mode === "all") {
    selectedAgentIds.value = selectableAgents.value.map((agent) => agent.key);
  } else if (mode === "core") {
    const core = new Set(["data_auditor_agent", "fundamental_analyst_agent", "quant_research_agent", "risk_manager_agent", "red_team_agent", "cio_agent"]);
    selectedAgentIds.value = investmentAgents.value.filter((agent) => core.has(agent.key)).map((agent) => agent.key);
  } else {
    selectedAgentIds.value = defaultAgentIds();
  }
}

async function loadRuntimeMeta() {
  try {
    const [health, skillsPayload, toolsPayload] = await Promise.all([fetch("/health"), apiJson("/skills"), apiJson("/tools")]);
    const healthPayload = await health.json().catch(() => ({}));
    apiStatus.value = healthPayload.status === "ok" || health.ok ? "online" : "offline";
    skills.value = skillsPayload.data || [];
    tools.value = toolsPayload.data || [];
  } catch {
    apiStatus.value = "offline";
  }
}

async function loadPlatformConfig() {
  try {
    const [config, catalog, active, agents] = await Promise.all([
      apiJson(tenantUrl("/platform/config")),
      apiJson("/platform/capability-catalog"),
      apiJson(tenantUrl("/platform/capabilities/active")),
      apiJson(tenantUrl("/platform/agents")),
    ]);
    platformConfig.value = config;
    capabilityCatalog.value = catalog.capabilities || [];
    activeCapabilities.value = active.capabilities || [];
    agentPlugins.value = agents.agents || [];
    if (!selectedAgentIds.value.length || committeeSelectionMode.value === "auto_default") {
      selectedAgentIds.value = defaultAgentIds();
    }
  } catch {
    platformConfig.value = { model_providers: [], data_sources: [] };
  }
}

function agentStatus(key) {
  if (!lastRun.value) return "idle";
  if ((lastRun.value.agent_metrics || []).some((metric) => metric.agent === key)) return "done";
  if (key === "committee_discussion" && discussionRows.value.length) return "done";
  if (key === "investment_committee" && lastRun.value.committee_decision) return "done";
  if (key === "writer" && lastRun.value.final) return "done";
  if (key === "critic" && lastRun.value.review) return "done";
  return "idle";
}

function prettyAgent(key) {
  return String(key || "")
    .replaceAll("_agent", "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function redactClientSecrets(value) {
  if (Array.isArray(value)) return value.map(redactClientSecrets);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      /api[_-]?key|token|password|secret|authorization|credential/i.test(key) ? "[redacted]" : redactClientSecrets(item),
    ]),
  );
}

function safeJsonPreview(value) {
  return JSON.stringify(redactClientSecrets(value), null, 2).slice(0, 1600);
}

async function copyLastRun() {
  if (!lastRun.value) return;
  await navigator.clipboard.writeText(JSON.stringify(redactClientSecrets(lastRun.value), null, 2));
  traceStatus.value = "copied";
  window.setTimeout(() => {
    traceStatus.value = "done";
  }, 900);
}

onMounted(async () => {
  await Promise.all([loadRuntimeMeta(), loadPlatformConfig()]);
  resetChat();
});
</script>
