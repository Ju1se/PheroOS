# PheroOS

Language: **English** | [简体中文](README.zh-CN.md)

PheroOS is the protocol-core package for governed, swarm-native multi-agent runtimes.

Agents are not authority. Protocol is authority.

This repository defines ABI contracts, validation, governance semantics, driver boundaries, trace lineage, and conformance checks. It does not implement an application runtime.

## Status

PheroOS is a draft ABI.

Public interfaces are conformance-backed, but not yet stable. Compatibility changes should be additive where possible and should keep baseline protocols working without swarm-specific requirements.

Checked-in schema artifacts include the full capability manifest shape and the protocol, kernel, driver, and trace ABI surfaces.

## Documentation

- [SPEC.md](SPEC.md) - protocol-core specification.
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution process and patch requirements.
- [SECURITY.md](SECURITY.md) - vulnerability reporting and protocol security scope.
- [docs/process/index.md](docs/process/index.md) - source-tree process entry point.
- [docs/protocol/runtime-integration.md](docs/protocol/runtime-integration.md) - how external runtimes compose with PheroOS.
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

Manifest extensions are metadata unless a protocol invariant adopts them. Extension metadata does not create evidence, permission, quorum, commit authority, or output authority.

## Development

Keep changes small, deterministic, provider-free, network-free, and domain-neutral.

Prefer dataclasses, pure functions, explicit validation, small schemas, provider-free examples, direct tests, and conformance checks.

Do not weaken package boundaries to make a test pass.

## License

See [LICENSE](LICENSE).
