# Receptor-Gated Ligand Field G0-G3 Qualification Report

状态：G0、G1 通过；G2、G3 阻断；仅工程资格验证，不构成 H1-H6 结果

检查点起始日期：2026-07-28；本次续审日期：2026-07-29

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
- G3 除 G2 前置条件外，还存在 `P` durable lifecycle、尚未 materialize/激活的
  methodology descriptors 与 actual cost ledger 阻断；inactive G3 draft 已选择
  sweep budget 和 S/G size policy，但尚无 implementation、receipt 或 gate effect；
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
| G3 Baseline Qualification | 阻断 | G2 前置未通过；`P` durable diffusion replay 失败；inactive amendment 尚未 materialize descriptor set 或激活；actual natural/iso/sweep ledger 未接入 |

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

- profile bytes：119,802
- profile SHA-256：
  `bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6`
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

原 text-level 独立二审确实关闭了五个 `duplicate` transform、cross-variant code
precedence、base-artifact total order、schema/geometry/resource predicate domains
和 process measurement constructor，并独立重算了 companion roots、positive inputs、
expected receipts 和 commitments。它当时报告的 `P0=P1=P2=P3=0` 只覆盖所选
design assertions；后续 executable materialization audit 已证明该结论不能解释为
“完整 materialization contract 无歧义”。

新的 [v0.7 materialization audit finding](receptor-ligand-field-v0.7-materialization-audit-finding.md)
发现：

- `BaseMaterializationV1` 没有 exact outer schema、field set、byte contract 和
  root labels；
- `PositiveTransactionProductV1` 没有 exact post-closure object contract；
- `/raw_ndjson_bytes` 没有 canonical JSON encoding；
- `profile_defined_root_pairs` 没有 71-record exact locator oracle；
- `MaterializationReviewInputIdentityV1` 没有绑定上述完整合同；
- 两个 intended whole-document `apply-transform` 的 operation/precondition 共四个
  pointer 使用 `path="/"`，与 RFC 6901 document root `""` 不一致；
- supervisor 的 R7 attack matrix 尚未完整实现。

两个独立 materializer 的局部测试均曾通过，却产生不兼容的 base objects，并共同把
positive payload 错投影成 `fixture_input`。一个 transport-only fake double 还能以
任意 IDs、空 root pairs 和 `E-FAKE` code 达成内部 equality。Public supervisor 现已
加入 `blocked-underspecified-v1` stop-line；当前正确状态是 fail-closed NO-GO，而不是
materialization pass。

该拒绝已在 clean immutable candidate commit
`5c1d2a92b8a257955aa287df674f6d1a32d1f424` 上运行并封存；refusal manifest root 是
`sha256:758fd1e0978da8712a144571ffabd9b1574ba7b7deb1554714fc38b5ac980e22`，
fresh-process reread 为 `verified=true`。

新的
[V2 closure design](receptor-ligand-field-v0.7-materialization-v2-closure-design.md)
进一步确定 normative contract 与 golden oracle 必须分层，避免 profile hash 与
golden payload root 循环；official A/B 不得挂载 oracle。该文件仍只是 unsealed
design，不是 pass。

最终 closure-design 交叉复核固定在该设计文件：

```text
raw_sha256 =
  sha256:1f408183703528066de3545d776e7b7d9f7884610fde8e74a785d7fb60f337d0
independent_read_only_review_paths = 3
residual_undeclared_P0 = 0
residual_undeclared_P1 = 0
residual_undeclared_P2 = 0
```

三路复核先后暴露并关闭了 source-freeze 内容寻址、Oracle/Identity
mix-and-match、closure-review count、main-component tree join、receipt
source-boundary 和 Manifest/SealEvidence 回边。这里的 residual `0` 只表示没有再
发现未登记的内部矛盾；设计文件第 13 节当时列出的 18 项 implementation P1 仍全部开放，
不构成 contract freeze、materialization pass、G2/G3 通过或 activation evidence。

