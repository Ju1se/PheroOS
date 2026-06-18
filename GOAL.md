Goal: Implement the next minimal end-to-end version of PheroOS as a small, protocol-core AI-as-OS project.

Repository: Ju1se/PheroOS

Project intent:
PheroOS is not an agent framework, app server, dashboard, prompt chain, or provider wrapper. PheroOS is a protocol-core package for governed agent runtimes. The core authority model is:

- Agents are not authority.
- Protocol is authority.
- Kernel decides what is available.
- Governance decides what is allowed.
- Drivers provide capability.
- Trace explains what happened.
- Conformance proves compatibility.

Primary implementation objective:
Build the smallest working vertical slice that proves the PheroOS protocol can execute an end-to-end governed multi-agent flow without restoring the old app runtime.

The target end-to-end path is:

1. Load a capability manifest.
2. Validate Protocol ABI invariants.
3. Create an InputEnvelope.
4. Produce an OSPlan.
5. Materialize a RuntimeContext.
6. Declare/register/probe/bind/expose a driver.
7. Execute a minimal governed action through explicit kernel/syscall-style contracts.
8. Produce evidence with provenance.
9. Propose/verify a signal using governance authority.
10. Commit a declared candidate through quorum logic.
11. Authorize output only if committed candidate, evidence provenance, stop resolution, and publication permission are satisfied.
12. Emit trace events for the run.
13. Prove the flow through conformance checks and tests.

Important scope boundaries:
Only work inside protocol-core surfaces unless a tiny example or test is required:

- pheroos.protocol
- pheroos.kernel
- pheroos.governance
- pheroos.drivers
- pheroos.trace
- pheroos.conformance
- pheroos.cli
- examples/toy-protocol or examples/e2e-protocol
- tests
- docs directly related to the ABI

Do not restore or recreate the removed application runtime.
Do not add FastAPI routes, dashboards, LangGraph graphs, provider routers, endpoint catalogs, local server wrappers, visual UI tests, finance/WRDS workflows, product APIs, or application-specific skills.

Design style:
Prefer a small explicit ABI over broad abstractions. Implement the protocol path directly and test it. Do not create speculative protection layers, safety managers, meta-policy frameworks, plugin frameworks, middleware stacks, or multi-level wrappers unless they are required by the immediate end-to-end test.

Linux-inspired architecture guidance:
Use Linux as a structural analogy, not as something to copy literally.

- Agent = userspace process
- Kernel = capability planning, permission boundary, handles, runtime context
- Syscall = explicit request from agent/runtime into kernel-controlled capability
- Driver = model/tool/data/storage capability provider
- Governance = authority and decision policy, similar to a security hook layer
- Trace = audit/proc-style visibility
- Conformance = ABI compatibility test suite

Implementation priorities:
1. Preserve existing public concepts and naming where possible.
2. Add missing small dataclasses or pure-Python contracts only when needed by the vertical slice.
3. Keep dependencies minimal. Prefer Python standard library. Do not add heavy frameworks.
4. Make schemas stricter where they are currently placeholders.
5. Add tests before or alongside behavior.
6. Keep CLI thin; CLI should delegate to core packages.
7. Keep examples provider-free: no API keys, no network requirement, no model provider requirement.
8. Make failure states explicit: denied permission, missing provenance, uncommitted candidate, unresolved stop signal, missing trace event.
9. Every new object must have a direct caller, test, or conformance check.
10. Every new protection rule must correspond to an actual protocol invariant or testable runtime failure.

Do not overbuild:
Avoid adding broad “protection layer” code that does not execute in the minimal end-to-end path. Do not create classes named like SafetyManager, PolicyManager, GuardrailStack, ProtectionLayer, SecurityOrchestrator, or RuntimeFramework unless the code is directly needed by tests and cannot be expressed with existing protocol/governance/kernel primitives.

Import boundaries:
- pheroos.protocol must not import pheroos.kernel, pheroos.governance, app/runtime modules, provider frameworks, tools, examples, or CLI.
- pheroos.kernel may import pheroos.protocol and pheroos.drivers only.
- pheroos.kernel should not import pheroos.governance directly; governance integration should be represented by explicit contracts, dependency injection, or conformance/runtime composition.
- pheroos.governance may import pheroos.protocol concepts where practical, but should remain independent of app/runtime/provider code.
- pheroos.drivers should not depend on app/runtime/provider frameworks.
- pheroos.conformance may import protocol, kernel, governance, drivers, and trace.
- CLI must stay thin and delegate to core packages.

Concrete deliverables:
A. Implement a minimal pheroos.trace package if missing:
   - TraceEvent
   - TraceRecord or TraceStore
   - append-only in-memory trace store for tests
   - required event validation for plan, grant/expose, invoke, evidence, signal, commit, recovery, output

B. Strengthen kernel/syscall-style contracts:
   - Keep kernel as planner and boundary.
   - Add only the minimum syscall/request/reply objects needed by the e2e test.
   - Avoid a full daemon, server, worker pool, async runtime, or scheduler unless required by tests.

C. Strengthen driver lifecycle:
   - Keep declare -> validate -> register -> probe -> bind -> expose.
   - Add minimal invoke result semantics only if required by the e2e path.
   - Driver results must include provenance when used as evidence.

D. Strengthen governance:
   - Ensure agents can propose but cannot verify unless authority is sufficient.
   - Quorum must commit only declared candidates.
   - Output must be denied unless committed candidate, provenance, stop resolution, and publication permission are all satisfied.
   - Do not build a generic policy engine unless the tests require it.

E. Add an end-to-end example:
   - examples/e2e-protocol/capability.json or extend toy-protocol minimally.
   - It must remain provider-free, network-free, and domain-neutral.
   - It should demonstrate declared targets, candidates, fallback candidate, quorum, recovery, evidence policy, output policy, trace requirements, and at least one driver descriptor if driver conformance is part of the vertical slice.

F. Add tests:
   - happy path: manifest -> kernel plan -> runtime context -> driver lifecycle -> evidence -> governance -> commit -> output authorization -> trace
   - denial path: output denied when evidence provenance is missing
   - denial path: signal verification rejected when authority is insufficient
   - denial path: undeclared candidate cannot be committed
   - conformance path: example protocol passes conformance

G. Update docs only where needed:
   - Keep docs short.
   - Document the vertical slice and ABI invariants.
   - Do not add marketing copy or product runtime documentation.

Validation commands:
Run these before finishing:

python -m pytest -q
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol

If you add examples/e2e-protocol, also run:

python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol

