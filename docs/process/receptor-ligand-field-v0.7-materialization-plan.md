# Receptor-Gated Ligand Field v0.7 Materialization Review Plan

## 1. Status, scope, and authority

This document is a review-only execution plan for resolving the transition
dependency between the active v0.6 external lab and the inactive v0.7
candidate. It is not a run report, an activation record, a lock migration, or
evidence that any materializer already exists.

The plan is:

- provider-free;
- network-free;
- outcome-blind;
- authority-free;
- external-lab-only for executable review tooling;
- currently executable only as the `design-review` pass bound to
  `activation_ready=false`; future true vectors are reserved phase contracts,
  not present authority;
- prohibited from changing PheroOS ABI, TCK, Governance, Trace, Conformance,
  Optimal Commit, permissions, fallback, or output authority.

The two planned materializers are review instruments. They are not active
runners, controllers, arms, agents, evaluators, providers, or protocol
authorities. They cannot commit a candidate, authorize output, publish a
result, alter a lock, or make v0.7 active.

They are single-review-lifecycle, disposable audit compilers for the Section
18 materialization review, not the task reducer, full-scale runner, or
independent qualification verifier whose implementation is forbidden before
profile activation by v0.7 Section 1.1. Their source namespaces may never be
imported, copied, generated into, or treated as qualification evidence by the
later active runtime. A future runtime must use separately reviewed source and
cannot claim source independence merely because these audit compilers agreed.

This plan does not change any activation flag and does not implement any
materializer, reducer, runner, controller, provider, or experiment.

The `runtime-review` identity defined below is a reserved contract for the
later, separately reviewed runtime producer and qualification verifier. It
does not authorize the two disposable `ReviewAuditCompilerV1` programs to run
a third lifecycle pass or to become runtime source. Those audit compilers may
execute only the exact `design-review`, exact `promotion-review`, and retained
diagnostic attempts allowed by profile Section 1.2.

## 2. Frozen review inputs

The initial review inventory is exactly the immutable core commit:

```text
core_commit =
  9644acd0ae99970c47b169d4735dd2047b722fa1
core_commit_short = 9644acd
```

The candidate profile and companion at that commit are:

```text
profile_path =
  docs/process/receptor-ligand-field-experiment-profile-v0.7.md
profile_raw_sha256 =
  bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6
profile_byte_count = 119802

fixture_companion_path =
  docs/process/receptor-ligand-field-experiment-profile-v0.7-fixtures.json
fixture_companion_byte_count = 62097
fixture_companion_raw_root =
  sha256:322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360

fixture_input_set_root =
  sha256:0227f38c34f9d50b81b257675065e73ab1c18e02fff684ca851603b3d963aed8
positive_fixture_set_root =
  sha256:2a0e9ff10b6e2d5e2e42bebe77dd9c32f871a48638ad4d41a796995d1ce1613e
negative_fixture_set_root =
  sha256:ae57ce3f050c4f1560026ecb198cb274adfee6ffcf49282fb4520ecf6e12f4e5
fixture_semantic_manifest_root =
  sha256:dfbb83daea99bedc25e91c07f10aa301f42fba93808d57d9e6aaf395ae33feca
```

These are design-inventory bindings, not observed materialization results.
The companion remains frozen as:

```text
activation_ready=false
artifact_bytes_compiled=false
runner_implemented=false
receipt_artifact_bytes_present=false
status="draft-design-inventory-not-activation-ready"
```

Every pass is selected by a complete
`MaterializationReviewInputIdentityV1`, never by flags alone. Its exact keys
are:

```text
schema="pheroos-rglf-materialization-review-input-identity-v1"
phase_kind
core_commit
profile_path
profile_byte_count
profile_raw_sha256
companion_path
companion_byte_count
companion_raw_root
fixture_input_set_root
positive_fixture_set_root
negative_fixture_set_root
fixture_semantic_manifest_root
status
activation_ready
artifact_bytes_compiled
runner_implemented
receipt_artifact_bytes_present
identity_root
```

`identity_root` excludes itself and uses the review-only label
`rglf-v07-materialization-input-identity-v1`. `phase_kind` is one of
`design-review`, `promotion-review`, or `runtime-review`.

For `design-review`, every field is the exact value above and all four flags
are false. Future phases must provide a fully concrete immutable core commit,
profile/companion bytes and roots before R0 starts; metavariables, inherited
Section 2 bytes, or runtime-selected fields are refused.

The proposed exact future statuses and vectors are:

```text
promotion-review:
  status="activation-candidate-materialization-reviewed-runtime-not-implemented"
  activation_ready=true
  artifact_bytes_compiled=true
  runner_implemented=false
  receipt_artifact_bytes_present=true

runtime-review:
  status="activation-candidate-runtime-reviewed"
  activation_ready=true
  artifact_bytes_compiled=true
  runner_implemented=true
  receipt_artifact_bytes_present=true
```