后续
[V2 authoring checkpoint](receptor-ligand-field-v0.7-materialization-v2-authoring-checkpoint.md)
选择 deterministic companion-first amendment，把 71-record design review 与
10,446-record runtime actual chain 分相，并用 external authoring helper 复现四个
RFC 6901 pointer correction。独立代码复核在修复 canonical byte/object
`false == 0` 类型混淆后，对该 helper 的声明边界得到
`P0=P1=P2=P3=0`；targeted tests 为 `19 passed, 9 subtests passed`。该 residual zero
只覆盖 authoring helper，不覆盖正式合同或 evidence。

后续 external authoring commit `cbca3c31184067645b1de8ffa280672ec4390b2c`
把 exact four-pointer counterfactual 投影为 12 Base、3 positive、56 negative 的
71-record machine inventory。它绑定 69 个 operation、literal constructor/view/
stage-code/precondition/receipt/recipe roots，并以 exact source bytes 和 expected-byte
join 拒绝同形篡改；combined tests 为 `32 passed, 12 subtests passed`。但其每条
record 仍明确携带 unresolved normative leaves，故不是 descriptor registry、
Main、GoldenOracle、materialization evidence 或 P1 count reduction。

后续 external authoring commit `28ce671dcbd86cb5ebf173f64dc1d42a46e01497`
把 56 个 negative records 的未知 judge input 机器化为 ambiguity audit。独立审计
确认 constructor/view materialization 为 `0/12`，operation/reseal/judge/receipt
actual execution 为 `0/56`；audit 只固定 41 structured、3 raw-NDJSON、6 source、
6 process 候选 families、14-cell matrix、5 个 closed facts 和 9 个 blockers。
只有三条 raw-NDJSON
source-selection rules 可唯一识别，但 Base/C1/runtime joins 仍开放；因此 audit
固定 `53` 项 source ambiguity、`final_projection_count=0` 和所有 execution/
materialization/receipt count 为零。Combined tests 为
`47 passed, 16 subtests passed`，两路独立 code review 均为
`P0=P1=P2=P3=0`；该 residual zero 只覆盖 ambiguity-audit 的声明边界。

后续 external authoring commits `d954daad0bb9f52fcdf182b53a2426e0532ed341`
和 `d58ad290b21d340203d3e324a27d3cbceea18d87`
把 12 个 current Base parameter instances 绑定到 exact companion/inventory
bytes、双 order ordinal、canonical parameter roots 和 106-node path-specific
type fingerprints。Audit 明确固定 `exact_instance_count=12`、
`normative_schema_count=0`、constructor/view/Base materialization count 全为零，
并把 environment expansion、suite/pair domain、跨 v0.6/v0.7 label
name/classification、source literal-order-to-sorted-view、process cross-field/
OS-evidence envelope 记录为六项 blockers。Combined tests 为
`61 passed, 31 subtests passed`，独立 code review 为
`P0=P1=P2=P3=0`；该 residual zero 只覆盖 exact-instance audit 的声明边界，不表示
constructor schema、Base payload、G2 或实验完成。Source parameter literal array
与 normalized Unicode-sorted file map 是必须并存的两层；开放项是 exact
array-to-map projection，而不是选择其中一个 order。

后续
[Base schema closure audit](receptor-ligand-field-v0.7-base-schema-closure-audit.md)
确认六类 reusable schemas/projections 均未闭合，并把 T7 labels 从“样本冲突”推进为
provenance 结论：active v0.6 与 v0.7 no-estimand-change 条款唯一支持 intrinsic
为空、两个 positions 均 mandatory；companion 的 split 是 blocking draft defect。
审计只记录 A correction 及 B estimand-changing counterfactual 的 primary companion
root blast radius，没有修改任何 active 或 candidate contract，因此不降低 G2/G3
blocker。

