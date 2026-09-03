# Receptor-Gated Ligand Field G3 Methodological Amendment v0.1

状态：**review draft / not active**

边界：**provider-free engineering qualification only；no H1-H6 conclusions**

```text
implementation_allowed=false
lock_migration_allowed=false
gate_changes={}
contract_descriptor_set_materialized=false
contract_descriptor_meta_schema_root=null
contract_descriptor_set_root=null
contract_descriptor_set_qualification_receipt_root=null
methodology_activation_root=null
```

本文件只冻结拟议的 external research-harness 方法。它不激活 experiment profile，不迁移
preregistration lock，不修改 PheroOS ABI、Governance、Trace、Conformance、TCK、
Evidence、Optimal Commit、permission、fallback 或 output authority。

本 draft 没有 materialize artifact、receipt 或 content root。下文的 `*_root` 只是未来
contract 字段名，不是已计算 hash；不得填入臆造值或把 expected geometry 写成 observed
result。上述 control fields 表示本 review draft 本身不授权实现、lock migration 或
任何 gate 状态变化，并且 machine-readable descriptor set 尚不存在；只有后续单独审阅
并激活的新 profile 才能改变这些控制项。

## 1. 冻结决策

G3 方法修订固定为：

1. 公共、arm-independent、receiver-step budget schedule；
2. iso/sweep 下 controller 输出 full pre-cap ranking，由一个 common reducer 只应用一次
   cap；
3. S/G 对 N=4 和 N=16 分别资格化；
4. N>=64 的 S/G 只做显式 OOD cost mechanics，不产生 outcome；
5. Cost Ledger v2 强制 expected slots、唯一 physical ownership、allocation conservation、
   CostObservationV2、AttemptIdentity/ReceiptV2、primary ITT 和独立 verifier；
6. P 在当前 strict goal 内保持 blocked；
7. 第一条可执行 vertical slice 仅为一个既有 T1/F smoke cell。

这些决定只以可重复性、公平性、完整性和 fail-closed behavior 为通过标准，不以 R 或任一
baseline 的性能为通过标准。

## 2. Geometry 与 task size

Smoke/attack axes 不变：

```text
tasks=T1..T7
arms=F,P,S,B,Q,G,R
matrix_kind=smoke_attack
agent_count=4,16
event_count=100
steps=20
attack_severity=0.00,0.25
seed=9000,9001
repeat_id=0,1
budget_layer_ids=
  natural,iso,
  sweep:0.10,sweep:0.20,sweep:0.35,
  sweep:0.50,sweep:0.75,sweep:1.00
```

Expected geometry 为 `112` environments 和 `6,272` arm-budget intents。

External `TaskSizeProfileV2` 必须显式绑定：

| task | smoke/train/dev | pilot/confirmatory planned-only |
| --- | ---: | ---: |
| T1 facts | 20 | 100 |
| T2 candidates | 4 | 8 |
| T3 artifacts | 16 | 32 |
| T4 jobs | 32 | 64 |
| T5 subjects | 50 | 200 |
| T6 candidates | 20 | 64 |
| T7 subjects per tenant | 16 | 64 |

G3 不执行 pilot/confirmatory。Scale 仍只有：

```text
matrix_kind=scale
split=smoke
tasks=T1..T7
(agent_count,event_count)=
  (4,100),(16,1000),(64,10000),(256,100000),(1024,100000)
seed=9000,9001
repeat_id=0,1
steps=50
attack_severity=0.00
budget_layer_id=natural
outcome_authorized=false
```

Scale planning geometry 精确为：

```text
7 tasks * 5 size pairs * 2 seeds * 2 repeats = 140 environments
140 environments * 7 arms * 1 natural layer = 980 intents
```

T4 scale 的 `job_count=event_count`，不能回落到 32。Full-scale profile 尚未激活或
materialization review 未完成时，scale execution 保持 blocked。不得新增未预注册的
scale iso/sweep。每个未来 scale execution envelope 必须一对一引用 active v0.5/v0.6
labelled `PublicEnvironmentCellV05.planning_cell_root`、
`LazyEpisodeManifestBindingV05.root` 和 `ArmBudgetIntentV05.root`。Manifest/intent
内部引用 planning cell 的字段名是 `environment_plan_root`；intent 引用 lazy manifest
的字段名是 `episode_manifest_root`。新 execution root 只能扩展这些 planning
identities，不能重写、替代、改名或追溯升级 v0.5 planning artifact。

## 3. BudgetScheduleV2

### 3.1 Arm-independent basis

`F-reference` 是公共预算基准，不是先执行 F，也不把 shared eligibility 成本记给 F。

对每个：

```text
(public_episode_commitment_root, receiver_id, logical_step)
```

在 controller ranking 前计算：

```text
E = common-eligible receiver-event count
T = sum(token_estimate for every common-eligible event)
```

Basis 不得读取 controller selection、sealed sidecar、relevance label、future suffix、
outcome 或 provider response。Eligibility predicate exact 固定为：

```text
event.logical_time <= logical_step
and receiver.receiver_id in event.eligible_receiver_ids
and (event.is_public or receiver.tenant_id == event.tenant_id)
and event.scope_ref in receiver.grants
and event.evidence_status in {"verified","superseding"}
```

这 byte-for-byte 对应 external V1 `make_context`/`eligibility_reason` 语义；version 固定
`receiver-prefix-v1-exact`。事件 canonical order 是
`(logical_time ascending,event_id UTF-8 ascending)`，event IDs 必须唯一。
`token_estimate` 是 positive integer 且必须等于
`max(1,ceil(len(payload_text UTF-8 bytes)/4))`，禁止 controller 自报 token count。

Scale prefixes 使用 `CommonEligibilityStreamV2`，不内嵌 Cartesian arrays。Exact keys：

```text
schema="pheroos-rglf-common-eligibility-stream-v2"
public_episode_commitment_root
receiver_root
receiver_id
logical_step
eligibility_predicate_root
chunk_capacity=4096
chunk_count
row_count
first_chunk_root
last_chunk_root
ordered_chunk_roots_root
ordered_eligible_event_roots_root
eligible_event_ids_root
eligible_token_rows_root
eligible_token_count
stream_closed=true
stream_root
```

`CommonEligibilityChunkV2` exact keys：

```text
schema="pheroos-rglf-common-eligibility-chunk-v2"
public_episode_commitment_root
receiver_root
receiver_id
logical_step
eligibility_predicate_root
chunk_capacity=4096
chunk_index
start_ordinal
row_count
previous_chunk_root
rows_root
chunk_root
```

Chunk row exact keys 是 `logical_time,event_id,event_root,token_estimate`，按 canonical
event order。首 chunk 固定
`chunk_index=0,start_ordinal=0,previous_chunk_root=null`；后续 chunk 的
`chunk_index` 加一、`start_ordinal` 等于前一项 start 加 row count、
`previous_chunk_root` 等于前一 chunk root。除最后一 chunk 外必须恰好 4096 rows，
最后一 chunk 为 1..4096 rows；禁止 zero-row chunk、gap、overlap、duplicate index 或
错误 previous root。Root recipes：

```text
rows_root =
  digest_json("g3-common-eligibility-chunk-rows-v2",
              ordered chunk row dictionaries)
chunk_root =
  digest_json("g3-common-eligibility-chunk-v2",
              chunk record without chunk_root)
ordered_chunk_roots_root =
  digest_json("g3-common-eligibility-ordered-chunks-v2",
              chunk roots in chunk_index order)
ordered_eligible_event_roots_root =
  digest_json("g3-common-eligibility-event-roots-v2",
              event roots in canonical event order)
eligible_event_ids_root =
  digest_json("g3-common-eligibility-event-ids-v2",
              event IDs in canonical event order)
eligible_token_rows_root =
  digest_json("g3-common-eligibility-token-rows-v2",
              event_id,event_root,token_estimate rows in canonical event order)
stream_root =
  digest_json("g3-common-eligibility-stream-v2",
              stream record without stream_root)
```

Stream 与每个 chunk 的 public/receiver/step/predicate roots 必须 exact equality；
`chunk_count,row_count,first_chunk_root,last_chunk_root` 和全部 final roots 必须从
closed chain 独立重算。空 stream 固定
`chunk_count=0,row_count=0,first_chunk_root=null,last_chunk_root=null`，三个 ordered
content roots 与 ordered-chunk root 分别是对应 domain label 对空 list 的 digest，
`eligible_token_count=0`，且不得产生 chunk。Final roots 从 chained rows streaming
计算；不得把全 prefixes 展开为 memory-resident nested arrays。

`CommonEligibilityBasisV2` exact keys：

```text
schema="pheroos-rglf-common-eligibility-basis-v2"
task_size_profile_root
active_planning_cell_root
public_episode_commitment_root
receiver_universe_root
receiver_root
receiver_id
logical_step
eligibility_predicate_version="receiver-prefix-v1-exact"
eligibility_predicate_root
canonical_event_order="logical_time,event_id"
eligibility_stream_root
eligible_event_root_count
ordered_eligible_event_roots_root
eligible_event_ids_root
eligible_token_rows_root
eligible_event_count=E
eligible_token_count=T
basis_root
```

Predicate root 使用 `g3-common-eligibility-predicate-v2` 绑定上述 exact literal。
Three event/token roots 只由 Stream 使用
`g3-common-eligibility-event-roots-v2|g3-common-eligibility-event-ids-v2|
g3-common-eligibility-token-rows-v2` 计算，Basis 原样引用，不用第二套 domain label
重算；token row exact keys 是 `event_id,event_root,token_estimate`。
Basis 的 stream/count/three roots/token total
必须与 closed stream exact equality。Basis root 排除自身并使用
`g3-common-eligibility-basis-v2`。E 等于 rows count，T 由 exact integer sum 重算。
除此以外必须 dereference Stream 与 PublicEpisode，逐项证明：

```text
basis.public_episode_commitment_root == stream.public_episode_commitment_root
basis.receiver_root == stream.receiver_root
basis.receiver_id == stream.receiver_id
basis.logical_step == stream.logical_step
basis.eligibility_predicate_root == stream.eligibility_predicate_root
basis.task_size_profile_root == public.task_size_profile_root
basis.active_planning_cell_root == public.active_planning_cell_root
basis.receiver_universe_root == public.receiver_universe_root
basis.receiver_root ==
  canonical receiver root for basis.receiver_id in public.receiver_universe_root
0 <= basis.logical_step < public.steps
```

`public` 必须是由 `basis.public_episode_commitment_root` 解出的 exact
`PublicEpisodeCommitmentV2`；只让 Stream 与 Basis 的 aggregate roots/counts 相等而
不核 context，或整体 graft 另一 receiver-step Stream，均拒绝。

`CommonEligibilityBasisSetChunkV2` exact keys 是：

```text
schema="pheroos-rglf-common-eligibility-basis-set-chunk-v2"
task_size_profile_root
active_planning_cell_root
public_episode_commitment_root
receiver_universe_root
steps
chunk_capacity=4096
chunk_index
start_ordinal
row_count
previous_chunk_root
rows_root
chunk_root
```

Index row exact keys 为 `receiver_id,logical_step,basis_root`，按 receiver ID UTF-8/
logical step ascending 排序。Chunk predecessor、capacity、non-empty 和 ordinal rules
与 `CommonEligibilityChunkV2` exact 相同；rows/chunk roots 分别使用
`g3-common-eligibility-basis-set-chunk-rows-v2` 与
`g3-common-eligibility-basis-set-chunk-v2`。

`CommonEligibilityBasisSetV2` exact keys 是：

```text
schema="pheroos-rglf-common-eligibility-basis-set-v2"
task_size_profile_root
active_planning_cell_root
public_episode_commitment_root
receiver_universe_root
steps
basis_count
chunk_capacity=4096
chunk_count
first_chunk_root
last_chunk_root
ordered_chunk_roots_root
basis_set_stream_root
ordered_basis_index_rows_root
ordered_basis_roots_root
set_root
```

每个 chunk 的 task-size/planning/public/universe/steps roots 必须与 enclosing Set exact
equality。Set 还必须 dereference public commitment 并证明
`set.task_size_profile_root == public.task_size_profile_root`、
`set.active_planning_cell_root == public.active_planning_cell_root`、
`set.receiver_universe_root == public.receiver_universe_root` 和
`set.steps == public.steps`。Index rows 必须完整覆盖 dereferenced receiver universe IDs 与
`logical_step in [0,steps)` 的 exact Cartesian key set，且
`(receiver_id,logical_step)` 唯一。每个 row 引用的
`CommonEligibilityBasisV2` 必须满足：

```text
basis.task_size_profile_root == set.task_size_profile_root
basis.active_planning_cell_root == set.active_planning_cell_root
basis.public_episode_commitment_root == set.public_episode_commitment_root
basis.receiver_universe_root == set.receiver_universe_root
basis.receiver_id == row.receiver_id
basis.logical_step == row.logical_step
basis.receiver_root ==
  canonical receiver root for row.receiver_id in set.receiver_universe_root
```

Verifier 必须 dereference 和重算 basis/receiver roots；只核对 row key/count/digest 无效。
`ordered_chunk_roots_root` 使用
`g3-common-eligibility-basis-set-ordered-chunks-v2`；stream/index/basis roots 使用
`g3-common-eligibility-basis-set-{stream|index-rows|basis-roots}-v2`，都从 closed
chunk chain streaming 重算。Exact preimages：

```text
ordered_basis_index_rows_root =
  digest_json("g3-common-eligibility-basis-set-index-rows-v2",
              all index rows in canonical order)
ordered_basis_roots_root =
  digest_json("g3-common-eligibility-basis-set-basis-roots-v2",
              basis roots in the same order)
basis_set_stream_root =
  digest_json("g3-common-eligibility-basis-set-stream-v2", {
    "task_size_profile_root": task_size_profile_root,
    "active_planning_cell_root": active_planning_cell_root,
    "public_episode_commitment_root": public_episode_commitment_root,
    "receiver_universe_root": receiver_universe_root,
    "steps": steps,
    "basis_count": basis_count,
    "chunk_capacity": 4096,
    "chunk_count": chunk_count,
    "first_chunk_root": first_chunk_root,
    "last_chunk_root": last_chunk_root,
    "ordered_chunk_roots_root": ordered_chunk_roots_root,
    "ordered_basis_index_rows_root": ordered_basis_index_rows_root,
    "ordered_basis_roots_root": ordered_basis_roots_root
  })
```

Set root 排除自身并使用
`g3-common-eligibility-basis-set-v2`。若 expected basis count 为 0，则固定
zero-chunk/null first/null last，ordered-chunk/index/basis 三个 roots 分别是对应
domain label 对 empty list 的 digest，stream root 使用上面的 zero-valued object；
否则最后一 chunk close 后 `basis_count` 必须等于 expected count。不得内嵌
full-scale basis arrays。

同一 environment/receiver/step 的七个 arms 和八个 layers 引用相同 basis root；arm/layer
ID 不进入 basis。

### 3.2 Exact caps

Natural：

```text
event_cap=null
token_cap=null
retrieval_cap=null
model_call_cap=1
tool_call_cap=1
```

Iso：

```text
event_cap=8
token_cap=512
retrieval_cap=8
model_call_cap=1
tool_call_cap=1
```

Sweep 只用整数有理数：

| budget layer ID | event cap | token cap | retrieval/ref cap |
| --- | ---: | ---: | ---: |
| `sweep:0.10` | `floor(E/10)` | `floor(T/10)` | `2*floor(E/10)` |
| `sweep:0.20` | `floor(E/5)` | `floor(T/5)` | `2*floor(E/5)` |
| `sweep:0.35` | `floor(7E/20)` | `floor(7T/20)` | `2*floor(7E/20)` |
| `sweep:0.50` | `floor(E/2)` | `floor(T/2)` | `2*floor(E/2)` |
| `sweep:0.75` | `floor(3E/4)` | `floor(3T/4)` | `2*floor(3E/4)` |
| `sweep:1.00` | `E` | `T` | `2E` |

全部六档 sweep 也固定：

```text
model_call_cap=1
tool_call_cap=1
```

早期低预算 entry 合法为零，不强制选择一个；但非空 environment 的某档 sweep 若在全部
receiver-step 恒为零，则视为 placeholder regression。Caps 必须单调，且 F 在 1.00 的
selected set 必须等于 natural。

`BudgetScheduleEntryV2` exact keys：

```text
schema="pheroos-rglf-budget-schedule-entry-v2"
basis_root
budget_layer_id
budget_regime
ratio_numerator
ratio_denominator
event_cap
token_cap
retrieval_cap
model_call_cap
tool_call_cap
entry_root
```

Natural/iso 的 ratio fields 是 `null`；六档 sweep 使用约分后的 exact integer
numerator/denominator。`entry_root` 排除自身并使用
`g3-budget-schedule-entry-v2`。`BudgetScheduleV2` exact keys：

```text
schema="pheroos-rglf-budget-schedule-v2"
basis_root
entry_count=8
ordered_budget_layer_ids
ordered_entry_roots
schedule_root
```

Layer 顺序固定为
`natural,iso,sweep:0.10,sweep:0.20,sweep:0.35,sweep:0.50,sweep:0.75,sweep:1.00`；
schedule root 排除自身并使用 `g3-budget-schedule-v2`。Verifier 必须 dereference
全部八个 entries，要求每个 `entry.basis_root == schedule.basis_root`、entry 的 layer ID
与同 ordinal `ordered_budget_layer_ids` exact equality、八个 layer IDs/entry roots
unique 且无 missing/extra，并从 referenced basis 的 E/T 重算全部 cap；只核
entry_count/list roots 无效。

`BudgetScheduleSetV2` exact keys 是：

```text
schema="pheroos-rglf-budget-schedule-set-v2"
task_size_profile_root
active_planning_cell_root
public_episode_commitment_root
receiver_universe_root
steps
basis_set_root
schedule_count
ordered_schedule_index_rows_root
ordered_schedule_roots
missing_count=0
extra_count=0
duplicate_key_count=0
duplicate_basis_root_count=0
set_root
```

Schedule index row exact keys 是
`receiver_id,logical_step,basis_root,schedule_root`，按 receiver ID UTF-8/logical step
ascending 排序；root 使用 `g3-budget-schedule-index-rows-v2`。Set 必须 dereference
`CommonEligibilityBasisSetV2` 与 `PublicEpisodeCommitmentV2` 并证明：

```text
set.task_size_profile_root == basis_set.task_size_profile_root
set.active_planning_cell_root == basis_set.active_planning_cell_root
set.public_episode_commitment_root == basis_set.public_episode_commitment_root
set.receiver_universe_root == basis_set.receiver_universe_root
set.steps == basis_set.steps
set.task_size_profile_root == public.task_size_profile_root
set.active_planning_cell_root == public.active_planning_cell_root
set.receiver_universe_root == public.receiver_universe_root
set.steps == public.steps
```

Expected schedule index 是 BasisSet ordered index rows 的 exact one-to-one projection：
每个 `(receiver_id,logical_step,basis_root)` 恰有一个 schedule，dereferenced
`schedule.basis_root == row.basis_root`，且 `ordered_schedule_roots` 是同序 schedule
roots。`schedule_count == basis_set.basis_count`，四个 defect counts 必须为 0；
cross-episode、cross-universe、cross-step、duplicate-basis 或 count-preserving graft
均拒绝。Set root 排除自身并使用 `g3-budget-schedule-set-v2`。