Those future values have no effect unless an atomic profile/companion
amendment explicitly adopts them and recomputes all identities. If the
normative profile rejects either status/vector, the review remains blocked;
the plan cannot override it.

The review must reject a different commit, profile byte sequence, companion
byte sequence, count, order, or embedded root. A later atomic amendment
creates a different candidate and invalidates the review identity above.

## 3. Resolving the active/candidate dependency

For `design-review` and `promotion-review`, the active external-lab worktree
and lock remain on v0.6 throughout review. Candidate tooling is developed only
in an isolated external-lab worktree at an immutable candidate commit recorded
as:

```text
CANDIDATE_EXTERNAL_COMMIT
```

`CANDIDATE_EXTERNAL_COMMIT` is a required future receipt field, not a value
claimed by this plan.

The separation rule is:

```text
active external lab
  -> clean, v0.6 lock, no candidate source, no review writes

isolated candidate worktree
  -> review-only source and artifacts, no active lock mutation

core 9644acd
  -> immutable design-review input, not active authority
```

The candidate worktree may contain source-independent review materializers
without making them active. Activation is determined only by a later reviewed
profile/companion candidate and atomic external lock migration. Merely
creating, running, or committing review tooling has no activation effect.

For a future `runtime-review`, the required predecessor is instead the exact
post-profile-lock-migration state described in Section 10: v0.7 methodology is
active, the prior runtime source binding is still unchanged, and
`v07_runtime_implemented=false`. The new runtime producer and independent
qualification verifier remain in an isolated candidate commit until the
implementation-source migration. The disposable review compiler namespaces
must not be present on their import paths.

Before every phase, the supervisor records the phase-specific predecessor
external-lab HEAD, tracked-tree root, porcelain status root, active lock
bytes/root, active profile identity, and expected runtime-source binding. The
same values must be re-read after the phase. Any predecessor worktree or lock
change blocks the review.

## 4. Candidate source separation

For `design-review` and `promotion-review`, the isolated external candidate
must use three disjoint source namespaces:

```text
review/v07/materializer_a/
review/v07/materializer_b/
review/v07/supervisor/
```

Materializer A and Materializer B must independently implement:

- canonical parsing and serialization;
- the 12 base constructors;
- literal selector and RFC 6901 path resolution;
- operation transactions and preconditions;
- reseal policies;
- positive transition checking;
- negative validation stages and precedence;
- receipt and artifact root recomputation.

They may share only:

- the language standard library;
- immutable profile and companion bytes;
- immutable input files explicitly named in the review manifest;
- operating-system process and filesystem primitives.

They must not share source, generated source, reducer helpers, schema helpers,
canonicalization helpers, operation dispatch, receipt constructors, test
fixtures, caches, serialized intermediate objects, or imported runtime
modules.

The following are prohibited in both directions:

- static or dynamic imports across A and B;
- imports from an active v0.6 materializer, runner, or reducer namespace;
- imports from production controller, evaluator, provider, or outcome code;
- symlinks, namespace-package merging, path injection, shared bytecode, or
  generated code crossing the source boundary;
- `eval`, `exec`, runtime module loading, plugin discovery, or subprocess use
  to call the other materializer;
- reading the other materializer's intermediate outputs before both sides
  have sealed their own results.

The supervisor may launch, constrain, hash, and compare A and B. It cannot
implement or import materialization semantics. Its source root must differ
from both materializer source roots.

Static source inventory, AST/import audit, runtime import inventory, resolved
module paths, Git blob IDs, file modes, and source-tree roots are mandatory
evidence. Any shared non-standard-library semantic source blocks the review.

For `runtime-review`, A denotes the separately reviewed runtime producer and B
denotes the separately implemented qualification verifier. They use their own
disjoint runtime, verifier, and supervisor source namespaces; none may reuse
either `review/v07/materializer_*` namespace. The same cross-import,
source-root, helper-sharing, generated-code, and supervisor restrictions apply
to their materialization-integrity roles. This role mapping does not authorize
runtime implementation before the profile-lock migration in Section 10.

### 4.1 Semantic bodies and source-bound wrappers

A/B equality is defined at two distinct layers.

`MaterializationSemanticBodyV1` has exact keys:

```text
schema="pheroos-rglf-materialization-semantic-body-v1"
phase_identity_root
artifact_kind
stable_id
canonical_payload_root
profile_defined_root_pairs
expected_code
observed_code
rejected
verified
semantic_body_root
```

`artifact_kind` is the closed enum `base|positive|negative`. `stable_id` is the
literal base artifact ID for `base` and the literal fixture ID for
`positive|negative`. `canonical_payload_root` is
`RAW(exact_source_independent_payload_bytes)`, where the bytes are exactly:

| artifact kind | exact source-independent payload bytes |
| --- | --- |
| `base` | `C(canonical_base_object)||LF` emitted by the declared R3 constructor |
| `positive` | `C(canonical_post_closure_transaction_product)||LF` from R4, excluding `PositiveFixtureReceiptV07`, its receipt artifact, manifests, and all review wrappers |
| `negative` | the exact raw bytes produced by the declared R5 operation transaction and passed unchanged to its judge; these bytes may intentionally be non-canonical, truncated, appended, duplicate-key, partial, or non-JSON |

The payload cannot be reprojected, normalized after execution, or replaced by
a selected subset. The historical field name `canonical_payload_root` does not
authorize parsing, re-emitting, repairing, or canonicalizing negative bytes.

`profile_defined_root_pairs` is an array of exact objects with keys
`root_locator,root_value`. `root_value` is its full
`sha256:<lowercase-hex>` value. `root_locator` is unique and has one of these
closed forms:

```text
companion#<absolute RFC 6901 JSON Pointer>
payload#<absolute RFC 6901 JSON Pointer>
derived#/<literal v0.7 root field name>
```

The first two forms locate a literal root in the exact companion or exact
source-independent payload preimage; RFC 6901 escaping is mandatory. The
third is used only when v0.7 defines an exact root preimage but the derived
root is not embedded in either object. For example, repeated expected receipt
roots use distinct locators such as
`companion#/positive_fixtures/0/expected_receipts/0/receipt_root`; they are not
collapsed under the field name `receipt_root`. Entries are sorted by UTF-8
bytes of `root_locator`, with no duplicate or unknown locator, and contain all
and only source-independent roots defined by v0.7 and applicable to that exact
artifact instance. The array excludes materializer source, attempt,
observation, outer receipt, and outer manifest roots.

The status matrix is exact:

| artifact kind | `expected_code` | `observed_code` | `rejected` | `verified` |
| --- | --- | --- | --- | --- |
| `base` | `null` | `null` | `false` | `true` |
| `positive` | `null` | `null` | `false` | `true` |
| `negative` | exact declared code | same exact observed code | `true` | `true` |

`verified=true` in this body means only that the producing side passed every
profile-defined, source-independent local predicate before sealing. It neither
asserts nor replaces later cross-role verification; only the source-bound
wrappers and profile receipts can establish that separate fact.

`semantic_body_root` excludes itself and uses
`rglf-v07-materialization-semantic-body-v1`. A and B must independently
produce byte-identical source-independent, phase-bound semantic bodies and the
same body root.

`MaterializerEvidenceWrapperV1` has exact keys:

```text
schema="pheroos-rglf-materializer-evidence-wrapper-v1"
phase_identity_root
role_pair
producer_source_root
verifier_source_root
supervisor_source_root
attempt_id
observation_root
semantic_body_root
profile_receipt_root
artifact_manifest_root
wrapper_root
```

`role_pair` is `A-producer/B-verifier` or `B-producer/A-verifier`.
`wrapper_root` excludes itself and uses
`rglf-v07-materializer-evidence-wrapper-v1`. The two wrappers must bind the
same semantic body root and distinct producer/verifier source roots. Their
bytes, observations, wrapper roots, and source-bound artifact manifest roots
are expected to differ and are each verified against their own preimage.
Equality of source-bound wrappers is not an acceptance condition.

Profile receipt/artifact equality is artifact-specific:

- `PositiveFixtureReceiptV07` and its positive receipt artifact are
  source-bound by the producer/verifier roots and therefore differ across role
  pairs;
- `NegativeFixtureReceiptV07` has no source field, so each of the 56 negative
  receipts and the negative receipt artifact must be byte-identical across
  role pairs;
- both positive and negative
  `FixtureReceiptArtifactManifestV07` objects are source-bound and therefore
  differ across role pairs;
- when an artifact kind has no profile receipt, `profile_receipt_root` in the
  wrapper is exactly `null`.

Both materializers first seal their own semantic products without reading the
other side. The supervisor then performs two cross-verification passes:

```text
A-produced artifacts -> B verifier -> A-producer/B-verifier wrapper
B-produced artifacts -> A verifier -> B-producer/A-verifier wrapper
```

This satisfies the positive-fixture source-independence requirement without
pretending that a source-bound `PositiveFixtureReceiptV07` can be identical
across role pairs. Negative receipts and identity-free canonical artifacts
may be byte-identical; their outer evidence wrappers still remain
source-bound and distinct.

## 5. Process and filesystem isolation

Each materializer runs in a fresh process with:

- an empty provider-key environment;
- no inherited OpenAI, MiniMax, Zhipu, or other model credential;
- network denied at process and test level;
- an explicit read-only input directory;
- a unique write-only temporary output directory;
- no access to the active external-lab worktree except its supervisor-recorded
  read-only identity;
- a restricted import path containing only its own namespace and the standard
  library;
- deterministic locale, timezone, encoding, and hash-seed settings.

Materializer A cannot read B's output directory and B cannot read A's output
directory until both produce sealed completion manifests. Comparison occurs
in a third supervisor-owned directory.

