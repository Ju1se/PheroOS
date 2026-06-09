# Architecture

PheroOS is organized as a protocol-governed AI-as-OS kernel plus a reference
runtime. The goal is to let contributors replace model providers, tools, data
providers, skills, capabilities, API shells, and runtime hosts without editing
protocol authority or kernel governance.

The public architecture separates:

- **PheroOS Protocol**: manifest, schemas, targets, candidates, evidence,
  quorum, recovery, output, and trace contracts.
- **PheroOS Kernel**: OS planning, permissioning, runtime materialization,
  connection handles, tool exposure, and validation.
- **PheroOS Driver Model**: model, tool, data provider, storage, and secret
  store adapters.
- **PheroOS Reference Runtime**: the current FastAPI/LangGraph/dashboard host.
- **Capabilities**: domain or workflow modules mounted by protocol, not core
  assumptions.

## Layers

```text
app/
  FastAPI routes and static frontend for the reference runtime

pheroos/
  protocol/           public protocol ABI wrappers
  drivers/            public driver contract models and helpers

runtime/
  graph.py              LangGraph workflow and node policy
  ports.py              public extension interfaces
  factory.py            runtime assembly from swappable components
  capability_registry.py local capability plugin catalog and tenant enablement state
  agent_registry.py      agent manifests shipped inside capabilities
  permission_policy.py  capability permission and auto-enable policy
  os_kernel.py          AI OS planning: intent -> capability gaps -> runtime plan
  llm.py                LiteLLM/OpenAI-compatible adapter
  model_gateway.py      direct OpenAI-compatible gateway from user connections
  connection_control.py AI-as-OS connection registry and capability index
  secret_store.py       replaceable local/Vault secret store adapters
  runtime_context.py    per-run tenant runtime materialization
  swarm/                typed pheromone field, stop-signals, quorum trace
  tool_registry.py      tool dispatch boundary
  skill_loader.py       SKILL.md registry
  data_gate.py          deterministic data policy and output permissions
  wrds_planner.py       legacy/reference WRDS data package planning

capabilities/
  */capability.json     reviewed local capability manifests
  */agents/*.json       pluggable agent manifests
  */workflow.py         optional capability-owned workflow descriptor
  */data_contract.py    optional data/source contract descriptor
  */evidence_adapter.py optional evidence graph adapter descriptor
  */ui.schema.json      optional dashboard schema

tools/
  safe_tools.py         workspace-safe file/test tools
  web_tools.py          public web search/fetch adapter
  wrds_tools.py         WRDS read-only reference data-provider driver

skills/
  */SKILL.md            agent-readable capability instructions
```

## Dependency Rule

High-level modules may depend on ports, but should avoid importing concrete
adapters unless they are factory/bootstrap code.

```text
API/CLI -> runtime.factory -> runtime.graph
runtime.graph -> runtime.ports + policy modules
adapters -> external services
```

## Runtime Flow

Every run can now begin with an OS planning pass:

```text
user intent
-> OSKernel
-> required capability types
-> CapabilityRegistry local match
-> PermissionPolicy
-> low-risk auto enable / high-risk confirmation
-> RuntimeMaterializer
-> AgentRegistry filters selectable agents by enabled capability
-> Dashboard user selection / AI default committee plan
-> Swarm Governance Layer emits constraints, stop-signals, and quorum state
-> AgentRuntime
```

The kernel is a control plane component only. It does not perform financial
analysis, document writing, or data analysis directly. It maps task taxonomy to
capability requirements, including `portfolio_review`, `document_writing`, and
`data_analysis`, then lets RuntimeMaterializer and AgentRuntime execute through
enabled capabilities and tools.

General tasks stay lightweight:

```text
orchestrator -> optional executor/research/quant/domain -> critic -> writer
```

Investment/company tasks use the WRDS-only path:

```text
orchestrator
-> executor: wrds_company_financials
-> data_gate
-> deterministic research/quant
-> committee_opening
-> committee_discussion
-> investment_committee
-> critic
-> writer
-> optional final_judge
```

If Data Gate blocks publication, the workflow returns a defect or readiness
memo instead of a formal investment report.

