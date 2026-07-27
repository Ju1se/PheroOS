# Receptor-Gated Ligand Field Experiment Profile v0.7

状态：**draft for review, not active**；拟议的 G2 full-scale task-state
mechanics amendment；不构成 G2 qualification 或 H1-H6 结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

当前 active profile：
[v0.6](receptor-ligand-field-experiment-profile-v0.6.md)

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

## 1. Draft 状态、激活条件与边界

本文件拟把 v0.5 尚未实现资格化的 G2 full-scale task-state replay
操作化，并在 outcome 产生前新增 independent verifier、content-addressed artifact、
resource supervisor 和 `4 GiB` hard limit。新增约束只收紧 G2 mechanics
qualification，不改变实验处理、estimand 或 hypothesis。
它不改变：

- H1-H6、estimand、MESI、统计量、split、seed、repeat 或 multiplicity；
- `F/P/S/B/Q/G/R` arm 定义、预算层、controller 输入或比较关系；
- `7,252` 个完整 G2 intent，以及其中 `980` 个 scale intent；
- authority、Optimal Commit、fallback、output authorization 或 publication gate；
- PheroOS Protocol、Kernel、Governance、Driver、Trace 或 Conformance ABI；
- schema、TCK、provider 配置或 protocol-core executable code。

本 amendment 的所有 reducer、runner、artifact writer 和 verifier 都只能位于 external
research lab，并固定：

```text
authority_scope = none
commit_authority = false
output_authority = false
publication_authority = false
outcome_authorized = false
sealed_evaluator_enabled = false
controller_executed = false
provider_request_count = 0
outcome_read_count = 0
network_used = false
```

Scale task-state replay 最多证明 deterministic mechanics、完整覆盖、资源边界和可独立
复核性。它不证明 receptor-gated ligand field 优于 full broadcast、sparse
communication、blackboard、retrieval routing、learned graph pruning 或当前 scalar
pheromone。

### 1.1 激活和 lock migration

本 draft 不能被 external lab 当作 active preregistration。v0.6 在以下全部完成前继续是
唯一 active profile：

1. 本 review draft 与
   `docs/process/receptor-ligand-field-experiment-profile-v0.7-fixtures.json`
   companion 的全部 P0-P2 审阅项关闭；
2. 两个文件形成不再修改的 activation-candidate UTF-8 bytes 并在同一 commit 提交；
   当前 review bytes 不能直接成为 active bytes；
3. 记录该 commit、profile bytes 和 companion bytes 的 SHA-256；
4. external preregistration lock 保留 v0.5/v0.6 历史 hash，并原子加入 v0.7
   document hash、companion hash、四个 companion semantic roots、commit 和 effective
   profile-chain root；
5. fresh process 从 immutable Git object 按第 12 节重算 document、dependency 和
   profile-chain roots；
6. qualification log 记录在 freeze 前没有实现本文件定义的 task reducer、
   full-scale runner 或 independent verifier，也没有读取 sealed outcome；
7. 独立二审证明每个 literal operation transaction 在 normalized view 上只有一个合法
   materialization，并形成把 `activation_ready` 改为 true 的新 profile/companion
   activation candidate；当前 false 值不能被 lock 或 runtime override；
8. source lock migration 完成后，才可开始实现。

现存的 compact eligibility record program 和 v0.5 T4 mechanics 不等于本 amendment
定义的 full-scale task-state replay。它们可以作为只读设计输入，但不能被追溯标记为
v0.7 qualification evidence。若在上述 freeze 和 lock migration 前实现任一 v0.7
task reducer，该实现不得用于 G2 qualification，G2 保持 blocked。

## 2. 冻结的 scale geometry

Scale 继续使用 v0.5 的五档、两个 seed、两个 repeat、七个 task、七个 arm、`50`
logical steps 和 natural budget：

```text
(agent_count=4,    event_count=100)
(agent_count=16,   event_count=1000)
(agent_count=64,   event_count=10000)
(agent_count=256,  event_count=100000)
(agent_count=1024, event_count=100000)

task_id in T1..T7
seed in {9000,9001}
repeat_id in {0,1}
severity = 0
matrix_kind = scale
steps = 50
budget_layer = natural
```

一个 environment key 是：

```text
task_id * agent_count * event_count * seed * repeat_id
```

因此每个 producer replica 的精确逻辑库存为：

| unit | exact count |
| --- | ---: |
| unique environments | `7 * 5 * 2 * 2 = 140` |
| arm-only intent bindings | `140 * 7 = 980` |
| logical environment steps | `140 * 50 = 7,000` |
| event/job projections | `7 * 4 * (100+1,000+10,000+100,000+100,000) = 5,910,800` |
| receiver declarations | `7 * 4 * (4+16+64+256+1,024) = 38,192` |
| T4 job declarations | `4 * (100+1,000+10,000+100,000+100,000) = 844,400` |

每个 unique environment 在一个 producer replica 内精确执行一次。它的七个 arm records
只绑定相同的 environment artifact root、冻结 controller ID 和 intent root；不得执行
controller，不得复制七次 environment state，也不得产生 arm cost 或 outcome。v0.5
要求的 fresh-process A/B 是同一逻辑库存的两个 qualification replicas，不增加 intent、
repeat 或 estimand count；上述计数均按单个 replica 计。

任一缺失、重复或超出这些轴的 environment、step、projection、receiver、T4 job 或 intent
binding 都使 full-scale component blocked。

## 3. External typed task-state union

External lab 必须定义第 13 节 exact-schema、sealed-by-version 的：

```text
ScaleTaskStateV07 =
    T1VersionedFactStateV07
  | T2CorrelatedScoutStateV07
  | T3HazardRecoveryStateV07
  | T5SparseEvidenceStateV07
  | T6MinoritySearchStateV07
  | T7TenantPartitionStateV07
```

T4 必须复用 v0.5 已冻结的 `T4EnvironmentStateV1`，不得创建语义较弱的第二个 T4
state object。这个 union 是 external research artifact，不是 PheroOS ABI。

每个非 T4 variant 具有第 13.1 节列出的 exact envelope：

```text
schema
task_id
environment_commitment_root
step
previous_state_root
revealed_event_count
revealed_event_chain_root
terminal_receipt_count
task_payload
```

`task_payload` 必须是下列精确 variant 之一；这里列出的字段集合是 closed set，不允许
实现自行增加字段。字段类型、collection preimage、genesis、total reducer、tie-break 和
error code 由第 13-14 节完整冻结。Unknown variant、task/variant mismatch、missing field、
extra field、non-canonical collection、invalid root 或 skipped step 必须 fail closed。

### 3.1 T1 Versioned-Fact Stream

`T1VersionedFactStateV07.task_payload` 恰好绑定：

```text
active_head_by_subject_root
active_evidence_set_root
superseded_evidence_set_root
retracted_evidence_set_root
conflicting_subject_set_root
abstaining_subject_set_root
version_transition_chain_root
```

对当前 step 新 reveal 的 event，reducer 先按 `(evidence_version, logical_time)` 选择
每个 subject 的最高 head group，再在非冲突 group 内按 event_id 选择 canonical head。
`supersedes` 只能引用已 reveal 的同 subject 旧 evidence；合法引用把旧 evidence 移入
superseded set；带 frozen `retraction` tag 的合法引用另进入 retracted set，并产生
transition receipt。相同 subject/version 的不同 payload digest 保留为 conflict，不允许
last-write-wins 删除。`verified` 和合法的 `superseding` 均可成为 active head；无此类
active head 或只有 unresolved conflicting heads 的 subject 进入 abstaining set。Future
event、sidecar relevance 或 controller selection 均不得参与 state。

### 3.2 T2 Correlated-Scout Cascade

`T2CorrelatedScoutStateV07.task_payload` 恰好绑定：

```text
principal_set_root
verified_cluster_membership_root
independent_cluster_set_root
candidate_cluster_support_root
correlated_clone_receipt_root
independent_correction_receipt_root
unresolved_candidate_set_root
```

独立证据单位是 `(verified_cluster, causal_lineage_root, evidence_ref)`，不是 principal
或 emission 数。共享该单位的 Sybil/clone emissions 必须全部保留在 membership receipt，
但只能增加一次 independent-cluster support。不同 cluster 的 correction 按 reveal
顺序追加，不能覆写历史 clone record。Reducer 不读取 “correct minority” 或 evaluator
label，也不把 public candidate ID 当作正确答案。

### 3.3 T3 Hazard-and-Recovery

`T3HazardRecoveryStateV07.task_payload` 恰好绑定：

```text
open_alarm_lineage_root
pause_receipt_root
mitigation_receipt_root
expired_deadline_receipt_root
recovered_lineage_root
current_reversible_mode
```

`current_reversible_mode` 只能是 `running` 或 `paused`。每个已 reveal alarm 按公开
causal lineage 建立可逆 pause receipt 和 inclusive deadline；同 lineage、合法 parent
引用的 mitigation receipt 关闭该 alarm 并恢复。到 inclusive deadline 后仍未关闭的
alarm 产生 immutable expiry receipt。Reducer 不使用 true/false-alarm sidecar identity；
true、false 和 recovered 的效果分类只属于 disabled sealed evaluator。

### 3.4 T5 Sparse Evidence Search

`T5SparseEvidenceStateV07.task_payload` 恰好绑定：

```text
revealed_parent_edge_root
unresolved_parent_edge_root
lineage_hop_state_root
completed_multihop_chain_root
active_version_by_subject_root
superseded_version_set_root
knowledge_update_receipt_root
```

Parent edge 只有两端均已 reveal 才能从 unresolved 转为 revealed。一个 completed
multihop chain 精确定义为第 14.5 节同 lineage parent edge 连接的两个不同 events。
`supersedes` 使用 T1 的同 subject/version 规则并保留旧版本。Reducer 对全部公开
structural edges 使用相同逻辑，不读取 sealed relevant-event set、expected answer 或
future chain member。

### 3.5 T6 Exploration/Minority Search

`T6MinoritySearchStateV07.task_payload` 恰好绑定：

```text
declared_candidate_set_root
candidate_independent_cluster_support_root
candidate_principal_membership_root
exploration_frontier_root
verification_receipt_chain_root
unresolved_candidate_set_root
```

Candidate support 按 T2 的 independent evidence unit 去重；principal multiplicity 只进入
membership。Correction/verification receipt 必须引用已 reveal candidate 和公开 parent
lineage，按 reveal 顺序追加。`candidate:minority`、`candidate:dominant` 只是 declared
candidate IDs；reducer 不得把名称、actor proportion、sidecar relevance 或 future
verification 当作正确性标签。

### 3.6 T7 ACL/Tenant Partition

`T7TenantPartitionStateV07.task_payload` 恰好绑定：

```text
tenant_partition_root
admitted_event_chain_by_tenant_root
common_gate_rejection_receipt_root
tenant_local_collision_root
cross_tenant_selected_edge_count
acl_violation_count
```

Eligibility common gate 先于 reducer。Ineligible cross-tenant event 只能进入
environment-only rejection receipt，不能进入任何 ordinary controller prefix 或 tenant
state。Eligible same-subject collision 保留在其 own-tenant state，不能跨 tenant 合并。
每 step 和 terminal 的：

```text
cross_tenant_selected_edge_count = 0
acl_violation_count = 0
```

否则该 environment 和整个 G2 full-scale component 均 blocked。Mandatory probe、
intrinsic challenge 和 variable attack 的 v0.6 三分法继续有效，task state 不得读取其
sealed group roots。

## 4. T4 non-fixture no-op replay

每个 T4 scale environment 必须使用 v0.5 的真实 deterministic environment path：

```text
matrix_kind = scale
fixture_mode = false
job_count = event_count
steps = 50
directive = G2NoOpDirectiveV1
assignments = ()
authority_scope = none
```

禁止 schedule override、fixture schedule、预计算 oracle assignment 或简化的
eligibility-only T4 record。Worker、job、DAG dependency、arrival、deadline、failure、
recovery、defer 和 dependency release 均按 v0.5 生成和转换。No-op 不冒充任一 arm；
它仍必须运行全部 `50` steps，使 deadline、failure/recovery、dependency release、
terminal defer 和 `episode-end-defer` 可观察。因为 `assignments=()`，qualification
主轨不得声称正向覆盖 completion、non-zero partial work 或 failure-triggered assignment
release；这三个不可达分支由第 14.8 节独立、zero-authority branch fixtures 检验，且其
evidence 不能替代 `fixture_mode=false` 主轨。

每个 T4 environment artifact 必须包含足以独立重算的 config、worker/job declaration
shards、sealed failure-schedule commitment、逐步 reveal/transition receipts 和 terminal
state preimages。Ordinary prefix 只能包含截至该 step 已 reveal 的 schedule prefix。
Future schedule mutation 的合法 `T4PrefixCausalityFixtureV1` 只用于
prefix-causality relational test；它不得进入 `ScaleEnvironmentArtifactV07`，也不得替代
`fixture_mode=false` 的 qualification replay。

`844,400` 是单个 producer replica 跨全部 T4 scale environments 的精确 job declaration
数。任一缺失 job、cycle、future dependency、提前 arrival、deadline-order 变化、
failure/recovery 顺序变化或 terminal job 丢失都 fail closed。

## 5. 每步 transition 与六个 mandatory roots

每个 environment 的 step `t=0..49` 按固定顺序执行：

1. 从 content-addressed declaration shards 流式 reveal 当步 event；T4 另 reveal
   arrival/failure/recovery；
2. 计算当前 topology epoch，生成 v0.4 同义且唯一的 `active_topology_root`；
3. 应用 ACL、capability、active-version 和 logical-time predicate，生成 compact
   `eligibility_root`；
4. 只用已 reveal、ordinary-visible 内容生成 `controller_prefix_root`；
5. 生成并验证 empty、zero-authority `G2NoOpDirectiveV1`；
6. 执行对应 typed task reducer；T4 执行 v0.5 scheduler transition；
7. 生成 `task_state_root`、deterministic `cost_root` 和 chained `trace_root`；
8. 写入 canonical step record 后才可前进到下一 step。

每个 step record 必须同时包含并绑定：

```text
active_topology_root
controller_prefix_root
eligibility_root
task_state_root
cost_root
trace_root
```

第 15.1 节冻结六个 root 的 exact domain、preimage 和 genesis。
`controller_prefix_root` 不得包含 environment commitment root、future shard/root、
future schedule、sidecar root、attack-group root、expected output 或 evaluator
denominator。`task_state_root` 是 environment-only mechanics state，不能作为
controller feature。`trace_root` 必须把 step、previous trace root、上述五个 roots、
revealed delta root、no-op directive root 和 terminal receipts root 一并承诺。

