# Implementation Plan

This is the living checklist for the AI-as-OS refactor. Keep it updated as the
platform moves from a fixed multi-agent app to a capability-driven runtime.

## Phase 1 - Current State Map

- [x] Inspect backend, frontend, tests, graph runtime, registries, and dashboard.
- [x] Document current architecture in `docs/architecture/current-state.md`.
- [x] Add this living implementation checklist.

## Phase 2 - Capability Manifest Contract

- [x] Scan `capabilities/*/capability.json`.
- [x] Validate required manifest fields.
- [x] Detect duplicate capability ids.
- [x] Expose capability types, permissions, tools, skills, data packages.
- [x] Add `required_connections`, `agents_path`, `ui`, and permission diagnostics.
- [x] Add tests for invalid manifests, unknown permissions, list-by-type, and missing required connections.
- [x] Move runtime tool registration behind enabled capability tool declarations while preserving unrestricted `ToolRegistry()` for direct unit tests/dev assembly.

## Phase 3 - Agent Manifest Contract

- [x] Discover agent manifests from enabled capabilities.
- [x] Validate malformed manifests and duplicate keys.
- [x] Sort agents by order.
- [x] Filter by enabled capability.
- [x] Support user-selected committee members.
- [x] Add metadata for committee role, required capabilities, required tools, risk level, tags, and UI accent.
- [x] Expose dashboard-safe agent serialization.

## Phase 4 - Connection Control Plane

- [x] Infer model provider and WRDS credentials from raw intake.
- [x] Confirm connection and store secrets through `SecretStore`.
- [x] List active connections without raw secrets.
- [x] Provide connection test and discovery endpoints.
- [x] Route model calls through `ConnectionAwareModelGateway`.
- [x] Add explicit disable/revoke/delete endpoints for connection-control records, including SecretStore cleanup on revoke/delete.
- [x] Add a production-oriented Vault KV-v2 SecretStore adapter selected by `PLATFORM_SECRET_STORE_BACKEND=vault`.

## Phase 5 - Permission Policy

- [x] Define known auto-grant permissions.
- [x] Define confirmation-required permissions.
- [x] Treat unknown permissions as confirmation-required.
- [x] Attach permission decisions to OS plans.
- [x] Evaluate individual tool permissions and required connections during dynamic tool registration.

## Phase 6 - OS Kernel Planning

- [x] Infer general, code, web, WRDS, and investment task intent.
- [x] Infer required capability types.
- [x] Auto-enable low-risk local capabilities.
- [x] Respect disabled capabilities.
- [x] Report missing capabilities and missing connections.
- [x] Generate selected/default committee plans.
- [x] Keep web search disabled for investment by default.
- [x] Add richer task-type taxonomy for portfolio review, document writing, and data analysis.

## Phase 7 - Runtime Materializer

- [x] Build tenant-scoped runtime contexts per run.
- [x] Hot-load active model/data connections.
- [x] Mount enabled capabilities, skills, tools, and agents.
- [x] Expose safe runtime validation issues.
- [x] Include validation issues in run metadata for dashboard trace.
- [x] Add hard preflight blocking before graph execution for selected fatal validation issues.

## Phase 8 - Tool Registry and WRDS Tooling

- [x] Route tool execution through `ToolRegistry`.
- [x] Keep WRDS tools disabled unless WRDS capability and connection are available.
- [x] Provide WRDS capability discovery and company financials tools.
- [x] Sanitize tool args in graph logs.
- [x] Convert all built-in and dynamic tool manifests to include required permissions and required connections, and expose `connection_granted` in public tool metadata.

## Phase 9 - Metric Registry and Data Gate

- [x] Build deterministic WRDS metric registry path.
- [x] Run Data Gate before formal investment conclusions.
- [x] Block or degrade formal valuation when required data is missing.
- [x] Force writer caveats from Data Gate.
- [x] Expand deterministic metric coverage for segment, estimates, and peer comparison packages.

## Phase 10 - Graph Runtime Integration

- [x] Generic graph mode.
- [x] Investment graph mode.
- [x] Committee opening and discussion.
- [x] Selected agent plugins flow from dashboard metadata to graph runtime.
- [x] Critic and final judge outputs are included in run result.
- [x] Replace remaining hard-coded fallback committee seats once all default agents are represented as manifests.

## Phase 11 - Dashboard Integration

- [x] Redacted connection intake.
- [x] OS capabilities panel.
- [x] OS plan panel.
- [x] Agent plugin picker with AI default/Core/All/manual selection.
- [x] Research trace panels for committee, metrics, data gate, and final output.
- [x] Continue visual simplification around a ChatGPT/Claude-like primary compose surface.

## Phase 12 - API Surface