Episode-level placeholder 不能作为 effective sweep。External execution envelope 必须绑定：

```text
public_episode_commitment_root
materialized_episode_manifest_root
active_arm_budget_intent_root
budget_layer_id
budget_schedule_set_root
controller_config_root
attempt_policy_root
sealed_evaluator_enabled=false
provider_adapter_enabled=false
```

每个 bundle/run/trace 再绑定实际 budget-entry root。该 envelope 不进入 PheroOS ABI。

### 3.3 PreCapCandidateV2

Controller ranking 的全部可见状态先冻结为 `ControllerInputStateV2`，exact keys：

```text
schema="pheroos-rglf-controller-input-state-v2"
public_episode_commitment_root
basis_root
controller_id
controller_config_root
receiver_id
logical_step
parent_logical_step
parent_controller_state_root
initial_state_contract_root
parent_state_transition_root
state_dependency_kind
ordered_state_dependency_roots
visible_state_payload_root
budget_layer_id=null
budget_schedule_entry_root=null
materialized_episode_manifest_root=null
arm_budget_execution_binding_root=null
ranking_input_budget_blind=true
controller_input_state_root
```

Root 排除自身并使用 `g3-controller-input-state-v2`。
`ControllerInitialStateV2` exact keys：

```text
schema="pheroos-rglf-controller-initial-state-v2"
public_episode_commitment_root
controller_id
controller_config_root
receiver_id
state_dependency_kind
ordered_state_dependency_roots
initial_state_payload_root
budget_layer_id=null
materialized_episode_manifest_root=null
initial_state_root
```

Initial root 排除自身并使用 `g3-controller-initial-state-v2`；F/B/Q 的 payload 是
canonical empty object。Closed initial mapping：

```text
F,B,Q -> payload={}, dependencies=()
S     -> payload={}, dependencies=(exact size-qualified graph/config)
P     -> receiver payload={}, dependencies=(initial domain/manifest/topology/store roots);
         no preloaded trail/pressure/snapshot
G     -> payload={} with missing seen_clusters interpreted exactly as empty;
         dependencies=(exact checkpoint,S graph,allowlist)
R     -> payload={"habituation":{},"cluster_history":{}};
         dependencies=(declared topology/environment roots);
         step-0 visible field is derived only from the public prefix and is
         added in ControllerInputState, never preloaded here
```

Unknown/nonempty preload、pre-seen G cluster、P trail/pressure、R habituation/history 或
non-public-derived R field 均拒绝。`parent_logical_step=null`
仅用于 step 0，且 `parent_controller_state_root` 必须等于 referenced
`ControllerInitialStateV2.initial_state_root`；此时 `initial_state_contract_root` 非 null、
`parent_state_transition_root=null`。其余 step 的 initial field 必须 null，并引用同一
episode/controller/receiver 的 step-1 `ControllerStateTransitionV2.output_state_root`，
并将 corresponding transition root 写入 `parent_state_transition_root`。
Closed dependency mapping 是：

```text
F,B,Q       -> stateless
S N=4,16    -> static_graph_binding
S N>=64     -> ood_destination_static_graph
P           -> scalar_trail_state
G N=4,16    -> checkpoint_and_seen_clusters
G N>=64     -> ood_checkpoint_destination_graph_and_seen_clusters
R           -> ligand_field_habituation_cluster_history
```

Stateless payload 必须是 canonical empty object；S primary 必须绑定 exact
size-qualified graph，S OOD 必须绑定 S extrapolation receipt 与 destination graph；
P payload 必须覆盖完整 visible trail state；G primary 必须覆盖 exact size-qualified
checkpoint 与 graph、prior `seen_clusters`，G OOD 必须覆盖 Section 4.2 pre-execution
binding、source checkpoint、destination graph 与 prior clusters；R 必须覆盖 visible
field、habituation 和 cluster-history。`ordered_state_dependency_roots` 按
dependency name 的 UTF-8 顺序，payload root 分别使用
`g3-controller-visible-state-{f|s|b|q|p|g|r}-v2`。任何影响 priority/filter 的状态若未
进入 payload 或 dependency roots，ranking 无效。Candidate、chunk、final、reducer 和
run/trace 中的 `controller_input_state_root` 必须 exact equality。State transition
只能读取完整 common-eligible public prefix，不能读取 current/prior selected set、
budget layer、effective caps、manifest marker 或 reducer output；因此同一
`(public episode,controller,receiver,logical_step)` 的八个 layers 必须引用 byte-exact
相同的 input-state root 和 parent semantic state lineage。

Budget-blind semantic output 由 `ControllerStateTransitionV2` 闭合，exact keys：

```text
schema="pheroos-rglf-controller-state-transition-v2"
public_episode_commitment_root
basis_root
controller_id
controller_config_root
receiver_id
logical_step
controller_input_state_root
state_dependency_kind
transition_input_event_ids_root
output_state_payload_root
output_state_root
budget_layer_id=null
budget_schedule_entry_root=null
selected_event_ids_root=null
budget_fields_read_count=0
selected_history_fields_read_count=0
transition_root
```

`transition_input_event_ids_root` 必须等于 basis 的 complete eligible IDs root。
`output_state_root` 使用
`digest_json("g3-controller-semantic-output-state-v2",
{public_episode_commitment_root,controller_id,controller_config_root,receiver_id,
logical_step,state_dependency_kind,output_state_payload_root})`；transition root 排除自身并
使用 `g3-controller-state-transition-v2`。同 arm/receiver/step 八层必须引用同一
transition/output roots；下一 step 的 input 必须 exact 引用该 output/transition。
Stateless output payload 是 canonical empty object。Budget/reducer/bundle-specific
wrapper 可以不同，但不得进入 semantic state root。

Natural native selection 另由 closed `NativeSelectionPolicyV2` 表达，不能压成一个对
所有 controller 通用的 scalar event limit。Exact keys：

```text
schema="pheroos-rglf-native-selection-policy-v2"
controller_id
controller_config_root
policy_kind
flat_event_limit
group_cap
members_per_group_cap
group_key_contract
group_rank_contract
member_rank_contract
native_policy_root
```

Root 排除自身并使用 `g3-native-selection-policy-v2`。Closed mapping：

```text
F,S -> all_eligible
P   -> flat_rank_limit, flat_event_limit=8
B   -> flat_rank_limit, flat_event_limit=16
Q   -> flat_rank_limit, flat_event_limit=8
G   -> flat_rank_limit, flat_event_limit=checkpoint native_k in {4,8,16}
R   -> group_then_member_limit, group_cap=4, members_per_group_cap=2
```

不适用的 cap/contract fields 必须为 null。R 的 group key 是 frozen subject key；group
排序是 `(-subject_salience_decimal,subject_key)`；group 内排序是
`(-logical_time,-canonical_ligand_dose_sum_decimal,event_id)`。这精确保留 R 的
subject-first/ref-second 语义，不得用 global top-8 代替。

每个 common-eligible event 恰好产生一个 closed-schema `PreCapCandidateV2`。字段和顺序
固定为：

```text
schema="pheroos-rglf-pre-cap-candidate-v2"
basis_root
controller_id
controller_config_root
controller_input_state_root
controller_state_transition_root
native_policy_root
ranking_contract_id
rank_contract_root
receiver_id
logical_step
event_id
event_root
evidence_ref
filter_state
filter_code
priority_decimal
priority_quantum
native_group_id
native_group_priority_decimal
native_group_rank_ordinal
native_member_rank_ordinal
event_demand
token_demand
retrieval_demand
```

Closed filter code 只有：

```text
admitted
inactive_evidence_version
static_graph_edge_absent
scalar_field_inactive
receptor_field_inactive
```

Controller mapping 与 precedence 固定为：

```text
F       admitted
S       static_graph_edge_absent -> admitted
B,Q,G   inactive_evidence_version -> admitted
P       inactive_evidence_version -> scalar_field_inactive -> admitted
R       inactive_evidence_version -> receptor_field_inactive -> admitted
```

Arrows 是 first-match precedence：inactive/superseded version 必须先从 P/R 排除，只有
active version 才能被 field gate 判断。Generic/unknown/“其他机制”均禁止。Natural
native policy 不是 controller filter；
所有语义上 admitted 的 candidate 必须先获得 priority，natural native limit 只能由
common reducer 记录为 `native_limit` drop。

`filter_state` 只能是 `ranked|controller_filtered`。`ranked` 固定
`filter_code=admitted`，priority 是 finite canonical Decimal text 和 controller
contract quantum；`controller_filtered` 必须使用上述非 admitted code，两个 priority
fields 都是 `null`。所有 controller 的 v2 priority quantum 固定为
`0.000000001`，rounding 固定 `ROUND_HALF_EVEN`，text grammar 固定为
`^(0|[1-9][0-9]*)\.[0-9]{9}$`：无 sign、exponent、NaN/Infinity、leading zero
变体或省略的小数位。映射为
`F/P/S/B/Q/G/R -> q9`；改变任一 controller quantum 是 descriptor-breaking change。

只有 R ranked row 的四个 native-group fields 非 null；其
`native_group_priority_decimal == priority_decimal == subject_salience_decimal`，
ordinal 从 0 连续，并按上文 group/member contracts 独立重算。其他 controller 以及所有
controller-filtered rows 的四个字段必须为 null。`ranking_contract_id` mapping 固定为
`R:r-subject-member-v2`，其他六 arms 为 `priority-event-v2`。每行 `event_demand=1`、
`token_demand=event.token_estimate`、`retrieval_demand=1`。Model/tool demand 属于
attempt/bundle 层，不属于 per-event demand。

每个 candidate 的 `ranking_contract_id` 必须 exact 等于其 final 所引用
`RankContractV2.ranking_contract_id`，`rank_contract_root` 必须引用同一个 exact
contract，并且 controller ID exact equality；混用 ID/root 或只改一侧必须由
`G3-RANK-CONTRACT-MISMATCH` 拒绝。

Pre-cap coverage stream 按 `event_id` 排序，ranking view 只包含 `ranked` rows，并按
Section 3.4 的 controller-specific closed `RankContractV2` 排序。F/P/S/B/Q/G 使用
priority-desc/event-id；R 使用 subject-rank/member-rank/event-id。不得由 budget layer
选择不同 comparator。

`PreCapChunkV2` exact keys 是：

```text
schema="pheroos-rglf-pre-cap-chunk-v2"
basis_root
controller_id
controller_config_root
controller_input_state_root
controller_state_transition_root
native_policy_root
ranking_contract_id
rank_contract_root
receiver_id
logical_step
chunk_index
start_ordinal
row_count
previous_chunk_root
rows_root
chunk_root
```

首 chunk 固定 `chunk_index=0,start_ordinal=0,previous_chunk_root=null`；后续 chunk 的
start ordinal 等于前一项 start 加 row count，previous root 等于前一 chunk root。
Rows 按 event ID 升序：

```text
rows_root =
  digest_json("g3-pre-cap-chunk-rows-v2",
              ordered PreCapCandidateV2 dictionaries)

chunk_root =
  digest_json("g3-pre-cap-chunk-v2",
              chunk record without chunk_root)
```

空中间 chunk、ordinal gap/overlap、重复 index 或错误 previous root 均拒绝。
Canonical chunk capacity 固定为 4096 rows；除最后一 chunk 外每 chunk 必须恰好 4096
rows，最后一 chunk 为 1..4096 rows。若 basis eligible count 为 0，则不得产生 chunk：
`chunk_count=0,total_row_count=0,first_chunk_root=null,last_chunk_root=null`，且
`ordered_chunk_roots_root=digest_json("g3-pre-cap-ordered-chunks-v2",[])`。不得用一个
zero-row chunk 表示空 stream。

`PreCapFinalReceiptV2` exact keys 是：

```text
schema="pheroos-rglf-pre-cap-final-v2"
basis_root
controller_id
controller_config_root
controller_input_state_root
controller_state_transition_root
native_policy_root
ranking_contract_id
receiver_id
logical_step
chunk_count
total_row_count
first_chunk_root
last_chunk_root
ordered_chunk_roots_root
coverage_event_ids_root
ranked_candidate_ids_root
controller_filtered_ids_root
rank_contract_root
rank_order_root
common_eligible_demand_root
ranked_demand_root
controller_filtered_demand_root
duplicate_count
missing_count
extra_count
stream_closed
final_root
```

Roots：

```text
ordered_chunk_roots_root =
  digest_json("g3-pre-cap-ordered-chunks-v2",
              chunk roots in chunk_index order)
coverage_event_ids_root =
  digest_json("g3-pre-cap-coverage-event-ids-v2",
              event IDs in ascending event_id order)
ranked_candidate_ids_root =
  digest_json("g3-pre-cap-ranked-event-ids-v2",
              ranked event IDs in rank order)
controller_filtered_ids_root =
  digest_json("g3-pre-cap-filtered-event-ids-v2",
              filtered event IDs in ascending event_id order)
final_root =
  digest_json("g3-pre-cap-final-v2",
              final record without final_root)
```

Final close 必须证明：

```text
coverage IDs == basis eligible IDs
total_row_count == basis eligible_event_count
ranked disjoint-union controller_filtered == coverage
duplicate_count=0
missing_count=0
extra_count=0
stream_closed == true
every candidate row basis/controller/config/input-state/state-transition/
native-policy/ranking-contract ID+root/receiver/step
  == enclosing chunk and final exact fields
every chunk context field == enclosing final exact field
for every candidate event_id, exact one CommonEligibilityStream row exists and
  candidate.event_root == stream.event_root
  candidate.token_demand == stream.token_estimate
  candidate.evidence_ref == referenced canonical event.evidence_ref
  candidate.event_demand == 1
  candidate.retrieval_demand == 1
```

这叫 logical completeness；scale 可以 streaming，不要求同时 materialize 全部 rows，但
没有 final close record 的 prefix 不能 qualification。

Budget-specific execution 只包裹、不能改变上述 semantic ranking。
Freshness 由 supervisor-owned `ProcessLaunchReceiptV2` 证明，exact keys：

```text
schema="pheroos-rglf-process-launch-receipt-v2"
supervisor_run_root
attempt_identity_root
arm_budget_execution_binding_root
controller_id
receiver_id
logical_step
launch_ordinal
process_instance_identity_root
executable_source_tree_root
producer_source_root
controller_input_state_root
process_isolation_policy_root
sanitized_environment_root
provider_credential_variable_count=0
network_isolation_enabled=true
network_access_enabled=false
network_used=false
start_provenance_root
end_provenance_root
exit_code=0
terminal_code="completed"
output_controller_state_transition_root
output_pre_cap_final_root
authority_scope="none"
commit_authority=false
process_launch_receipt_root
```

Supervisor 在 spawn/exit 边界生成 receipt；child 不能自签。
`process_instance_identity_root` 绑定 supervisor run、canonical launch ordinal、OS
process-start token 与 executable source tree，不进入 semantic replay root。同一
attempt/receiver/step 只有一个 launch；跨八 layers 的 process identity 和 launch
receipt roots 必须两两不同，而 semantic input/transition/final roots必须相同。
Receipt root 使用 `g3-process-launch-receipt-v2`。

`PreCapExecutionReceiptV2` exact keys：

```text
schema="pheroos-rglf-pre-cap-execution-receipt-v2"
arm_budget_execution_binding_root
attempt_identity_root
controller_id
receiver_id
logical_step
controller_input_state_root
controller_state_transition_root
native_policy_root
pre_cap_final_root
rank_contract_root
rank_order_root
producer_source_root
process_launch_receipt_root
fresh_execution=true
budget_layer_fields_read_count=0
effective_cap_fields_read_count=0
selected_history_fields_read_count=0
authority_scope="none"
commit_authority=false
execution_receipt_root
```

Root 使用 `g3-pre-cap-execution-receipt-v2`。每个 arm/layer attempt 必须 fresh
materialize 一份 receipt；同一 arm/receiver/step 的八份 receipt 必须有不同 execution
binding/attempt/process-launch roots，但 `controller_input_state_root`、
`controller_state_transition_root`、`native_policy_root`、`pre_cap_final_root`、
`rank_contract_root` 和 `rank_order_root` 全部 exact equality。Source audit 与
independent verifier 必须同时证明三个 read count
为 0；只比较 final count 不够。
PreCap receipt 的 attempt/execution binding/controller/receiver/step/input-state/
transition/final/source roots 必须与 referenced ProcessLaunch receipt exact equality；
任一 cross-process graft 都以 `G3-PRECAP-PROCESS-RECEIPT-MISMATCH` 拒绝。

### 3.4 CommonBudgetReducerV2

`DemandVectorV2` exact keys 为
`schema,event_units,token_units,retrieval_units,demand_root`；三个 value 都是 exact
non-negative integer，root 排除自身并使用 `g3-demand-vector-v2`。Aggregate demand
必须从对应 rows 独立求和，不接受自报 total。

`RankContractV2` exact keys 为：

```text
schema="pheroos-rglf-rank-contract-v2"
controller_id
ranking_contract_id
priority_parser="unsigned-fixed-q9-decimal"
priority_grammar="^(0|[1-9][0-9]*)\\.[0-9]{9}$"
priority_quantum="0.000000001"
priority_rounding="ROUND_HALF_EVEN"
ordered_rank_key_spec
nan_allowed=false
infinity_allowed=false
duplicate_event_id_allowed=false
rank_contract_root
```

Closed rank-key mapping：

```text
F,P,S,B,Q,G / priority-event-v2:
  (-Decimal(priority_decimal), event_id UTF-8 ascending)

R / r-subject-member-v2:
  (native_group_rank_ordinal ascending,
   native_member_rank_ordinal ascending,
   event_id UTF-8 ascending)
```

R group ordinal 已由
`(-Decimal(native_group_priority_decimal),native_group_id UTF-8 ascending)` 导出，
member ordinal 已由 Section 3.3 的 recency/dose/event comparator 导出。这个 R full
ranking 同时用于 natural、iso 和 sweep；natural 另外应用 4-group/2-member predicate，
iso/sweep 只应用公共 cap。不得在 iso/sweep 回落到 priority/event-id tie-break。

Root 排除自身并使用 `g3-rank-contract-v2`。`rank_order_root` 使用 label
`g3-rank-order-v2`，preimage 是按对应 contract 排序的
`(rank_ordinal,event_id,priority_decimal,priority_quantum,native_group_id,
native_group_priority_decimal,native_group_rank_ordinal,
native_member_rank_ordinal)` rows，nullable fields 显式 null。

`BudgetSelectedRowV2` exact keys：

```text
schema="pheroos-rglf-budget-selected-row-v2"
budget_entry_root
event_id
rank_ordinal
demand_root
counters_before_root
counters_after_root
row_root
```

`BudgetDropRowV2` exact keys：

```text
schema="pheroos-rglf-budget-drop-row-v2"
budget_entry_root
event_id
rank_ordinal
demand_root
drop_reason
counters_before_root
proposed_counters_root
scan_continued=true
row_root
```

Row roots 分别排除自身并使用
`g3-budget-selected-row-v2|g3-budget-drop-row-v2`。Drop reason closed enum：

