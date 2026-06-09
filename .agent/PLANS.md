# ExecPlans

Use this file for long-running features, architectural refactors, protocol
migrations, or changes touching more than three subsystems.

An ExecPlan is a living implementation plan. Keep it current as work proceeds.
Do not use it for ordinary small fixes.

## Template

```md
# ExecPlan: <short goal>

## User-visible goal

Describe the outcome in user-facing terms.

## Current architecture facts

- Fact with file/function evidence.
- Fact with file/function evidence.

## Files to inspect

- `path/to/file.py`
- `path/to/other_file.py`

## Milestones

1. Baseline and audit.
2. Implementation slice.
3. Tests and docs.
4. Final validation.

## Tests to run

- `.venv/bin/pytest tests/...`
- `.venv/bin/pytest`

## Migration and compatibility notes

- Legacy behavior to preserve.
- Compatibility fields or shims.
- Trace or lineage requirements.

## Progress log

- YYYY-MM-DD: Started.

## Final validation checklist

- [ ] Relevant focused tests pass.
- [ ] Full test suite passes, or failures are documented as pre-existing.
- [ ] Docs updated where public behavior changed.
- [ ] Compatibility risks summarized.
- [ ] No new domain behavior was added to core runtime when a protocol or
      capability boundary could express it.
```

# ExecPlan: PheroOS Protocol-Core Destructive Migration

## User-visible goal

Complete `docs/architecture/pheroos-protocol-core-migration-goal.md` by turning
this repository into a small protocol/kernel/conformance package and deleting
the old local app/runtime/domain surfaces.

## Current architecture facts

- Current branch: `codex/protocol-core-migration`.
- Baseline before destructive migration: `.venv/bin/pytest -q --maxfail=20`
  reported 873 passed, 11 failed, and one upstream Pydantic/Python warning.
- `pyproject.toml` still installs `app*`, `runtime*`, `tools*`, and `pheroos*`,
  and still depends on FastAPI, LangGraph, uvicorn, psycopg2, and app-runtime
  packages.
- Existing `pheroos/` is partial and does not yet expose the full protocol,
  kernel, governance, driver, conformance, and CLI package structure required
  by the migration goal.
- Old app/runtime/domain directories still exist and contain FastAPI,
  LangGraph, provider routing, dashboard, WRDS, and value-investing behavior.

## Files to inspect

- `docs/architecture/pheroos-protocol-core-migration-goal.md`
- `pyproject.toml`
- `README.md`
- `pheroos/`
- `schemas/`
- `examples/`
- `tests/`
- `.github/workflows/tests.yml`

## Milestones

1. Baseline and migration inventory.
2. Rebuild the `pheroos/` protocol, kernel, governance, drivers, conformance,
   and CLI package.
3. Replace schemas, docs, README, and toy protocol example with protocol-core
   versions.
4. Delete old app/runtime/domain code, docs, examples, and tests.
5. Add core invariant tests and run import/CLI/domain-neutrality/full pytest
   validation.

## Tests to run

- `.venv/bin/pytest -q`
- `.venv/bin/python -c "import pheroos; import pheroos.protocol; import pheroos.kernel; import pheroos.governance"`
- `.venv/bin/pheroos validate examples/toy-protocol/capability.json`
- `.venv/bin/pheroos conformance examples/toy-protocol`
- `git diff --check`

## Migration and compatibility notes

- This migration intentionally does not preserve old app/API/runtime
  compatibility.
- Deleted app behavior should be documented only in `docs/removed-app-runtime.md`.
- Core public files must remain domain-neutral and must not import old
  app/runtime/tool/capability modules or provider frameworks.

## Progress log

- 2026-06-09: Started destructive migration on `codex/protocol-core-migration`;
  recorded baseline test failures before deleting old app/runtime tests.
- 2026-06-09: Added `docs/migration-inventory.md` with CORE_KEEP,
  CORE_REWRITE, DELETE_APP, DELETE_DOMAIN, DELETE_DOCS, and DELETE_TESTS
  classifications before continuing checkpoints.
- 2026-06-09: Rebuilt protocol-core package, schemas, toy example, docs,
  replacement tests, pyproject metadata, GitHub workflow, and CLI.
- 2026-06-09: Validation passes: `.venv/bin/pytest -q` reports 18 passed;
  core imports, `pheroos validate`, `pheroos conformance`, and
  `git diff --check` pass.

## Final validation checklist

