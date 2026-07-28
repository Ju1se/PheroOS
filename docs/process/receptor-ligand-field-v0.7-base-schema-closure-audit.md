# Receptor-Gated Ligand Field v0.7 Base Schema Closure Audit

状态：`research-only-no-go`；不构成 profile amendment、schema freeze、materialization
或实验许可

日期：2026-07-29

## 1. 决定

现有证据可以精确绑定 companion 中 12 个 current Base parameter instances，但不能
唯一推出六类 reusable constructor schemas 或完整 normalized-view projections：

```text
exact_instance_count = 12
normative_schema_count = 0
constructor_execution_count = 0
normalized_view_count = 0
base_materialization_count = 0
authority_scope = "none"
G2 = "blocked"
G3 = "blocked"
G4_G8_authorized = false
```

因此 API key 不是当前 blocker，也不是开始实验的充分条件。该审计不修改 v0.6、
v0.7、fixture companion、external lock、ABI、Governance、Evidence、TCK 或 runtime。

## 2. 证据边界

本审计消费：

- active v0.6 attack-label firewall；
- v0.7 review draft 与 12/3/56 fixture companion；
- v0.7 materialization plan；
- V1 executable NO-GO；
- V2 closure design；
- V2 four-pointer counterfactual、71-record inventory、56-record negative
  projection audit 和 12-record Base exact-instance audit。

External authoring branch 的最终相关 commits：

```text
d954daad0bb9f52fcdf182b53a2426e0532ed341
d58ad290b21d340203d3e324a27d3cbceea18d87
6707c028dfec9fae7fdc166788e2dd7b5e56ac21
d6e4d05c0b7db80b802394091de32efc11c929ba
```

12-record audit 仍绑定 106 个 path-specific parameter nodes、六项 blockers 和零
authority。Source-projection clarification 后：

```text
audit_byte_count = 25551
audit_raw_root =
  sha256:1612f3636a21a7689025cb8a1939fdfc86b119fada11537151485f787da21469
record_set_root =
  sha256:b79644c975496a7e9ca88bc19722f4f5b696cf5a402fcf5f687969db51854113
blocker_set_root =
  sha256:48e2dd6160dab7a884e9fd88e410cbfef32132d63b9ae78fd4eccc4617407979
audit_root =
  sha256:3e8e6df93b99d5b714f6dc80ed5e2c1fe955e3473dd926d97b9278c4f8e7b9c3
```

这些是 authoring audit roots，不是 Main contract、GoldenOracle 或 acceptance roots。

## 3. 六类 closure matrix

| Family | Current exact fact | Declared downstream intent | 未闭合项 |
| --- | --- | --- | --- |
| environment | 七个六参数对象；均为 A4/N100/S9000/R0/steps50，task T1-T7 | 140-environment scale domain 与 15-field `ScaleEnvironmentConfigV07` | reusable input schema、六参数到 15 fields 的 exact projection、activation-root context、7-review/140-runtime 分相、完整 Base view |
| suite | `{producer_replica:"A"}` | 一个 replica 的 140 environments、每环境七 arms、980 intent bindings | replica domain、980 payload membership/order/root、source join、outer view schema |
| replica pair | directional `{A,B}` sample | fresh A/B 对同一 140/980 logical inventory byte-exact | reusable name domain、ordered/symmetric rule、materializer-vs-runtime replica namespace、copy/reference/re-chain semantics |
| labels | active protocol 要求 T7 intrinsic 为空、两个 positions 均 mandatory；companion current literals 却把两者拆为 intrinsic/mandatory | variable/intrinsic/mandatory 三分法和 T7 public mechanics | versioned A correction；若提出 B，须显式 supersede no-estimand-change 条款；相应 negative coverage |
| source | declaration-order seven-file array | normalized exact file map 与 Unicode-sorted path order | exact array-to-map transform、file value schema、duplicate/NFC/path policy、trace；与 actual Git source evidence 的 join |
| process | 13-field synthetic success transcript | normalized process view 与 resource-stage mutations | reusable types/ranges/nullability、base64/frame/count/clock/exit/RSS cross-fields、measurement root、OS evidence envelope |

