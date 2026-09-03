# PheroOS

Language: **English** | [简体中文](README.zh-CN.md)

[![tests](https://github.com/Ju1se/PheroOS/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Ju1se/PheroOS/actions/workflows/tests.yml)

PheroOS is the provider-free protocol-core package for governed multi-agent
runtimes, centered on authority and commit semantics.

> Agents are not authority. Protocol is authority.

PheroOS defines how an external runtime declares capabilities, scopes work,
verifies agent inputs, reaches a governed decision, records causal lineage, and
proves compatibility. It does not run agent loops, call models or tools, host an
API, or provide a database.

The validated public positioning is a governed authority/commit protocol.
Attention and pheromone code is retained only as private experimental
implementation detail; it is not part of the baseline public ABI or a claim of
demonstrated emergent or swarm intelligence.

## Project Status

| Property | Current state |
| --- | --- |
| Package | `pheroos 0.1.0` |
| ABI stability | Implemented, conformance-backed **Draft ABI** |
| Python | `>=3.12`; CI covers CPython 3.12, 3.13, and 3.14 |
| Runtime dependencies | None |
| Published distribution | None; the documented user path is a source checkout, while CI and the offline non-publishing RC rehearsal build and verify wheel/sdist artifacts |
| License | MIT |

Draft means that public shapes may still evolve through documented migration;
it does not mean that the reference paths are placeholders. Baseline,
authority/commit, durable-authority contracts and their atomic reference path,
Trace, and Conformance are implemented and exercised by
deterministic tests. Until the first stable ABI release, consumers should pin
an exact commit and the schema/profile versions they implement.
The checked Stable Core candidate remains
`draft / promotion_candidate / formal_stable=false`; no public lifecycle entry
has been formally promoted to Stable.

## Quick Start

Clone and install from source:

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Validate the minimal protocol and run its selected conformance profile:

```bash
pheroos version
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
```

CLI responses are versioned JSON. A conforming report contains `"ok": true`
and the exact profile and checks applied to the subject.

The top-level examples are source-checkout fixtures and are not included in the
wheel. Installed CLI, schema, ABI, and TCK commands work from any directory.

For development:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
pheroos source-conformance .
```

## Protocol Model

PheroOS separates runtime execution from protocol authority.

The runtime path is:

```text
capability manifest
-> strict Protocol validation
-> RuntimeScope and Kernel plan
-> external Driver binding and scoped invocation
-> governance-verified facts, reports, and signals
-> governed decision or explicit terminal outcome, including safe fallback
-> canonical Trace plus output authorization
```

The compatibility path is independent:

```text
manifest / adapter / installed artifact
-> versioned Conformance profile or TCK
-> deterministic PASS or FAIL report
```

The external runtime remains the orchestrator. It owns agents, model and tool
calls, scheduling, networking, credentials, durable infrastructure, and
delivery. PheroOS owns the contracts and deterministic reference semantics at
the trust boundaries.

## Architecture and Boundaries

| Public surface | Owns | Explicit boundary |
| --- | --- | --- |
| `pheroos.protocol` | Manifests, candidates, policies, schemas, loading, validation | Pure contract code; no Kernel, runtime, provider, or Conformance dependency |
| `pheroos.kernel` | Scope-aware plans, permissions, readiness, connections, exposure contracts | Decides availability; does not call tools/providers or make domain conclusions |
| `pheroos.drivers` | Provider-neutral descriptor and `declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace` lifecycle | Real adapters and provider SDKs stay external |
| `pheroos.governance` | Verification, evidence, quorum, collective decisions, risk, commit, certificates, finality, output gates | Agents and adaptive layers may propose; only Governance acting under the declared Protocol issues runtime decision authority |
| `pheroos.trace` | Canonical `TraceEvent`, scoped envelopes, validation, append-only store contract | Not a database, queue, event bus, or monitor daemon |
| `pheroos.conformance` | Manifest profiles, source checks, external-adapter matrices, Commit TCK | Deterministic, provider-free, and network-free |
| `pheroos.cli` | Thin versioned-JSON management commands | Local wrapper only; not an HTTP API or service |

The import graph stays one-way: Protocol, Drivers, and Trace are foundational;
Kernel depends only on Protocol and Drivers; Governance remains independent of
Kernel runtime machinery; Conformance composes the core surfaces; CLI delegates
to their public facades. Private engines are not a second ABI.

## Governance Invariants

- Agents, scouts, learned layers, evolutionary layers, and metacognitive layers
  can propose records. They cannot issue authority.
- A caller-controlled `verified` flag is not verification. Scout, recruitment,
  inhibition, and quorum inputs count only with a matching governance-issued
  `SignalVerification`.
- Governance commits only a candidate declared for the active target. Failed
  consensus selects the target's declared safe fallback.
- Private attention profiles may maintain bounded collective memory. That state
  is not evidence, truth, permission, quorum, a certificate, or output
  authority.
- Unknown critical versions, non-finite numbers, cross-scope records, malformed
  authority facts, and stale state heads fail closed.
- Governed Baseline Output v2 and collective output paths require four
  independent gates: an authoritative commitment to a declared candidate,
  provenance-bearing evidence, at least one `StopResolution` for the active
  target with no matching resolution blocked, and current publication
  permission.
- Optimal Commit makes every governance-issued terminal outcome deliverable.
  Publication and execution remain separate current-action decisions and never
  follow from delivery alone.

## Opt-In Decision Paths

Optional protocols do not change baseline manifests that do not declare them.

| Path | Manifest selection | Governed behavior | Conformance profile | Example |
| --- | --- | --- | --- | --- |
| Baseline | No optional attention or Commit declaration | Verified quorum, declared candidate, safe fallback | `pheroos-core-v1` | [`toy-protocol`](examples/toy-protocol/), [`e2e-protocol`](examples/e2e-protocol/) |
| Scoped Hybrid Replay v2 | Capability/Protocol v3 documents selecting `pheroos.protocol.v2` | Store-backed durable replay and scoped authority | Exact v2 Store, session, replay, and runtime-integration Conformance | [`hybrid-replay-protocol`](examples/hybrid-replay-protocol/) |
| Optimal Commit | `collective_commit_policy` | Evidence-governed truth, stability, liveness, certificates, optional distributed finality | Assurance-specific Commit profile | [`hybrid-commit-protocol`](examples/hybrid-commit-protocol/), [`distributed-commit-protocol`](examples/distributed-commit-protocol/) |

Optimal Commit selects `pheroos-commit-integrity-v1`,
`pheroos-hybrid-commit-v1`, `pheroos-certified-commit-v1`, or
`pheroos-distributed-commit-v1` according to its assurance and any declared
attention semantics. Attention is advisory only and cannot create evidence,
truth, permission, or authority.

### Optimal Commit: truth and authority

Optimal Commit keeps two channels separate:

| Channel | Inputs | May influence | Cannot do |
| --- | --- | --- | --- |
| Optional attention | External proposals and bounded memory | Search priority, candidate attention, external evidence collection | Create evidence, change commit truth, issue a certificate |
| Truth/authority | Verified principal, risk, membership, evidence, counterevidence, challenge, lease, stop, permission, replay, and prior-window records | Commit metrics, terminal outcome, certificate and action gates | Call providers or bypass the declared policy |

The manifest selects an assurance level:

| Assurance | Required result |
| --- | --- |
| `advisory` | Advisory or declared fallback; no epistemic commit |
| `evidence_bound` | Stable evidence decision plus a current local receipt |
| `certified` | Evidence-bound proof plus an independently verifiable portable certificate |
| `distributed` | Portable proof plus static-epoch Byzantine quorum finality |

`evaluate_hybrid_commit_step(request=...)` is the total finalization boundary.
Assurance never silently downgrades, identifier order never breaks a tie, and
the absolute deadline cannot be extended. At the deadline the result is an
explicit commit or non-commit terminal outcome. This guarantee requires the
external runtime to continue evaluation with monotonically increasing logical
steps; protocol-core neither schedules calls nor advances a clock. Distributed
assurance validates `n >= 3f + 1`, `2q - n > f`, exact witness/value roots,
replay, equivocation, and conflict freeze; networking and witness collection
remain external.

## Runtime Integration

Every external runtime request should create
`RuntimeScope(tenant_id, run_id, request_id)`. Its
tenant/run-derived `scope_ref` binds Kernel plans, Driver invocation/result
receipts, Governance authority domains, and scoped Trace. Matching data from a
different scope is not a retry and cannot reuse authority.

Durable v2 authority is an external adapter boundary:

- `GovernanceStateStoreV2` provides explicit heads, compare-and-swap, immutable
  prepared transitions, atomic state-plus-authority-Trace batches, receipts,
  rehydration, retirement, and tombstones.
- The v2 durable sequence is `prepare/validate an exact portable request (and a
  context-bound source proof where that ABI defines one) -> bind/open a
  request-scoped authority session -> atomic_commit_v2(state +
  authority-critical Trace) -> validate the typed committed result and receipt
  -> rehydrate and recheck inclusion/currentness before reuse`. A proposal
  cannot expose durable output authority before the exact state and Trace batch
  is committed and verified.
- `ScopedTraceStoreV2` is the separate provider-neutral append-only lineage
  contract for the selected tenant/run scope.
- Bundled in-memory stores are deterministic reference adapters, not production
  databases. External stores can run
  `run_governance_state_store_conformance_v2(...)` and
  `run_scoped_trace_store_conformance_v2(...)` before integration. The
  unversioned `GovernanceStateStore` remains the v1 trusted-host Draft
  compatibility path; generic `TraceStore` remains an independent
  reconstructible projection. Neither is an alias or silent upgrade to v2.

Driver declarations may use an opaque `config_ref`; provider kind, version, and
capability metadata may be declared, but credentials and concrete connection
configuration must stay outside manifests. An API key alone is insufficient to
run a multi-agent system: the external runtime must also provide the model/tool
adapters, orchestration, conformant stores, cancellation/retry/recovery, and
output delivery. PheroOS does not read the key.

See the [runtime integration contract](docs/protocol/runtime-integration.md)
and [runtime adapter guide](docs/protocol/runtime-adapter-guide.md).

## ABI Versioning and Compatibility

The original unversioned schema IDs and CLI aliases are frozen v1 compatibility
roots. New semantics use separate documents and exact selectors:

| Surface | Frozen v1 `$id` / alias | Versioned compatibility document | Current exact opt-in |
| --- | --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json`; `capability`, `capability-v1` | `schemas/capability-v2.schema.json`; `pheroos-capability-schema-v2`; payload `pheroos.protocol.v1` | `schemas/capability-v3.schema.json`; `pheroos-capability-schema-v3`; payload `pheroos.protocol.v2` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json`; `protocol`, `protocol-v1` | `schemas/protocol-v2.schema.json`; `pheroos-protocol-schema-v2`; payload `pheroos.protocol.v1` | `schemas/protocol-v3.schema.json`; `pheroos-protocol-schema-v3`; payload `pheroos.protocol.v2` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json`; `driver`, `driver-v1` | `schemas/driver-v2.schema.json` | `descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json`; `kernel`, `kernel-v1` | `schemas/kernel-v2.schema.json` | `plan_version=pheroos-kernel-plan-v2` |
| Runtime scope | None | None | `schemas/runtime-scope-v1.schema.json`; `pheroos-runtime-scope-v1` |
| Scoped authority | None | None | `schemas/authority-v2.schema.json`; `pheroos-authority-schema-v2`; `schemas/scoped-authority-tck-v2.schema.json`; `pheroos-scoped-authority-tck-v2` |

Schema-document versions and protocol payload versions are independent.
Capability/Protocol v3 is the exact Draft opt-in for scoped authority v2.
Driver `descriptor_version` is independent of the external provider version in
`DriverDescriptor.version`, and Kernel independently selects plans with
`plan_version`.

Readers select versions explicitly; object shape or package version never
silently promotes v1 to v2. Migration cannot invent readiness, scope,
capability, provider-version, or authority facts. The public Python shape and
lifecycle are checked in as
[`public-python-api-v1.json`](pheroos/conformance/abi/public-python-api-v1.json)
and
[`public-python-api-lifecycle-v1.json`](pheroos/conformance/abi/public-python-api-lifecycle-v1.json).

`pheroos validate`, `pheroos conformance`, and `pheroos profile show` select
legacy v1 manifest profiles. Capability/Protocol v3 artifacts use exact wire
validation and the dedicated v2 Store/session/runtime Conformance surfaces; a
legacy command never infers v2 from object shape.

Namespaced `x-*`, `ext.*`, and manifest `extensions` values remain open as
non-authoritative metadata. Adding a record that can affect commit truth or
authority requires a versioned ABI, validation, Trace lineage, Conformance, and
migration notes.

See the [schema migration rules](docs/process/schema-v1-v2-migration.md),
[API lifecycle](docs/process/api-lifecycle.md), and
[extension boundaries](docs/protocol/extension-points.md).

## CLI Reference

The local CLI never starts a service:

```bash
pheroos version
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos source-conformance .
pheroos profile show examples/hybrid-commit-protocol/capability.json
pheroos schema list
pheroos schema show commit
pheroos schema export commit > commit.schema.json
pheroos wire validate commit path/to/commit-record.json
pheroos wire validate capability-v3 examples/hybrid-replay-protocol/capability.json
pheroos tck run --version v1
pheroos tck run --version v2
pheroos abi show
pheroos abi diff
```

Unknown critical versions and malformed wire records return a versioned,
fail-closed JSON result and a non-zero exit status.

## Examples

All examples are deterministic, provider-free, network-free, and
domain-neutral.

| Example | What it proves |
| --- | --- |
| [`toy-protocol`](examples/toy-protocol/) | Minimal manifest, declared candidates, quorum and fallback |
| [`e2e-protocol`](examples/e2e-protocol/) | Minimal Protocol -> Kernel -> Driver -> Governance -> Trace slice |
| [`hybrid-replay-protocol`](examples/hybrid-replay-protocol/) | Scoped Hybrid Replay v2, restart, and fresh-process continuation |
| [`scoped-output-protocol`](examples/scoped-output-protocol/) | Baseline Output v2 activation, current grants, and atomic output commit |
| [`runtime-integration-protocol`](examples/runtime-integration-protocol/) | Exact-version Driver, authority, Trace, recovery, and delivery transcript |
| [`risk-v2-protocol`](examples/risk-v2-protocol/) | Store-backed risk authority and restart-safe currentness |
| [`support-v2-protocol`](examples/support-v2-protocol/) | Principal, membership, and support authority v2 |
| [`hybrid-commit-protocol`](examples/hybrid-commit-protocol/) | Attention/truth separation, stability, liveness and no downgrade |
| [`commit-evidence-v2-protocol`](examples/commit-evidence-v2-protocol/) | Durable evidence truth and counterevidence binding |
| [`commit-decision-v2-protocol`](examples/commit-decision-v2-protocol/) | Durable terminal decision with exact evidence lineage |
| [`commit-certificate-v2-protocol`](examples/commit-certificate-v2-protocol/) | Portable certificate verification, authority-leaf binding, and tamper rejection |
| [`commit-certificate-replay`](examples/commit-certificate-replay/) | Portable certificate reconstruction and mutation/replay rejection |
| [`distributed-commit-protocol`](examples/distributed-commit-protocol/) | Byzantine quorum, provisional state, conflict freeze and deadline |
| [`distributed-commit-v2-protocol`](examples/distributed-commit-v2-protocol/) | Durable distributed witness/finality authority |
| [`commit-finality-v2-protocol`](examples/commit-finality-v2-protocol/) | Decision-to-certificate-to-distributed finality composition |

## Conformance and Release Integrity

The frozen Commit TCK v1 contains 38 legacy adversarial vectors. TCK v2 uses 23
expected-free declarative cases: adapters receive inputs while the harness owns
expected results. The public reference adapter and an independent
standard-library spec model must agree; malformed, echo/constant, out-of-order,
state-leaking, and timeout adapters fail the harness.

Useful verification commands:

```bash
python -m pytest -q
pheroos source-conformance .
python scripts/generate_schema_artifacts.py --check
python scripts/generate_commit_tck.py --check
python scripts/generate_public_api_inventory.py --check
python scripts/generate_governance_public_api.py --check
```

CI tests CPython 3.12 through 3.14, validates the import DAG and public ABI,
exercises wheel and sdist installations from an external working directory,
and enforces reference performance budgets. Release gates bind the complete
workflow execution context, use a hash-closed Ubuntu x86_64 CPython 3.12-3.14
toolchain, snapshot the candidate from raw Git tree/blob objects, and derive
CycloneDX/SPDX identity from the exact wheel/sdist metadata and filenames.
Provenance proves artifact origin; it does not create protocol evidence or
governance authority. Proposed branch/tag rulesets and immutable-release
settings are checked-in inert policy, not active remote protection. This is a
build and attestation pipeline, not evidence of a GitHub Release or package
publication. See the
[Conformance Suite](docs/conformance/conformance-suite.md) and
[release checklist](docs/process/release-checklist.md).

## Documentation

- Core specification: [SPEC.md](SPEC.md)
- Historical attention profiles remain in the repository as private Draft
  implementation references; they are not part of the supported public ABI.
- Optimal Commit: [ABI reference](docs/protocol/optimal-commit-abi.md) and
  [v1 migration](docs/protocol/optimal-commit-v1-migration.md)
- Project process: [development index](docs/process/index.md),
  [CONTRIBUTING.md](CONTRIBUTING.md), and [CHANGELOG.md](CHANGELOG.md)
- Security: [SECURITY.md](SECURITY.md)

## Non-Goals

Protocol-core is not an agent framework, model-provider gateway, FastAPI or
product server, dashboard, LangGraph runtime, provider SDK wrapper, database,
queue, worker pool, daemon, plugin marketplace, or domain workflow package.
External runtimes may implement those concerns around the ABI.

## Development

Keep changes small, deterministic, domain-neutral, provider-free, and directly
covered by tests, examples, Trace, or Conformance. Do not weaken package
boundaries to make a test pass.

## License

See [LICENSE](LICENSE).