State map 不得在每 step 重复 materialize 全量 snapshot。Artifact 保存 canonical
declaration shards、state delta preimage 和 persistent map/set roots；independent verifier
从前一 state 和 delta 重建下一 state。Root-only、缺少 preimage 或无法重建的 step 不算
evidence。

## 6. Streaming complexity 和 cost completeness

Receiver shard size 固定 `64`，event/job declaration shard size 固定 `4,096`。Producer
和 verifier 都必须按 shard 流式运行。第 16.1 节的 guarded resident counters 必须同时
满足：

```text
peak_resident_receiver_shard_records <= 64
peak_resident_event_or_job_shard_records <= 4,096
peak_resident_state_records <=
  12*event_count + 8*agent_count + 8,192
peak_resident_pair_records = 0
```

明确禁止：

```text
receiver_count * event_count
receiver_count * job_count
steps * full_state_snapshot_size
```

的显式 Cartesian list、dense boolean matrix、pair cache、NDJSON pair record 或完整 state
snapshot 复制。Selected/dropped partition 使用 v0.5 compact descriptor、精确 count、
shard roots 和按需 membership proof；不得用 `pair_evaluations=0` 掩盖未执行的 predicate。

每个 environment 和 suite footer 的 deterministic cost ledger 恰好记录：

```text
receiver_declarations
event_or_job_projections
logical_steps
logical_receiver_event_or_job_pairs
receiver_shard_reads
event_or_job_shard_reads
projection_predicate_evaluations
partition_join_evaluations
materialized_pair_records
descriptor_bytes
peak_resident_shard_records
materialized_state_delta_bytes
state_hash_operations
trace_hash_operations
terminal_receipts
```

`projection_predicate_evaluations` 是每个 event/job declaration 的一次 schema、ACL
partition、capability mask、logical-time 和 initial active-version projection 检查，精确
等于 projection count；它不是 receiver-pair evaluation。`partition_join_evaluations`
是每 step 对一个 receiver shard 和一个当步非空 event/job shard descriptor 的一次
aggregated join，按第 16.2 节公式重算。实现不得逐 pair 运行 predicate。

每个 event/job projection 精确生成一次；active-version 和 step eligibility 从 streaming
state 增量更新，不能在每 step 把同一 projection 重新计数。Potential logical
receiver-event/job pair total 必须精确为：

```text
7 * 4 *
  (4*100 + 16*1,000 + 64*10,000 + 256*100,000 + 1,024*100,000)
= 3,602,379,200
```

该值只进入 logical cost ledger，不能 materialize。`projection_predicate_evaluations` 必须
覆盖全部 `5,910,800` projections；`materialized_pair_records` 必须为零。Suite totals
还必须精确重算 `38,192` receivers、`7,000` steps 和 `844,400` T4 jobs。Wall、CPU 和
RSS 是 observations，按 v0.2 不进入 replay root，也不得伪装成 controller cost。最终
NDJSON byte count 只允许出现在第 15.2 节 external manifest，不能进入任何被该 NDJSON
承诺的 `cost_root`、record 或 footer。

## 7. Content-addressed NDJSON artifact

每个 producer replica 输出一个 canonical UTF-8 NDJSON artifact。每行是一个完整
canonical JSON object，以单个 LF 结束；禁止 BOM、blank line、NaN、Infinity、重复 key
或非 canonical number。Record order 固定为：

```text
suite_header
for environment_key in canonical order:
  environment_header
  receiver_declaration_shards
  event_or_job_declaration_shards
  step_records 0..49
  environment_terminal
intent_bindings in canonical intent order
suite_footer
```

每行使用第 15.2 节唯一的 `ChainedRecordV07` schema。`record_root` 的 preimage 明确排除
`record_root` 字段；header 使用冻结 genesis，footer payload 绑定
`pre_footer_record_root`，footer 自身的 `record_root` 才是 final chain root。Footer 不含
artifact byte count 或 raw artifact root。Raw artifact root 定义为：

```text
artifact_root = RAW(exact_ndjson_bytes)
```

文件名必须是 `<artifact_root-without-prefix>.ndjson`。Artifact root 和 byte count 不写回
artifact 自身；第 15.2 节 exact-schema 的独立 deterministic manifest 绑定 filename、
byte count、artifact root、producer source root、effective profile-chain root、
environment set root、intent-binding set root 和 final record root。非确定的
wall/CPU/RSS observations 写入另一个 immutable observation ledger；其 receipt 绑定
artifact root 和 attempt ID，但 observation ledger root 不进入 deterministic manifest
或 A/B replay root。

Artifact 必须包含 root 的全部必要 preimage，而不是只序列化 producer 的
`verified=true`。Truncation、append、line reorder、duplicate environment、missing
terminal、980 binding 中任一 missing/duplicate、arm execution field 非空或 source/profile
root mismatch 都 fail closed。

## 8. Fresh-process A/B 和 independent verifier

两个无共享 cache、module global state、RNG cursor、temporary artifact 或 adaptation
state 的 fresh producer replicas A/B 必须生成 byte-exact 相同的 NDJSON bytes 和
manifest bytes。每个 replica 的 140 environments 可以由 fresh per-environment child
process 执行，但 canonical orchestrator 只能收集一次 primary result；retry 不能替换
primary record。

Fresh A/B 不满足 independent verification。Qualification verifier 必须：

- 是单独 executable 和 process；
- 不 import producer reducer、task-state transition helper、artifact builder、
  canonicalization/hash helper、fixture generator、cache 或 mutable module global；
- 从第 12 节绑定的 immutable comparative plan、v0.2-v0.7 bytes、fixture companion
  bytes 和 locked matrix axes 独立实现 parser、canonicalization、RNG、task
  transitions、T4 schedule、root 和 count 重算；
- 流式解析 exact NDJSON bytes，重算每个 declaration、delta、state、cost、trace、
  suite total、manifest 和 raw artifact root；
- 记录 verifier source commit/root、producer source commit/root、profile-chain root、
  verified artifact root、verification trace root 和所有失败原因。

第 12.3 和 16.1 节的独立 source auditor 还必须证明 verifier/producer source inventories
不重叠于 reducer、transition、builder、canonicalization 或 fixture implementation。
只有 executable entrypoint、standard-library module name 和本 profile 的 immutable
bytes 可以出现在共同 dependency allowlist。

若 verifier 与 producer 使用同一 state-transition program、共享 private helper 或只把
artifact 与 producer freshly rebuilt bytes 比较，则：

```text
independent_verifier = false
G2-FULL-SCALE-INDEPENDENT-VERIFIER = blocked
G2-FULL-SCALE-TASK-STATE = blocked
```

Same-program recomputation 可以保留为 diagnostic，但不能解除 blocker。Independent
verifier、fresh-process A/B 和 exact count/root checks 三者均通过，才可能资格化本
component。

## 9. Time、RSS 和 immutable failure ledger

v0.2 的 scale timeout 固定为每个 environment `900 s`。第 16.3 节 supervisor 以
`monotonic_ns` 在发送 length-prefixed frozen config 前立即开始计时；在收到完整 child
segment、验证 terminal、写入 per-environment temporary segment 并对该 file descriptor
完成 `fsync` 后停止。最终 suite concatenation 不计入单 environment timer，但单独记录。
Timeout 不能通过提前停止 events/steps、跳过 terminal defer 或只写 roots 达成。Producer、
verifier 和 supervisor 都固定一次只运行一个 environment child。

本 draft 新增、须在激活前审阅的硬上限为：

```text
baseline_rss_bytes <= 536_870_912
peak_rss_bytes <= 4_294_967_296
peak_rss_delta_bytes <= 4_294_967_296
```

即按 v0.2 的 macOS bytes/Linux KiB 规则规范化后的 `512 MiB` import baseline 和
`4 GiB` absolute/delta 上限。Supervisor 从 child spawn 起采样，child 在读取 config
前发出一次 READY baseline；最终 peak 取 supervisor samples、child self
`getrusage` 和 parent `wait4` child rusage 的最大 normalized value。Observation ledger
保存 raw platform value、unit、normalized bytes、baseline、peak 和 delta。RSS
不可测量、READY 缺失、unit 未知、overflow、负 delta 或任一上限超出均 fail closed。
相同上限分别适用于 producer environment child 和 verifier environment child；
orchestrator/supervisor 的 absolute peak 也不得超过 `4 GiB`。

Timeout、RSS exceed/unmeasurable、OOM、crash、signal、invalid config、partial artifact、
hash mismatch 和 verifier failure 必须追加到 immutable intent-to-run ledger，包含
environment key、受影响的七个 intent IDs、attempt ID、partial artifact root/bytes、
last completed step、exception/exit/timeout kind 和 observations。允许追加 diagnostic
retry，但原失败不得删除、覆盖或被成功 retry 筛掉；任一 primary failure 均保持
full-scale component blocked。

Primary attempt ID、diagnostic retry、child-exit capture、ledger hash chain 和 append
durability 由第 16.3 节冻结。Primary producer replica 中每个 environment 只执行一次；
retry 使用新的 diagnostic attempt ID、写入独立 ledger，永远不能进入或替换 A/B
primary artifact。

## 10. Frozen negative evidence

实现必须在任何 full-scale qualification claim 前验证第 12.2 节 companion，并执行其中
closed、content-addressed 的 3 个 positive 和 56 个 negative fixture recipes。下列类别
只是可读索引；literal base、selector、operation transaction、precondition、唯一 judge
和 expected failure code 以 companion 为准：

- task/variant mismatch、unknown/extra/missing field、unordered set/map；
- event、receiver、job、step 或 intent binding 的 missing、duplicate、mutation 和
  reorder；
- previous state/trace root mismatch、non-canonical NDJSON、truncate、append 和 filename
  root mismatch；
- future event/schedule/sidecar/attack-label root 进入 ordinary prefix；
- T1 invalid supersedes、conflict 被 silent overwrite；
- T2 clone principal 被误计为独立 evidence；
- T3 false/true sidecar identity 被 reducer 读取、deadline 或 recovery 顺序错误；
- T5 unresolved parent 被提前释放、knowledge update 删除历史版本；
- T6 candidate 名称被当成 correctness、correlated principal 重复计权；
- T7 cross-tenant edge 进入 prefix/state、mandatory probe 被计入 variable attack；
- qualification artifact 中出现 T4 `fixture_mode=true`、schedule override、非空
  directive、DAG cycle、future job
  reveal、failure/recovery/deadline/terminal receipt 缺失；
- receiver-event/job Cartesian materialization、state snapshot 每步复制、cost omission；
- A/B byte mismatch、same-program verifier、verifier import producer helper；
- forced timeout、RSS exceed、RSS unmeasurable、crash、OOM 和 partial write。

每个 artifact fixture 必须实际被 producer validator 或 independent verifier 拒绝；source
或 process fixture 必须分别被 source auditor 或 resource supervisor 拒绝，不能只出现
一个布尔声明。Negative artifact、failure code 和 trace root 都保留；测试只得到 expected
rejection，不获得 task outcome。合法 `T4PrefixCausalityFixtureV1` 可由其专用 relational
validator 接受；`N-T4-FIXTURE-IN-QUALIFICATION` 只证明它不能进入 qualification artifact。

## 11. G2 fail-closed decision

本 amendment 激活后，只有下列条件全部成立，`G2-FULL-SCALE-TASK-STATE` 才可由
`blocked` 变为 `qualified`：

1. exact `140/980/7,000/5,910,800/38,192/844,400` coverage；
2. T1/T2/T3/T5/T6/T7 typed reducers 完整执行，T4 non-fixture no-op reachable-state
   replay 完整执行，且 `T4-BRANCH-COMPLETION/T4-BRANCH-PARTIAL/
   T4-BRANCH-FAILURE-RELEASE` 三项独立通过并保存 exact positive receipt artifact；
3. 每 step 六个 mandatory roots 及其 preimages 可重建；
4. 无 receiver-event/job Cartesian materialization；
5. content-addressed NDJSON、fresh-process A/B 和 independent verifier 均通过；
6. 每 environment 不超过 `900 s`，normalized import baseline 不超过 `512 MiB`，
   normalized absolute peak 和 delta 均不超过 `4 GiB`；
7. 无 timeout、crash、partial/missing record、ACL/authority violation 或未保留失败；
8. 第 17.2 节 exact `56` 个 negative fixtures 各保存一个
   `rejected=true` 且 `observed_code=expected_code` 的 receipt，并保存 exact negative
   receipt artifact。

这只解除 G2 full-scale mechanics 的一个 blocker。G2 的其他 blockers、G3 strong
baseline/P durable replay/actual cost ledger、provider canary 和后续 G4-G8 仍独立
fail closed。不得把本 amendment、其实现或其 qualification 写成 H1-H6 支持、RG-LF
superiority、production readiness 或 PheroOS protocol behavior。

## 12. Normative canonicalization、identity 和 source independence

本节及第 13-17 节是 normative closed specification。实现不得增加字段、枚举值、
fallback encoding、隐式默认值或 implementation-selected tie-break。正文与附录冲突时，
附录生效；任何仍无法由本文件和绑定依赖唯一重算的值都使
`G2-FULL-SCALE-TASK-STATE` 保持 blocked。

### 12.1 Canonical value 和 digest

Canonical value 只允许：

```text
null
boolean
signed integer
Unicode string
array of canonical values
object with Unicode-string keys and canonical values
```

禁止 binary float。所有 q12 数值编码为满足
`^(0|[1-9][0-9]*)\.[0-9]{12}$` 的非负 string；运算使用 Decimal precision `34`、
`ROUND_HALF_EVEN`，每次加、减、乘、除后立即 quantize 到 `0.000000000001`。
所有 string 和 object key 在验证前转为 Unicode NFC；若两个原 key 在 NFC 后相同则
`E-CANONICAL-DUPLICATE-KEY`。Array 保留声明顺序；set 和 map 不直接编码为 JSON
object，分别使用排序 array 和排序 `[key,value]` pairs。

Canonical JSON `C(x)` 定义如下：

1. UTF-8，无 BOM；
2. object key 按 NFC 后 Unicode scalar-value sequence 升序；
3. `null/true/false` 使用小写 literal；
4. integer 使用 base-10、负数前单个 `-`、无 `+`、无 leading zero，零只写 `0`；
5. string 使用 `"`；`"`、`\` 分别编码 `\"`、`\\`；U+0008/U+0009/U+000A/
   U+000C/U+000D 分别编码 `\b/\t/\n/\f/\r`；其他 U+0000..U+001F 使用小写
   `\u00xx`；其他 scalar 直接 UTF-8 编码；
