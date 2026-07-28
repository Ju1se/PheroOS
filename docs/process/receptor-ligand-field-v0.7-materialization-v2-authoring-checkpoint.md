# Receptor-Gated Ligand Field v0.7 Materialization V2 Authoring Checkpoint

状态：`draft-authoring-check-only`；V1 NO-GO、G2/G3 blocker 继续有效

检查点起始日期：2026-07-28；本次续审日期：2026-07-29

## 1. 决定

本检查点把
[V2 closure design](receptor-ligand-field-v0.7-materialization-v2-closure-design.md)
中的三个开放方向收敛为可测试的候选设计：

1. profile/companion 使用固定原始 bytes 加 deterministic amendment transform；
2. 71-record design materialization 与 140-environment actual-chain runtime
   fidelity 分相；
3. design/promotion source freeze 使用八个 source actors、一个共同 bootstrap
   launch-intent batch 和下游 process-start records。

这仍不是冻结合同、profile amendment、source audit、materialization pass 或 runtime
evidence。当前状态保持：

```text
materialization_review = "blocked"
G2 = "blocked"
G3 = "blocked"
G4_G8_authorized = false
provider_or_network_use = false
comparative_superiority_conclusion = null
hypothesis_conclusions = {}
```

本轮没有读取 API key，没有 provider/network request，没有 outcome read，没有修改
PheroOS ABI、schema、TCK、Evidence、Governance、Optimal Commit、permission、
fallback 或 output authority。所有 authoring reports 固定：

```text
authority_scope="none"
acceptance_authorized=false
commit_authority=false
controller_execution=false
evaluator_enabled=false
provider_call_count=0
outcome_read_count=0
network_used=false
core_write_count=0
```

## 2. Profile/companion amendment 决策

### 2.1 固定输入

选择“固定原始 bytes + deterministic transform”，不维护第二份平行语义 profile。
输入固定为：

```text
P0 =
  docs/process/receptor-ligand-field-experiment-profile-v0.7.md
  byte_count = 119802
  raw_root =
    sha256:bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6

C0 =
  docs/process/receptor-ligand-field-experiment-profile-v0.7-fixtures.json
  byte_count = 62097
  raw_root =
    sha256:322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360
```

Main-bound `ProfileCompanionAmendmentTransformV2` 只能定义：

- P0/C0 path、byte count 和 raw root；
- 四个带 old-value assertion 的 RFC 6901 patch；
- V2 companion schema、exact keys 和 semantic-root formula；
- profile appendix 的 literal segments；
- closed typed sealing-binding context；
- stale-range registry 和 machine precedence；
- transform 自身 root formula。

Main 不能包含 amendment 输出 count/root，不能包含 GoldenOracle、commit 或 Identity。

### 2.2 SealingBindingContextV2

先前候选中的“runtime slots”容易被误解为可由实验 runtime 覆盖的值，现改为
`SealingBindingContextV2`。它不是调用者自由填写的 map。

唯一外部输入是 actual canonical Main blob。Context builder 必须：

1. 严格解析 Main canonical bytes；
2. 重算 Main byte count、raw root 和 `contract_root`；
3. 验证 Main path 是 transform 固定的 target；
4. 从这些 observed bytes 派生 `main_contract.*`；
5. 执行 companion transform 后，从 C1 observed bytes 派生全部
   `companion_output.*`；
6. 拒绝 caller-supplied companion output value、unknown field、unresolved value、
   duplicate declaration 或错误 use count。

允许的 typed getters 只有：

```text
main_contract.path
main_contract.byte_count
main_contract.raw_root
main_contract.semantic_root

companion_output.path
companion_output.byte_count
companion_output.raw_root
companion_output.fixture_input_set_root
companion_output.positive_fixture_set_root
companion_output.negative_fixture_set_root
companion_output.semantic_manifest_root
```

`companion_output.path` 是 transform 固定 target，不是 caller slot。每个 declaration
出现一次；template 可以重复引用，但 expected use count 必须由 transform 冻结。

### 2.3 Companion-first transform

Transform 必须先严格解析 C0，拒绝 duplicate/NFC-colliding keys，并对下列四个
pointer 执行 old value `"/"` 到 new value `""` 的原子修正：

```text
/negative_fixtures/36/operations/0/path
/negative_fixtures/36/operations/0/precondition/path
/negative_fixtures/40/operations/0/path
/negative_fixtures/40/operations/0/precondition/path
```

`""` 是 RFC 6901 document root；`"/"` 不是 alias。

随后 transform：

- 将 companion schema 改为明确的 V2 literal；
- 新增且只新增五个 Main bindings：

```text
materialization_contract_version
materialization_contract_path
materialization_contract_byte_count
materialization_contract_raw_root
materialization_contract_semantic_root
```

- 重算 negative fixture set；
- 使用新的 V2 semantic-manifest label；
- 输出 `C(C1) || LF`。

新的 fixture semantic preimage 必须包含上述五个 Main fields。否则 Main 改变时，
semantic root 可能保持不变。它不得包含 C1 自身 byte count、raw root 或 semantic
root。

只执行四个 RFC 6901 patch、仍保留 V1 schema/formula 的 read-only counterfactual
固定为：