- [x] `/platform/connections/infer`
- [x] `/platform/connections/confirm`
- [x] `/platform/connections`
- [x] `/platform/capability-catalog`
- [x] `/platform/capabilities/resolve`
- [x] `/platform/capabilities/enable`
- [x] `/platform/capabilities/{id}/disable`
- [x] `/platform/capabilities/active`
- [x] `/platform/agents`
- [x] `/platform/os/plan`
- [x] `/agents/run`
- [x] Add first-class `/runs/{run_id}/trace` after persistent run store exists.

## Phase 13 - Trace and Observability

- [x] Run result includes OS plan, active capabilities, selected agents, metrics, data gate, debate, critic, and final answer.
- [x] Audit log records run summaries without raw secrets.
- [x] Agent metrics include model, duration, status, and failure reason.
- [x] Add formal PheroOS event schema and lifecycle contract.
- [x] Add SQLite-backed swarm trace store with timeline, why-blocked, why-committed, evidence-graph, and agent-allocation queries.
- [x] Expand SQLite persistence for tool and permission events beyond the initial schema and expose decision-debugger query endpoints.
- [x] Add run-level tenant index and tenant-scoped query checks for first-class run trace and swarm decision-debugger APIs.
- [x] Add tenant-scoped JSONL signal/event readers and tenant-aware agent-profile APIs.

## Phase 14 - Documentation

- [x] README documents product shape and commands.
- [x] `docs/architecture.md` documents layers and cohesion rules.
- [x] `docs/architecture/current-state.md` records current state and gaps.
- [x] `docs/extensions.md` covers capability and agent authoring basics.
- [x] Split detailed docs into dedicated files for connection control, OS kernel, runtime materializer, dashboard, and security.

## Phase 15 - Tests and Verification

- [x] Capability registry tests.
- [x] Agent registry tests.
- [x] Connection control tests.
- [x] Permission policy tests.
- [x] OS kernel tests.
- [x] Runtime materializer tests.
- [x] Graph runtime tests.
- [x] API tests.
- [x] Add browser-level dashboard visual regression tests.
- [x] Add browser-level dashboard tests to CI.

## Phase 16 - Swarm Governance Layer