All writes use:

```text
temporary file -> flush -> fsync -> close -> raw-root verification
-> no-overwrite atomic rename -> directory fsync
```

Existing content-addressed files must match byte-for-byte or cause refusal.
No evidence file may be silently replaced.

## 6. Review phases

### Phase R0 — Active-state freeze

Before any executable starts, record one complete
`MaterializationReviewInputIdentityV1` as `phase_identity`, verify its root,
and make it immutable for the whole pass. Record and verify:

1. the phase-specific predecessor external lab is clean and its worktree,
   lock, active-profile, and runtime-source roots equal the frozen predecessor
   snapshot;
2. for `design-review`, every `phase_identity` field equals Section 2,
   including core commit `9644acd0ae99970c47b169d4735dd2047b722fa1`,
   status, roots, byte counts, and the four false flags;
3. for `promotion-review`, the active predecessor still identifies v0.6 and
   `phase_identity` equals one fully concrete immutable activation-candidate
   commit with the exact proposed promotion status/vector in Section 2;
4. for `runtime-review`, the predecessor is the exact reviewed profile-lock
   migration state, `v07_runtime_implemented=false`, and `phase_identity`
   equals one fully concrete immutable runtime-candidate commit with the exact
   proposed runtime status/vector in Section 2;
5. the profile and companion exact bytes independently hash to the byte
   counts and raw roots named by `phase_identity`;
6. no provider key is present in the review environment;
7. the network denial probe succeeds;
8. no sealed outcome artifact is mounted or addressable.

Unknown phase kinds, mixed identities, a field inherited implicitly from
Section 2, an unbound placeholder, or an identity selected after execution
starts are refusals. The legacy label `R0-PROMOTION` means exactly
`phase_kind=promotion-review`; it is not a partial override of design inputs.

Failure stops all later phases.

### Phase R1 — Candidate commit and source audit

Apply the phase-specific source rule:

- `design-review`: create the isolated candidate worktree, develop the two
  disposable review materializers and supervisor there, and freeze them in one
  clean immutable external commit;
- `promotion-review`: use that exact same immutable review-compiler commit;
  source edits, generated-source changes, dependency changes, or a different
  source inventory are refusals. Independently prove that promotion changed
  only the complete input identity/status/flag vector and mechanically
  propagated roots allowed by profile Section 1.2; otherwise the compiler is
  invalid and the design/source review restarts;
- `runtime-review`: use the later immutable runtime-producer,
  qualification-verifier, and supervisor commit from Section 10, with both
  disposable audit compiler namespaces absent and unimportable.

Record:

- candidate commit;
- A, B, and supervisor source inventories;
- Git blob IDs and file modes;
- three source roots;
- clean-worktree evidence;
- static and runtime import audits.

The commit is not merged into the active worktree and is not written into the
active lock.

### Phase R2 — Canonical companion preflight

A and B independently:

1. parse the exact companion byte sequence and byte count named by
   `phase_identity`;
2. reject duplicate keys, non-canonical encoding, trailing bytes, or missing
   final LF;
3. re-emit `C(parsed_json)||LF` and require byte equality;
4. verify exact top-level keys, counts `12/3/56`, order declaration, and the
   complete status/flag vector in `phase_identity`;
5. recompute and match the exact top-level
   `fixture_input_set_root`, `positive_fixture_set_root`,
   `negative_fixture_set_root`, and `fixture_semantic_manifest_root` named by
   `phase_identity`;
6. for each positive fixture, recompute only the root families actually
   defined by v0.7: `source_prefix_root`, `fixture_input_root`, every expected
   receipt `receipt_root`, `expected_receipt_set_root`, and
   `fixture_commitment_root`;
7. for each negative fixture, recompute the v0.7
   `operation_transaction_root` over its literal operation array and
   `recipe_root` over its exact recipe.

Their canonical semantic preflight bodies must agree byte-for-byte. Each
materializer's outer receipt separately binds its distinct source root,
attempt ID, and observation root and therefore is not expected to be
byte-identical to the other receipt. A self-reported root without exact
preimage verification is insufficient.

### Phase R3 — Twelve base constructors

A and B independently materialize the companion's exact base array in
`g2-v07-constructor-rank-then-base-id-v1` order:

| ordinal | base artifact ID | constructor |
| ---: | --- | --- |
| 0 | `base:environment:T1:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 1 | `base:environment:T2:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 2 | `base:environment:T3:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 3 | `base:environment:T4:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 4 | `base:environment:T5:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 5 | `base:environment:T6:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 6 | `base:environment:T7:A4:N100:S9000:R0` | `g2-v07-base-scale-environment-v1` |
| 7 | `base:suite:A` | `g2-v07-base-suite-v1` |
| 8 | `base:replica-pair:A-B` | `g2-v07-base-replica-pair-v1` |
| 9 | `base:labels:T7:A4:N100:S9000:R0` | `g2-v07-three-way-label-fixture-base-v1` |
| 10 | `base:source:minimal` | `g2-v07-source-auditor-base-v1` |
| 11 | `base:process:success` | `g2-v07-process-transcript-base-v1` |