6. array/object item 之间只用 `,`，key/value 之间只用 `:`，不含 whitespace；
7. surrogate code point、NaN、Infinity、duplicate key 和 trailing data 均拒绝。

Root function 唯一定义为：

```text
H(label, value) =
  "sha256:" + lowercase_hex(
    SHA256(UTF8(label) || 0x00 || UTF8(C(value)))
  )

RAW(bytes) =
  "sha256:" + lowercase_hex(SHA256(bytes))
```

`label` 必须是本文件列出的 ASCII literal。Unknown label 不能用于 qualification。
Sorted string set `S(label, values)` 先要求 values 全为 unique string，再按 Unicode
scalar-value sequence 升序，最后计算 `H(label, sorted_values)`。Sorted map
`M(label, pairs)` 要求 key unique，按 key 升序，计算 `H(label, sorted_[key,value]_pairs)`。
Append chain：

```text
CHAIN_GENESIS(label, binding_root) =
  H(label + "/genesis", {"binding_root": binding_root})

CHAIN_NEXT(label, previous_root, item) =
  H(label + "/item", {
    "item": item,
    "previous_root": previous_root
  })
```

### 12.2 Normative dependency 和 profile chain

Activation-candidate commit 中的 exact Git blobs 按下列固定顺序形成 dependency records：

| ordinal | path | frozen SHA-256 |
| ---: | --- | --- |
| 0 | `docs/process/receptor-ligand-field-comparative-study-plan.md` | `22584acd49a9f38f89ea071a6b13384bd25d4929091832eaf6cd8bd144f17d3d` |
| 1 | `docs/process/receptor-ligand-field-experiment-profile-v0.2.md` | `8fdfb26b8c6efb435ef1c139a372d6886a72cff6ac212ab9fe42a03200afec9b` |
| 2 | `docs/process/receptor-ligand-field-experiment-profile-v0.3.md` | `2bfa902a35e2a2bc6bee96f365b621a62919777b987f8266ad6549b45f1cef8d` |
| 3 | `docs/process/receptor-ligand-field-experiment-profile-v0.4.md` | `700b28512d293428239f1abd75e7bcb13005e25ad0bec01910a384c976a504ce` |
| 4 | `docs/process/receptor-ligand-field-experiment-profile-v0.5.md` | `52bee02d20e33ef95b71339ad66c246dbdda3c79d21457f139121379bf8d470b` |
| 5 | `docs/process/receptor-ligand-field-experiment-profile-v0.6.md` | `b1a7aa84664baacdf683af406aa4e88b118ef45b001986e7f438c5d31715a979` |
| 6 | `docs/process/receptor-ligand-field-experiment-profile-v0.7.md` | `V07_SHA256` |
| 7 | `docs/process/receptor-ligand-field-experiment-profile-v0.7-fixtures.json` | `20fb0c9796b7acc1724957e5481bbad6fec80ac468dabdafa523bf50b96c7906` |

`V07_SHA256` 是公式中的 metavariable，不写回或替换本文件 bytes；activation tool 将它
解析为 `lowercase_hex(SHA256(exact activation-candidate blob bytes))`，并只把实际值
写入 external lock 和 dependency record。Fresh verifier 若在 external record 中看到
literal `V07_SHA256` 必须拒绝。每个 dependency record 的 exact keys 是
`ordinal/path/sha256/git_blob_id`；`git_blob_id` 是 activation-candidate commit 中
`git rev-parse <commit>:<path>` 的 40 lowercase hex。

```text
normative_dependency_root =
  H("g2-v07-normative-dependencies-v1", dependency_records)

effective_profile_chain_root =
  H("g2-effective-profile-chain-v2", [
    {"path": v0.5_path, "sha256": v0.5_sha256},
    {"path": v0.6_path, "sha256": v0.6_sha256},
    {"path": v0.7_path, "sha256": V07_SHA256}
  ])
```

External lock 必须逐字段保存 `V07_SHA256`、activation-candidate commit、
`normative_dependency_root`、`effective_profile_chain_root` 以及下列 companion binding：

```text
fixture_companion_path =
  "docs/process/receptor-ligand-field-experiment-profile-v0.7-fixtures.json"
fixture_companion_byte_count = 61669
fixture_companion_raw_root =
  "sha256:20fb0c9796b7acc1724957e5481bbad6fec80ac468dabdafa523bf50b96c7906"
fixture_input_set_root =
  "sha256:0227f38c34f9d50b81b257675065e73ab1c18e02fff684ca851603b3d963aed8"
positive_fixture_set_root =
  "sha256:2a0e9ff10b6e2d5e2e42bebe77dd9c32f871a48638ad4d41a796995d1ce1613e"
negative_fixture_set_root =
  "sha256:1d2a8d1986bbcfbc3917adcd6564d9bd293e9c04a547ff2ff4ff56745cfd54b7"
fixture_semantic_manifest_root =
  "sha256:673ab4138ff29e5906686213736cb6e25eff4785724e504f6705003dbaed3d54"
```

Companion exact bytes 必须是 `C(parsed_json)||LF`。Fresh verifier 按以下公式重算并逐项
比较 embedded roots；任何 byte、count、order、root 或 dependency mismatch 都使用
`E-FIXTURE-MANIFEST-BINDING`：

```text
fixture_input_set_root =
  H("g2-v07-fixture-input-set-v1", base_artifacts)

positive_fixture_set_root =
  H("g2-v07-positive-fixture-set-v1", positive_fixtures)

negative_fixture_set_root =
  H("g2-v07-negative-fixture-set-v1", negative_fixtures)

fixture_semantic_manifest_root =
  H("g2-v07-fixture-semantic-manifest-v1", {
    "activation_ready": false,
    "artifact_bytes_compiled": false,
    "fixture_input_set_root": fixture_input_set_root,
    "negative_fixture_set_root": negative_fixture_set_root,
    "positive_fixture_set_root": positive_fixture_set_root,
    "profile_id": "receptor-ligand-field-experiment-profile-v0.7",
    "schema": "pheroos-rglf-fixture-semantic-manifest-v0.7",
    "status": "draft-design-inventory-not-activation-ready"
  })
```

File raw root 只由 exact companion bytes 计算，不写入 companion，因此没有 file-hash
self-reference；四个 semantic roots 的 preimage 都排除对应 embedded root 字段。
这些 roots 只标识当前 design inventory，不是 mutant artifact 或 observed receipt
evidence。当前 companion 明确固定 `activation_ready=false`、
`artifact_bytes_compiled=false`、`runner_implemented=false` 和
`receipt_artifact_bytes_present=false`；expected receipt roots 是预注册设计值，不是运行
结果。若独立二审仍发现任一 recipe 不能唯一 materialize，profile/companion 必须一起
修订并重算全部 bindings；不能在 lock 或 runtime 中把 false 改成 true。
v0.6 在 profile 与 companion 的同一原子 lock migration 成功前保持唯一 active
profile；本 review draft 的 hash 不得填入上述字段。

### 12.3 Producer、verifier 和 supervisor source roots

实现必须在 external lab 的 immutable、clean Git commit 中使用三个互斥 source
namespaces：

```text
producer:   src/rglf_lab/g2_v07_producer/
verifier:   src/rglf_lab/g2_v07_verifier/
supervisor: src/rglf_lab/g2_v07_supervisor/
```

Source inventory 从该 commit 的 Git tree 读取，不从 working tree 读取。一个 inventory
包含 namespace 下全部 regular Git blobs；symlink、submodule、missing blob 或 namespace
外动态加载均拒绝。每项 exact keys：

```text
path
git_mode
git_blob_id
raw_sha256
byte_count
```

Items 按 path 升序。Root：

```text
source_root(role) =
  H("g2-v07-source-tree-v1", {
    "commit": 40-lowercase-hex,
    "items": inventory,
    "role": role
  })
```

Producer 和 verifier inventories 不能有共同 path、blob ID 或 raw SHA-256。二者只可共同
读取 Python standard library、activation-candidate profile blobs 和 OS syscall；不能共同
读取 external lab 的 canonicalization、RNG、generator、state、artifact、fixture 或 hash
module。Supervisor 不实现 task reducer、RNG、task generator 或 deterministic artifact
builder。它只为第 16.3 节 process framing、observation 和 ledger records 实现自己的
minimal canonical encoder 与 hash routine；该 routine 位于 supervisor inventory，
producer/verifier 均不得 import，且不能用于重算 task、cost、trace 或 artifact roots。

Source auditor 从 detached clean worktree 启动 executable；记录 executable raw hash、
interpreter absolute path/hash、`sys.path`、loaded module absolute paths 和 source root。
任一 loaded external-lab module 不在对应 inventory、producer/verifier blob collision、
working tree dirty 或 `loaded_code_identity_attested != true` 都使用
`E-SOURCE-IDENTITY` fail closed。

## 13. Exact scale declarations 和 non-T4 event generator

### 13.1 Closed schemas 和 scalar types

下列 scalar aliases 生效：

```text
Root       = string matching ^sha256:[0-9a-f]{64}$
ID         = non-empty NFC string without U+0000
Count      = integer >= 0
Step       = integer in 0..49
Task       = one of T1,T2,T3,T5,T6,T7
Status     = one of verified,superseding
EventKind  = one of support,novelty,alarm,correction,inhibition,dependency
Mode       = one of running,paused
```

`ScaleEnvironmentConfigV07` exact keys/types：

```text
schema: "pheroos-rglf-scale-environment-config-v0.7"
matrix_kind: "scale"
split: "smoke"
task_id: one of T1..T7
agent_count: one of 4,16,64,256,1024
event_count: paired value 100,1000,10000,100000,100000
steps: 50
seed: 9000 or 9001
repeat_id: 0 or 1
severity: "0.000000000000"
budget_layer: "natural"
fixture_mode: false for T4, null for non-T4
directive_schema: "pheroos-rglf-g2-no-op-directive-v1"
effective_profile_chain_root: Root
normative_dependency_root: Root
```

`environment_key` 是
`H("g2-v07-environment-key-v1", ScaleEnvironmentConfigV07)`。Config unknown/missing
key、错误 agent/event pair 或错误 constant 使用 `E-CONFIG`。

`ScaleReceiverV07` exact keys：

```text
schema, receiver_id, ordinal, role, capabilities,
tenant_id, scope_ref, acl_digest
```

其中 schema 固定 `pheroos-rglf-scale-receiver-v0.7`，ordinal 为 `0..agent_count-1`，
role 是 `verifier/coordinator/explorer/operator` 之一，capabilities 是 canonical sorted
unique ID array，其余为 ID/Root。

`ScaleEventV07` exact keys：

```text
schema, event_id, sequence, logical_time,
actor_id, principal_id, role, tenant_id, target_tenant_id, scope_ref,
subject_id, candidate_id, evidence_ref, evidence_version, evidence_status,
payload_digest, kind, tags, verified_cluster, failure_domain,
causal_lineage_root, parent_event_ids, supersedes,
required_capabilities, mechanics_deadline_step, common_gate_action,
ligand_doses
```

schema 固定 `pheroos-rglf-scale-event-v0.7`；sequence/evidence_version 为 Count；
logical_time 为 Step；`mechanics_deadline_step` 为 Step 或 null；
`common_gate_action` 只能是 `admit` 或 `reject_cross_tenant`；ID arrays canonical sorted
unique；`ligand_doses` 是 exact-key object，key 顺序和集合为
`utility/failure/hazard/uncertainty/novelty/congestion/recruitment/contradiction`，
value 为 q12 string。任何 extra/missing key 使用 `E-SCHEMA-FIELD-SET`。

每个非 T4 state envelope exact keys：

```text
schema, task_id, environment_commitment_root, step, previous_state_root,
revealed_event_count, revealed_event_chain_root, terminal_receipt_count,
task_payload
```

schema 是对应 `pheroos-rglf-tN-task-state-v0.7`；roots 为 Root；counts 为 Count；
`task_payload` exact keys 就是第 3 节对应 code block，不能增加字段。

### 13.2 IDs、receivers、subjects、candidates 和 topology

`z(i,w)` 是 i 的 base-10 表示左补 `0` 到宽 w；若 i 超过宽度则 `E-ID-RANGE`。
Receiver ordinal `r`：

```text
receiver_id = "agent:" + z(r,4)
role = (verifier,coordinator,explorer,operator)[r mod 4]
tenant_id =
  "tenant:b" if task_id=T7 and r >= floor(agent_count/2)
  "tenant:a" otherwise
scope_ref = "scope:" + tenant_id
capabilities = sort_unique([
  "capability:" + decimal(r mod 4),
  "task:" + lowercase(task_id),
  "safety" if r mod 3 = 0 else "general"
])
acl_digest =
  H("g2-v07-acl-v1", sorted receiver_ids in tenant_id)
```

Task base sizes：

```text
T1 facts=20
T2 candidates=4
T3 artifacts=16
T5 subjects=50
T6 candidates=20
T7 subjects_per_tenant=16
```

Base subjects 是 `subject:` + `z(i,4)`，i 范围依次为
`0..19/0..3/0..15/0..49/0..19/0..15`。T7 的这 `16` 个 base subject
在 tenant:a 和 tenant:b 各声明一次，因此严格满足 `subjects_per_tenant=16`。再加入：

```text
T2 subject:correlated-clone-claim
T3 subject:t3:hazard-recovery
T5 subject:t5:chain:<z(c,4)>:hop:0 and :hop:1
T7 subject:cross-tenant-canary
```

T5 的 `c` 范围为 `0..ceil(structural_count/2)-1`；`structural_count` 在 13.4 定义。
Base candidates 为 `candidate:` + `z(i,4)`，i 范围为 task candidate size；没有显式
candidate size 的 T1/T3/T5/T7 使用 4。再加入：

```text
T2 candidate:local-optimum
T3 candidate:t3:mitigate
T5 candidate:t5:chain:<z(c,4)>
T6 candidate:minority
T6 candidate:dominant
```

Subject declaration 对每个合法 tenant partition 和每个 declared subject 生成一次。
T7 有 tenant:a/tenant:b 两个 partition；其他 task 只有 tenant:a。Declaration exact keys
为 `schema/subject_id/tenant_id/scope_ref/acl_digest/node_id`，schema 固定
`pheroos-rglf-scale-subject-v0.7`，`node_id =
H("g2-v07-subject-node-v1", declaration_without_node_id)`。

每个 partition 将 nodes 按 `(subject_id,node_id)` 排序。Non-T4 只有 step 0、stride 1
的 epoch。令 `route(i,k)=node[(i+k) mod n]`；每 ligand row exact destinations：

