# Scoped Authority TCK v2 Artifacts (Draft)

`schemas/scoped-authority-tck-v2.schema.json` describes the provider-free
Conformance vectors and actual-only reports for the reserved
`pheroos-scoped-authority-tck-v2` profile. Its `$id` is
`https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json`.

The direct Draft API is
`pheroos.conformance.scoped_authority_tck_v2`. It provides strict immutable
readers for:

- an expected-free request containing one declared case ID, operation, profile,
  and an existing Authority Wire v2 record;
- a closed case containing verifier-owned required-invariant labels and an
  optional real StateStore failure stage;
- a complete case artifact pinned to the exact StateStore, Authority Session,
  and Baseline Output Conformance versions;
- an actual-only report with exact booleans, closed diagnostic/failure values,
  and one result for every declared case.

The case vocabulary mirrors the active top-level StateStore, Authority Session,
and Baseline Output matrices. The invariant registry also includes every real
StateStore failure-injection stage and persisted-image tamper case. Partial,
duplicate, reordered, unknown-version, unknown-field, cross-bound request, and
expected-bearing artifacts fail closed.

Only the enclosing harness sees `required_invariants`. The subject request has
no `expected` outcome, and a report carries observations rather than an answer
key. This is an envelope invariant: canonical Authority Wire payload data is
not rejected merely because an application-owned nested key is named
`expected`. Passing the artifact reader or JSON Schema does not pass the TCK; an
independent harness must still execute the existing Conformance matrices and
compare actual observations with its retained invariants.

This schema is a Conformance vector/report format. It is not a runtime adapter
protocol, server, worker, plugin mechanism, Store implementation, or authority
source. It is Draft and does not promote `pheroos-scoped-authority-tck-v2` to
Stable.
