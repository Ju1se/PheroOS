# PheroOS Protocol-Core Migration Inventory

## Evidence Captured Before Continuing

- Branch: `codex/protocol-core-migration`
- Baseline command: `.venv/bin/pytest -q --maxfail=20`
- Baseline result: 873 passed, 11 failed, 1 warning
- Baseline failing areas:
  - old conformance wrapper for previous toy capability
  - old runtime domain-neutrality guard against `runtime/`
  - old graph/runtime value-research fallback routing
  - old OSKernel app/domain committee planning expectations
  - old FastAPI platform capability endpoint expectations

These failures are not migration blockers. The migration contract explicitly says not to preserve old app behavior to satisfy old tests.

## Classification Rules

- `CORE_KEEP`: already aligned with the final protocol-core repository.
- `CORE_REWRITE`: conceptually useful, but must be rewritten into `pheroos/`, `schemas/`, `examples/toy-protocol/`, or protocol-core docs.
- `DELETE_APP`: app shell, endpoint/runtime server, dashboard, frontend, local wrappers, product API.
- `DELETE_DOMAIN`: domain/reference capability implementation or provider-specific behavior not allowed in core.
- `DELETE_DOCS`: documentation describing deleted app/runtime/domain behavior.
- `DELETE_TESTS`: tests for deleted app/runtime/domain behavior.

## CORE_KEEP

Keep these files and directories:

- `LICENSE`
- `CODE_OF_CONDUCT.md`
- `SECURITY.md`
- `CONTRIBUTING.md` after protocol-core wording is checked
- `.gitignore`
- `.github/` after workflow and PR template are rewritten for protocol-core tests
- `.agent/PLANS.md`
- `docs/migration-inventory.md`
- `examples/toy-protocol/`
- `schemas/protocol.schema.json`
- `schemas/kernel.schema.json`
- `schemas/driver.schema.json`
- `schemas/trace.schema.json`
- `pheroos/__init__.py`
- `pheroos/protocol/`
- `pheroos/kernel/`
- `pheroos/governance/`
- `pheroos/drivers/`
- `pheroos/conformance/`
- `pheroos/cli/`

## CORE_REWRITE

Rewrite or replace these files and directories for protocol-core scope:

- `README.md`
- `pyproject.toml`
- `.github/workflows/tests.yml`
- `.github/pull_request_template.md`
- `AGENTS.md`
- `.env.example`
- `pheroos/protocol/manifest.py`
- `pheroos/protocol/schema.py`
- `pheroos/protocol/validation.py`
- existing early `pheroos/drivers/*.py`
- previous `schemas/pheroos.*.schema.json` files, replaced by core schema names
- previous `docs/protocol/*`, replaced by minimal protocol ABI docs
- previous `docs/kernel/*`, replaced by minimal kernel ABI docs
- previous `docs/drivers/*`, replaced by minimal driver ABI docs
- new `docs/governance/`
- new `docs/conformance/`
- new `docs/security/`
- new `docs/process/`
- new `docs/removed-app-runtime.md`
- tests under:
  - `tests/protocol/`
  - `tests/kernel/`
  - `tests/governance/`
  - `tests/drivers/`
  - `tests/conformance/`

## DELETE_APP

Delete these app/runtime/product surfaces:

- `app/`
- `frontend/`
- `static/`
- `server.py`
- `package.json`
- `package-lock.json`
- `vite.config.js`
- `configs/litellm.yaml`
- `configs/runtime.yaml`
- `distros/`
- `scripts/start_api.sh`
- `scripts/start_litellm.sh`
- `scripts/restart_litellm.sh`
- `runtime/graph.py`
- `runtime/factory.py`
- `runtime/llm.py`
- `runtime/model_gateway.py`
- `runtime/tool_registry.py`
- `runtime/nodes/`
- `runtime/workflows/`
- `runtime/swarm_pipeline.py`
- `local_agent_platform.egg-info/`
- generated dashboard artifacts under `output/`, `logs/`, and local frontend image captures

## DELETE_DOMAIN

Delete these domain/provider/reference implementations from the core repository:

- `capabilities/`
- `skills/`
- `tools/`
- `pips/` if not rewritten into `docs/process/`
- all `runtime/legacy_*`
- `runtime/wrds_company_planner.py`
- `runtime/wrds_planner.py`
- `runtime/financial_data_sources.py`
- `runtime/data_gate.py`
- `runtime/output_contract.py`
- `runtime/writer_guardrails.py`
- `runtime/final_judge_guardrails.py`
- `runtime/research_selection.py`
- `runtime/web_research_planner.py`
- provider/data/source-specific runtime helpers
- root-level research/report artifacts:
  - `AI_AS_OS_PHEROOS_COMPLETENESS_AUDIT.md`
  - `AI_AS_OS_PHEROOS_SYSTEM_AUDIT.md`
  - `PHEROOS_GOAL.md`
  - `PLANS.md`
  - `MU_investment_analysis.md`
  - `NVIDIA_最终评审报告.md`
  - `NVIDIA_研究报告.md`
  - `apple_critic_review.md`
  - `apple_domain_expert_analysis.md`
  - `critic_review.md`
  - `domain_assessment.md`
  - `domain_investment_assessment_sndk.md`
  - `final_judge_assessment.md`
  - `final_report_gigadevice.md`
  - `investment_research_report_sndk.md`
  - `quant_analysis.md`
  - `quant_analysis_sndk.md`
  - `research_evidence_packet.md`
  - `wus_printed_circuit_deep_analysis_report.md`