- [x] Add typed pheromone signal primitives under `runtime/swarm/`.
- [x] Add run-level `PheromoneFieldManager` snapshots and trace events.
- [x] Convert Data Gate failures, publication blocks, and formal-valuation limits into stop-signals.
- [x] Convert permission decisions into permission / stop-signal governance signals.
- [x] Add candidate-based quorum trace for committee decisions.
- [x] Include swarm governance fields in `/agents/run` responses.
- [x] Add Dashboard Swarm Governance trace panel.
- [x] Add tests for Data Gate stop-signals, permission stop-signals, writer guardrails, and quorum fallback.
- [x] Add deterministic PatrollerGate preflight report and signals.
- [x] Add Stage 0 `InputEnvelope` and Stage 1 input preflight normalization before OS planning.
- [x] Convert input secret / prompt-injection detections into contamination and quarantine signals.
- [x] Convert OS Kernel `swarm_plan` target demands and activated agents into PheroOS demand / lane-assignment signals.
- [x] Convert enabled capability and model-routing handles into runtime field initialization signals.
- [x] Add deterministic response-threshold allocation trace for committee activation reasons.
- [x] Add PatrollerGate as a pre-executor graph node.
- [x] Add response-threshold dynamic committee allocation using agent profile history.
- [x] Persist swarm signals and events to local JSONL trace logs.
- [x] Expose swarm signals, events, and agent profiles through platform APIs.
- [x] Scope swarm signal/event/profile platform APIs by tenant while preserving legacy `default` local records.
- [x] Add manifest-scoped `emitted_signals` for committee agents.
- [x] Validate agent-emitted signals as unverified/contested proposals with diagnostics.
- [x] Add deterministic verifier promotion for contested agent stop-signal proposals.
- [x] Add browser-level visual tests for the Swarm Governance panel.
- [x] Add canonical target registry and signal authority levels.
- [x] Add Evidence Graph separating facts, proposals, blockers, candidate decisions, and writer output permissions.
- [x] Surface Evidence Graph in `/agents/run` and the dashboard Swarm panel.
- [x] Add encounter-rate, bottleneck recruitment, trust-badge, social-immunity, and worker-policing protocols.
- [x] Feed protocol reports into response-threshold allocation and dashboard trace.
- [x] Add arousal, lane scheduling, homeostasis, maturity lifecycle, independent-scout quorum, and artifact-cue protocols.
- [x] Surface all PHEROOS_GOAL protocol diagnostics in `/agents/run` and dashboard trace.
- [x] Add canonical target namespace, authority levels, lifecycle states, and signal/event contracts.
- [x] Move swarm lifecycle events to typed JSONL + SQLite trace-store persistence.
- [x] Add Swarm Controller to convert encounter/bottleneck/arousal/homeostasis/lane reports into executable scheduling, writer, verifier, and quorum policies.
- [x] Add stop-signal resolution so resolved/rejected lifecycle states no longer block quorum, tools, or writer guardrails.
- [x] Add independence-gated quorum fallback that can force `Insufficient Data` when support is too correlated.
- [x] Add PheroOS governance caste agent manifests: scheduler, receiver, evidence steward, quorum marshal, social immunity, protocol police, tool sentinel, outcome memory, sandbox auditor, and independent scout.
- [x] Add deterministic receiver/evidence/tool-health/capability-sandbox/outcome-memory/quorum-marshal modules and expose `swarm_governance_trace`.
- [x] Surface governance caste reports in `/agents/run` and Dashboard Swarm Governance / Agent Plugins views.
- [x] Add runtime enforcement contracts for Protocol Police, Evidence Steward, Quorum Marshal, Writer Guardrails, Final Judge Guardrails, and Outcome Memory boundary tests.
- [x] Add `governance_contracts`, `governance_results`, and `enforcement_bus` so governance actors expose normalized runtime contracts, blocked targets, writer constraints, final-judge checks, trace events, and blocking stop-signals.
- [x] Add `evidence_contract` and upgrade Evidence Graph `writer_contract` so Writer/Final Judge are constrained by verified claims, caveated claims, blocked claims, required caveats, forbidden phrases, and allowed metrics.
- [x] Split remaining business-heavy graph nodes into capability-owned workflow entrypoints.
  - [x] First routing pass: compile enabled capability workflow descriptors into graph node order and expose `workflow_routing` in run output.
  - [x] Node policy pass: capability workflow descriptors can require/disable graph nodes and override legacy orchestration flags.
  - [x] First node extraction pass: move Data Gate, deterministic research, and deterministic quant node implementations into `capabilities/value-investing-research/runtime_nodes.py`.
  - [x] CIO decision extraction pass: move investment committee decision, quorum, evidence graph, and enforcement-bus closure into `capabilities/value-investing-research/runtime_nodes.py`.
  - [x] Opening/discussion extraction pass: move committee member opening execution, governance caste activation, and challenge/response debate moderation into `capabilities/value-investing-research/runtime_nodes.py`.
  - [x] WRDS node extraction pass: move direct WRDS retrieval action planning and retrieval-only rendering into `capabilities/wrds-financial-data/runtime_nodes.py`.
  - [x] WRDS support extraction pass: move WRDS action normalization, safe arg redaction, and final rendering out of `runtime/graph.py` into the WRDS capability node module.
  - [x] Output-chain extraction pass: move Critic, Writer, and Final Judge node execution into `runtime/nodes/output_chain.py` while preserving Data Gate, Evidence Contract, and PheroOS guardrails.
  - [x] Preflight/memory extraction pass: move PatrollerGate and Memory node bodies into `runtime/nodes/preflight.py` and `runtime/nodes/memory.py`.
  - [x] Move investment node implementations out of `runtime/graph.py` into capability-owned workflow modules.
  - [x] Move investment committee support helpers out of `runtime/graph.py` into `capabilities/value-investing-research/support.py`.

## Phase 17 - PheroOS Hardening Roadmap

- [x] Phase 1 P0: standardize target namespace, authority levels, signal lifecycle, and blocking state contracts.
- [x] Phase 2 foundation: add `runtime/swarm_pipeline.py`, `runtime/writer_guardrails.py`, `runtime/final_judge_guardrails.py`, plus `runtime/nodes/` and `runtime/workflows/` namespaces.
- [x] Phase 3 pilot: add workflow/data-contract/evidence-adapter/UI entrypoints to `value-investing-research`.
- [x] Phase 3 runtime bridge: add `runtime/capability_runtime.py` and `runtime/workflows/loader.py` so enabled capability entrypoints are safely loaded into `RuntimeContext`.
- [x] Phase 4 foundation: persist swarm decisions to SQLite and expose decision-debugger APIs.
- [x] Phase 4 replay pass: reconstruct pheromone snapshots from SQLite trace-store signals and expose `/platform/swarm/runs/{run_id}/pheromone-snapshot`.
- [x] Phase 5 foundation: add Dashboard Decision Debugger panels for Why This Candidate, Why Blocked, Evidence Graph, Why This Agent, safety events, and trace-store hydration.
- [x] Phase 5 controller pass: make PheroOS protocol reports actionable through `runtime/swarm/controllers.py`.
- [x] Phase 5 follow-up: make Evidence Graph nodes/edges clickable and add drill-down drawers for each blocker/candidate.
- [x] Phase 5 goal-router pass: route user intent into canonical PheroOS targets and recruit agents through response-threshold allocation before graph execution.
- [x] Phase 6 foundation: add third-party capability security diagnostics with trust level, sandbox policy, allowed imports, network allowlists, checksum status, and sandbox-auditor enforcement.
- [x] Phase 7: add failure-path tests for writer/quorum mismatch, unsupported claim publication, raw WRDS leaks, protocol-police blockers, and process-only outcome memory.
- [x] Phase 7 boundary tests: add static tests proving provider SDK calls, arbitrary network clients, WRDS access, and shell execution stay confined to approved gateway/tool layers.
- [x] Phase 7 evidence tests: add Writer Evidence Contract tests for verified claims, caveated claims, blocked/unsupported claims, required caveats, and replayed signal snapshots.
- [x] Phase 7 evidence-link follow-up: require claim-to-metric matching before Evidence Graph marks a claim verified and expose `evidence_sources` in writer contracts.
- [x] Phase 7 model-gateway follow-up: add boundary tests for LiteLLM instantiation confinement and capability manifest `model_calls: gateway_only` sandbox declarations.