```text
native_limit
event_cap
token_cap
retrieval_cap
```

Natural 只允许 `native_limit`；iso/sweep 禁止 `native_limit`。多重 cap 超限 precedence
固定 `event_cap > token_cap > retrieval_cap`。

Reducer exact keys 固定为：

```text
schema="pheroos-rglf-common-budget-reducer-v2"
basis_root
pre_cap_final_root
pre_cap_execution_receipt_root
budget_entry_root
budget_layer_id
controller_config_root
controller_input_state_root
native_policy_root
rank_contract_root
rank_order_root
backfill_enabled=true
common_eligible_demand_root
ranked_demand_root
controller_filtered_demand_root
selected_rows_root
drop_rows_root
selected_ids_root
budget_dropped_ids_root
selected_demand_root
budget_dropped_demand_root
selection_order_root
payload_order_root
reducer_root
```

Partition invariants：

```text
common eligible
  = controller_filtered disjoint-union ranked
ranked
  = selected disjoint-union budget_dropped
```

`ranked_demand_root` 绑定 ranked rows 的 event/token/retrieval sums；
`controller_filtered_demand_root` 单独报告 filtered sums，不能消失或伪装为 budget
drop；两者之和必须等于 `common_eligible_demand_root`。

Root recipes：

```text
selected_rows_root =
  digest_json("g3-budget-selected-rows-v2",
              selected rows in rank order)
drop_rows_root =
  digest_json("g3-budget-drop-rows-v2",
              drop rows in rank order)
selected_ids_root =
  digest_json("g3-budget-selected-ids-v2",
              selected event IDs in rank order)
budget_dropped_ids_root =
  digest_json("g3-budget-dropped-ids-v2",
              dropped event IDs in rank order)
selection_order_root =
  digest_json("g3-budget-selection-order-v2",
              selected event IDs in rank order)
payload_order_root =
  digest_json("g3-budget-payload-order-v2",
              selected event rows ordered by
              (logical_time ascending,event_id ascending), each row exact
              (logical_time,event_id))
reducer_root =
  digest_json("g3-common-budget-reducer-v2",
              reducer record without reducer_root)
```

`native_policy_root` 必须匹配 controller config，并在每个 layer 保持相同 identity。
Reducer 按 rank 逐行执行：

1. Natural 时先应用 native policy：`all_eligible` 永不 native-drop；
   `flat_rank_limit` 在 `rank_ordinal>=flat_event_limit` 时 drop；
   R 在 `native_group_rank_ordinal>=group_cap` 或
   `native_member_rank_ordinal>=members_per_group_cap` 时 drop。该 drop reason 固定
   `native_limit`，并继续扫描；
2. Iso/sweep 禁止应用 native policy；计算加入 candidate 后的
   event/token/retrieval totals；
3. 若任一 cap 超限，将 candidate 放入 `budget_dropped`；
4. 多重超限的 reason precedence 固定为
   `event_cap > token_cap > retrieval_cap`；
5. drop 后继续扫描后续 candidate，即 backfill；
6. 未超限则加入 selected；
7. ranking 扫描结束后一次性关闭 selected/dropped roots。

Common reducer 对每个 envelope 只执行一次。Pre-cap rank、filtered、selected、
budget-dropped、selection-order 和 payload-order roots 必须都进入 run/trace lineage。
Selection order 按 rank；payload order 按现有 canonical temporal contract。Reducer
operations 属于调用它的 controller envelope；公共 basis/schedule construction 属于
shared `common_eligibility`，二者不得重复记账。

Model/tool caps 在 AttemptPolicyV2 的 bundle-level call ledger 校验，不参加 per-event
backfill。本 provider-free G3 路径要求 actual model/tool calls 均为零；adapter disabled
时出现任一 call occurrence 立即拒绝。

### 3.5 Budget-free public episode identity

`PublicEpisodeCommitmentV2` 不含 controller、budget regime、ratio 或 cap。Exact keys：

```text
schema="pheroos-rglf-public-episode-commitment-v2"
active_planning_cell_root
source_profile_chain_root
matrix_kind
task_id
split
seed
repeat_id
agent_count
event_count
steps
attack_severity
task_size_profile_root
receiver_universe_root
event_set_root
declared_subjects_root
declared_candidates_root
ligand_topologies_root
environment_parameters_root
public_episode_payload_root
budget_free=true
arm_free=true
authority_scope="none"
commit_authority=false
outcome_authorized=false
sealed_evaluator_enabled=false
provider_adapter_enabled=false
public_episode_commitment_root
```

```text
public_episode_payload_root =
  digest_json("g3-public-episode-payload-v2", {
    receiver_universe_root,
    event_set_root,
    declared_subjects_root,
    declared_candidates_root,
    ligand_topologies_root,
    environment_parameters_root
  })

public_episode_commitment_root =
  digest_json("g3-public-episode-commitment-v2",
              record without public_episode_commitment_root)
```

必须满足：

```text
PublicEnvironmentCellV05.planning_cell_root
  == active_planning_cell_root
LazyEpisodeManifestBindingV05.environment_plan_root
  == active_planning_cell_root
ArmBudgetIntentV05.environment_plan_root
  == active_planning_cell_root
```

`planning_cell_root` 是 active planning object 的 computed root；
`environment_plan_root` 是 manifest/intent 内引用它的字段。禁止互换命名或计算一个新
planning root。

对每个 smoke/attack planning cell，按以下 exact layer order 唯一查找八个 active
`LazyEpisodeManifestBindingV05`：

| layer ID | regime | sweep ratio |
| --- | --- | --- |
| `natural` | `natural` | `not_applicable` |
| `iso` | `iso` | `not_applicable` |
| `sweep:0.10` | `sweep` | `0.10` |
| `sweep:0.20` | `sweep` | `0.20` |
| `sweep:0.35` | `sweep` | `0.35` |
| `sweep:0.50` | `sweep` | `0.50` |
| `sweep:0.75` | `sweep` | `0.75` |
| `sweep:1.00` | `sweep` | `1.00` |

每项必须保持 active constructor：

```text
lazy_manifest_root =
  digest_json("g2-lazy-episode-manifest-binding-v0.6",
              exact LazyEpisodeManifestBindingV05 dictionary)
```

且 `environment_plan_root`、counterfactual pair、axes、layer fields、
`episode_manifest_materialized=false`、`evaluator_enabled=false` 和
`outcome_authorized=false` 全部 exact。

同一个 `PublicEpisodeCommitmentV2` materialize 八个 budget-bound
`EpisodeManifestV1`。八项 receiver/event/subject/candidate/topology/environment
components 必须 byte-exact 相同；只允许 episode ID 与 budget object 不同。
`EpisodeManifestV1.root` 继续使用 active
`digest_json("episode-manifest-v1",manifest.public_dict())`，不得改写 V1 root recipe。

Budget marker exact fields：

```text
natural:
  regime=natural
  event_cap=null
  token_cap=null
  retrieval_cap=null
  model_call_cap=1
  tool_call_cap=1
  deadline_seconds=30.0

iso:
  regime=iso
  event_cap=8
  token_cap=512
  retrieval_cap=8
  model_call_cap=1
  tool_call_cap=1
  deadline_seconds=30.0

all sweep layers:
  regime=sweep
  event_cap=null
  token_cap=null
  retrieval_cap=null
  model_call_cap=1
  tool_call_cap=1
  deadline_seconds=30.0
```

Sweep null caps 表示 effective caps 只来自 `BudgetScheduleV2`；把 V1 budget marker 当作
unbounded execution、保留当前 `(0,0,0)` placeholder 或从 marker 读取 effective cap
均拒绝。Episode ID 沿用冻结格式：

```text
episode:{task_lower}:{split}:{seed}:r{repeat_id}:
a{agent_count}:e{event_count}:s{steps}:x{severity_2dp}:
b{budget_regime}:w{ratio_or_0.00}
```

`EpisodeMaterializationBindingV2` exact keys：

```text
schema="pheroos-rglf-episode-materialization-binding-v2"
planning_cell_root
environment_plan_root
public_episode_commitment_root
budget_layer_id
lazy_manifest_root
materialized_episode_manifest_root
budget_schedule_set_root
public_components_equal=true
effective_budget_source="BudgetScheduleV2"
binding_root
```

Binding root 排除自身并使用 `g3-episode-materialization-binding-v2`。
这里的 `budget_schedule_set_root`、execution envelope 和下述
`ArmBudgetExecutionBindingV2.budget_schedule_set_root` 必须 exact equality；不存在
隐含或未声明的 schedule-program artifact。

对每个 arm/layer，从 active matrix 唯一查找 `ArmBudgetIntentV05` 并要求：

```text
intent.environment_plan_root=planning_cell_root
intent.episode_manifest_root=lazy_manifest_root
intent.budget_layer_id=budget_layer_id
intent.controller_id=arm
intent.controller_execution=false
intent.evaluator_enabled=false
intent.outcome_authorized=false
```

注意 active intent 的 `episode_manifest_root` 引用 lazy binding，不是 materialized
`EpisodeManifestV1.root`。新 execution binding 只能扩展它：

```text
schema="pheroos-rglf-arm-budget-execution-binding-v2"
planning_cell_root
public_episode_commitment_root
active_arm_budget_intent_root
active_lazy_manifest_root
materialized_episode_manifest_root
episode_materialization_binding_root
budget_schedule_set_root
controller_config_root
sealed_evaluator_enabled=false
provider_adapter_enabled=false
authority_scope="none"
commit_authority=false
execution_binding_root
```

Root 排除自身并使用 `g3-arm-budget-execution-binding-v2`。固定一个 arm 得到八个 lazy
roots、八个 materialized manifest roots、八个 active intent roots 和八个 execution
roots；跨七 arms 是 56 个 intent/execution bindings，不能把一个 environment 的
layer count 与 arm-layer count 混写。

## 4. S/G size policy

### 4.1 S

Primary qualification key：

```text
(task_family, agent_count), agent_count in {4,16}
```

N=4 必须 exact replay 现有 artifact；N=16 从真实 receiver/ACL universe 重新运行相同
dev-only candidate、metric 和 tie-break。拟冻结的最小 corpus：

```text
agent_count=4 or 16
event_count=max(8,agent_count)
steps=2
attack_severity=0.25
budget_layer_id=natural
repeat_id=0
dev seeds=2000..2029
task sizes=small
```

`SGraphConstructorV2` 的 closed inputs 是：

```text
task_family
agent_count
graph_name
matched_degree
dev_declaration_root
receivers sorted by receiver_id
per-receiver tenant_id, grants, capabilities
constructor_version
```

它不得接收 event payload/tags、future schedule、sidecar 或 outcome。每条 edge 的 source
和 destination 都必须属于同一 `receiver_universe_root`，禁止 self-edge；edge 只在
source/destination tenant 相同且 grants/scopes 的冻结 ACL predicate 允许时成立。T7 的
两个 tenant partitions 分别构图，禁止跨 partition edge。

每个 size artifact 分开绑定：

```text
constructor_config_root
receiver_universe_root
source_partition_root
destination_partition_root
acl_partition_root
dev_declaration_root
dev_sidecar_selection_root
R_density_reference_root
candidate_edge_set_roots
selected_edge_set_root
derived_graph_root
selection_metrics_root
selection_rule
physical_cost_root
```

Root recipes 使用项目 `digest_json(label,payload)`：

```text
receiver_universe_root =
  digest_json("s-v2-receiver-universe", ordered public receiver records)
source_partition_root =
  digest_json("s-v2-source-ids", ordered unique edge source IDs)
destination_partition_root =
  digest_json("s-v2-destination-ids", ordered unique edge destination IDs)
acl_partition_root =
  digest_json("s-v2-acl-partitions",
              ordered (receiver_id,tenant_id,sorted grants) rows)
selected_edge_set_root =
  digest_json("s-v2-selected-edges",
              ordered (source_id,destination_id) rows)
derived_graph_root =
  digest_json("s-v2-derived-graph", {
    constructor_config_root,
    receiver_universe_root,
    source_partition_root,
    destination_partition_root,
    acl_partition_root,
    selected_edge_set_root
  })
```

Candidate edge sets 使用同一 edge-root recipe 和各自 graph name/degree config；所有 ID
按 Unicode code-point/UTF-8 canonical text order，edge 按 `(source_id,destination_id)`
排序。

Source/destination/ACL roots 不能合并成一个含义不明的 graph root。把 N=4 exact graph
加载到 N=16 必须因 receiver-universe mismatch 拒绝。

`SArtifactMigrationReceiptV1ToV2`：

- 对 N=4 绑定 immutable v1 artifact、v2 artifact 和两者的 canonical edge bytes；
- 只在 edge bytes、graph name、degree 和 v1 selection payload exact 相等时报告
  `payload_preserved=true`；
- v2 因新增 size/ACL/source/destination bindings 可有新的 artifact root，禁止覆写 v1；
- N=16 写 `migration_kind=new_size_qualification`，不能伪称 v1 migration；
- 所有 equality fields 都是未来 observed values，本 draft 不预填结果。

Scale：

- N=4/N=16 可加载匹配 graph；
- N=64/256/1024 从 N=16 frozen `graph_name+degree` 在真实 receiver/ACL universe
  重新实例化；
- receipt 固定 `scale_extrapolation=true`、`outcome_qualified=false`；
- graph build/read 进入 actual cost。

全部 `140` scale environments 与 `980` intents 分别引用 active
`PublicEnvironmentCellV05.planning_cell_root`、lazy manifest root 与
`ArmBudgetIntentV05.root`；constructor 另绑定 task、size pair、seed `9000/9001` 和
repeat_id `0/1`。Execution receipt 不得改变 planning axes 或把 cost-only
extrapolation升级为 v0.5 outcome evidence。

N>=64 的 S reconstruction 必须在 controller activation 前形成 closed
`SScaleOODExtrapolationReceiptV2`，exact keys：

```text
schema="pheroos-rglf-s-scale-ood-extrapolation-receipt-v2"
active_planning_cell_root
active_arm_budget_intent_root
matrix_kind="scale"
split="smoke"
task_id
seed
repeat_id
agent_count
event_count
steps=50
budget_layer_id="natural"
source_agent_count=16
source_s_size_qualification_root
source_s_derived_graph_root
source_s_constructor_config_root
destination_receiver_universe_root
destination_acl_partition_root
destination_s_constructor_config_root
destination_s_selected_edge_set_root
destination_s_derived_graph_root
destination_s_controller_config_root
graph_construction_physical_pool_root
source_parameters_exact=true
destination_graph_reconstructed=true
pre_execution_binding=true
out_of_support=true
scale_cost_only=true
outcome_qualified=false
sealed_evaluator_enabled=false
provider_adapter_enabled=false
authority_scope="none"
commit_authority=false
receipt_root
```

Root 使用 `g3-s-scale-ood-extrapolation-receipt-v2`。Receipt 单向引用独立构造的 S
controller config；`ControllerInputStateV2.ordered_state_dependency_roots` 必须引用该
receipt 与 exact destination graph。Source N=16 edge set 不得作为 destination ranking graph。Graph
construction cost pool 必须在 receipt 前关闭且只计一次。N=4/N=16 不生成该 receipt。
Controller config 必须先独立构造且不引用 receipt/self：

```text
destination_s_controller_config_root =
  digest_json("g3-s-scale-controller-config-v2", {
    destination_s_constructor_config_root,
    destination_s_selected_edge_set_root,
    destination_s_derived_graph_root
  })
```

### 4.2 G

Checkpoint key：

```text
(task_family, agent_count), agent_count in {4,16}
```

每个 checkpoint 使用匹配的 S root，并保持 10-field allowlist、Decimal-34、
`ROUND_HALF_EVEN`、canonical full batch、54-point grid、train `1000..1029`、dev
`2000..2029`。N=4 exact replay；N=16 独立训练/selection，禁止 fallback 到 N=4。
Label counts、class weights、grid metrics、native-k、training cost 和 checkpoint 均按
size 冻结。

`GCheckpointMigrationReceiptV1ToV2` 对 N=4 绑定 immutable v1 checkpoint payload 与 v2
size-qualified wrapper；只有 weights、hyperparameters、feature order、train/dev payload
和 selected native-k exact 相等时才能报告 `payload_preserved=true`。V2 必须新增匹配
的 S derived graph、receiver universe、CostOntologyV2 和 training-callsite bindings，
不能覆写 v1。N=16 固定为 `migration_kind=new_size_training`。

N>=64 scale 可加载 N=16 checkpoint，但 `ScaleOODTransferReceiptV2` 只适用于
`agent_count in {64,256,1024}`，exact keys：

在任何 G ranking/PreCap 前，先 materialize
`GScaleControllerInputBindingV2`：

```text
schema="pheroos-rglf-g-scale-controller-input-binding-v2"
active_planning_cell_root
active_arm_budget_intent_root
matrix_kind="scale"
split="smoke"
task_id
seed
repeat_id
agent_count
event_count
steps=50
budget_layer_id="natural"
source_agent_count=16
source_g_checkpoint_root
source_s_derived_graph_root
checkpoint_bound_s_graph_root
destination_s_ood_extrapolation_receipt_root
destination_receiver_universe_root
destination_acl_partition_root
destination_s_constructor_config_root
destination_s_selected_edge_set_root
destination_s_derived_graph_root
feature_allowlist_root
frozen_g_numeric_config_root
controller_config_root
pre_execution_binding=true
out_of_support=true
scale_cost_only=true
outcome_qualified=false
sealed_evaluator_enabled=false
provider_adapter_enabled=false
binding_root
```

Root 使用 `g3-g-scale-controller-input-binding-v2`。Source checkpoint/S binding 必须是
exact N=16 pair；G binding 与 referenced S OOD receipt 的 planning root、matrix/split、
task、seed、repeat、agent/event counts、steps、budget layer 及全部 destination fields
必须 exact equality。两项 active intent 分别必须是同一 planning cell 的 G-natural 与
S-natural intent，不能跨 cell/seed 拼接。
`controller_config_root` 必须先独立构造，且不得引用 binding 或自身：

```text
controller_config_root =
  digest_json("g3-g-scale-controller-config-v2", {
    source_g_checkpoint_root,
    destination_s_selected_edge_set_root,
    destination_s_derived_graph_root,
    feature_allowlist_root,
    frozen_g_numeric_config_root
  })
```

随后 binding 单向引用该 config root。G 的
`ControllerInputStateV2.state_dependency_kind` 在 N>=64 固定为
`ood_checkpoint_destination_graph_and_seen_clusters`，ordered dependencies 必须包含
本 binding、source checkpoint、destination graph 和 prior seen-clusters roots。
不得把 post-execution receipt 当 activation input。

随后 `ScaleOODTransferReceiptV2` 只适用于
`agent_count in {64,256,1024}`，exact keys：