The seven environment constructors use the exact companion parameters:
`agent_count=4`, `event_count=100`, `seed=9000`, `repeat_id=0`, `steps=50`,
and their literal task ID. The suite, replica pair, labels, source inventory,
and process transcript use only their exact companion parameter objects.

No constructor may read a sealed outcome, provider, active runner, evaluator,
or controller. Each side emits:

- canonical base bytes;
- raw root and byte count;
- constructor/parameter preimage;
- normalized-view commitment;
- exposed path inventory;
- construction trace;
- source root.

A and B must produce byte-identical base artifacts and matching path
inventories for all 12 IDs. A count-only or eligibility-only record does not
satisfy this phase.

### Phase R4 — Three positive transactions

For each of the exact three companion positive fixtures, A and B independently:

1. resolve the literal base and selector;
2. verify every operation precondition;
3. execute the ordered transaction atomically;
4. apply `positive-fixture-closure-v1`;
5. preserve zero authority;
6. recompute the exact fixture input, expected receipt, receipt-set, and
   fixture commitment roots;
7. execute the declared branch transition;
8. compare observed receipt bodies byte-for-byte with the companion bodies.

The review requires exact coverage of:

- `T4-BRANCH-COMPLETION`;
- `T4-BRANCH-PARTIAL`;
- `T4-BRANCH-FAILURE-RELEASE`.

Fixture execution cannot replace the non-fixture T4 qualification path and
cannot authorize any output.

### Phase R5 — Fifty-six negative transactions

For every negative fixture in exact fixture-ID order, A and B independently:

1. bind the exact base, selector, recipe, and operation array;
2. recompute the operation transaction and recipe roots;
3. verify all preconditions before committing the transaction;
4. execute the transaction in array order or reject it atomically;
5. apply only the declared reseal policy;
6. invoke only the declared judge and validation stage;
7. apply the frozen within-stage precedence;
8. stop at the first applicable failure code;
9. require `observed_code == expected_code`;
10. emit exactly one rejection receipt with `rejected=true`.

Missing, duplicate, additional, reordered, skipped, or post-selected fixtures
block the whole phase. Timeout, crash, OOM, RSS failure, partial output, and
source-audit rejection remain intent-to-run outcomes and cannot be deleted
from the evidence set.

The five total `duplicate` operations must additionally prove:

- source exists and is a direct child of the declared container;
- object destination keys `100`, `100`, and `980` are absent;
- array insertion index `1` is in bounds;
- copied embedded sequence, ordinal, ID, and root are unchanged;
- no duplicate JSON object key is created.

### Phase R6 — Independent A/B comparison

Only after A and B have sealed their outputs may the supervisor expose both
manifests to the comparison step. It must compare:

- the source-independent canonical bytes, path-inventory bytes/roots, and
  `MaterializationSemanticBodyV1` roots for all 12 base artifacts;
- the source-independent transaction products and semantic bodies for all 3
  positive fixtures and all 56 negative fixtures;
- all profile-defined operation, recipe, set, semantic, trace, artifact, and
  receipt roots for which v0.7 defines equality;
- all expected and observed codes;
- each source-bound wrapper and manifest against its own exact preimage,
  including distinct producer/verifier source roots, role pair, attempt,
  observation, and outer roots;
- positive profile receipts/artifacts as source-bound non-equal pairs,
  negative profile receipts/artifacts as source-independent byte-equal pairs,
  and both positive/negative artifact manifests as source-bound non-equal
  pairs;
- both cross-role pairs:
  `A-producer/B-verifier` and `B-producer/A-verifier`;
- source and import evidence, including the required source-root
  non-equalities;
- resource and intent-to-run ledgers.

Any mismatch where equality is required, or equality where a source-bound
non-equality is required, is a refusal. The two wrappers, observations,
source-bound manifests, positive profile receipts, and positive receipt
artifacts must differ; negative profile receipts and their receipt artifact
must agree byte-for-byte. A majority vote, tolerance, normalization after the
fact, or manual selection of one side is prohibited.

### Phase R7 — Adversarial review

Both implementations and the supervisor must prove fail-closed behavior for
at least:

- companion byte flip, truncation, append, duplicate key, and root mismatch;
- base-array permutation, duplicate ID, unknown constructor, and wrong order;
- missing, duplicate, additional, or reordered positive/negative recipe;
- duplicate object destination already present;
- duplicate array index out of bounds;
- duplicate mode/container mismatch or cross-parent source;
- forged schema-stage expected code or reordered schema precedence;
- forged OOM-as-crash and crash-as-OOM classifications;
- step missing classified as coverage rather than sequence;
- event/job/intent duplicate classified as sequence rather than coverage;
- operation, recipe, receipt, set, artifact, or manifest root tampering;
- A/B identical source root, cross-import, shared helper, symlink, generated
  shared code, or runtime import escape;