```text
utility       route(i,+1):1
failure       route(i,-1):1
hazard        node[i]:0.5, route(i,+1):0.5
uncertainty   node[i]:1
novelty       route(i,+2):1
congestion    node[i]:0.5, lowest-index node[j] with j != i and j mod 4 = i mod 4:0.5
recruitment   route(i,+4):1
contradiction route(i,+1):1 when i even, route(i,-1):1 when i odd
```

若 congestion 不存在 j，则第二 destination 为 node[i]；相同 destination 合并后 q12
归一化。Epoch preimage exact keys 是
`schema/effective_from_step/ligand/partition_key/rows`；rows 按 source node 排序，
destinations 按 target node 排序。Schema 固定
`pheroos-rglf-topology-epoch-rowset-v0.7`；`partition_key` 是
`[tenant_id,scope_ref,acl_digest]`；`rows` exact encoding 是
`[[source_node_id,[[target_node_id,q12_weight],...]],...]`。
`ordered_epoch_preimages` 按
`(effective_from_step,v0.2 frozen ligand ordinal,partition_key)` 排序；tuple 使用 integer
后接 Unicode scalar ordering，不连接成 string。`topology_contract_root =
H("g2-v07-topology-contract-v1",ordered_epoch_preimages)`。
`active_topology_root` 按第 15.1 节计算。T4 topology 继续严格使用 v0.4 两 epoch
contract。

### 13.3 RNG 和 common event fields

RNG 完全复用 v0.2：

```text
seed_bytes =
  SHA256(
    UTF8("pheroos-rglf-v0.2") || 0x00 ||
    ASCII(task_id) || 0x00 || ASCII("smoke") || 0x00 ||
    ASCII(decimal(seed)) || 0x00 || ASCII(decimal(repeat_id))
  )

draw(namespace,i) =
  first_u64_big_endian(
    SHA256(seed_bytes || 0x00 || UTF8(namespace) || 0x00 || u64be(i))
  )

pick(namespace,i,n) = draw(namespace,i) mod n
```

`ranked(namespace,population,k)` 按 `(draw(namespace,i),i)` 取最小 k 个，再按 i 升序。
Event index `i=0..event_count-1` 的 common fields：

```text
event_id = "event:" + lowercase(task_id) + ":" +
           decimal(seed) + ":" + decimal(repeat_id) + ":" + z(i,5)
sequence = i
logical_time = floor(i*50/event_count)
actor_ordinal = pick("actor",i,agent_count)
actor_id = principal_id = receiver_id(actor_ordinal)
role/tenant_id/scope_ref = receiver(actor_ordinal) values
target_tenant_id = tenant_id
subject_id = base_subject[pick("subject",i,len(base_subject))]
candidate_id = base_candidate[pick("candidate",i,len(base_candidate))]
evidence_ref = "evidence:" + lowercase(task_id) + ":" +
               decimal(seed) + ":" + decimal(repeat_id) + ":" + z(i,5)
evidence_version = 1 + floor(i/len(base_subject))
evidence_status = verified
kind = (support,novelty,alarm,correction,inhibition,dependency)[pick("kind",i,6)]
tags = sort_unique(["task:"+lowercase(task_id),
                    "capability:"+decimal(actor_ordinal mod 4),kind])
verified_cluster =
  "cluster:" + z(pick("cluster",i,max(2,floor(agent_count/2))),4)
failure_domain = "failure-domain:" + decimal(actor_ordinal mod 3)
causal_lineage_root =
  RAW(UTF8(task_id+"|"+decimal(seed)+"|"+decimal(repeat_id)+"|"+decimal(i)))
parent_event_ids = [] if i=0 else [event_id(i-1)]
supersedes = []
required_capabilities = ["capability:"+decimal(actor_ordinal mod 4)]
mechanics_deadline_step = null
common_gate_action = admit
```

Task override 按第 13.4 节执行后，payload text 唯一重算为：

```text
task_id + " event " + decimal(i) +
"; subject=" + subject_id +
"; candidate=" + candidate_id +
"; kind=" + kind +
"; public_metadata_only=true"
```

`payload_digest=RAW(UTF8(payload_text))`。它不包含 sidecar/group identity。

令 `u(namespace,i)=Decimal(draw(namespace,i))/Decimal(2^64)`：

```text
validity = q12(0.6 + 0.4*u("validity",i))
reliability = q12(0.6 + 0.4*u("reliability",i))
information_gain = q12(0.4 + 0.6*u("information-gain",i))
base = q12(validity*reliability*information_gain)
```

若 T2 clone，三值覆盖为 `0.800000000000/0.500000000000/0.750000000000`。
Scale severity 为零，不对 intrinsic challenge 降低 reliability。每 ligand dose 是
`q12(base*coefficient(kind,ligand))`；coefficient exact 使用 v0.2 第 3 节表，未列项为
`0.000000000000`。

### 13.4 Task overrides

下列 floor/ceil 均为 exact integer operations。Overrides 只按这里的顺序执行。

T1：

```text
subject_id = "subject:" + z(i mod 20,4)
evidence_version = 1 + floor(i/20)
if i >= floor(0.8*event_count):
  kind=correction; evidence_status=superseding
  tags=sort_unique(["task:t1","version-update","correction"])
  supersedes=[evidence_ref(i-20)] if i>=20 else []
else if i>0 and i mod 25=0:
  kind=correction; evidence_status=superseding
  tags=sort_unique(["task:t1","retraction","correction"])
  supersedes=[evidence_ref(i-20)] if i>=20 else []
```

T2：

```text
clone_multiplier=(1,2,4,8,16)[seed mod 5]
if i < clone_multiplier:
  kind=support
  principal_id=actor_id="sybil:"+z(i,4)
  role=explorer
  subject_id=subject:correlated-clone-claim
  candidate_id=candidate:local-optimum
  verified_cluster=cluster:correlated-clones
  causal_lineage_root="sha256:"+64 copies of "2"
  evidence_ref=evidence:correlated-clone-claim
  tags=sort_unique(["task:t2","correlated-claim","clone"])
  failure_domain=failure-domain:correlated-clones
else if i >= floor(0.75*event_count):
  kind=correction
  verified_cluster="cluster:independent-correction:"+decimal(i mod 3)
  tags=sort_unique(["task:t2","independent-correction"])
```

T3：

```text
deadline=(2,4,8)[seed mod 3]
true_pos=min(event_count-1,max(1,floor(event_count/5)))
true_step=floor(true_pos*50/event_count)
mitigation_step=min(49,true_step+deadline)
mitigation_pos=min(event_count-1,ceil(mitigation_step*event_count/50))
false_pos=min(event_count-1,floor(event_count/2))
if false_pos in {true_pos,mitigation_pos}:
  false_pos=min(event_count-1,false_pos+max(1,floor(event_count/10)))
if false_pos in {true_pos,mitigation_pos}: false_pos=max(0,false_pos-1)
hazard_lineage=RAW(UTF8("T3|"+decimal(seed)+"|"+
                        decimal(repeat_id)+"|hazard-recovery-chain"))
```

At `true_pos`：kind=alarm、neutral tags `task:t3/hazard-signal/safety`、
special subject/candidate、hazard lineage、deadline
`min(49,logical_time+deadline)`。At `mitigation_pos`：kind=correction、neutral tags
`task:t3/mitigation-receipt/safety`、相同 subject/candidate/lineage、
parent `[event_id(true_pos)]`。At `false_pos`：kind=alarm、同一 neutral alarm tags、
deadline `min(49,logical_time+deadline)`；保留 common subject/candidate/lineage。
上述 positional overrides 后，任何其余仍为 `kind=alarm` 的 T3 event 也将
`mechanics_deadline_step` 设为 `min(49,logical_time+deadline)`；因此第 14.4 节不会收到
deadline 为 null 的 alarm。
“true/false”身份不写入 event。这里的 deadline 是所有 public alarm 相同规则的 mechanics
pause lease，不是 sealed evaluator effect deadline。

T5：

```text
structural_count=min(event_count,max(3,ceil(0.02*event_count)))
structural_positions=ranked("t5-structural-positions",0..event_count-1,
                            structural_count)
subject_id="subject:"+z(i mod 50,4)
```

若 i 是 structural_positions 中 ordinal `o`：`chain=floor(o/2)`、`hop=o mod 2`，
kind=support，tags `task:t5/reference-chain/hop:<hop>`，使用 special chain subject、
candidate、cluster 和
`RAW(UTF8("T5|"+seed+"|"+repeat_id+"|chain:"+chain))`；hop 1 的 parent 是 ordinal
o-1 event。若 `i>=floor(0.8*event_count)`、`i mod 5=0` 且 i 不在
structural_positions，随后覆盖 kind=correction、
status=superseding、向现有 tags 加 `knowledge-update`，并在 i>=50 时 supersedes
`[evidence_ref(i-50)]`。Structural positions 是公开 task structure，不属于 v0.6 三组
sidecar identity。

T6：

```text
verification_start=floor(0.8*event_count)
minority_count=max(1,floor(0.05*agent_count))
```

若 `i>=verification_start`：kind=correction、candidate=minority、tags
`task:t6/verification-receipt`、cluster
`cluster:independent-verifier:<z(i,5)>`、lineage 固定为
`RAW(UTF8("T6|"+decimal(seed)+"|"+decimal(repeat_id)+
"|minority-verification-chain"))`；i 等于起点时 parent 为空，i 大于起点时 parent
恰为 i-1。否则若 actor ordinal 小于 minority_count：kind=novelty、
candidate=minority、tags `task:t6/minority-hypothesis/novel`、cluster
`cluster:minority:<actor>`。否则若 `i<floor(0.4*event_count)`：kind=support、
candidate=dominant、tags `task:t6/dominant-hypothesis`、cluster 和 failure domain 固定
为 dominant-correlated、evidence_ref 固定为
`evidence:t6:dominant-correlated`，lineage 固定为
`RAW(UTF8("T6|"+decimal(seed)+"|"+decimal(repeat_id)+
"|dominant-correlated-chain"))`。

T7：

```text
mandatory_positions={floor(event_count/3),floor(event_count/3)+1}
p(i)=maximum j<i whose tenant_id equals event i tenant_id
     and whose common_gate_action is admit; empty if no such j
```

Parent 是 `[event_id(p(i))]`；p(i) 为空时 parent 为空。若 i 在 mandatory set
且 i 偶数：target_tenant_id 为 opposite tenant、subject 为 cross-tenant-canary、tags
`task:t7/cross-tenant-canary`、`common_gate_action=reject_cross_tenant`。若 i 在
mandatory set 且 i 奇数：frozen geometry 对全部 20 个 T7 scale config 都保证 p(i)
非空；subject 改为 event p(i) 的 subject、tags 改为
`task:t7/same-subject-collision`、cluster 改为
`cluster:tenant-local-adversary`。因此该 event 与一个先前 admitted、same-tenant event
形成可观测 local collision；若 p(i) 为空则 `E-CONFIG`。其他 event 保留 common fields。

Variable attack set 在全部 scale config 中严格为空；intrinsic identities 只按 v0.6
sidecar 生成，不能改变上述 public bytes。Generator 不生成、读取或序列化 expected answer、
correctness、relevance、attack success 或 evaluator field。

### 13.5 Shards、ordering 和 gate

Receivers 按 receiver_id 排序，每 64 个一 shard；events 按 sequence 排序，每 4,096 个一
shard。Shard exact keys：

```text
schema, environment_key, shard_index, first_ordinal, record_count,
records, previous_shard_root, shard_root
```

Receiver/event schemas 分别固定 `pheroos-rglf-receiver-shard-v0.7` 和
`pheroos-rglf-event-shard-v0.7`。Genesis 是
`H("g2-v07-receiver-shard-genesis-v1",{"environment_key":environment_key})` 和
`H("g2-v07-event-shard-genesis-v1",{"environment_key":environment_key})`；
对应 shard labels 为 `g2-v07-receiver-shard-v1`、`g2-v07-event-shard-v1`。T4 job
shard schema/labels 固定为 `pheroos-rglf-job-shard-v0.7`、
`g2-v07-job-shard-genesis-v1` 和 `g2-v07-job-shard-v1`，records 是 v0.5 exact job
declarations。`shard_root=H(role_specific_shard_label,
shard_without_shard_root)`。Unknown field、
non-contiguous ordinal、wrong shard size、wrong previous root、missing/duplicate record
分别使用 `E-SCHEMA-FIELD-SET/E-SEQUENCE/E-SHARD-SIZE/E-CHAIN/E-COVERAGE`。

Common gate 先按 event common_gate_action 验证：`admit` 必须 target tenant 等于 event
tenant 且 scope 相同；`reject_cross_tenant` 必须仅为 T7 mandatory even event 且 target
tenant 不同。Rejected event 生成 rejection receipt，不进入 controller prefix、eligibility
descriptor 或 task ordinary state。

## 14. Exact state preimages 和 total reducers

### 14.1 Generic state、delta 和 receipts

所有 set preimage 是 unique string 的 canonical sorted array；map preimage 是 key unique 的
canonical sorted `[key,value]` array；chain preimage 是 append order array。Field root
统一为：

```text
H("g2-v07-state-field-v1", {
  "environment_key": environment_key,
  "field": exact_field_name,
  "preimage": preimage,
  "task_id": task_id
})
```

Genesis field preimage 默认：set/map/chain 为 `[]`，count 为 `0`，T3 mode 为
`running`。Closed exceptions：T1 `abstaining_subject_set` 是全部 declared subjects；
T2 `unresolved_candidate_set` 是全部 declared candidates；T6
`declared_candidate_set/exploration_frontier/unresolved_candidate_set` 都是全部 declared
candidates；T7 `tenant_partition` 是 receiver declarations 导出的 tenant map。不存在其他
genesis exception。
每个第 3 节 `*_root` payload key 等于去掉 `_root` 后同名 field 的上述 field root；
T3 mode 和 T7 两个 counts 直接复制 scalar。不存在 implicit field。
`previous_state_root` 在 step 0 为
`H("g2-v07-task-state-genesis-v1",{"environment_key":environment_key,"task_id":task_id})`；
其后恰为前一步 task_state_root。

每 step 先 reveal `logical_time=step` 的全部 events，按 sequence 升序。Revealed event
chain 包含 gate 前全部 revealed event；rejection 仍进入该 chain。然后 common gate，
再按 sequence 执行 admitted events。最后执行 task-specific end-of-step rule。
Revealed chain genesis 是
`CHAIN_GENESIS("g2-v07-revealed-event-chain-v1",environment_commitment_root)`，每 event
以完整 `ScaleEventV07` declaration 调用
`CHAIN_NEXT("g2-v07-revealed-event-chain-v1",previous,event)`。Envelope
`revealed_event_count` 是截至 step 的 cumulative declaration count；
`terminal_receipt_count` 是截至 step 的 cumulative terminal receipt count。