```text
schema="pheroos-rglf-g-scale-ood-transfer-v2"
active_planning_cell_root
active_arm_budget_intent_root
matrix_kind="scale"
split="smoke"
task_id
seed
repeat_id
agent_count
event_count
steps=50
budget_layer_id="natural"
source_agent_count=16
g_scale_controller_input_binding_root
source_g_checkpoint_root
source_s_derived_graph_root
checkpoint_bound_s_graph_root
destination_receiver_universe_root
destination_acl_partition_root
destination_s_constructor_config_root
destination_s_selected_edge_set_root
destination_s_derived_graph_root
feature_allowlist_root
pre_cap_final_root_count
ordered_pre_cap_final_roots_root
post_execution_projection_input_root
is_frozen_s_edge_projection_root
source_checkpoint_exact=true
source_s_binding_exact=true
destination_graph_reconstructed=true
out_of_support=true
scale_cost_only=true
outcome_qualified=false
sealed_evaluator_enabled=false
provider_adapter_enabled=false
authority_scope="none"
commit_authority=false
transfer_root
```

`checkpoint_bound_s_graph_root == source_s_derived_graph_root`；source checkpoint
必须属于 exact `(task_id,N=16)`；destination graph 必须属于 exact destination
task/receiver/ACL universe，使用冻结 N=16 `graph_name+degree` 重新构造但不得复制 N=16
edge IDs。Receipt 的 active planning/intent、matrix/split/task/seed/repeat/N/E/steps/layer
及全部 source/destination/config fields 必须与 pre-execution G binding exact equality。

Feature allowlist 顺序固定为：

```text
intercept
tag_jaccard
role_exact
capability_jaccard
inverse_one_plus_age
clamped_strength
is_superseding
version_over_max_visible_version
is_new_verified_cluster
is_frozen_s_edge
```

Allowlist root 使用 `g3-g-feature-allowlist-v2`。该 receipt 是 controller execution
完成后的 lineage/feature audit，不是 pre-execution activation input；因此其 projection
root 不得被 AttemptIdentity、activation、basis、schedule 或 PreCap 反向引用。

Pre-cap final set rows 的 exact keys 为
`receiver_id,logical_step,pre_cap_final_root`，按
`(receiver_id,logical_step)` 排序。Count 必须为 `agent_count*steps`，每个
receiver-step 恰好一行，并与 destination receiver universe 及 frozen step range 完全
覆盖：

```text
ordered_pre_cap_final_roots_root =
  digest_json("g3-g-scale-pre-cap-final-roots-v2",
              ordered final-set rows)
```

Projection rows 按
`(receiver_id,logical_step,event_id)` 排序，exact keys 是
`basis_root,receiver_id,logical_step,event_id,event_actor_id,
destination_s_derived_graph_root,is_frozen_s_edge`，其中：

```text
is_frozen_s_edge =
  1 iff (event_actor_id,receiver_id)
  is in destination_s_selected_edge_set
  else 0

post_execution_projection_input_root =
  digest_json("g3-g-scale-post-execution-projection-input-v2", {
    pre_cap_final_root_count,
    ordered_pre_cap_final_roots_root,
    destination_s_derived_graph_root,
    feature_allowlist_root
  })

is_frozen_s_edge_projection_root =
  digest_json("g3-g-scale-is-frozen-s-edge-projection-v2",
              ordered projection rows)

transfer_root =
  digest_json("g3-g-scale-ood-transfer-v2",
              receipt without transfer_root)
```

Projection rows 必须与上述 final set 中全部 `ranked` rows 一对一覆盖；controller-filtered
rows 不进入 G feature projection，但其存在仍由各 PreCapFinal coverage root 证明。
任何 missing/extra/duplicate receiver-step 或 event row 均拒绝。

禁止使用 source N=16 exact edges 计算 destination projection bit。它只支持
provider-free cost mechanics。未来若要产生 N>16 outcome，必须在 unblinding 前新增 size
qualification。

## 5. P decision

P 在当前 strict goal 内保持 blocked。

合法修复需要 versioned **Hybrid Replay v3** 与 lifecycle receipt。Identity 至少绑定
step、parent head、transition kind、policy、topology 和 upstream lineage；payload 至少
绑定 before/after strength、transition inputs/output 和 canonical state root。还需要
v2-to-v3 migration、Trace、Conformance、TCK 更新以及新 contract/controller version 的
明确 authority。

这些 production-surface changes 不在当前 authority 内。未来的“新 authority”只表示
允许扩大 core change scope；它本身不构成 contract 通过、P qualification 或 scientific
result。获权后的第一条实现也必须使用新 diagnostic controller ID：

```text
P-v3-diagnostic
```

该 ID 排除在 frozen primary arms、primary ITT consumer set 和 hypothesis comparisons
之外。
只有 migration、Trace、Conformance、TCK 和 independent diagnostic 全部通过，并另行
预注册 comparator promotion 后，才可讨论新的 primary controller ID；不得把 diagnostic
receipt 追溯标成 primary P。

本 branch 禁止用 zero decay、删除 diffusion、旧 ID 复用、one-step replay、external
shim 或 minimal scalar substitute 伪装成 P 通过。Primary P intent 也不得从 expected
matrix 删除。

T1/F slice 可独立资格化，但 `G3-P-LIFECYCLE` 和 aggregate G3 保持 blocked，直到取得新
authority 并完成独立 versioned change。

## 6. Cost Ledger v2

### 6.1 CostOntologyV2

`CostOntologyV2` 是 closed、ordered、versioned ontology。它固定以下 59 fields，顺序是
canonical serialization order：

```text
01 eligible_events
02 eligible_event_bytes
03 selected_events
04 selected_event_bytes
05 prompt_tokens
06 completion_tokens
07 reasoning_tokens
08 cached_tokens
09 controller_operations
10 index_build_operations
11 index_query_operations
12 graph_build_operations
13 graph_read_operations
14 state_serialization_operations
15 state_serialization_bytes
16 state_hash_operations
17 state_hash_bytes
18 storage_reads
19 storage_writes
20 storage_read_bytes
21 storage_write_bytes
22 p_store_operations
23 p_store_bytes
24 p_replay_operations
25 p_replay_events
26 p_replay_bytes
27 b_append_history_operations
28 b_append_history_events
29 b_append_history_bytes
30 q_rebuild_operations
31 q_tokenize_operations
32 q_tokenized_bytes
33 q_query_operations
34 s_frozen_graph_build_operations
35 s_frozen_graph_read_operations
36 s_frozen_graph_bytes
37 g_train_operations
38 g_inference_operations
39 g_checkpoint_operations
40 g_checkpoint_bytes
41 g_amortized_training_operations
42 r_field_update_operations
43 r_diffusion_operations
44 r_receptor_operations
45 model_calls
46 tool_calls
47 retries
48 timeouts
49 partial_work_operations
50 partial_work_bytes
51 trace_bytes
52 shared_generator_operations
53 shared_generator_bytes
54 common_eligibility_operations
55 common_eligibility_bytes
56 sealed_evaluator_operations
57 sealed_evaluator_bytes
58 ndjson_flush_operations
59 ndjson_flush_bytes
```

任何 cost vector 必须编码为长度恰好 59 的 ordered array，而不是依赖 object insertion
order：

```text
[
  {"ordinal":1,"field":"eligible_events","value":...},
  ...
  {"ordinal":59,"field":"ndjson_flush_bytes","value":...}
]
```

Ordinal/name 必须与 ontology exact match；value 只能是 non-negative integer 或 literal
`not_applicable`。

Applicability sets 使用上表的 field names，serialization 仍按 01..59 顺序：

```text
CONTROLLER_COMMON =
  eligible_events,eligible_event_bytes,selected_events,selected_event_bytes,
  prompt_tokens,completion_tokens,reasoning_tokens,cached_tokens,
  controller_operations,
  state_serialization_operations,state_serialization_bytes,
  state_hash_operations,state_hash_bytes,
  storage_reads,storage_writes,storage_read_bytes,storage_write_bytes,
  model_calls,tool_calls,retries,timeouts,
  partial_work_operations,partial_work_bytes,trace_bytes

F = CONTROLLER_COMMON
B = CONTROLLER_COMMON +
    b_append_history_operations,b_append_history_events,b_append_history_bytes
P = CONTROLLER_COMMON +
    p_store_operations,p_store_bytes,
    p_replay_operations,p_replay_events,p_replay_bytes
Q = CONTROLLER_COMMON +
    index_build_operations,index_query_operations,
    q_rebuild_operations,q_tokenize_operations,q_tokenized_bytes,
    q_query_operations
S = CONTROLLER_COMMON +
    graph_build_operations,graph_read_operations,
    s_frozen_graph_build_operations,s_frozen_graph_read_operations,
    s_frozen_graph_bytes
G = CONTROLLER_COMMON +
    graph_read_operations,s_frozen_graph_read_operations,
    g_train_operations,g_inference_operations,
    g_checkpoint_operations,g_checkpoint_bytes,
    g_amortized_training_operations
R = CONTROLLER_COMMON +
    graph_read_operations,
    r_field_update_operations,r_diffusion_operations,r_receptor_operations

SHARED_STATE =
  state_serialization_operations,state_serialization_bytes,
  state_hash_operations,state_hash_bytes,
  storage_reads,storage_writes,storage_read_bytes,storage_write_bytes,
  trace_bytes

shared_generator = SHARED_STATE +
  shared_generator_operations,shared_generator_bytes
common_eligibility = SHARED_STATE +
  eligible_events,eligible_event_bytes,
  common_eligibility_operations,common_eligibility_bytes
budget_schedule = SHARED_STATE
g_training = SHARED_STATE +
  g_train_operations,g_checkpoint_operations,g_checkpoint_bytes,
  g_amortized_training_operations
sealed_evaluator = SHARED_STATE +
  sealed_evaluator_operations,sealed_evaluator_bytes
ndjson_flush = SHARED_STATE +
  ndjson_flush_operations,ndjson_flush_bytes
```

上表是 component family 的 potential-field superset，不是单一 view 的最终 profile。
Exact applicability key 必须同时包含
`component_kind,component_id,component_version,phase_id,slot_scope_kind,
view_selector,ontology_root`；未列或被该 view 排除的 field 必须
`not_applicable`。Diagnostic IDs 使用独立 profile，不能借用 primary P profile。

每个 ontology version 同时冻结 component-version applicability table。每个 field value
只能是 exact non-negative integer 或 literal `not_applicable`；measured zero、missing、
not invoked 和 not applicable 是不同状态。Unknown/reordered/omitted field 均拒绝。

Physical view 中 field 只汇总其唯一 callsite occurrences；derived allocation 只允许进入
allocated view。特别地，`g_amortized_training_operations` 在 physical view 必须是
`not_applicable`，在 allocated view 才能是整数。

Applicability/observation rows 不是 prose lookup。
`CostProfileDerivationProgramV2` exact keys：

```text
schema="pheroos-rglf-cost-profile-derivation-program-v2"
ontology_root
component_kind
component_id
component_version
phase_id
slot_scope_kind
physical_owner
potential_field_set_root
physical_field_mode_program_ast
allocated_field_mode_program_ast
observation_subject_kinds
ordered_observation_row_program_asts
program_root
```

两个 field-mode programs 必须对 ontology 的每个 ordinal 恰好返回一个 closed mode；
五个 observation programs 必须对每个 declared subject kind 恰好返回
`requirement_mode,api_id,unit,boundary_id,optional_missing_reason_universe`。Programs 只用
Section 8 typed AST，不能读 runtime result；root 使用
`g3-cost-profile-derivation-program-v2`。

Program roots 必须在 descriptor candidate 中逐 component/version/phase 预注册。
Expected universe 不由 ProgramSet 自报。独立的
`CostProfileDerivationExpectedProgramInventoryV2` exact keys：

```text
schema="pheroos-rglf-cost-profile-derivation-expected-program-inventory-v2"
methodology_body_root
ontology_root
catalog_version="g3-primary-cost-components-v2"
expected_program_key_count=14
ordered_expected_program_key_rows
ordered_expected_program_keys_root
inventory_root
```

`ordered_expected_program_key_rows` 每行 exact keys 是
`component_kind,component_id,component_version,phase_id,slot_scope_kind`，并且必须
byte-exact 等于下面按五项 UTF-8 排序的 literal 14-row universe：

| component_kind | component_id | component_version | phase_id | slot_scope_kind |
| --- | --- | --- | --- | --- |
| budget_schedule | budget_schedule | g3-budget-schedule-v2 | schedule_construction | budget_entry |
| common_eligibility_basis | common_eligibility | g3-common-eligibility-basis-v2 | eligibility_basis | receiver_step_basis |
| controller_attempt | B | g3-controller-B-v2 | controller_execution | intent_attempt |
| controller_attempt | F | g3-controller-F-v2 | controller_execution | intent_attempt |
| controller_attempt | G | g3-controller-G-v2 | controller_execution | intent_attempt |
| controller_attempt | P | g3-controller-P-v2 | controller_execution | intent_attempt |
| controller_attempt | Q | g3-controller-Q-v2 | controller_execution | intent_attempt |
| controller_attempt | R | g3-controller-R-v2 | controller_execution | intent_attempt |
| controller_attempt | S | g3-controller-S-v2 | controller_execution | intent_attempt |
| g_training | G | g3-g-training-v2 | checkpoint_training | checkpoint_training_pool |
| ndjson_flush | ndjson_flush | g3-ndjson-flush-v2 | attempt_flush | intent_attempt |
| ndjson_flush | ndjson_flush | g3-ndjson-flush-v2 | batch_close | batch_once |
| sealed_evaluator | sealed_evaluator | g3-sealed-evaluator-disabled-v2 | sealed_evaluation | intent_attempt |
| shared_generator | shared_generator | g3-shared-generator-v2 | episode_materialization | environment_once |

Keys root 使用 `g3-cost-profile-derivation-expected-program-keys-v2` 对 exact literal rows
计算；inventory root 排除自身并使用
`g3-cost-profile-derivation-expected-program-inventory-v2`。Independent verifier 必须
从本 methodology body 的 literal table 重建 count/rows/root；artifact 中删行、加行、
改 version/phase/scope 或仅同步修改自报 count/root 都拒绝。Inventory artifact 引用
pre-existing `methodology_body_root`，不进入 body root preimage。

`CostProfileDerivationProgramSetV2` exact keys：

```text
schema="pheroos-rglf-cost-profile-derivation-program-set-v2"
ontology_root
expected_program_inventory_root
expected_program_key_count
ordered_expected_program_keys_root
ordered_expected_program_bindings_root
program_count
ordered_program_registration_rows_root
ordered_program_roots
missing_count
extra_count
duplicate_key_count
duplicate_root_count
program_set_root
```

Expected key rows/count/root 必须从 referenced
`CostProfileDerivationExpectedProgramInventoryV2` 原样引用并 exact equality，不能由
ProgramSet producer 选择；`ProgramSet.ontology_root` 必须 exact 等于
`ExpectedInventory.ontology_root`。Expected key row exact keys 是
`component_kind,component_id,component_version,phase_id,slot_scope_kind`；
expected-binding/program-registration row 在这五项后增加 `program_root`，全部按五项
UTF-8/ordinal canonical key 排序。Expected key/binding rows 是 inactive methodology
review candidate 的 immutable input，keys projection 必须 exact equality；
registration rows 必须与 expected-binding rows byte-exact 相等，并且每个
`program_root` 所指
`CostProfileDerivationProgramV2` 的五项 identity、ontology 和 root 都独立验证。
Roots 使用
`g3-cost-profile-derivation-expected-program-keys-v2`、
`g3-cost-profile-derivation-expected-program-bindings-v2`、
`g3-cost-profile-derivation-program-registration-rows-v2`、
`g3-cost-profile-derivation-program-set-v2`；四个 defect counts 必须为 0，
`program_count=expected_program_key_count`。Program set root 必须被
`ContractDescriptorSetV1`、inactive profile review receipt 与 activated profile
共同绑定；activation allowlist 不允许改变 program 或 set artifact。因此 runtime
不能新增、替换或选择未审 program root。

Normative row semantics：

- controller-attempt physical：arm potential fields 为 `physical`；allocated：
  同 fields 为 `allocated_copy`；
- shared generator/common eligibility/budget schedule/NDJSON/sealed evaluator
  physical：其 potential fields 为 `physical`；若分摊，allocated 对应 fields 为
  `allocated_share`；
- G training physical：training/checkpoint potential fields 为 `physical` 且
  `g_amortized_training_operations=N/A`；allocated：`g_train_operations=N/A`，
  amortized field 为 `allocated_share`，允许同名 checkpoint fields 按 Section 6.3
  分摊；
- 所有非 potential 或被 view 排除的 field 一律 N/A。

对启用 observation 的 subject，wall/cpu/latency/peak-allocation 固定 required，
peak-RSS 固定 optional 且 optional reasons 只用本节三项；未启用 subject 不产生 profile。
任何不同 mapping 都要求新 descriptor/program version，不能由 runtime 选择。

Pre-execution `CostComponentPlanEntryV2` exact keys 为：

```text
schema="pheroos-rglf-cost-component-plan-entry-v2"
component_kind
component_id
component_version
phase_id
slot_scope_kind
physical_owner
allowed_view_selectors
observation_subject_kinds
profile_derivation_program_root
entry_root
```

`allowed_view_selectors` 只能是 canonical `("physical","allocated")` 或经 descriptor
明确限制的一个非空子集。`observation_subject_kinds` 是
`attempt|physical_pool` 的 canonical ordered subset；empty 表示该 entry 不生成
observation profile。Program identity fields、potential set、views/subjects 与 entry
必须 exact equality。`CostComponentPlanV2` exact keys 是
`schema,batch_profile_root,ontology_root,
cost_profile_derivation_program_set_root,entry_count,
ordered_component_plan_entry_roots,component_key_set_root,component_plan_root`；
entry 按
`(component_kind,component_id,component_version,phase_id,slot_scope_kind)` 排序且 key
不得重复，roots 分别使用
`g3-cost-component-plan-entry-v2|g3-cost-component-key-set-v2|
g3-cost-component-plan-v2`。每个 entry 的 `profile_derivation_program_root` 必须是
referenced reviewed program set 中同 key registration 的 exact member；缺失、额外或
key/root mismatch 均拒绝，不能由 component plan 自报新 program。
`ComponentPlan.ontology_root`、referenced ProgramSet/ExpectedInventory ontology root 和
每个 member Program 的 ontology root 必须全部 exact equality。

`CostApplicabilityProfileV2` exact keys：

```text
schema="pheroos-rglf-cost-applicability-profile-v2"
component_plan_entry_root
component_kind
component_id
component_version
phase_id
slot_scope_kind
view_selector
ontology_root
profile_derivation_program_root
field_mode_rows
profile_root
```

`field_mode_rows` 恰好 59 行，按 ontology ordinal，exact row keys 为
`ordinal,field_name,field_mode`；mode 只能是
`physical|allocated_copy|allocated_share|not_applicable`，并满足本节 physical/
allocated constraints。Profile root 使用 `g3-cost-applicability-profile-v2`。

完整 table 是 `CostApplicabilityProfileSetV2`，exact keys：

```text
schema="pheroos-rglf-cost-applicability-profile-set-v2"
ontology_root
component_plan_root
expected_profile_key_count
ordered_expected_profile_keys_root
profile_count
ordered_profile_roots
missing_count
extra_count
duplicate_count
profile_set_root
```

