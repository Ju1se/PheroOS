# Receptor-Gated Ligand Field v0.7 Materialization V2 Closure Design

状态：`draft-closure-design-not-content-addressed`；V1 NO-GO 继续有效

检查点日期：2026-07-28

## 1. 决定

本文件记录 V1 executable audit 之后，对
`MaterializationContractV2`、golden oracle、phase identity、source
independence 和 R7 adversarial review 的候选关闭设计。它不是已经冻结的机器合同，
不是 profile amendment，不是 materialization receipt，也不解除任何 gate。

当前决定保持：

```text
materialization_review = "blocked"
G2 = "blocked"
G3 = "blocked"
G4_G8_authorized = false
provider_or_network_use = false
comparative_superiority_conclusion = null
hypothesis_conclusions = {}
```

API key 不能关闭这里的任何 deterministic blocker。现有
`blocked-underspecified-v1` public guard 必须保持，直到本文件第 12 节全部完成并从
新的 V2 identity 的 R0 重启。

本设计不修改 PheroOS ABI、schema、TCK、Evidence、Governance、Optimal Commit、
permission、fallback 或 output authority。所有 review actor 仍为：

```text
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
```

## 2. 三项新的方法学结论

### 2.1 A/B agreement 不是 exact oracle

V1 transport fake 已证明，两个程序可以对任意 payload、空 root-pair set 和任意
`E-FAKE` code 达成内部一致。因此 V2 必须同时具备：

1. source-independent A/B byte equality；
2. 每项预注册的 golden byte count 和 raw root；
3. all-and-only root-locator oracle；
4. independent source、process 和 adversarial evidence。

缺任一项仍是 NO-GO。

### 2.2 语义合同与 golden 结果不能是同一层

若把 71 个 golden payload roots 写入 payload contract，contract 同时成为规则和规则
结果，难以区分 specification closure 与 regression oracle。更严重的是，若 golden
root 被写回 profile 或 companion：

```text
profile bytes
  -> effective_profile_chain_root
  -> BaseMaterializationV2 bytes
  -> golden payload root
  -> profile bytes
```

会形成内容寻址循环。

所以 V2 必须分为：

- normative `MaterializationContractV2`，只定义规则和 descriptor；
- independent `MaterializationGoldenOracleV2`，只冻结规则应用后的 expected
  bytes/roots；
- external `MaterializationReviewInputIdentityV2`，最后单向绑定两者。

Profile/companion 可以绑定 normative contract root，但不得绑定 golden oracle root。

Because the current profile already binds the companion, the concrete freeze
order is `main contract -> companion -> profile`, not an interchangeable
profile/companion step.

### 2.3 Golden bytes 不能单独证明执行路径

Golden bytes 可以拒绝“两边同错”，但不能单独证明 positive implementation 实际从
before-view 执行 operation、closure 和 T4 transition；程序仍可能复制预期结果。
因此 positive contract 还必须冻结：

- every operation 的 before/after evidence；
- all-and-only closure field projection；
- declarative positive transition contract；
- source audit 中的 golden/oracle literal firewall。

这些项当前尚未展开为完整机器记录，所以 V2 仍未冻结。

## 3. 无环内容寻址图

唯一允许的依赖方向是：

In this diagram, `X -> Y` means “Y binds X”; it does not mean X's preimage
contains Y.

```text
normative leaf contracts
  ├─ base contract
  ├─ positive contract
  ├─ negative raw-byte contract
  ├─ root-expression contract
  ├─ GoldenOracle schema/validation contract
  ├─ IdentityV2 schema/validation contract
  ├─ SourceFreezeManifest and seal-evidence schema/validation contracts
  ├─ transport/evidence contracts
  ├─ 71-record descriptor registry
  └─ R7 case manifest
             |
             v
MaterializationContractV2
             |
             v
companion amendment followed by its binding profile amendment
             |
             v
final profile/companion bytes and semantic bindings
             |
             v
freeze bootstrap A0/B0, official A1/B1, supervisor/fresh-reader
and closure-reviewer A/B sources; run frozen pairwise audit
             |
             v
seal SourceFreezeManifestV2
             |
             v
seal downstream SourceFreezeSealEvidenceV2
             |
             v
bootstrap A0/B0 candidate payloads
             |
             v
independent closure review + MaterializationGoldenOracleV2
             |
             v
immutable core commit containing final profile/companion/contract,
source-freeze manifest/seal-evidence and oracle blobs
             |
             v
MaterializationReviewInputIdentityV2
             |
             v
official source re-audit and A1/B1 R0-R8
```

以下 downstream-to-upstream preimage references 全部禁止：

```text
leaf contract contains full contract root
payload contains full contract root
payload contains oracle root or expected value
contract contains identity root
contract contains final profile/companion raw root
profile or companion contains oracle root
oracle payload contains identity root
official A1/B1 reads bootstrap payload bytes
official A1/B1 reads golden oracle bytes
```

Bootstrap A0/B0 的 outputs 和 source 只能形成 oracle provenance；它们不得作为 official
A1/B1 acceptance evidence，也不得复制、import、生成或挂载到 official namespaces。
Official A1/B1 source 应在 golden oracle 生成或公开前冻结为 clean immutable commit；
否则“未挂载 oracle”仍不能排除实现者在 oracle 发布后硬编码其值。

There is also a non-cyclic semantic-drift risk: the main contract is frozen
before the final profile, yet it relies on hundreds of profile rules that it
does not restate. Before sealing, V2 must choose one exact solution:

1. bind a complete `profile_semantic_basis_root` plus a machine-checkable
   final-profile projection；or
2. bind the current profile raw root and an exact deterministic amendment
   transform whose output is the only accepted final profile bytes。

