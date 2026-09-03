# Protocol ABI

`pheroos.protocol` defines the public manifest and validation surface for
governed runtimes.

The formal protocol-core specification is [SPEC.md](../../SPEC.md). Extension
boundaries are described in [extension-points.md](extension-points.md).
External runtime composition is described in
[runtime-integration.md](runtime-integration.md). The type-closed Draft
promotion-candidate boundary for external consumers is documented in
[stable-core-consumer.md](stable-core-consumer.md). The former swarm-memory
contract in [hybrid-pheromone-abi.md](hybrid-pheromone-abi.md) is retained for
historical reference only; it is not a supported public profile or a
conformance requirement. The implemented Draft Optimal Commit evolution that
keeps optional attention inputs separate from commit authority is specified in
[optimal-commit-abi.md](optimal-commit-abi.md).
Migration rules live in the corresponding Hybrid and Optimal Commit migration
documents. Completed execution plans remain as short link-compatible history
stubs and are not active specifications.

The accepted scoped authority v2 direction is frozen in
[authority-v2-decision.md](authority-v2-decision.md), with its
[threat model](authority-trust-model-v2.md) and
[migration contract](authority-v2-migration.md). The additive Draft WP-02
[StateStore v2 contract](authority-store-v2.md) implements the bounded read-set,
atomic state/Trace/receipt commit, historical inclusion, seal, total view, and
provider-neutral Conformance slice. The public Draft WP-03
[Authority Session v2 contract](authority-session-v2.md) composes that Store
with portable grants/requests and opaque store-, run-, request-, operation-, and
scope-bound handles for atomic `VERIFY_SIGNAL` and `RETIRE_DOMAIN` paths. The
Draft WP-05 [Hybrid Replay v2 ABI](hybrid-replay-v2.md) specifies the
scope/protocol/run/target replay stream, portable snapshot versus Store-verified
authority boundary, atomic parent/grant/lifecycle read-set, historical
rehydration, and restart-safe Hybrid memory without provider or runtime
infrastructure. Its public Draft lifecycle and reference/independent Store
Conformance matrix are active. The public Draft WP-05
[Commit Replay State v2 ABI](commit-state-v2.md) adds the target-scoped durable
replay bookkeeping slice with an explicit empty genesis, three-axis receipt
collision semantics, Store-reverified historical state, and atomic
`commit_replay_advanced` lineage. Its portable receipts do not verify upstream
evidence authority, and the slice is not Stable or production-complete until
later WP-05 upstream heads and consumers are migrated. The public Draft WP-05
[Risk State v2 ABI](risk-state-v2.md) adds an exact manifest-derived threshold
snapshot and durable assessment lineage. Epoch is state inside one fixed
target/run/policy stream; portable records do not become authority until a
current request-bound issuer session commits state and the two closed Trace
events atomically. The public Draft WP-05
[Support v2 ABI](support-v2.md) separates Principal Verification, Membership,
and Support into three durable owners, so principal eligibility and lease
support remain independently current and CAS-visible. The public Draft
[Commit Gate v2 ABI](commit-gate-v2.md) owns COMMIT Stop and Permission as
separate target-scoped streams and binds Replay, Risk, Principal Verification,
Membership, and Support in each atomic gate decision. The public Draft
[Commit Evidence v2 ABI](commit-evidence-v2.md) owns subject-aware evidence
replacement/history and exposes only Store-qualified projections to Decision;
portable evidence records, roots, and replay receipts are never authority.
The [Commit Certificate v2 Draft ABI](commit-certificate-v2.md) defines an
independently verifiable portable certificate plus a durable owner over the
actual Decision seal and eight authority leaves. Its portable verifier matrix
and durable cross-owner Conformance matrix are active. The
[Commit Finality v2 ABI](commit-finality-v2.md) is the canonical public identity
owner for the authority-neutral projection and opaque owner bridge; it exposes
no issuer and grants no authority to portable bytes. The public Draft
[Distributed Commit v2 ABI](distributed-commit-v2.md) owns four fixed durable
lanes for epoch, proposal, witness, and certificate state. Its public
conflict-observation path can only freeze a current witness lane after a trusted
verifier proves one principal signed two semantically distinct values; it
cannot add quorum support, advance proposal/certificate authority, or authorize
the alternate value. The public Draft
[Commit Decision v2 ABI](commit-decision-v2.md) has a dual-Store Conformance
matrix and provider-free terminal journey. Decision, Certificate, Distributed,
and their neutral Finality bridge are aggregate-activated together, including
durable verified, conflict, deadline, opaque-substitution, restart, and CAS
journeys. They remain Draft and are not a production-runtime claim. WP-04 also
activates the exact Capability and
Protocol Schema v3 selectors for opt-in `pheroos.protocol.v2` scoped local
authority; legacy schema selectors remain exact and are not inferred from
payload shape. Authenticated external-verifier, full runtime TCK, and Stable
promotion gates remain separate and inactive. None of these documents
reinterpret the existing Capability/Protocol v2 schema documents or make the
trusted-host v1 issuer surface a production credential.

Protocol code is contract code. It declares what exists and validates whether a
manifest is structurally compatible with the protocol.

The capability manifest schema is a public ABI artifact. The loader rejects
unknown non-namespaced fields, invalid primitive shapes, and invalid collection
shapes before constructing typed manifest objects.

## Owned Surface

- capability manifests
- protocol manifests
- target declarations
- candidate declarations
- quorum policy
- collective decision policy
- optional collective commit policy and assurance profile
- recovery policy
- evidence policy
- output policy
- trace policy
- driver declarations
- extension metadata
- validation diagnostics

## Import Boundary

The protocol package must not import kernel, governance, driver, conformance,
CLI, examples, app runtime modules, provider frameworks, or tools.

## Invariants

- A manifest declares at least one target.
- A manifest declares at least one candidate.
- Every candidate references a declared target.
- Quorum fallback references a declared safe fallback candidate.
- Collective fallback references a declared safe fallback candidate, or defaults
  to the quorum fallback.
- Recovery trigger targets are declared.
- Recovery failure candidates are declared.
- Writer fact creation is not permitted.
- Agent fact creation is denied when the evidence policy forbids it.
- Trace policy includes lineage for block, commit, recovery, and output decisions.
- Trace policy includes lineage for every event required by the selected
  baseline or Commit profile.
- Legacy collective and pheromone fields, when encountered, are bounded
  advisory inputs only; no public profile requires swarm or pheromone behavior.
- An activated collective commit policy binds a declared target and safe
  fallback, exact evidence/risk/window rules, bounded liveness, certificate
  mode, and any distributed fault model without changing baseline manifests.
- Secret-like manifest fields are rejected or diagnosed.
- Extension metadata is preserved without granting evidence, permission, quorum,
  commit, or output authority.

## Compatibility

Protocol ABI changes should follow
[api-lifecycle.md](../process/api-lifecycle.md).

Schema changes should keep checked-in artifacts under `schemas/` aligned with
schema export behavior.

The original Capability and Protocol schema IDs are frozen legacy v1 document
contracts. Their strict v2 schema-document versions still validate payload
`protocol_version=pheroos.protocol.v1`; schema-document selection and protocol
meaning are separate version axes. See the
[schema migration](../process/schema-v1-v2-migration.md).

Baseline protocols must not be forced to opt into swarm-specific behavior.