Expected key set 是每个 component-plan entry 与其每个 allowed view 的 exact cross
product，按上述 component key 后接 `view_selector` 排序；profile count 必须等于
expected count，三个 defect count 必须为 0。Expected-key/set roots 使用
`g3-cost-applicability-expected-keys-v2` 和
`g3-cost-applicability-profile-set-v2`。因此不存在 runtime default、family superset
fallback 或“未列即零”；independent verifier 从 component plan 重建 key set，并独立
执行每个 referenced derivation program 重建每个 59-row profile，要求 byte-exact
equality。ProfileSet、每个 Profile、ComponentPlan、ProgramSet、ExpectedInventory 与
Program 的 ontology roots 必须形成同一个 exact equality class。

### 6.2 ExpectedCostSlotProgramV2 与 AttemptPolicyV2

Root primitive 是项目 `digest_json(label,payload)`：UTF-8 canonical JSON、sorted keys、
无空白、禁止 NaN/Infinity，domain label 后接 NUL。所有 schema closed，nullable field
必须显式为 `null`；computed root 永不进入自身 preimage。

唯一合法 root DAG：

```text
methodology body literal table + reviewed ontology
  -> CostProfileDerivationExpectedProgramInventoryV2
       + expected program bindings + derivation programs
       -> CostProfileDerivationProgramSetV2
            -> CostComponentPlanV2
                 -> CostApplicabilityProfileSetV2 / CostObservationProfileSetV2

locked batch/policy/component roots
  -> AttemptIdentityV2 / PhysicalPoolIdentityV2
  -> ExpectedCostSlotV2 / activation decisions
  -> PhysicalOccurrenceV2 / CostObservationV2
  -> PhysicalPoolV2 / observed physical slots
  -> allocation plan/rows/pool
  -> observed allocated slots
  -> AttemptReceiptV2
  -> child retry activation
  -> batch close / CostAggregateV2
```

Slot、observation、occurrence、pool 或 allocation 不得引用当前/未来 final attempt receipt。

`AttemptPolicyV2` exact keys：

```text
schema="pheroos-rglf-attempt-policy-v2"
max_attempts
terminal_code_universe
terminal_status_map
retryable_terminal_codes
non_retryable_terminal_codes
retry_authorization_rule="explicit-retry-receipt-v2"
manual_rerun_allowed=false
attempt_policy_root
```

`max_attempts` 是 `>=1` integer。Closed terminal universe/status mapping：

```text
completed                 -> completed
completed_with_fallback   -> completed
controller_error          -> failed
timeout                    -> timed_out
crash                      -> crashed
oom_kill                   -> oom_killed
invalid_contract           -> invalid
invalid_bundle             -> invalid
quarantined                -> quarantined
partial_timeout            -> partial
partial_crash              -> partial
```

Retryable/non-retryable sets 必须互斥且并集等于 universe；`completed`、
`completed_with_fallback`、两个 invalid code 与 `quarantined` 必须 non-retryable。
Root 排除自身并使用 `g3-attempt-policy-v2`。

`AttemptIdentityV2` 在执行前冻结，exact keys：

```text
schema="pheroos-rglf-attempt-identity-v2"
batch_root
intent_root
run_plan_root
assignment_root
controller_id
budget_layer_id
attempt_ordinal
attempt_kind
parent_attempt_identity_root
attempt_policy_root
component_plan_root
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
outcome_authorized=false
attempt_identity_root
```

Root 排除自身并使用 `g3-attempt-identity-v2`。Ordinal 0 是
`initial,parent=null`；`0<k<max_attempts` 是 `retry`，parent 必须是同 intent 的 k-1
identity。Identity 不含 status、terminal、cost、observation、trace、allocation 或 final
receipt root。

`AttemptActivationDecisionV2` exact keys：

```text
schema="pheroos-rglf-attempt-activation-decision-v2"
attempt_identity_root
decision
reason_code
parent_activation_decision_root
parent_attempt_receipt_root
parent_terminal_code
retry_authorization_root
decision_root
```

Decision 是 `activated|not_activated`；reason closed enum 是
`initial_assignment|retry_authorized|parent_non_retryable|retry_denied|
parent_not_activated`。Ordinal 0 必须 `activated/initial_assignment` 且 parent fields
null。Child 只有在 parent receipt terminal retryable 且
`RetryAuthorizationV2.authorized=true` 时可 activated；parent 未激活时 child 必须
`not_activated/parent_not_activated`。Root 排除自身并使用
`g3-attempt-activation-decision-v2`。

`RetryAuthorizationV2` exact keys 是
`schema,child_attempt_identity_root,parent_attempt_receipt_root,
attempt_policy_root,authorized,decision_code,authority_scope,
commit_authority,outcome_authority,authorization_root`。Decision code 只能是
`authorized_by_policy|denied_by_policy`；三项 authority 固定
`none|false|false`；root 使用 `g3-retry-authorization-v2`。

为避免 scale materialize 巨大 list，`ExpectedCostSlotProgramV2` 可 streaming，但 inputs
必须完整绑定：

```text
batch_root
intent_set_root
ontology_root
applicability_table_root
observation_profile_set_root
attempt_policy_root
component_plan_root
canonical_axis_order_root
```

这里 `applicability_table_root` 必须 exact 等于
`CostApplicabilityProfileSetV2.profile_set_root`，且其 component plan/ontology roots
分别与 program fields exact equality。

`slot_namespace_root` 使用 label `g3-cost-slot-namespace-v2` 绑定上述 fields。
Program 按
`(scope,receiver,step,phase,attempt,component,view,field_ordinal)` 生成 exact 59-slot
arrays、chunk chain、expected count/root 和 final close；independent verifier 使用独立
generator 重算。

`ExpectedCostSlotV2` exact keys：

```text
schema="pheroos-rglf-expected-cost-slot-v2"
slot_namespace_root
batch_root
slot_scope_kind
slot_scope_root
intent_root
receiver_id
logical_step
phase_id
attempt_ordinal
attempt_identity_root
component_kind
component_id
component_version
field_ordinal
field_name
view_selector
applicability_profile_root
field_mode
expected_state
activation_rule
activation_plan_root
value_source_contract
expected_slot_root
```

Scope union：

```text
intent_attempt
environment_once
receiver_step_basis
budget_entry
checkpoint_training_pool
batch_once
```

Scope target root 固定为：

```text
intent_attempt            -> AttemptIdentityV2 root
environment_once          -> PublicEpisodeCommitmentV2 root
receiver_step_basis       -> CommonEligibilityBasisV2 root
budget_entry              -> BudgetScheduleEntryV2 root
checkpoint_training_pool  -> pre-execution GTrainingPlanV2 root
batch_once                -> immutable batch identity root
```

不得使用包含 occurrence 的 final PhysicalPool/AttemptReceipt 作为 scope root。
Intent-attempt 需要 intent/attempt；environment/batch/checkpoint scopes 的 receiver/step
必须 null；receiver-step/budget scopes 需要 receiver+step。
`view_selector=physical|allocated`。Field mode 是
`physical|allocated_copy|allocated_share|not_applicable`。Expected state 是
`required|conditional|not_applicable`；activation rule 是
`always|attempt_activated|phase_activated|attempt_and_phase_activated|
assigned_consumer_initial_attempt|never_not_applicable`；value source 是
`physical_occurrence_sum|physical_slot_copy|allocation_row|none`。

Physical view 只允许 physical/N-A；allocated view 只允许 allocated-copy/share/N-A。
Required 只配 `always`；conditional 必须绑定预冻结 activation plan；N-A 只配
`never_not_applicable+none`。Root 排除自身并使用 `g3-expected-cost-slot-v2`。

`PhaseActivationDecisionV2` exact keys 是
`schema,subject_identity_kind,subject_identity_root,phase_plan_root,decision,
reason_code,input_root,decision_root`。Subject 是 `attempt|physical_pool`，decision 是
`activated|not_activated`，reason 是
`enabled_by_plan|disabled_by_envelope|not_applicable_by_component`。它只能读预冻结
envelope/component plan，不得读 terminal、sidecar 或 future result；decision root
排除自身并使用 `g3-phase-activation-decision-v2`。

`ObservedCostSlotV2` exact keys：

```text
schema="pheroos-rglf-observed-cost-slot-v2"
expected_slot_root
attempt_activation_decision_root
phase_activation_decision_root
observed_state
exact_value
value_source_kind
occurrence_set_root
source_physical_slot_root
allocation_plan_root
allocation_pool_root
allocation_row_root
nonmaterialization_code
observed_slot_root
```

Observed state 是 `materialized|not_invoked|not_applicable`；value source 是
`physical_occurrence_sum|physical_slot_copy|allocation_row|none`；nonmaterialization
code 是 `attempt_not_activated|phase_disabled_by_plan|not_applicable_by_profile`。
Activated applicable slot 必须 materialized，即使 timeout/crash/partial。Measured zero
在 physical view 是 materialized integer 0 与该 field 的 canonical empty occurrence
set；allocated view 的 zero 必须由 zero-valued source physical slot 或 allocation row
导出。`not_invoked` 只允许 conditional 且必须引用 predicate-false decision；N-A 只允许
profile N-A。Physical slot只引用 field-filtered occurrence set；allocated-copy
exact-copy 一个 physical slot；allocated-share 只引用匹配 allocation plan/pool/row。
Root 使用 `g3-observed-cost-slot-v2`，不得引用
AttemptReceiptV2。

### 6.3 Occurrence、consumer 与 view selector

`PhysicalPoolIdentityV2` exact keys：

```text
schema="pheroos-rglf-physical-pool-identity-v2"
batch_root
pool_kind
physical_owner
scope_kind
scope_root
component_kind
component_id
component_version
phase_id
ontology_root
physical_applicability_profile_root
callsite_table_root
planned_axis_root
physical_pool_identity_root
```

Pool kind 是
`controller_attempt|shared_generator|common_eligibility_basis|budget_schedule|
g_training|ndjson_flush|sealed_evaluator`；root 使用
`g3-physical-pool-identity-v2`。Physical owner closed enum 是
`F|P|S|B|Q|G|R|shared_generator|common_eligibility|sealed_evaluator|ndjson_flush`。
Scope kind 是 6.2 的 union。Owner mapping：

```text
F/P/S/B/Q/G/R controller -> intent_attempt
shared_generator          -> environment_once
common basis              -> receiver_step_basis
schedule construction     -> budget_entry
G training                -> checkpoint_training_pool
NDJSON flush              -> batch_once or declared intent_attempt
```

Shared/common/G-training occurrence 禁止携带任意 consumer intent identity。
若 NDJSON flush 采用 `batch_once` scope，它只能在 batch close 后进入 aggregate，不得
反向附着到已生成的 AttemptReceipt；若需要进入 attempt receipt，必须预声明
`intent_attempt` scope 并在该 receipt 前关闭。禁止用 post-receipt batch pool 构造
parent attempt 的 allocated slot。

`PhysicalOccurrenceV2` ID：

```text
occurrence_id =
  digest_json("g3-physical-occurrence-id-v2", {
    batch_root,
    physical_pool_identity_root,
    physical_owner,
    scope_kind,
    scope_root,
    phase_id,
    component_kind,
    component_id,
    component_version,
    callsite_id,
    receiver_id,
    logical_step,
    local_ordinal
  })
```

Record exact keys 是
`schema,occurrence_id,batch_root,physical_pool_identity_root,physical_owner,scope_kind,scope_root,
phase_id,component_kind,component_id,component_version,callsite_id,receiver_id,
logical_step,local_ordinal,contributions,occurrence_root`。Contributions 是按 field ordinal
排序的非空 array：

```text
{"field_ordinal": integer,
 "field_name": exact ontology name,
 "value": positive integer}
```

Occurrence root 使用 `g3-physical-occurrence-record-v2`。同一 action 只有一个
occurrence/owner，但一个 occurrence 可同时贡献 operation/byte fields。同 ID 对应不同
root 是 substitution attack。Local ordinal 在同 pool/scope/phase/component/callsite/
receiver/step 内从 0 连续，无 gap/duplicate。

零贡献字段不得写入 occurrence contribution。比如一次 serialization 产生 0 bytes，
该 occurrence 只贡献 operation field；对应 byte slot 仍由“对该 field 有贡献的
occurrences”之 canonical empty set 得到 measured zero。Slot-level occurrence set 是
pool occurrences 按 exact field ordinal 过滤后的集合，不等同于整个 pool occurrence
set；因此 pool 可非空而某个 applicable field 的 slot set 为空。

`PhysicalPoolV2` exact keys：

```text
schema="pheroos-rglf-physical-pool-v2"
physical_pool_identity_root
occurrence_count
occurrence_set_root
ordered_occurrence_roots
cost_cells
cost_observation_set_root
stream_closed=true
physical_pool_root
```

Occurrence set 按 occurrence ID 排序并用 `g3-physical-occurrence-set-v2`；pool root 使用
`g3-physical-pool-v2`。`cost_cells` 是 exact 59-row ordered array，由 occurrence
contributions 独立求和；N-A 显式 `not_applicable`。Empty set 只可产生 applicable fields
的 measured zero；任一 applicable field 若没有 positive contribution，也以 integer 0
初始化，禁止 synthetic zero occurrence。

`AllocationConsumerV2` exact keys：

```text
schema="pheroos-rglf-allocation-consumer-v2"
batch_root
analysis_scope
intent_root
initial_attempt_identity_root
controller_id
budget_layer_id
task_family
agent_count
attack_severity
seed
repeat_id
checkpoint_key_root
assignment_root
consumer_id
```

Consumer ID 使用 `g3-allocation-consumer-v2`，必须从 locked assigned intents 预先生成，
不得由 observed load/success/cache/provider result 生成。

完整 denominator 由 closed `AllocationConsumerMembershipRuleV2` 决定，exact keys：

```text
schema="pheroos-rglf-allocation-consumer-membership-rule-v2"
rule_id
analysis_scope
physical_pool_identity_root
assignment_set_root
execution_binding_set_root
scope_root
consumer_assignment_policy_root
task_family
agent_count
attack_severity_set_root
seed_set_root
repeat_id_set_root
budget_layer_id_set_root
controller_id_set_root
attachment_rule="initial-attempt-only"
membership_rule_root
```

`rule_id` 只能是：

```text
environment_assigned_intents_v2
receiver_step_basis_assigned_intents_v2
budget_entry_assigned_intents_v2
g_primary_checkpoint_consumers_64_v2
batch_flush_assigned_intents_v2
```

每个 rule 的 predicate 固定：

- environment：全部且仅全部 execution binding 的 public episode root 等于 pool
  environment scope root 的 assigned intents；
- receiver-step basis：全部且仅全部 binding 的 basis root 等于 pool scope root 的
  assigned intents；
- budget entry：全部且仅全部 binding 引用该 entry root 的 assigned intents；
- G primary：exact `(task_family,N in {4,16})`、primary smoke axes 和本节定义的 64
  consumers；
- batch flush：全部且仅全部属于 exact batch/analysis scope 的 assigned intents。

不适用的 filter roots 必须 null；适用集合由 immutable assignment/binding roots
重算，不能传入任意子集。只有 `g_primary_checkpoint_consumers_64_v2` 的
`consumer_assignment_policy_root` 非 null，并必须引用对应
`GConsumerAssignmentPolicyV2`；其他 rule 必须 null。`AllocationConsumerSetV2` exact keys 是
`schema,membership_rule_root,expected_consumer_count,
ordered_consumer_roots,consumer_set_root`；ordered consumers 必须与 rule predicate 的
完整结果 exact equality。Generic canonical order 是
`(analysis_scope,task_family,agent_count,attack_severity,seed,repeat_id,
budget_layer_order,intent_root)`：

```text
consumer_set_root =
  digest_json("g3-allocation-consumer-set-v2",
              ordered consumer IDs)
remainder_order_root =
  digest_json("g3-allocation-remainder-order-v2",
              same ordered consumer IDs)
```

Membership rule 的 physical-pool identity 必须等于
`AllocationPlanV2.physical_pool_root` 所引用
`PhysicalPoolV2.physical_pool_identity_root`，且 rule scope root 必须等于该 identity
的 scope root；跨 pool 或跨 scope 复用 consumer set 一律拒绝。

每个 `(physical pool,source field,target field,analysis scope)` 建立一个
`AllocationPlanV2`，exact keys：

```text
schema="pheroos-rglf-allocation-plan-v2"
batch_root
analysis_scope
physical_pool_root
membership_rule_root
expected_consumer_set_root
consumer_set_root
source_field_ordinal
source_field_name
target_field_ordinal
target_field_name
source_cost_cell_root
physical_total
consumer_count
algorithm="quotient-remainder-v1"
remainder_order_root
target_expected_slot_set_root
attachment_rule="initial-attempt-only"
view_selector="allocated"
allocation_plan_root
```

`expected_consumer_set_root == consumer_set_root`，且 consumer count 必须等于
`AllocationConsumerSetV2.expected_consumer_count`。Source cell root 固定为：

```text
source_cost_cell_root =
  digest_json("g3-allocation-source-cost-cell-v2", {
    physical_pool_root,
    source_field_ordinal,
    source_field_name,
    exact_value
  })
```

`exact_value` 必须是 referenced `PhysicalPoolV2.cost_cells[source_field_ordinal]` 的
integer value，并且 `physical_total == exact_value`。N-A、字段名/ordinal mismatch 或
自报 total 均拒绝。

`consumer_count>0`。Shared generator/common eligibility 只允许同名 source→target；
G training 固定
`g_train_operations -> g_amortized_training_operations`；同一 frozen physical
G-training profile 中其他 numeric fields（包括 `g_checkpoint_operations` 与
`g_checkpoint_bytes`）只允许同名 source→target。N-A 不产生 allocation，且
`g_amortized_training_operations` 不得接收第二个 source。

`AllocationRowV2` exact keys：

```text
schema="pheroos-rglf-allocation-row-v2"
allocation_plan_root
consumer_id
consumer_ordinal
target_expected_slot_root
quotient
remainder
allocated_value
allocation_row_root
```

对 `n=consumer_count`：

```text
q=physical_total//n
r=physical_total%n
allocated_value=q+1 iff consumer_ordinal<r else q
```

`AllocationPoolV2` exact keys 是
`schema,allocation_plan_root,row_count,ordered_allocation_row_roots,
allocated_sum,unallocated_remainder,stream_closed,allocation_pool_root`。Roots 分别使用
`g3-allocation-plan-v2|g3-allocation-row-v2|g3-allocation-pool-v2`。必须证明 row count
等于 consumer count、ordinals 是 `0..n-1`、每个 consumer/target slot 恰好一次、
`allocated_sum=physical_total`、`unallocated_remainder=0`。

这里使用 6.1 的 exact `CostApplicabilityProfileV2` 和完整
`CostApplicabilityProfileSetV2`，不得另建 local/default table。Physical G-training 中
`g_train_operations=physical,g_amortized_training_operations=N/A`；allocated G consumer
中相反且 amortized field 是 allocated-share。Controller physical costs 在 allocated
view 是 allocated-copy，不产生第二组 occurrences。Shared/training physical entries 只进
physical aggregate；allocation rows 只进 allocated aggregate。

`CostAggregateV2.view_selector` 是 required closed enum：

```text
physical
allocated
```

`physical` 包含 controller/shared/training physical totals，排除 derived allocations；
`allocated` 包含 controller physical costs 与 per-consumer shared/training allocations，
排除 shared/training physical pool entries。Aggregate 还必须绑定单一
`analysis_scope,slot_membership_program_root`。没有 `both`；physical/allocated slot root
sets 必须互斥，禁止两种 view 相加。