Merely storing `profile_id` would allow later profile semantics to drift while
the main contract root remains unchanged. The basis or transform may not bind
the final profile hash in a way that recreates a cycle.

## 4. Normative contract package

最终 main contract 建议位于：

```text
docs/process/receptor-ligand-field-v0.7-materialization-contract-v2.json
```

它按 `component_id` 的 UTF-8 bytes 排序绑定每个 normative component：

```text
component_id
path
byte_count
raw_root
semantic_root
```

```text
component_set_root =
  H("rglf-v07-materialization-contract-component-set-v2", components)
```

Main object 的 proposed exact keys：

```text
schema="pheroos-rglf-materialization-contract-v2"
contract_version="MaterializationContractV2"
profile_id="receptor-ligand-field-experiment-profile-v0.7"
canonicalization="receptor-ligand-field-experiment-profile-v0.7#12.1"
component_order="utf8-component-id-v1"
component_count
components
component_set_root
contract_root
```

```text
contract_root =
  H("rglf-v07-materialization-contract-v2",
    contract_without_contract_root)
```

Main contract 只能绑定 normative components；不能绑定 golden oracle、bootstrap
payload、identity、phase、source、attempt、observation 或 experiment outcome。

任何 leaf、descriptor、R7 case 或 label 仍含 placeholder、metavariable、free-form
preimage expression 或 unknown enum 时，main contract 不得生成 `contract_root`。

## 5. BaseMaterializationV2 candidate interface

### 5.1 Outer object

Proposed exact keys：

```text
schema="pheroos-rglf-base-materialization-v2"
payload_contract_root
stable_id
base_artifact_id
constructor_id
constructor_parameters
constructor_preimage_root
view_kind
view_id
normalized_view
normalized_view_root
path_inventory
construction_trace
base_materialization_root
```

`stable_id == base_artifact_id`。Companion 的 `view:*` selector 只进入 `view_id`。
`payload_contract_root` 只等于 base leaf root，不等于 main contract root。

```text
constructor_preimage_root =
  H("rglf-v07-base-constructor-preimage-v2", {
    "payload_contract_root": payload_contract_root,
    "stable_id": stable_id,
    "base_artifact_id": base_artifact_id,
    "constructor_id": constructor_id,
    "constructor_parameters": constructor_parameters,
    "view_kind": view_kind,
    "view_id": view_id
  })

normalized_view_root =
  H("rglf-v07-base-normalized-view-v2", {
    "base_artifact_id": base_artifact_id,
    "constructor_preimage_root": constructor_preimage_root,
    "view_kind": view_kind,
    "view_id": view_id,
    "normalized_view": normalized_view
  })

base_materialization_root =
  H("rglf-v07-base-materialization-v2",
    base_object_without_base_materialization_root)
```

Payload bytes 唯一为：

```text
UTF8(C(full_base_object)) || 0x0A
```

Payload raw root/count 只进入 golden oracle，不写回 payload。

### 5.2 Six source-independent view variants

The proposed closed variants are:

| variant | schema | required top-level content |
| --- | --- | --- |
| environment | `pheroos-rglf-normalized-environment-view-v2` | profile bindings, config, receiver/event/job/step/directive/failure/terminal/unrevealed views, source-neutral manifest, raw bytes |
| suite | `pheroos-rglf-suite-view-v2` | producer replica and exact 980 intent bindings |
| replica pair | `pheroos-rglf-replica-pair-view-v2` | replicas A/B and exact T1-T7 environment projections |
| labels | `pheroos-rglf-label-fixture-view-v2` | three label arrays and sealed-outcome-field flag |
| source | `pheroos-rglf-source-inventory-view-v2` | exact file map and Unicode-sorted path order |
| process | `pheroos-rglf-process-transcript-view-v2` | exact 13 companion process parameters |

All inapplicable containers must be exact empty arrays/objects, never absent.
Every nested schema and map-to-view projection must be expanded in the machine
leaf; prose or fixture-ID branching is insufficient.

This table is a variant inventory, not a closed field/type table. The nested
keys, scalar types, projection sources, map ordering and constructor-specific
literal trace steps are still an open P1 and prohibit main-contract sealing.

### 5.3 Source-neutral environment projection

`ArtifactManifestV07` and its record genesis are source-bound because they contain
`producer_source_root`. Removing that field while retaining downstream chain roots
would create invalid preimages. One candidate review-only projection is:

```text
EnvironmentCoreV2 exact keys:
  schema="pheroos-rglf-base-environment-core-v2"
  base_artifact_id
  view_id
  task_id
  profile_bindings
  config
  receivers
  events
  jobs
  steps
  directives
  failure_schedule
  terminal_receipts
  unrevealed_edges
```

```text
environment_core_root =
  H("rglf-v07-base-environment-core-v2", EnvironmentCoreV2)

raw_ndjson_bytes_decoded =
  UTF8(C(EnvironmentCoreV2)) || 0x0A
```

Under that candidate, normalized `/artifact_manifest` is a distinct source-neutral
`pheroos-rglf-base-artifact-manifest-view-v2` over those bytes. It is not
`ArtifactManifestV07`, does not contain a producer source binding, and cannot
substitute for the later G2 runtime chained NDJSON.

The Base payload excludes:

```text
producer_source_commit
producer_source_root
source-bound record genesis and record chain
final_record_root derived from that genesis
ArtifactManifestV07
review source/attempt/observation/wrapper roots
```

Actual producer/verifier source identity remains in source-bound completion and
verification evidence.

This single-line projection is not sufficient to close the original review:
it removes `ChainedRecordV07`, genesis, record-chain, final-record and
`ArtifactManifestV07` behavior from the tested base. Before contract sealing,
V2 must choose and fully specify one of:

