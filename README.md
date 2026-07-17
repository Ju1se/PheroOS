# PheroOS

Language: **English** | [简体中文](README.zh-CN.md)

PheroOS is the protocol-core package for governed, swarm-native multi-agent runtimes.

Agents are not authority. Protocol is authority.

This repository defines ABI contracts, validation, governance semantics, driver boundaries, trace lineage, and conformance checks. It does not implement an application runtime.

## Status

PheroOS is a draft ABI.

Public interfaces are conformance-backed, but not yet stable. Compatibility changes should be additive where possible and should keep baseline protocols working without swarm-specific requirements.

Checked-in schema artifacts include the full capability manifest shape and the
protocol, kernel, driver, trace, Commit Wire, and Commit TCK ABI surfaces.

Bee-swarm, ant-colony, and Hybrid collective signals require a
governance-issued `SignalVerification`. Hybrid pheromone manifests use the
`pheroos-hybrid-swarm-v1` conformance profile; their complete reference path
also requires all numeric inputs to be finite, and
output requires a target-scoped stop resolution in addition to commit,
evidence provenance, and publication permission; any blocked resolution for
that target denies output.

The optional Optimal Commit Draft ABI adds evidence/counterevidence,
challenge, support-lease, risk, stability, bounded-liveness, portable
certificate, and Byzantine distributed-finality contracts. It keeps Hybrid
pheromone and layer behavior in an attention-only channel: changing attention
alone cannot change a commit or certificate.

## Schema Document Versions

The four core schema surfaces have an immutable legacy v1 alias and a separate
strict v2 document:

| Surface | Frozen v1 `$id` and CLI alias | Strict v2 artifact and selector |
| --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json`; `capability`/`capability-v1` | `schemas/capability-v2.schema.json`; `pheroos-capability-schema-v2` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json`; `protocol`/`protocol-v1` | `schemas/protocol-v2.schema.json`; `pheroos-protocol-schema-v2` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json`; `driver`/`driver-v1` | `schemas/driver-v2.schema.json`; `descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json`; `kernel`/`kernel-v1` | `schemas/kernel-v2.schema.json`; `plan_version=pheroos-kernel-plan-v2` |

The old unversioned `$id` values and CLI aliases are permanently pinned to v1;
they never select v2 by shape or package version. Capability and Protocol v2
are schema-document versions and their payloads still declare
`protocol_version=pheroos.protocol.v1`. Driver's `descriptor_version` is
independent of the external provider version in `DriverDescriptor.version`,
and Kernel uses its own `plan_version` discriminator.

Typed v1-to-v2 migration is explicit and non-lossy. Driver migration uses
`upgrade_driver_descriptor_v1` and rejects non-migratable input with a typed
error. Kernel's `os_plan_v1_from_dict` returns a non-authoritative
`LegacyOSPlan`; `upgrade_os_plan_v1` requires caller-supplied scope, readiness,
probe, capability, and provider-version facts instead of inventing defaults.

## Documentation

- [SPEC.md](SPEC.md) - protocol-core specification.
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution process and patch requirements.
- [SECURITY.md](SECURITY.md) - vulnerability reporting and protocol security scope.
- [docs/process/index.md](docs/process/index.md) - source-tree process entry point.
- [docs/protocol/runtime-integration.md](docs/protocol/runtime-integration.md) - how external runtimes compose with PheroOS.
- [docs/protocol/hybrid-pheromone-abi.md](docs/protocol/hybrid-pheromone-abi.md) - normative Hybrid Pheromone ABI.
- [docs/protocol/hybrid-pheromone-v1-migration.md](docs/protocol/hybrid-pheromone-v1-migration.md) - draft Hybrid v1 migration notes.
- [docs/protocol/optimal-commit-abi.md](docs/protocol/optimal-commit-abi.md) - complete Optimal Commit Draft ABI semantics.
- [docs/protocol/optimal-commit-v1-migration.md](docs/protocol/optimal-commit-v1-migration.md) - opt-in runtime and manifest migration.
- [docs/protocol/runtime-adapter-guide.md](docs/protocol/runtime-adapter-guide.md) - mapping `DriverSpec` to external adapters.
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - extension boundaries.
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - public API and ABI lifecycle.
- [docs/process/schema-v1-v2-migration.md](docs/process/schema-v1-v2-migration.md) - frozen v1 schema aliases and explicit v2 migration.
- [docs/conformance/conformance-suite.md](docs/conformance/conformance-suite.md) - compatibility checks.
- [docs/process/release-checklist.md](docs/process/release-checklist.md) - release gates.
- [CHANGELOG.md](CHANGELOG.md) - draft ABI changes and migration notes.
- [AGENTS.md](AGENTS.md) - repository rules for coding agents.

## Tree Layout

```text
pheroos/
  protocol/       Manifest objects, schema helpers, validation.
  kernel/         Capability planning, permissions, runtime context contracts.
  governance/     Authority, evidence, quorum, collective decision, output checks.
  drivers/        Provider-neutral driver ABI and lifecycle objects.
  trace/          Canonical trace events and append-only test store.
  conformance/    Deterministic compatibility checks.
  cli/            Thin wrapper around core packages.

