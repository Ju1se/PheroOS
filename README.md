# PheroOS

PheroOS is an open **AI-as-OS protocol core** for governed, swarm-native multi-agent runtimes.

> Agents are not authority. Protocol is authority.

PheroOS defines the protocol boundary between agents, kernel planning, governance decisions, driver capabilities, trace lineage, and conformance checks. It is intentionally small: this repository is a protocol-core package, not an app runtime.

## What This Repository Contains

This repository contains the public protocol-core surfaces for PheroOS:

- **Protocol ABI** - capability manifests, protocol manifests, schemas, loading, and validation.
- **Kernel ABI** - input envelopes, OS plans, capability resolution, permission grants, runtime contexts, and syscall-style boundaries.
- **Governance Core** - authority levels, signals, evidence, stop signals, quorum decisions, collective decisions, recovery traces, and output authorization.
- **Driver ABI** - generic driver descriptors, registry, lifecycle, health, bindings, handles, and standardized results.
- **Trace ABI** - canonical trace events, append-only records, and required-event validation.
- **Conformance Suite** - deterministic compatibility checks for protocol, kernel, governance, driver, trace, and package boundaries.
- **Provider-free examples** - minimal manifests that require no API keys, model provider, network connection, app server, or database.

## Open Protocol Materials

The public protocol materials are:

- [SPEC.md](SPEC.md) - protocol-core specification and compatibility requirements.
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - public API and ABI lifecycle policy.
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - supported extension boundaries.
- [docs/process/release-checklist.md](docs/process/release-checklist.md) - release validation checklist.
- [CHANGELOG.md](CHANGELOG.md) - notable draft ABI changes and migration notes.

## What This Repository Is Not

PheroOS protocol-core is not:

- an agent framework;
- a prompt-chain framework;
- a FastAPI product server;
- a dashboard or frontend;
- a LangGraph graph runtime;
- a model-provider router;
- a LiteLLM/OpenAI/Ollama/vLLM wrapper;
- a plugin marketplace;
- a finance, WRDS, valuation, or other domain-specific workflow package;
- a complete operating-system daemon.

Full runtime infrastructure should live outside protocol-core and implement the ABI exposed here.

## Design Model

PheroOS uses an operating-system-inspired boundary model:

| OS-style role | PheroOS surface | Responsibility |
| --- | --- | --- |
| Userspace process | Agent | Proposes work, evidence, signals, and candidates. |
| Kernel boundary | `pheroos.kernel` | Plans available capabilities and materializes run-scoped context. |
| Device driver | `pheroos.drivers` | Provides model/tool/data/storage/sandbox capability through a generic lifecycle. |
| Security / governance hook | `pheroos.governance` | Verifies authority, resolves stops, commits candidates, and authorizes output. |
| Audit / proc-style view | `pheroos.trace` | Records lineage for decisions, evidence, calls, fallback, and output. |
| Compatibility court | `pheroos.conformance` | Proves that manifests and implementations obey protocol-core invariants. |

The kernel plans availability. It does not make domain conclusions, call tools directly, or access secrets directly.

Governance decides what is allowed. Agents may propose; governance authority is required to verify.

Drivers provide capability. Protocol provides authority.

## Protocol Layers

PheroOS currently has three provider-free protocol layers.

### 1. Baseline Governed Protocol

`examples/toy-protocol/` is the smallest protocol example. It demonstrates:

- declared targets;
- declared candidates;
- safe fallback candidate;
- quorum policy;
- recovery policy;
- evidence policy;
- output policy;
- required trace events.

This is the baseline compatibility layer. It does not require swarm behavior.

### 2. Governed E2E Protocol Slice

`examples/e2e-protocol/` demonstrates a minimal end-to-end governed vertical slice:

```text
manifest -> validation -> kernel plan -> runtime context -> driver exposure -> evidence -> signal -> commit -> recovery/output trace
```

It remains provider-free and deterministic.

### 3. Swarm-Native Collective Protocol

`examples/swarm-protocol/` demonstrates optional swarm-native collective decision behavior.

Swarm-native behavior is inspired by bee-swarm and ant-colony mechanisms, but encoded as protocol semantics, not as a large swarm framework.

| Biological mechanism | PheroOS protocol concept |
| --- | --- |
| Scout bee | Independent `ScoutReport` |
| Nest site | Declared candidate |
| Waggle dance | `RecruitmentSignal` |
| Stop / dissent | `InhibitionSignal` |
| Pheromone trail | `PheromoneTrail` |
| Evaporation | Pheromone confidence decay |
| Swarm quorum | Collective consensus threshold |
| Failed convergence | Declared safe fallback candidate |

A manifest may declare:

```json
"collective_decision_policy": {
  "mode": "hybrid",
  "min_independent_scouts": 2,
  "quorum_threshold": 3,
  "recruitment_enabled": true,
  "inhibition_enabled": true,
  "pheromone_enabled": true,
  "pheromone_evaporation_rate": 0.25,
  "fallback_candidate": "candidate:safe_fallback"
}
```

Supported collective modes:

```text
quorum
bee_swarm
ant_colony
hybrid
```

Swarm-specific trace and conformance checks apply only to swarm modes:

```text
bee_swarm
ant_colony
hybrid
```

Baseline quorum-only protocols continue to validate and pass conformance without swarm trace events.

## Core Invariants

PheroOS protocol-core validates these invariants:

- Protocols must declare at least one target.
- Protocols must declare at least one candidate.
- Every candidate must reference a declared target.
- Quorum fallback must reference a declared safe fallback candidate.
- Collective fallback must reference a declared safe fallback candidate, or default to the quorum fallback.
- Recovery trigger targets must be declared.
- Recovery failure candidates must be declared.
- Writers may not create facts.
- Agents may not create facts when evidence policy forbids it.
- Required trace events must be declared.
- Swarm trace events are required only for swarm collective modes.
- Public core must remain domain-neutral.
- Core packages must preserve import boundaries.

## Driver Lifecycle

Drivers are generic capability providers. The driver lifecycle is:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

Driver contracts are intentionally provider-neutral. Real provider integrations should not live in protocol-core.

## Trace ABI

`pheroos.trace.TraceEvent` is the canonical Trace ABI.

Trace events are small, explicit, and provider-neutral. Current event types include baseline governed events and swarm-native events such as:

```text
plan
explore
grant
expose
invoke
evidence
scout_report
signal
recruit
inhibit
pheromone_deposit
pheromone_evaporate
pheromone_score
pheromone_clip
pheromone_expire
pheromone_inhibit
candidate_score
consensus_check
block
commit
fallback
recovery
output
```

Trace is not a database, queue, event bus, or runtime monitor. The core package provides minimal append-only trace support for tests and conformance.

## Quick Start

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest -q
```

Validate the baseline protocol:

```bash
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
```

Validate the governed E2E protocol:

```bash
python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol
```

Validate the swarm-native protocol:

```bash
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
```

Export schemas:

```bash
python -m pheroos.cli.main schema export protocol
python -m pheroos.cli.main schema export kernel
python -m pheroos.cli.main schema export driver
python -m pheroos.cli.main schema export trace
```

If the package is installed with console scripts available, the equivalent commands are:

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos schema export protocol
```

## Repository Layout

```text
pheroos/
  protocol/       Protocol ABI models, manifest loading, schema helpers, validation.
  kernel/         Kernel ABI models, planning, permissions, runtime materialization.
  governance/     Authority, signals, evidence, quorum, collective decisions, output authorization.
  drivers/        Generic driver descriptors, registry, lifecycle, handles, results.
  trace/          Canonical trace events and append-only test store.
  conformance/    Compatibility checks and conformance reports.
  cli/            Thin command-line wrapper around core packages.

examples/
  toy-protocol/    Baseline governed protocol example.
  e2e-protocol/    Provider-free governed vertical slice.
  swarm-protocol/  Provider-free swarm-native collective protocol.

schemas/           Exported protocol schema artifacts.
docs/              ABI-focused documentation.
tests/             Deterministic protocol-core tests.
```

## Conformance

`pheroos.conformance` is the compatibility gate for PheroOS protocol-core.

Checks include:

- manifest schema;
- candidate declaration;
- quorum policy;
- collective policy;
- safe collective fallback;
- pheromone policy;
- pheromone behavior;
- recovery policy;
- output contract;
- trace contract;
- swarm trace contract;
- driver contract;
- domain-neutral public core;
- kernel import boundary.

Conformance checks must stay deterministic, provider-free, network-free, and explicit about the invariant they enforce.

## API and ABI Management

PheroOS is currently a draft ABI. Public package exports, schema artifacts, CLI commands, provider-free examples, and conformance checks are managed as the public compatibility surface.

Changes to public API or ABI should include:

- tests or conformance coverage;
- schema updates when manifest or artifact shape changes;
- changelog notes;
- migration notes when behavior changes;
- no new runtime, provider, server, dashboard, database, or domain workflow dependency.

The compatibility rule is additive by default: new behavior should be opt-in when possible, and baseline protocols should not be forced into swarm-specific requirements.

## AI Coding Assistants

If you are using Codex or another AI coding assistant, read `AGENTS.md` before changing code.

Important rules:

- Do not restore the removed app runtime.
- Do not add provider SDKs, web frameworks, dashboards, or domain workflows to protocol-core.
- Do not add broad protection-layer frameworks.
- Keep swarm-native work inside protocol, governance, trace, conformance, examples, and tests.
- Preserve baseline protocol compatibility.
- Add tests before or alongside behavior.

## Project Status

| Surface | Status |
| --- | --- |
| Protocol models | implemented, draft ABI |
| Protocol validation | implemented |
| Kernel models | implemented, minimal ABI |
| Runtime materializer | implemented, minimal ABI |
| Governance primitives | implemented |
| Collective decision primitives | implemented, draft ABI |
| Driver lifecycle | implemented, minimal ABI |
| Trace ABI | implemented, minimal provider-free surface |
| Conformance runner | implemented |
| CLI | implemented |
| Toy protocol | implemented |
| E2E protocol | implemented |
| Swarm protocol | implemented |
| Stable public ABI | draft |
| Full runtime daemon | out of scope for this repository |

## Development Principles

PheroOS should evolve through small, testable ABI increments.

Prefer:

- explicit dataclasses;
- pure functions;
- deterministic examples;
- provider-free conformance tests;
- stable package boundaries;
- minimal dependencies.

Avoid:

- speculative orchestration layers;
- broad safety/protection managers;
- product runtime code;
- provider-specific integrations;
- domain-specific workflows;
- changes that force baseline protocols to become swarm protocols.

## License

See `LICENSE`.