- [x] `pyproject.toml` installs only `pheroos*`.
- [x] Core import boundary is clean.
- [x] CLI validate/conformance works against `examples/toy-protocol`.
- [x] Domain-neutrality guard passes for core files and docs.
- [x] Old app/runtime/domain tests are deleted or replaced.
- [x] Full pytest passes.
- [x] README/docs present PheroOS as protocol/kernel, not app/runtime.

# ExecPlan: Open Multi-Agent Protocol Refactor Finish

## User-visible goal

Finish `docs/open_multi_agent_protocol_refactor_goal.md` by making the runtime
more protocol-first, adding the missing public protocol documentation surface,
and tightening the generic data-provider boundary while preserving WRDS
compatibility.

## Current architecture facts

- Baseline test suite passes: `.venv/bin/pytest` reported 859 passed and one
  upstream Pydantic/Python warning on 2026-06-09.
- `runtime/swarm/protocol_loader.py` already loads protocol declarations from
  capability manifests and validates them through `runtime/swarm/protocol_validation.py`.
- `runtime/swarm/quorum.py`, `runtime/swarm/recovery_engine.py`, and related
  tests already enforce protocol-declared candidates, recovery declarations,
  stop-signal targets, and generic agent-output fields.
- `capabilities/wrds-financial-data/runtime_nodes.py` owns direct WRDS runtime
  node behavior, while `runtime/graph.py` keeps a compatibility bridge.
- `runtime/runtime_context.py` exposes `data_source_registry`, but it still
  builds a minimal connection/package list and does not yet publish a neutral
  `DataProviderDescriptor` contract.
- Public docs exist under older PheroOS filenames, but the requested
  `docs/protocol/` boundary and examples are missing.

## Files to inspect

- `runtime/runtime_context.py`
- `runtime/capability_registry.py`
- `runtime/capability_runtime.py`
- `runtime/financial_data_sources.py`
- `capabilities/wrds-financial-data/capability.json`
- `capabilities/wrds-financial-data/runtime_nodes.py`
- `app/routes/agents.py`
- `runtime/state.py`
- `tests/test_runtime_materializer.py`
- `tests/test_capability_runtime.py`
- `tests/test_protocol_manifest.py`
- `docs/pheroos_protocol_manifest.md`
- `docs/swarm_signal_spec.md`

## Milestones

1. Baseline and audit.
2. Add neutral data-provider descriptor/result contracts and WRDS compatibility.
3. Add focused tests for generic provider registry/result behavior.
4. Add public `docs/protocol/` docs and examples.
5. Run focused tests, grep guards, and full suite.

## Tests to run

- `.venv/bin/pytest tests/test_runtime_materializer.py tests/test_capability_runtime.py tests/test_graph.py`
- `.venv/bin/pytest tests/test_protocol_manifest.py tests/test_architecture_boundaries.py`
- `.venv/bin/pytest`

## Migration and compatibility notes

- Preserve `wrds_result` in public run responses as a legacy provider-specific
  alias.
- Add `data_source_results` and `provider_results` next to `wrds_result` for
  neutral consumers.
- Keep WRDS tools behind `ToolRegistry` and the WRDS capability-owned runtime
  node.
- Prefer manifest-declared provider descriptors, with legacy descriptors only
  as compatibility fallback.

## Progress log

- 2026-06-09: Started finishing slice; baseline full test suite passes.
- 2026-06-09: Added generic data provider/result contracts, WRDS
  `DataSourceResult` compatibility output, public protocol docs/examples, and
  README protocol-first framing.
- 2026-06-09: Focused tests and full suite pass after implementation.

## Final validation checklist

- [x] Focused tests pass.
- [x] Full test suite passes, or failures are documented as pre-existing.
- [x] Public protocol docs added under `docs/protocol/`.
- [x] Generic data-provider fields are additive and WRDS compatibility remains.
- [x] No new WRDS or finance behavior was added to core runtime when a protocol
      or capability boundary could express it.

# ExecPlan: PheroOS Kernel/Protocol Identity

## User-visible goal

Open a new branch and turn the public repository presentation from "Local Agent
Platform" into a PheroOS-first AI-as-OS kernel/protocol project, with visible
kernel ABI, machine-readable schemas, conformance entry points, driver model
contracts, and PIP governance process.

## Current architecture facts

- The current branch was created from `main` after the initial public import to
  `Ju1se/PheroOS`.
- `README.md` already describes protocol-governed runtime behavior but still
  begins with "Local Agent Platform".
- `pyproject.toml` still uses `local-agent-platform` package identity and keeps
  WRDS in core package keywords.
