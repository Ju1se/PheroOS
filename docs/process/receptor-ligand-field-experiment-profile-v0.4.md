# Receptor-Gated Ligand Field Experiment Profile v0.4

状态：active G1-G3 topology-epoch qualification amendment；先于任何
outcome-bearing arm；不构成 H1-H6 结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

被取代的执行 profile：
[v0.3](receptor-ligand-field-experiment-profile-v0.3.md)

## 1. Change control 与证据边界

v0.4 只冻结第一次 G0-G3 资格验证后发现的动态 topology epoch 合同，以及 T4
provider-free fixture 的精确图变化。形成本 amendment 前：

- 没有执行 provider request；
- 没有运行 full smoke、pilot 或 confirmatory arm；
- 没有读取 smoke、pilot、test 或 confirmatory sealed outcome；
- baseline train/dev sidecar 尚未用于生成本 amendment 的参数；
- `hypothesis_conclusions` 为空。

因此，epoch 边界、图生成公式和阻断条件不是根据 RG-LF 或任一 baseline 的结果选择。
H1-H6、estimand、MESI、统计规则、split、seed、预算、claim gate、provider canary 和
protocol-core baseline 均不改变。v0.3 保留为历史记录；本文件未明确替换的 v0.3 条款
继续适用。

## 2. Versioned topology epochs

每个 `LigandTopologyV1` 增加：

```text
effective_from_step: non-negative integer
```

默认值为 `0`，仅用于兼容 v0.3 的单 epoch fixture。非空 topology contract 必须满足：

1. `(effective_from_step, ligand)` 唯一；
2. 第一个 epoch 必须从 step `0` 生效；
3. 每个 epoch 恰好声明冻结顺序中的八种 ligand；
4. 每个 epoch、每个 ligand 都为完整 declared subject universe 声明一行；
5. v0.3 的 q12、row mass、最大四条 outgoing edge、已声明节点和 ACL partition
   隔离规则逐 epoch 生效；
6. epoch 与 ligand 的 canonical 顺序分别为数值升序和冻结 ligand 顺序。

step `t` 的 active epoch 定义为：

```text
max(effective_from_step <= t)
```

R 在每个 field step 只能读取该 active epoch。若没有 active epoch，继续使用 v0.3 的
fail-closed self-only 语义，且不能通过 R-G3。

Lineage 同时记录：

- `topology_contract_root`：绑定 manifest 预先声明的全部 epochs；
- `active_topology_epoch`；
- `active_topology_root`：只绑定当前 active epoch 和 declared subject universe。

修改未来 epoch 可以合理改变 manifest、contract 和完整 run root，因为调度表是 episode
开始时的公开承诺；但不得改变其生效步之前的 field mass、selection、receiver state 或
active topology root。Fresh-process continuation 必须从 manifest 和 step 重新选择同一
epoch，不能依赖 process-local cursor。

## 3. T4 topology-shift fixture

T4 只从公开的 `task_id/split/seed/repeat/agent_count/event_count/steps/size` 构造图，
不得读取 event payload、tag、candidate、controller output 或 sealed sidecar。
Qualified T4 topology fixture 要求 `steps >= 2`，并声明两个 epochs：

```text
epoch_0_step = 0
epoch_1_step = max(1, floor(steps / 2))
epoch_0_stride = 1
epoch_1_stride = 3
```

对每个 ACL field partition，按 `(subject_id, node_id)` 排列 `n` 个节点。令：

```text
route(i, k) = node[(i + k) mod n]
```

在 stride `s` 的每个 epoch 中，八种图逐 row 定义为：

| ligand | destinations |
| --- | --- |
| utility | `route(i,+s):1` |
| failure | `route(i,-s):1` |
| hazard | `node[i]:0.5, route(i,+s):0.5` |
| uncertainty | `node[i]:1` |
| novelty | `route(i,+2s):1` |
| congestion | `node[i]:0.5, route(i,+4):0.5` |
| recruitment | `route(i,+4s):1` |
| contradiction | even `i -> route(i,+1)`；odd `i -> route(i,-1)` |

若两个 destination 因小图退化为同一节点，先合并质量，再按 q12 规范化；T4 的冻结
`32/64` job 规模不会触发该退化。图生成器必须记录 schema、epoch steps、strides 和每个
active topology root。

机械 fixture 至少证明：

1. step `epoch_1_step - 1` 使用 epoch 0，边界 step 使用 epoch 1；
2. utility/failure 的方向在两个 epochs 都互为反向；
3. 修改 epoch 1 的边，不改变边界前的 field、selection 和 receiver state；
4. checkpoint/restart 与 uninterrupted execution 的 active epoch、field 和 bundle
   字节一致；
5. 缺 epoch 0、不完整八 ligand、重复 `(step,ligand)`、负 step 或跨 partition edge
   均 fail closed；
6. 多 epoch 输入顺序不改变 canonical manifest root。

## 4. T4 仍未获得完整环境资格

本 amendment 只资格化 topology shift mechanics。它不把下列尚未实现的部分写成已经通过：

- job arrival、completion 和 dependency release 的 deterministic state machine；
- receiver/resource capacity 和 oversubscription；
- frozen failure injection、recovery receipt 和 partial-work accounting；
- congestion ground truth 与 deadline/fallback；
- post-shift normalized performance evaluator；
- smoke/attack/scale counterfactual matrix。

在这些环境语义和 evaluator 形成独立、版本化、可重放 artifact 前：

```text
T4 topology_qualified = true
T4 environment_qualified = false
G2-TASK-FIDELITY = blocked
```

S/G 的 dev-only engineering qualification 可以运行 T4 的 topology mechanics，但 artifact
必须标记 `baseline-mechanics-only`，不得把 T4 纳入任务效果、H1-H6 或 baseline
优越性结论。

## 5. Gate consequences

v0.4 生效后，external lock 必须绑定本文件 hash 和其提交。Gate 只能由可执行证据升级：

- R-G3 的 topology-contract 子项可在 epoch、方向、prefix、partition、restart 和
  canonical tests 全部通过后升级；
- G2 继续被 T4 完整环境和完整 counterfactual matrix 阻断；
- G3 继续要求 Q/S/G/R/cost 全部 qualification，并要求 v0.3 所述 P durable multistep
  blocker 被合规解决；
- G1-G3 全部通过前，full smoke、provider canary 和 pilot 继续 fail closed。

这一级证据最多证明版本化动态图合同的确定性与因果边界，不能证明 RG-LF 比稀疏通信、
blackboard、retrieval routing、learned graph pruning 或 scalar PheroOS 更好。
