# PheroOS

PheroOS is an open AI-as-OS protocol and reference kernel for governed
multi-agent runtimes. It is a kernel/protocol system for governed agent
societies: capabilities declare what may be possible, the kernel decides what is
available, governance decides what is allowed, and traces explain why.

Agents are not authority. Protocol is authority.

Agents propose. Protocol validates. Kernel materializes. Governance blocks or
commits. Writer expresses only what is permitted. TraceStore explains why.

PheroOS is not a prompt chain, not an agent chat app, and not a finance-specific
workflow. WRDS, value investing, web research, and code development live here as
reference capabilities or adapters; they are not kernel concepts.

Public framing: PheroOS Kernel + PheroOS Protocol + PheroOS Reference Runtime +
Capability/Driver ecosystem.

## What Is PheroOS?

PheroOS defines protocol-governed infrastructure for running multi-agent
systems where tools, models, data, evidence, recovery, quorum, and publication
are controlled by explicit contracts. The repository contains:

- PheroOS Protocol: versioned contracts for capabilities, evidence, tools,
  quorum, recovery, output, and trace.
- PheroOS Kernel: reference authority layer for planning, permissions,
  capability loading, runtime materialization, and governance boundaries.
- PheroOS Reference Runtime: local implementation used to exercise the protocol
  and compatibility layer.
- PheroOS Driver Model: adapter boundary for model, tool, data, storage, and
  sandbox providers.
- PheroOS Conformance Suite: CLI and tests for protocol/capability compatibility.

## Core Principle

Agents can propose observations, plans, evidence, tool calls, risks, recovery
actions, and drafts. They cannot directly create verified facts, hard blockers,
committed candidates, publication permission, or final authority.

Those decisions belong to protocol and kernel-mode governance.

## Architecture At A Glance

```text
User Request
  -> InputEnvelope
  -> OSKernel
  -> RuntimeMaterializer
  -> Capability Loader
  -> Driver Registry / ToolRegistry
  -> PheroOS Governance Loop
  -> EvidenceGraph
  -> StopSignal / Recovery / Quorum
  -> Writer Contract
  -> FinalJudge Contract
  -> Final Output + Trace
```

AI-as-OS handles resources, permissions, connections, capabilities, tools,
agents, and runtime context.

PheroOS handles signals, target pressure, evidence, stop signals, quorum,
recovery, output contracts, and trace/debugger explanations.

## Public Surfaces

| Surface | Purpose |
| --- | --- |
| PheroOS Protocol | Versioned protocol contracts for governed multi-agent runtime behavior. |
| PheroOS Kernel | Authority layer for validation, permissioning, materialization, and governance. |
| PheroOS Governance | Signal, evidence, stop-signal, quorum, recovery, output, and trace subsystems. |
| Capability ABI | Manifest and entrypoint contract for third-party capabilities. |
| Driver Model | Adapter boundary for model, tool, data, storage, and sandbox providers. |
| Conformance Suite | Checks that capabilities and runtime surfaces obey protocol/kernel rules. |
| Reference Runtime | Local implementation used to run and test PheroOS-compatible capabilities. |

## AI-as-OS Vs PheroOS

AI-as-OS is the operating-system layer for resources and execution. It plans
capability availability, grants permissions, resolves connections, exposes
tools, selects agents, and materializes a tenant-scoped runtime context.

PheroOS is the governance layer. It decides which signals count, which targets
are pressured, which evidence is usable, which stop signals block execution,
which candidate can be committed, which recovery path is allowed, which output
mode is permitted, and which trace explains the result.

## PheroOS As An AI Operating-System Kernel

PheroOS separates user-mode proposals, kernel-mode authority, and driver-mode
capability.