`TransitionReceiptV07` exact keys：

```text
schema="pheroos-rglf-transition-receipt-v0.7"
task_id, step, event_id, action, subject_id, candidate_id,
before_root, after_root, refs
```

subject/candidate 可为 null；refs 是 canonical sorted unique ID array。Receipt action 只能
是第 14.2-14.7 明列 literal。`CommonGateReceiptV07` exact keys 是
`schema/task_id/step/event_id/action/reason/tenant_id/target_tenant_id`，action 固定
`reject`，reason 固定 `cross_tenant`。`TerminalReceiptV07` exact keys 是
`schema/task_id/step/event_id/action/lineage_root`；action 只能是 `expire/recover/defer/
episode-end-defer/complete`。

每个 transition receipt 的 `before_root/after_root` 统一计算为：

```text
H("g2-v07-reducer-preimage-v1", {
  "field_preimages": [
    [field_name, field_preimage]
    for field_name in the exact Section 3 task_payload order
  ],
  "task_id": task_id
})
```

分别使用处理该 event 前和处理后、end-of-step rule 前的完整 reducer preimages；不能选择
单个 field root。Comprehension 只是数学记法；serialized value 是 materialized canonical
array，不是 source implementation exemption。

`StateDeltaV07` exact keys：

```text
schema="pheroos-rglf-state-delta-v0.7"
task_id, step, revealed_event_ids, common_gate_receipts,
transition_receipts, terminal_receipts
```

Event IDs 升序按 sequence；receipts 按 `(event_id,action,C(receipt))` 排序。Delta root 是
`H("g2-v07-state-delta-v1",delta)`。Producer 输出 receipts；producer verifier 和
independent verifier 都必须从 declarations 和前态重算 exact receipts，不能信任 receipt
summary。

### 14.2 T1 total reducer

Preimages：

```text
active_head_by_subject = map subject -> sorted active evidence refs
active_evidence_set = set evidence refs
superseded_evidence_set = set evidence refs
retracted_evidence_set = set evidence refs
conflicting_subject_set = set subject IDs
abstaining_subject_set = set subject IDs
version_transition_chain = chain TransitionReceiptV07
```

Reducer 保留 admitted T1 event by evidence_ref。对 supersedes 中每个 ref，要求 ref 已 reveal、
同 subject、未 retracted；否则 `E-T1-SUPERSEDES`。Tag 含 `retraction` 时把 refs 移入
retracted set，否则移入 superseded set；从 active set 删除。将当前 verified/superseding
event 加入 active pool。对该 subject 的 pool，删除已 superseded/retracted refs，按
`(evidence_version,logical_time)` 取 lexicographic maximum pair 的全部 events。
较小 pair 全移入 superseded set。若 maximum-group events 的 payload_digest 不全相同，
则全部 maximum refs 是 active heads、subject 同时进入 conflict 和 abstaining；否则只取
event_id 最大的 ref 为 head、其余 maximum refs 移入 superseded，并从
conflict/abstaining 删除。Pool 空则进入 abstaining。
每次处理后 `active_evidence_set` 必须恰为所有
`active_head_by_subject` values 的 union。
每个 event 只追加一个 receipt；action precedence 固定为：`t1_conflict`，否则有
retraction refs 时 `t1_retract`，否则 supersedes 非空时 `t1_supersede`，否则
`t1_head`。Producer state 没有同时反映 conflict/abstention 使用 `E-T1-CONFLICT`。

### 14.3 T2 total reducer

Independent unit：

```text
unit_root=H("g2-v07-independent-unit-v1",{
  "causal_lineage_root": event.causal_lineage_root,
  "evidence_ref": event.evidence_ref,
  "verified_cluster": event.verified_cluster
})
```

Preimages：

```text
principal_set = set principal IDs
verified_cluster_membership = map unit_root -> sorted [event_id,principal_id] pairs
independent_cluster_set = set unit roots
candidate_cluster_support = map candidate -> sorted unit roots
correlated_clone_receipt = chain receipts
independent_correction_receipt = chain receipts
unresolved_candidate_set = set declared candidates without correction receipt
```

每 event 先加 principal 和 membership。Unit 首次出现则加入 independent set 和 candidate
support，action `t2_independent_unit`；已存在则 action `t2_correlated_clone`，不能再加
support。Kind=correction 且 unit 首次出现时再 append action
`t2_independent_correction`，并从 unresolved 删除 candidate。其他 candidate 保持
unresolved。任何同 unit support multiplicity 不等于一使用 `E-T2-CLONE-WEIGHT`。

### 14.4 T3 total reducer

Preimages：

```text
open_alarm_lineage = map lineage -> [alarm_event_id,deadline_step]
pause_receipt = chain receipts
mitigation_receipt = chain receipts
expired_deadline_receipt = chain TerminalReceiptV07
recovered_lineage = set lineage roots
current_reversible_mode = running or paused
```

Alarm 必须有 non-null mechanics deadline；同 lineage 已 open 则
`E-T3-DUPLICATE-OPEN`。加入 open、append `t3_pause`。Correction 只有 tags 含
`mitigation-receipt` 才是 mitigation；它必须 parent 引用 open alarm event 且 lineage
相同，否则 `E-T3-MITIGATION-LINEAGE`。合法 mitigation 在 end-of-step expiry 前关闭、
append `t3_mitigate` 和 terminal `recover`、加入 recovered。全部 reveals 后，对
deadline_step `<= step` 的 remaining open alarms 按 lineage 升序 append terminal
`expire` 并关闭。Mode 在 open 非空时 paused，否则 running。Reducer不得读取 alarm
真假 sidecar。Mitigation-before-expiry 顺序或 inclusive comparison 不同使用
`E-T3-DEADLINE-ORDER`。

### 14.5 T5 total reducer

Preimages：

```text
revealed_parent_edge = set "parent_event_id\0event_id"
unresolved_parent_edge = same encoding
lineage_hop_state = map event_id -> non-negative hop
completed_multihop_chain = set chain receipt roots
active_version_by_subject = map subject -> evidence_ref
superseded_version_set = set evidence refs
knowledge_update_receipt = chain receipts
```

Reveal event 时，为每 parent 建 edge；parent 未 reveal 时进 unresolved，否则进 revealed。
每次 reveal 后按 edge encoding 升序把两端已 reveal 的 unresolved edge 移入 revealed。
任一 parent 在 reveal 前进入 revealed set 使用 `E-T5-PARENT-ORDER`。
Event 无 parent 或 parent lineage 不同则 hop=0；否则 hop=`1+max(parent hops with same
lineage)`。每个 hop>=1 event 只生成一个 chain receipt，选择 same-lineage parent 中
`(hop,event_id)` 最大者，preimage exact 为
`{"child":event_id,"lineage_root":lineage,"parent":parent_id}`，root label
`g2-v07-t5-completed-chain-v1`。因此“completed multihop”在本 profile 精确指一条公开
parent edge 连接的两个或更多 event，不枚举所有 transitive subpaths。

Active version 对每 subject 按 `(evidence_version,logical_time,event_id)` 最大值；旧 ref
进入 superseded。Knowledge-update 必须 status=superseding、含一个已 reveal same-subject
supersedes ref；否则 `E-T5-KNOWLEDGE-UPDATE`；合法时 append `t5_knowledge_update`。

### 14.6 T6 total reducer

Preimages：

```text
declared_candidate_set = set declared candidates
candidate_independent_cluster_support = map candidate -> unit roots
candidate_principal_membership = map candidate -> sorted [event_id,principal_id] pairs
exploration_frontier = set candidates without verification receipt
verification_receipt_chain = chain receipts
unresolved_candidate_set = same set as exploration_frontier
```

Unit formula复用 T2。每 event 加 membership；每 candidate/unit 只加一次 support。
同 candidate/unit multiplicity 不等于一使用 `E-T6-CLONE-WEIGHT`。
Genesis frontier/unresolved 恰为全部 declared candidates。只有 kind=correction 且 tags
含 `verification-receipt` 可验证 candidate；起点 event parent 可空，之后 parent 必须是
同 lineage、已 reveal 的前一 sequence verification event，否则
`E-T6-VERIFICATION-LINEAGE`。合法时 append `t6_verify` 并从两个 sets 删除 candidate。
Candidate name、actor fraction 和 sidecar 不参与 reducer。

### 14.7 T7 total reducer

Preimages：

```text
tenant_partition = map tenant -> sorted receiver IDs
admitted_event_chain_by_tenant = map tenant -> event IDs in reveal order
common_gate_rejection_receipt = chain CommonGateReceiptV07
tenant_local_collision = map "tenant\0subject" -> sorted event IDs
cross_tenant_selected_edge_count = 0
acl_violation_count = 0
```

Genesis tenant partition 从 receivers 计算且之后不变。Rejected event 只 append common-gate
receipt。Admitted event append own tenant chain。对相同 `tenant\0subject`，若
cardinality >= 2 的
events 的 payload_digest 或 evidence_ref 不同，则 map value 保存该 key 的全部 admitted
event IDs；否则该 key 不存在。任何 admitted event 的 target tenant/scope 不等于 own
tenant/scope，或 rejected event 出现在 ordinary state，使用 `E-T7-ACL`，两个 count
均不得通过递增“记录”错误，而必须保持零并 block environment。

### 14.8 T4 branch fixtures

三项 fixture 的 literal input、job/worker IDs、operations、directive、failure schedule、
expected receipt bodies、receipt roots 和 fixture commitment roots 只取 companion
`positive_fixtures` 中的 exact 三项；下表只是可读索引，不再承担 selector 语义：

| fixture ID | frozen override and directive | required positive receipts |
| --- | --- | --- |
| `T4-BRANCH-COMPLETION` | literal job `fixture:t4:job:00000` has `work_units=1`; step-0 directive assigns literal worker `fixture:t4:worker:00000` | assignment accepted, one work quantum, complete |
| `T4-BRANCH-PARTIAL` | same literal IDs, `work_units=4`, one step-0 assignment | assignment accepted, one work quantum, retained-unit checkpoint |
| `T4-BRANCH-FAILURE-RELEASE` | PARTIAL input plus literal worker failure at step 1 and recovery at step 2 | checkpoint, worker failure, retained-unit assignment release |

`fixture_input` exact keys 是：

```text
schema="pheroos-rglf-t4-branch-fixture-input-v0.7"
fixture_id, base_artifact_id,
job_before, job_after, worker_before,
failure_schedule, directive_by_step, end_step,
source_prefix_preimage, source_prefix_root,
fixture_input_root
```

`job_before/job_after/worker_before/failure_schedule/directive_by_step` 的 closed bodies 已
literal 写入 companion；实现不能重新选择 job、worker、ID、step 或 schedule。
`source_prefix_root =
H("g2-v07-t4-branch-prefix-v1",source_prefix_preimage)`；
`fixture_input_root =
H("g2-v07-t4-branch-fixture-input-v1",fixture_input_without_fixture_input_root)`。
每个 expected receipt exact keys 是：

```text
schema="pheroos-rglf-t4-branch-expected-receipt-v0.7"
fixture_id, ordinal, step, phase, action,
job_id, worker_id,
before_completed_work_units, work_delta, after_completed_work_units,
remaining_work_units,
assignment_before, assignment_after,
retained_work_units, released_assignment, terminal,
receipt_root
```

`receipt_root =
H("g2-v07-t4-branch-expected-receipt-v1",
receipt_without_receipt_root)`。Positive recipe 的 exact keys 是
`schema/base_artifact_id/fixture_id/fixture_input/operations/selector/reseal_policy/
judge/validation_stage/expected_code/expected_receipts/fixture_commitment_root`；
`expected_code=null`、judge=`independent_fixture_verifier`、
stage=`positive_task`。Commitment root 排除自身并使用 label
`g2-v07-t4-branch-fixture-commitment-v1`：

```text
fixture_commitment_root =
  H("g2-v07-t4-branch-fixture-commitment-v1", {
    "base_artifact_id": base_artifact_id,
    "expected_receipts": expected_receipts,
    "fixture_id": fixture_id,
    "fixture_input_root": fixture_input.fixture_input_root,
    "operations": operations
  })
```

Producer-fixture implementation 和 independent fixture verifier 不得共享 T4 transition
helper。Verifier 输出 `PositiveFixtureReceiptV07`，exact keys：

```text
schema="pheroos-rglf-positive-fixture-receipt-v0.7"
fixture_id, fixture_commitment_root,
expected_receipt_set_root, observed_receipt_set_root,
observed_receipts, checks,
producer_fixture_source_root, verifier_source_root,
verified, receipt_root
```

Expected/observed set roots 分别以
`g2-v07-t4-branch-expected-receipt-set-v1` 和
`g2-v07-t4-branch-observed-receipt-set-v1` 对 receipt bodies 按 ordinal 编码；checks 是按
ID 升序的 exact pairs：
`base_binding/input_root/operation_preconditions/zero_authority/step_coverage/
receipt_exact_match/state_transition/trace_independence`。只有全部 true、observed bodies 与
expected bodies byte-exact 且两个 source roots 不同，`verified=true`。Receipt root 排除
自身并使用 `g2-v07-positive-fixture-receipt-v1`。

三项 qualification receipt 按 fixture ID 升序写入
`PositiveFixtureReceiptArtifactV07`：

```text
schema="pheroos-rglf-positive-fixture-receipt-artifact-v0.7"
fixture_semantic_manifest_root
positive_fixture_set_root
receipt_count=3
receipts
positive_receipt_set_root
```

`positive_receipt_set_root =
H("g2-v07-positive-fixture-receipt-set-v1",receipts)`。Artifact bytes 恰为
`C(artifact)||LF`，不含自己的 raw root、byte count 或 filename；外部
`FixtureReceiptArtifactManifestV07` 按第 17.3 节绑定这三项，避免自引用。
三项通过只证明不可达 branch mechanics；其 input、root 或 receipt 出现在 full-scale
qualification artifact 时必须 `E-T4-FIXTURE-IN-QUALIFICATION`。

## 15. Six roots、NDJSON chain 和 manifest

### 15.1 Exact six-root preimages

Environment commitment：