- partial write, crash before rename, timeout, OOM, unmeasurable RSS, or
  over-limit RSS;
- dirty predecessor worktree, changed phase-specific predecessor lock, changed
  phase identity/core commit, or changed candidate commit;
- provider credential access, socket use, sealed outcome read, or evaluator
  import.

Each tamper must produce a retained refusal receipt. A test that merely raises
an unclassified exception is not acceptance evidence.

### Phase R8 — Bundle sealing and independent reread

After all prior phases pass, create a content-addressed review bundle. The
bundle is review evidence only and does not enter the active lock.

Required logical contents:

```text
input/
  phase-identity.json
  profile bytes
  companion bytes
  predecessor-lock-snapshot.json
source/
  materializer-a-source.json
  materializer-b-source.json
  supervisor-source.json
  import-audit.json
materializer-a/
  base manifest and 12 artifacts
  positive artifact and 3 receipts
  positive FixtureReceiptArtifactManifestV07
  negative artifact and 56 receipts
  negative FixtureReceiptArtifactManifestV07
  semantic-body-inventory.json and exact 71 MaterializationSemanticBodyV1 records
materializer-b/
  base manifest and 12 artifacts
  positive artifact and 3 receipts
  positive FixtureReceiptArtifactManifestV07
  negative artifact and 56 receipts
  negative FixtureReceiptArtifactManifestV07
  semantic-body-inventory.json and exact 71 MaterializationSemanticBodyV1 records
cross-verification/
  A-producer-B-verifier/
    wrapper-inventory.json and exact 71 MaterializerEvidenceWrapperV1 records
  B-producer-A-verifier/
    wrapper-inventory.json and exact 71 MaterializerEvidenceWrapperV1 records
supervisor/
  intent-to-run ledger
  resource observations
  ab-comparison.json
  adversarial-receipts.json
review-manifest.json
```

Each `semantic-body-inventory.json` has exact keys:

```text
schema="pheroos-rglf-materialization-semantic-body-inventory-v1"
phase_identity_root
materializer_role
body_count=71
ordered_semantic_body_roots
inventory_root
```

`materializer_role` is `A` or `B`. The root order is the closed artifact rank
`base<positive<negative` followed by UTF-8 bytes of `stable_id`.
`inventory_root` excludes itself and uses
`rglf-v07-materialization-semantic-body-inventory-v1`. All 71 exact body
preimages must be present beside the inventory. The A and B inventory objects
differ by role, while every aligned semantic body and body root must be
byte-identical.

Each `wrapper-inventory.json` has exact keys:

```text
schema="pheroos-rglf-materializer-wrapper-inventory-v1"
phase_identity_root
role_pair
wrapper_count=71
ordered_wrapper_roots
inventory_root
```

`ordered_wrapper_roots` contains the full roots of the 12 `base`, 3
`positive`, and 56 `negative` wrapper records, ordered first by the closed
artifact rank `base<positive<negative` and then by UTF-8 bytes of `stable_id`.
`inventory_root` excludes itself and uses
`rglf-v07-materializer-wrapper-inventory-v1`. The corresponding 71 exact
wrapper preimages must be present under the same role-pair directory; a
root-only list without those records is incomplete.

Every JSON record is `C(record)||LF`. Every artifact filename is derived from
the SHA-256 of its exact bytes. Manifests bind `phase_identity_root`, byte
count, raw root, source-independent semantic roots, source-bound wrapper roots,
candidate commit, core commit, and previous evidence where applicable. Raw
file roots do not write themselves into their own preimages.

A fresh process must reread the closed bundle with neither materializer
importable, recompute every file and manifest root, verify exact inventory,
reconfirm equality of source-independent semantic bodies and required inequality
of source-bound wrappers, and confirm that no undeclared file is present.

## 7. Resource supervision

The supervisor applies the exact v0.7 resource policy. In particular, an
environment attempt has the frozen `900` second limit and normalized
`4 GiB` peak RSS limit where specified by the profile. Platform units and
normalization evidence must be retained.

Each A/B unit has one primary intent-to-run record. A diagnostic retry:

- receives a distinct retry identity;
- cannot overwrite or replace a failed primary;
- remains in the append-only ledger;
- cannot convert a failed review into acceptance.

Timeout, OOM, crash, signal, RSS-limit, RSS-unit, partial segment, missing
receipt, or supervisor uncertainty blocks the review. The child cannot certify
its own crash or peak RSS.

## 8. Exact acceptance and refusal

The only review decision values are:

```text
materialization-review-passed
materialization-review-blocked
```

`materialization-review-passed` requires all of the following:

1. exact complete `phase_identity`, profile/companion bytes, counts, status,
   flags, roots, and immutable phase-specific core commit;