| Mode | Examples | Authority |
| --- | --- | --- |
| User mode | agents, capability workflows, model-generated plans, model-generated evidence proposals, model-generated drafts | Can propose. |
| Kernel mode | protocol validation, permission grants, tool exposure, signal verification, stop-signal resolution, evidence checks, quorum commit, recovery outcome, output authorization, trace explanation | Can verify, block, commit, recover, publish, and explain. |
| Driver mode | model providers, tool providers, data providers, storage providers, sandbox providers | Can return structured capability; cannot author final conclusions. |

User-mode agents can propose. Kernel-mode services verify, block, commit,
recover, publish, and explain. Driver-mode adapters return structured
capability, but do not author final conclusions.

## Protocol ABI

PheroOS-compatible capabilities declare behavior through versioned protocol
manifests. A manifest may declare:

- intents
- required capability types
- permissions
- connections
- agent roles
- tool contracts
- data-provider contracts
- evidence policy
- signal lifecycle
- canonical targets
- stop-signal policy
- candidate set
- quorum policy
- recovery protocols
- output contract
- trace requirements

Illustrative generic protocol fragment:

```json
{
  "protocol_version": "pheroos.protocol.v0.1",
  "id": "example.review",
  "targets": [
    {"id": "decision:review"}
  ],
  "candidates": [
    {"id": "candidate:approve"},
    {"id": "candidate:reject"},
    {"id": "candidate:insufficient_evidence", "safe_fallback": true}
  ],
  "quorum_policy": {
    "target": "decision:review",
    "fallback_candidate": "candidate:insufficient_evidence"
  }
}
```

A candidate cannot be committed unless it is declared by the active protocol.

Protocol docs:

- [Protocol overview](docs/protocol/overview.md)
- [Protocol spec v0.1](docs/protocol/protocol-spec-v0.1.md)
- [Capability manifest](docs/protocol/capability-manifest.md)
- [Evidence contract](docs/protocol/evidence-contract.md)
- [Quorum contract](docs/protocol/quorum-contract.md)
- [Recovery contract](docs/protocol/recovery-contract.md)
- [Output contract](docs/protocol/output-contract.md)
- [Trace contract](docs/protocol/trace-contract.md)

## Capability ABI

Third-party capabilities should be addable without editing kernel/runtime
governance files. The expected shape is:

```text
capabilities/my-capability/
  capability.json
  workflow.py
  data_contract.py
  evidence_adapter.py
  runtime_nodes.py
  agents/*.json
```

Capability authors should not need to edit:

- `runtime/graph.py`
- `runtime/swarm/quorum.py`
- `runtime/swarm/recovery_engine.py`
- `runtime/writer_guardrails.py`
- `runtime/final_judge_guardrails.py`

See [capability authoring](docs/capability-authoring.md) and
[capability manifest docs](docs/protocol/capability-manifest.md).

## Driver Model

Drivers provide capability. Protocol provides authority.

| Driver | Purpose |
| --- | --- |
| ModelDriver | Model provider access through the configured model gateway boundary. |
| ToolDriver | Controlled tool execution through explicit registry contracts. |
| DataProviderDriver | Structured data with provenance, freshness, license, and adapter metadata. |
| StorageDriver | Trace and artifact persistence. |
| SandboxDriver | Restricted third-party execution. Planned beyond the current local runtime. |

See [driver model](docs/drivers/driver-model.md).

## Governance Subsystems

| Subsystem | Responsibility |
| --- | --- |
| Signal Protocol | Proposal, verification, contamination, and resolution. |
| Target Pressure | Runtime scheduling pressure for unresolved targets. |
| Stop Signals | Block tools, candidates, output, or publication. |
| Evidence Graph | Provenance, support/challenge links, contradictions, and evidence gaps. |
| Quorum | Commit only protocol-declared candidates. |
| Recovery | Recover by protocol-declared roles, tags, and tools. |
| Output Contract | Restrict Writer and FinalJudge behavior. |
| TraceStore | Explain why something happened. |

Governance docs:

- [Kernel/User/Driver boundaries](docs/architecture/kernel-user-driver-boundaries.md)
- [Swarm governance](docs/swarm-governance.md)
- [Signal spec](docs/swarm_signal_spec.md)
- [Evidence contract](docs/protocol/evidence-contract.md)
- [Output contract](docs/protocol/output-contract.md)
- [Trace contract](docs/protocol/trace-contract.md)

## Minimal Quickstart

The current reference runtime includes a no-key minimal distro. It uses the
`toy-review` protocol, deterministic mock model/tool drivers, local JSONL trace
storage, no network access, and no secrets.

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

pheroos init minimal ./minimal-workspace
pheroos run "review this claim: SQLite is an embedded database" --distro minimal --workspace ./minimal-workspace
pheroos trace latest --workspace ./minimal-workspace
```

Reference runtime setup for provider-backed local development:

```bash
scripts/start_litellm.sh
scripts/start_api.sh
```

Provider configuration lives in [configs/litellm.yaml](configs/litellm.yaml).
Connection activation and secret handling are described in
[connection control plane](docs/connection-control-plane.md) and
[security and permissions](docs/security-and-permissions.md).

## Conformance

The initial conformance CLI is implemented for manifest/protocol compatibility:

```bash
pheroos validate capabilities/toy-review/capability.json
pheroos conformance capabilities/toy-review
pheroos-conformance capabilities/toy-review
```

Current checks include:

- manifest schema
- protocol validation
- candidate declarations
- quorum fallback
- recovery protocol
- tool contracts
- output contract
- trace contract
- domain-neutral public ABI guard
- domain-neutral core runtime governance guard

See [conformance suite](docs/conformance/conformance-suite.md) and
[tests/conformance](tests/conformance).

## Reference Capabilities

| Capability | Role |
| --- | --- |
| `toy-review` | Minimal no-key protocol/conformance example. |
| `web-research` | Evidence-gathering example for sourced public-web answers. |
| `code-development` | Tool-assisted coding example with test, security, and patch gates. |
| `wrds-financial-data` | Reference `DataProviderDriver` for licensed financial data. |
| `value-investing-research` | Reference decision protocol for governed investment analysis. |

WRDS and value investing are examples. They are not PheroOS kernel concepts.

Reference examples:

- [Open multi-agent protocol examples](docs/examples/open-multi-agent-protocol-examples.md)
- [Generic research protocol](docs/protocol/examples/generic-research-protocol.md)
- [Minimal toy protocol](docs/protocol/examples/minimal-toy-protocol.md)
- [WRDS provider adapter](docs/protocol/examples/wrds-provider-adapter.md)
- [Value investing reference](docs/protocol/examples/value-investing-reference.md)

## Security Model

Current local controls:

- manifest validation
- permission declarations
- ToolRegistry boundary
- model gateway boundary
- secret redaction
- connection-scoped runtime materialization
- trace redaction
- capability diagnostics

Planned controls:

- signed capabilities
- capability provenance
- revocation metadata
- sandboxed third-party drivers
- network/filesystem allowlists with runtime enforcement
- WASM host-call boundary

Signed capabilities, sandboxed third-party execution, and network/filesystem
policy enforcement are not claimed as implemented in the current local runtime.

See [security and permissions](docs/security-and-permissions.md) and
[capability security roadmap](docs/security/capability-security-roadmap.md).

## Documentation Map

| Area | Links |
| --- | --- |
| Protocol docs | [overview](docs/protocol/overview.md), [spec v0.1](docs/protocol/protocol-spec-v0.1.md), [migration](docs/protocol/migration-from-current-pheroos.md) |
| Kernel docs | [kernel overview](docs/kernel/kernel-overview.md), [kernel syscalls](docs/kernel/kernel-syscalls.md), [OS plan contract](docs/kernel/os-plan-contract.md), [runtime context contract](docs/kernel/runtime-context-contract.md), [kernel/user/driver boundaries](docs/architecture/kernel-user-driver-boundaries.md) |
| Capability docs | [capability authoring](docs/capability-authoring.md), [capability runtime](docs/capability_runtime.md), [capability agent roadmap](docs/capability-agent-roadmap.md) |
| Driver docs | [driver model](docs/drivers/driver-model.md) |
| Security docs | [security and permissions](docs/security-and-permissions.md), [capability security roadmap](docs/security/capability-security-roadmap.md), [security policy](SECURITY.md) |
| Conformance docs | [conformance suite](docs/conformance/conformance-suite.md), [conformance tests](tests/conformance) |
| Examples | [examples](docs/examples/open-multi-agent-protocol-examples.md), [protocol examples](docs/protocol/examples), [minimal distro](distros/minimal/README.md) |
| Development docs | [contributing](CONTRIBUTING.md), [known gaps](docs/known-gaps.md), [acceptance audit](docs/pheroos-acceptance-audit.md) |

## Repository Map

```text
runtime/           Reference runtime, OS kernel, materialization, graph bridge.
runtime/swarm/     PheroOS governance subsystems and compatibility policies.
capabilities/      Capability manifests, protocol blocks, workflows, adapters.
tools/             Tool/provider adapters behind controlled execution boundaries.
pheroos/           Public CLI, protocol helpers, minimal distro, driver ABI modules.
distros/           Reference distro manifests and docs.
schemas/           Draft PheroOS protocol/capability/evidence/signal/trace schemas.
docs/protocol/     Public protocol contracts and examples.
docs/kernel/       Kernel ABI and runtime materialization contracts.
docs/examples/     Reference multi-agent protocol examples.
tests/conformance/ PheroOS public ABI and conformance tests.
pips/              Draft PheroOS Improvement Proposal process and ABI proposals.
```

## Project Status

Status labels: `implemented` means present in the reference runtime, not stable
public API; `draft` means present but still evolving; `experimental` means
usable for local/reference testing; `planned` means not implemented here yet.

| Area | Status | Notes |
| --- | --- | --- |
| Protocol manifest v0.1 | draft | Schemas, loader, and docs exist; compatibility is still evolving. |
| Reference runtime | experimental | Local FastAPI/LangGraph-backed runtime and compatibility bridge. |
| Capability loading | implemented | Capability manifests are discovered and validated by the runtime. |
| OSKernel planning | experimental | Plans capabilities, permissions, connections, and readiness. |
| Runtime materialization | experimental | Builds tenant-scoped runtime context from kernel plans. |
| ToolRegistry boundary | implemented | Tools are registered and invoked through controlled boundaries. |
| PheroOS governance loop | experimental | Signal, target, recovery, quorum, and output governance exist in `runtime/swarm`. |
| Evidence graph | experimental | Evidence graph and contracts exist; public ABI is still draft. |
| Stop signals | experimental | Stop-signal policies and runtime enforcement paths exist. |
| Quorum | experimental | Protocol-declared candidates are the intended authority boundary. |
| Recovery | experimental | Recovery policies are moving toward protocol-declared roles/tools. |
| Writer / FinalJudge contracts | experimental | Guardrails exist; protocol-first enforcement remains under active hardening. |
| Minimal distro | draft | No-key `init` / `run` / `trace` path is implemented; distro ABI is still evolving. |
| Conformance suite | draft | CLI checks and conformance tests exist; deeper levels are planned. |
| Signed capabilities | planned | Roadmap only. |
| Sandboxed capabilities | planned | Roadmap only. |
| Stable public ABI | draft | PIPs and schemas exist; do not treat the ABI as final. |

See [known gaps](docs/known-gaps.md) for current limitations.

## Contributing

Protocol, kernel ABI, driver model, security model, trace contract, and
conformance changes should go through the PheroOS Improvement Proposal process.
The PIP process exists as a draft in [PIP-0001](pips/PIP-0001-process.md).

For general contribution guidance, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

PheroOS is distributed under the terms in [LICENSE](LICENSE).