1. a dual layer in which source-neutral semantic bytes are compared across A/B
   while each role's real source-bound chained artifact and manifest are
   independently reconstructed and cross-verified；or
2. a complete source-neutral re-chained stream that retains every record,
   payload and chain invariant, plus separate verification of each role's
   actual source-bound wrapper。

If the one-line `EnvironmentCoreV2` is retained only as a narrow mutation
fixture, actual chained-artifact materialization remains a separate blocker
and the review cannot claim to have closed the original base-artifact contract.

### 5.4 raw_ndjson_bytes

The JSON value at `/raw_ndjson_bytes` must be canonical RFC 4648 standard
base64:

- standard alphabet only；
- length multiple of four；
- at most two terminal `=`；
- no whitespace；
- strict decode succeeds；
- strict re-encode is byte-identical。

Byte operations decode first, apply the declared offset to decoded octets,
verify `value_raw_sha256` over decoded operation bytes, then re-encode. The
frame judge receives mutated decoded octets, never the base64 text or a
re-serialized outer object.

### 5.5 Path inventory and construction trace

Path inventory proposed exact keys：

```text
schema="pheroos-rglf-base-path-inventory-v2"
base_artifact_id
view_id
normalized_view_root
entry_count
entries
inventory_root
```

Entry exact keys are `path,node_kind,byte_count`. `node_kind` is:

```text
object|array|null|boolean|integer|string|bytes-base64
```

RFC 6901 document root is the empty string `""`; `/` is not repurposed as a
root sentinel. The root entry and every descendant appear exactly once, sorted
by UTF-8 path bytes. `byte_count=null` except for contract-declared
`bytes-base64` nodes, where it is decoded-octet count.

The current companion violates that rule in exactly two known records:

```text
N-T1-SILENT-CONFLICT operations[0].path              = "/"
N-T1-SILENT-CONFLICT operations[0].precondition.path = "/"
N-T4-DAG-CYCLE      operations[0].path              = "/"
N-T4-DAG-CYCLE      operations[0].precondition.path = "/"
```

Both `apply-transform` operations and their preconditions intend the whole normalized view, whose
RFC 6901 pointer is `""`. V2 closure therefore requires an atomic
profile/companion correction of all four literals to `path=""` and recomputation of the two
operation roots, two recipe roots, negative set, semantic manifest, companion
raw root and all downstream identities. Accepting both `""` and `/` as aliases
is prohibited.

Independent read-only Python/Node recomputations agree that this four-literal
counterfactual changes the companion from `62097` bytes and
`sha256:322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360`
to `62093` bytes and
`sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795`.
The exact intermediate roots are retained in the audit finding. These values
are impact evidence only; no companion byte has been changed.

Construction trace proposed exact keys：

```text
schema="pheroos-rglf-base-construction-trace-v2"
base_artifact_id
constructor_id
constructor_preimage_root
steps
trace_root
```

Each step has exact `ordinal,operation_id,inputs,output_name,output_root`;
each input has `name,root`. The leaf must enumerate the literal step tables
for environment, suite, replica pair, labels, source and process. Runtime
logs, source roots, clock, host and resource observations are excluded.

The frozen leaf must also add exact omit-self formulas and labels:

```text
inventory_root =
  H("rglf-v07-base-path-inventory-v2",
    path_inventory_without_inventory_root)

trace_root =
  H("rglf-v07-base-construction-trace-v2",
    construction_trace_without_trace_root)
```

## 6. PositiveTransactionProductV2 candidate interface

Proposed outer fields must bind:

```text
schema="pheroos-rglf-positive-transaction-product-v2"
payload_contract_root
stable_id
fixture_id
base_artifact_id
selector
reseal_policy
judge
validation_stage
expected_code
fixture_semantic_manifest_root
positive_fixture_set_root
base_materialization_root
transaction_before_view_root
transaction_before_view_raw_root
operations
operation_transaction_root
operation_evidence
operation_execution_root
transaction_after_view_encoding
transaction_after_view_byte_count
transaction_after_view_raw_root
transaction_after_view_bytes_b64
transaction_after_view_root
transaction_committed
closure
transaction_trace
verified
positive_transaction_product_root
```

`stable_id == fixture_id`、`expected_code=null`、
`transaction_committed=true`。After-view encoding is
`canonical-json-line-base64-v1` and strictly decodes to
`C(post_operation_normalized_view)||LF`.

Every operation evidence record distinguishes absent from present-null and
binds:

```text
fixture_id
operation_index
companion_operation_pointer
operation
precondition_satisfied
target_present_before
target_value_before
target_present_after
target_value_after
evidence_root
```

Positive closure must preserve:

```text
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
```

It binds expected and observed transition receipt bodies, both receipt-set
roots, fixture commitment, exact receipt equality, closure projection root and
positive transition contract root. `PositiveFixtureReceiptV07`, its artifact,
source-bound manifest and review wrappers remain outside the source-independent
product.

Three `PositiveClosureProjectionV2` records are still required. Each must
all-and-only map every non-derived `fixture_input` leaf using:

```text
destination_pointer
source_document =
  "transaction-before-view" |
  "transaction-after-view" |
  "companion"
source_pointer
copy_mode="canonical-value-copy-v1"
```

The positive transition component must separately freeze the branch transition
table. If a value such as `job_after.deadline_step` cannot be assigned one exact
source pointer or exact contract literal, the profile/companion remains
under-specified and must be amended before any golden is generated.

The contract must also decide whether `transaction_after_view_bytes_b64`
contains the raw post-operation view with opaque carried-through internal
roots, or a semantically resealed view. Current prose does not uniquely choose
between them. Golden bytes cannot repair this missing semantic rule.

