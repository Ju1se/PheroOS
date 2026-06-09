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