对每个 `(task_family,N)`、`N in {4,16}`，G primary training consumer 精确为：

```text
controller=G
matrix_kind=smoke_attack
split=smoke
attack_severity=0.00,0.25
seed=9000,9001
repeat_id=0,1
all 8 budget_layer_ids
```

即每 checkpoint `2*2*2*8=64` consumers；7 tasks*2 sizes=14 pools、总 896 assignments。
Canonical order 是
`(attack_severity_order,seed,repeat_id,budget_layer_order,intent_root)`。Denominator 在训练前
冻结为 64；失败、timeout、quarantine、fallback、retry 或未成功 load checkpoint 均
不得删除。Allocation 只附着 ordinal-0 attempt；retry 不重复分摊。N>=64
`scale_cost_only` 使用互斥 analysis scope，默认不分摊 primary pool，且禁止与 primary
aggregate 求和。

### 6.4 GTrainingCallsiteVectorV2

`GConsumerAssignmentPolicyV2` 是先于 training plan/pool 的 immutable denominator
policy，exact keys：

```text
schema="pheroos-rglf-g-consumer-assignment-policy-v2"
batch_root
analysis_scope="primary_smoke_attack"
task_family
agent_count
checkpoint_key_root
assignment_set_root
controller_id="G"
matrix_kind="smoke_attack"
split="smoke"
attack_severity_set_root
seed_set_root
repeat_id_set_root
budget_layer_id_set_root
attachment_rule="initial-attempt-only"
expected_consumer_count=64
policy_root
```

Set roots 必须 exact 对应 Section 6.3 的 2 severities、2 seeds、2 repeats、8 layers；
policy root 使用 `g3-g-consumer-assignment-policy-v2`。它不引用 GTrainingPlan、
PhysicalPoolIdentity、occurrence、checkpoint output 或结果。

`GTrainingPlanV2` 是 pre-execution scope identity，exact keys：

```text
schema="pheroos-rglf-g-training-plan-v2"
batch_root
task_family
agent_count
train_dataset_root
dev_dataset_root
source_s_derived_graph_root
checkpoint_key_root
feature_allowlist_root
numeric_contract_root
grid_contract_root
callsite_table_root
consumer_assignment_policy_root
ontology_root
physical_applicability_profile_root
training_plan_root
```

Root 排除自身并使用 `g3-g-training-plan-v2`。它不含 weights、winner、occurrences、
cost pool、checkpoint payload 或 final receipt，因此可作为
`checkpoint_training_pool` scope root 而不形成循环。构造顺序固定为
`GConsumerAssignmentPolicy -> GTrainingPlan -> PhysicalPoolIdentity ->
AllocationConsumerMembershipRule`；最后一项同时引用 policy 和 pool identity，前两项
绝不反向引用它。

每个 `(task_family,N)` training pool 先绑定：

```text
R = exact train row count from train_dataset_root
D = exact dev row count from dev_dataset_root
F = 10 ordered features
A = 3 learning rates * 3 L2 values = 9 trajectories
E = 50 epochs
K = 2 snapshot epochs (25,50)
C = A * K * 3 native-k values = 54 dev candidates
```

Disjoint callsite/multiplicity vector：

| ordinal | callsite | exact occurrences |
| ---: | --- | ---: |
| 1 | `train_feature_extract` | `R` |
| 2 | `train_feature_value_emit` | `R*F` |
| 3 | `train_sidecar_label_read` | `R` |
| 4 | `train_example_visit` | `A*E*R` |
| 5 | `train_feature_multiply_accumulate` | `2*A*E*R*F` |
| 6 | `train_sigmoid_evaluate` | `A*E*R` |
| 7 | `train_weight_update` | `A*E*F` |
| 8 | `dev_feature_extract` | `D` |
| 9 | `dev_feature_value_emit` | `D*F` |
| 10 | `dev_sidecar_label_read` | `D` |
| 11 | `dev_grid_example_visit` | `C*D` |
| 12 | `dev_feature_multiply_accumulate` | `C*D*F` |
| 13 | `dev_sigmoid_evaluate` | `C*D` |
| 14 | `dev_metric_label_read` | `C*D` |
| 15 | `dev_candidate_finalize` | `C` |
| 16 | `dev_winner_key_evaluate` | `C` |
| 17 | `train_checkpoint_snapshot` | `A*K` |
| 18 | `final_checkpoint_serialize` | `1` |
| 19 | `final_checkpoint_hash` | `1` |

Callsites 1–16 每 occurrence 对 `g_train_operations` 贡献 1，因此 verifier 从 corpus
独立重算：

```text
g_train_operations =
  9912*R + 714*D + 4608
```

Callsites 17–19 对 `g_checkpoint_operations` 各贡献 1，即 20 operations。每个 trajectory
snapshot 与 final checkpoint 都必须形成 exact canonical bytes；其 byte counts 进入
`g_checkpoint_bytes`。Final hash 另贡献一个 state-hash operation 及其 exact hashed
bytes。一个 physical action 只产生一个 occurrence，但其 contribution array 可同时写
checkpoint operation/bytes 与 state-hash fields。

这是一组冻结的 semantic-operation callsites，不是 CPU instruction count。Unknown
callsite、multiplicity 不等式、R/D 与 dataset root 不符、把 dev 54-grid 漏出 cost、
把 snapshot 同时计入 train 与 checkpoint，或用 aggregate descriptor 再加一次均拒绝。
`g_amortized_training_operations` 只由 locked physical pool 分摊产生。

每个 task/size pool 绑定 corpus、checkpoint、callsite vector、physical vector 和 64 个
primary consumers。假想 `1/10/100/1000 lifetime` 只能作为 planning sensitivity，不能
冒充 primary allocation。

### 6.5 CostObservationV2

Observation requiredness 在执行前由 `CostObservationProfileV2` 冻结。Exact keys：

```text
schema="pheroos-rglf-cost-observation-profile-v2"
component_plan_entry_root
component_kind
component_id
component_version
phase_id
subject_identity_kind
profile_derivation_program_root
observation_rows
profile_root
```

Subject kind 是 `attempt|physical_pool`。`observation_rows` 恰好五行，按下表 field 顺序，
每行 exact keys 是
`ordinal,observation_field,requirement_mode,api_id,unit,boundary_id,
optional_missing_reason_universe`。Mode 只能是
`required|optional|not_applicable`；required 的 optional-missing universe 必须空，
optional 只能列
`unsupported_platform|permission_denied|measurement_failed`，N-A 的
API/unit/boundary 和 missing universe 必须 null/empty。Profile root 使用
`g3-cost-observation-profile-v2`。

`CostObservationProfileSetV2` exact keys 是
`schema,component_plan_root,expected_profile_key_count,
ordered_expected_profile_keys_root,profile_count,ordered_profile_roots,
missing_count,extra_count,duplicate_count,profile_set_root`。Expected keys 是
component plan 中每个 entry 与其 `observation_subject_kinds` 的 exact cross
product；排序、coverage 和 defect=0 规则与 applicability set 相同。Set root 使用
`g3-cost-observation-profile-set-v2`。Expected-slot program 和每个 observation batch
都必须绑定这个 pre-execution set root；independent verifier 必须执行 referenced
derivation program 重建五行并要求 exact equality，runtime 不能把 required 改成
optional。

`CostObservationV2` 只绑定 pre-execution identity，不引用 final attempt/pool receipt：

```text
schema="pheroos-rglf-cost-observation-v2"
subject_identity_kind
subject_identity_root
activation_decision_root
component_kind
component_id
component_version
phase_id
observation_profile_set_root
observation_profile_root
observation_field_ordinal
observation_field
requirement_mode
observed_state
value
api_id
unit
boundary_id
start_provenance_root
end_provenance_root
platform_runtime_root
missing_reason
measurement_failure_provenance_root
excluded_from_replay_root=true
observation_root
```

Subject 是 `attempt|physical_pool`，分别引用 `AttemptIdentityV2` 或
`PhysicalPoolIdentityV2`。五个 ordered fields 与 API/boundary：

| field | API | boundary ID | exact boundary |
| --- | --- | --- | --- |
| `wall_ns` | `time.perf_counter_ns()` | `controller_outer_v2` | outer phase start through immutable deterministic cost-entry finalize |
| `cpu_ns` | `time.thread_time_ns()` | `controller_outer_thread_cpu_v2` | same work interval as outer phase, measured on one thread |
| `latency_ns` | `time.perf_counter_ns()` | `controller_rank_to_precap_close_v2` | immediately before controller ranking invocation through immutable controller result and PreCapFinal close |
| `peak_allocation_bytes` | `tracemalloc.get_traced_memory()[1]` | `isolated_phase_peak_v2` | isolated phase tracer after start/reset through pre-stop peak read |
| `peak_rss_bytes` | `resource.getrusage(RUSAGE_SELF).ru_maxrss` | `process_hwm_phase_end_v2` | process high-water sample at phase end |

Controller outer phase 在 complete immutable context、basis、budget entry、
controller-input-state 和 native-policy roots 就绪后立即开始，且必须早于 controller
ranking/PreCap construction。它依次包住 ranking、PreCap final close、common reducer、
bundle serialization/hash 与 immutable deterministic cost-entry finalize。Inner
latency 在 controller ranking invocation 前开始，在 immutable controller result 与
PreCapFinal close 后结束；因此 inner 完全包含于 outer，reducer/bundle finalize 只在
outer 内。Generator、basis/schedule、sealed evaluator 和 NDJSON flush 使用 disjoint
phases。
CPU start/end 必须在同一 thread，被测 work 不得委托给未计量 worker thread。
Tracemalloc 每 attempt/process 隔离，phase 串行执行
`start -> reset_peak -> work -> read -> stop`；禁止 concurrent/global tracer reuse。RSS 在
Linux 以 KiB*1024，Darwin 以 bytes 规范化并绑定 OS；它是 process high-water，不是
phase delta，只能在同 scope 取 max，永不相加。
Controller observation 必须满足 `latency_ns <= wall_ns`。

Observed state 是 `materialized|not_invoked|not_applicable|missing`。Missing reason
closed enum：

```text
attempt_not_activated
phase_not_activated
not_applicable_by_profile
unsupported_platform
permission_denied
measurement_failed
```

逐状态约束：

- `materialized`：profile required/optional，value 是 non-negative integer，
  API/unit/boundary 与 profile exact equality，start/end/platform roots 非 null，
  missing/failure roots 为 null；
- `not_invoked`：profile required/optional，value/provenance/failure roots 为 null，
  reason 是 `attempt_not_activated|phase_not_activated` 并引用 predicate-false activation；
- `not_applicable`：profile N-A，value/API/unit/boundary/provenance/failure roots 为
  null，reason 固定 `not_applicable_by_profile`；
- `missing`：只允许 profile optional，value 和 start/end roots 为 null，
  API/unit/boundary 仍与 profile exact equality，platform root 与
  `measurement_failure_provenance_root` 非 null，reason 只能是 profile 已列的三个
  optional failure code。

Primary required field 的 missing 阻断；missing 不能填零，也不能伪装为 not-invoked。
Observation root 排除自身并使用
`g3-cost-observation-v2`；ordered set root 使用
`g3-cost-observation-set-v2`。五项 observation 全部排除 deterministic replay root。

### 6.6 AttemptReceiptV2 and primary ITT

只有 activated attempt 产生 final `AttemptReceiptV2`，exact keys：

```text
schema="pheroos-rglf-attempt-receipt-v2"
attempt_identity_root
activation_decision_root
terminal_status
terminal_code
partial_work_root
physical_pool_roots
observed_physical_slot_set_root
observed_allocated_slot_set_root
cost_observation_set_root
trace_root
authority_scope="none"
commit_authority=false
output_authority=false
publication_authority=false
outcome_authorized=false
attempt_receipt_root
```

Root 排除自身并使用 `g3-attempt-receipt-v2`，必须在所有 applicable slots、
partial-work 和 observations 关闭后生成。任何 child retry decision 可引用它；本
attempt 的 slot/observation/occurrence/pool/allocation 不得反向引用它。Initial、retry、
timeout、crash、invalid、quarantine 与 partial completion 全部 append-only 保留，status
与 terminal code 必须匹配 6.2 closed map。

`observed_allocated_slot_set_root` 只包含 receipt 前已关闭的 controller allocated-copy
与 pre-attempt shared/basis/schedule/G-training pools。`batch_once` post-attempt flush
allocation 只在 `CostAggregateV2` 的 batch-close membership 中出现；它不允许回填或
改变既有 AttemptReceipt。Independent verifier 必须据 scope/phase 拒绝任何时间倒置。

Primary ITT 以 locked assigned intents 为 denominator：

- 保留失败、timeout、crash 和 fallback；
- 同一 intent 的全部 activated attempts 成本进入 primary cost；
- retry success 不覆盖 prior failure；
- completed-only/warm-cache 只能是 secondary sensitivity；
- 本 G3 qualification 不计算 task outcome。

### 6.7 Independent verifier

Verifier 不得 import builder、slot/attempt constructor、allocation helper、callsite
accumulator 或 controller reducer。它独立重算 ontology order/applicability、slot program、
attempt activation、occurrence IDs、owner uniqueness、consumer roots/order、
physical/allocated view closure、shared/G conservation、ITT denominator、ledger roots 和
observation boundary/exclusion。只做同函数 fresh call 不算 independent。

至少拒绝：

- 任意 self-root/root cycle，或 child record 对 final AttemptReceipt 的反向引用；
- ordinal/parent/kind/activation chain 不一致，terminal universe 不 closed，retry sets
  overlap/incomplete，或 success/invalid/quarantine 被 retry；
- conditional slot 缺 activation plan/decision，inactive 被 materialized，或 activated
  applicable 写 not-invoked；
- measured zero 写 missing/not-invoked、zero contribution occurrence、required
  observation missing、optional missing 无 profile/failure proof，或 missing 填零；
- scope nullability 错误，shared/common/G pool 绑定任意 consumer intent；
- unknown callsite、multiplicity 错误、local ordinal gap/duplicate、同 occurrence ID
  对应不同 root、或 pool 59 rows 与 contribution sum 不闭合；
- `consumer_count=0`、membership rule 与 complete assigned-intent set 不相等、
  consumer post-selection、失败者删除、source cost cell/physical total 不相等、
  q/r/order/field mapping/row coverage/conservation 失败；
- physical 中出现 amortized value、allocated G consumer 出现 physical
  `g_train_operations`、copy/share 无唯一 source、使用 `both` 或混合 primary/OOD；
- 任一 `(task,N in {4,16})` G consumer set 不等于 64 或总 assignment 不等于 896；
- Observation API/boundary/unit 随意变化、RSS 求和、tracemalloc 并发、或 observation
  进入 replay root；
- 任一 record 携带 Commit/output/publication/outcome/hypothesis authority。

## 7. Minimal T1/F vertical slice

Exact cell：

```text
matrix_kind=smoke_attack
task_id=T1
split=smoke
seed=9000
repeat_id=0
agent_count=4
event_count=100
steps=20
logical_step=0..19
attack_severity=0.00
facts=20
controller_id=F
budget_layer_ids=
  natural,iso,
  sweep:0.10,sweep:0.20,sweep:0.35,
  sweep:0.50,sweep:0.75,sweep:1.00
sealed_evaluator_enabled=false
provider_adapter_enabled=false
```

Expected geometry：

```text
1 active planning_cell_root
1 PublicEpisodeCommitmentV2 root
8 active lazy-manifest roots
8 materialized EpisodeManifestV1 roots
8 active F ArmBudgetIntentV05 roots
8 execution binding roots
4 receivers * 20 steps = 80 arm-independent bases
80 bases * 8 layers = 640 budget schedule cells
4 budget-blind F controller-initial-state roots
80 budget-blind controller-input-state roots
80 budget-blind controller-state-transition roots
80 budget-blind PreCapFinal roots
8 execution bindings * 80 receiver-steps = 640 PreCap execution receipts
8 execution bindings * 80 receiver-steps = 640 reducer roots
8 execution envelopes * 80 receiver-steps = 640 F bundles
8 F arm-budget intents
```

Public episode generation 只执行一次并由 `shared_generator` 拥有；同一个 budget-free
`PublicEpisodeCommitmentV2` 被八个 budget envelopes 引用，不得按 layer 重新生成。八个
budget-bound EpisodeManifest roots 仍分别保留，不能冒充同一 root。Common eligibility 的 80
prefixes 只计算一次；640 schedule cells 是对这些 bases 应用八个 layer 公式，不是 640
次 public generation。每个 envelope 各自产生 80 F bundles。

计费边界：

- 一次 task/event/receiver construction 归 `shared_generator`；
- 80 次 eligibility basis 与 640 个 schedule-cell constructions 归
  `common_eligibility`；
- 每个 envelope 内 fresh F ranking execution、CommonBudgetReducerV2、bundle
  serialization/hash 归 F；八个 layers 的 semantic PreCap root 必须相同，但 640 次
  physical executions/receipts 仍分别计费，不得用一次 cached execution 冒充八次；
- trace append 与 NDJSON flush 按各自 ontology owner；
- sealed evaluator 与 provider adapter 都是 disabled/not invoked，其 API、credential
  environment 和 outcome surface 对 attempt 不可见。

Deterministic attempt policy 是每个 F intent 一个 ordinal-0
`AttemptIdentityV2`、一个 activated initial decision、`max_attempts=1`、无 retry。

任一 timeout、crash、missing bundle、slot mismatch 或 verifier mismatch 都使 slice
blocked，不得拼接重跑结果。全部通过后唯一允许的声明是：

```text
T1-F-cost-mechanics-qualified
```

它不表示 aggregate G3、F outcome、cost frontier 或任何 hypothesis conclusion，也不把
640 bundles 当作独立实验样本。

## 8. Required contracts and receipts

下列 artifact 当前全部是 `unmaterialized`，本 draft 不指定 hash：