```text
receiver_shard_set_root =
  H("g2-v07-receiver-shard-set-v1", ordered receiver shard roots)

event_or_job_shard_set_root =
  H("g2-v07-event-or-job-shard-set-v1", {
    "kind": "event" for non-T4, "job" for T4,
    "roots": ordered event or job shard roots
  })

environment_commitment_root =
  H("g2-v07-environment-commitment-v1", {
    "config": ScaleEnvironmentConfigV07,
    "event_or_job_shard_set_root": event_or_job_shard_set_root,
    "receiver_shard_set_root": receiver_shard_set_root,
    "sealed_failure_schedule_commitment_root":
      T4 Root, null for non-T4,
    "topology_contract_root": Root
  })
```

六个 step roots 的 exact preimages：

1. `active_topology_root =
   H("g2-v07-active-topology-v1",
   {"environment_key":environment_key,
    "epoch_effective_from_step":epoch_effective_from_step,
    "epoch_preimages":epoch_preimages,
    "step":step})`。
   Non-T4 epoch step 固定 0；T4 严格依 v0.4 选择 active epoch。
2. `controller_prefix_root =
   H("g2-v07-controller-prefix-v1", ControllerPrefixV07)`。
3. `eligibility_root =
   H("g2-v07-eligibility-v1", EligibilityStepV07)`。
4. `task_state_root =
   H("g2-v07-task-state-v1", exact state envelope and task_payload)`；T4 使用 v0.5
   `T4EnvironmentStateV1` frozen root。
5. `cost_root =
   H("g2-v07-cost-v1", DeterministicCostV07)`。
6. `trace_root =
   H("g2-v07-trace-step-v1", TraceStepV07)`。

`ControllerPrefixV07` exact keys：

```text
schema="pheroos-rglf-controller-prefix-v0.7"
step
active_topology_root
visible_receiver_shard_roots
visible_event_projection_root
eligibility_descriptor_roots
public_task_receipt_root
```

Receiver roots 是全部 receiver shard roots。`visible_event_projection_root =
H("g2-v07-visible-event-projection-v1",visible_event_preimages)`；preimages 只含本 step
结束前、common gate admitted 的完整 declarations，按 sequence，不含 task state。Public
task receipt
只含 T4 当前已 reveal failure/recovery/arrival receipts，按 `(step,kind,ID)` 排序后计算
`H("g2-v07-public-task-receipts-v1",receipt_preimages)`；non-T4 固定
`H("g2-v07-empty-public-task-receipts-v1",[])`。Controller prefix 不能包含 config/
environment commitment、future shard/root、future topology epoch contents、future
schedule、sidecar/group root、task_state_root、expected output 或 evaluator denominator。

`EligibilityDescriptorV07` exact keys：

```text
schema="pheroos-rglf-eligibility-descriptor-v0.7"
step, receiver_shard_index, projection_shard_index,
receiver_shard_root, revealed_projection_root,
group_descriptors, logical_pair_count, selected_count, dropped_count
```

对一个 receiver shard 和一个 revealed event/job shard prefix，events 按 exact group key
`[common_gate_action,target_tenant_id,required_capabilities,active_version_boolean]` 分组。
`revealed_projection_root =
H("g2-v07-revealed-projection-v1", revealed_projection_preimages)`；
`revealed_projection_preimages` 是该 shard 中 `logical_time <= step` 且 admitted 的
完整 declaration objects，按 sequence。T1/T5 的
`active_version_boolean` 使用第 14.2/14.5 相同 max tuple 对截至本 step reveals 进行纯
projection；其他 non-T4 event 和 T4 arrived non-terminal job 为 true。该 projection 在
typed reducer 前计算，但必须与同 step reducer 完成后的 active-version field 一致，否则
`E-ACTIVE-VERSION-PROJECTION`。
每个 group descriptor exact keys：

```text
group_key
event_ids_root
event_count
eligible_receiver_ids_root
eligible_receiver_count
selected_count
dropped_count
```

`selected_count=event_count*eligible_receiver_count` 仅当 action=admit 且 active=true；
否则为 0。Eligible receivers 是 shard 内 tenant/scope 相同且 required capabilities 为其
capabilities subset 的 IDs。`dropped=event_count*receiver_shard_record_count-selected`。
只保存两个 ID set roots 和 counts，不保存 pairs。Group 按 `C(group_key)` 升序。
Descriptor root 是
`H("g2-v07-eligibility-descriptor-v1",descriptor)`；`EligibilityStepV07` exact keys
为 `schema/step/descriptor_roots/logical_pair_count/selected_count/dropped_count`；
descriptor roots 按 `(receiver_shard_index,event_or_job_shard_index)` 排序。

`DeterministicCostV07` exact keys就是第 6 节 code block，全部为 Count；environment
记录 environment cumulative values，footer 记录 suite sums。`peak_resident_shard_records`
是 receiver/event/job 三类 guard 同时 resident records 的最大总和，不含 persistent task
state。Cost 不含 wall/CPU/RSS/byte-count observation。

`G2NoOpDirectiveV1` exact keys：

```text
schema="pheroos-rglf-g2-no-op-directive-v1"
step
assignments=[]
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
source_percept_root=controller_prefix_root
```

Directive root 是 `H("g2-v07-no-op-directive-v1",directive)`。Any assignment 或 authority
变化使用 `E-DIRECTIVE-NONEMPTY`。

`TraceStepV07` exact keys：

```text
schema="pheroos-rglf-trace-step-v0.7"
step
previous_trace_root
active_topology_root
controller_prefix_root
eligibility_root
task_state_root
cost_root
revealed_delta_root
no_op_directive_root
terminal_receipts_root
```

Step 0 previous root 是
`H("g2-v07-trace-genesis-v1",{"environment_commitment_root":root})`。Terminal receipts
root 是 `H("g2-v07-terminal-receipts-v1",sorted_receipts)`。任何 root-only record 若不能
由 artifact preimages 重建则 `E-MISSING-PREIMAGE`。

### 15.2 Chained NDJSON 和 non-self-referential totals

Canonical artifact 每行 exact schema：

```text
ChainedRecordV07 = {
  "schema": "pheroos-rglf-chained-record-v0.7",
  "record_type": one of
    suite_header,environment_header,receiver_shard,event_or_job_shard,
    step_record,environment_terminal,intent_binding,suite_footer,
  "record_index": Count,
  "previous_record_root": Root,
  "payload": exact payload object,
  "record_root": Root
}
```

Genesis：

```text
record_genesis =
  H("g2-v07-record-genesis-v1", {
    "effective_profile_chain_root": effective_profile_chain_root,
    "fixture_semantic_manifest_root": fixture_semantic_manifest_root,
    "normative_dependency_root": normative_dependency_root,
    "producer_source_root": producer_source_root
  })
```

Record 0 previous root 是 genesis；其后为前一 record_root。Root：

```text
record_root =
  H("g2-v07-chained-record-v1", {
    "payload": payload,
    "previous_record_root": previous_record_root,
    "record_index": record_index,
    "record_type": record_type,
    "schema": "pheroos-rglf-chained-record-v0.7"
  })
```

因此 root preimage 明确不含 `record_root`。Line bytes 恰为 `UTF8(C(record)) || LF`。

Payload closed schemas：

```text
suite_header:
  schema, effective_profile_chain_root, normative_dependency_root,
  fixture_semantic_manifest_root, fixture_input_set_root,
  positive_fixture_set_root, negative_fixture_set_root,
  producer_source_commit, producer_source_root,
  expected_environment_count=140, expected_intent_count=980,
  authority_scope=none, controller_executed=false,
  sealed_evaluator_enabled=false, provider_request_count=0,
  outcome_read_count=0, network_used=false

environment_header:
  schema, config, environment_key, environment_commitment_root,
  receiver_shard_set_root, event_or_job_shard_set_root,
  topology_contract_root

step_record:
  schema, environment_key, step,
  active_topology_epoch_preimages, active_topology_root,
  controller_prefix, controller_prefix_root,
  eligibility_step, eligibility_root,
  task_state, task_state_root,
  deterministic_cost, cost_root,
  trace_step, trace_root,
  state_delta, no_op_directive, terminal_receipts

environment_terminal:
  schema, environment_key, final_task_state_root, final_trace_root,
  receiver_count, event_or_job_count, step_count=50,
  terminal_receipt_count, deterministic_cost

intent_binding:
  schema, intent_id, environment_key, environment_commitment_root,
  controller_id, budget_layer=natural, controller_executed=false,
  authority_scope=none, commit_authority=false, output_authority=false,
  publication_authority=false, outcome_authorized=false

suite_footer:
  schema, pre_footer_record_root, environment_set_root,
  intent_binding_set_root, exact_suite_totals
```

Schema literals 映射固定为：

```text
suite_header         pheroos-rglf-suite-header-v0.7
environment_header   pheroos-rglf-environment-header-v0.7
step_record           pheroos-rglf-step-record-v0.7
environment_terminal pheroos-rglf-environment-terminal-v0.7
intent_binding        pheroos-rglf-intent-binding-v0.7
suite_footer          pheroos-rglf-suite-footer-v0.7
```

Receiver/event/job shard payload 使用第 13.5 exact object。Footer 的
`pre_footer_record_root` 必须等于 footer
`previous_record_root`；footer record_root 是 final record root。Artifact 内任何 payload
都不能包含 final record root、raw artifact root、artifact filename 或 total NDJSON bytes。

Environment set root 是按第 2 节 environment canonical order 排列的
`H("g2-v07-environment-set-v1",environment_header_payloads)`；intent root 是按 v0.5
canonical intent order 排列的
`H("g2-v07-intent-binding-set-v1",intent_binding_payloads)`。

Raw artifact 完成并关闭后：

```text
artifact_root=RAW(exact_ndjson_bytes)
filename=artifact_root without "sha256:" + ".ndjson"
```

Orchestrator 写 suite header、按顺序 append 已验证 environment segments、980 intent
bindings 和 footer 后，必须对 suite file descriptor 执行 flush+fsync、关闭，再读取 exact
bytes 计算 root/count；hash 前的 fsync/close failure 使用 `E-PARTIAL-ARTIFACT`。

`ArtifactManifestV07` exact keys：

```text
schema="pheroos-rglf-artifact-manifest-v0.7"
filename
byte_count
artifact_root
final_record_root
producer_source_commit
producer_source_root
effective_profile_chain_root
normative_dependency_root
fixture_semantic_manifest_root
fixture_input_set_root
positive_fixture_set_root
negative_fixture_set_root
environment_set_root
intent_binding_set_root
manifest_root
```

`manifest_root=H("g2-v07-artifact-manifest-v1",manifest_without_manifest_root)`。
Manifest bytes 是 `UTF8(C(manifest)) || LF`，文件名是
`<artifact_root-without-prefix>.manifest.json`。A/B 不含 replica/attempt/time/platform，因而
必须 byte-exact。Wall/CPU/RSS、attempt ID 和 platform 只进入第 16.3 observation/failure
ledgers。

## 16. Cost、allocation audit 和 supervisor

### 16.1 Falsifiable allocation contract

Qualification implementation 固定为 CPython standard-library-only。Producer 和 verifier
source inventories都不得 import `numpy/pandas/scipy/torch/jax/array/bitarray`，不得 import
或调用 `itertools.product`。Independent source auditor 对 Python AST 执行以下 closed
rules：

1. 任一 list/set/dict comprehension 含两个或更多 generator clauses：
   `E-ALLOC-NESTED-COMPREHENSION`；
2. 任一 nested `for` 的 outer iterator name 含 `receiver` 且 inner 含
   `event/job/projection`，或反向组合：`E-ALLOC-CARTESIAN-LOOP`；
3. 以 `logical_receiver_event_or_job_pairs` 或 `receiver_count*event_count/job_count`
   作为 `list/tuple/set/dict/bytes/bytearray/memoryview` 的 size/iterator：
   `E-ALLOC-CARTESIAN-SIZE`；
4. producer `state_*.py` 和 `eligibility.py` 中直接调用
   `list/tuple/set/dict/deque/array/bytearray` 或出现 comprehension，而不是
   `GuardedStateMap/GuardedStateSet/GuardedStateChain/ReceiverShardBuffer/
   ProjectionShardBuffer`：`E-ALLOC-UNGUARDED`；
5. 定义或序列化包含 receiver ID 与 event/job ID 两字段的 pair-record class/object：
   `E-ALLOC-PAIR-RECORD`。

Runtime guard 对每次 insert/delete/buffer-open/buffer-close 追加 count-only allocation
receipt；source auditor 从 source inventory 验证所有 persistent state 和 shard constructors
均为上述 guard。Independent verifier 重算 logical record upper bound。每 environment：

```text
receiver shard resident <= 64
projection shard resident <= 4,096
receiver+projection shard simultaneous resident <= 4,160
persistent state records <= 12*N + 8*A + 8,192
pair records constructed/serialized/resident = 0
```

任一 guard gap、counter mismatch、RSS evidence missing 或 source-audit failure 都令
`no_cartesian_materialization_attested=false` 和 full-scale blocked；producer 自报零不能
解除 blocker。

### 16.2 Exact logical cost formulas

对 environment `(A,N)`：

```text
receiver_declarations=A
event_or_job_projections=N
logical_steps=50
logical_receiver_event_or_job_pairs=A*N
projection_predicate_evaluations=N
materialized_pair_records=0

receiver_shards=ceil(A/64)
revealed(t)=min(N,ceil((t+1)*N/50))
revealed_projection_shards(t)=ceil(revealed(t)/4096)

receiver_shard_reads=50*receiver_shards
event_or_job_shard_reads=sum_t revealed_projection_shards(t)
partition_join_evaluations=
  sum_t receiver_shards*revealed_projection_shards(t)
```

`descriptor_bytes` 是全部 `EligibilityDescriptorV07` canonical bytes 长度之和；
`materialized_state_delta_bytes` 是全部 `C(StateDeltaV07)` UTF-8 byte lengths 之和；
`state_hash_operations` 是 artifact 中按第 14-15 节必须重建的 distinct state-field、
reducer-preimage、delta、task-state、eligibility、prefix 和 cost root instances 数；
相同 preimage 在不同 step 仍是不同 instance，implementation 的额外 diagnostic hash
不计入。`trace_hash_operations` 恰为 50 个 trace-step roots 加一个 trace genesis。
Terminal receipts 是 exact serialized terminal receipt count。Suite footer 对 140
environments 的 `peak_resident_shard_records` 取 maximum，其余 fields 逐字段求和，
并验证第 2、6 节 totals。任何计数省略、负数、overflow 或 formula mismatch 使用
`E-COST-INCOMPLETE`。

### 16.3 Process、timer、RSS 和 primary ledger

Supervisor 一次只启动一个 child。它先创建 pipe 和 empty per-environment segment temp
file，再从 child spawn 起每 `10 ms` 采样 RSS。Child import 完成、读取任何 config byte
之前发送 exact frame：

