# PheroOS

Language: **English** | [简体中文](README.zh-CN.md)

PheroOS is the protocol-core package for governed, swarm-native multi-agent runtimes.

Agents are not authority. Protocol is authority.

This repository defines ABI contracts, validation, governance semantics, driver boundaries, trace lineage, and conformance checks. It does not implement an application runtime.

## Status

PheroOS is a draft ABI.

Public interfaces are conformance-backed, but not yet stable. Compatibility changes should be additive where possible and should keep baseline protocols working without swarm-specific requirements.

Checked-in schema artifacts include the full capability manifest shape and the protocol, kernel, driver, and trace ABI surfaces.

Bee-swarm, ant-colony, and Hybrid collective signals require a
governance-issued `SignalVerification`. Hybrid pheromone manifests use the
`pheroos-hybrid-swarm-v1` conformance profile; their complete reference path
also requires all numeric inputs to be finite, and
output requires a target-scoped stop resolution in addition to commit,
evidence provenance, and publication permission; any blocked resolution for
that target denies output.

## Documentation

- [SPEC.md](SPEC.md) - protocol-core specification.
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution process and patch requirements.
- [SECURITY.md](SECURITY.md) - vulnerability reporting and protocol security scope.
- [docs/process/index.md](docs/process/index.md) - source-tree process entry point.
- [docs/protocol/runtime-integration.md](docs/protocol/runtime-integration.md) - how external runtimes compose with PheroOS.
- [docs/protocol/hybrid-pheromone-v1-migration.md](docs/protocol/hybrid-pheromone-v1-migration.md) - draft Hybrid v1 migration notes.
- [docs/protocol/runtime-adapter-guide.md](docs/protocol/runtime-adapter-guide.md) - mapping `DriverSpec` to external adapters.
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - extension boundaries.
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - public API and ABI lifecycle.
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

## Runtime Integration

External runtimes may fork or depend on this repository and build their own agent loops, model calls, tool calls, databases, memory stores, scheduling, queues, servers, and secret management around the ABI.

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
[full hardening plan](docs/protocol/hybrid-pheromone-full-hardening-plan.md),
[ABI reference](docs/protocol/hybrid-pheromone-abi.md), and
[migration note](docs/protocol/hybrid-pheromone-v1-migration.md).

Run the provider-free references with:

```bash
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-pheromone-protocol
.venv/bin/python examples/hybrid-pheromone-protocol/run.py
.venv/bin/python examples/adaptive-pheromone-replay/replay.py
```

Manifest extensions are metadata unless a protocol invariant adopts them. Extension metadata does not create evidence, permission, quorum, commit authority, or output authority.

## Development

Keep changes small, deterministic, provider-free, network-free, and domain-neutral.

Prefer dataclasses, pure functions, explicit validation, small schemas, provider-free examples, direct tests, and conformance checks.

Do not weaken package boundaries to make a test pass.

## License

See [LICENSE](LICENSE).
