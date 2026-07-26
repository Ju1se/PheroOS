# Receptor-Gated Ligand Field Experiment Profile v0.5

状态：active G2 deterministic-environment and intent-matrix freeze；先于任何
outcome-bearing/full-smoke/provider 调用；不构成 H1-H6 结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

被取代的执行 profile：
[v0.4](receptor-ligand-field-experiment-profile-v0.4.md)

## 1. Change control 与边界

v0.5 只冻结 v0.4 明确保留为 blocked 的 T4 deterministic environment、G2
counterfactual intent matrix、compact eligibility 和 fresh-process replay 条件。形成本
amendment 前：

- 没有执行 provider request；
- 没有运行 full smoke、pilot、test 或 confirmatory arm；
- 没有读取 smoke、pilot、test 或 confirmatory sealed outcome；
- 没有用 controller success、cost、ranking 或 evaluator 输出选择本文件参数；
- `hypothesis_conclusions` 为空。

H1-H6、estimand、MESI、统计规则、split、seed、repeat、共同预算、authority、Optimal
Commit、fallback/output authorization、claim gate 和 protocol-core baseline 均不改变。
v0.4 保留为历史记录；本文件未明确替换的 v0.4、v0.3 和 v0.2 条款继续适用。

本文件是 documentation-only research freeze，不新增或修改 PheroOS ABI、schema、TCK、
Governance、Trace、Conformance 或示例。下列 environment、runner、sidecar、controller
adapter、cost collector 和 evaluator 全部只能实现在 external research lab。它们的所有
authority 字段固定为：

```text
authority_scope = none
commit_authority = false
output_authority = false
publication_authority = false
```

Scheduling 和 fallback 只改变模拟环境状态，不获得 protocol Commit 或真实执行权限。

## 2. T4 deterministic environment commitment

每个 T4 intent 在 controller 获得 prefix 前生成 canonical
`T4EnvironmentCommitmentV1`，绑定：

```text
schema, matrix_kind, task_id, split, seed, repeat
agent_count, event_count, steps, severity
job_declaration_root, worker_declaration_root
failure_schedule_commitment_root
topology_contract_root, sealed_evaluator_spec_root
```

完整 future schedule 只存在 sealed sidecar。Runner trace 保存 commitment root；普通
controller context 不得包含该 root 或其他会随 future suffix 改变的 digest。

### 2.1 Job 和 worker declarations

令 `W=agent_count`，capability vocabulary 为按字符串升序排列的
`capability:0000 ... capability:(K-1)`，其中 `K=min(16,W)`。Worker `w`：

```text
worker_id       = canonical_id("t4-worker", w)
capabilities    = {capability:(w mod K), capability:((w+1) mod K)}
capacity_units  = 1 + draw("t4/worker-capacity", w) mod 2
```

Job count 按 v0.2 的 smoke/pilot `32/64` 含义冻结，不得按 seed
奇偶改变任务规模：

```text
J = 32          if matrix_kind=smoke
J = 64          if split in {pilot,confirmatory_reserved}
J = event_count if matrix_kind=scale
```

G2 不运行 pilot/confirmatory；第二行只消除 v0.2 的歧义。Job `i`：

```text
job_id               = canonical_id("t4-job", i)
subject_id           = canonical_id("t4-subject", i)
arrival_step         = floor(i * steps / J)
required_capability  = capability:(i mod K)
work_units           = 1 + draw("t4/work-units", i) mod 4
parallelism_cap      = 1
```

Dependencies 是最多两条、只指向更小 job index 的 DAG：

```text
dependency_1 = i-K  if i >= K
dependency_2 = i-1  if i > 0 and i mod 8 == 0
```

重复 dependency 合并。Deadline 是 inclusive：

```text
deadline_step =
  min(steps-1, arrival_step + 2 + work_units + dependency_count)
```

每个 job 声明一个 environment-only `defer` fallback receipt。它不是 PheroOS candidate、
safe collective fallback 或 output authorization。