```text
ContractDescriptorV1
ContractDescriptorSetV1
ContractDescriptorMetaSchemaV1
ContractDescriptorSetQualificationReceiptV1
MethodologyProfileReviewReceiptV1
MethodologyActivationAllowedChangedPathsV1
ActivatedMethodologyProfileV1
MethodologyActivationChangedPathBindingV1
MethodologyActivationCandidateBindingV1
MethodologyActivationV1
TaskSizeProfileV2
PublicEpisodeCommitmentV2
EpisodeMaterializationBindingV2
ArmBudgetExecutionBindingV2
CommonEligibilityChunkV2
CommonEligibilityStreamV2
CommonEligibilityBasisV2
CommonEligibilityBasisSetChunkV2
CommonEligibilityBasisSetV2
BudgetScheduleEntryV2
BudgetScheduleV2
BudgetScheduleSetV2
BudgetScheduleQualificationReceiptV2
ControllerInitialStateV2
ControllerInputStateV2
ControllerStateTransitionV2
NativeSelectionPolicyV2
PreCapCandidateV2
PreCapCandidateStreamV2
PreCapChunkV2
PreCapFinalReceiptV2
ProcessLaunchReceiptV2
PreCapExecutionReceiptV2
PreCapRankingReceiptV2
DemandVectorV2
RankContractV2
BudgetSelectedRowV2
BudgetDropRowV2
CommonBudgetReducerV2
CommonBudgetReducerReceiptV2
SGraphConstructorV2
SSizeQualificationArtifactV2
SArtifactMigrationReceiptV1ToV2
SScaleOODExtrapolationReceiptV2
GSizeCheckpointArtifactV2
GCheckpointMigrationReceiptV1ToV2
GScaleControllerInputBindingV2
ScaleOODTransferReceiptV2
CostOntologyV2
CostProfileDerivationProgramV2
CostProfileDerivationExpectedProgramInventoryV2
CostProfileDerivationProgramSetV2
CostComponentPlanEntryV2
CostComponentPlanV2
CostApplicabilityProfileV2
CostApplicabilityProfileSetV2
ExpectedCostSlotProgramV2
ExpectedCostSlotV2
AttemptPolicyV2
AttemptIdentityV2
AttemptActivationDecisionV2
RetryAuthorizationV2
PhaseActivationDecisionV2
ObservedCostSlotV2
PhysicalPoolIdentityV2
PhysicalOccurrenceV2
PhysicalOccurrenceLedgerV2
PhysicalPoolV2
AllocationConsumerV2
AllocationConsumerMembershipRuleV2
AllocationConsumerSetV2
AllocationPlanV2
AllocationRowV2
AllocationPoolV2
SharedAllocationViewV2
GTrainingPlanV2
GConsumerAssignmentPolicyV2
GTrainingCallsiteVectorV2
GTrainingPoolAllocationV2
CostObservationProfileV2
CostObservationProfileSetV2
CostObservationV2
AttemptReceiptV2
CostAggregateV2
CostLedgerQualificationReceiptV2
T1FCostMechanicsReceiptV1
G3MethodologicalQualificationReceiptV1
NegativeMutationReceiptV2
```

上表是 planning inventory，不等于可执行 schema。任何未在正文完全闭合的 contract，
以及所有 final qualification receipts，在 activation 前必须进入一个 independently
reviewed machine-readable descriptor set。

`ContractDescriptorV1` exact keys：

```text
schema="pheroos-rglf-contract-descriptor-v1"
contract_name
dependency_stage_ordinal
schema_literal
ordered_fields
closed_schema=true
root_label
root_method="digest_json-v1"
root_field_name
root_excludes_self=true
ordered_invariants
dependency_contract_names
ordered_reference_guards
descriptor_meta_schema_root
producer_role
independent_verifier_role
descriptor_root
```

`ordered_fields` 每行 exact keys 为
`ordinal,field_name,type,nullable,constraint_ast,enum_values,reference_contract,
cardinality`；不适用项显式 `null`。`ordered_invariants` 每行 exact keys 是
`ordinal,invariant_id,predicate_ast,error_code,referenced_contract_names`，不能放自由
文本。`ordered_reference_guards` 每行 exact keys 是
`reference_field_name,dependency_contract_name,dependency_mode,
dependent_rank_tuple_paths,referenced_rank_tuple_paths,required_relation`；
mode 只能是 `strict_predecessor|well_founded_back_reference`，back reference 的
relation 必须是 typed lexicographic `<`。Descriptor root 排除自身并使用
`g3-contract-descriptor-v1`。`dependency_stage_ordinal` 是 non-negative integer；
同一 SCC 内唯一，用于识别必须携带 well-founded guard 的 backward edge。

`ContractDescriptorMetaSchemaV1` exact keys：

```text
schema="pheroos-rglf-contract-descriptor-meta-schema-v1"
descriptor_schema_literal
field_type_universe
constraint_ast_operator_universe
predicate_ast_operator_universe
root_method_universe=("digest_json-v1",)
error_code_grammar
dependency_edge_schema_literal
meta_schema_root
```

AST operator exact closed universe 为
`literal,path_get,project,all,any,not,eq,ne,lt,le,gt,ge,in,set_eq,disjoint,
implies,is_null,non_null,type_is,regex_fullmatch,count_eq,unique_by,sorted_by,
for_all,exists,if_then_else,add,sub,mul,floor_div,mod,sum,min,max,len,
decimal_parse_q9,decimal_compare,reference_eq,digest_eq`；
每个 operator 的 arity/operand types 在 schema literal 中机器定义。Meta root 排除自身
并使用 `g3-contract-descriptor-meta-schema-v1`。Descriptor、set 与 verifier 必须
引用 exact meta root；unknown operator、opaque text constraint 或 untyped operand
均拒绝。Arithmetic 只接受 exact integers；无 generic `/` 或 float。六档 cap 必须用
`mul+floor_div`，demand/occurrence totals 用 `sum`，allocation 用
`floor_div+mod`，ordinal predecessor 用 `sub`，q9 只用专用 parse/compare。

`ContractDescriptorSetV1` exact keys：

```text
schema="pheroos-rglf-contract-descriptor-set-v1"
methodology_input_root
specification_commit
producer_source_root
descriptor_meta_schema_root
cost_profile_derivation_expected_program_inventory_root
cost_profile_derivation_program_set_root
activation_allowed_changed_paths_root
required_contract_names
descriptor_count
ordered_descriptor_roots
dependency_edge_count
ordered_dependency_edges_root
dependency_scc_count
ordered_dependency_scc_roots
unguarded_dependency_cycle_count
all_required_present
descriptor_set_root
```

Required names 必须与上表 exact set 相等，按 UTF-8 contract name 排序且一项一个
descriptor；set root 排除自身并使用 `g3-contract-descriptor-set-v1`。
`cost_profile_derivation_expected_program_inventory_root` 必须引用从 methodology body
literal 14-row table 独立重建的 exact inventory；`cost_profile_derivation_program_set_root`
必须引用 candidate 中已 materialize 的
exact reviewed set，且其 ontology/program contract descriptors 都是 required set
members；descriptor verifier 必须重算 program set、四个 defect counts 和全部
program roots，且 Set 的 expected-inventory root 必须与前一字段 exact equality，不能
接受 late-bound registry 或自报 expected universe。
`activation_allowed_changed_paths_root` 必须引用 candidate 中已 materialize 的 exact
one-path allowlist；verifier 从其 closed descriptor 和 literal path 重算，不接受 binding
producer 提供的替代 path set。
Dependency edge exact keys 为
`dependency_contract_name,dependent_contract_name,reference_field_names,
dependency_mode,reference_guard_root`，按两个 contract name/mode 排序；必须由
descriptors 的 reference fields/invariants 独立导出。Raw type graph 允许因
`PreCapChunk.previous`、Attempt parent/retry/receipt 或 prior-step state 形成 SCC，不能
伪称 type DAG。

Verifier 先求 exact SCC，再在每个 SCC 内按 descriptor-declared stage order移除
`well_founded_back_reference` edges；剩余 edges 必须 acyclic。每条移除 edge 必须在
instance 上证明 referenced rank tuple 严格小于 dependent tuple，例如
`chunk_index`、`attempt_ordinal` 或 `logical_step`。SCC condensation graph 的 canonical
topological order使用最小 UTF-8 contract name tie-break，并写入
`ordered_dependency_scc_roots`；`unguarded_dependency_cycle_count=0`。
`all_required_present` 是 verifier 重算结果的 redundant assertion，不是授权位。
`methodology_input_root` 与 `specification_commit` 只能引用已存在、且不包含该
descriptor-set artifact 的 immutable methodology input；candidate commit/tree identity
由外部 manifest 在 commit
形成后单向绑定，禁止把 future commit hash 写入自身文件形成循环。
`producer_source_root` 必须是生成 candidate 以前已存在的 immutable producer-tool
source commit/tree root，并明确排除所有 generated methodology candidate artifacts；
它不得等于、包含或反向引用 candidate source-tree root、descriptor set、qualification
receipt 或 review records。只有未来 atomic
candidate 实际 materialize 该 set并通过下述 independent receipt 后，才可进入 activation
审议；本 draft 当前仍 false，不能据 planning prose 自行实现缺失 schema。

Candidate tree 必须先 immutable commit，且只包含 reviewed methodology/meta schema、
expected-program inventory、derivation programs/program set、activation allowlist 和
contract descriptors 等 non-executable candidate artifacts。下面的 descriptor-set
qualification receipt、reviewed inactive profile record 和 profile review receipt 必须
在该 commit/tree 形成后由外部 registry/evidence store 单向生成；三者都不得进入其
`candidate_source_tree_root` 所指 tree。否则因为 record 内含 candidate tree root，会
形成 self-root，必须拒绝。

`ContractDescriptorSetQualificationReceiptV1` exact keys：

```text
schema="pheroos-rglf-contract-descriptor-set-qualification-receipt-v1"
candidate_descriptor_set_root
descriptor_meta_schema_root
candidate_source_tree_root
independent_verifier_source_root
recomputed_required_contract_names_root
recomputed_descriptor_roots_root
recomputed_dependency_edges_root
recomputed_dependency_scc_roots
recomputed_cost_profile_derivation_expected_program_inventory_root
recomputed_cost_profile_derivation_program_set_root
recomputed_activation_allowed_changed_paths_root
closed_schema_check_count
invariant_ast_check_count
reference_guard_check_count
instance_graph_check_count
expected_program_inventory_check_count=1
program_registration_check_count=14
activation_allowlist_check_count=1
missing_count
extra_count
duplicate_count
unguarded_dependency_cycle_count
observed_instance_cycle_count
unknown_ast_operator_count
qualification_passed
authority_scope="none"
commit_authority=false
output_authority=false
receipt_root
```

Qualification pass 必须由所有 recomputed roots（包括 literal-derived expected
program inventory、reviewed program set 与 exact changed-path allowlist）exact
equality、所有 defect counts 为 0、三个新增 check counts
覆盖全部相应 instance，和独立 verifier source 与 producer source 不同共同导出；
recursive instance fixtures
还必须证明 valid predecessor chain 接受、same/future ordinal 与真实 root cycle 拒绝。
布尔自报无效。Root 使用
`g3-contract-descriptor-set-qualification-receipt-v1`。

Methodology content 与 activation registry 分离，避免 profile self-root。Body root 固定为：

```text
methodology_body_root =
  digest_json("g3-methodology-body-v1",
              canonical methodology content excluding the displayed
              inactive control block and all activation/registry records)
```

Inactive control block exact 为本文件顶部 false/null 值，其 root 使用
`g3-methodology-inactive-control-block-v1`。`reviewed_inactive_profile_root` 使用
`g3-reviewed-inactive-methodology-profile-v1` 绑定 body root、inactive-control root、
candidate source-tree root、descriptor set/qualification receipt roots、
cost-profile derivation expected-inventory/program-set roots 和下面的 activation
changed-path allowlist root；它是 candidate tree 外的 immutable review record，不在
activation 后重写，也不得写回其 referenced candidate tree。

`MethodologyActivationAllowedChangedPathsV1` 是 reviewed input，不由 activation
candidate 自报。Exact keys：

```text
schema="pheroos-rglf-methodology-activation-allowed-changed-paths-v1"
repository_scope="external-lab-source-tree"
path_syntax="repo-relative-posix-no-dot-segments-v1"
path_count=1
ordered_changed_paths=[
  "config/g3/activated-methodology-profile.v1.json"
]
ordered_changed_paths_root
allowlist_root
```

Path 必须是 UTF-8 bytewise ascending、unique、repo-relative regular-file path；禁止
absolute path、`.`/`..`、symlink target、directory、glob 或 case-fold alias。
`ordered_changed_paths_root` 使用
`g3-methodology-activation-allowed-changed-paths-list-v1` 对 exact one-path list 计算；
allowlist root 排除自身并使用
`g3-methodology-activation-allowed-changed-paths-v1`。该 artifact 必须在 inactive
review candidate 中 materialize，由 descriptor set、profile review receipt 和
reviewed profile root 共同绑定；其自身不引用 candidate/result tree root，避免
source-tree self-cycle。

`MethodologyProfileReviewReceiptV1` exact keys：

```text
schema="pheroos-rglf-methodology-profile-review-receipt-v1"
methodology_body_root
reviewed_inactive_profile_root
descriptor_set_root
descriptor_set_qualification_receipt_root
cost_profile_derivation_expected_program_inventory_root
cost_profile_derivation_program_set_root
activation_allowed_changed_paths_root
candidate_source_tree_root
independent_reviewer_source_root
reviewed_control_block_root
boundary_check_passed
profile_descriptor_consistency_passed
implementation_authority_absent_during_review=true
review_passed
authority_scope="none"
commit_authority=false
output_authority=false
receipt_root
```

Reviewer source 必须不同于 methodology/descriptor producer source；`review_passed` 必须
由 reviewed profile/descriptor/expected-inventory/program-set/allowlist exact root
equality 与三个 machine checks 导出。Root 使用
`g3-methodology-profile-review-receipt-v1`。

Canonical allowed delta exact object 只允许：

```text
contract_descriptor_set_materialized: false -> true
implementation_allowed: false -> true
lock_migration_allowed: false -> true
contract_descriptor_meta_schema_root: null -> reviewed exact root
contract_descriptor_set_root: null -> reviewed exact root
contract_descriptor_set_qualification_receipt_root: null -> reviewed exact root
gate_changes: {} -> {}
```

Delta root 使用 `g3-methodology-allowed-control-delta-v1`；不能增加其他 path。
`ActivatedMethodologyProfileV1` exact keys 是
`schema="pheroos-rglf-activated-methodology-profile-v1",
methodology_body_root,reviewed_inactive_profile_root,
descriptor_set_root,descriptor_set_qualification_receipt_root,
cost_profile_derivation_expected_program_inventory_root,
cost_profile_derivation_program_set_root,activation_allowed_changed_paths_root,
independent_profile_review_receipt_root,allowed_control_delta_root,
activated_control_block,reviewed_candidate_source_tree_root,activated_profile_root`。
Activated control block 必须是上面 delta 的 exact result，但不含 activation root；
profile root 使用 `g3-activated-methodology-profile-v1`。Expected-inventory、
program-set 与 changed-path allowlist roots 必须 exact 等于 reviewed profile receipt
中的 roots，不能在 activation 时替换。

Activated profile artifact 提交后，由 source tree 外部生成
`MethodologyActivationChangedPathBindingV1`。Exact keys：

```text
schema="pheroos-rglf-methodology-activation-changed-path-binding-v1"
reviewed_candidate_commit
reviewed_git_tree_oid
reviewed_candidate_source_tree_root
result_candidate_commit
result_git_tree_oid
result_source_tree_root
path="config/g3/activated-methodology-profile.v1.json"
change_kind="add"
reviewed_path_present=false
reviewed_git_blob_oid=null
file_mode="100644"
git_blob_oid
raw_byte_count
raw_sha256
artifact_contract_name="ActivatedMethodologyProfileV1"
artifact_schema="pheroos-rglf-activated-methodology-profile-v1"
artifact_root_field_name="activated_profile_root"
expected_artifact_root
recomputed_artifact_root
path_binding_root
```

Binder 必须从 local immutable Git object database 先解析 reviewed
commit/tree/source-tree root 并证明 exact path absent，再解析
`result_candidate_commit -> result_git_tree_oid -> exact path/mode/blob`；commit 不存在、
tree 不等、reviewed path 已存在、change kind 不是 add、submodule/symlink/executable
mode 或 missing/duplicate/case-alias path 均拒绝。
Reviewed/result `source_tree_root` 都必须从各自 Git tree 的 canonical
`(path,file_mode,git_blob_oid,raw_sha256)` rows（path UTF-8 ascending）用
`digest_json("g3-methodology-source-tree-v1", rows)` 独立重算。Binder 读取 target blob
的 exact
bytes，验证 `raw_byte_count/raw_sha256`，要求 canonical closed JSON，按
`ActivatedMethodologyProfileV1` descriptor 重算 root，并强制
`recomputed_artifact_root == expected_artifact_root == activated_profile_root`。
Path-binding root 排除自身并使用
`g3-methodology-activation-changed-path-binding-v1`。该 record 与下面的 candidate
binding 都只存在于外部 registry/evidence store，不进入 result tree。

然后生成
`MethodologyActivationCandidateBindingV1`，exact keys：

```text
schema="pheroos-rglf-methodology-activation-candidate-binding-v1"
reviewed_candidate_source_tree_root
reviewed_candidate_commit
reviewed_git_tree_oid
activated_profile_root
allowed_control_delta_root
activation_allowed_changed_paths_root
result_candidate_commit
result_git_tree_oid
result_source_tree_root
ordered_changed_paths_root
changed_path_binding_count=1
ordered_changed_path_binding_roots_root
missing_allowed_changed_path_count
unexpected_changed_path_count
executable_source_change_count
binding_root
```

Independent binder 必须从 local immutable Git object database 解析
`reviewed_candidate_commit -> reviewed_git_tree_oid`，从该 tree 重算
`reviewed_candidate_source_tree_root` 并要求 exact 等于 reviewed profile/receipt 中的
root；再从已验证的 reviewed/result Git trees 重算 canonical changed-path list。
Missing/unresolvable reviewed commit、tree OID 不等或 source-tree-root 不等均拒绝。
`activation_allowed_changed_paths_root` 必须 exact 等于 review receipt 与 activated
profile 引用的 allowlist，`ordered_changed_paths_root` 必须 exact 等于该 allowlist 的
`ordered_changed_paths_root`。Changed paths 因而必须 exact 只包含上面的 activated
methodology profile artifact，missing/unexpected/executable 三个 defect counts 都为
0；`ordered_changed_path_binding_roots_root` 使用
`g3-methodology-activation-changed-path-bindings-v1` 对上面 exact one binding root
计算，且其 reviewed/result commit/tree/source-tree/profile roots 必须与 parent exact
equality。
`result_candidate_commit` 必须真实解析为 `result_git_tree_oid`，后者必须是用于
reviewed/result diff 与 source-tree-root 重算的同一 result tree；reviewed commit/tree
同样必须是用于 diff 的同一 reviewed tree。Binding producer 无权扩大
allowlist、替换 blob 或把合法 profile root与任意 tree拼接。Binding 存在
registry/evidence store，不在
`result_source_tree_root` 内，故 commit/tree 不自指。Root 使用
`g3-methodology-activation-candidate-binding-v1`。

未来 `MethodologyActivationV1` exact keys 是
`schema,reviewed_inactive_profile_root,activated_profile_root,
allowed_control_delta_root,activation_allowed_changed_paths_root,
cost_profile_derivation_expected_program_inventory_root,
cost_profile_derivation_program_set_root,descriptor_set_root,
descriptor_set_qualification_receipt_root,independent_profile_review_receipt_root,
activation_candidate_binding_root,activation_registry_version,authority_scope,
commit_authority,activation_root`。
全部 input/result/review roots 必须 exact 验证，authority 固定 `none|false`；Activation
root 使用 `g3-methodology-activation-v1`。Active methodology lock/registry 必须原子绑定
`(activated_profile_root,activation_candidate_binding_root,activation_root)`；第二项也
必须 exact 等于 activation record 内的 candidate-binding root。Activated profile 不反向
包含 binding/activation root，因此无 cycle。禁止原地改写 reviewed bytes、把 activation
root 写回 body，或只翻 boolean。本 draft 的四个 displayed roots 仍为 null。