```text
T1 operation root =
  sha256:8e77fe97dc76ac3e16693f3c26f2c82467089a933fc71bc688b0266aff8dacbc
T1 recipe root =
  sha256:8ced8a22c7fa8382be2db04831835a1a80aa9ef0d43ebf2b51549d7d4ac66fc0
T4 operation root =
  sha256:1d3f6fa6e68cd8dd8f1944b023e3335d31121ce335898f6394fbe36e0df6723c
T4 recipe root =
  sha256:a75e0a6cfd8583f0a56ddb22da43918e7da37ba9bf9dfb918dd9570324123e06
negative_fixture_set_root =
  sha256:5c4cf71f6985766af2ab30735900403ef2dfeee57e674b0a2abbd342590c785e
semantic_manifest_root =
  sha256:eccec79803913d858ebc60b4c78ae8854a606102fffec7e681ae29c6d87a3bf2
byte_count = 62093
raw_root =
  sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795
```

这些是 impact evidence，不是最终 C1 roots；Main bindings 尚不存在，所以 final C1
不能生成。

### 2.4 Append-only profile 和 precedence

Profile transform 固定：

```text
P1 = P0 || APPENDIX_BYTES
appendix_start_byte_offset = 119802
```

不得通过 heading search、fuzzy match 或 Markdown renderer 定位 appendix。
APPENDIX 可以绑定 P0、observed Main 和 derived C1；禁止包含：

```text
final_profile_byte_count
final_profile_raw_root
amendment_result_root
golden_oracle_root
core_commit
identity_root
```

P0 中三个 stale ranges 只作 baseline/history identity：

| byte range | content role | exact range root |
| --- | --- | --- |
| `[34803,34955)` | old companion dependency row | `sha256:ade9f5823009ae8fd2082076da7b4c97db8116ecba82e36d205a8b70b062c4d3` |
| `[35788,38578)` | old companion bindings/formula | `sha256:8fcd3bc50dd26bebd7bac140dbd216859ce098c6de3538d7b6284859c85ffa7a` |
| `[91245,92063)` | old companion key inventory | `sha256:c06861aedfed371db979ba0c73de36b1d3852235dc4e4072188294f920545f20` |

Machine precedence 唯一定义为：

```text
effective_v2(key) =
  appendix_binding[key], if key is in closed_v2_override_key_set
  baseline_value[key],   otherwise
```

Override missing、duplicate、unknown、从 stale range fallback 或 consumer 绕过
`effective_v2` 都拒绝。旧 ranges 不再是 V2 fallback source。

### 2.5 无环性

只允许：

```text
P0,C0
  -> Main
  -> C1
  -> P1
  -> AmendmentResult
  -> GoldenOracle
  -> immutable core commit
  -> Identity
```

Main 不绑定 C1/P1 output；C1/P1 不绑定自身 file root；Oracle/commit/Identity 只在
下游。因此此 transform 没有发现内容寻址循环。

## 3. Base 与 actual chain 分相

### 3.1 三个不同角色轴

| 轴 | identities | source relationship | required comparison |
| --- | --- | --- | --- |
| design materializers | A1/B1 | distinct frozen source roots | 12 个 source-neutral Base bytes/roots equal |
| runtime producer replicas | RA/RB | same frozen producer P source | actual NDJSON 和 `ArtifactManifestV07` byte-exact |
| independent runtime verifier | V | source distinct from P | independently reconstruct P-bound actual chain |

A1/B1 不是 RA/RB；V 不是第二个 producer replica。

### 3.2 Design/promotion scope

71-record materialization 只覆盖：

```text
12 Base
3 positive
56 negative
```

环境 Base 应使用完整 source-neutral record stream，而不是一行弱化
`EnvironmentCoreV2`。每个 environment/intent record 保留对应
`ChainedRecordV07.payload` 的 exact semantic payload，但排除 source-bound genesis、
previous/record roots、suite header/footer 和 `ArtifactManifestV07`。

Design product 可以证明：

- exact 12 constructors；
- normalized view、path inventory、construction trace；
- source-neutral record/payload order；
- A1/B1 byte equality；
- positive/negative operation materialization。

它不能证明 actual source-bound chain、140-environment coverage 或 runtime fidelity。

### 3.3 Runtime-review scope

Actual runtime layer 必须另外保存：

- `ActualRecordIndexEntryV2`；
- `ActualRecordIndexV2`；
- `ActualChainArtifactWrapperV2`；
- `ActualChainVerificationV2`；
- `BaseActualRecordSpanV2`；
- `BaseActualChainJoinV2`。

每个 actual wrapper 保留完整 source-bound：

```text
producer_source_commit
producer_source_root
record_genesis
all ChainedRecordV07 records
exact NDJSON bytes/root/count
final_record_root
exact 16-key ArtifactManifestV07
```

每个 full-scale replica 的 exact record inventory 是：

```text
suite_header                 1
environment_header         140
receiver_shard             644
event_or_job_shard        1540
step_record               7000
environment_terminal       140
intent_binding             980
suite_footer                 1
total                     10446
```

因此 runtime verifier 必须 all-and-only 验证 10,446 records、140-row total order、
980 intents、coverage、chain、manifest 和 totals。12 个 fixture joins 不能替代其余
133 个 environments。

首次 source-neutral/source-bound 汇合只能发生在
`BaseActualChainJoinV2`：

```text
BaseMaterializationV2 + ActualChainArtifactWrapperV2
  -> BaseActualChainJoinV2
  -> runtime supervisor attestation
```

Base 不能包含 actual wrapper root；actual artifact 不能包含 Base root；verifier source
不能写入 producer manifest。

### 3.4 Phase claim boundary

```text
design-review:
  may prove deterministic 12/3/56 materialization
  may not claim actual chain, runtime fidelity or G2 qualification

promotion-review:
  may rerun the same immutable design materializers
  may not execute or claim 140-environment task-state fidelity

runtime-review:
  must use same-source fresh RA/RB plus separately sourced V
  must prove full actual-chain coverage before G2 qualification
```