Acceptance criteria:
- All tests pass.
- Existing toy protocol still validates.
- New e2e path is provider-free and deterministic.
- No old app runtime is restored.
- No FastAPI, LangGraph, LiteLLM, WRDS, dashboard, product API, finance workflow, or provider routing is added.
- No speculative protection layers are added.
- New abstractions are small, test-covered, and used by the e2e flow.
- Public core remains domain-neutral.

Current update - 2026-06-15:
The repository already contains the minimal governed vertical slice and the optional swarm-native collective slice. The current examples include:

- examples/toy-protocol
- examples/e2e-protocol
- examples/swarm-protocol

The current implementation includes:

- CollectiveDecisionPolicy in the Protocol ABI.
- Scout reports, recruitment signals, inhibition signals, pheromone trails, evaporation, scoring, and collective decision evaluation in Governance Core.
- Canonical TraceEvent plus an append-only in-memory trace store.
- Swarm-specific conformance checks for collective policy, safe collective fallback, pheromone policy, and swarm trace requirements.
- Provider-free vertical slice tests for governed e2e and swarm-native collective behavior.

Validation observed in this workspace:

- `python` is not available in the shell.
- `python3` is available and reports Python 3.14.5rc1.
- `python3 -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `python3 -m pheroos.cli.main conformance examples/toy-protocol` passes.
- `python3 -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `python3 -m pheroos.cli.main conformance examples/e2e-protocol` passes.
- `python3 -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `python3 -m pheroos.cli.main conformance examples/swarm-protocol` passes.
- `python3 -m pytest -q` could not run because pytest is not installed in the active Python environment.

Next action:
Do not add a new runtime, provider wrapper, swarm framework, server, dashboard, or broad policy layer. The next smallest useful action is to harden ABI schema export and testing:

1. Establish a test baseline by installing or using a dev environment with pytest, then run the full suite.
2. Replace placeholder CLI schema exports for kernel, driver, and trace with concrete ABI schemas that match the checked-in schema artifacts.
3. Add tests that assert `pheroos schema export protocol|kernel|driver|trace` returns the expected ABI shape.
4. Keep all changes inside protocol-core surfaces and provider-free tests.

Completion update - 2026-06-15:
The next action above has been completed in the current worktree.

Implemented:

- Added concrete kernel, driver, and trace schema helpers under their ABI surfaces.
- Updated the CLI schema export path to use concrete protocol, kernel, driver, and trace schemas instead of placeholder permissive schemas.
- Added provider-free CLI schema export tests.
- Kept the change limited to protocol-core surfaces and tests.

Verification:

- `.venv/bin/python -m pytest -q` passes with 50 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes.
- Exported kernel, driver, and trace schemas match the checked-in schema artifacts.

Stigmergic pheromone layer upgrade plan - 2026-06-15:
Based on the pasted research notes, the next swarm-native evolution should upgrade the ant-colony side of PheroOS from simple pheromone scoring into a focused Stigmergic Memory ABI.

Project structure analysis:

- Protocol declarations live in `pheroos.protocol`. `CollectiveDecisionPolicy` currently declares `pheromone_enabled` and `pheromone_evaporation_rate`, but does not yet declare strength bounds, decay model, provenance requirements, trace requirements, or pheromone kind semantics.
- Governance decision semantics live in `pheroos.governance`. `pheroos/governance/collective.py` currently defines `PheromoneTrail(candidate_id, strength)` and `PheromonePolicy(enabled, evaporation_rate)`, then adds pheromone strength as a positive score bias when `policy.pheromone_enabled` is true.
- Trace owns provider-neutral lineage. Existing trace event types already include `pheromone_deposit` and `pheromone_evaporate`, but a pheromone trail does not yet carry a trace event id or evidence binding.
- Conformance currently includes `pheromone_policy`, but it only checks evaporation range. It does not yet prove provenance requirements, strength bounds, positive/negative distinction, cautionary behavior, stale decay, or that pheromone cannot authorize output.
- `examples/swarm-protocol` is the right example to extend. `examples/toy-protocol` must remain a baseline quorum protocol and should not be forced to become swarm-native.
- Tests already cover simple evaporation, simple pheromone scoring, swarm trace requirements, and the provider-free swarm vertical slice. They do not yet cover stigmergic memory semantics.
- The active worktree also contains the completed schema export hardening. Do not revert that work while implementing the pheromone upgrade.

Design principle for the upgrade:
Bee-swarm decision and ant-colony memory must remain separate protocol concepts.

- `bee_swarm` behavior should continue to mean independent scout reports, recruitment signals, inhibition signals, and quorum.
- `ant_colony` behavior should mean externalized, traceable, decaying pheromone memory.
- `hybrid` may compose both.
- Pheromone is not evidence, not truth, not permission, and not output authority. It is only a decaying preference, routing, or memory signal used during scoring.

ABI upgrade objective:
Upgrade `PheromoneTrail` into a backward-compatible stigmergic mark while keeping the existing name.

Suggested governance shape:

```python
@dataclass(frozen=True)
class PheromoneTrail:
    candidate_id: str
    strength: float
    target: str = ""
    route_id: str = ""
    tool_id: str = ""
    kind: str = "positive"
    source_id: str = ""
    source_role: str = ""
    evidence_id: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    deposited_at_step: int = 0
    updated_at_step: int = 0
    ttl_steps: int | None = None
```

Keep `candidate_id` and `strength` as the first fields so existing tests and examples can be migrated gradually.

Suggested governance policy shape:

```python
@dataclass(frozen=True)
class PheromonePolicy:
    enabled: bool = False
    evaporation_rate: float = 0.0
    decay_model: str = "linear"
    min_strength: float = 0.0
    max_strength: float = 10.0
    positive_weight: float = 1.0
    negative_weight: float = 1.0
    cautionary_weight: float = 1.0
    cautionary_override_threshold: float = 1.0
    require_provenance: bool = True
    require_trace: bool = True
