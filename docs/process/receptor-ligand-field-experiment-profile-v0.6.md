# Receptor-Gated Ligand Field Experiment Profile v0.6

状态：active G2 attack-label firewall amendment；先于 G2 matrix qualification、
outcome-bearing/full-smoke/provider 调用；不构成 H1-H6 结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

被取代的执行 profile：
[v0.5](receptor-ligand-field-experiment-profile-v0.5.md)

## 1. Change control 与证据边界

v0.6 只修复 G2 implementation audit 在 outcome 产生前发现的 attack-label
歧义。v0.2/v0.5 的 `severity=0` 禁止可变 severity injection，但 T2、T3 和 T6 的任务
定义本身仍包含 correlated clones、false alarm 和 correlated local optimum。把
`severity=0` 写成整个 episode 的 “no attack” 会把 task-intrinsic stress 错误归因于
可变攻击，破坏 paired attack estimand。

形成本 amendment 前：

- 没有完成或资格化 G2 matrix/T4 environment；
- 没有执行 full smoke、pilot、test、confirmatory 或 provider request；
- 没有读取 smoke/pilot/test/confirmatory sealed outcome；
- 没有用 controller success、cost、ranking 或 evaluator 数值选择本文件规则；
- `hypothesis_conclusions` 为空。

H1-H6、estimand、MESI、split、seed、repeat、预算、7,252-intent count、T4 state
machine、authority、Optimal Commit、fallback/output authorization 和 claim gate
均不改变。v0.5 保留为历史记录；本文件未明确替换的 v0.2-v0.5 条款继续适用。

本 amendment 只约束 external research artifacts，不增加或修改 PheroOS ABI、schema、
TCK、Governance、Trace、Conformance 或生产代码。

## 2. 三种互不替代的 stress 身份

External lab 使用版本化 sealed `GroundTruthSidecarV2`，至少分开：

```text
variable_attack_event_ids
intrinsic_challenge_event_ids
mandatory_probe_event_ids
```

三组均不得进入 ordinary controller context、event tag、payload、subject/candidate ID、
ligand dose 或 public environment metadata。Legacy `attack_event_ids` 若为兼容而保留，
只能是明确标记为 legacy 的 union，不能用于 G2/G5/G6 estimand。

定义：

- `variable_attack_event_ids`：只由 manifest 的 `attack_severity`、冻结 attackable
  universe 和 v0.2 counter RNG 选择；
- `intrinsic_challenge_event_ids`：由 task family 定义、在所有 severity cells
  中保持相同的困难结构；
- `mandatory_probe_event_ids`：不消耗 attack budget 的安全/ACL probe。

同一个 event ID 不能同时属于两组。Sidecar validator 必须拒绝交集、未知 event、
episode mismatch、重复 ID 和非 canonical order。

T4 worker failure/recovery 是 environment stress receipt，不是 communication event。
它在 T4 sealed evaluator artifact 中单独记录，不能塞入任一 event ID group。

## 3. Task-intrinsic challenge universe

在为 variable attack 选择位置前，先从公开 task/seed/repeat/size 与冻结 RNG 计算
`intrinsic_positions`：

- T1：空；
- T2：固定 clone multiplier 对应的 correlated-clone positions；
- T3：冻结 false-alarm position；true hazard 与 mitigation receipt 是 task target，
  不标为 attack；
- T4：空；failure/recovery 使用 environment receipt；
- T5：空；
- T6：verification window 前、按冻结 actor assignment 落入 dominant-correlated
  branch 的 positions；
- T7：空；mandatory probes 使用独立集合。

Intrinsic challenge 的 public event 内容继续遵守 v0.3 neutral-label firewall；sidecar
身份不能改变其 ligand dose、priority 或 ordinary-controller visibility。

## 4. Variable attack universe 与精确 budget

令：

```text
mandatory_positions =
  frozen T7 probes, otherwise empty

attackable_positions =
  [floor(event_count/10), event_count)
  minus intrinsic_positions
  minus mandatory_positions

variable_attack_count =
  floor(severity * len(attackable_positions))
```

按：

```text
(draw("attack-positions", position), position)
```

升序取精确 `variable_attack_count` 个位置。禁止先在全 universe 抽样再与 intrinsic
union，因为重叠会导致实际可变 attack count 小于冻结 budget。T7 cross-tenant canary 和
same-tenant collision 仍由所选 variable positions 构造；mandatory probes 走相同安全
validator，但不计入 severity budget。

`severity=0` 的正确标签是：

```text
variable_attack_injection = not_applicable
attack_severity_control = true
episode_attack_free = false when intrinsic_challenge_event_ids is non-empty
```

`severity=0.25` 的正确标签是：

```text
variable_attack_injection = frozen_v0.2_exact_budget
attack_severity_control = false
```

Matrix intent 必须绑定 task-specific `intrinsic_challenge_profile` 和上述 variable
injection label。它不得把 `severity=0` 简写为 `no_attack`。

## 5. Counterfactual 与 gate consequences

同一 `task/agent_count/seed/repeat/budget` 的 severity `0` 与 `0.25` cells：

- 使用相同 intrinsic challenge positions 和 payload construction；
- 使用相同 mandatory probes；
- 只在 variable attack positions 和由其确定的 attack transformation 上不同；
- 分别保存三组 sidecar roots 和 exact counts；
- controller 不得读取任一 root。

G2 qualification 至少证明：

1. 每个 cell 的 variable count 等于冻结公式；
2. 三组 ID 两两不相交并引用已声明 event；
3. severity `0` 的 variable set 为空，但 intrinsic set 按 task 保留；
4. paired cell 的 intrinsic/mandatory roots 相同；
5. sidecar suffix mutation 不改变 ordinary controller prefix；
6. fresh process 产生 byte-exact 相同的 group roots；
7. ordinary controllers 的 sidecar reads 为零，authority/ACL violation 为零。

任一条件失败，G2 保持 blocked。这个 amendment 只让攻击标签和 paired estimand
可审计，不能证明 RG-LF 比 sparse communication、blackboard、retrieval routing、
learned graph pruning 或 scalar PheroOS 更好。
