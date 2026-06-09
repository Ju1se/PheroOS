# PheroOS

PheroOS is an open AI-as-OS protocol and kernel for governed agent runtimes.

Agents are not authority. Protocol is authority.

OSKernel decides what is available. PheroOS decides what is allowed. Drivers provide capability. Protocol provides authority.

This repository is now a protocol-core project. The old local app runtime was intentionally removed so the public surface can focus on:

- Protocol ABI
- Kernel ABI
- Governance Core
- Driver ABI
- Trace ABI
- Conformance Suite
- Minimal toy protocol example

## Protocol ABI

`pheroos.protocol` owns capability and protocol manifests, typed protocol models, loading, schema helpers, and validation diagnostics.

Protocol validation checks declared targets, declared candidates, quorum fallback safety, recovery references, output authority, trace lineage, and domain-neutral public core boundaries.

## Kernel ABI

`pheroos.kernel` owns input envelopes, OS plans, capability resolution, permission grants, connection requirements, driver and tool exposure, runtime context materialization, and kernel syscalls.

The kernel plans availability. It does not make conclusions, call tools, or access secrets directly.

## Governance Core

`pheroos.governance` owns targets, signals, authority levels, evidence graphs, stop signals, candidate sets, quorum decisions, recovery traces, output authorization, and trace events.

Agents can propose signals. Governance authority is required to verify them.

## Driver ABI

`pheroos.drivers` owns generic driver descriptors, registry, lifecycle, health, bindings, handles, and standardized results.

Driver lifecycle:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

## Conformance Suite

`pheroos.conformance` runs compatibility checks. The CLI is intentionally thin and delegates to this package.

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos schema export protocol
pheroos schema export kernel
pheroos schema export driver
pheroos schema export trace
```

## Minimal Toy Protocol

The only example kept in this protocol-core repository is `examples/toy-protocol/`.

It requires no API keys, no network, and no model provider. It declares a target, candidate set, safe fallback, quorum policy, recovery policy, output policy, and trace requirements.

## Removed Runtime

The old FastAPI product API, dashboard, LangGraph reference graph, provider routing, endpoint catalog, local server wrappers, visual regression suite, and domain/reference workflows were intentionally removed.

See [removed app runtime](docs/removed-app-runtime.md).

## Project Status

| Surface | Status |
| --- | --- |
| Protocol models | implemented |
| Protocol validation | implemented |
| Kernel models | implemented |
| Runtime materializer | implemented |
| Governance primitives | implemented |
| Driver lifecycle | implemented |
| Conformance runner | implemented |
| CLI | implemented |
| Toy protocol | implemented |
| Stable public ABI | draft |