Current sample 的 keys、types、ASCII/NFC、base64 或数值特征只能记录为 observed
instance facts；不能据一个样本推导 generic acceptance rules。

## 4. Environment：声明域不等于 constructor contract

v0.7 唯一声明的 full-scale domain 是：

```text
task_id in T1..T7
(agent_count,event_count) in
  {(4,100),(16,1000),(64,10000),(256,100000),(1024,100000)}
seed in {9000,9001}
repeat_id in {0,1}
steps = 50
```

总计 `7 × 5 × 2 × 2 = 140` environments。`event_count=100000` 对应两个 agent
counts，不能实现为 event-count-to-agent-count 单值 map。第 13.1 节的 `Task` alias
排除 T4，但 `ScaleEnvironmentConfigV07.task_id` 明确包含 T4；validator 不能复用该
alias。

输出 config 的 15-field set、13 个 non-root fields 的 literal/domain/conditional
rules，以及两个 Root-typed slots 在 prose 中可读，包括 string severity
`"0.000000000000"`、T4 `fixture_mode=false`/其他 task 为 null。两个 roots 的 concrete
values 尚未冻结。当前也没有 machine leaf 规定每个 destination field 是 parameter
copy、contract literal、conditional derivation 还是 sealing-context binding，也没有
分开七个 review-only Base instances/views 与 140 个 runtime configs。

`effective_profile_chain_root` 只依赖 frozen v0.5/v0.6 hashes 与 final v0.7 blob hash。
`normative_dependency_root` 依赖八个 dependency records，包括 final v0.7 hash、
corrected companion hash 与 activation-candidate Git blob IDs。Activation commit 和
external lock 保存并证明这些值；lock migration 本身不进入任一 root preimage。两者
都不能从六参数对象计算，也不能作为隐式 default 塞入 parameters。

## 5. T7 label：active protocol 支持 A，companion 当前冲突

冲突在同一个 v0.7 初始 commit 中出现，提交先后本身不能裁决：

- v0.6 使用 `intrinsic_challenge_event_ids`，并声明 T7 intrinsic universe 为空、
  mandatory probes 使用独立集合；
- v0.7 声明不改变既有 estimand，且 v0.6 三分法继续有效；
- v0.7 public mechanics 把 positions
  `{floor(event_count/3), floor(event_count/3)+1}` 同称 `mandatory_positions`，并说
  sidecar intrinsic identities 只按 v0.6 生成；
- companion 却使用 `task_intrinsic_challenge_event_ids=[...00033]`、
  `mandatory_probe_event_ids=[...00034]`。

适用 active-contract provenance 后，当前 protocol 唯一支持：

- A：T7 intrinsic 为空，positions 33/34 都是 mandatory。

companion 中的 B（position 33 是 task-intrinsic，position 34 是 mandatory）是
blocking draft defect，不是当前等权的 protocol choice。若科研团队希望提出 B，必须用
新版本 amendment 显式声明 estimand change，并 supersede v0.6/v0.7 的 no-change
clauses。两者不是纯命名差异：按 v0.6，B 会使全部 T7 cells 的
`episode_attack_free=false`，影响 matrix intent、counterfactual strata 和后续
G2/G5/G6 estimand。本审计不修改 companion；在 A correction 原子版本化前，Base
schema closure 仍为 NO-GO。

### 5.1 Four-pointer counterfactual root blast radius

下表从已审但未激活的 four-pointer counterfactual source 起算；均是 in-memory
authoring alternatives，不是 final C1。表中的 locator index 专指
`operations[0].value.path`；mutation target `operations[0].path` 始终是
`/variable_attack_event_ids/0`：