后续 external authoring commits
`6707c028dfec9fae7fdc166788e2dd7b5e56ac21`、
`d6e4d05c0b7db80b802394091de32efc11c929ba` 与
[T7 A1 counterfactual audit](receptor-ligand-field-v0.7-t7-a1-counterfactual-audit.md)
把建议的 preserve-event-34 A1 变成 exact in-memory byte/root evidence。Static
RFC 6901 resolution 证明 source locator index 0 与 A1 locator index 1 都指向
event 34；这不是 operation 或 judge execution。旧 71-record inventory、56-record
negative audit 和 12-record Base audit 均对 A1 source fail closed，且另外两个
T7 disjointness negative relations 仍未覆盖。Machine report 保持 final C1、
amendment、write、activation、provider/network、execution 和 authority 为
false/zero；因此 G2/G3 继续 blocked。

后续 external authoring commit
`f3af7f68ea6724942ceaf1c180b58c2a2017f07d` 与
[six-family constructor resolution matrix audit](receptor-ligand-field-v0.7-constructor-resolution-matrix-audit.md)
把六类 constructor research 整理为 90 条 claims：31 `PROVEN`、13
`DERIVABLE`、45 `OPEN`、1 `CONFLICT`。唯一 conflict 由 exact four-pointer
membership、active v0.6 intrinsic-empty 规则和 draft v0.7 semantic bridge
共同绑定。Audit 同时固定 v0.7 draft、A1 unselected、rule locator/semantic
entailment/schema/projection/execution/observation/authority counts 为零；因此它不把
author-reviewed interpretation 伪称为 normative proof，也不降低 G2/G3 blocker。

再后续 external authoring commit
`ea73fe1add86529884adbf0ece7f6622fe4e3fa9` 与
[environment evidence overlay audit](receptor-ligand-field-v0.7-environment-evidence-overlay-audit.md)
为 environment 的 15/15 rules、20/20 source-ref edges 绑定 26 个 exact
Markdown/RFC 6901/absence-domain locators；global coverage 明确保留为 15/90、
`false`。Overlay 为 55,432 bytes，root 为
`sha256:abb8c6eee795b8dc1076d0f35c5289e615988ba790e813af0e6c2abe5c5b273c`。
它不回写原 63,776-byte audit；machine/normative semantic proof、schema、
projection、execution、materialization、observation、provider 与 outcome 的相关
counts 仍为 0，`network_used=false`、`authority_scope=none`。Strict-integer
relation 明确记为 bound source 不支持 Python `type(value) is int`。

同一红队复核发现八 actor design/promotion SourceFreeze 不包含 runtime producer P
和 independent verifier V。该项作为第 19 个显式 P1 加入；runtime RA/RB 是同一 P
source 的两个 process identities，不能被误写成两个 source-independent actors。

在新 V2 contract 与独立 golden oracle 被内容寻址、绑定到新 phase identity 并从 R0
重跑前，activation
blocker 包括：

1. 先冻结 exact base/positive payload、root-pair registry、RFC 6901 root pointer
   和 byte encoding；
2. 从 12 个 constructors 实际生成 base views；
3. 在 bootstrap candidate 生成前冻结 bootstrap A0/B0、official A1/B1、
   supervisor、fresh reader 与两名 closure reviewers 的八份 source，并封存
   Manifest/SealEvidence；在任一 child 启动前原子封存同时包含 A0/B0 的 launch-intent
   batch；只由 bootstrap pair 生成 golden candidate，只由 official pair 参加后续
   R0-R8；
4. 保存并复算全部 preconditions、observed codes、receipts、source roots 与
   content-addressed artifacts；
5. 完成 R7 closed attack matrix并证明 zero authority、zero outcome read、
   zero network，以及“冻结检测程序未发现禁止共享通道”；不得把该结果表述为不可观测
   历史独立性的证明；
6. 在 runtime-review 前另行冻结 producer P、verifier V、runtime supervisor 和
   runtime fresh reader 的 source manifest，并证明 same-source RA/RB process
   isolation。

该 audit compiler 例外只存在于隔离 candidate commit，永久不得 merge、copy、import
或生成到 future active runtime；它不能执行 140 个 full-scale task states 或 980 个
controller intents，也不能计为 G2 coverage。

