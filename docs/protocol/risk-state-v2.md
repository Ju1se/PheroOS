# Risk State v2

Status: public Draft ABI. Risk State v2 is a durable, policy-bound authority
slice for WP-05. It is not yet a Stable or production-complete Commit profile.

## Boundary

Risk v2 records one exact assessment and the threshold projection selected by
an exact scoped manifest. It does not itself decide a candidate, issue support,
seal a commit window, certify finality, or authorize output.

`prepare_risk_state_advance_v2` derives the manifest, commit-policy, risk-policy,
profile, assurance, protocol, run, target, epoch, assessment, and threshold
bindings. It returns portable data plus a final, non-portable source proof. The
source proof is input integrity, not authority. Authority exists only when a
current `QUALIFY_EVIDENCE` issuer session atomically commits the request to the
selected StateStore v2 domain.

Portable dictionaries, roots, pickles, same-shape objects, and assessment
records never satisfy `VerifiedRiskSourceV2` or `VerifiedRiskStateV2`.

## State identity

Each exact target, run, and policy binding owns one fixed stream. Epoch is
versioned state inside that stream; it is intentionally excluded from stream
identity so long-lived runs do not consume one final head per epoch:

```text
authority:risk-v2:sha256(
  scope_ref \0 profile \0 assurance \0 manifest_root \0
  commit_policy_root \0 risk_policy_root \0 protocol_ref \0
  run_ref \0 target_ref
)
```

Each advance owns one transition:

```text
transition:risk-v2:sha256(stream_ref \0 advance_ref)
```

All text is canonical UTF-8 and forbids U+0000. A genesis snapshot uses the
versioned genesis root and reserved parent transition `genesis`. Later
snapshots form a complete replacement lineage with exact revision, epoch,
parent epoch, parent transition, parent snapshot, assessment predecessor,
current step, and source context bindings.

Within one epoch, risk bands may stay equal or increase, expiry is frozen, and
they cannot silently decrease. A band change requires
`window_reset_required`. A later epoch may reset both band and expiry, but must
advance monotonically and always requires `window_reset_required`; epoch jumps
are allowed and epoch rollback is rejected. The threshold record freezes every
selected bound, label, required challenge, minimum assurance, allowed outcome,
and namespaced policy extension into `threshold_root`.

## Atomic operation

`advance_risk_state_v2` performs the following order:

1. validate the exact portable request and request-bound authority session;
2. reconcile the transition before checking ephemeral source material;
3. require a current `QUALIFY_EVIDENCE` grant and matching issuer;
4. require the scoped manifest authority selector to match the selected domain;
5. load and revalidate the committed parent, including inclusion, finality, and
   historical position;
6. verify full replacement, monotonic lineage, freshness, and source binding;
7. atomically compare the risk, issuer-grant, and domain-lifecycle heads;
8. commit state together with `risk_state_advanced` and `risk_assessed_v2`.

The two Trace events are an ordered atomic batch. Both use an exact closed
lineage schema. They bind the authority session, manifest and policy roots,
profile/assurance, target, parent, snapshot, assessment, threshold, source
context, and complete read-set. The semantic event additionally records the
issuer, band, input roots, rationale codes, assessment method, validity window,
predecessor, reset decision, provenance, and canonical source Trace roots.

An exact retry returns the original committed receipt, including after a lost
response or later grant revocation. A different request under the same
transition id conflicts. A structurally valid historical snapshot remains
verifiable, but only the Store-current head may parent a new transition.

## Bounds

- 1,024 risk input roots and 1,024 source Trace roots;
- 128 rationale codes and threshold labels;
- 4,096 UTF-8 bytes per bounded text field;
- 2 MiB per complete canonical snapshot;
- JSON-safe non-negative integers;
- bounded depth, node count, and aggregate text before recursive decoding.

Arrays are exact, unique, and UTF-8 sorted. Namespaced extensions must be
JSON-safe, finite, deeply frozen, and included in the threshold root. No
provider, database, server, worker, network, or background runtime is part of
this ABI.

## Public verification

External StateStore implementations run
`pheroos.conformance.checks.risk_v2_contract.run_governance_risk_conformance_v2(...)`.
The provider-free [Risk v2 protocol example](../../examples/risk-v2-protocol/README.md)
shows manifest loading, grant/session binding, atomic commit, portable request
serialization, fresh-reader rehydration, fixed cross-epoch lineage, and dynamic
currentness using public ABI surfaces only. The reference Conformance Store is
test infrastructure, not a production persistence adapter.

Risk v2 does not import the legacy `_risk` authority owner. The shared
`RiskBand` vocabulary and deterministic policy projection live in a stateless
leaf with no issuance, registry, cursor, replay state, or Store access; the v1
Draft facade re-exports that same vocabulary for compatibility. All durable
assessment, threshold, lineage, currentness, and write authority remain owned
by the Risk v2 contracts and StateStore-backed operations.

## Promotion blockers

The public-only reference and independent Store Conformance matrices and the
provider-free restart example are active. Risk v2 remains Draft until the
downstream Commit-window consumer and complete WP-05 migration gates pass. The
source proof deliberately has no process-global issuance sentinel: complete
deterministic reconstruction establishes input integrity, while authority
remains exclusively in a current request-bound session and its selected
StateStore.
