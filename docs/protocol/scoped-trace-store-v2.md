# Scoped TraceStore v2 ABI

Status: Draft, additive ABI

Scoped TraceStore v2 defines the provider-neutral persistence boundary for
`ScopedTraceEvent` v1 envelopes. It does not change `TraceEvent`, `TraceStore`
v1, the Scoped Trace Event v1 wire, or either frozen v1 schema. It also does
not prescribe a database, queue, event bus, logger, or runtime.

## Contract

`ScopedTraceStoreV2` exposes only:

- scoped append with a versioned append receipt;
- immutable chronological snapshots and bound cursors;
- a portable checkpoint and deterministic restart;
- permanent scope retirement.

Every record is bound to an opaque canonical `scope_ref`, stream, contiguous
per-stream sequence, and the revalidated v1 envelope root. A trace identity or
transition identity may name only one envelope within a scope and stream.
Exact replay is idempotent and returns the original record. A changed envelope
under either identity is a conflict and must fail before mutation.

Portable objects use closed exact fields, explicit versions, canonical roots,
and defensive snapshots. Missing or unknown fields, implicit coercion,
noncanonical text or roots, nonportable values, and nonfinite numbers fail
closed. Stream and trace/transition identity text must be NFC-normalized and
must not contain NUL or unpaired Unicode surrogate code points.  Event bodies
and lineage keys and values apply the same recursive Unicode-scalar rule so
checkpoint bytes remain portable across implementations.

## Isolation and lifecycle

Sequences are contiguous independently for each `(scope_ref, stream)` pair.
Tenant/run scopes cannot observe or advance each other's history. A cursor is
bound to its scope, stream, next sequence, and exact prefix root, so a forged or
stale cursor cannot silently skip or splice records.

Retirement creates a scope tombstone bound to the complete history root.
Historical snapshot and cursor reads remain available after retirement. Every
new append, including exact replay, is permanently rejected, and restart must
preserve that decision.

A checkpoint has one canonical image: records are ordered by
`(scope_ref, stream, sequence)` and retirements by `scope_ref`. Reordered wire
values fail closed even when their members describe the same logical state;
implementations must not silently sort or repair an incoming checkpoint.

## Atomicity and conformance

The stdlib reference store validates and stages before one lock-protected
publication. Concurrent exact replay produces one canonical record; concurrent
distinct events may be scheduled in any order but cannot be lost, duplicated,
or leave a sequence gap. Failure before append or retirement publication
cannot expose partial state; checkpoint failure cannot expose a partial image.

The public Conformance TCK runs the same matrix against the reference adapter
and external adapters without putting expected answers in adapter requests. It
checks portable round trips, isolation, conflicts, restart/cursor consistency,
retirement, 32-worker races, mutation resistance, and failure atomicity.