Declarations 按 canonical ID 排序，使用 v0.2 RNG 和 canonical JSON。未来 job declaration
在其 `arrival_step` 前只由 commitment 覆盖，不进入 controller-visible prefix。Dependency
只能在其所有 parent 已 arrival 后变为 runnable。v0.3 要求的 opaque declared subject
universe 和 topology epochs 仍可预先公开，但不能借此公开 future job attributes。

### 2.2 Failure、recovery 和 partial work

每 episode 选择：

```text
failure_count = ceil(0.10 * W)
```

个不同 worker。选择顺序为
`(draw("t4/failure-worker",worker_ordinal),worker_id)`，取最小值。
令 `shift_step=max(1,floor(steps/2))`。被选 worker 按 canonical rank `r` 生成：

```text
failure_step =
  shift_step +
  draw("t4/failure-step", r) mod max(1, steps-shift_step-1)

failure_duration =
  1 + draw("t4/failure-duration", r) mod
      min(3, max(1, steps-failure_step))

recovery_step = min(steps, failure_step + failure_duration)
```

Failure schedule 的完整内容 sealed；普通 controller 只在对应 logical step 看到
failure/recovery receipt。Worker 在 `[failure_step,recovery_step)` capacity 为零。
Failure 在该 step 的 work quantum 前生效：此前完成的 partial work 全部保留，当步不记
work，assignment 被释放。Recovery 从 `recovery_step` 的 scheduling phase 起恢复声明容量。
每次变化必须记录 previous/new state、retained work、released assignment 和 lineage。

## 3. Prefix-causal transition contract

每个 logical step 严格按以下顺序运行：

1. reveal 当步 job arrivals、failure 和 recovery receipts；
2. 对 failure 释放 assignment，并保留已完成 partial work；
3. 用上一步的 terminal receipts 释放 dependencies；
4. 计算 runnable jobs、healthy capacity、ACL/capability eligibility 和 congestion；
5. 向 controller 提供 `T4ControllerPrefixV1`；
6. 接收 zero-authority `T4SchedulingDirectiveV1` proposal；
7. fail closed 验证 assignment、capacity、parallelism、ACL 和 capability；
8. 按 `(job_id,worker_id)` 执行一个 work quantum；
9. 发出 completion receipts；
10. 对当步 inclusive deadline 后仍未完成的 job 发出 `defer` fallback receipt；
11. canonicalize state、cost、trace 和 state root。

一个 accepted `(job,worker)` assignment 消耗 worker 一个 capacity unit并增加 job 一个
work unit；同 job 同 step 最多一个单位。`complete` 和 `defer` 都是 terminal environment
receipt，并在下一 step 释放 dependent job；`defer` lineage 必须把 downstream 标为
degraded。Episode 结束时所有非 terminal job 获得
`episode-end-defer`，不得作为 missing observation 删除。

`T4SchedulingDirectiveV1` 必须列出其 prefix 中的 proposed/selected/dropped partition、
reason 和 source percept root。Invalid proposal 被记录并拒绝，不能被 runner 静默修正。
它只是一项模拟 proposal：

```text
authority_scope = none
commit_authority = false
```

Controller-visible prefix 只包含：

- 已 arrival job 及其已揭示 dependencies、deadline 和 fallback kind；
- 截至当前 step 已揭示的 failure/recovery/completion/fallback receipts；
- 当前 healthy worker capability/capacity；
- 当前 active topology epoch；
- 当前 runnable、assigned、partial-work 和 congestion state；
- 当前 ACL/capability eligibility descriptor root。

它不得包含 future job、future failure/recovery、sealed eligibility label、oracle schedule、
expected completion、future congestion 或 evaluator denominator。替换 step `t` 后的 sealed
suffix，不得改变 `0..t` 的 prefix bytes、directive、environment state 或 trace records。

## 4. Congestion、deadline 和 sealed evaluator

对 capability `c` 和 step `t`：

```text
demand(c,t) =
  sum remaining_work_units of runnable jobs requiring c

capacity(c,t) =
  sum free capacity_units of healthy workers providing c

congestion_units(c,t) = max(0, demand(c,t)-capacity(c,t))
congestion_ratio(c,t) = q12(demand(c,t) / max(1,capacity(c,t)))
```