| Alternative | Bytes / raw root | Fixture-input root | Negative root | Semantic root |
| --- | --- | --- | --- | --- |
| B / four-pointer-corrected companion | 62093 / `sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795` | `sha256:0227f38c34f9d50b81b257675065e73ab1c18e02fff684ca851603b3d963aed8` | `sha256:5c4cf71f6985766af2ab30735900403ef2dfeee57e674b0a2abbd342590c785e` | `sha256:eccec79803913d858ebc60b4c78ae8854a606102fffec7e681ae29c6d87a3bf2` |
| A0 / protocol correction, locator index 0 | 62094 / `sha256:1c5fa79a5857423c31f93fa2599929744075d0b6596e5aa3896c9867eba39083` | `sha256:6cce58e91e662c282def133b6c53962a67b5b400d24e7bac1aac7e6cbe58c6b1` | `sha256:5c4cf71f6985766af2ab30735900403ef2dfeee57e674b0a2abbd342590c785e` | `sha256:4cd2d2cc7a3a17412c376d300458bbc76a91344bdf8676a0c697316d07cec5d2` |
| A1 / protocol correction, preserve event 34 at locator index 1 | 62094 / `sha256:3929670021f447c6f3c4f325be2db46f89809468a72428b57374bb93e80c035b` | `sha256:6cce58e91e662c282def133b6c53962a67b5b400d24e7bac1aac7e6cbe58c6b1` | `sha256:29b142086ae04c989390e0c0aa6cbccd315be9c5ad0f6600c2f1ce611553da1e` | `sha256:7aaaaceba005b5a35946cc65d011311bb9b35d251a639aec5d201916131c51b9` |

三者的 positive root 都保持
`sha256:2a0e9ff10b6e2d5e2e42bebe77dd9c32f871a48638ad4d41a796995d1ce1613e`，
negative recipe count 都保持 56。

A0/A1 都把 intrinsic array 设为空，并把 mandatory array 设为
`[...00033,...00034]`。A0 不改 `N-T7-PROBE-AS-ATTACK` 的 copy locator，却会把其测试
目标从 event 34 静默改成 event 33。A1 把 locator 改为 index 1，保留 event 34，因而
negative root 变化。B 至少缺少两个独立 negative fixtures：
intrinsic-to-variable 和 intrinsic-to-mandatory；现有 fixture 只覆盖
mandatory-to-variable。因此三行的 56-count 都不是 negative-plan completeness 证明。

### 5.2 版本化纠正程序

当前分类必须采用 A，而不能由代码作者或单个 sample 暗选 B。纠正应原子规定三组
membership、position formula、public mechanics、field-name migration、v0.6
precedence、negative coverage 和全部受影响 roots。为避免在保持 recipe bytes 时静默
改变被测 event，本审计建议 A1；这只是 research recommendation，不授予 amendment、
materialization 或 activation authority。

如果科研团队仍要评估 B，必须先以新的操作性判据明确把 same-subject collision 定义为
跨 severity 固定的 task difficulty，而不是当前 protocol 中的 safety/ACL mandatory
probe。两名独立审阅者必须从该新判据对全部 20 个 T7 scale configs 得到相同分类；
随后用 estimand-changing amendment 显式 supersede 当前规则，不能 in-place 修补
companion。

### 5.3 A1 counterfactual machine audit

后续
[T7 A1 counterfactual audit](receptor-ligand-field-v0.7-t7-a1-counterfactual-audit.md)
在 external authoring commits
`6707c028dfec9fae7fdc166788e2dd7b5e56ac21` 与
`d6e4d05c0b7db80b802394091de32efc11c929ba` 中把建议 A1 实现为 exact
in-memory byte counterfactual 并补齐 downstream byte-first evidence。它证明：

- source 必须是 62093-byte four-pointer bytes；
- A1 恰好改变三个 substantive leaves 与三个派生 roots；
- RFC 6901 locator 从 mandatory index 0 移到 index 1 后，前后均解析为
  `event:t7:9000:0:00034`；
- 旧 71-record inventory、56-record negative audit 和 12-record Base audit
  均对 A1 source fail closed，必须重建；
