# Receptor-Gated Ligand Field G0-G3 Qualification Report

状态：G0、G1 通过；G2、G3 阻断；仅工程资格验证，不构成 H1-H6 结果

检查点日期：2026-07-27

## 1. 客观结论

当前证据没有证明 receptor-gated ligand field（RG-LF，实验 arm `R`）优于 full
communication（`F`）、scalar PheroOS（`P`）、static sparse（`S`）、
blackboard（`B`）、BM25 retrieval（`Q`）或 learned graph pruning（`G`）。

研究稿中的 H1-H5 仍是设计良好、可证伪的机制假设，H6 仍是系统级 claim gate；
它们都不是实验结论。“最合适方向”在科研严谨度上只能解释为“理论动机很强的候选
架构”，不能解释为已证实的最优架构。

本检查点的准确解释是：

- G0 的边界与预注册验证通过；
- G1 的 zero-authority controller contract 与确定性重放通过；
- G2 已形成可持久化、内容寻址的局部证据，但完整 scale task-state replay 和全部
  intent 的外部隔离 A/B 尚未完成，因此 G2 总 gate 阻断；
- G3 除 G2 前置条件外，还存在 sweep budget、S/G scale fairness、`P` durable
  lifecycle 和 actual cost ledger 阻断；
- `full_smoke_authorized=false`，provider canary、pilot 和 confirmatory LLM run
  均未获授权；
- `hypothesis_conclusions={}`，`comparative_superiority_conclusion=null`；
- controller execution、evaluator call、provider call、outcome read、credential use
  和 network use 均为零。

API key 不是开始实验的充分条件，当前阶段也不需要 API key。只有 G0-G3 全部通过后，
才可配置并执行 G4 provider canary；正式 provider 配置还必须同时冻结 model/version、
endpoint、采样参数、quota、timeout、retry、价格快照和 cost ledger 规则。

## 2. 冻结身份与证据边界

### 2.1 Protocol-core

- branch：`codex/receptor-ligand-field-experiments`
- protocol baseline：
  `e447d2c96c40b69bb7f98613e23556be7bbe3d76`
- active preregistration commit：
  `3cba9f7f19c6bceb8a6ea545a6ea51b7833446ab`
- 当前局部 G2 evidence 所绑定的 core checkpoint：
  `cfb61386df14a8fbda3504698a45cac18eef9b36`
- active profile：
  `docs/process/receptor-ligand-field-experiment-profile-v0.6.md`
- active profile SHA-256：
  `b1a7aa84664baacdf683af406aa4e88b118ef45b001986e7f438c5d31715a979`
- effective profile chain root：
  `sha256:f77b0da288a73b5e5ce2554c38d4ea1af95fcb4759646f64103d84e80a51b739`
- preregistration lock root：
  `sha256:1b459d9d9043c47d21c4d2a1e61a72bc31a151a0454bba2a960ded3340f17d18`

`v0.7` 是 review draft，不是 active profile，也没有进入 preregistration lock。

### 2.2 External research lab

- branch：`codex/receptor-ligand-field-lab`
- scoped G2 evidence commit：
  `b584bd3`
- refrozen baseline artifact commit：
  `2f1d473a6edb9fba61ccfa39d7214b0d688e44d7`
- source-tree root：
  `sha256:9e3b1884fce7185e910b1d953c0ab1c1c7e690791e9ced2396429cb410352061`
- baseline qualification artifact-set root：
  `sha256:33be52932afba00d461d29016efa6fb6cd2218d6435c0dd470155adc63c4bf7a`
- baseline qualification manifest root：
  `sha256:a9bd29870d3d6b25abf1494e43b7d0dd605912156dba639af531a5d04d411eb6`

冻结 baseline roots：

| Artifact | Root |
| --- | --- |
| Q BM25 golden fixture | `sha256:bf66679dc498e9f4a79c3f8576632904c2865621e8f6a1f82ee87c89b5ae1603` |
| S matched-density fixture | `sha256:f43d2426123eef64933a945e1fc5e371261351048c006fcda9f1037094523238` |
| G Decimal-34 checkpoints | `sha256:7e84caef5fe25f42e5c19194df248a203ee53942b194549bbaea4a8bfca9692e` |
| Qualification manifest | `sha256:a9bd29870d3d6b25abf1494e43b7d0dd605912156dba639af531a5d04d411eb6` |

### 2.3 当前内容寻址证据