2. unchanged clean phase-specific predecessor worktree, lock, active-profile
   identity, and runtime-source binding before and after every phase;
3. clean immutable candidate external commit;
4. three distinct source roots and passing static/runtime import audits;
5. byte-exact A/B agreement for all 12 base artifacts;
6. exact A/B source-independent semantic agreement, two cross-role
   verifications,
   and valid distinct source-bound wrappers for all 3 positive fixtures;
7. exact A/B source-independent semantic agreement, `rejected=true`,
   expected/observed-code equality, and valid source-bound wrappers for all 56
   negative fixtures;
8. complete content-addressed artifacts, ledgers, receipts, manifests, and
   fresh-process reread;
9. every mandatory adversarial test rejected at its declared boundary;
10. zero outcome reads, zero provider calls, zero network use, zero authority,
    and zero active-lock writes;
11. no timeout, crash, OOM, RSS uncertainty, partial write, missing record, or
    unclassified exception.

Any false or unknown item yields `materialization-review-blocked`. There is no
partial pass, warning pass, quorum override, manual waiver, or “close enough”
byte comparison.

The retained review-only refusal reason set is:

```text
MR-ACTIVE-STATE
MR-INPUT-BINDING
MR-SOURCE-COLLISION
MR-IMPORT-BOUNDARY
MR-BASE-MATERIALIZATION
MR-TRANSACTION
MR-EXPECTED-CODE
MR-RECEIPT
MR-AB-MISMATCH
MR-RESOURCE
MR-TAMPER
MR-OUTCOME-READ
MR-PROVIDER-OR-NETWORK
MR-ARTIFACT-INTEGRITY
MR-UNCLASSIFIED
```

These are review-plan labels, not PheroOS protocol or Conformance ABI.

## 9. Failure return paths

Every failure first retains the failed intent, artifacts, logs, observations,
and refusal receipt and leaves the phase-specific predecessor worktree and
lock unchanged. It is then classified without changing the expected result:

1. **Specification or companion under-specification.** If profile text,
   companion literal, root binding, predicate, precedence, or the review
   contract admits zero or multiple legal interpretations, revise profile and
   companion atomically in a new core review commit. Recompute every affected
   raw, operation, recipe, set, semantic, dependency, and chain root; create a
   newly source-reviewed isolated compiler commit when materialization
   semantics changed; restart at R0.
2. **Audit-source defect or independence failure.** If the immutable compiler
   source, supervisor, import boundary, or implementation is wrong while the
   specification remains total, apply the phase-specific path:
   - for `design-review|promotion-review`, leave profile and companion bytes
     unchanged, fix only in a new immutable isolated audit-compiler commit,
     repeat the complete independent source/import review, and restart at R0;
   - for `runtime-review`, freeze a new immutable runtime/verifier/supervisor
     source commit, rebuild every source-bound S/G, replay, fixture, cost, and
     qualification artifact, prepare a new atomic runtime-candidate
     profile/companion with every affected identity/dependency/chain root, and
     restart R0 plus the full provider-free G2 chain. The old runtime candidate
     and evidence remain blocked and cannot be inherited.
3. **Environment, resource, or attempt failure.** Timeout, OOM, crash, RSS
   uncertainty, partial write, unavailable measurement, or transient
   supervisor failure permanently blocks the current review lifecycle. A
   later attempt may start only under a distinct primary/review identity and
   fresh process, with no acceptance inherited from the failed lifecycle and
   with the profile Section 1.2 compiler-lifecycle/reuse restriction
   rechecked. If that restriction does not allow source reuse, a new
   source-reviewed compiler commit is required. Only a demonstrated defect in
   the frozen resource policy returns to path 1.

All three paths restart at R0 and carry prior evidence only as append-only
failure history, never as acceptance evidence.

Runtime patches, lock overrides, fixture-specific exceptions, post-hoc
expected-code changes, and evidence deletion are prohibited.

## 10. Candidate promotion and lock migration

A passing review bundle does not itself promote v0.7.

Promotion requires a later, separately reviewed sequence:

1. freeze the passing review bundle and independent review decision;
2. prepare a new atomic core activation-candidate commit derived from the
   reviewed profile and companion;
3. in that future commit only, set the proposed activation evidence vector
   exactly to:

   ```text
   activation_ready=true
   artifact_bytes_compiled=true
   runner_implemented=false
   receipt_artifact_bytes_present=true
   ```

   and recompute every affected companion, document, dependency, and chain
   binding. `runner_implemented` remains false because the review
   materializers are not the active runtime;
4. keep the external active lock on v0.6 while the activation candidate is
   tested in isolation;
5. rerun R0-R8 with `phase_kind=promotion-review` against the complete
   activation-candidate identity and exact bytes from step 3. Changing any
   identity field, flag, status, or companion byte changes the phase/semantic
   bindings and invalidates the first-pass artifact bindings;