## 7. Negative payload contract

All 56 records use:

```text
payload_schema=null
payload_encoding="raw-bytes-v1"
```

The payload is the exact octet sequence after ordered operations and declared
reseal, passed unchanged to the judge. Even when valid JSON, it may not be
parsed, NFC-normalized, repaired, canonicalized, LF-normalized or re-emitted.
Only the oracle instance stores the concrete `expected_payload_byte_count` and
`expected_payload_raw_root`; its normative validation rule is
`expected_payload_raw_root == RAW(exact_judge_input_octets)`.

The phrase `exact_judge_input_octets` is not yet closed. The normative leaf
must contain 56 literal `NegativeJudgeInputProjectionV2` records selecting,
for each fixture, exactly one source and transformation path, such as structured
view canonical line, strict-decoded `/raw_ndjson_bytes`, source-file UTF-8,
process segment, or declared resealed-view bytes. The table must bind the
operation result, reseal output and judge input without fixture-ID inference.
Until that table exists, the negative contract is P1-blocked.

Every negative record has exactly zero `payload#` descriptors. It may have
`companion#` and `derived#` descriptors. Non-null operation
`value_raw_sha256` is recomputed over the declared UTF-8 or strict-base64
bytes. An ordinary mutation value that happens to match `sha256:<hex>` is not
automatically a root claim.

## 8. Descriptor registry and golden oracle

### 8.1 Normative descriptor registry

The eventual frozen contract-level registry must contain exactly 71 literal
records, ordered by:

```text
artifact rank: base < positive < negative
then UTF8(stable_id)
```

Its records contain no expected payload bytes, counts, roots or expected root
values. Proposed record keys:

```text
schema
ordinal
artifact_kind
stable_id
companion_record_pointer
payload_schema
payload_encoding
payload_contract_root
expected_code
descriptor_count
descriptors
descriptor_set_root
record_root
```

Proposed top-level keys:

```text
schema="pheroos-rglf-materialization-root-locator-registry-v2"
contract_version="MaterializationContractV2"
profile_id
canonicalization
record_order="artifact-rank-then-utf8-stable-id-v1"
artifact_rank=["base","positive","negative"]
record_count=71
descriptor_count
records
registry_root
```

```text
descriptor_root =
  H("rglf-v07-root-locator-descriptor-v2",
    descriptor_without_descriptor_root)

descriptor_set_root =
  H("rglf-v07-root-locator-descriptor-set-v2", descriptors)

record_root =
  H("rglf-v07-root-locator-record-v2",
    record_without_record_root)

registry_root =
  H("rglf-v07-materialization-root-locator-registry-v2",
    registry_without_registry_root)
```

Descriptor proposed exact keys:

```text
schema="pheroos-rglf-root-locator-descriptor-v2"
root_locator
root_authority
root_value_source
root_value_pointer
root_algorithm
root_label
preimage_expression
descriptor_root
```

Closed locators:

```text
whole companion: companion#
companion member: companion#/...
whole payload: payload#
payload member: payload#/...
derived value: derived#/...
```

`#/` is never a document-root alias. Empty-key members are rejected by the
closed source schemas.

The closed expression AST is limited to:

```text
literal
pointer
record-pointer
omit
object
array
utf8-encode
base64-decode-strict
parse-canonical-json-line
raw-payload-bytes
```

There is no search, suffix inference, `_root` heuristic, sort chosen at runtime,
task reducer, judge, reseal or fixture-special-case opcode. Arrays and maps use
the exact order and pointers declared by the contract.

The opcode names above are still only an inventory. Before sealing, each must
be a closed tagged union with exact fields, input/output types, depth and
resource bounds, deterministic error code and no implicit coercion. The
root-authority/source/algorithm enums and exact expected-root-pair
construction, UTF-8 sorting, duplicate rejection and all-and-only comparison
also remain open P1s.

The final registry must expand every applicable root occurrence and every
record literally. A template is acceptable only during authoring; the frozen
artifact contains its complete expansion.

### 8.2 Independent golden oracle

Before main-contract sealing, a value-free `GoldenOracleContractV2` leaf must
freeze the oracle top-level, record, kind-specific, input-binding, bootstrap
provenance and closure-review schemas, labels, ordering and root formulas.
The later `MaterializationGoldenOracleV2` is only an instance of that leaf.

Proposed top-level instance keys:

```text
schema="pheroos-rglf-materialization-golden-oracle-v2"
oracle_version="MaterializationGoldenOracleV2"
profile_id
canonicalization
input_binding
input_binding_root
record_order="artifact-rank-then-utf8-stable-id-v1"
artifact_rank=["base","positive","negative"]
record_count=71
records
bootstrap_provenance
bootstrap_provenance_root
closure_review_count=2
closure_review_roots
closure_review_set_root
oracle_set_root
```

`input_binding` must include the exact final profile path/count/raw root and
semantic-basis root；companion path/count/raw root plus the four semantic set
roots；main-contract path/count/raw/semantic root；and descriptor-registry root.
It must also bind the pre-golden `SourceFreezeManifestV2` and downstream
`SourceFreezeSealEvidenceV2` paths/counts/raw/semantic roots. It cannot bind
Identity or the final Git commit.

`bootstrap_provenance` must bind distinct A0/B0 source roots, completion roots,
payload-inventory roots, agreement receipt and the same
`source_freeze_manifest_root` and `source_freeze_seal_evidence_root`. Each of
the two
closure-review roots must bind its own pre-candidate frozen reviewer source
root and a separately sourced all-and-only review. The two reviewers may not
share semantic source or helper with each other, the supervisor, fresh reader
or any materializer. The four bootstrap/official implementations may not share
semantic blobs or helpers.