```

Protocol plan:

1. Extend `CollectiveDecisionPolicy` with backward-compatible optional pheromone fields:
   - `pheromone_decay_model`
   - `pheromone_min_strength`
   - `pheromone_max_strength`
   - `pheromone_positive_weight`
   - `pheromone_negative_weight`
   - `pheromone_cautionary_weight`
   - `pheromone_cautionary_override_threshold`
   - `pheromone_require_provenance`
   - `pheromone_require_trace`
2. Keep existing `pheromone_enabled` and `pheromone_evaporation_rate` fields.
3. Update manifest loading, protocol schema export, and validation for the new fields.
4. Validate:
   - supported decay models: `linear`, `exponential`, `step`
   - evaporation rate between 0 and 1
   - min strength is not greater than max strength
   - weights are non-negative
   - cautionary threshold is non-negative
   - provenance and trace requirements default to enabled, but protocol validation should not overconstrain explicit policy choices; governance enforces them when policy requires

Governance plan:

1. Add supported pheromone kinds:
   - `positive`
   - `negative`
   - `cautionary`
   - `novelty`
   - `stale`
2. Add pure helper functions:
   - `clip_pheromone_strength`
   - `validate_pheromone_trail`
   - `deposit_pheromone`
   - `score_pheromone_trails`
   - updated `evaporate_trails`
3. Preserve deterministic behavior and use only the Python standard library.
4. Deterministic scoring semantics:
   - positive pheromone increases candidate score by weighted strength
   - negative pheromone decreases candidate score by weighted strength
   - cautionary pheromone decreases candidate score and can suppress positive support when its weighted strength reaches the configured override threshold
   - novelty and stale kinds are validated and decayed, but should not authorize commit or output
5. Require declared candidates when a pheromone trail references a candidate.
6. Reject or ignore invalid pheromone trails according to explicit tests; prefer raising `GovernanceError` for missing required provenance, missing required trace id, unsupported kind, invalid step values, or undeclared candidate.
7. Ensure a high pheromone score cannot commit a candidate unless the collective policy still has enough independent scout support.

Trace plan:

1. Reuse canonical `TraceEvent`.
2. Continue using `pheromone_deposit` and `pheromone_evaporate`.
3. Require `trace_event_id` on pheromone trails when policy requires trace.
4. Store scores and mark ids in trace lineage only as small provider-neutral dictionaries.
5. Do not add a trace database, event bus, queue, daemon, or monitor.

Conformance plan:

1. Extend `pheromone_policy` conformance to check decay model, strength bounds, weights, and cautionary threshold while covering provenance and trace as explicit governance policy behavior rather than protocol-layer hard failures.
2. Add or extend checks/tests for:
   - positive and negative pheromone semantics are distinct
   - evaporation applies to all pheromone kinds
   - strength is clipped to declared bounds
   - cautionary pheromone can override positive support at the configured threshold
   - stale or expired pheromone does not cause commit
   - pheromone cannot authorize output
3. Keep swarm-specific conformance active only when a manifest declares swarm behavior.

Example plan:

1. Extend `examples/swarm-protocol/capability.json` with the new pheromone policy fields.
2. Keep examples provider-free, network-free, deterministic, and domain-neutral.
3. Do not modify `examples/toy-protocol` to satisfy swarm-specific checks.
4. Update `examples/swarm-protocol/README.md` only with short ABI-focused notes.

Test plan:

1. Protocol tests:
   - valid swarm manifest accepts the new pheromone policy fields
   - invalid decay model is rejected
   - invalid strength bounds are rejected
   - invalid weights are rejected
   - explicit pheromone trace/provenance policy flags are accepted by protocol validation without overconstraining the manifest
2. Governance tests:
   - positive pheromone increases score
   - negative pheromone decreases score
   - cautionary pheromone suppresses positive support at threshold
   - evaporation reduces every kind deterministically
   - expired TTL produces stale or zero-strength behavior
   - missing provenance is rejected when governance policy requires it
   - missing trace event id is rejected when governance policy requires it
   - provenance and trace enforcement can be relaxed by explicit governance policy
   - undeclared candidate is rejected
   - high pheromone without enough independent scouts falls back safely
3. Trace tests:
   - `pheromone_deposit` and `pheromone_evaporate` remain valid canonical events
   - trace lineage can carry small pheromone mark metadata
4. Conformance tests:
   - swarm protocol passes after new pheromone fields are declared
   - toy protocol still passes without swarm-specific requirements
   - pheromone output boundary is covered
5. Vertical slice:
   - update the swarm vertical slice to deposit positive, negative, and cautionary trails with evidence provenance and trace event ids
   - keep output authorization dependent on committed candidate, evidence provenance, stop resolution, and publication permission

Validation commands for the upgrade:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol
.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol
.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol
```

Non-goals for this upgrade:

- Do not add a swarm runtime.
- Do not add a generic memory database.
- Do not add model/provider routing.
- Do not add agent frameworks, worker pools, servers, dashboards, or background daemons.
- Do not make pheromone an authority mechanism.
- Do not make baseline quorum protocols declare pheromone policy.
- Do not implement adaptive or learned decay until a deterministic conformance need exists.

Acceptance criteria for the pheromone upgrade:

- Existing baseline toy protocol remains compatible.
- Existing e2e protocol remains compatible.
- Swarm protocol demonstrates traceable, evidence-bound, decaying positive/negative/cautionary pheromone memory.
- Pheromone scoring is deterministic and provider-free.
- Pheromone cannot commit or authorize output without the existing governance and output contracts.
- All new fields and helper functions are directly exercised by tests or conformance.
- Public core remains small, domain-neutral, and ABI-focused.

Completion update for stigmergic pheromone layer - 2026-06-15:
The pheromone upgrade above has been implemented in the current worktree without adding runtime infrastructure, provider wrappers, servers, dashboards, worker pools, databases, or a swarm framework.

Implemented:

- Extended `CollectiveDecisionPolicy` with pheromone decay model, strength bounds, positive/negative/cautionary weights, cautionary override threshold, provenance requirement, and trace requirement.
- Updated manifest loading, protocol schema export, checked-in protocol schema artifact, and protocol validation for the new pheromone policy fields.
- Kept protocol validation focused on structural ABI invariants; provenance and trace enforcement remain explicit governance policy choices instead of protocol-layer hard failures.
- Upgraded `PheromoneTrail` into a backward-compatible stigmergic mark with target, route, tool, kind, source, evidence, provenance, trace event id, step, and TTL metadata.
- Added deterministic governance helpers for clipping, validation, deposit, evaporation, policy conversion, and pheromone scoring.
- Added distinct positive, negative, cautionary, novelty, and stale pheromone semantics.
- Ensured high pheromone support cannot commit a candidate without enough independent scout support.
- Ensured pheromone cannot authorize output without the existing output contract.
- Extended pheromone conformance checks for decay model, strength bounds, weights, and cautionary threshold while leaving provenance and trace as explicit governance policy choices rather than protocol-layer hard failures.
- Updated `examples/swarm-protocol` to declare the new pheromone policy fields and demonstrate evidence-bound, traceable pheromone memory.
- Kept `examples/toy-protocol` and `examples/e2e-protocol` compatible without forcing swarm-specific requirements.
- Expanded tests across protocol, governance, trace, conformance, CLI schema export, output authorization, and the swarm vertical slice.