该 public current-step congestion 可生成 v0.2 congestion ligand，但不能泄漏 future
demand。Evaluator 在独立 sealed sidecar 中使用 immutable environment receipts，计算：

```text
productive_units(t)
capacity_upper(t) =
  min(total_healthy_capacity(t), total_runnable_remaining_work(t))

normalized_performance(t) =
  1                                      if capacity_upper(t) == 0
  productive_units(t)/capacity_upper(t)  otherwise

post_shift_auc =
  mean(q12(normalized_performance(t)))
  for t in [shift_step, steps)

on_time_completion_rate
deadline_fallback_rate
degraded_dependency_rate
congestion_area
failure_recovery_lag
invalid_assignment_count
capacity_violation_count
acl_violation_count
authority_violation_count
```

Ratios 和 means 使用 Decimal precision `34`、`ROUND_HALF_EVEN`、q12。Independent
evaluator 必须从 receipts 重算，不能 import controller ranking/helper。普通
`F/P/S/B/Q/G/R` 永远不能读取 sidecar；只有 v0.3 的 excluded oracle diagnostic 可读，且其
read 必须显式记录。G2 要求 ACL、capacity 和 authority violation 全为零，但 evaluator
数值仍只是 task-fidelity/mechanics evidence，不支持 H1-H6。

## 5. Compact eligibility 和 scale sharding

`1024 agents * 100000 events = 102400000` 个潜在 receiver-event refs。External lab
不得把该 Cartesian product 写成显式列表。Scale 使用 canonical
`EligibilityDescriptorV1`：

```text
receiver_shard_size = 64
event_shard_size = 4096

eligible(receiver,event,step) iff
  same tenant and scope
  and ACL/public predicate passes
  and required_capabilities subset of receiver capabilities
  and event.logical_time <= step
  and event is the current active version
```

Receiver/event 分别按 canonical ID 排序后切 shard。Descriptor 绑定 shard bounds、
tenant/scope/ACL partition root、capability mask、active-version root、eligible count 和
canonical predicate version，不列举 pair。按 receiver 请求流式展开时，输出顺序仍为
`(receiver_id,event_id)`；selected refs 必须附 descriptor root 和 membership proof。

Scale trace 用 descriptor root、count 和 selected/dropped subroots 完整承诺 partition，
不得伪造零成本或遗漏 dropped set。Ledger 分开记录 logical pair count、实际 predicate
evaluations、materialized refs、descriptor bytes、shard reads 和 peak resident shard。
Descriptor/shard 是 external research artifact，不是 PheroOS ACL、Kernel 或 Trace ABI。

## 6. G2 counterfactual intent matrix

统一计数单位为一个：

```text
task * arm * environment cell * budget layer
```

的 `arm-budget intent`。相同 environment cell 的七个 arms 和全部 budget layers 共用同一
`environment_commitment_root`。由于冻结的 `EpisodeManifestV1` 将 budget 纳入身份，
不同 budget layer 的 episode/manifest root 可以不同；controller ID 也必须进入 intent
root，但不能进入公共 environment root。

### 6.1 Smoke/attack layers

v0.2 smoke base 每一个 budget layer 精确为：

```text
7 tasks
* 7 arms (F,P,S,B,Q,G,R)
* 2 agent counts (4,16)
* 2 severities (0,0.25)
* 2 seeds (9000,9001)
* 2 repeat IDs (0,1)
= 784 arm-budget intents
```

其中 severity `0` 是 paired no-attack control，`0.25` 按 v0.2 固定 injection order 和
`floor(severity*attackable_slots)` 形成 attack intent；inapplicable attack kind 必须显式
记为 `not_applicable`。Pilot-only severity `0.10/0.50` 不被偷偷提升到 G2 smoke。

预算是正交层，不是额外 task 或 scale cell：

| budget layer | intents |
| --- | ---: |
| natural | 784 |
| iso | 784 |
| sweep `0.10` | 784 |
| sweep `0.20` | 784 |
| sweep `0.35` | 784 |
| sweep `0.50` | 784 |
| sweep `0.75` | 784 |
| sweep `1.00` | 784 |
| **smoke/attack total** | **6272** |