Activation lineage 的真实方向固定为：

```text
pre-existing methodology body + producer-tool source
  -> meta/inventory/program-set/allowlist/descriptors
       -> immutable reviewed candidate tree
            -> out-of-tree descriptor qualification receipt
                 -> out-of-tree reviewed inactive profile/review receipt
                      -> ActivatedMethodologyProfileV1 blob
                           -> immutable result commit/tree
                                -> out-of-tree changed-path binding
                                     -> out-of-tree candidate binding
                                          -> MethodologyActivationV1 registry
```

任一 receipt/record 不得成为它已经引用的 candidate/result tree 的 ancestor；上图不允许
反向边。

未来 receipt 必须绑定真实 source/profile/lock/input/output identities、expected/observed
counts、producer/verifier identity，并固定：

```text
authority_scope=none
commit_authority=false
output/publication_authority=false
outcome_authorized=false
sealed_outcome_reads=0
sealed_evaluator_enabled=false
provider_adapter_enabled=false
network_used=false
provider_credentials_used=false
hypothesis_conclusions={}
```

未 materialize 字段保持 absent/pending，不写看似真实的 `sha256:` value。

## 9. Required negative fixtures

每个 negative fixture 从一个 immutable positive base 单独派生。`NegativeMutationReceiptV2`
exact keys 固定：

```text
schema="pheroos-rglf-negative-mutation-receipt-v2"
base_artifact_root
mutation_id
target_json_pointer
before_value_root
after_value_root
mutated_artifact_root
expected_error_code
observed_error_code
unchanged_field_set_root
first_stale_descendant_root
mutation_receipt_root
```

Mutation 必须只改变声明的 target；`mutated_artifact_root` 必须由 mutated bytes 重算且与
base root 不同。Expected error 不进入 mutated artifact，不能通过改 expected root 让
错误样本通过。Verifier 独立重算 before/after/unchanged roots；一个 fixture 同时改两个
语义字段、复用 base root 或没有 observed rejection receipt 均无效。
`first_stale_descendant_root` 只对 `G3-LINEAGE-STALE-DESCENDANT` 非 null，其他 mutation
必须 null。Receipt root 排除自身并使用 `g3-negative-mutation-receipt-v2`。

Positive lineage 是下面的 root DAG，不是线性链；箭头只表示真实 preimage dependency：

```text
active planning_cell_root
  -> PublicEpisodeCommitmentV2
       + receiver + eligibility predicate
       -> CommonEligibilityChunkV2
            -> CommonEligibilityStreamV2
                 + task-size/planning/receiver-universe roots
                 -> CommonEligibilityBasisV2

CommonEligibilityBasisV2
  -> CommonEligibilityBasisSetChunkV2
       -> CommonEligibilityBasisSetV2
            -> BudgetScheduleSetV2

CommonEligibilityBasisV2
  -> BudgetScheduleEntryV2
       -> BudgetScheduleV2
            -> BudgetScheduleSetV2

planning + public + active lazy + materialized manifest + schedule set
  -> EpisodeMaterializationBindingV2

planning + public + active intent + active lazy + materialized manifest
  + materialization binding + schedule set + controller config
  -> ArmBudgetExecutionBindingV2

destination S constructor config + selected edges/derived graph
  -> S OOD controller config

S N=16 qualification + destination receiver/ACL/graph/controller config
  -> SScaleOODExtrapolationReceiptV2
       -> S OOD controller dependencies

G N=16 checkpoint + destination graph/allowlist/frozen numeric config
  -> G OOD controller config

G OOD controller config + source S + SScaleOODExtrapolationReceiptV2
  + planning/G-intent/destination identities
  -> GScaleControllerInputBindingV2
       -> G OOD controller dependencies

public + controller config + declared dependencies
  -> ControllerInitialStateV2

public + basis + controller config + initial/prior semantic controller state/dependencies
  -> ControllerInputStateV2
       + basis
       -> ControllerStateTransitionV2
            -> next-step ControllerInputStateV2

ControllerInputStateV2 + ControllerStateTransitionV2
  + NativeSelectionPolicyV2 + RankContractV2
  -> PreCapCandidateV2
       -> PreCapChunkV2
            -> PreCapFinalReceiptV2

ControllerStateTransitionV2 + NativeSelectionPolicyV2 + RankContractV2
  -> PreCapFinalReceiptV2

execution binding + AttemptIdentityV2 + controller input
  + output transition/final + source/supervisor
  -> ProcessLaunchReceiptV2

execution binding + AttemptIdentityV2 + PreCapFinal + ProcessLaunchReceiptV2
  + ControllerStateTransitionV2 + NativeSelectionPolicyV2 + RankContractV2
  -> PreCapExecutionReceiptV2

GScaleControllerInputBindingV2 + OOD PreCapFinal/projection rows
  -> ScaleOODTransferReceiptV2

PreCapFinal + PreCapExecutionReceiptV2 + BudgetScheduleEntryV2
  + ControllerInputStateV2
  + NativeSelectionPolicyV2
  -> CommonBudgetReducerV2
       -> bundle/run/trace
```

`stale-descendant` negative 只改变一个上游 field，重算 mutated object root，但故意保留
至少一个旧 descendant。Receipt 另绑定
`first_stale_descendant_root`，expected code 固定
`G3-LINEAGE-STALE-DESCENDANT`。若 mutation 后完整重算全部 descendants，则它不是
stale negative：

- 改变 frozen axes、planning root、source lock、budget ID 或 active intent mapping 时
  以 `G3-FROZEN-IDENTITY-MISMATCH` 拒绝；
- 其他 schema-valid public/basis/schedule change 形成新 experiment lineage，不能替代
  原 expected root，也不能算原 fixture 通过；
- 不能仅因 mutated root 与 base root 不同而声称 schema rejection。

任一 eligibility/token preimage mutation 都必须改变 basis root，即使 floor 后全部 cap
数值碰巧相同；basis-set、所有引用该 basis 的 schedule entries、schedule 和
schedule-set roots 也必须改变。
Schedule-entry mutation 必须向前传播到 schedule、schedule set、bindings、reducer 和
run/trace roots；schedule-set-only mutation 不得反向改变既有 entry。Basis mutation
必须传播到 basis-set/entry/schedule/schedule-set/controller state/PreCap/reducer/
run/trace。Eligibility stream/chunk/order/token mutation 必须先改变 stream/basis，再
传播完整 basis descendant chain。Initial-state mutation 必须传播到 step-0
input/transition/PreCap 和全部
后续 state lineage；state-transition mutation 必须传播到
candidate/chunk/final/execution receipt/reducer/run 与下一 step input。
Native-policy 或 rank-contract mutation 必须传播到
candidate/chunk/final/execution receipt/reducer/run/trace。每种 fixture
只要求真实 descendants 改变，禁止要求 ancestor 或 sibling 反向变化。未传播即由
stale-descendant fixture 捕获。

Descriptor/meta fixtures 必须拒绝 opaque constraint text、unknown/untyped arithmetic、
错误 floor-div/mod、missing required contract、self-reported pass、unguarded type-cycle
back edge、same/future ordinal predecessor 和真实 instance root cycle；同时必须接受
合法 eligibility/basis-set/PreCap chunk、attempt/prior-step 的 strictly-decreasing
predecessor chain；producer source 包含 generated candidate、qualification/review
records 进入其 referenced candidate tree 或任一 receipt/tree self-root 也必须拒绝。
Program-set fixtures 必须拒绝 literal 14-row inventory count/key/root 变化、Set expected
root 不等于 inventory、expected key/binding projection 不等、
late-added/substituted program root、missing/extra/duplicate key/root、component plan
引用非 member、ExpectedInventory/ProgramSet/Plan/Profile ontology roots 不等，或
program identity/ontology mismatch。Activation fixtures 另拒绝
reviewed bytes 原地改写、binding 自报替代 allowlist、review/profile/binding allowlist
root 不相等、changed-path root 与 reviewed exact one-path list 不相等、missing allowed
path、allowed delta 外新增 path、reviewed/result commit 任一无法解析或对应
commit/tree/source-tree root
不等、reviewed tree 已含 target path、`change_kind!=add`、changed-path file
mode/blob/raw hash/byte count/schema/recomputed profile root 不等、candidate/path
binding 被写入其自身 result tree、activated profile 反含
activation root、unexpected/executable diff 非零，或 registry 的
profile/candidate-binding/activation roots 不相等。

Budget/reducer 必须拒绝：

- 六档 `(0,0,0)`、natural-as-zero、错误 iso 或 float 0.35；
- missing/duplicate entry、entry/schedule basis 不等、arm-dependent basis、
  ScheduleSet 与 Public/BasisSet context 不等、schedule-index coverage
  missing/extra/duplicate/cross-graft、non-monotonic caps；
- eligibility predicate/order/token estimator 变化、stream 未 close、非 4096 chunk、
  eligibility/basis-set chunk schema 或 predecessor 错误、basis/stream roots/count/tokens
  不等、Stream/Basis public/receiver/step/predicate context 不等、
  Basis/Set 与 dereferenced Public 的 task-size/planning/universe/steps 不等、
  chunk/Set context 不等、index row graft 另一 basis/receiver context，或
  materialize full prefix Cartesian arrays；
- F 1.00 不恢复 natural；
- pre-cap truncation 或 oversized top event 后不继续 backfill；
- PreCapCandidate unknown/reordered field、非法 filter/priority/demand；
- step-0 缺/伪造 initial-state contract/payload，controller-input-state root 缺 prior
  lineage，G 漏 checkpoint/seen-clusters，或 R 漏 field/habituation/cluster-history；
- ranking/state 读取 budget layer、manifest marker、effective cap 或 selected history，
  state-transition 两个 read count 非零，同 arm/receiver/step 八层 input/output/
  transition/PreCap/rank roots 不相等，下一 step parent output/transition root 不匹配，
  process launch receipt 缺 supervisor provenance/source/zero-secret/network-isolated/
  no-access/no-use proof、与 PreCap receipt identity/output 不相等、八层 process identity
  不唯一，或用一次 cached ranking execution 伪造八份 fresh receipts；
- 把 R 的 subject-4/ref-2 policy 压成 global top-8，flat/native group ordinal 错误，
  iso/sweep 偷用 natural native policy，或 R iso/sweep 回落到 priority/event-id 而不
  使用 subject/member rank；
- stream 未 close、basis coverage missing/extra/duplicate；
- 非 canonical 4096 chunk、zero-row chunk 或 q9 grammar/quantum 变化；
- Candidate/RankContract 的 `ranking_contract_id` 或 controller ID 不相等；
- candidate/chunk/final 任一 basis/controller/config/input/transition/native/rank/
  receiver/step context 混根；
- candidate event ID 对应的 event root/evidence ref/token demand 与 eligibility stream
  canonical row 不相等；
- selected/filtered/budget-dropped partition 或 roots 不闭合；
- tie-break、drop-reason precedence、backfill 或 payload-order 变化；
- eligibility/token mutation 不改变 basis/schedule lineage root，即使 cap value 不变；
- sidecar/future/outcome 影响 basis。

S/G 必须拒绝：

- N=4 graph/checkpoint 加载到 N=16；
- unknown graph endpoint、错误 receiver/ACL/S root；
- S 读取 payload/future/forbidden sidecar；
- 缺 candidate/metric/tie-break/cost；
- source/destination/ACL root 合并、跨 tenant edge 或 v1 payload 被静默改写；
- v1→v2 receipt 把 N=16 new qualification 伪称 migration；
- S N>=64 缺 pre-execution extrapolation receipt/cost pool、加载 source N=16 edge IDs，
  或 destination receipt/config/state roots 不相等；
- G 缺 task/N、正负 labels、54-grid 或 training cost；
- G 读取 smoke/pilot/confirmatory/provider labels；
- G callsite overlap、checkpoint occurrence 同时计入 train/checkpoint；
- N>=64 写 `out_of_support=false`/`outcome_qualified=true`；
- G N>=64 缺 pre-execution controller-input binding、config root 反向引用 binding/self、
  source checkpoint/S 不匹配、state 未绑定 destination graph，或用 source edges
  计算 destination feature；
- S receipt、G binding 或 post-transfer receipt 的 planning/task/seed/repeat/N/E/step/
  layer identities 不相等，或 S/G active intents 不是同 cell 的 respective natural
  intents；
- scale execution 缺 active v0.5 planning root 或不是完整 140/980 mapping；
- scale mechanics 进入 outcome aggregate。

Cost/attempt 必须拒绝：

- missing/extra/duplicate slot 或 applicable missing-as-zero；
- ontology field 缺失、乱序、unknown、profile derivation program 缺失/读取 result/
  不能重建 exact rows、applicability/observation profile-set coverage 不完整或错误
  version；
- expected/observed state 混写，或 conditional retry activation 不满足 policy；
- double/unowned occurrence；
- occurrence formula、null handling、local ordinal、consumer order/root 变化；
- shared/G allocation membership 不是 complete locked predicate、source cost cell 与
  physical total 不相等、不守恒或 physical+allocation double count；
- aggregate 缺 view selector、使用非法 `both` 或混合 primary/OOD consumer scope；
- 失败 consumer 被移出 denominator；
- observation 使用非冻结 API/boundary、required 降级 optional、missing 状态不合法、
  进入 replay root或缺 provenance；
- retry 覆盖 prior failure、删除 timeout/crash/partial attempt；
- completed-only primary aggregate；
- invalid attempt ordinal/parent/retry predicate；
- verifier 与 builder 共享实现。

P/T1 必须拒绝：

- P 缺 step/parent/before-after/policy/topology，或用 zero-decay/no-diffusion shim；
- 未获 authority 修改 ABI/Trace/Conformance/TCK，或把 `P-v3-diagnostic` 放入 primary；
- T1 cell axes 改变，observed count 非 80/640，layer 缺失/增加；
- 把 640 schedule cells 写成 640 public generations；
- `sealed_evaluator_enabled`/`provider_adapter_enabled` 非 false、network/credential 可见或
  outcome 字段非空；
- shared generator/eligibility 被每 layer 重复记 physical cost。

## 10. Fail-closed gates

下列是未来 activation candidate 必须实现的 proposed subgate contracts；本 draft 的
`gate_changes={}` 表示它们现在不改变任何 active gate 状态：

```text
G3-CONTRACT-DESCRIPTORS
G3-G2-PREREQUISITE
G3-BUDGET-SCHEDULE
G3-PRECAP-RANKING
G3-S-SIZE-QUALIFICATION
G3-G-DISTRIBUTION-QUALIFICATION
G3-COST-LEDGER-V2
G3-P-LIFECYCLE
```

任一 blocked，aggregate G3 blocked。`T1-F-cost-mechanics-qualified` 只解除 narrow slice；
N>=64 OOD mechanics 不解除 S/G outcome qualification；P 在当前 authority 下继续 blocked。
Timeout/OOM/crash/quarantine/tamper/verifier mismatch 必须保留，不得删失败记录升级 gate。

所有 G3 gates 通过前，不执行 provider canary、pilot、confirmatory 或 hypothesis
evaluation。

## 11. Execution order

本 draft 的 control fields 仍禁止实施。未来若发起单独 methodology
review/activation，唯一允许流程如下；steps 1–2 只可生成 non-executable
candidate/registry artifacts，在 step 2 的独立 activation 与 lock fresh-readback 完成前
不产生 implementation authority：

1. 先在不含 executable source 的 atomic methodology candidate 中 materialize Section 8
   exact meta schema、literal-derived expected-program inventory、reviewed
   `CostProfileDerivationProgramSetV2`、exact one-path
   `MethodologyActivationAllowedChangedPathsV1`、`ContractDescriptorSetV1`、guarded
   dependency SCC graph；producer source 必须 pre-exist 且排除 generated artifacts。
   先提交该 immutable candidate tree，再由 source-independent verifier 在 tree 外
   materialize `ContractDescriptorSetQualificationReceiptV1`；qualification receipt、
   reviewed-profile record 和 review receipt 均不得写回其 referenced tree；
2. 在 tree 外独立审阅该 exact candidate；只有 set/receipt/profile review roots 全部
   exact 通过，
   才可按 canonical allowed delta materialize `ActivatedMethodologyProfileV1`，再生成
   只新增该 one-path profile 的 immutable result commit/tree、out-of-tree
   `MethodologyActivationChangedPathBindingV1` 与
   `MethodologyActivationCandidateBindingV1`，最后生成外部
   `MethodologyActivationV1` registry record；methodology lock 原子绑定 profile/
   candidate-binding/activation roots，不把 activation root 写回 reviewed/body bytes；
   tree diff 必须 exact 等于 reviewed allowlist 的单个 activated-profile JSON path，
   不能由 binder 扩张。
   只有单独 lock migration 与 fresh readback 后，实现 authority 才生效；当前 draft 的
   false/null 值不能由 runtime override、孤立 boolean 或未审 result tree 替换；
3. 然后才在 external lab 完整实现 budget、PreCap/CommonBudgetReducer、S/G v2 constructors、
   controller-state/native-policy、CostOntology/applicability/observation profile sets、
   slot/attempt/observation/occurrence/allocation contracts、independent verifier 和全部
   negative fixtures；
4. 将完整 external implementation 提交为 immutable implementation commit；dirty 或
   uncommitted source 不得进入下一步；
5. 从该实现重建 N=4/N=16 S/G artifacts 与 v1→v2 receipts，提交 artifact rebuild；
   rebuild 后的最终 clean external source commit 是唯一 qualification source；
6. 形成单独 source-lock migration candidate，绑定最终 commit、source-tree root、
   artifacts 和 active profiles；本 draft 的 `lock_migration_allowed=false` 不因此自动
   改变，migration 必须另审；
7. Source lock 获批后先运行 G0，并验证 clean worktree、profile/artifact/source identities；
8. G0 通过后运行 G1 typed log、attempt/cost schemas、zero authority 和 independent
   replay；
9. G1 通过后，在新的 locked source 上重跑完整 G2，而不是复用旧 source 的 G2 receipt；
10. G2 aggregate 通过后才 materialize exact T1/F slice；
11. 独立验证 80 bases、80 budget-blind state/PreCap roots、640 schedule cells、
   640 fresh PreCap execution receipts、640 bundles、8 initial attempts、slots、ownership、
   view、allocation、observations 与 zero evaluator/provider/network；
12. 全部通过才记录 narrow `T1-F-cost-mechanics-qualified`；
13. 再扩展 N=4/N=16 S/G、其他 primary arms 和完整 actual ledgers；N>=64 只运行 OOD
    cost mechanics；
14. Primary P 与 aggregate G3 继续 blocked，直到新 authority 允许独立 Hybrid Replay v3
    core change；`P-v3-diagnostic` 仍排除 primary；
15. 只有 G0-G3 全部通过后，才可另行授权 provider canary。

Descriptor lock 后任何 schema/descriptor change 先返回 step 1。Source lock 后任一影响
executable source、constructor、artifact、schema、fixture 或 verifier 的 change 都使
后续 receipts stale，必须从新 implementation commit、S/G rebuild、source-lock
migration、G0、G1、完整 G2 到 T1 slice 全链重跑；禁止只重跑被认为“相关”的尾部测试。

本 draft 不提供 activation、provider 或 scientific-claim authority。