Verification:

- `.venv/bin/python -m pytest -q` passes with 67 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes.
- `git diff --check` passes.

Next pheromone simulation improvement plan - 2026-06-15:
Based on the latest pasted improvement notes, the current Stigmergic Memory ABI is directionally correct, but the next step should make the pheromone layer more uniform, better bounded against source dominance, and more traceable without moving adaptive or neural strategy into protocol-core.

Core interpretation:

```text
Stigmergic Memory ABI
= multi-type pheromone + decay + evidence binding + source weighting/caps + positive/negative feedback + trace + conformance
```

Pheromone remains collective external memory. It is not evidence, truth, permission, quorum, or output authority.

Architecture stance:

1. Protocol ABI declares objects, policy fields, bounds, and schemas.
2. Governance provides the deterministic reference engine: deposit, evaporate, clip, aggregate, score, fallback, and policy-controlled validation.
3. Trace records pheromone changes through canonical `TraceEvent`.
4. Conformance proves ABI compatibility and behavior boundaries.
5. Adaptive or neural strategy stays outside protocol-core. If used later, it may only suggest bounded parameters; protocol bounds, governance decisions, trace, conformance, and deterministic fallback remain authoritative.

Current implementation already covers:

- multi-kind pheromone: `positive`, `negative`, `cautionary`, `novelty`, `stale`
- decay models: `linear`, `exponential`, `step`
- strength bounds
- provenance and trace policy flags
- candidate, route, and tool attachment metadata
- TTL expiry
- no direct commit from pheromone alone
- no output authorization from pheromone alone
- provider-free tests and conformance

Remaining improvement gaps:

- `PheromoneTrail` still uses candidate-centric fields plus optional `route_id` and `tool_id`; the next ABI should converge on `subject_type` and `subject_id`.
- `PheromonePolicy` does not yet include `novelty_weight`, `per_source_cap`, `per_round_deposit_cap`, or `min_source_diversity`.
- The default decay model is currently `linear`; the pasted recommendation prefers `exponential` as the default deterministic model.
- `evaluate_collective_decision()` still reads `policy.fallback_candidate` directly; runtime behavior should align with `collective_fallback_id(protocol)` by accepting an explicit `fallback_candidate_id` override.
- Trace currently has `pheromone_deposit` and `pheromone_evaporate`; the next step should add or strengthen `pheromone_score`, `pheromone_clip`, `pheromone_expire`, and optionally `pheromone_inhibit`.
- Conformance should more directly prove per-source cap behavior, trace lineage, and no-direct-output boundaries.

PR 1 - Runtime fallback consistency:

Goal: align runtime collective fallback behavior with protocol validation and conformance.

Implement:

- Add `fallback_candidate_id: str | None = None` to `evaluate_collective_decision`.
- Resolve fallback as `fallback_candidate_id or policy.fallback_candidate`.
- Keep validation/conformance support for collective fallback defaulting to quorum fallback.

Tests:

- `policy.fallback_candidate == ""` can still fall back safely when caller passes the quorum fallback id.
- Undeclared fallback remains rejected.
- Non-safe fallback remains rejected.
- Existing swarm vertical slice still passes.

PR 2 - Uniform pheromone subject ABI:

Goal: make pheromone marks attach to a uniform subject rather than being primarily candidate-shaped.

Extend `PheromoneTrail` with backward-compatible fields:

```python
subject_type: str = "candidate"  # candidate | route | tool | evidence | agent
subject_id: str = ""
```

Migration rule:

- If `subject_id` is empty and `candidate_id` is set, treat it as `subject_type="candidate"` and `subject_id=candidate_id`.
- Keep `candidate_id`, `route_id`, and `tool_id` during the compatibility window.
- Candidate scoring should only apply to `subject_type == "candidate"` with a declared candidate subject.

Tests:

- candidate subject scores candidates.
- route/tool/evidence/agent subjects validate and trace without accidentally scoring candidates.
- old `PheromoneTrail(candidate_id, strength)` form remains compatible.
- undeclared candidate subject is rejected when candidate scoring is requested.

PR 3 - PheromonePolicy source caps and novelty weight:

Goal: reduce source dominance and make novelty explicit without adding a broad safety framework.

Extend `PheromonePolicy` and `CollectiveDecisionPolicy` with:

```python
novelty_weight: float = 0.5
per_source_cap: float = 3.0
per_round_deposit_cap: float = 5.0
min_source_diversity: int = 1
```

Protocol validation should remain structural and avoid overconstraint:

- weights and caps are non-negative
- `min_source_diversity` is positive
- protocol should not make source-trust judgments

Governance behavior:

- clip each source's total scoring contribution to `per_source_cap`
- clip per-round deposited strength to `per_round_deposit_cap`
- apply `novelty_weight` as positive exploration support without allowing novelty to commit or authorize output by itself
- expose source diversity information in `CollectiveDecisionState` or a small pheromone score record only if directly exercised by tests

Tests:

- per-source cap is enforced.
- per-round deposit cap is enforced.
- novelty affects score with `novelty_weight`.
- novelty-only support cannot commit without independent scout support.
- source diversity is counted deterministically where used.

PR 4 - Exponential default and trace event strengthening:

Goal: make the reference deterministic engine closer to the pasted recommendation and more auditable.

Implement:

- Change default `pheromone_decay_model` / `PheromonePolicy.decay_model` to `exponential` only if existing tests and examples are updated explicitly.
- Keep `linear` and `step` supported.
- Add canonical trace event types:
  - `pheromone_score`
  - `pheromone_clip`
  - `pheromone_expire`
  - optionally `pheromone_inhibit`
- Update required swarm trace behavior only when the manifest declares pheromone-enabled swarm behavior and the new events are part of the example contract.

Tests:

- exponential default decays deterministically.
- linear and step remain supported.
- pheromone score trace lineage can carry subject, kind, old/new strength, source, evidence, and step metadata.
- expired pheromone emits or can be represented by `pheromone_expire`.

PR 5 - Conformance hardening without overconstraint:

Goal: prove compatibility and boundaries without turning protocol validation into a policy cage.

Add or extend conformance/tests for:

- pheromone strength bounds
- negative pheromone reduces score
- cautionary pheromone suppresses positive support at threshold
- stale or expired pheromone cannot cause commit
- pheromone cannot authorize output
- pheromone trace lineage is present in the swarm example
- per-source cap is enforced

Keep conformance deterministic, provider-free, network-free, and explicit about the invariant being checked.

Non-goals for the next improvement:

- Do not add neural networks to protocol-core.
- Do not add adaptive strategy to protocol-core unless a deterministic conformance need exists.
- Do not add persistent pheromone storage, database, event bus, queue, worker, server, or runtime.
- Do not make information pheromone a fact, authority, quorum substitute, or output permission.
- Do not force `examples/toy-protocol` or `examples/e2e-protocol` to declare pheromone behavior.

Acceptance criteria for the next improvement:

- Existing toy and e2e protocols remain compatible.
- Swarm protocol demonstrates uniform subject-based, traceable, evidence-bound, bounded pheromone memory.
- Pheromone decay defaults and supported modes are deterministic and tested.
- Source caps and novelty behavior are tested directly.
- Runtime fallback behavior matches protocol fallback semantics.
- Trace and conformance prove pheromone lineage and no-direct-output boundaries.
- Public core remains protocol-focused, provider-free, domain-neutral, and not overconstrained.

AGENTS.md alignment update - 2026-06-15:
The next implementation pass must follow the repository-level AGENTS.md contract exactly. The active task remains the pheromone simulation improvement plan above, especially PR 1 through PR 5. Do not silently narrow the task, substitute a smaller test set, or drift into unrelated cleanup.

Repository identity and authority:

- This repository is the PheroOS protocol-core package.
- Agents are not authority. Protocol is authority.
- OSKernel decides what is available.
- Governance decides what is allowed.
- Drivers provide capability.
- Trace explains what happened.
- Conformance proves compatibility.
- The core must remain small, cohesive, deterministic, domain-neutral, provider-free by default, and ABI-focused.

Allowed implementation surfaces for this task:

- `pheroos.protocol` for manifest declarations, schemas, and structural validation.
- `pheroos.governance` for deterministic collective decision and pheromone semantics.
- `pheroos.trace` for canonical provider-neutral lineage events.
- `pheroos.conformance` for compatibility checks.
- `examples/swarm-protocol` for the provider-free swarm example.
- `tests` for deterministic proof of the invariants.
- `pheroos.cli` only if schema export or existing thin wrapper behavior must stay aligned.

Do not add or restore:

- app runtime code
- FastAPI product APIs
- dashboards or frontend code
- LangGraph graphs
- model-provider routing or provider SDK wrappers
- endpoint catalogs
- local server wrappers
- visual regression UI tests
- WRDS, finance, investment, valuation, or other domain-specific workflows
- background daemons, worker pools, queues, databases, or server infrastructure
- plugin marketplaces
- broad agent frameworks
- broad safety/protection frameworks
- neural, adaptive, or learned pheromone strategy inside protocol-core

Swarm-native interpretation for this task:

- Bee-swarm semantics are independent scout reports, recruitment signals, inhibition signals, quorum/consensus, and safe fallback.
- Ant-colony semantics are pheromone trails, evaporation, positive/negative/cautionary/novelty/stale signal behavior, bounded source contribution, and traceable collective memory.
- Biology is only inspiration. The implementation must encode testable protocol, governance, trace, and conformance behavior.
- Pheromone remains a bounded memory or preference signal. It is not evidence, truth, permission, quorum, or output authority.

Required end-to-end direction:

1. Load and validate the swarm capability manifest.
2. Read the declared collective decision policy.
3. Use declared targets and candidates only.
4. Identify a declared safe fallback candidate.
5. Collect independent scout reports with evidence provenance.
6. Apply recruitment and inhibition signals when enabled.
7. Apply pheromone deposit, clipping, scoring, and evaporation when enabled.
8. Evaluate collective consensus deterministically.
9. Commit only a declared candidate, or fall back safely.
10. Authorize output only when the output contract is satisfied.
11. Emit trace events for the collective decision path.
12. Pass conformance.

Implementation constraints:

- Prefer dataclasses, pure functions, explicit validation, small schemas, deterministic examples, conformance checks, and direct tests.
- Add a new abstraction only if it enforces a Protocol ABI invariant, is required by Kernel/Governance/Driver/Trace/Conformance behavior, or is directly exercised by a test or provider-free example.
- Do not add speculative managers, unused hooks, framework scaffolding, or dependency-heavy implementations.
- Protocol validation should stay structural: declared targets/candidates, safe fallback references, evidence provenance requirements, trace lineage requirements, and collective decision policy invariants.
- Protocol validation must not make source-trust judgments.
- Governance must enforce that consensus commits only declared candidates, failed consensus falls back to a declared safe fallback candidate, stop/inhibition signals can block or reduce support, and output authorization requires committed candidate, evidence provenance, stop resolution, and publication permission.
- Trace must use canonical `pheroos.trace.TraceEvent` and must not become a database, event bus, queue, logging framework, runtime monitor, or daemon.
- Conformance must remain deterministic, provider-free, network-free, small, and explicit about the invariant being checked.

Import boundaries that must not be weakened:

- `pheroos.protocol` must not import `pheroos.kernel`, `pheroos.governance`, `pheroos.drivers`, `pheroos.conformance`, CLI, examples, app/runtime modules, provider frameworks, or tools.
- `pheroos.kernel` may import `pheroos.protocol` and `pheroos.drivers`.
- `pheroos.kernel` should not import `pheroos.governance` directly.
- `pheroos.governance` may import protocol concepts where practical, but must remain independent of kernel runtime machinery and provider frameworks.
- `pheroos.drivers` and `pheroos.trace` must remain generic and independent of app/runtime/provider frameworks.
- `pheroos.conformance` may import protocol, kernel, governance, drivers, and trace.
- CLI code must stay thin and delegate to core packages.

Backward compatibility requirements:

- Do not force existing baseline protocols to become swarm protocols.
- `examples/toy-protocol` remains the minimal baseline governed protocol example.
- `examples/e2e-protocol` remains a governed vertical slice and should not be rewritten to satisfy swarm-only checks.
- Swarm-native checks apply only when a manifest explicitly declares `collective_decision_policy` with a swarm mode such as `bee_swarm`, `ant_colony`, or `hybrid`.
- Existing schema export hardening and other current worktree changes must not be reverted while implementing this plan.

Testing and validation requirements:

- Add tests before or alongside behavior.
- Do not write only a hand-picked "minimum" test set if the change touches protocol, governance, trace, conformance, examples, and CLI/schema behavior.
- Tests must prove protocol validation invariants, governance authority and decision semantics, trace lineage requirements, conformance checks, provider-free examples, and backward compatibility for existing examples.
- The PR 1 through PR 5 tests listed above are required task scope, not optional stretch work.