## Phase 18 - Capability Agent Roadmap

- [x] Add `code-development` capability manifest with workflow, data-contract, evidence-adapter, and UI entrypoints.
- [x] Add 11 code-development agent manifests for scout, architecture, planning, coding, tests, interface, security, dependency, review, regression, and docs/changelog roles.
- [x] Add `compliance-workflow` capability manifest with read-only policy workflow, policy contract, evidence adapter, and UI entrypoint.
- [x] Add 9 compliance workflow agent manifests for policy, obligation, privacy/DLP, RBAC, approval, evidence, escalation, retention, and human-in-loop roles.
- [x] Add `evidence-research` capability manifest with claim-first workflow, data contract, evidence adapter, and UI entrypoint.
- [x] Add 6 evidence research agent manifests for claim decomposition, retrieval, source quality, evidence stewardship, citation audit, and contradiction mapping.
- [x] Extend OS Kernel taxonomy for `compliance_workflow` and `evidence_research`.
- [x] Route code tasks to `code-development` rather than the old FastAPI-only skill.
- [x] De-duplicate OS Kernel confirmation prompts when one capability satisfies multiple required capability types.
- [x] Add registry and OS Kernel tests for the new roadmap capabilities.
- [x] Materialize dedicated code/compliance/evidence tool allowlists into `RuntimeContext`.
- [x] Materialize compliance/evidence agent plugins and capability runtime descriptors into `RuntimeContext`.
- [x] Prove evidence-research can list retrieval tools while arbitrary network execution remains denied until explicitly granted.
- [x] Add graph-node routing bridge for code-development, compliance-workflow, and evidence-research workflow descriptors while preserving domain node order for traces.
- [x] Add workflow modules for code-development, compliance-workflow, and evidence-research with deterministic execution plans and domain trace metadata.
- [x] Dispatch compliance/evidence research nodes to capability-specific prompts instead of value-investing research prompts.
- [x] Add Writer/Final Judge domain workflow guardrails for failed code tests, unapproved compliance external action, and evidence gaps.
- [x] Add PheroOS canonical targets for code/compliance/research workflow gates.
- [x] Add authority/lifecycle support for domain blocking agents and pending approval / rejected-by-gate / accepted patch states.
- [x] Add domain workflow event types for code/compliance/evidence trace logging.
- [x] Add Protocol Police checks for code success overclaims, compliance external-action approval bypass, and evidence-research overclaims.
- [x] Add fully specialized mutation/extraction/retrieval node bodies for code-development, compliance-workflow, and evidence-research graph modes.
- [x] Add Dashboard Domain Workflow trace panel and capability-grouped agent plugin chooser for code, compliance, and evidence workflows.
- [x] Add explicit human approval request UI for OS permissions and compliance/external-action workflow confirmations.

## Phase 19 - PheroOS Execution Loop

- [x] Add `runtime/swarm/execution_loop.py` for deterministic observe → propose → verify → schedule loops.
- [x] Convert OS Kernel `swarm_plan` activated agents into runtime loop waves rather than leaving them as passive metadata.
- [x] Validate loop-generated agent proposals through manifest-scoped `signal_emit_permissions`.
- [x] Keep all loop agent proposals unverified/contested and non-blocking unless deterministic system gates promote them.
- [x] Surface `swarm_execution_loop` in typed state, `/agents/run`, pheromone field snapshots, and `swarm_protocol_trace`.
- [x] Reuse existing input envelope/preflight metadata during runtime delegation so one request has one stable redacted input contract.
- [x] Add regression tests for loop startup, stop-signal downgrade, field updates, and protocol trace events.