只有满足正式合同并通过的 promotion-review 才可关闭 deterministic-design
materialization；只有满足正式 runtime 合同并通过的 runtime-review 才可关闭
actual-chain fidelity。二者均不支持 H1-H6 或 comparative superiority。

## 4. Source freeze refinement

### 4.1 Design/promotion actor set

Design/promotion `SourceFreezeManifestV2` 固定八个 source actors：

```text
bootstrap-a0
bootstrap-b0
official-a1
official-b1
supervisor
fresh-reader
closure-reviewer-a
closure-reviewer-b
```

按 upper-triangular ordinal 覆盖全部 `8 choose 2 = 28` pairs。每个 actor 必须绑定：

```text
actor_id
actor_role
source_commit
source_tree_oid
source_inventory_root
semantic_source_root
actor_root
```

实际使用记录必须与完整 actor tuple exact equal，不能只比较一个 semantic root。

### 4.2 检测结论不是历史独立性证明

Pair decision literal 采用：

```text
no-prohibited-collision-detected-under-v2-procedure
```

禁止使用 `independence-audit-passed` 作为历史或认知独立性的证明。正式 metric record
至少还必须包含：

```text
check_kind
applicability
pair_policy_root
source_audit_procedure_root
left_actor_root
right_actor_root
left_scoped_inventory_root
right_scoped_inventory_root
allowed_shared_input_set_root
algorithm_id
parameter_root
observation_count
observation_set_root
observed_statistic
threshold
comparison_operator
prohibited_collision_detected
evidence_path
evidence_byte_count
evidence_raw_root
evidence_semantic_root
metric_observation_root
```

Threshold 必须来自 frozen procedure；applicability 必须来自 closed role-pair matrix。
Opaque root 加 `detected=false` 只能通过 authoring structure check，不能通过正式 source
audit。

候选 AST/token operating point：

```text
AST subtree node count >= 48
contiguous normalized token run >= 96
token shingle width = 24
minimum intersection = 16
Jaccard threshold = 65/100
containment threshold = 80/100
waiver_count = 0
```

这些阈值必须在读取最终八份 actor source 结果前，用从零实现正控和
copy/rename/comment/literal/line-ending 负控校准。它们不是 independence probability，
也不是 RG-LF 性能证据。

### 4.3 Manifest、Seal 和 launch DAG

修订后的结构是：

```text
SourceAuditProcedureV2
  + SourceAuditBasisV2
  + 8 frozen actor sources
  + 28 observed pair metrics
  -> SourceFreezeManifestV2
  -> SupervisorPrelaunchCheckpointV2
  -> FreshReadObservationV2
  -> SourceFreezeSealEvidenceV2
  -> SourceFreezeLaunchBatchV2(A0 intent, B0 intent)
  -> ProcessStartRecordA0 and ProcessStartRecordB0
  -> bootstrap completions
  -> separately sourced closure reviews
  -> GoldenOracle
  -> core commit
  -> Identity
```

Seal 内的 structural chain 必须验证：

```text
genesis
  -> supervisor checkpoint(previous_root=genesis, ordinal=0)
  -> fresh observation(previous_root=checkpoint_root, ordinal=1)
```

三 root 必须 distinct。Checkpoint/observation 均绑定对应 actor tuple、
Manifest path/count/raw/semantic root；Seal tip 等于 observation root。

Seal 时：

```text
bootstrap_launch_intent_count=0
bootstrap_completion_count=0
golden_candidate_record_count=0
```

随后先原子封存一个同时包含 A0/B0 intents 的 launch batch，任何 child spawn 都必须
晚于 batch durable seal。两份 process-start records 均绑定同一个 batch root；它们不
以 A0 start root 作为 B0 的 predecessor。这样不会允许 A0 在 B0 intent 尚未封存时
运行。

结构记录不能证明真实 atomic write、fsync、fresh read、mount denial 或 process timing；
正式 evidence 仍必须由 OS-level supervisor/fresh reader 观察。

### 4.4 Runtime source freeze 是独立 P1

八 actor Manifest 不包含 runtime producer P 或 independent verifier V。A1/B1
不得改名为 P/V。

Runtime-review 需要独立 `RuntimeSourceFreezeManifestV2`，最小 source actors：

```text
producer-p
independent-verifier-v
runtime-supervisor
runtime-fresh-reader
```

这形成 4 actors 和 6 unordered source pairs。RA/RB 不是两个 source actors，而是
同一 `producer-p` source 的两个 fresh process identities：

```text
RA.source_actor_id = RB.source_actor_id = "producer-p"
RA/RB source commit/tree/inventory/semantic roots equal
RA/RB process, attempt, checkpoint and output namespaces distinct
```

Runtime identity 必须绑定 runtime source manifest、P/V source tuples 和 RA/RB
process records；不能复用 design `MaterializationReviewInputIdentityV2` 来承担该证明。

## 5. R7 source-freeze fragment

Source-freeze 专属 R7 fragment 的当前机械下界为 7 families、103 literal cases：

| family | count |
| --- | ---: |
| `SF-PROCEDURE` | 8 |
| `SF-AUDIT-BASIS` | 4 |
| `SF-MANIFEST` | 23 |
| `SF-PAIR-DETECTION` | 8 |
| `SF-SEAL-TEMPORAL` | 23 |
| `SF-ACTUAL-USE` | 32 |
| `SF-DOWNSTREAM-JOIN` | 5 |
| total | **103** |