局部 G2 bundle 位于 external lab 的
`artifacts/g2-partial-cfb6138-2f1d473/`：

- manifest root：
  `sha256:4f1f2f40ec9b4f45282ba004a7261eb40877696121cf1d3af78e58c0d1cbb2b3`
- artifact-set root：
  `sha256:314b8db4de80f16d66dc1d97b4aecfd2e3d67ac74c419ec3ff43017eef1c9116`
- verification receipt：
  `sha256:1dcc4dd0daff24a653da0f376c2d40adf1b716445723c7f29da6934080da8e6f`

fail-closed qualification run 位于
`runs/g0-g3-cfb6138-2f1d473/`：

- qualification root：
  `sha256:26e8ed58cb424d9ae5f33f2760614fccceb79e83f26af533227a925323d3aa41`
- independently reverified trace head：
  `sha256:19014e9164db4d156bf98a745d0b50247a1921cc06d7818eb13a4096a2263de4`

这些目录被 Git ignore 排除。bundle 证明当前局部 artifact 的完整性和绑定关系，但不
证明 loaded-code identity、publication/crash durability provenance、full-scale
replay、provider effects、hypothesis outcome 或 comparative superiority。

## 3. Gate 结果

| Gate | 状态 | 当前证据或阻断 |
| --- | --- | --- |
| G0 Boundary/Prereg | 通过 | branch、ancestor、immutable Git blobs、active v0.6 profile、prereg lock、core boundary、external source tree 和 refrozen baseline artifacts 通过严格验证 |
| G1 Controller Contract | 通过 | typed closed log、diagnostic-only oracle/random、zero authority、sidecar firewall、deterministic replay 和 secret-free subprocess environment 通过 |
| G2 Deterministic Simulator | 阻断 | 5/7 components 在其明确限定的 scope 内资格化；full scale T1-T7 task state 为 0/980 intents，全部 7,252 intents 的外部隔离 A/B 为 0/7,252 |
| G3 Baseline Qualification | 阻断 | G2 前置未通过；`P` durable diffusion replay 失败；actual natural/iso/sweep ledger 未接入；另有未冻结的 sweep 与 S/G scale fairness 问题 |

`qualify-baselines` 的退出码为 `2`，这是预期的 fail-closed gate refusal，不是 `R`
的 outcome failure，也不能解释为任一 arm 的优劣。

## 4. G2 局部资格证据

冻结 planning geometry 为：

- 112 smoke/attack environments × 8 budgets × 7 arms = 6,272 intents；
- 140 scale environments × 7 arms = 980 intents；
- 共 252 environments、7,252 distinct arm-budget intents；
- scale tiers：
  `(4,100)`、`(16,1000)`、`(64,10000)`、`(256,100000)`、
  `(1024,100000)`，每个 episode 50 steps。

七个 component 必须逐项解释：

| Component | 覆盖 | 状态 | 严格 scope |
| --- | ---: | --- | --- |
| Lazy matrix enumeration | 252 env / 7,252 intents | qualified | 只证明 v0.5 geometry 与 active v0.6 labels 的 planning records |
| Attack label firewall v0.6 | 252 env / 7,252 intents | qualified | 112 smoke manifests materialized；140 scale labels lazy；same-module fresh recomputation，不主张 independent implementation diversity |
| T4 smoke transitions v3 | 16 env / 896 intents / 320 steps | qualified | transcript、matrix binding 与 relational suffix A/B；896 links 仅是环境适用性，不是 arm/budget execution；共享同一 state-machine implementation |
| Compact record-backed smoke | 112 env / 6,272 intents | qualified | 20-step prefix records、selected/dropped full partition、ACL digest 与 receipt |
| Scale eligibility program | 140 env / 980 intents | qualified | 5,910,800 event projections、38,192 receiver records；只证明 eligibility program，不证明 task state 或 full-scale replay |
| Full scale task-state replay | 0 / 980 intents | blocked | 缺少 T1-T7 state preimages/replay，尤其缺少 T4 worker/job/failure/recovery/dependency/deadline state |
| All-intent external A/B | 0 / 7,252 intents | blocked | 缺少隔离 workspace/process 的 byte-exact per-step episode/environment/topology/prefix/eligibility/state/cost/trace attestation |

当前 intent evidence links 共 22,652 条：

```text
7,252 lazy matrix links
+ 7,252 attack-label links
+   896 T4 applicability links
+ 6,272 compact smoke links
+   980 scale-eligibility links
= 22,652
```