Each of 71 record instances has proposed keys:

```text
schema
ordinal
artifact_kind
stable_id
descriptor_record_root
expected_payload_byte_count
expected_payload_raw_root
expected_root_pair_count
expected_root_pairs
expected_root_pair_set_root
source_independent_receipt_bindings
kind_specific_expected_roots
golden_record_root
```

Base records additionally freeze constructor, environment-core, decoded raw
bytes, source-neutral manifest, normalized-view, path-inventory,
construction-trace and base-materialization roots. Positive records additionally
freeze before/after, operation, closure, transition, trace, expected/observed
transition-receipt-body and receipt-set roots. They must not freeze concrete
`PositiveFixtureReceiptV07`, positive receipt-artifact, source-bound manifest or
wrapper roots；the oracle contract stores only their formula/non-equality
matrix. Source-independent `NegativeFixtureReceiptV07` bodies and
`NegativeFixtureReceiptArtifactV07` may have concrete golden values.
`FixtureReceiptArtifactManifestV07` is source-bound for both positive and
negative artifacts and may only appear through its formula/non-equality
matrix, never as one concrete golden root shared across roles.

Proposed root labels are:

```text
rglf-v07-golden-oracle-input-binding-v2
rglf-v07-golden-root-pair-set-v2
rglf-v07-golden-oracle-record-v2
rglf-v07-golden-bootstrap-provenance-v2
rglf-v07-golden-closure-review-set-v2
rglf-v07-materialization-golden-oracle-v2
```

The roots use scoped preimages, not a blanket omit-self rule:

```text
input_binding_root =
  H("rglf-v07-golden-oracle-input-binding-v2", input_binding)

expected_root_pair_set_root =
  H("rglf-v07-golden-root-pair-set-v2", expected_root_pairs)

golden_record_root =
  H("rglf-v07-golden-oracle-record-v2",
    golden_record_without_golden_record_root)

bootstrap_provenance_root =
  H("rglf-v07-golden-bootstrap-provenance-v2", bootstrap_provenance)

closure_review_set_root =
  H("rglf-v07-golden-closure-review-set-v2", {
    "closure_review_count": closure_review_count,
    "closure_review_roots": closure_review_roots
  })

oracle_set_root =
  H("rglf-v07-materialization-golden-oracle-v2", {
    "schema": schema,
    "oracle_version": oracle_version,
    "profile_id": profile_id,
    "canonicalization": canonicalization,
    "input_binding_root": input_binding_root,
    "record_order": record_order,
    "artifact_rank": artifact_rank,
    "record_count": record_count,
    "ordered_golden_record_roots": ordered golden_record_root values,
    "bootstrap_provenance_root": bootstrap_provenance_root,
    "closure_review_set_root": closure_review_set_root
  })
```

The oracle validator must require
`closure_review_count == len(closure_review_roots) == 2`. It must also perform
these all-and-only joins:

```text
oracle profile_id/canonicalization
  == parsed profile, companion, main contract and descriptor registry values
oracle record_order/artifact_rank/record_count
  == descriptor registry record_order/artifact_rank/record_count
for every ordinal 0..70:
  oracle record ordinal/artifact_kind/stable_id/descriptor_record_root
    == the same registry record ordinal/artifact_kind/stable_id/record_root
no missing, additional, duplicate or reordered oracle/registry record
oracle input_binding.source_freeze_manifest_root
  == bootstrap_provenance.source_freeze_manifest_root
oracle input_binding.source_freeze_seal_evidence_root
  == bootstrap_provenance.source_freeze_seal_evidence_root
bootstrap_provenance A0/B0 source commit/tree/inventory/semantic roots
  == SourceFreezeManifest bootstrap-a0/bootstrap-b0 actor records
each closure-review root's reviewer source commit/tree/inventory/semantic roots
  == its SourceFreezeManifest closure-reviewer-a/b actor record
SealEvidence supervisor checkpoint and fresh-read observation source roots
  == SourceFreezeManifest supervisor/fresh-reader actor records
```

No sibling subroot preimage contains `oracle_set_root` or a downstream record
root. The final leaf still has to expand the exact key/type formulas for
`kind_specific_expected_roots`, receipt bindings, provenance and closure
reviews；until then main-contract sealing remains blocked.

The oracle stores no experiment outcome and grants no authority. It is a
deterministic regression oracle for exact materialization only.

The oracle must not contain its own raw root, final Git commit, identity root,
phase identity root, semantic-body root or wrapper root. Those downstream
values would create a self-hash or `identity -> oracle -> identity` cycle.

Candidate golden values require two source-independent bootstrap implementations
and two independent closure reviews. Their payloads and provenance are retained,
but cannot be inherited by the official R0-R8 pass.

### 8.3 Oracle firewall

Full Identity V2 is supervisor/fresh-reader input. Official A1/B1 compile
children receive a contract-defined `MaterializerInputProjectionV2` containing
`phase_identity_root` plus the allowed profile/companion/main/descriptor
bindings, but no oracle path or value. A compile mount contains only those
exact input blobs, own source and own empty output. It does not contain:

```text
golden oracle bytes
golden payload bytes
bootstrap source or artifacts
the other materializer output
reference implementation output
```

The projection has separate closed variants:

```text
compile       -> own allowed inputs and own empty output only
cross-verify  -> descriptor inputs plus the other side's already sealed product
```

Neither variant contains GoldenOracle or bootstrap bytes. A compile actor
cannot see the other side's output；a verifier cannot see it before both
completion roots are sealed.

Compiler completion and semantic bodies bind the normative
`descriptor_record_root`, not `golden_record_root`. Only supervisor-owned
oracle attestations and fresh reread bind the golden record. A/B
cross-verification binds descriptors and the other side's sealed product, not
GoldenOracle. This prevents either verifier from needing oracle access.