这是 source-freeze fragment，不是全局 R7 final count，也不能直接加到此前的 `182`，
因为 case 可能重叠。每个 case 仍须 literal 展开 locator、mutation、八行 actor
expectations 和 expected refusal precedence。

Refusal total order 候选为：

```text
00 MR-ACTIVE-STATE
01 MR-INPUT-BINDING
02 MR-ARTIFACT-INTEGRITY
03 MR-SOURCE-COLLISION
04 MR-IMPORT-BOUNDARY
05 MR-OUTCOME-READ
06 MR-PROVIDER-OR-NETWORK
07 MR-RESOURCE
08 MR-BASE-MATERIALIZATION
09 MR-TRANSACTION
10 MR-EXPECTED-CODE
11 MR-RECEIPT
12 MR-AB-MISMATCH
13 MR-TAMPER
14 MR-UNCLASSIFIED
```

`103` cases、完整 metric evidence 和全局 R7 manifest 尚未物化，所以本节不关闭
P1 #13/#16。

## 6. External authoring implementation

独立 external-lab authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = 7d4e82ffefa33103c8708e0c1f352b240243c4e5
```

该 commit 只新增：

```text
src/rglf_lab/v2_contract_authoring.py
tests/test_v2_contract_authoring.py
```

它实现：

- v0.7 NFC canonical JSON、strict UTF-8、duplicate/NFC collision、
  surrogate、BOM、float、trailing-data rejection；
- 不依赖 Python digit limit 的 signed-integer parser/encoder；
- `H` 和 `RAW`；
- 四 pointer read-only counterfactual；
- SourceAuditBasis、8 actor、28 pair、Manifest、nested Seal chain、
  common launch batch 和 process-start structural validators；
- Manifest/Seal/Batch/Transcripts 的 canonical byte-first joins；
- `false == 0` / `true == 1` type-confusion rejection；
- zero-authority reports；
- AST regression denying IO/process/network/provider/dynamic-import surfaces。

Final source bytes：

```text
src/rglf_lab/v2_contract_authoring.py
  sha256:a66d1101a3653f4113d30c9477179d36c4d24167dfa3dc6e63e114ce139da28e

tests/test_v2_contract_authoring.py
  sha256:e79dd2a3c0dd5716d2acf122109724af6aa7e2c5acab7b389991388393916ef1
```

Provider-free verification：

```text
pytest:
  19 passed, 9 subtests passed

unittest:
  Ran 19 tests
  OK

ruff:
  All checks passed

independent declared-boundary code review:
  P0=0
  P1=0
  P2=0
  P3=0
```

这里的 residual zero 只覆盖该 authoring module 明确声明的结构性边界。它不表示
MaterializationContractV2、SourceAuditProcedureV2、GoldenOracle、Identity、R7、
G2 或 G3 没有 blocker。

Module 没有 CLI、write、acceptance、provider 或 network entrypoint。它不会写 profile、
companion、core 或 evidence；counterfactual bytes 只在 memory 中返回。

### 6.1 71-record fixture inventory authoring

同一隔离 branch 的后续 commit：

```text
commit = cbca3c31184067645b1de8ffa280672ec4390b2c
```

只新增：

```text
src/rglf_lab/v2_fixture_inventory_authoring.py
tests/test_v2_fixture_inventory_authoring.py
```

它从 exact current companion 开始，只执行前述四 pointer in-memory
counterfactual，然后 byte-first 绑定：

```text
source_state = "four-pointer-counterfactual-v1-not-final-c1"
source_byte_count = 62093
source_raw_root =
  sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795
```

Machine inventory 固定 71 个 stable identities：

```text
base_count = 12
positive_count = 3
negative_count = 56
operation_count = 69
record_order = "artifact-rank-then-utf8-stable-id-v1"
artifact_rank = ["base", "positive", "negative"]
```

它验证 literal base constructor/parameters、view selector、positive
fixture-input/expected-receipt/commitment roots、negative recipe roots、
operation/precondition shapes、stage/code joins，以及三个 exact authoring guard：

```text
base_literal_binding_set_root =
  sha256:54b0e993ec560bcbd5d48e206e0fd7682f06cc8d1a7405626b3c6dcc3328353d
negative_stage_code_binding_set_root =
  sha256:96d54045a1dc418c8faace0e1167f096b57ddaf15331a702dbdb74710fbab7ff
operation_literal_binding_set_root =
  sha256:fc74d74abda8691500f78a0a7641c23fd3950e4ea105c9fac60a22545eedb65c
```

生成的内存 inventory 固定为：

```text
byte_count = 116430
raw_root =
  sha256:37ad9ec7c217bec60911ea952b3abf43f9102da0cf47bb352842026a456ce155
inventory_root =
  sha256:eb6df144a64f8daebfebe6a6a8819ef99c83d44bab3130707cf5dde22fce4d04
```

Final source bytes：

```text
src/rglf_lab/v2_fixture_inventory_authoring.py
  sha256:15549dc900daca987f8d185df4f02798ec84f7c7e42b04d560b61feb0be7ceed

tests/test_v2_fixture_inventory_authoring.py
  sha256:5476b16742b97f0b7813cd28246e467c6436cc6501f32afc7149d1fabaec5419
```

Combined authoring verification：

```text
pytest:
  32 passed, 12 subtests passed

unittest:
  Ran 32 tests
  OK

ruff:
  All checks passed

independent declared-boundary code review:
  P0=0
  P1=0
  P2=0
  P3=0