- Protocol docs exist under `docs/protocol/`, but kernel ABI docs,
  conformance docs, schemas, and PIP process docs are not yet first-class.
- Runtime protocol implementation currently lives under `runtime/swarm/*`;
  a clean public `pheroos/protocol` package boundary is not yet exposed.

## Files to inspect

- `README.md`
- `pyproject.toml`
- `CONTRIBUTING.md`
- `docs/architecture.md`
- `docs/protocol/overview.md`
- `runtime/swarm/protocol_loader.py`
- `runtime/swarm/protocol_manifest.py`
- `runtime/swarm/protocol_validation.py`
- `tests/test_protocol_manifest.py`
- `tests/test_architecture_boundaries.py`

## Milestones

1. Create branch and record migration plan.
2. Update public project identity and package metadata to PheroOS.
3. Add kernel ABI docs, schema files, PIP process, and conformance docs.
4. Add minimal `pheroos` package with protocol boundary, driver contracts, and
   CLI validation/conformance commands.
5. Add focused conformance tests and run existing suites.

## Tests to run

- `.venv/bin/pytest tests/conformance tests/test_protocol_manifest.py tests/test_architecture_boundaries.py`
- `.venv/bin/pytest`

## Migration and compatibility notes

- Do not rename `runtime/` or existing import paths in this slice.
- Keep WRDS and value investing as reference capabilities and compatibility
  surfaces, not package identity.
- `pheroos/protocol` should wrap existing protocol loader/validation without
  importing FastAPI, LangGraph, WRDS tools, or provider SDKs.
- CLI should validate manifests using existing runtime loaders rather than
  inventing parallel behavior.

## Progress log

- 2026-06-09: Created branch `pheroos-kernel-protocol-identity` and started
  PheroOS identity/kernel ABI slice.
- 2026-06-09: Updated public identity, package metadata, README, architecture
  docs, kernel ABI docs, schemas, driver contracts, conformance CLI/tests, and
  PIP process docs.
- 2026-06-09: Focused and full pytest suites pass on the branch.

## Final validation checklist

- [x] README and package metadata present PheroOS as the public identity.
- [x] Kernel ABI docs exist under `docs/kernel/`.
- [x] Machine-readable schema files exist under `schemas/`.
- [x] `pheroos/protocol` and driver contract modules exist without forbidden
      runtime/provider imports.
- [x] Conformance docs/tests and PIP process are present.
- [x] Focused and full test suites pass, or failures are documented.

# ExecPlan: PheroOS Checklist Implementation PR Series

## User-visible goal

Implement the improvements from
`docs/architecture/pheroos-kernel-protocol-execution-checklist.md` as staged
pull requests, starting with P0 conformance and domain leakage guardrails.

## Current architecture facts

- PR #1 merged the PheroOS public identity, kernel docs, schemas, driver
  contracts, PIP process, and basic `pheroos-conformance` CLI.
- The mistaken docs-only PR #2 was closed; checklist items should be
  implemented rather than submitted as a standalone artifact.
- `pheroos/cli.py` already emits basic manifest/protocol conformance checks but
  some checks are shallow or unconditional.
- `tests/conformance/test_pheroos_public_abi.py` guards the public ABI surface,
  but conformance fixtures do not yet cover invalid tool, recovery, output, or
  trace policy cases.

## Files to inspect

- `pheroos/cli.py`
- `pheroos/protocol/manifest.py`
- `runtime/swarm/protocol_schema.py`
- `runtime/swarm/protocol_validation.py`
- `tests/conformance/test_pheroos_public_abi.py`
- `docs/conformance/conformance-suite.md`

## Milestones

1. Close mistaken docs-only PR and start a real implementation branch.
2. Strengthen P0 conformance checks and add positive/negative fixtures.
3. Submit the conformance PR.
4. Follow with separate PRs for boundary documentation, minimal distro, and
   third-party capability security roadmap.

## Tests to run

- `.venv/bin/pytest tests/conformance tests/test_protocol_manifest.py tests/test_architecture_boundaries.py`
- `.venv/bin/pytest`

## Migration and compatibility notes

- Keep CLI report fields additive and preserve existing `ok`, `checks`, and
  `conformance_level` keys.
- Do not alter runtime behavior in the first P0 conformance PR.
- Domain-specific examples remain allowed in capabilities, tools adapters,
  docs examples, tests fixtures, and explicit legacy compatibility paths.

## Progress log

- 2026-06-09: Closed mistaken PR #2 and started
  `codex/pheroos-conformance-p0` for the first implementation PR.