Source audit rejects embedded expected payload roots, golden record roots,
golden payload blobs or bootstrap paths. This does not prove unobservable human
independence; it proves only that the frozen source and process evidence did
not expose those channels.

The child sandbox is a blob-only mount, not a Git worktree. It contains no
`.git`, object database, pack, alternates, archive, Git executable or Git
environment. The access policy also denies oracle-path `read`, `stat`,
directory listing, hardlink, mmap, inherited descriptors/IPC and shared cache.
Supervisor mounts the oracle only after both sides have sealed their
source-independent products. R7 must exercise every bypass class explicitly.

## 9. MaterializationReviewInputIdentityV2

Before main-contract sealing, a value-free
`MaterializationReviewInputIdentityContractV2` leaf must freeze the 27-key
schema, field types, phase/status enums, flag vectors, path rules, equality
predicates, nullability, root label and refusal mapping. The identity below is
only a later instance of that main-bound validation contract；its acceptance
semantics may not be selected after GoldenOracle exists.

The external phase identity has 27 exact keys and extends V1 with both
bindings:

```text
schema="pheroos-rglf-materialization-review-input-identity-v2"
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
materialization_contract_path
materialization_contract_byte_count
materialization_contract_raw_root
materialization_contract_semantic_root
golden_oracle_path
golden_oracle_byte_count
golden_oracle_raw_root
golden_oracle_semantic_root
status
activation_ready
artifact_bytes_compiled
runner_implemented
receipt_artifact_bytes_present
identity_root
```

```text
identity_root =
  H("rglf-v07-materialization-input-identity-v2",
    identity_without_identity_root)
```

```text
materialization_contract_semantic_root == contract.contract_root
golden_oracle_semantic_root == oracle.oracle_set_root
```

The validation leaf must also require one all-field binding join, not merely
two independent hash checks:

```text
identity.profile path/count/raw plus parsed profile semantic-basis
  == oracle.input_binding.profile path/count/raw/semantic-basis
identity.companion path/count/raw and four fixture/semantic set roots
  == oracle.input_binding.companion path/count/raw and four set roots
identity.materialization_contract path/count/raw/semantic
  == oracle.input_binding.main_contract path/count/raw/semantic
oracle.input_binding.descriptor_registry_root
  == the descriptor-registry component bound by contract.contract_root
oracle.input_binding SourceFreezeManifest and seal-evidence path/count/raw/semantic
  == the exact parsed pre-golden source-freeze blobs and semantic roots
identity golden path/count/raw/semantic
  == the exact parsed oracle blob and oracle.oracle_set_root
identity core_commit tree entries at the four top-level paths
  == the declared regular blobs, modes, byte counts and raw roots
every parsed contract.components[] entry
  == exactly one core_commit regular blob at its path/mode/count/raw/semantic
oracle-bound SourceFreezeManifest and seal-evidence path/count/raw/semantic
  == exact core_commit regular blobs with the same bytes and semantic roots
the all-and-only expected component and source-freeze paths
  == the validated bound component/source-freeze subset of the commit tree
```

Any mix-and-match across profile, companion, main contract, descriptor
registry, oracle or commit is a refusal even when each object is internally
hash-valid.

All paths are NFC repo-relative regular Git blob paths. No absolute path,
symlink, implicit default, placeholder or working-tree-only file is allowed.
The identity is created outside the bound core commit after that commit exists;
it is not a self-referential Git blob.

`status` and the four booleans are immutable pre-run candidate declarations,
not review outcomes. They must equal the exact values in the bound companion
and the contract's closed `phase_kind -> status/flag-vector` matrix before R0.
R0-R8 may never edit or “promote” this identity；pass, refusal and review
decisions live only in downstream decision/receipt objects. The exact V2 phase
matrix is not yet frozen and is therefore an explicit P1；until it is closed,
no V2 identity can be instantiated.

V1 identity, semantic body, completion, verification and wrapper objects cannot
be grandfathered.

## 10. Supervisor, process proof and source independence

Main contract must contain value-free V2 transport/evidence leaves for:

```text
MaterializationSemanticBodyV2
CompilerCompletionRecordV2 and completion manifest
CrossVerificationRecordV2 and verification manifest
MaterializerEvidenceWrapperV2 and inventories
SupervisorGoldenOracleAttestationV2 and 71-record inventory
ProcessCheckpointV2 and process-proof set
source inventory and source-audit decision
refusal record and refusal manifest
fresh-reread decision and bundle manifest
MaterializerInputProjectionV2
R7ExecutionScheduleV2
SourceFreezeManifestV2
SourceFreezeSealEvidenceV2
```

Each requires exact schema, closed keys/types/enums, root label, omit rule,
order, nullability and file layout. V1 evidence objects are prohibited, so
prose capabilities cannot substitute for these V2 leaves. They remain open P1.

The value-free `SourceFreezeManifestContractV2` leaf must require one
pre-golden instance with this closed conceptual content:

```text
schema="pheroos-rglf-source-freeze-manifest-v2"
source_audit_procedure_root
actor_count=8
actor_order=[
  "bootstrap-a0", "bootstrap-b0", "official-a1", "official-b1",
  "supervisor", "fresh-reader", "closure-reviewer-a", "closure-reviewer-b"
]
actors
pair_count=28
pairwise_audit_roots
pairwise_audit_set_root
source_freeze_manifest_root
```

Every actor record binds its role, immutable source commit/tree, exact source
inventory root and semantic-source root. Every unordered actor pair appears
exactly once and binds the already frozen audit procedure plus its
collision/import/shared-helper decision.