- 当前 negative plan 仍只覆盖 mandatory-to-variable，另外两个 disjointness
  relations 未覆盖。

其 audit 固定为 6744 bytes、raw root
`sha256:b6736881bf1f996d261f3012b1eb902259d2ef870185b870eda219b414fdba92`、
audit root
`sha256:d6edfe1f1f9dd2b193b4d1b7b8802d6c5e8c0564731dca80f2df012aa0624b1a`。
Combined V2 authoring verification 为 76 tests、49 subtests；两路独立 post-fix
review 均为 `P0=P1=P2=P3=0`。

该结果只关闭 A1 impact-calculation 的局部不确定性。其 machine leaves 仍固定
`final_c1_selected=false`、所有 execution/projection counts 为零、
`authority_scope="none"`；本审计的六类 schema closure NO-GO 不变。

## 6. Source 和 process 的双层边界

Source 不存在 literal-order 与 sorted-order 二选一：

```text
constructor_parameters:
  exact companion declaration-order files array

normalized_source_view:
  separately projected exact file map
  + Unicode-sorted path order
```

开放的是 exact array-to-map mapping、map value 是否重复 path、duplicate/NFC collision、
ordering encoding 和 construction trace。Current seven snippets 的 git mode、ASCII/NFC、
terminal LF 或 AST parse 不能变成 generic source limits。实际 source audit 还需要
commit/blob/raw/count/role、detached worktree 和 loaded-code identity；Base fixture
不能替代。

Process 同样分成 synthetic mutation preimage 与 actual evidence：

```text
Base process parameters:
  exact 13 current literals

runtime evidence:
  READY frame + supervisor samples + monotonic clock
  + child rusage + wait4 + pipe/temp/fsync
  + attempt/environment/role/source/process identity
```

`Cg==` strict-decodes 为一个 LF、current counts 为 1/1/1、current RSS 可映射为
1/2/1 MiB，这些都只是 current facts。它们不证明 generic base64、frame/count、
clock/exit/RSS cross-fields，也不是 OS-observed receipt。

## 7. Root blast radius 与下一顺序

任何正式 schema/projection 选择都会传播：

```text
constructor leaf
→ MaterializationContractV2 component/root
→ profile/companion atomic amendment
→ V07_SHA256 and dependency/profile-chain roots
→ constructor preimages + normalized views + path inventories + Base bytes
→ every dependent positive/negative materialization, judge-input projection and root
  (mechanically recompute the affected set; current inventory: environment references
   3/3 positive and 40/56 negative records; all six families cover 56/56 negatives)
→ GoldenOracle + Identity + R0-R8 evidence
→ G2/G3 requalification
```

后续仍只允许 provider-free research：

1. 原子版本化 T7 的 A correction；若另提 B，先走 estimand-changing amendment；
2. 分别冻结六类 exact parameter schemas、projection tables、error precedence 和
   construction traces；
3. 为 environment 明确 sealing context 和 exact-7/140 scope；
4. 为 source/process 保持 parameter/view/evidence 分层；
5. 独立生成并复核 Main leaves，之后才生成 oracle；
6. 原子形成新的 profile/companion candidate；重新执行 source freeze 与 R0-R8；
7. G2/G3 全部通过后才允许 provider canary、pilot 或 LLM experiment。

## 8. Claim boundary

本审计证明的是：

- current 12 parameter instances 可精确复核；
- 六类 reusable schemas/projections 尚未闭合；
- T7 companion 与 active protocol 冲突；provenance 支持 A，而 B 会改变 estimand
  和 roots；
- source parameters/view、process fixture/evidence 必须分层。

本审计不证明：

- 任一 normative schema 已冻结；
- 任一 constructor/view 已执行；
- G2/G3 已通过；
- API key 可以解除 gate；
- provider/LLM behavior；
- H1-H6 或 RG-LF 相对任何 baseline 的优势。

科研结论保持：RG-LF 是理论动机较强、可证伪的候选架构；comparative superiority
仍未证明。