这对应 `112` 个 underlying environment cells、每个 cell 七 arms、八 budget layers。
G2 只生成、校验和在 sealed evaluator disabled 下 fresh-process 重放 simulator
mechanics 与 intent records；在 G3 通过前不得执行 outcome-bearing full smoke。

为使 G2 与 G3 可独立判定，G2 的 transition replay 使用单独声明的
`G2NoOpDirectiveV1` diagnostic：它对完整 prefix 提议空 assignment，具有零 authority，
因此所有 terminal defer、failure、deadline 和 state transitions 仍可重放。它不冒充
F/P/S/B/Q/G/R，也不产生 controller cost 或 baseline fidelity 证据。七个 arm ID 在 G2
只作为未来执行 intent/config binding；真实 controller execution、P durable replay 和
每-arm cost ledger 仍只由 G3 判定。

### 6.2 Scale layer

Scale 沿用上位 v0.1 计划冻结的完整五档 capability curve：

```text
(agent_count=4,    event_count=100)
(agent_count=16,   event_count=1000)
(agent_count=64,   event_count=10000)
(agent_count=256,  event_count=100000)
(agent_count=1024, event_count=100000)
steps=50
severity=0
budget=natural
matrix_kind=scale
outcome_authorized=false
```

使用 smoke seeds/repeats，但其独立 `matrix_kind`、event count 和 steps 使其不与 smoke
重复：

```text
7 tasks
* 7 arms
* 5 scale pairs
* 2 seeds (9000,9001)
* 2 repeat IDs (0,1)
* 1 natural layer
= 980 arm-budget intents
```

Scale 只验证可生成性、compact eligibility、replay、成本完整性、资源上限和
ACL/authority invariants；不运行 sealed evaluator outcome，不进入 H1-H6。Iso/sweep scale
未被预注册，不能在结果产生后追加。

因此 v0.5 的完整、无重复 G2 intent set 为：

```text
6272 smoke/attack + 980 scale = 7252 arm-budget intents
```

历史性的 `1232` 和草案中的 `6664` 都不是本 profile 的有效计数：前者混用了
episode-manifest、arm intent 和 budget intent 单位；后者遗漏了上位计划中的三个 scale
档位。Fresh-process A/B replay 是同一 intent 的验证副本，不把 `7252` 再乘二。

## 7. Fresh-process replay 与 fail-closed gate

两个无共享 cache、global RNG、process-local cursor 或 adaptation state 的新进程，必须对
全部 `7252` intents 在 sealed evaluator disabled 的 qualification replay 中生成
byte-exact 相同的：

- intent、episode、environment 和 topology roots；
- 每 step controller prefix 和 eligibility descriptor roots；
- failure/recovery/partial-work transitions；
- no-op scheduling validation、environment state、simulator cost 和 canonical trace
  roots；不得把它们写成 controller cost；
- 仅在独立、非 smoke 的 evaluator contract fixture 中，sealed evaluator records。

Wall/CPU/RSS 等 observation 不进入 replay root。运行时 timeout、crash、invalid manifest、
missing shard、hash mismatch、directive rejection、fallback 和 partial work 全部保留在
immutable intent-to-run ledger；不得删除失败后只重跑成功样本。任一 intent 缺失、
fresh-process root 不一致、显式 materialize 102.4m refs、sidecar leak、ACL/capacity/
authority violation，均保持：

```text
G2-TASK-FIDELITY = blocked
G2-DETERMINISTIC-MATRIX = blocked
```

只有全部 T1-T7 environment、`7252` intent roots、T4 state machine、sharding 和 replay
mechanics 通过，才可升级 G2。G3 仍独立要求强 baseline、P durable multistep 和实际 cost
ledger 完整；G1-G3 全通过前，full smoke、provider canary 和 pilot 继续 fail closed。

本证据最多证明可重复、权限中性的 deterministic research mechanics，不能证明
receptor-gated ligand field 优于 sparse communication、blackboard、retrieval routing、
learned graph pruning 或 scalar PheroOS。