在该二审完成以前，禁止把 `activation_ready` 改为 true，禁止 lock migration、
v0.7 runner/reducer 实现或借此宣称 G2 通过。

## 6. G3 客观审计

### 6.1 Sweep budget 是 P0 级 fairness blocker

当前 `tasks._budget` 对 sweep ratios 实际返回的 cap 都为零，且 runner 没有替代的
非零 budget schedule。若直接执行 sweep，所有 arm 会在一个退化的零预算设计上比较，
formal experiment 将无效。必须先冻结每个 task/size/regime 的非零、可复算、跨 arm
一致的 budget mapping 与拒绝规则。

Inactive `receptor-ligand-field-g3-methodological-amendment-v0.1.md` 已拟定 exact
natural/iso/六档 sweep schedule、full pre-cap ranking 和 common reducer；它的
implementation/lock/descriptor controls 仍为 false/null。因此该设计选择消除了“该选
哪种方法”的歧义，但没有消除 active gate blocker。

### 6.2 S/G scale policy 尚不公平

`S` 的冻结图只在 4-agent corpus 上选择；用于 16-agent cell 时，12/16 agents 会被
系统性隔离。`G` 继承相同的 graph/distribution 约束。必须在 G3 amendment 中选择并
冻结以下一种策略：

- 限定 `S/G` 只参与其 graph 有效的 size；
- 或预注册 size-specific graph family，并在 train/dev 上重新冻结；
- 或明确定义可跨 size 外推且对所有 arm 公平的 graph construction。

在此之前，不能把 `S/G` 的 scale 结果当作架构效应。

同一 inactive amendment 选择 N=4/N=16 size-specific qualification，N>=64 只允许
OOD cost mechanics 且 `outcome_qualified=false`。在 exact S/G artifacts、migration
receipts、source lock 和完整 replay materialize 以前，该选择仍不是资格证据。

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

这同时是一个 architecture P0：在当前 authority 下，G3 `P` 的 faithful durable
multistep replay 尚未证明可达。下一步只能先研究一种完全 external、仍使用现有 ABI，
并通过既有 lifecycle/Trace/Conformance/TCK 的忠实路线；如果该路线不能成立，必须
停止当前 G3 `P` 实现并进入另行授权的 versioned core governance。External shim、
scalar substitute 或弱化 replay identity 都不能作为 qualification evidence。

### 6.4 Cost contract 尚未成为 actual ledger

59-field closed schema 的 self-check 已通过，但 natural/iso/sweep 的 per-run actual
ledger 尚未接入。Inactive amendment 已提出 expected slots、attempt/occurrence、
physical ownership、complete membership、allocation conservation、observation profile
和 independent verifier contracts；这些 contracts 尚未 machine-materialize 或执行。
当前实际证据仍缺：

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
- bundle roots、counts、positive receipts 与 trace chain 均经独立重算；
- V2 authoring helper：19 tests、9 subtests、19 unittest 和 Ruff 全部通过；其
  read-only RFC 6901 counterfactual 为 `62093` bytes、
  `sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795`；
  该项不是 profile/companion mutation 或 materialization evidence。
- 四组 V2 authoring helpers 联合验证：61 tests、31 subtests、61 unittest 和
  Ruff 全部通过；Python 3.12、3.13、3.14 各自通过新增的 14 项 Base parameter
  audit tests。该项只证明 exact-instance audit 的声明边界，不证明 normative
  constructor schema 或 materialization。
- 加入 T7 A1 counterfactual 后，五组 V2 authoring helpers 最新联合验证为
  76 tests、49 subtests、76 unittest；Python 3.12、3.13、3.14 各自通过 15 项
  T7 A1 tests，两个新增文件的 targeted Ruff 与 `py_compile` 通过，两路独立
  post-fix review 均为 `P0=P1=P2=P3=0`。Audit 明确
  `event_34_preservation_basis=static-rfc6901-copy-locator-resolution-only`，
  不把静态 locator identity 伪称为执行证据。