examples/
  toy-protocol/    Minimal governed protocol.
  e2e-protocol/    Provider-free governed vertical slice.
  swarm-protocol/  Swarm-native collective decision example.
  hybrid-pheromone-protocol/  Full Hybrid Pheromone ABI example.
  adaptive-pheromone-replay/  Trace-like adaptive input replay example.
  hybrid-commit-protocol/     Hybrid attention plus evidence-governed commit examples.
  commit-certificate-replay/  Portable certificate reconstruction and mutation rejection.
  distributed-commit-protocol/  Byzantine quorum, provisional, conflict, and deadline examples.

schemas/           Exported ABI schema artifacts.
docs/              Protocol and process documentation.
tests/             Provider-free deterministic tests.
```

## Core Surfaces

`pheroos.protocol` owns declarations and validation.

`pheroos.kernel` owns planning boundaries. It does not call tools, models, providers, or secrets.

`pheroos.governance` owns authority and decision semantics. Agents may propose; governance verifies.

`pheroos.drivers` owns generic capability contracts. Real provider adapters belong outside protocol-core.

`pheroos.trace` owns provider-neutral lineage. It is not a database, queue, event bus, or runtime monitor.

`pheroos.conformance` proves ABI compatibility.

These package facades are the cohesive external entry points. Their
implementations are split into one-way private engines for commit state,
support, certificates, distributed finality, Hybrid evaluation, swarm, and
pheromone lifecycle. Private module paths are not ABI; the facades preserve
canonical object identity and delegate to one implementation owner without a
dynamic service registry. Governance and Conformance use static, thread-safe
lazy facades, and the Commit TCK artifact path does not load the optional
reference adapter or Governance engine. All facade exports and compatibility
modules remain covered by the checked API lifecycle artifact.

Built-in Commit Wire and Trace dispatch comes from immutable static contract
registries shared by schema generation and validation. Namespaced extensions
remain open as non-authoritative metadata; they cannot install new authority
handlers at runtime.

## Management CLI

The thin, local CLI exposes versioned JSON for protocol management without
starting an API server:

```bash
pheroos version
pheroos profile show examples/hybrid-commit-protocol/capability.json
pheroos schema list
pheroos schema show commit
pheroos schema export capability-v2
pheroos schema export protocol-v2
pheroos schema export driver-v2
pheroos schema export kernel-v2
pheroos wire validate commit record.json
pheroos wire validate driver-v2 descriptor.json
pheroos wire validate kernel-v2 plan.json
pheroos tck run --version v2
pheroos abi show
pheroos abi diff
```

Schema drift is checked with
`python scripts/generate_schema_artifacts.py --check`. The `--write` mode
regenerates only v2 artifacts and never rewrites the frozen v1 files.

Unknown critical versions and malformed wire records fail closed. HTTP APIs,
authentication, rate limiting, remote routing, and service discovery belong to
an external runtime or gateway, not protocol-core.

## Runtime Integration

External runtimes may fork or depend on this repository and build their own agent loops, model calls, tool calls, databases, memory stores, scheduling, queues, servers, and secret management around the ABI.

Each request constructs `RuntimeScope(tenant_id, run_id, request_id)` and
carries its tenant/run-derived `scope_ref` through Kernel, Driver, Governance,
and scoped Trace records. Durable authority is supplied through an external
`GovernanceStateStore` adapter: state and Trace commit atomically,
compare-and-swap heads reject forks, and only a verified store receipt can
finalize durable output authority. The included in-memory store is a reference
adapter, not a database.

Append-only lineage uses the separate provider-neutral `TraceStore` Protocol.
External StateStore and TraceStore implementations can run the public
`run_governance_state_store_conformance(...)` and
`run_trace_store_conformance(...)` matrices before integration.

The expected composition is:

```text
manifest
-> validation
-> kernel plan
-> external adapter binding
-> evidence, scout reports, and signals
-> governance decision
-> trace lineage
-> output authorization
-> conformance
```

Provider configuration should stay outside manifests. Use opaque external references such as `config_ref`; do not put API keys, passwords, tokens, credentials, or secrets in protocol files.

## Swarm Semantics

Swarm-native behavior is protocol behavior, not a swarm framework.

Bee-swarm concepts map to scout reports, recruitment signals, inhibition signals, quorum, consensus, and safe fallback.

Ant-colony concepts map to pheromone trails, evaporation, positive or negative feedback, bounded source contribution, and traceable collective memory.

Pheromone is not evidence, truth, permission, quorum, or output authority.

All swarm modes require verified scouts and enabled collective signals before
they count or score. Hybrid runtimes additionally submit trails,
topology, feedback, layer proposals, performance snapshots, strategy biases,
and bounded policy-adjustment proposals to
`evaluate_hybrid_collective_step(...)`. The pure reference step performs the
declared deposit, evaporation, diffusion, reinforcement, coordination,
scoring, scout-gate, and commit-or-fallback path and returns the canonical
`trace_events` produced by that path.

`LayerCoordinationState` is a governance output, not an authoritative Hybrid
input. External runtimes must submit `LayerProposal` records and related
proposal inputs so governance can recompute coordination. The manifest ABI has
one canonical `PheromoneKindProfile`, exported by `pheroos.protocol`; the
`pheroos.governance` name is the same compatibility type.

## Out Of Scope

This repository must not become:

- an agent framework
- a model-provider gateway
- a FastAPI or product server
- a dashboard
- a LangGraph runtime
- a LiteLLM/OpenAI/Ollama/vLLM wrapper
- a database, queue, worker pool, or daemon
- a plugin marketplace
- a domain workflow package

## Compatibility

Baseline governed protocols remain valid without swarm behavior.

Swarm-specific conformance applies only when a manifest declares a swarm collective mode.

Hybrid declarations select `pheroos-hybrid-swarm-v1`, which includes the core,
swarm, and Hybrid required checks. Baseline quorum and basic swarm protocols do
not acquire Hybrid-only required fields or checks.

Optimal Commit is also opt-in. Only a manifest with
`collective_commit_policy` selects a Commit profile; baseline, swarm, and
Hybrid v1 manifests keep their existing profile and result/trace behavior.

## Release Integrity

CI checks Python 3.12 through 3.14 and exercises both the wheel and sdist from
an external working directory. The exact distributions that pass those checks
are the only inputs to deterministic CycloneDX/SPDX SBOM generation and
trusted-main provenance attestations. Pull requests retain read-only
permissions. Build provenance records artifact origin; it does not create
protocol evidence or governance authority. See the
[release checklist](docs/process/release-checklist.md).

## Hybrid Pheromone Draft ABI

The complete Hybrid reference path is implemented as a deterministic,
provider-free protocol-core slice: governed signal verification, bounded
deposit/evaporation/diffusion/reinforcement, L1–L4 coordination, run-scoped
policy adjustment, declared-candidate consensus or safe fallback, four output
gates, and causal trace/conformance replay. Pheromone remains collective memory
rather than evidence or authority.

External runtimes continue a Hybrid run only with the governance-issued
`HybridReplayState` returned by `replay_state_from_hybrid_step(...)`. Replay
receipts bind deposit, diffusion, feedback, and adjustment payloads; trace
conformance rejects substituted payloads, cross-lifecycle identity collisions,
and replay claims without the matching issued prior state. See the
[ABI reference](docs/protocol/hybrid-pheromone-abi.md) and
[migration note](docs/protocol/hybrid-pheromone-v1-migration.md).

Run the provider-free references with:

```bash
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-pheromone-protocol
.venv/bin/python examples/hybrid-pheromone-protocol/run.py
.venv/bin/python examples/adaptive-pheromone-replay/replay.py
```

## Optimal Commit Draft ABI

Optimal Commit separates exploration pressure from truth authority. Verified
principal, risk, membership, observation, counterevidence, challenge, support
lease, stop, permission, replay, and prior-window heads determine exact
fixed-point commit metrics. A unique leader must satisfy every declared gate
for a continuous stability window; identifier order never breaks a tie.

The manifest chooses `advisory`, `evidence_bound`, `certified`, or
`distributed` assurance. Missing proof cannot silently produce a lower-level
commit. The absolute deadline cannot be extended by new attention, evidence,
leader changes, resets, or finality delay.

This liveness guarantee requires the external runtime to advance monotonic
logical steps and continue evaluation. It guarantees a terminal response, not
a forced evidence commit: `safe_fallback`, `advisory`, `blocked`, `invalid`,
`finality_unavailable`, and `safety_violation` remain explicit non-commit
outcomes.

`evaluate_hybrid_commit_step(request=...)` returns an authoritative progress or
terminal outcome when the governance envelope is usable, plus the exact
window/replay heads, required certificate/finality records, terminal output
decisions when applicable, canonical trace, diagnostics, and a root binding
every authority leaf.
Malformed authority facts fail closed. A missing, malformed, or mismatched
attention channel is quarantined as non-authoritative diagnostic metadata; it
cannot veto an otherwise valid commit path. Every issued terminal outcome is
deliverable; publication and execution remain separate, current action gates.

Distributed assurance verifies `n >= 3f + 1` and `2q - n > f`, exact witness
proposal digests, semantic commit-value roots, membership/epoch scope,
replay/equivocation, and conflict freeze. Equivalent proof-envelope retries do
not freeze an epoch; distinct candidate, claim, output, or authority roots do.
The core defines records and deterministic governance only; networking, witness
collection, scheduling, providers, and storage stay external.

The frozen TCK v1 contains 38 legacy adversarial vectors. TCK v2 adds 23
expected-free declarative request cases: adapters receive only inputs, while
the harness owns expected outcomes. The public reference adapter and an
independent standard-library spec model must agree; echo/constant, malformed,
out-of-order, state-leaking, and timeout adapters fail the harness. Active
Commit conformance has no skip or N/A path. Run it with:

```bash
.venv/bin/python -c \
  'from pheroos.conformance import run_commit_tck; assert run_commit_tck().ok'
.venv/bin/python -m pheroos.cli.main tck run --version v2
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-commit-protocol
.venv/bin/python -m pheroos.cli.main conformance examples/distributed-commit-protocol
.venv/bin/python examples/hybrid-commit-protocol/run.py
.venv/bin/python examples/commit-certificate-replay/replay.py
.venv/bin/python examples/distributed-commit-protocol/run.py
```

Manifest extensions are metadata unless a protocol invariant adopts them. Extension metadata does not create evidence, permission, quorum, commit authority, or output authority.

## Development

Keep changes small, deterministic, provider-free, network-free, and domain-neutral.

Prefer dataclasses, pure functions, explicit validation, small schemas, provider-free examples, direct tests, and conformance checks.

Do not weaken package boundaries to make a test pass.

## License

See [LICENSE](LICENSE).