这不是 22,652 次 controller execution，也不是 22,652 个 outcome。局部 bundle
明确记录：

```text
controller_execution_count = 0
evaluator_call_count = 0
provider_call_count = 0
outcome_read_count = 0
authority_scope = none
commit_authority = false
output_authority = false
publication_authority = false
network_used = false
```

因此当前 G2 的正确表述是“局部 evidence integrity 与限定 mechanics 资格化”，不是
“G2 passed”，更不是“实验完成”。

## 5. v0.7 review draft

`v0.7` 用于设计完整 scale state、独立 verifier、negative fixtures、resource
supervision 和 A/B materialization contract。它当前只有设计 inventory：

- profile bytes：116,230
- profile SHA-256：
  `8d7dbc32abe7f97142e21570a79e1a0ee64a4e20b66f1fd2b8d36538f2feb8c3`
- companion bytes：62,097
- companion SHA-256：
  `322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360`
- fixture inputs：12；
- positive fixtures：3；
- negative fixtures：56；
- fixture input set root：
  `sha256:0227f38c34f9d50b81b257675065e73ab1c18e02fff684ca851603b3d963aed8`
- positive fixture set root：
  `sha256:2a0e9ff10b6e2d5e2e42bebe77dd9c32f871a48638ad4d41a796995d1ce1613e`
- negative fixture set root：
  `sha256:ae57ce3f050c4f1560026ecb198cb274adfee6ffcf49282fb4520ecf6e12f4e5`
- semantic manifest root：
  `sha256:dfbb83daea99bedc25e91c07f10aa301f42fba93808d57d9e6aaf395ae33feca`

Companion 明确冻结：

```text
activation_ready = false
artifact_bytes_compiled = false
runner_implemented = false
receipt_artifact_bytes_present = false
```

原独立二审发现的 2×P1 与 2×P2 已在 design specification 层关闭：五个
`duplicate` 已成为 literal total transforms；cross-variant code precedence、
base-artifact total order、schema/geometry/resource predicate domains 和 process
measurement constructor 均已冻结。第二位审阅者使用独立 canonical encoder 重算
全部 roots、3 个 positive inputs、11 个 expected receipts、3 个 positive
commitments 和六组受影响 operation/recipe roots，最终严重度为：

```text
P0 = 0
P1 = 0
P2 = 0
P3 = 0
```

这只说明当前 design specification 没有已知的 P0-P3 歧义，不是 materialization
evidence。唯一保留的 activation blocker 是尚未执行的独立 materialization：

1. 从 12 个 constructors 实际生成 base views；
2. 由互不共享 reducer 的 producer/verifier 执行 3 个 positive 和 56 个 negative
   transactions；
3. 保存并复算全部 preconditions、observed codes、receipts、source roots 与
   content-addressed artifacts；
4. 证明 zero authority、zero outcome read、zero network 和 source independence。

在该二审完成以前，禁止把 `activation_ready` 改为 true，禁止 lock migration、
v0.7 runner/reducer 实现或借此宣称 G2 通过。

## 6. G3 客观审计

### 6.1 Sweep budget 是 P0 级 fairness blocker

当前 `tasks._budget` 对 sweep ratios 实际返回的 cap 都为零，且 runner 没有替代的
非零 budget schedule。若直接执行 sweep，所有 arm 会在一个退化的零预算设计上比较，
formal experiment 将无效。必须先冻结每个 task/size/regime 的非零、可复算、跨 arm
一致的 budget mapping 与拒绝规则。

### 6.2 S/G scale policy 尚不公平

`S` 的冻结图只在 4-agent corpus 上选择；用于 16-agent cell 时，12/16 agents 会被
系统性隔离。`G` 继承相同的 graph/distribution 约束。必须在 G3 amendment 中选择并
冻结以下一种策略：

- 限定 `S/G` 只参与其 graph 有效的 size；
- 或预注册 size-specific graph family，并在 train/dev 上重新冻结；
- 或明确定义可跨 size 外推且对所有 arm 公平的 graph construction。

在此之前，不能把 `S/G` 的 scale 结果当作架构效应。

### 6.3 `P` durable lifecycle 仍不闭合

External `P` 每 step 恢复 state；core 路径会先 evaporate trail。现有 diffusion ID
没有绑定 transition step、parent receipt 或 before/after payload，同一 ID 对不同
decayed strength 会被 Hybrid Replay v2 拒绝。