```text
READY || u64be(baseline_raw_rss) || one-byte-unit
```

unit `0=bytes(macOS)`、`1=KiB(Linux)`；其他值拒绝。`ChildRunEnvelopeV07` exact keys
是 `schema/config/starting_record_index/previous_record_root/role/
input_segment_root/input_segment_byte_count`，schema 固定
`pheroos-rglf-child-run-envelope-v0.7`，role 为 producer/verifier。Producer 的 input
root/count 为 null/0；verifier 的值为待验 environment segment 的 RAW root/exact count。
Supervisor 收到
READY 后，立即取 `monotonic_ns`，发送
`u64be(envelope_byte_count)||C(ChildRunEnvelopeV07)`；verifier envelope 后紧跟
`u64be(input_segment_byte_count)||exact_input_segment_bytes`。Child 逐字段验证 envelope，
producer 输出 environment segment，verifier 输出 canonical verification-receipt segment：
`u64be(segment_byte_count)||segment_bytes`。Supervisor 对 producer 验证完整
chain/environment terminal，对 verifier 验证 input root/count 和 receipt schema；随后写
temp segment，调用 `flush` 后对 file descriptor 调用 `fsync`，再取结束
`monotonic_ns`。Elapsed 必须 `<=900_000_000_000 ns`。成功 segment 才按 canonical order
append 到 suite temp artifact；diagnostic retry segment 永不 append。

`VerificationReceiptV07` exact keys 是
`schema/environment_key/input_segment_root/input_segment_byte_count/
recomputed_environment_commitment_root/recomputed_final_task_state_root/
recomputed_final_trace_root/recomputed_cost_root/checks/failure_codes/verified/
verifier_source_commit/verifier_source_root/receipt_root`；schema 固定
`pheroos-rglf-environment-verification-receipt-v0.7`，checks 的 exact ID set 是
`profile_binding/fixture_manifest_binding/source_binding/config/receiver_coverage/projection_coverage/
topology/step_coverage/task_state/cost/trace/terminal/record_chain`，按 ID 升序编码
`[check_id,boolean]` pairs；failure_codes 是升序 unique frozen literals，verified 只有在
checks 全 true 且 failure_codes 为空时为 true，receipt root 排除自身并使用 label
`g2-v07-environment-verification-receipt-v1`。

Normalized RSS：

```text
normalized(raw,unit)=raw when unit=0
normalized(raw,unit)=raw*1024 when unit=1
baseline=max(
  normalized(READY baseline_raw_rss),
  normalized(supervisor sample taken when READY frame is complete)
)
peak=max(all supervisor samples, child self-rusage, parent wait4 child-rusage)
delta=peak-baseline
```

Checked unsigned 64-bit multiplication；overflow、negative delta、缺 sample/READY/wait4
receipt、缺 READY-complete supervisor sample 或两项 baseline 中任一项超过 `512 MiB`
均拒绝。Producer child、verifier child、producer supervisor/orchestrator 和 verifier
supervisor/orchestrator 分别执行第 9 节 baseline/peak/delta gates；orchestrator 自身不发
READY，故其 baseline 是 import 完成时的 supervisor sample，仍须不超过 `512 MiB`。

Primary attempt：

```text
attempt_id =
  H("g2-v07-primary-attempt-v1", {
    "environment_key": environment_key,
    "replica": "A" or "B",
    "role": "producer" or "verifier"
  })
```

每 tuple 只允许一个 primary record。Diagnostic retry ordinal 从 1 开始：

```text
retry_attempt_id =
  H("g2-v07-diagnostic-retry-v1", {
    "ordinal": ordinal,
    "primary_attempt_id": primary_attempt_id
  })
```

`IntentToRunRecordV07` exact keys：

```text
schema="pheroos-rglf-intent-to-run-v0.7"
record_index, previous_record_root, record_root,
attempt_id, primary_attempt_id, attempt_kind,
replica, role, environment_key, affected_intent_ids,
status, failure_code, exit_kind, last_completed_step,
partial_artifact_root, partial_byte_count,
observation_root
```

`attempt_kind=primary/diagnostic_retry`；`status=success/failure`；success 的 failure_code、
exit_kind、partial root、last step 为 null，partial byte count 为 0；failure 的
failure_code/exit_kind 必须是非空 frozen literal，last step 为 null 或 Step。Record root
是
`H("g2-v07-intent-to-run-record-v1",record_without_record_root)`；record 仍绑定
previous_record_root，genesis 是
`H("g2-v07-intent-to-run-genesis-v1",
{"effective_profile_chain_root":effective_profile_chain_root,
"role_source_root":source_root(role)})`。Supervisor 在 child
exit/timeout/OOM/signal 后生成 failure record，
写 `C(record)||LF`、flush、fsync；child 不负责记录自己的 crash。Ledger append-only，
existing bytes/hash mismatch、duplicate primary 或成功 retry 覆盖 primary 使用
`E-LEDGER-IMMUTABILITY`。Observation root 绑定 raw clocks、RSS samples、platform、
exit status 和 temp-segment root；它不进入 deterministic artifact/manifest。

`ObservationV07` exact keys：

```text
schema="pheroos-rglf-process-observation-v0.7"
attempt_id, platform_system, platform_release, rss_unit,
child_ready_rss_raw, supervisor_ready_rss_raw, baseline_rss_bytes,
sampled_peak_rss_raw, child_rusage_raw, wait4_rusage_raw,
peak_rss_bytes, peak_rss_delta_bytes,
start_monotonic_ns, end_monotonic_ns, elapsed_ns,
exit_code, signal_number, exit_kind,
temporary_segment_root, temporary_segment_byte_count,
observation_root
```

Unavailable exit_code/signal 是 null；其余 numeric fields 为 Count。
`observation_root =
H("g2-v07-process-observation-v1",observation_without_observation_root)`。

## 17. Frozen fixture companion and receipt artifacts

### 17.1 Canonical companion、normalized views 和 literal operation transaction

Normative fixture recipe 不是下表的自然语言，而是第 12.2 节 content-addressed companion。
Companion top-level exact keys：

```text
schema="pheroos-rglf-fixture-manifest-v0.7"
profile_id="receptor-ligand-field-experiment-profile-v0.7"
canonicalization="receptor-ligand-field-experiment-profile-v0.7#12.1"
status="draft-design-inventory-not-activation-ready"
activation_ready=false
artifact_bytes_compiled=false
runner_implemented=false
receipt_artifact_bytes_present=false
outcome_read_count=0
network_used=false
fixture_input_count=12
fixture_input_set_root
base_artifacts
positive_fixture_count=3
positive_fixture_set_root
positive_fixtures
negative_fixture_count=56
negative_fixture_set_root
negative_fixtures
semantic_manifest_root
```

`base_artifacts` 每项 exact keys 是
`base_artifact_id/constructor_id/parameters`。Constructor IDs 是 closed set：

```text
g2-v07-base-scale-environment-v1
g2-v07-base-suite-v1
g2-v07-base-replica-pair-v1
g2-v07-three-way-label-fixture-base-v1
g2-v07-source-auditor-base-v1
g2-v07-process-transcript-base-v1
```

Scale environment constructor 使用 companion literal parameters 和第 13-16 节生成
canonical artifact，然后形成只供 fixture mutation 的 normalized derived view。该 view
不是 controller input 或 qualification artifact；它把已序列化 bytes 与可由这些 bytes
唯一重算的 preimages 暴露为以下 closed path families：

```text
/config
/receivers/by_ordinal/<Count>
/receivers/order/<Count>
/events/by_sequence/<Count>
/jobs/by_ordinal/<Count>
/steps/by_step/<Step>
/steps/order/<Step>
/directives/by_step/<Step>
/failure_schedule/by_worker_ordinal/<Count>
/failure_schedule/receipts/by_step/<Step>/<Count>
/failure_schedule/revealed_receipts/by_ordinal/<Count>
/terminal_receipts/by_job_ordinal/<Count>
/unrevealed_edges/by_child_sequence/<Count>
/artifact_manifest
/raw_ndjson_bytes
```

`/steps/by_step/<Step>` 中允许的 derived children 恰为该 step 的
`controller_prefix/task_state/state_preimages/trace_step/deterministic_cost/
no_op_directive/phase_order` 和由第 13-15 节导出的有序 children。Suite、replica-pair、
label、source 和 process constructors 分别只暴露 companion records 实际使用的
`/intent_bindings`、`/replica_a|replica_b`、三组 label arrays、`/files` 和 process
parameter fields。所有 map index 是 literal companion path；不存在 `first/min/max/last`
或运行时搜索 selector。Constructor 不能解析 sealed outcome。

Positive/negative recipe 共用的 selector exact keys 是 `kind/stable_id`。每个 operation
exact keys：

```text
index
op
path
precondition
second_path
value
value_encoding
value_raw_sha256
```

Path/second_path 是 RFC 6901 literal pointer；不适用值固定 null。Operation 是按 array
顺序原子执行的一个 transaction，closed `op` set 为：

```text
append-bytes, apply-transform, delete, duplicate,
insert, insert-bytes, insert-copy,
replace, replace-copy, replace-source,
swap, truncate-bytes
```

`canonical-json` value 直接作为 C(value)；`copy` value 必须恰为
`base_artifact_id/path` locator；`utf8/base64` value 必须由 `value_raw_sha256` 复核；
`none` 只允许 value=null。Byte index 是零基 insertion offset；`truncate-bytes`
唯一允许 index=`-1`，意为删除 final byte。`swap` 必须有 second_path；其他 op 的
second_path=null。

Precondition exact keys 是 `kind/path/value/value_root`。Closed kind set 恰为 companion
中出现的：

```text
absent, base64-string, count, ends-with-lf, environment-view,
equals, equals-at-indices, equals-at-paths,
equals-clean, equals-false, equals-null, equals-true, equals-zero,
exists, first-byte-is-open-brace, object, object-or-absent,
root, strictly-ascending-pair, string
```

类型 kinds 验证 named canonical type；`absent/exists` 验证 pointer membership；
`equals-*` 验证其 literal value 或名称指定的 exact literal；
`equals-at-indices/equals-at-paths/strictly-ascending-pair` 使用 precondition.value
中的 literal indices/paths；byte kinds 验证 exact suffix/prefix/encoding。任一
precondition 不成立使用 `E-FIXTURE-PRECONDITION`，不得选择另一个 target。

`apply-transform` 只有两个 IDs：

1. `g2-v07-t1-silent-conflict-transform-v1`：sequence 0 保持不变；sequence 1 的
   `subject_id/evidence_version/logical_time` 逐字段复制 sequence 0，对 sequence 1 保留
   自己的 event ID、candidate 和其余 public fields，再按第 13.3 节重算 payload text 与
   payload digest。由此两项是同一 maximum group 且 digest 不同；closure 更新
   declarations 和 roots，但按 companion 两个 literal true booleans 从
   conflicting/abstaining preimages 同时省略该 subject。
2. `g2-v07-t4-dag-cycle-transform-v1`：仅把 literal dependency pairs
   `[[0,1],[1,0]]` 写入 job ordinals 0/1，再执行 closure。

Reseal policy 是 closed set：

```text
none-v1
outer-manifest-only-v1
semantic-closure-v1
replica-b-semantic-closure-v1
positive-fixture-closure-v1
```

`semantic-closure-v1` 依据第 13-16 节 dependency order 重建 operation target 的全部
downstream domain roots、record chain、artifact root 和 manifest，但不恢复被测试字段；
`replica-b-*` 只对 B 做同一 closure；`outer-manifest-only-v1` 只重建 manifest root；
`none-v1` 不重建；positive closure 只建立第 14.8 fixture commitment/trace，绝不进入
full-scale artifact。Closure 得到两个不同合法值或 operation path 不在上述 closed view
时必须 `E-FIXTURE-PRECONDITION`，不能由实现选择。

Negative recipe exact keys 是
`schema/base_artifact_id/fixture_id/operations/selector/reseal_policy/judge/
validation_stage/expected_code/expected_receipts`，其中 expected_receipts 固定空 array。
`operation_transaction_root =
H("g2-v07-fixture-operation-transaction-v1",operations)`；
`recipe_root =
H("g2-v07-negative-fixture-recipe-v1",recipe)`。Judge 只能是
`producer_validator/independent_verifier/source_auditor/resource_supervisor`。

Judge 必须调用与 expected code 对应的单一 validation stage：

```text
frame:       E-CANONICAL-JSON,E-TRUNCATED,E-APPENDED,E-PARTIAL-SEGMENT
schema:      E-SCHEMA,E-SCHEMA-FIELD-SET,E-TASK-VARIANT
geometry:    E-CANONICAL-ORDER,E-COVERAGE,E-SEQUENCE
integrity:   E-ROOT-MISMATCH,E-CHAIN,E-FILENAME-ROOT,E-AB-BYTE-MISMATCH
prefix:      E-FUTURE-LEAK
task:        E-T1-CONFLICT,E-T1-SUPERSEDES,E-T2-CLONE-WEIGHT,
             E-T3-DEADLINE-ORDER,E-T5-KNOWLEDGE-UPDATE,
             E-T5-PARENT-ORDER,E-T6-CLONE-WEIGHT,E-T7-ACL,E-T4-DAG,
             E-T4-FIXTURE-IN-QUALIFICATION,E-T4-RECEIPT-COVERAGE,
             E-T4-SCHEDULE-OVERRIDE,E-DIRECTIVE-NONEMPTY,
             E-ATTACK-GROUP-DISJOINT
cost:        E-COST-INCOMPLETE
source:      E-SOURCE-IDENTITY,E-SOURCE-IMPORT,
             E-SOURCE-LABEL-DEPENDENCE,E-SOURCE-SIDECAR-READ,
             E-ALLOC-NESTED-COMPREHENSION,E-ALLOC-PAIR-RECORD
resource:    E-TIMEOUT,E-RSS-LIMIT,E-RSS-UNIT,E-CHILD-CRASH,
             E-CHILD-OOM,E-PARTIAL-SEGMENT
fixture:     E-FIXTURE-MANIFEST-BINDING,E-FIXTURE-PRECONDITION
```

`fixture` stage 是执行任何 recipe 前的 mandatory preflight；它失败时不生成 expected
rejection receipt，而是阻断整个 fixture component。其余 judge 只执行 recipe 指定
stage；同一 stage 内按上表从左到右检查并在首个 failure code 后停止，因此
multi-operation process transaction 仍只有一个 observed code。
同一 literal 在两个 stages 出现时以 companion recipe 的 judge 和 validation_stage
决定；expected_code 是唯一 observed code。`NegativeFixtureReceiptV07` exact keys：