Before finishing the pheromone improvement, run the relevant full validation set:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol
.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol
.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol
git diff --check
```

Completion criteria for the AGENTS.md-aligned pass:

- PR 1 through PR 5 are implemented without task drift.
- All changed behavior is exercised by tests or conformance.
- Trace lineage covers the pheromone events introduced or required by the swarm example.
- Baseline toy and e2e protocols remain compatible.
- No forbidden runtime, provider, dashboard, framework, storage, or domain workflow code is added.
- Public core remains small, explicit, deterministic, domain-neutral, provider-free by default, and ABI-focused.

Completion update for next pheromone simulation improvement - 2026-06-15:
The PR 1 through PR 5 improvement plan from `GOAL.md` line 437 has been implemented in the current worktree under the AGENTS.md boundary rules.

Implemented:

- PR 1 runtime fallback consistency: `evaluate_collective_decision` accepts an explicit `fallback_candidate_id` and resolves fallback as runtime override first, policy fallback second.
- PR 2 uniform pheromone subject ABI: `PheromoneTrail` now supports `subject_type` and `subject_id` while preserving legacy `candidate_id`, `route_id`, and `tool_id` compatibility.
- PR 3 source caps and novelty: protocol and governance policies now include novelty weight, per-source scoring cap, per-round deposit cap, and minimum source diversity.
- PR 4 exponential default and trace strengthening: protocol and governance defaults use deterministic exponential decay, linear and step remain supported, and canonical trace events include `pheromone_score`, `pheromone_clip`, `pheromone_expire`, and optional `pheromone_inhibit`.
- PR 5 conformance hardening: pheromone conformance now checks decay model, bounds, weights, caps, and source diversity while keeping provenance and trace flags policy-controlled instead of protocol-layer hard failures.
- Updated `examples/swarm-protocol` to declare the new policy fields and required pheromone trace events.
- Updated the provider-free swarm vertical slice to deposit, clip, evaporate, expire, score, commit, and authorize output through traceable deterministic behavior.
- Expanded tests across protocol validation, governance scoring, trace lineage, conformance, CLI schema export, output authorization, and the swarm vertical slice.
- Kept `examples/toy-protocol` and `examples/e2e-protocol` compatible without forcing swarm-specific behavior.
- Did not add runtime infrastructure, provider wrappers, dashboards, servers, databases, queues, neural/adaptive strategy, or broad safety/agent frameworks.

Verification:

- `.venv/bin/python -m pytest -q` passes with 79 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes.
- `git diff --check` passes.

GitHub main alignment checkpoints for pheromone workflow - 2026-06-16:
The latest pasted review frames the pheromone workflow as a Stigmergic Memory ABI v0.2 target relative to GitHub main. Keep the following three steps as the required alignment checkpoints when comparing this worktree against upstream/main or preparing the next PR:

1. Fix `evaluate_collective_decision` fallback consistency.
   Runtime collective evaluation must accept `fallback_candidate_id` so callers can pass `collective_fallback_id(protocol)` when `policy.fallback_candidate` is empty. This is a consistency fix, not a new authority mechanism.

2. Upgrade `PheromoneTrail` from `candidate_id` plus `strength` into a subject/kind/source/evidence/provenance/time/TTL object.
   The v0.2 object model must support `subject_type` values `candidate`, `route`, `tool`, `evidence`, and `agent`; `kind` values `positive`, `negative`, `cautionary`, `novelty`, and `stale`; source metadata; evidence binding; provenance; trace id; deposited/updated steps; and TTL. Candidate scoring must remain limited to declared candidate subjects.

3. Complete pheromone trace and conformance boundaries.
   Trace/conformance must prove stale transitions, clipping, non-candidate no-score behavior, and no direct output authority. Required boundary checks include: pheromone is not evidence, pheromone cannot directly commit, pheromone cannot authorize output, stale pheromones do not push commit, and missing provenance/trace is rejected when policy requires it.

Completion update for GitHub main alignment checkpoints - 2026-06-16:
The three alignment checkpoints above have been completed and verified in the current worktree.

Implemented:

- `evaluate_collective_decision` supports `fallback_candidate_id`, allowing runtime callers to pass `collective_fallback_id(protocol)` when the collective policy fallback is empty.
- `PheromoneTrail` supports subject, kind, source, evidence, provenance, trace, step, and TTL metadata while preserving the legacy `candidate_id` and `strength` compatibility path.
- `pheromone_behavior` conformance now directly proves the runtime boundaries for missing provenance, missing trace id, deposit clipping, non-candidate no-score behavior, TTL stale transition, high pheromone without scouts falling back, pheromone not being evidence, and pheromone score not authorizing output.
- `pheroos conformance` now reports `pheromone_behavior` for toy, e2e, and swarm protocols; the check is a no-op pass when pheromone is not enabled and an active deterministic ABI check when pheromone is enabled.

Verification:

- `.venv/bin/python -m pytest -q` passes with 80 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes and includes `pheromone_behavior`.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes and includes `pheromone_behavior`.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes and includes `pheromone_behavior`.
- `git diff --check` passes.

Completion update for open protocol API/ABI management - 2026-06-18:
The repository now has an explicit open-protocol management layer for public API and ABI surfaces while preserving the protocol-core boundaries required by AGENTS.md.

Implemented:

- Added `SPEC.md` as the draft ABI v0.1 protocol-core specification covering public surfaces, compatibility requirements, swarm semantics, extension rules, versioning, and conformance gates.
- Added `docs/process/api-lifecycle.md` to define public API/ABI surfaces, internal surfaces, stability levels, change rules, deprecation policy, versioning, and validation gates.
- Added `docs/protocol/extension-points.md` to define supported extension paths without coupling protocol-core to app runtimes, providers, dashboards, servers, storage, or domain workflows.
- Added `docs/process/release-checklist.md` and `CHANGELOG.md` so public behavior changes have release and migration tracking.
- Updated `README.md`, `docs/protocol/overview.md`, `docs/process/pip-process.md`, and `docs/conformance/conformance-suite.md` to make the API/ABI management model discoverable.
- Updated CI and PR review templates so public API/ABI changes require schema, conformance, changelog, and toy/e2e/swarm compatibility checks.
- Added project metadata tests to assert version consistency and required open-protocol documents.

Verification:

- `.venv/bin/python -m pytest -q` passes with 82 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes.
- `git diff --check` passes.

Assessment:

- Public APIs are now managed as declared draft ABI surfaces rather than incidental imports.
- API changes are gated through tests, checked-in schemas, conformance, changelog/migration notes, CI, and PR checklist expectations.
- The current state is well managed for a pre-stable open protocol, but it is still explicitly draft ABI rather than a frozen stable public ABI.

ABI extensibility hardening plan - 2026-06-18:
Based on the architecture audit, the next task is to harden PheroOS as an extensible protocol ABI for external multi-agent runtimes without adding runtime infrastructure to protocol-core.

Audit summary:

- The current core is correctly provider-free and database-free by default.
- No hardcoded model API key, database backend, provider SDK, queue, server, dashboard, or domain workflow was found in core.
- `pyproject.toml` has no runtime dependencies.
- Kernel and driver code expose generic contracts instead of calling tools, models, databases, or secrets directly.
- Pheromone governance already proves important authority boundaries: pheromone is not evidence, not quorum, not permission, and not output authority.
- The remaining extensibility risks are ABI shape risks rather than provider-coupling risks.

Primary objective:

Make PheroOS easier for external runtimes to implement without forking protocol-core, while keeping protocol-core small, deterministic, provider-neutral, domain-neutral, and ABI-focused.

This means:

1. Preserve extension metadata across manifest loading and ABI objects.
2. Provide a provider-neutral driver declaration shape.
3. Allow namespaced extension points without giving them implicit authority.
4. Make the pheromone workflow harder to misuse.
5. Document how external runtimes compose with the protocol without adding runtime code here.

Required boundary:

Do not add:

- app runtime code
- FastAPI or product APIs
- dashboards or frontend code
- LangGraph graphs
- provider SDK wrappers
- model routing
- endpoint catalogs
- local server wrappers
- persistent storage implementations
- database adapters
- queues
- worker pools
- background daemons
- plugin marketplaces
- broad agent frameworks
- broad safety/protection frameworks
- domain workflows
- secrets, API keys, tokens, passwords, or provider configuration values in manifests

Allowed implementation surfaces:

- `pheroos.protocol` for manifest declarations, extension metadata, schema shape, and structural validation.
- `pheroos.kernel` for planning and exposure of declared provider-neutral driver specs.
- `pheroos.drivers` for generic driver ABI objects only.
- `pheroos.governance` for deterministic pheromone workflow helpers and extension-safe scoring behavior.
- `pheroos.trace` for canonical and namespaced provider-neutral trace events.
- `pheroos.conformance` for compatibility checks.
- `schemas/` for checked-in ABI artifacts.
- `docs/protocol` for integration contracts.
- `tests` for deterministic proof.
- `examples` only when an example is needed to prove ABI behavior without providers, networks, servers, or databases.
- `pheroos.cli` only if schema export must stay aligned.

Phase 0 - Record scope and preserve current worktree:

Goal: prevent task drift.

Actions:

- Treat this as "PheroOS ABI Extensibility Hardening", not as a runtime implementation.
- Preserve existing README, i18n, and documentation cleanup work.
- Preserve existing pheromone behavior and conformance boundaries.
- Keep `examples/toy-protocol` and `examples/e2e-protocol` compatible without forcing swarm behavior.

Acceptance:

- The implementation plan remains limited to protocol-core surfaces.
- No old runtime or provider gateway is restored.
- Existing public behavior is not narrowed to a hand-picked minimum test set.

Phase 1 - Manifest extension retention:

Goal: allow external runtimes to declare namespaced metadata without losing it during manifest loading.

Implement:

- Add small `extensions: dict[str, Any]` fields where needed on public ABI dataclasses.
- Candidate locations:
  - `CapabilityManifest`
  - `ProtocolManifest`
  - `CollectiveDecisionPolicy`
  - `TargetSpec`
  - `CandidateSpec`
  - `SignalSpec`
  - driver declaration shape from Phase 2
- Preserve namespaced extension fields from manifest payloads.
- Prefer an explicit `extensions` object for new manifests.
- Optionally support top-level `x-*` keys as compatibility extension keys if this stays simple and deterministic.

Rules:

- Extension metadata is data, not authority.
- Extension metadata must not affect commit, evidence, permission, or output authorization unless a future built-in protocol invariant explicitly adopts it.
- Extension metadata must not contain secrets.
- Protocol validation should reject or diagnose obvious secret-like keys such as `api_key`, `token`, `password`, `secret`, and credential-like nested fields.

Tests:

- Manifest loader preserves declared extension metadata.
- Unknown extension metadata does not break baseline validation.
- Secret-like extension keys are rejected or reported through validation diagnostics.
- Baseline toy and e2e manifests still validate unchanged.

Phase 2 - Provider-neutral driver manifest ABI:

Goal: replace raw driver dict usage with a small typed protocol declaration while avoiding provider-specific configuration.

Implement:

```python
@dataclass(frozen=True)
class DriverSpec:
    id: str
    kind: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_ref: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)