Seal evidence is a separate downstream object so the manifest cannot contain
the root of evidence that itself binds the manifest:

```text
schema="pheroos-rglf-source-freeze-seal-evidence-v2"
source_freeze_manifest_path
source_freeze_manifest_byte_count
source_freeze_manifest_raw_root
source_freeze_manifest_root
supervisor_prelaunch_checkpoint_root
fresh_read_observation_root
source_freeze_seal_evidence_root
```

The manifest is atomically sealed and fresh-read before bootstrap launch；the
seal evidence binds that exact root, and the later supervisor launch transcript
binds the seal-evidence root as a pre-launch input. GoldenOracle
input/provenance binds both roots, the final core commit retains the exact two
blobs, and official checkpoints/re-audit join their observed source commits and
roots back to their actor records. A later source rewrite cannot inherit the
manifest. Exact actor/pair/seal schemas and root formulas remain part of open
P1 #16.

The oracle-attestation leaf must keep two decisions separate:

```text
SC = A/B source-independent products are equal
SO = the equal product matches the independent GoldenOracle record
```

Each of 71 supervisor-owned attestation records binds artifact kind, stable ID,
ordinal, descriptor record, golden record, A/B completion records, observed
count/raw root/root-pair-set root, `source_independent_equal`, `golden_match`,
`verified` and its own root. An A/B verifier cannot set `golden_match`.

Supervisor may implement only:

```text
strict canonical JSON and duplicate-key rejection
RAW and H with frozen labels
RFC 6901
closed expression AST evaluation
strict UTF-8/base64
key projection and exclusion
count/order/unique/all-and-only checks
file inventory and no-symlink checks
exact equality/non-equality matrices
atomic content-addressed sealing and fresh reread
```

It may not implement a base constructor, task reducer, transaction, reseal,
positive closure, validation stage, judge or expected-code inference.

Every clean acceptance actor/action must have two process checkpoints:

```text
post-import-pre-input
pre-terminal
```

Expected timeout, OOM, crash and pre-rename failure cases may retain only the
first checkpoint plus a supervisor-owned terminal classification and partial
output inventory；they can never satisfy acceptance. The R7 case descriptor
must declare this nullability and expected launch boundary.

Each checkpoint binds candidate commit, source root, executable/interpreter
bytes, cwd, argv, minimal environment, exact `sys.path`, loaded modules,
access policy and zero-authority vector. Actor modules must resolve to their
Git inventory; other modules are only bound stdlib, builtin or frozen modules.
Site packages, namespace packages, zip import, bytecode-only escape and unknown
origins are refusals.

For one actor/action, the two checkpoint `loaded_modules` arrays, sorted by the
contract's module order, must be byte-identical；there is no allowed delta,
superset rule or lazy-import exception. A/B actor-owned Git modules and semantic
source inventories remain disjoint；bound stdlib modules may overlap. The first
checkpoint precedes input
reads; the second precedes completion/decision atomic rename. Process proof is
combined with OS-level network denial, socket probe, zero-outcome mount and
credential-free environment evidence; child self-report alone is insufficient.

Near-copy review must be predeclared and waiver-free. At minimum it compares
exact blobs, normalized AST subtrees, contiguous normalized tokens and token
shingles across A/B. A passing audit means only “no collision was detected
under the frozen procedure”, not proof of unknowable historical independence.

The frozen source-audit leaf must replace “at minimum” with exact AST
normalization, tokenization, shingle width, thresholds, decision root and
zero-waiver rule. The same exact collision/import/helper audit applies
pairwise across bootstrap A0/B0 and official A1/B1, including cross-lifecycle
pairs. Supervisor, fresh reader and both closure reviewers also require
distinct source roots. No pair among those four may share semantic
source/helper, and none may share semantic source/helper with any materializer；
different namespace labels alone are not independence evidence. Bound standard
library and canonical primitive specifications may overlap, but no shared
project helper implementation is allowed. All eight source roots and the
pairwise audit procedure must be frozen before any bootstrap candidate payload
or golden value is generated.

## 11. R7 is not yet freezeable

A first candidate expansion produced 13 families and 140 cases covering input
binding, oracle, base, recipe, duplicate operations, classification,
root tampering, A/B comparison, source, process, predecessor state, access and
fresh reread.

That count cannot be frozen after the contract/oracle split. The manifest must
add at least:

- oracle byte flip, truncation, append and duplicate-key cases；
- oracle raw/semantic-root mismatch；
- oracle/profile/contract/registry profile-ID or canonicalization mismatch；
- oracle/registry record-order, artifact-rank or record-count mismatch；
- closure-review count/array mismatch；
- identity oracle path/count/root mismatch；
- every profile/companion/main/descriptor/oracle Identity-to-input-binding
  cross-equality mismatch；
- phase/status/flag-vector mismatch or attempted post-R0 identity mutation；
- missing/duplicate/additional/reordered golden records；
- ordinal/kind/stable-ID/descriptor-record-to-golden-record mismatch；
- missing or mismatched main-component commit-tree blob；
- missing/additional/duplicate/reordered expected root pairs；
- source-freeze manifest/seal-evidence byte/root mismatch, missing actor/pair,
  frozen-actor/actual-user root mismatch, broken temporal order or post-golden
  source rewrite；
- illegal official materializer oracle mount/read；
- embedded golden literal or bootstrap artifact access。

Therefore `case_count=140` is rejected as premature. The exact count must be
recomputed only after the split schemas and actor expectations are expanded.

A second mechanical expansion of the split architecture yielded a candidate
lower bound of 15 families and 182 cases by adding GoldenOracle binding,
golden-record, supervisor-attestation, access and reread cases. It is not yet
frozen because it still needs explicit cases for embedded golden literals,
bootstrap-path/cache leakage, directory `stat/list`, inherited descriptors,
hardlinks and the semantic-basis binding above. `182` therefore cannot yet be
written as the manifest's final `case_count`.
Every frozen case must contain:

```text
case_id
family_id
tamper_stage
target_locator
mutation
expectations
evidence_profile_id
case_root
```

Every applicable actor receives an explicit expectation row with boundary,
refusal code and launch expectation. Family-level receipts cannot replace
per-case/per-actor retained evidence. Wrong code, unclassified exception,
missing partial-output inventory or failed fresh reread blocks all R7.

Because the R7 manifest is a normative main-contract component, its final
literal case set, count, actors and evidence profiles must be expanded and
independently reviewed before main-contract sealing. After the oracle exists,
only identity-specific schedules and tampered instances may be generated；the
case manifest itself cannot change.

## 12. Required closure sequence

No step may be skipped or inherited from V1:

1. Expand all normative leaf components, including every projection,
   transition, root descriptor, oracle schema, transport/evidence schema,
   semantic-basis/amendment transform, label, field set, exclusion and the
   final literal R7 manifest.
2. Run two independent contract reviews for canonical bytes, duplicate keys,
   exact fields, root DAG and all-and-only coverage.
3. Seal the normative main contract without any golden or identity value.
4. Atomically amend companion and then its binding profile to adopt the main
   contract, new labels and exact V2 schemas；do not embed an oracle root.
5. Recompute final profile/companion raw and semantic bindings.
6. Implement and freeze clean bootstrap A0/B0, official A1/B1,
   supervisor/fresh-reader and closure-reviewer A/B source commits before any
   bootstrap candidate payload or golden value is generated or published；
   every required pairwise semantic source/helper audit passes under the
   already frozen procedure. Atomically seal and fresh-read the all-eight
   `SourceFreezeManifestV2`, then seal its acyclic
   `SourceFreezeSealEvidenceV2`, before bootstrap launch.
7. Run only disposable bootstrap A0/B0 to generate all 71
   candidate payloads plus positive transition evidence.
8. Require bootstrap byte agreement and two independent closure reviews; retain any
   mismatch as negative engineering evidence.
9. Seal `MaterializationGoldenOracleV2` only when all 71 concrete counts,
   roots, root pairs and applicable receipt roots are present.
10. Materialize and freeze one clean immutable core commit containing the
    exact profile, companion, every main-contract component, source-freeze
    manifest/seal-evidence and oracle blobs；audit every Git path, mode, blob
    ID, byte count, raw root and applicable semantic root from the commit tree.
11. Create external `MaterializationReviewInputIdentityV2` binding the exact
    core commit, profile, companion, normative contract and golden oracle.
12. Deterministically instantiate `R7ExecutionScheduleV2` from the frozen
    manifest and new `identity_root`; bind every case/actor all-and-only and
    prove that no case descriptor changed.
13. Re-audit the already frozen official A1/B1, supervisor/fresh-reader and
    closure-reviewer A/B source against the final identity, including
    golden-literal, all-actor source-manifest joins and mount/object-store
    firewalls.
14. Run R0-R8 from zero and fresh-reread the sealed bundle with neither
    materializer importable.

Any schema, profile, companion, contract, oracle, source or R7 change restarts
the affected chain at or before R0. Bootstrap results never become acceptance
results by renaming.

## 13. Current open P1 blockers

At this checkpoint, at least the following remain open:

1. exact machine-readable Base projection tables and schema-typed root
   occurrence expansion；
2. dual-layer or fully re-chained actual-artifact preservation；
3. three complete positive closure projection records；
4. exact positive transition and after-view reseal contract；
5. 56-record negative judge-input projection table；
6. RFC 6901 correction for the four current whole-document operation/precondition pointers；
7. 71 descriptor records, expanded locators and closed expression AST；
8. normative GoldenOracle input/provenance/record contract；
9. 71 golden payload counts/raw roots/root-pair values；
10. source-independent receipt values and source-bound receipt formula matrix；
11. exact V2 semantic/completion/verification/wrapper/process/attestation/
    R7-schedule/bundle schemas；
12. exact value-free IdentityV2 validation/schema leaf, including pre-run
    phase/status/flag matrix and full Oracle-input-binding equality join；
13. revised R7 case count and complete actor expectation matrix, frozen before main；
14. concrete main component path/count/raw/semantic roots；
15. profile semantic-basis or exact amendment-transform binding；
16. exact access-policy schema/evidence, Git-object-store denial,
    `SourceFreezeManifestV2`/`SourceFreezeSealEvidenceV2` root formulas,
    acyclic pre-golden temporal evidence and all-eight-source independence
    policy；
17. concrete oracle path/count/raw/semantic roots；
18. V2 implementation, process proofs and fresh R0-R8 evidence。

Consequently no V2 object may currently use a status such as `frozen`,
`complete`, `passed` or `activation-ready`.

## 14. Claim boundary

Even a future V2 R0-R8 pass would prove only exact deterministic
materialization for the bound bytes, sources and review process. It would not
prove:

- v0.7 activation or G2/G3 completion；
- provider or LLM behavior；
- H1-H6；
- receptor-gated ligand field superiority over sparse communication,
  blackboard, retrieval routing, quorum, flooding or learned graph pruning；
- PheroOS ABI/TCK/Governance changes；
- `ChainedRecordV07`, `ArtifactManifestV07` or actual runtime NDJSON correctness
  unless the final Base leaf includes the unresolved dual-layer/re-chain proof；
- production readiness or publication authority。

The rigorous interpretation remains: receptor-gated ligand field is a
theoretically motivated, falsifiable candidate architecture. Comparative
superiority remains unproven.