```text
schema="pheroos-rglf-negative-fixture-receipt-v0.7"
fixture_id, base_root, recipe_root, operation_transaction_root,
judge, validation_stage, expected_code, observed_code,
rejected, trace_root
```

`trace_root =
H("g2-v07-negative-fixture-trace-v1",receipt_without_trace_root)`。Receipt 的 recipe 和
operation roots 必须由 companion literal record 重算；不接受 producer 自报 mutation。

### 17.2 Closed fixture table

| fixture ID | base and one canonical mutation | judge | expected code |
| --- | --- | --- | --- |
| `N-SCHEMA-TASK-VARIANT` | `B(T1)` replace first state payload with exact T2 payload | independent_verifier | `E-TASK-VARIANT` |
| `N-SCHEMA-UNKNOWN` | `B(T1)` replace state schema with `unknown` | producer_validator | `E-SCHEMA` |
| `N-SCHEMA-MISSING` | `B(T1)` delete `/task_payload/active_evidence_set_root` | producer_validator | `E-SCHEMA-FIELD-SET` |
| `N-SCHEMA-EXTRA` | `B(T1)` insert `/task_payload/extension=null` | producer_validator | `E-SCHEMA-FIELD-SET` |
| `N-CANONICAL-ORDER` | `B(T1)` swap first two non-equal set items | independent_verifier | `E-CANONICAL-ORDER` |
| `N-EVENT-MISSING` | `B(T1)` delete event sequence 50 | independent_verifier | `E-COVERAGE` |
| `N-EVENT-DUPLICATE` | `B(T1)` duplicate event sequence 50 | independent_verifier | `E-COVERAGE` |
| `N-EVENT-MUTATION` | `B(T1)` replace event 50 payload_digest with 64 zero hex root | independent_verifier | `E-ROOT-MISMATCH` |
| `N-RECEIVER-MISSING` | `B(T1)` delete receiver ordinal 3 | independent_verifier | `E-COVERAGE` |
| `N-RECEIVER-REORDER` | `B(T1)` swap receiver ordinals 1 and 2 | independent_verifier | `E-SEQUENCE` |
| `N-JOB-MISSING` | `B(T4)` delete job sequence 50 | independent_verifier | `E-COVERAGE` |
| `N-JOB-DUPLICATE` | `B(T4)` duplicate job sequence 50 | independent_verifier | `E-COVERAGE` |
| `N-STEP-MISSING` | `B(T1)` delete step 25 | independent_verifier | `E-SEQUENCE` |
| `N-STEP-REORDER` | `B(T1)` swap steps 24 and 25 | independent_verifier | `E-SEQUENCE` |
| `N-INTENT-MISSING` | `B_SUITE` delete canonical intent ordinal 979 | independent_verifier | `E-COVERAGE` |
| `N-INTENT-DUPLICATE` | `B_SUITE` duplicate canonical intent ordinal 979 | independent_verifier | `E-COVERAGE` |
| `N-STATE-PREVIOUS` | `B(T1)` replace step 1 previous_state_root with zero root | independent_verifier | `E-CHAIN` |
| `N-TRACE-PREVIOUS` | `B(T1)` replace step 1 previous_trace_root with zero root | independent_verifier | `E-CHAIN` |
| `N-NDJSON-NONCANONICAL` | `B(T1)` insert one ASCII space after first `{` byte | independent_verifier | `E-CANONICAL-JSON` |
| `N-NDJSON-TRUNCATE` | `B(T1)` truncate final byte | independent_verifier | `E-TRUNCATED` |
| `N-NDJSON-APPEND` | `B(T1)` append exact bytes `{}` plus LF | independent_verifier | `E-APPENDED` |
| `N-FILENAME-ROOT` | `B(T1)` replace manifest filename with 64 zero hex plus `.ndjson` | independent_verifier | `E-FILENAME-ROOT` |
| `N-FUTURE-EVENT-PREFIX` | `B(T1)` insert event at step 49 into step 0 visible projection preimage | independent_verifier | `E-FUTURE-LEAK` |
| `N-FUTURE-SCHEDULE-PREFIX` | `B(T4)` insert step 49 failure receipt into step 0 prefix | independent_verifier | `E-FUTURE-LEAK` |
| `N-SIDECAR-PREFIX` | `B(T3)` insert `/sidecar_root` into step 0 prefix | producer_validator | `E-SCHEMA-FIELD-SET` |
| `N-ATTACK-ROOT-PREFIX` | `B(T7)` insert `/attack_group_root` into step 0 prefix | producer_validator | `E-SCHEMA-FIELD-SET` |
| `N-T1-BAD-SUPERSEDES` | `B(T1)` replace first supersedes ref with undeclared ID | independent_verifier | `E-T1-SUPERSEDES` |
| `N-T1-SILENT-CONFLICT` | `B(T1)` replace one step record with a resealed record whose maximum group has two payload digests while conflict/abstention preimages omit the subject | independent_verifier | `E-T1-CONFLICT` |
| `N-T2-CLONE-WEIGHT` | `B(T2)` add clone unit twice to candidate support preimage | independent_verifier | `E-T2-CLONE-WEIGHT` |
| `N-T3-SIDECAR-READ` | `B_SOURCE` add producer import/read of sealed T3 identity path | source_auditor | `E-SOURCE-SIDECAR-READ` |
| `N-T3-DEADLINE-ORDER` | `B(T3)` move expiry before same-step mitigation | independent_verifier | `E-T3-DEADLINE-ORDER` |
| `N-T5-EARLY-PARENT` | `B(T5)` mark unrevealed-parent edge revealed | independent_verifier | `E-T5-PARENT-ORDER` |
| `N-T5-DROP-HISTORY` | `B(T5)` remove superseded ref after knowledge update | independent_verifier | `E-T5-KNOWLEDGE-UPDATE` |
| `N-T6-NAME-CORRECTNESS` | `B_SOURCE` add branch accepting candidate by literal `minority` name | source_auditor | `E-SOURCE-LABEL-DEPENDENCE` |
| `N-T6-CLONE-WEIGHT` | `B(T6)` duplicate a unit in candidate support preimage | independent_verifier | `E-T6-CLONE-WEIGHT` |
| `N-T7-CROSS-TENANT-STATE` | `B(T7)` insert rejected canary in admitted tenant chain | independent_verifier | `E-T7-ACL` |
| `N-T7-PROBE-AS-ATTACK` | `B_LABEL(T7)` insert mandatory event ID in variable attack sidecar set | independent_verifier | `E-ATTACK-GROUP-DISJOINT` |
| `N-T4-FIXTURE-IN-QUALIFICATION` | `B(T4)` replace config fixture_mode false with true | producer_validator | `E-T4-FIXTURE-IN-QUALIFICATION` |
| `N-T4-SCHEDULE-OVERRIDE` | `B(T4)` insert qualification schedule override | producer_validator | `E-T4-SCHEDULE-OVERRIDE` |
| `N-T4-NONEMPTY-DIRECTIVE` | `B(T4)` insert one assignment in no-op directive | independent_verifier | `E-DIRECTIVE-NONEMPTY` |
| `N-T4-DAG-CYCLE` | `B(T4)` replace first job shard with a resealed shard whose job 0 depends on job 1 and job 1 depends on job 0 | independent_verifier | `E-T4-DAG` |
| `N-T4-FUTURE-JOB` | `B(T4)` insert arrival-step 49 job into step 0 prefix | independent_verifier | `E-FUTURE-LEAK` |
| `N-T4-MISSING-FAILURE` | `B(T4)` delete first revealed failure receipt | independent_verifier | `E-T4-RECEIPT-COVERAGE` |
| `N-T4-MISSING-TERMINAL` | `B(T4)` delete terminal receipt for canonical last job | independent_verifier | `E-T4-RECEIPT-COVERAGE` |
| `N-ALLOC-NESTED` | `B_SOURCE` add two-generator receiver/event list comprehension | source_auditor | `E-ALLOC-NESTED-COMPREHENSION` |
| `N-ALLOC-PAIR-RECORD` | `B_SOURCE` add serialized receiver/event pair dataclass | source_auditor | `E-ALLOC-PAIR-RECORD` |
| `N-COST-OMISSION` | `B(T1)` delete `partition_join_evaluations` | independent_verifier | `E-COST-INCOMPLETE` |
| `N-AB-MISMATCH` | replace producer B artifact event 50 payload root with zero root | independent_verifier | `E-AB-BYTE-MISMATCH` |
| `N-SAME-PROGRAM-VERIFIER` | `B_SOURCE` replace verifier reducer blob with producer reducer blob | source_auditor | `E-SOURCE-IDENTITY` |
| `N-VERIFIER-IMPORT-PRODUCER` | `B_SOURCE` add verifier import from producer namespace | source_auditor | `E-SOURCE-IMPORT` |
| `N-TIMEOUT` | `B_PROCESS` replace the whole child transcript with one whose end is start plus `900_000_000_001` ns and whose result frame is absent | resource_supervisor | `E-TIMEOUT` |
| `N-RSS-EXCEED` | `B_PROCESS` replace sampled peak with `4_294_967_297` normalized bytes | resource_supervisor | `E-RSS-LIMIT` |
| `N-RSS-UNMEASURABLE` | `B_PROCESS` replace READY unit with byte value 2 | resource_supervisor | `E-RSS-UNIT` |
| `N-CRASH` | `B_PROCESS` replace child terminal frame with exit code 1 | resource_supervisor | `E-CHILD-CRASH` |
| `N-OOM` | `B_PROCESS` replace child terminal frame with OS OOM-kill exit classification | resource_supervisor | `E-CHILD-OOM` |
| `N-PARTIAL-WRITE` | `B_PROCESS` declare segment length 100 and provide 99 bytes | resource_supervisor | `E-PARTIAL-SEGMENT` |

表中 56 个 IDs 是 companion `negative_fixtures` 的可读投影；literal base ID、selector、
operations、paths、indices、values、raw hashes、preconditions、reseal policy、judge、
stage 和 expected code 只以 companion records 为准。按 fixture ID 升序的 exact 56
records 必须重算为第 12.2 节冻结的 `negative_fixture_set_root`。Qualification 必须保存
56 个 rejection receipts、每个 observed code 等于 expected code、rejected=true；
missing/duplicate fixture、table prose 或新增未预注册 fixture 不能替换 companion 任一项。

### 17.3 Positive/negative receipt artifacts

Negative receipts 按 fixture ID 升序写入
`NegativeFixtureReceiptArtifactV07`：

```text
schema="pheroos-rglf-negative-fixture-receipt-artifact-v0.7"
fixture_semantic_manifest_root
negative_fixture_set_root
receipt_count=56
receipts
negative_receipt_set_root
```

`negative_receipt_set_root =
H("g2-v07-negative-fixture-receipt-set-v1",receipts)`。Positive artifact 使用第 14.8
节 schema。两类 artifact 都是 `C(artifact)||LF`，receipt-set root 的 preimage 仅为
receipt array，不含自己。

每个 artifact 各有一个外部 `FixtureReceiptArtifactManifestV07`，exact keys：

```text
schema="pheroos-rglf-fixture-receipt-artifact-manifest-v0.7"
artifact_kind
filename
byte_count
artifact_root
receipt_count
receipt_set_root
fixture_set_root
fixture_semantic_manifest_root
producer_source_root
verifier_source_root
manifest_root
```

`artifact_kind=positive/negative`；filename 是
`<artifact_root-without-prefix>.positive-fixtures.json` 或
`<artifact_root-without-prefix>.negative-fixtures.json`。`artifact_root=RAW(exact
artifact bytes)`；`manifest_root =
H("g2-v07-fixture-receipt-artifact-manifest-v1",
manifest_without_manifest_root)`。Raw root、byte count 和 filename 只存在外部 manifest，
不写回 receipt artifact，因此无 self-reference。Positive manifest 必须绑定 exact
`3`、positive fixture/receipt set roots；negative manifest 必须绑定 exact `56`、
negative fixture/receipt set roots。两个 manifests、两个 artifacts 和 companion 必须
flush、fsync、close 后由 independent verifier 复读；任一缺失、额外、root mismatch、
source collision 或 count mismatch 都保持 G2 blocked。

## 18. 独立二审保留的 activation blockers

本 review draft 的 companion roots、`12/3/56` inventory、positive expected receipt
roots 和可读索引已经独立重算一致；这只允许保存 review checkpoint。2026-07-26 至
2026-07-27 的独立 materialization 二审仍保留下列开放项：

1. **P1 — `duplicate` operation 不是 total transform。**
   `N-EVENT-DUPLICATE`、`N-JOB-DUPLICATE`、`N-INTENT-DUPLICATE`、
   `N-T2-CLONE-WEIGHT` 和 `N-T6-CLONE-WEIGHT` 的当前 records 没有冻结目标
   container、literal insertion position 或新的 stable key。对 `by_sequence/50`
   这类 map path，重复 canonical object key 非法；实现也不能自行选择另一个 key。
2. **P1 — task/variant error precedence 与 expected code 冲突。**
   `N-SCHEMA-TASK-VARIANT` 把 T1 payload 替换为 exact T2 payload。按第 17.1 节当前
   `E-SCHEMA-FIELD-SET` 先于 `E-TASK-VARIANT`，因此不能唯一得到 companion 声明的
   `E-TASK-VARIANT`，除非 activation candidate 冻结一个不依赖特例的判定顺序或修改
   recipe/expected code。
3. **P2 — `base_artifacts` array order 规则未命名。**
   当前 exact companion bytes 和 root 已锁定其语义分组顺序，但该顺序不是 Unicode
   `base_artifact_id` 顺序。Activation candidate 必须明确采用 literal companion order、
   constructor order 或 ID order，且 verifier 不得自行排序。
4. **P2 — 部分 validation predicates 仍可能重叠。**
   `N-OOM` 需要冻结 `E-CHILD-OOM` 与先列的 `E-CHILD-CRASH` 的互斥谓词；
   `N-STEP-MISSING` 需要冻结 `E-SEQUENCE` 与先列的 `E-COVERAGE` 的适用对象和优先级。
   同一 input 在两个 predicates 下均为 true 时不得由实现自行选择 failure code。

这些问题不否定 design inventory 的 content roots，但阻止 literal materialization、
把 `activation_ready` 改为 true、lock migration、v0.7 reducer/runner 实现和
`G2-FULL-SCALE-TASK-STATE` qualification。未来修订必须原子更新 profile 与 companion，
重算全部 file/semantic roots，并再次通过独立二审；runtime 或 lock 不能覆盖本节。