```

Behavior:

- `CapabilityManifest.drivers` should become `list[DriverSpec]` or expose a typed compatibility path.
- Manifest loading converts driver payloads into `DriverSpec`.
- Kernel planning reads `DriverSpec.id` and `DriverSpec.permissions`.
- Driver lifecycle remains generic and provider-free.
- `config_ref` is only an external opaque reference, never an inline secret or provider config.

Rules:

- Do not implement concrete model, database, storage, queue, or tool adapters in protocol-core.
- Do not make kernel resolve `config_ref`.
- Do not add secret loading.

Tests:

- Driver specs load from existing e2e manifest.
- Kernel plan exposes typed driver specs with correct permissions.
- Missing driver id or kind remains a conformance failure.
- Secret-like driver fields are rejected or reported.
- Existing driver lifecycle tests continue to pass.

Phase 3 - Namespaced trace and pheromone extensions:

Goal: keep built-in ABI strict while allowing external runtimes to record extension events and pheromone metadata safely.

Trace plan:

- Keep built-in `VALID_EVENT_TYPES`.
- Allow namespaced extension event types only when they follow a safe naming rule such as `x-*` or `ext.*`.
- Namespaced events must still require `protocol_id`, `target`, and `reason`.
- Namespaced events are append-only trace facts, not authority.

Pheromone plan:

- Keep built-in pheromone kinds:
  - `positive`
  - `negative`
  - `cautionary`
  - `novelty`
  - `stale`
- Keep built-in subject types:
  - `candidate`
  - `route`
  - `tool`
  - `evidence`
  - `agent`
- Allow namespaced custom pheromone kinds or subject types only if they validate structurally and traceably.
- Unknown namespaced pheromone kinds must not contribute to candidate scoring by default.
- Unknown namespaced subject types must not accidentally map to declared candidates.

Tests:

- Built-in trace events continue to validate.
- Namespaced trace events validate and append.
- Invalid non-namespaced trace events still fail.
- Built-in pheromone scoring remains unchanged.
- Namespaced pheromone marks can validate as traceable metadata.
- Namespaced pheromone marks do not score candidates by default.

Phase 4 - Pheromone workflow helper:

Goal: reduce misuse of pheromone evaporation and scoring by giving runtime authors a deterministic reference workflow.

Problem:

- `evaporate_trails()` supports `current_step`.
- `score_candidates()` and `evaluate_collective_decision()` currently accept trails but do not own the step/evaporation workflow.
- External runtimes can accidentally evaluate stale or unexpired trails if they skip the evaporation step.

Implement one small pure helper, with final naming chosen to match local style:

```python
evaluate_collective_decision_step(...)
```

or:

```python
advance_collective_memory(...)
```

Required behavior:

- Accept `current_step`.
- Apply pheromone evaporation and TTL expiry deterministically.
- Score candidates.
- Evaluate collective decision using the existing declared-candidate and safe-fallback rules.
- Return enough structured data for trace lineage, but do not create a trace database or runtime loop.

Rules:

- Do not store memory.
- Do not add a scheduler, daemon, worker, or event bus.
- Do not make pheromone authority.
- Keep existing lower-level helpers available for advanced users.

Tests:

- Helper applies evaporation before scoring.
- Helper turns expired TTL pheromones stale before evaluation.
- Helper falls back safely when pheromone support is stale or insufficient.
- Helper still requires independent scouts for commit.
- Existing manual workflow tests continue to pass.

Phase 5 - Runtime integration contract documentation:

Goal: explain how users build their own multi-agent systems on top of PheroOS without putting runtime implementation into this repository.

Add:

- `docs/protocol/runtime-integration.md`

Document:

```text
manifest
-> protocol validation
-> kernel plan
-> external runtime binds adapters
-> agents produce scout reports, evidence, and signals
-> governance evaluates decision
-> trace records lineage
-> output authorization checks authority boundary
-> conformance proves compatibility
```

Clarify external runtime responsibilities:

- agent loops
- model calls
- tool calls
- database persistence
- vector stores or memory backends
- queueing
- scheduling
- secret management
- provider-specific adapter code

Clarify protocol-core responsibilities:

- ABI objects
- validation
- kernel planning contracts
- generic driver contracts
- governance reference semantics
- trace ABI
- conformance

Documentation constraints:

- Do not add Quick Start.
- Do not add provider setup.
- Do not add database setup.
- Do not add API key instructions.
- Do not document product runtime behavior as if it lives in protocol-core.

Phase 6 - Schema, conformance, and compatibility gates:

Goal: prove the extension mechanism is managed and does not weaken protocol authority.

Schema:

- Update protocol and driver schema helpers.
- Update checked-in schema artifacts.
- Keep CLI schema export aligned.

Conformance:

- Add checks for extension metadata retention where practical.
- Add checks for provider-free driver spec shape.
- Add checks that extension metadata does not bypass built-in authority boundaries.
- Add checks that secret-like manifest fields are rejected or diagnosed.

Tests:

- Protocol tests for extension loading and validation.
- Kernel tests for typed driver exposure.
- Driver tests for provider-neutral descriptor compatibility.
- Governance tests for namespaced pheromone safety.
- Trace tests for namespaced event validation.
- Conformance tests for toy/e2e/swarm compatibility.
- CLI schema export tests when schema changes.

Validation requirements:

Run the full relevant validation set before completion:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol
.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol
.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol
git diff --check
```