## DELETE_DOCS

Delete or replace docs that describe the removed local app/runtime/domain implementation:

- `docs/agent-authoring.md`
- `docs/architecture.md`
- `docs/architecture/current-state.md`
- `docs/architecture/kernel-user-driver-boundaries.md`
- `docs/architecture/pheroos-kernel-map.md`
- `docs/capability-agent-roadmap.md`
- `docs/capability-authoring.md`
- `docs/capability_runtime.md`
- `docs/connection-control-plane.md`
- `docs/dashboard.md`
- `docs/decision_debugger.md`
- `docs/examples/`
- `docs/extensions.md`
- `docs/investment-research-workflow.md`
- `docs/known-gaps.md`
- `docs/migration_from_static_rules.md`
- `docs/multi-agent-audit-checklist.md`
- `docs/open_multi_agent_protocol_refactor_goal.md`
- `docs/os-kernel.md`
- `docs/pheroos-acceptance-audit.md`
- `docs/pheroos_protocol_manifest.md`
- `docs/pheroos_protocol_migration.md`
- `docs/pheroos_protocol_migration_plan.md`
- `docs/pheroos_swarm_loop.md`
- `docs/public-financial-data-sources.md`
- `docs/runtime-materializer.md`
- `docs/security-and-permissions.md`
- `docs/swarm-governance.md`
- `docs/swarm_signal_spec.md`
- domain/reference examples formerly under `docs/protocol/examples/`

The replacement documentation set is:

- `docs/protocol/`
- `docs/kernel/`
- `docs/governance/`
- `docs/drivers/`
- `docs/conformance/`
- `docs/security/`
- `docs/process/`
- `docs/removed-app-runtime.md`

## DELETE_TESTS

Delete old tests for removed behavior:

- `tests/browser/`
- `tests/swarm/`
- `tests/test_api.py`
- `tests/test_agent_registry.py`
- `tests/test_architecture_boundaries.py`
- `tests/test_audit_log.py`
- `tests/test_capability_registry.py`
- `tests/test_capability_runtime.py`
- `tests/test_connection_control.py`
- `tests/test_data_gate.py`
- `tests/test_domain_workflow_guardrails.py`
- `tests/test_evidence_contract.py`
- `tests/test_extensibility.py`
- `tests/test_generic_output_policy.py`
- `tests/test_graph.py`
- `tests/test_input_envelope.py`
- `tests/test_model_gateway.py`
- `tests/test_multi_agent_audit.py`
- `tests/test_os_kernel.py`
- `tests/test_permission_policy.py`
- `tests/test_platform_capabilities.py`
- `tests/test_platform_config.py`
- `tests/test_protocol_manifest.py`
- `tests/test_public_financial_tools.py`
- `tests/test_redaction.py`
- `tests/test_research_selection.py`
- `tests/test_runtime_materializer.py`
- `tests/test_safe_tools.py`
- `tests/test_secret_store.py`
- `tests/test_skill_loader.py`
- `tests/test_swarm_execution_loop.py`
- `tests/test_swarm_governance.py`
- `tests/test_swarm_trace_store.py`
- `tests/test_tool_policy_resolver.py`
- `tests/test_toy_capability.py`
- `tests/test_web_research_planner.py`
- `tests/test_web_tools.py`
- `tests/test_wrds_company_planner.py`
- `tests/test_wrds_planner.py`
- `tests/test_wrds_tools.py`
- previous `tests/conformance/test_pheroos_minimal.py`
- previous `tests/conformance/test_pheroos_public_abi.py`

Replacement tests are protocol-core tests only:

- `tests/protocol/test_manifest_validation.py`
- `tests/protocol/test_candidate_declaration.py`
- `tests/protocol/test_quorum_policy.py`
- `tests/kernel/test_os_plan.py`
- `tests/kernel/test_runtime_context.py`
- `tests/kernel/test_kernel_import_boundary.py`
- `tests/governance/test_stop_signal.py`
- `tests/governance/test_quorum_commit.py`
- `tests/governance/test_recovery_policy.py`
- `tests/governance/test_output_contract.py`
- `tests/governance/test_trace_event.py`
- `tests/drivers/test_driver_descriptor.py`
- `tests/drivers/test_driver_lifecycle.py`
- `tests/conformance/test_toy_protocol_conformance.py`
- `tests/conformance/test_domain_neutrality.py`

## Checkpoints

1. Package checkpoint: finish `pheroos/` core package and import boundary tests.
2. Conformance checkpoint: make `pheroos validate` and `pheroos conformance` pass for `examples/toy-protocol`.
3. Metadata checkpoint: update `pyproject.toml`, README, GitHub workflow, and PR template.
4. Documentation checkpoint: write core docs and `docs/removed-app-runtime.md`.
5. Test checkpoint: add replacement tests and run full pytest.
6. Audit checkpoint: run CLI, import, domain-neutrality, `git diff --check`, and final status review.