```

红队用会重算 companion set/semantic roots 的反例验证了：同 stage 换 code、换
judge、同形 precondition、同形 operation value 和 Base parameter 漂移均被拒绝；
攻击者即使重算 record/inventory roots，也不能绕过 exact expected-byte join。

这个 inventory 是 identity/known-binding skeleton，不是
`MaterializationContractV2` 的 71-record descriptor registry。每条 record 都保留
kind-specific `unresolved_normative_leaves`；特别是 Base nested semantic schemas、
三个 `PositiveClosureProjectionV2`、positive after-view encoding/reseal、56 个
`NegativeJudgeInputProjectionV2`、71 个 locator descriptors、parser resource bounds
和 independent GoldenOracle 仍未闭合。三个 binding roots 是 authoring guards，不是
独立 oracle。

在 authoring branch 运行旧 full qualification suite 时，已完成部分得到
`139 passed, 45 subtests passed, 5 failed` 后人工停止高成本 replay。五个失败来自
frozen qualification/source-identity guard：同一 baseline exact-rebuild 测试在 clean
活动实验 branch 通过，在新增 authoring source 的 branch 按设计拒绝。Canonical
commit `2f1d473a6edb9fba61ccfa39d7214b0d688e44d7` 绑定 source root
`sha256:9e3b1884fce7185e910b1d953c0ab1c1c7e690791e9ced2396429cb410352061`；
在本轮后续 modules 出现前，authoring parent
`d6e4d05c0b7db80b802394091de32efc11c929ba` 已变为
`sha256:2a9907610d4ab19d83bb39e26038b3fcc019d90bed3dde09c3f48bc3928b0710`。
这是隔离 branch 的 frozen-qualification invalidation，不是 active-baseline defect。
不得 refreeze 旧 qualification artifacts 来掩盖该 source identity 变化。

### 6.2 56-record negative judge-input ambiguity audit

同一隔离 branch 的后续 commit：

```text
commit = 28ce671dcbd86cb5ebf173f64dc1d42a46e01497
```

只新增：

```text
src/rglf_lab/v2_negative_projection_authoring.py
tests/test_v2_negative_projection_authoring.py
```

在选择任何 final `NegativeJudgeInputProjectionV2` 前，独立 static/runtime API
审计确认当前执行覆盖是：

```text
base constructor execution     = 0 / 12
normalized view bytes          = 0 / 12
operation transaction execution = 0 / 56
reseal execution               = 0 / 56
judge invocation               = 0 / 56
rejection receipt generation   = 0 / 56
```

因此 fixture recipe 的存在不能解释成 fixture 已执行。现有相似 artifact verifier
分别只接受自己的 closed artifact、profile identity 或 evidence bundle，不能替代
negative fixture 的 producer validator、independent verifier、source auditor 或
resource supervisor。

新的 authoring-only audit 从 exact four-pointer counterfactual companion，经上一节
71-record inventory，再对 56 个 negative records 做第二层 byte-first expected-byte
join。它将已知分类固定为候选 source families，而不是 final byte selection：

```text
structured-view-family-v1       = 41
decoded-raw-ndjson-family-v1    = 3
source-file-family-v1           = 6
process-evidence-family-v1      = 6
mode_cell_count                 = 14
closed_fact_count               = 5
blocker_count                   = 9
```

只有以下三条的 source-selection rule 能由
[V2 closure design](receptor-ligand-field-v0.7-materialization-v2-closure-design.md)
第 5.4 节唯一识别：

```text
N-NDJSON-APPEND
N-NDJSON-NONCANONICAL
N-NDJSON-TRUNCATE
```

它们都要求 strict RFC 4648 decode `/raw_ndjson_bytes`、在 decoded octets 上执行
byte operation，并把 mutated decoded octets 原样交给 frame judge。但 Base bytes、
final C1 和 actual runtime source join 仍未生成，所以这三条也不产生 payload。

其余 53 条仍有 exact judge-input source ambiguity：

- structured records 尚未选择 normalized view line、source-neutral re-chain 或
  actual chained artifact；
- source records 尚未选择 target file UTF-8、file envelope 或 source inventory；
- process records 尚未选择 OS-observed transcript、supervisor envelope 或 child
  segment；
- suite、replica-pair 和 label records 尚未选择 view line 或 rebuilt artifact/
  comparison envelope；
- 38 条非 `none-v1` recipes 尚无 exact reseal output byte contract。

Audit 明确固定：

```text
ambiguous_projection_count = 53
final_projection_count = 0
materialized_payload_count = 0
operation_execution_count = 0
reseal_execution_count = 0
judge_execution_count = 0
rejection_receipt_count = 0
conclusion = "final-projection-freeze-blocked"
authority_scope = "none"
projection_freeze_authorized = false
main_contract_eligible = false
golden_oracle_eligible = false
```

五条 closed facts 的语义正文嵌入 audit 并内容寻址；九个 blockers 分别覆盖 Base
byte identity/dual layer、structured serialization、semantic closure、
outer/replica closure、source envelope、process envelope、judge context firewall、
final C1 join 和 actual runtime source join。它们是现有 P1 #5 及其与
#1/#2/#6/#15/#19 依赖的 machine decomposition，不是九项已经关闭的新合同。

生成的内存 audit 固定为：

```text
byte_count = 93067
raw_root =
  sha256:94b571da331b7fc8c1be72c29253bb47e532a00241f7a1dece37d17b5cd69ca6
mode_matrix_root =
  sha256:9f75ae9b2477910cac00c9512cd38141bed8d6940b03f2a7db3df164dff4fc84