- 加入 six-family resolution matrix 后，六组 V2 authoring helpers 联合验证为
  88 tests、64 subtests、88 unittest；Python 3.12、3.13、3.14 各自通过
  12 项 resolution-audit tests，targeted Ruff、`py_compile` 与 `git diff --check`
  通过，三路独立 code/semantic/tamper review 均为 `P0=P1=P2=P3=0`。
  固定 audit 为 63,776 bytes，root 为
  `sha256:c1b3b94ff07221a953c7373f77465f28f0f39df86cb1efd05dd19c4a12557669`；
  locator 与 semantic-entailment proof count 仍为零。
- 加入 environment evidence overlay 后，七组 V2 authoring helpers 联合
  `104` 个 unittest 全部通过；targeted overlay 为
  `16 passed, 35 subtests passed`，Python 3.12、3.13、3.14 各通过 16 项 tests，
  Ruff、`py_compile` 与 `git diff --check` 通过，最终独立 review 为
  `P0=P1=P2=P3=0`。Overlay 固定
  15/15 environment rules、20/20 source-ref edges、26 locators 和 global 15/90
  false；machine/normative proof、schema/projection/execution 的相关 counts 仍为
  0，`network_used=false`、`authority_scope=none`。
- Authoring branch 的 Q exact-rebuild refusal 是 frozen source-root isolation：
  canonical `2f1d473...` 绑定
  `sha256:9e3b1884fce7185e910b1d953c0ab1c1c7e690791e9ced2396429cb410352061`，
  而在 resolution/overlay module 之前的 authoring parent `d6e4d05...` 已是
  `sha256:2a9907610d4ab19d83bb39e26038b3fcc019d90bed3dde09c3f48bc3928b0710`。
  它不是 active Q baseline defect；不得在 authoring branch refreeze artifact
  来掩盖该隔离。同一 test 配对复现为 canonical
  `1 passed in 48.96s`、authoring `1 failed in 49.02s`。

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

1. 先完成 V2 normative contract、positive closure/transition mapping、两项 RFC 6901
   correction、71-record descriptor registry 和独立 golden oracle；冻结 official A/B
   source 时不得向其暴露 oracle；
2. 只有 materialization、source-independence 和全部 root 二审通过后，才形成新的
   activation candidate；profile activation 与 prereg lock migration 仍需单独审阅；
3. 在不含 executable source 的独立 methodology candidate 中 materialize G3 meta
   schema、完整 descriptor set、guarded dependency SCC graph 和
   source-independent qualification receipt；只有 exact review/activation 通过后才
   产生 implementation authority；
4. 在 external lab 的隔离 implementation commit 中实现 v0.7
   producer/verifier/resource-supervisor 与已激活的 G3 contracts；先冻结独立 runtime
   source manifest，令 RA/RB 共享 producer P source 但隔离 process namespace，再重建
   N=4/N=16 S/G artifacts；随后单独审阅 source-lock migration；
5. 在最终 locked source 上依次重跑 G0、G1 和完整 G2：140 个 scale task-state
   replays、980 intents，以及全部 7,252 intents 的隔离 A/B；不得复用旧 source 的
   G2 receipt；
6. G2 aggregate 通过后，用 sealed T1 的 `F` + shared
   generator/common eligibility 作为最小 G3 vertical
   slice，执行 natural、iso 和预注册的 6 个 sweep cells，生成 canonical actual
   ledger 与独立 verifier receipt；
7. 再扩展到 `S/B/Q/G/R`；对 `P` 先完成 external-only faithful replay
   reachability research。若现有 ABI 下不可达，则继续 blocked，并转入另行授权的
   versioned governance，不得用 shim 或 scalar substitute；保留任何 failure、
   null 或 negative result；
8. G0-G3 全部通过以前，不读取 API key，不运行 provider canary、pilot 或
   confirmatory LLM experiment。