The Swarm Governance Layer turns Data Gate and Permission Policy results into
typed signals. Blocking stop-signals such as `data_gate`, `report_publication`,
`formal_valuation`, `trade:execute`, or `tool:web_search` are included in the
run trace and must be obeyed by Writer and Final Judge. Committee decisions also
produce a candidate-based `quorum_trace`, so the final output can explain why a
candidate was committed or blocked.

Evidence Graph is now also a Writer input contract rather than a display-only
artifact. `runtime/swarm/evidence_contract.py` derives verified claims,
caveated claims, blocked claims, required caveats, forbidden phrases, and
allowed metrics from Data Gate, Metric Registry, Evidence Steward, Quorum, and
governance results. Writer and Final Judge guardrails reject drafts that violate
that contract.

## Public Extension Points

- `capabilities/<id>/capability.json`
- `capabilities/<id>/agents/*.json`
- `capabilities/<id>/workflow.py`
- `capabilities/<id>/data_contract.py`
- `capabilities/<id>/evidence_adapter.py`
- `capabilities/<id>/ui.schema.json`
- `runtime.capability_registry.CapabilityRegistry`
- `runtime.capability_runtime.load_capability_runtime_descriptors`
- `runtime.agent_registry.AgentRegistry`
- `runtime.permission_policy.evaluate_capability_permissions`
- `runtime.os_kernel.OSKernel`
- `runtime.ports.ChatModelClient`
- `runtime.ports.ToolExecutor`
- `runtime.ports.SkillRegistry`
- `runtime.factory.RuntimeComponents`
- `runtime.tool_registry.ToolRegistry(extra_tools=..., extra_tool_manifest=...)`
- `runtime.platform_config.PlatformConfigStore`
- `runtime.swarm.PheromoneFieldManager`

## Capability Entrypoints

Capabilities are now more than catalog metadata. Enabled capability manifests can
declare runtime entrypoints and the materializer loads them into
`RuntimeContext.capability_runtime`:

- `workflow`: graph-mode and ordered-node descriptor.
- `data_contract`: source mode, required data packages, forbidden claims, and
  confidence ceiling.
- `evidence_adapter`: accepted/proposal/blocked evidence sources and claim
  requirements.
- `ui_schema`: dashboard schema for plugin-specific surfaces.

The loader in `runtime/capability_runtime.py` only accepts local entrypoint paths
inside the capability directory, preventing path escape from third-party
capabilities. `runtime/workflows/loader.py` exposes workflow descriptors as the
bridge toward capability-owned workflows.

Capability manifests also declare the plugin security contract:

- `trust_level`
- `sandbox.network`
- `sandbox.filesystem`
- `sandbox.secrets`
- `sandbox.model_calls`
- `sandbox.tools`
- `allowed_imports`
- `network_allowlist`
- `signature` / `checksum`

`runtime/capability_manifest_security.py` validates those declarations and
computes a stable directory checksum. The PheroOS capability sandbox auditor
uses the diagnostics to quarantine untrusted plugins that request direct secret
access, direct model/tool calls, arbitrary network, filesystem write access,
dangerous imports, or blocking signal authority.

## Capability-Owned Workflow Routing

Enabled capabilities can now influence graph routing through their workflow
descriptor. `runtime/workflows/routing.py` normalizes descriptor nodes such as
`executor_wrds`, `deterministic_research`, and `deterministic_quant` into
LangGraph node names. It also reads `node_policy` so a capability can require
or disable nodes such as `memory_agent`, `domain_expert`, `critic`, or
`final_judge`. `runtime/graph.py` consumes this order and policy through
`next_required_node()` and the `should_run_*` predicates, then exposes the
selected route in `workflow_routing`.

This is the bridge from a fixed investment graph toward capability-owned
workflows: the ordered business path and node activation policy come from the
enabled capability entrypoint rather than a hard-coded list.

The value-investing capability has also started owning node implementations via
`node_entrypoints`. Extracted nodes live in
`capabilities/value-investing-research/runtime_nodes.py`:

- `data_gate_node`
- `research_agent_node`
- `quant_agent_node`
- `committee_opening_node`
- `committee_discussion_node`
- `investment_committee_node`

`runtime/graph.py` still provides LangGraph orchestration and shared routing
helpers, but the investment data path, committee opening, multi-round debate
moderator, and CIO decision closure are now
capability-owned. The extracted opening node owns member execution, committee
opening prompts, response-threshold allocation, governance caste activation,
agent signal verification, policing, and enforcement-bus setup. The extracted
discussion node owns the challenge/response moderator prompt and debate-round
termination logic. The extracted CIO node owns the final committee synthesis
prompt plus quorum, source-independence adjustment, quorum marshal, Evidence
Graph, governance results, and enforcement-bus closure.

The same capability now exposes
`capabilities/value-investing-research/support.py` through its
`runtime_support` entrypoint. That module owns committee member selection,
committee context construction, opening/decision JSON parsing, scorecard
normalization, fallback decision shaping, and WRDS-only deterministic
research/quant payload construction. `runtime/graph.py` keeps compatibility
wrappers for legacy imports, but the investment-specific helper logic is no
longer implemented inside the graph file.

Direct WRDS retrieval is also capability-owned. `wrds-financial-data` exposes a
`runtime_nodes` entrypoint whose `wrds_agent_node` owns the single-action WRDS
planner, safe action normalization, ToolRegistry execution, redacted WRDS
arguments, and retrieval-only final rendering. Core `runtime/graph.py` delegates
to this node and no longer contains the WRDS agent prompt, action planner,
action normalization table, argument redaction helper, or retrieval renderer.

The generic output safety chain now lives in `runtime/nodes/output_chain.py`.
`critic_node`, `writer_node`, and `final_judge_node` own the verifier prompt,
Data Gate / Patroller / stop-signal writer blocking, Evidence Contract
guardrails, final-judge guardrails, and artifact-cue governance closeout.
Core `runtime/graph.py` delegates to those nodes so it remains a workflow
orchestrator rather than a second business-policy kernel.

Preflight and context nodes are also being pulled into `runtime/nodes/`.
`preflight.py` owns the deterministic PatrollerGate node, while `memory.py`
owns memory-context assembly and metrics. The graph still owns routing
predicates and shared helpers, but concrete node bodies now live outside the
orchestrator wherever possible.

## BYOK/BYOD Platform Mode

The platform should be provider-neutral. Users can bring their own model API
keys and financial data APIs through the dashboard. The runtime should treat
those credentials as connection metadata, not as hard-coded product defaults.

```text
dashboard key paste
-> /platform/connections/infer
-> /platform/connections/confirm
-> ConnectionControlPlane + SecretStore
-> /platform/os/plan
-> CapabilityRegistry + OSKernel
-> RuntimeMaterializer per run
-> model/data/tool adapters
-> agent committee workflow
```

Current local adapter:

- Stores active connection records in `.local/connections.json`.
- Stores encrypted secrets in `.local/secrets.json`.
- Redacts secrets from all read APIs and audit surfaces.
- Keeps local files owner-only when supported by the OS.
- Is intended for localhost/self-hosted development.

Production deployments can set `PLATFORM_SECRET_STORE_BACKEND=vault` to use the
Vault KV-v2 adapter while preserving the `/platform/*` API shape. The local
connection record keeps only a `vault:*` `secret_ref` and redacted metadata; the
runtime resolves plaintext only through the `SecretStore` interface when a model
or data adapter needs it.

## Cohesion Rules

- Capability manifests declare resources and permissions. They do not modify
  orchestrator logic directly.
- Agent manifests declare role, prompt focus, model route, and default committee
  membership. The workflow consumes selected agent ids rather than hard-coded
  committee seats.
- OS Kernel plans and enables capabilities. It does not call tools or author
  business conclusions.
- Tool adapters execute and validate IO. They do not make investment judgments.
- Data Gate validates data contracts and metric registry policy. It does not
  write final prose.
- Committee agents make domain judgments. They do not call tools directly.
- Writer formats verified outputs. It must not invent new facts.
- API routes serialize requests/responses. They do not implement workflow logic.