合法修复需要 versioned lifecycle receipt，其 identity 至少绑定 step、parent head 和
transition，其 payload 至少绑定 before/after strength、policy、topology 与 replay
lineage。这会涉及 schema/migration/Trace/Conformance/TCK；当前研究 branch 的严格
约束禁止修改这些 production surfaces。因此不得用 zero decay、删除 diffusion、复用
旧 ID、最小 scalar substitute 或静默外部 shim 伪装成 `P` 通过。应保留 blocker，
或另行取得明确 authority 后通过新版本 contract/新 controller ID 处理。

### 6.4 Cost contract 尚未成为 actual ledger

59-field closed schema 的 self-check 已通过，但 natural/iso/sweep 的 per-run actual
ledger 尚未接入。当前还缺：

- controller 与 shared cost 的唯一归属及防重复记账；
- observation provenance 与 completeness binding；
- sweep cell、environment、intent、run、trace 的完整关联；
- failure/retry/timeout/partial work 的 actual receipts；
- `G` training amortization 的非整数分摊规则及守恒检查；
- 独立 verifier 对 ledger、applicability 和 aggregate 的重算。

因此任何“同等成本下更优”或“更省成本”的结论当前都不成立。

## 7. 验证记录

已执行并保留的验证包括：

- external lab full suite：262 tests，260 passed；两个失败发生在 refreeze 前，分别是
  预期的旧 artifact exact-replay mismatch 与 dirty/lock refusal；
- refreeze 后针对上述两个失败的 exact artifact replay 与 harness/prereg boundary
  tests 均单独通过；不把两次运行拼接伪称为一次 `262/262`；
- active profile identity：7/7；
- Attack evidence：8/8；
- T4 evidence：21/21；
- scale eligibility：15/15；
- CLI/process secret-free environment：12/12；
- prereg hardening：5/5；
- fail-closed partial bundle persistence/tamper/TOCTOU/quarantine：16/16，
  运行约 642.7 秒；
- unified heavy selection 中 4 个真实 tests 通过；命令另含一个不存在的 selector，
  已按原样记录，不伪称该 selector 通过；
- baseline frozen artifacts 在 refreeze 后 targeted exact rebuild 通过；
- provider-contract checks 通过，`network_used=false`；
- bundle roots、counts、positive receipts 与 trace chain 均经独立重算。

上述验证只支持工程资格声明，不支持 H1-H6 或相对性能结论。

## 8. Credential 与 provider policy

本检查点没有读取、保存或使用 provider credential，也没有发起网络请求。任何曾经
粘贴到聊天、issue、terminal history 或 log 的 key 都视为已暴露，必须撤销；不得
复用。

未来只有在 G0-G3 全部通过后，才可使用新轮换且从未出现在记录中的 credential。
允许的本地环境变量名为：

```text
PHEROOS_MINIMAX_API_KEY
PHEROOS_ZHIPU_API_KEY
```

Key 不得写入 Git、`.env`、Trace、report、command argument 或 fixture。子进程默认
使用 secret-free environment；只有获得 G4 gate authorization 的 provider adapter
进程可按最小范围继承对应变量。

## 9. 下一执行顺序

后续仍只做 provider-free gate work：

1. 按已通过 design 二审的 v0.7 specification 独立 materialize 12 个 base views、
   3 个 positive 和 56 个 negative transactions，并生成可检索 receipts；
2. 只有 materialization、source-independence 和全部 root 二审通过后，才形成新的
   activation candidate；profile activation 与 prereg lock migration 仍需单独审阅；
3. 在 external lab 实现 v0.7 producer/verifier/resource-supervisor，并完成 140 个
   scale task-state replays、980 intents 和全部 7,252 intents 的隔离 A/B；
4. G2 总 gate 通过后，先冻结 G3 amendment：非零 sweep schedule、S/G scale policy、
   `P` lifecycle decision 和 cost-ledger v2；
5. 用 sealed T1 的 `F` + shared generator/common eligibility 作为最小 G3 vertical
   slice，执行 natural、iso 和预注册的 6 个 sweep cells，生成 canonical actual
   ledger 与独立 verifier receipt；
6. 再扩展到 `P/S/B/Q/G/R`，保留任何 failure、null 或 negative result；
7. G0-G3 全部通过以前，不读取 API key，不运行 provider canary、pilot 或
   confirmatory LLM experiment。