closed_fact_set_root =
  sha256:e7c493653cc73d5c438f86dabe88aa6d14e9409ba3f1b7aa95ed196c7781276a
blocker_set_root =
  sha256:252bb40e66d7748890fea5070137b8fe34ca08ff73deccca86d0180560660f9f
audit_root =
  sha256:23ceb12efaf8d5c1e210d7c46c8d20660ac826d79c5d3269ee3f5480507ffcbf
```

Final source bytes：

```text
src/rglf_lab/v2_negative_projection_authoring.py
  sha256:7427e878471e68cc1a9afb9c2b95b78af6be19e05542e5ac5cb3b91895370ee2

tests/test_v2_negative_projection_authoring.py
  sha256:53afd3051e1dfbc16d8c53b70c55fe9b14c29aba5d7bc60118842bb0936ba818
```

Combined authoring verification：

```text
pytest:
  47 passed, 16 subtests passed

unittest:
  Ran 47 tests
  OK

Python 3.12 / 3.13 / 3.14:
  15 projection-audit tests per interpreter
  OK

ruff:
  All checks passed

independent declared-boundary code review path A:
  P0=0
  P1=0
  P2=0
  P3=0

independent declared-boundary code review path B:
  P0=0
  P1=0
  P2=0
  P3=0
```

红队在重算所有可见 roots 后，仍拒绝 closed-fact/blocker 文本替换、family/
operation/reseal/judge/stage/code substitution、missing/duplicate/reordered records、
raw status 漂移、bool/int type confusion、payload/root 字段注入，以及 final/
materialization/authority 假提升。Audit 不包含 payload bytes、expected payload
counts/roots、operation/reseal/judge-input bytes、observed code 或 receipt。

这一步将“不知道 exact judge input”变成可复核的 machine NO-GO；它没有填补该未知，
也没有关闭 `NegativeJudgeInputProjectionV2`。

### 6.3 12-record Base parameter exact-instance audit

同一隔离 branch 的后续 commit：

```text
initial commit =
  d954daad0bb9f52fcdf182b53a2426e0532ed341
source-projection clarification =
  d58ad290b21d340203d3e324a27d3cbceea18d87
```

只新增：

```text
src/rglf_lab/v2_base_parameter_authoring.py
tests/test_v2_base_parameter_authoring.py
```

该 audit 不尝试从 12 个样本归纳六类 constructor 的通用 schema。它从 exact
four-pointer counterfactual companion，经 71-record inventory，按 companion 的
constructor-rank order 绑定当前 12 个 literal parameter instances：

```text
exact_instance_count = 12
constructor_instance_counts =
  environment: 7
  suite: 1
  replica-pair: 1
  labels: 1
  source: 1
  process: 1

companion record ordinals = [0,1,2,3,4,5,6,7,8,9,10,11]
source inventory ordinals = [0,1,2,3,4,5,6,11,9,7,10,8]
```

两种 order 被分别保留，不能互换。每条 record 绑定 companion pointer、Base ID、
constructor ID/rank、source record root、现有 authoring parameter root、canonical
parameter byte count/raw root，以及从根 pointer `""` 开始的 all-node RFC 6901
type fingerprint。Object children 按 canonical key order，array children 保留
declaration order；`boolean` 与 `integer` 严格分开。

当前 12 个实例的 parameter shape 总计：

```text
parameter_node_count = 106
array   = 4
boolean = 3
integer = 43
null    = 1
object  = 19
string  = 36

per-record node counts =
  [7,7,7,7,7,7,7,2,3,8,30,14]
```

每条 path-specific fingerprint root 都由 immutable expected literal 独立锚定。
因此保持全局 histogram 不变但移动 label array membership，或交换 process
`exit_code`/`signal_number` 的 null/integer path，都会在 structure 层被拒绝；
同 path、同 type 的值变化则仍可通过 structure 层，并必须由 exact
source-to-inventory-to-audit byte join 拒绝。这一分层避免把结构审计偷升格成
constructor schema。

Audit 显式保留六项 machine blockers：

1. environment：七个 current literals 只绑定
   `A4/N100/S9000/R0/steps50/T1..T7` 的六参数对象；从该对象到完整
   `ScaleEnvironmentConfigV07`、derived records 和 140 个 full-scale
   environments 的投影仍未闭合；
2. suite：当前实例只绑定 `producer_replica="A"`；可复用 replica domain、980
   intent membership/order、projection 和 output bytes 仍未闭合；
3. replica pair：当前实例只按方向绑定 `A/B`；reusable member domain、T1-T7
   environment projection、actual artifact preservation/re-chain 和 comparison
   envelope 仍未闭合；
4. labels：v0.6 使用 `intrinsic_challenge_event_ids` 并声明 T7 intrinsic universe
   为空；v0.7 prose 把 positions 33/34 同列为 mandatory，但 companion 使用
   `task_intrinsic_challenge_event_ids=[...00033]` 和
   `mandatory_probe_event_ids=[...00034]`。Audit 只记录这个 name/classification
   conflict，不替 profile/companion 选择语义；
5. source：当前七项 literal array 保留 `entry.py` 在 `eligibility.py` 之前的
   declaration order；Unicode path order 的 observed permutation 是
   `[1,0,2,3,4,5,6]`。`constructor_parameters` 必须保留 literal array，而
   normalized source view 必须另行生成 Unicode-sorted file map；仍未冻结的是
   exact array-to-map projection、file value shape 和 construction-trace steps，
   不是在两个 order 中二选一；
6. process：当前实例只绑定 13 个 literal fields，以及 `Cg==`、segment count
   `1/1`、RSS `1048576/2097152` 等 observed facts；generic key/type/range/
   nullability、frame/count/clock/exit/wait4 cross-fields、measurement projection
   root 和 OS-observed evidence envelope 仍未闭合。Synthetic companion
   transcript 不是 runtime process receipt 或 experiment evidence。

因此 audit 固定：

```text
normative_schema_count = 0
normative_schema_closed = false
constructor_execution_count = 0
normalized_view_count = 0
base_materialization_count = 0
conclusion = "exact-instance-bound-normative-schema-open"
authority_scope = "none"
main_contract_eligible = false
golden_oracle_eligible = false
materialization_authorized = false
```

生成的内存 audit 固定为：

```text
byte_count = 25551
raw_root =
  sha256:1612f3636a21a7689025cb8a1939fdfc86b119fada11537151485f787da21469