Completion criteria:

- Extension metadata is preserved without granting authority.
- Provider-neutral driver specs replace or wrap raw manifest driver dicts.
- No secret-like manifest fields are accepted silently.
- Kernel still does not access secrets, tools, providers, databases, or queues.
- Trace supports safe namespaced extension events without weakening canonical event validation.
- Pheromone supports safe namespaced metadata without letting unknown pheromone kinds score candidates by default.
- A deterministic pheromone workflow helper prevents stale/evaporation misuse.
- Runtime integration documentation clearly explains how external systems compose with PheroOS.
- Existing toy, e2e, and swarm examples remain compatible.
- All changed public API or ABI surfaces are covered by tests, schema updates, conformance, and changelog/migration notes where appropriate.
- No runtime, provider gateway, database adapter, model SDK, dashboard, worker, queue, server, or broad agent framework is added.

Completion update for ABI extensibility hardening - 2026-06-18:
The ABI extensibility hardening plan above has been implemented in the current worktree while preserving the protocol-core boundary.

Implemented:

- Added manifest extension retention through explicit `extensions` metadata and namespaced `x-*` / `ext.*` keys.
- Added secret-like manifest field rejection/diagnostics for API keys, tokens, passwords, credentials, and secrets.
- Added provider-neutral `DriverSpec` declarations with opaque external `config_ref`.
- Updated manifest loading so capability driver declarations become typed `DriverSpec` objects.
- Updated kernel planning and driver conformance to consume typed driver specs while retaining a compatibility path for dict-shaped driver payloads.
- Added `extension_contract` conformance for extension and secret-boundary compatibility.
- Added namespaced trace extension event validation while preserving canonical built-in trace event validation.
- Added namespaced pheromone value validation for metadata-only extension kinds/subjects that do not score candidates by default.
- Added `CollectiveDecisionStep` and `evaluate_collective_decision_step()` to apply deterministic pheromone evaporation, TTL expiry, scoring, and evaluation in a single pure workflow helper.
- Updated protocol, driver, and trace schema helpers plus checked-in schema artifacts.
- Added `docs/protocol/runtime-integration.md` as the external runtime integration contract.
- Updated README links, protocol overview, extension docs, driver docs, governance docs, conformance docs, SPEC, API lifecycle notes, release checklist, project metadata tests, and CHANGELOG.
- Added tests for extension retention, typed driver specs, secret-like manifest rejection, namespaced trace events, namespaced pheromone safety, pheromone step evaluation, schema export, conformance, and runtime integration document presence.
- Kept toy, e2e, and swarm examples compatible.
- Did not add runtime infrastructure, provider wrappers, model SDKs, database adapters, queues, servers, dashboards, workers, or broad agent frameworks.

Verification:

- `.venv/bin/python -m pytest -q` passes with 97 tests.
- `.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol` passes and includes `extension_contract`.
- `.venv/bin/python -m pheroos.cli.main validate examples/e2e-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/e2e-protocol` passes and includes `extension_contract`.
- `.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json` passes.
- `.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol` passes and includes `extension_contract`.
- `git diff --check` passes.