- 2026-06-09: Strengthened `pheroos-conformance` P0 checks, added positive
  and negative conformance fixtures, updated conformance docs, and verified
  focused plus full test suites.
- 2026-06-09: Opened draft PR #3 for the first P0 conformance implementation
  slice.

## Final validation checklist

- [x] P0 conformance checks are meaningful and tested.
- [x] Domain leakage guard covers the intended public/core boundary without
      breaking legacy compatibility paths.
- [x] Focused tests pass.
- [x] PR is opened for the first implementation slice.

# ExecPlan: Remove Legacy Hardcoded Runtime Logic

## User-visible goal

Open a dedicated cleanup branch and remove legacy hardcoded runtime behavior,
fallback routing, domain-specific compatibility logic, and documentation that
describes those hardcoded paths as accepted architecture. The remaining core
runtime should prefer protocol, capability, driver, and manifest declarations
over hardcoded WRDS, value-investing, committee, candidate, agent, model, or
tool assumptions.

## Current architecture facts

- Branch `codex/remove-legacy-hardcoding` was created from latest
  `origin/main` on 2026-06-09.
- Runtime contains many explicit legacy modules:
  `runtime/legacy_*.py`, `runtime/swarm/legacy_*.py`, and
  `runtime/workflows/legacy_*.py`.
- `runtime/graph.py`, `runtime/audit_log.py`, `runtime/skill_loader.py`,
  `runtime/web_research_planner.py`, `runtime/swarm/policing.py`, and
  `app/routes/platform.py` import legacy helpers today.
- Current tests intentionally cover legacy compatibility behavior, including
  legacy WRDS routing fallback, legacy graph-mode fallback, legacy agent output
  mirrors, and legacy committee naming. Those tests must be removed, rewritten,
  or replaced with protocol/capability-first expectations.
- Domain-specific behavior is allowed under capability/adapters/tests/examples,
  but not as core runtime authority or fallback behavior.

## Files to inspect

- `runtime/legacy_*.py`
- `runtime/swarm/legacy_*.py`
- `runtime/workflows/legacy_*.py`
- `runtime/graph.py`
- `runtime/audit_log.py`
- `runtime/skill_loader.py`
- `runtime/web_research_planner.py`
- `runtime/swarm/policing.py`
- `runtime/runtime_context.py`
- `runtime/capability_registry.py`
- `runtime/os_kernel.py`
- `app/routes/platform.py`
- `capabilities/*/capability.json`
- `docs/`
- `tests/`

## Milestones

1. Audit legacy/hardcoded modules and import graph.
2. Remove legacy helper modules that only encode hardcoded fallback/default
   behavior.
3. Replace necessary behavior with protocol/capability/driver declarations or
   neutral helpers.
4. Remove docs that bless legacy hardcoding as architecture; keep reference
   capability docs only.
5. Rewrite or delete tests that assert legacy behavior, and add guards proving
   core runtime no longer imports legacy hardcoding.
6. Run focused architecture/conformance/runtime tests and the full suite.

## Tests to run

- `.venv/bin/pytest tests/conformance tests/test_architecture_boundaries.py`
- `.venv/bin/pytest tests/test_capability_runtime.py tests/test_graph.py`
- `.venv/bin/pytest tests/test_runtime_materializer.py tests/test_os_kernel.py`
- `.venv/bin/pytest`

## Migration and compatibility notes

- This cleanup intentionally removes legacy compatibility fallbacks when they
  encode domain-specific authority in core runtime.
- Keep domain-specific capability behavior in `capabilities/`, provider
  adapters under `tools/`, and reference examples under `docs/protocol/examples/`.
- If a public response field must remain for API shape compatibility, it should
  be a generic mirror generated from protocol-governed state, not a legacy
  authority path.
- No model-provider, WRDS, investment-candidate, committee-role, or hardcoded
  tool assumption should remain in core governance logic.

## Progress log

- 2026-06-09: Created cleanup branch and started legacy/hardcoding audit.

## Final validation checklist

- [ ] Core runtime no longer imports `runtime.legacy_*`,
      `runtime/swarm/legacy_*`, or `runtime/workflows/legacy_*` modules.
- [ ] Legacy helper modules that encode hardcoded fallback/default behavior are
      deleted or replaced by neutral protocol/capability helpers.
- [ ] Tests no longer assert legacy compatibility as desired runtime behavior.
- [ ] Docs no longer describe hardcoded legacy paths as accepted architecture.
- [ ] Focused architecture/conformance/runtime tests pass.
- [ ] Full test suite passes, or remaining failures are documented with
      concrete follow-up.