record_set_root =
  sha256:b79644c975496a7e9ca88bc19722f4f5b696cf5a402fcf5f687969db51854113
blocker_set_root =
  sha256:48e2dd6160dab7a884e9fd88e410cbfef32132d63b9ae78fd4eccc4617407979
audit_root =
  sha256:3e8e6df93b99d5b714f6dc80ed5e2c1fe955e3473dd926d97b9278c4f8e7b9c3
```

Final source bytes：

```text
src/rglf_lab/v2_base_parameter_authoring.py
  sha256:949dd0aab7f90059bf7fa3f48d739c8458a8a94e67125d3820695a8fda98b471

tests/test_v2_base_parameter_authoring.py
  sha256:c21979ef9fbf217701f11d6f118c154cfd69bba9926b7529c648526b9195fa4f
```

Combined authoring verification：

```text
pytest:
  61 passed, 31 subtests passed

unittest:
  Ran 61 tests
  OK

Python 3.12 / 3.13 / 3.14:
  14 Base-parameter-audit tests per interpreter
  OK

ruff:
  All checks passed

independent declared-boundary code review:
  P0=0
  P1=0
  P2=0
  P3=0
```

红队在重算全部可见 local roots 后，拒绝 nested bool/integer confusion、伪造
inventory ordinal、family/type count 漂移、record reorder、path-specific label/
process shape 漂移、unknown/missing keys，以及 authority/materialization 假提升。
Structure 层有意不拒绝 same-shape open-semantics 变体；exact-source join 对它们
fail closed。

这一步只把“当前 12 个 parameter instances 的 exact bytes 与 shape 是什么”变成
可复核事实。它没有生成 constructor、normalized view、Base payload、path inventory、
construction trace、receipt 或 OS evidence，也没有关闭任何 normative schema。

后续
[Base schema closure audit](receptor-ligand-field-v0.7-base-schema-closure-audit.md)
把六类 exact-instance facts 与 reusable contracts 分开复核。Active v0.6 与 v0.7
no-estimand-change provenance 唯一支持 T7 intrinsic 为空、positions 33/34 均为
mandatory；companion 中的 33-intrinsic/34-mandatory 分法因此是 blocking draft
defect，不是等权 protocol choice。该后续审计只推荐原子版本化 A correction（并优先
保留现有 negative recipe 所指 event 34），没有修改 companion、profile、lock、Main、
Golden 或 authority。

再后续
[T7 A1 counterfactual audit](receptor-ligand-field-v0.7-t7-a1-counterfactual-audit.md)
与 external commits `6707c028dfec9fae7fdc166788e2dd7b5e56ac21`、
`d6e4d05c0b7db80b802394091de32efc11c929ba`
把该推荐机器化为 exact in-memory A1 impact evidence。它从 exact 62093-byte
four-pointer source 生成 62094-byte A1，证明 locator index 0→1 前后均解析为
event 34，并把三项旧 downstream audits 标记为 invalidated/rebuild-required。
最终 targeted tests 为 15 tests/18 subtests，五组 V2 authoring helpers 合并为
76 tests/49 subtests；Python 3.12/3.13/3.14 与两路独立 post-fix review 均复现。
该 helper 仍固定 final C1、profile write、operation/reseal/judge execution、
negative projection、provider/network/outcome read 和 authority 为 false/zero，
因此不减少下节“至少 19”项开放 P1。

随后
[six-family constructor resolution matrix audit](receptor-ligand-field-v0.7-constructor-resolution-matrix-audit.md)
与 external commit `f3af7f68ea6724942ceaf1c180b58c2a2017f07d`
把 environment/suite/replica-pair/labels/source/process 的候选规则统一为 90 条
content-addressed claims：31 `PROVEN`、13 `DERIVABLE`、45 `OPEN`、1
`CONFLICT`。Audit 固定为 63,776 bytes，root 为
`sha256:c1b3b94ff07221a953c7373f77465f28f0f39df86cb1efd05dd19c4a12557669`。
三路独立 code/semantic/tamper review 均为 `P0=P1=P2=P3=0`；六组 V2 authoring
联合验证为 88 tests/64 subtests。

该矩阵显式固定 `rule_source_locator_count=0`、
`semantic_entailment_proof_count=0`、`normative_schema_count=0`、
`normative_projection_count=0`，并保持 execution、materialization、observation
的相关 counts 为 0，`network_used=false`、`authority_scope=none`。它是
author-reviewed candidate resolution，不是逐条 semantic proof、schema closure
或 G2/G3 放行，因此也不减少下节“至少 19”项开放 P1。

再后续
[environment evidence overlay audit](receptor-ligand-field-v0.7-environment-evidence-overlay-audit.md)
与 external commit `ea73fe1add86529884adbf0ece7f6622fe4e3fa9`
为 environment 的 15/15 rules、20/20 source-ref edges 生成 26 个 exact locators。
这只是 family coverage；global coverage 仍是 15/90 且
`global_rule_coverage_complete=false`。Overlay 固定为 55,432 bytes，root 为
`sha256:abb8c6eee795b8dc1076d0f35c5289e615988ba790e813af0e6c2abe5c5b273c`，
同时保持 machine/normative semantic proof、schema、projection、execution、
materialization、observation、provider 与 outcome 的相关 counts 为 0，
`network_used=false`、`authority_scope=none`。Strict-integer source 明确不能蕴含
Python `type(value) is int`。因此这一步不修改原 audit，也不减少下节“至少 19”项
开放 P1。

## 7. 当前开放 P1

原 closure design 的 18 项仍是“至少”集合。本检查点新增一个独立 runtime source
phase blocker，因此当前至少 19 项：

1. exact Base projection tables、nested schemas、其余五类 locators、全六类
   machine semantic proofs 和 construction traces；
2. source-neutral Base/actual-chain phase contract 的完整 machine leaves，以及后续
   runtime actual evidence；
3. 三个 positive closure projection records；
4. exact positive transition 和 after-view reseal contract；
5. 56-record negative judge-input projection table；
6. 四个 RFC 6901 pointers 的实际原子 profile/companion amendment；
7. 71 descriptor records、expanded locators 和 closed expression AST；
8. normative GoldenOracle schemas 和 joins；
9. 71 golden payload counts/raw roots/root-pair values；
10. source-independent/source-bound receipt formula matrix；
11. V2 semantic/completion/verification/wrapper/process/attestation/bundle
    machine schemas；
12. IdentityV2 exact schema、phase/status/flag matrix 和 full Oracle join；
13. global R7 literal manifest、final count 和 actor expectation matrix；
14. concrete main component paths/counts/raw/semantic roots；
15. `ProfileCompanionAmendmentTransformV2`、`SealingBindingContextV2` 和
    append-only precedence 的 machine implementation；
16. complete SourceAuditProcedure、observed metric records、Git/runtime import
    audits、OS/object-store evidence、Manifest/Seal/launch process proof；
17. concrete Oracle path/count/raw/semantic roots；
18. V2 official implementation、source freeze、R0-R8 process evidence；
19. `RuntimeSourceFreezeManifestV2`、P/V source audit、RA/RB process identity 和
    runtime source-to-actual-chain joins。

因此任何 V2 object 仍不得使用 `frozen`、`complete`、`passed` 或
`activation-ready`。

本轮 71-record inventory 只使 12/3/56 identity、literal source binding 和当前
unresolved set 可机读；它没有关闭上述第 1、3、4、5、7、8、9、14、15 或 17 项，
因此开放 P1 数量仍是“至少 19”。

本轮 56-record ambiguity audit 只把第 5 项拆成可机读的 41/3/6/6 family、
14-cell matrix 和九个 blocker；它明确保留 `final_projection_count=0`，所以同样不
减少开放 P1 数量。

本轮 12-record Base parameter audit 只把第 1 项中的 current-instance
parameter bytes、path-specific type shape 和六类 residual gap 机器化。它固定
`normative_schema_count=0`，没有生成 nested projections、locators、construction
traces 或 Base payload；因此开放 P1 数量仍是“至少 19”。

本轮 environment overlay 只关闭第 1 项中的 scoped evidence-location 子问题：
20 条 source-ref edges 可以 exact replay，但其余五类 locators、全六类 machine
semantic proof、schema/projection、trace 与 Base payload 仍开放。因此开放 P1
数量仍是“至少 19”。

## 8. Claim boundary

本检查点证明的是：

- 已发现的四个 RFC 6901 pointer 影响可由独立 canonical implementation 重算；
- 一个无环 amendment/source-freeze 候选结构可以被机器化；
- design materialization 与 actual runtime fidelity 可以被明确分相；
- 当前 authoring helpers 对其声明的 SourceFreeze、71-record inventory 和
  negative judge-input ambiguity、12-record Base exact-instance parameter
  结构边界 fail closed；
- 当前 negative fixture execution coverage 是 0/56，且 exact judge-input
  projection 仍被 fail-closed 阻断。
- 当前 12 个 Base parameter instances 可按 exact source bytes、双 order join 和
  path-specific type fingerprint 复核。
- 当前 environment 的 20 条 source-ref edges 可按 exact locator bytes/value
  复核，且 global coverage 明确保持 15/90。

它不证明：

- v0.7 activation；
- G2/G3 completion；
- actual `ChainedRecordV07`、`ArtifactManifestV07` 或 full-scale NDJSON 已生成；
- constructor-specific normative parameter schemas、normalized views 或 Base
  payloads 已生成；
- locator 等同 machine/normative semantic entailment，或 environment schema/
  projection/constructor execution 已关闭；
- synthetic process parameters 构成 OS-observed process evidence；
- source actors 的历史、认知或统计独立性；
- provider/LLM behavior；
- H1-H6；
- receptor-gated ligand field 优于 sparse communication、blackboard、
  retrieval routing、quorum、flooding 或 learned graph pruning；
- production readiness 或 publication authority。

科研表述继续保持：receptor-gated ligand field 是理论动机较强、可证伪的候选架构；
comparative superiority 尚未证明。
