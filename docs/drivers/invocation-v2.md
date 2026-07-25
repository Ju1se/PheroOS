# Driver Invocation ABI v2

Driver Invocation ABI v2 is the provider-neutral boundary between an external
runtime and a capability driver. It describes an invocation and its durable
idempotency receipt; it does not call a provider and does not grant governance,
commit, publication, execution, or output authority.

## Portable values

The public `pheroos.drivers` facade exports four strict wire values:

- `DriverInvocationRequestV2` binds scope, driver, invocation, operation,
  capability, idempotency key, payload, and request digest.
- `DriverInvocationResultV2` echoes every request identity, adds status,
  immutable result payload, nonblank provenance, and a result digest.
- `DriverInvocationReceiptV2` binds both digests and the result provenance to
  the same invocation identity.
- `DriverInvocationReplyV2` carries the exact request, result, and receipt and
  rejects any cross-binding.

Each value has an exact version discriminator, closed `to_dict`/`from_dict`
shape, and canonical JSON `to_wire`/`from_wire` representation. Unknown or
missing fields, type coercion, duplicate JSON keys, non-finite or noncanonical
numbers, non-NFC, NUL-bearing, or unpaired-surrogate text, digest mismatch,
noncanonical JSON, and oversized input fail closed.  The text rule applies
recursively to payload keys and values so different language runtimes hash the
same Unicode-scalar document. `scope_ref` must be the canonical lowercase
`sha256:` opaque reference produced by RuntimeScope; a tenant/run label is not
accepted as a scope identity.
Input mappings and sequences are detached and frozen at construction; emitted
dictionaries are detached copies.

The v2 values are additive. They do not depend on Kernel
`DriverInvokeRequest`, and they do not change the frozen Driver invocation and
ledger v1 behavior.

## Durable idempotency boundary

`DriverInvocationStoreV2` is a small runtime-checkable Protocol with only:

```text
record -> get -> retire -> checkpoint
```

The idempotency key is `(scope_ref, driver_id, idempotency_key)`. Repeating the
same exact request/result returns the same canonical receipt. Reusing that key
with a different request or result fails. Scope retirement removes active
receipts and persists a tombstone, so a restarted store cannot replay the
retired scope.

`InMemoryDriverInvocationStoreV2` is the deterministic, thread-safe standard
library reference implementation. Its checkpoint is versioned, canonical,
closed, digest-bound, and mutation-safe. It proves restart semantics for the
ABI; it is not a database, queue, worker, scheduler, provider gateway, or
runtime.

The Conformance adapter accepts only the closed failure stages in
`DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2`: `before_commit` and
`before_retire`. Failure injection occurs before the corresponding atomic
publication point. A failed record or retirement therefore leaves the previous
checkpoint byte-for-byte intact; failed retirement also leaves the receipt
current and does not publish a tombstone.

## Conformance

`DriverInvocationStoreConformanceAdapterV2` and
`run_driver_invocation_store_conformance_v2` define the provider-free black-box
TCK. The matrix checks:

- two operation results without placing expected answers in adapter requests;
- exact request/result/provenance binding;
- identical retry and conflicting-key behavior;
- 32-worker same-key convergence beginning from an empty store, followed by
  lookup, single-active-receipt, restart, and replay checks;
- tenant/run scope isolation;
- checkpoint restart and persistent retirement;
- checkpoint tamper rejection;
- failure-before-commit with no partial receipt and failure-before-retire with
  no lost receipt or premature tombstone.

The suite runs the same matrix against the reference store and an independent
standard-library test adapter. Echo, constant-result, malformed-result,
conflict-accepting, and failure-ignoring adapters are negative controls.

Receipts are replay/idempotency data only. JSON, pickle, copied dataclasses, or
receipt digests do not gain authority by being reconstructed or persisted.