6. require independent approval of that second exact bundle and verify again
   that no task reducer, full-scale runner, or qualification verifier exists
   in the active external source;
7. prepare an external-lab **profile-lock migration** commit that atomically
   binds the exact core activation commit, profile/companion roots, effective
   profile-chain root, two review bundles, and review-tool source roots. It
   retains the current runtime source-tree binding and explicitly records
   `v07_runtime_implemented=false`; review-tool source is evidence, not active
   runtime source;
8. fast-forward to that migration commit only after the active external lab is
   clean and still matches the recorded v0.6 predecessor;
9. perform a fresh post-migration readback. At this point v0.7 methodology may
   be active but G2 remains blocked and no full-scale claim is allowed;
10. only after that readback may a separate isolated candidate branch
    implement the actual v0.7 runtime producer and a source-independent
    qualification verifier. Neither may import, copy, vendor, generate from,
    or reuse either disposable audit compiler;
11. freeze the complete runtime and verifier source in an immutable external
    candidate commit, rebuild and refreeze every source-bound S/G/replay,
    fixture, cost, and qualification input affected by that source identity,
    and obtain independent source/import review;
12. prepare a new atomic core runtime-candidate profile/companion commit with
    `phase_kind=runtime-review`, the proposed runtime status/vector in Section
    2, and every mechanically affected identity, dependency, and chain root
    recomputed. The existing profile-lock and active runtime-source binding
    remain unchanged while this candidate is reviewed;
13. using the separately reviewed runtime producer/verifier rather than the
    audit compilers, rerun the R0-R8 materialization-integrity contract against
    that exact runtime identity and then run the separately specified
    provider-free full-scale G2 qualification. Both evidence families must
    bind the immutable runtime source commit and remain blocked on any
    mismatch, timeout, crash, OOM, or missing record;
14. only after independent review of those exact artifacts may a later
    **implementation-source migration** atomically bind the core runtime
    candidate, external runtime/verifier source, rebuilt artifacts, and G2
    evidence. The active source stays unchanged until that migration passes
    fresh-process readback;
15. any runtime, verifier, profile, companion, or source-bound artifact change
    after steps 11-14 invalidates the affected evidence and requires the
    refreeze, source review, materialization-integrity review, G2
    qualification, and migration chain to restart. A source-only patch cannot
    inherit old acceptance evidence.

The core activation candidate may exist before migration without becoming
active; the unchanged external lock continues to make v0.6 authoritative.
This is the required resolution of the chicken-and-egg dependency.

The vector in step 3 is a proposed future acceptance requirement, not a change
made by this review plan. If v0.7 activation rules reject that vector, the
profile and companion must be atomically revised and rereviewed; runtime or
lock code cannot choose a different vector. This plan neither prepares that
activation commit nor changes any current false flag.

## 11. Rollback

Before the first profile-lock migration, rollback means:

- leave active v0.6 untouched;
- retain and mark the candidate bundle blocked or superseded;
- abandon promotion without deleting evidence;
- create a new candidate commit for any correction.

After a future migration, destructive history rewriting is prohibited. If
profile-lock migration readback fails, the forward rollback target is the
exact recorded v0.6 predecessor. If implementation-source migration readback
fails, the immediate forward rollback target is the exact preceding
profile-lock state: v0.7 methodology active, prior runtime-source binding
unchanged, and `v07_runtime_implemented=false`. A separate reviewed forward
rollback may then restore v0.6. In either case:

1. block v0.7 claims and executions;
2. retain the failed migration and evidence;
3. create a forward rollback commit restoring the exact phase-specific
   predecessor lock and source binding;
4. verify the restored lock and active source from a fresh process;
5. return the affected v0.7 phase to atomic profile/companion/source review.

No `git reset --hard`, force push, artifact deletion, or lock-file manual edit
is an accepted rollback mechanism.

## 12. Claim limits

Even `materialization-review-passed` would prove only that, for the exact
commits and bytes named by its evidence:

- two source-independent implementations uniquely materialized the 12 base
  constructors;
- both executed the 3 positive and 56 negative literal transactions;
- their source-independent semantic bytes, roots, and classifications agreed,
  and both source-bound cross-verification wrappers validated;
- the review remained provider-free, outcome-blind, network-free, and
  authority-free.

It would not prove:

- that v0.7 is active;
- G2 full-scale task-state qualification;
- G3 or any later gate;
- receptor-gated ligand field superiority over flooding, sparse
  communication, blackboard, retrieval routing, quorum, or learned graph
  pruning;
- H1-H6;
- LLM quality, provider behavior, or production readiness;
- runtime/controller correctness outside the exact review inventory;
- PheroOS ABI, TCK, Governance, Trace, or Conformance changes;
- publication authority or permission to run confirmatory LLM experiments.

Null, negative, mismatch, timeout, crash, OOM, and refusal evidence must be
retained. No API key is required or permitted for this materialization review.
