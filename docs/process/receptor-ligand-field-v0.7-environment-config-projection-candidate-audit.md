# Receptor-Gated Ligand Field v0.7 Environment Config Projection Candidate Audit

状态：`research-candidate-internally-closed`；normative closure、actual runtime、
Main、GoldenOracle、G2 和 G3 仍为 `NO-GO`

日期：2026-07-29

## 1. 决定

External authoring branch 已把 environment family 的第一个最小 vertical slice
机器化：

```text
exact six parameters
+ exact two-root sealing context
+ exact review/runtime scope
→ all-and-only 15 ScaleEnvironmentConfigV07 candidate fields
→ H("g2-v07-environment-key-v1", complete config)
```

该实现对七个 review-scope records 和完整 140-record runtime parameter domain
生成 147 个 scoped records、140 个 unique configs 和 140 个 unique
`environment_key`。77 个 candidate conformance cases 已逐项执行并通过；独立审计
重算全部 308 个 content-addressed roots，得到 0 mismatch。

这只关闭一个 source-dependent authoring candidate 的内部歧义，不关闭：

```text
machine_semantic_proof_count = 0
normative_semantic_proof_count = 0
source_independent_implementation_count = 0
constructor_execution_count = 0
base_materialization_count = 0
normalized_view_count = 0
rechain_execution_count = 0
actual_root_count = 0
actual_runtime_execution_count = 0
provider_call_count = 0
authority_scope = "none"
```

因此 E0 不是正式 schema freeze、Base payload、actual runtime evidence、G2 pass 或
实验开始许可。API key 仍不是当前 blocker，也不是开始实验的充分条件。

## 2. External identity

实现位于独立 external research lab：

```text
branch =
  codex/v07-materialization-v2-authoring
initial candidate commit =
  4889971e846ab166c0c79a569ce4b42b26b9ff5a
strict-exactness hardening / final checkpoint =
  2fa2363f4291e6a63e910307280be726024aa4a1
module =
  src/rglf_lab/v2_environment_config_projection_candidate_authoring.py
module_sha256 =
  4b77846fa68bb2840450eb65c3b2384102a9cd7114daeb0d58aa40057cd44a4d
test =
  tests/test_v2_environment_config_projection_candidate_authoring.py
test_sha256 =
  945f7558a02ca0c4f4cf5bd28e15975246acd9c0a08e8afb5cf4d47ee575b4ba
```

该 helper 没有进入 protocol-core executable surface，没有修改 ABI、Governance、
Trace、Conformance、TCK、profile、companion、lock 或 runtime。

## 3. Primary-source boundary

Candidate 绑定四个 exact whole-file byte identities：

```text
v0.7 review profile
  bytes = 119802
  RAW = sha256:bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6
V2 authoring checkpoint
  bytes = 52105
  RAW = sha256:d0f3447d2b6cf0d09ec29aac9522a4ae66d164200f58f883528398b23c9e55c7
V2 closure design
  bytes = 50024
  RAW = sha256:a462140f0a21880b479eb17e8acad0eb4e2349866210f2881de8685f769b21bb
v0.7 fixture companion
  bytes = 62097
  RAW = sha256:322365b8eb50d5479329fde2a734901e8bd96ce48bcfe1afa177588d38788360
```

Source set root：

```text
sha256:9b787606735b643c2a6955bce8ee58e5bca47f4d4b29eb31d1c4890a5d86a8ae
```

这些 anchors 只证明 whole-file byte identity。Artifact 中的 section names 是人工
review labels，不是 machine locator proof，也不是 row-to-source semantic
entailment proof。Candidate 明确保持：

```text
section_locator_proof = false
semantic_proof = false
source_independent_implementation = false
```

状态也被拆成四个不可互换的 leaves：

```text
four_pointer_amendment_policy_selected = true
four_pointer_amendment_applied = false
final_c1_present = false
a1_correction_selected = false
```

因此 v0.7 仍是 draft，当前 companion 仍未被原子 amendment，A1 仍只是
counterfactual recommendation。

## 4. Candidate input contract

### 4.1 Six parameters

输入必须包含 all-and-only：

```text
agent_count
event_count
repeat_id
seed
steps
task_id
```

Domain 为：

```text
task_id in T1..T7
(agent_count,event_count) in
  {(4,100),(16,1000),(64,10000),(256,100000),(1024,100000)}
seed in {9000,9001}
repeat_id in {0,1}
steps = 50
```

五个 integer fields 使用 language-neutral JSON integer 语义并明确排除 boolean。
Agent/event 是五个合法 pairs，不是两个独立集合的任意 cross product。

### 4.2 Two-root sealing context

调用方还必须显式提供 all-and-only：

```text
effective_profile_chain_root
normative_dependency_root
```

两者都只能先按 canonical Root lexical form 验证，没有 default。Candidate 不声称
能从六参数计算 actual roots，也不声称 generic validator 能仅靠 root shape 判断两个
合法 roots 的语义是否交换。

### 4.3 Two scopes

```text
review-seven =
  T1..T7 × A4/N100/S9000/R0/steps50

runtime-140 =
  T1..T7 × five agent/event pairs × two seeds × two repeats × steps50
```

`review-seven` 是 `runtime-140` 的七项 subset。Scope order 只是本 candidate 的
authoring order，不是新 normative order。

## 5. Exact projection candidate

| Destination | Candidate source/transform |
| --- | --- |
| `schema` | literal `pheroos-rglf-scale-environment-config-v0.7` |
| `matrix_kind` | literal `scale` |
| `split` | literal `smoke` |
| `task_id` | `/parameters/task_id` |
| `agent_count` | `/parameters/agent_count` |
| `event_count` | `/parameters/event_count` |
| `steps` | `/parameters/steps` |
| `seed` | `/parameters/seed` |
| `repeat_id` | `/parameters/repeat_id` |
| `severity` | string literal `0.000000000000` |
| `budget_layer` | literal `natural` |
| `fixture_mode` | `false` iff T4, otherwise `null` |
| `directive_schema` | literal `pheroos-rglf-g2-no-op-directive-v1` |
| `effective_profile_chain_root` | explicit sealing-context root |
| `normative_dependency_root` | explicit sealing-context root |

Candidate `environment_key` 是：

```text
H("g2-v07-environment-key-v1", complete 15-field config)
```

这与 profile 第 2 节用
`task_id*agent_count*event_count*seed*repeat_id` 描述的 logical environment axis
不同；后者不能替代第 13.1 节的 cryptographic identity。

Public profile 把 config errors 映射为 `E-CONFIG`，但 exact public reason
precedence 尚未冻结。本 helper 的 `E0-P00..E0-P18` 只能作为 candidate-local
preflight diagnostics，不能冒充 normative/public error codes。

## 6. Content-addressed candidate

Canonical in-memory artifact anchors：

```text
byte_count = 283741
RAW =
  sha256:ef43aeddd52311abe70d97478e063e4d6389a8b97c3ca4525ebc16406ed83200
contract_root =
  sha256:cf0be4b05f6255a26e0eed1a504afd3a615015c4b577eb65d971ad0789e0888a
attack_case_set_root =
  sha256:dcb67a31919a36592c6e818f00df12625d5034a18c4da0f57633e22576900bf5
attack_breakdown_root =
  sha256:afd2613162fd91a24db5e52342e947da29346f04e5580f35b9476b9134d9e063
corpus_root =
  sha256:37b9d8a9f4874e294aadfc7df5a3e4553065b348dcd89cc99a5f791c74b1acaa
```

Corpus 使用两个明确标为 test-only 的 synthetic roots：

```text
effective_profile_chain_root =
  sha256:56d4f61e001b0950dfe8adec2fd3375fc9193bd31e2b57c9c832cead92b41811
normative_dependency_root =
  sha256:54f7807096ce9c7f73bba3dbe00e079583dc13330fa6cc6dd30e3a1d0e02e0af
small_T1_environment_key =
  sha256:ee3da3dec3b35e74f708a69818f5e08569cc33ed0a0dbfa9922df7789f18b5ff
```

它们来自公开 ASCII test preimages，只用于 deterministic replay。它们不是 actual
activation roots、Golden roots、evidence roots 或 promotion inputs。

Corpus counts：

```text
scoped_record_count = 147
review_record_count = 7
runtime_record_count = 140
unique_config_count = 140
unique_environment_key_count = 140
review_runtime_overlap_count = 7
actual_runtime_record_count = 0
```

147 是 scoped projection records，不是 147 次 runtime execution；七个 review
records 与 runtime domain 重叠，所以 unique count 是 140。

## 7. Candidate conformance and attacks

77-case set 是 exact records，不是只写一个 minimum count：

| Family | Count |
| --- | ---: |
| missing parameter key | 6 |
| missing sealing-context key | 2 |
| five integer fields × six invalid runtime kinds | 30 |
| invalid task runtime kinds | 4 |
| complete 5 × 4 agent/event cross product | 20 |
| mutated output literals | 6 |
| T4/non-T4 `fixture_mode` mutations | 2 |
| recursive JSON type-confusion mutations | 3 |
| object-key type-confusion mutations | 2 |
| input-object-key type-confusion mutations | 2 |
| **Total** | **77** |

其中 agent/event cross product 含五个合法 positive controls；其余 15 个 pair
组合和其他 57 个 mutations 必须拒绝：

```text
accepted_control_case_count = 5
rejected_mutation_case_count = 72
executed_candidate_attack_case_count = 77
passed_candidate_attack_case_count = 77
actual_runtime_attack_case_count = 0
```

新增三条 exact cases 分别要求 nested `false→0`、nested `4→4.0` 和 top-level
`false→0` 被拒绝。Artifact 只保存 `invalid_kind`，不把 float 写入 canonical JSON。
Result validator 使用递归 type-aware equality，而不是 Python 会把
`False == 0`、`4 == 4.0` 判为真的普通 equality。

另外两条 cases 把 observed result 的 top-level 与 nested config key 换成
hash/equality 相同的 `str` subclass。Validator 要求 observed 和 expected 两侧的
所有 object keys 都是 exact `str`，因此这些非 canonical-JSON keys 也必须拒绝。

最后两条 cases 对 parameter `agent_count` 与 sealing-context
`effective_profile_chain_root` 做同类 key substitution，并分别保持 P01/P03
fail-closed reason。Primary-source Mapping 也由单独 regression 拒绝 `str` subclass
及 arbitrary hash/equality-equivalent source IDs；它不被伪计入 77 条 projection
cases。

额外 tamper tests 包括：

- child、set、corpus 与 top-root corruption；
- canonical byte、duplicate-key、row order/source/drop/duplicate/addition/collision；
- key-label、source pointer、negative-vector ID 和 source-anchor mutation；
- 把两个 synthetic roots、preimages、147 configs、147 environment keys、
  record roots、unique sets、overlap、corpus、independent literals 和 top root
  全部协同重算后的 full collective reroot；
- provider count、Golden eligibility、profile activation 和 global authority
  的 collective mutation。

所有这些都在 frozen candidate exact validator 上 fail closed。这里证明的是 exact
candidate identity 对协同重根的拒绝，不是 generic root semantics 能识别任意
two-root swap。

## 8. Verification

Root agent 独立执行：

```text
targeted E0 =
  31 passed, 256 subtests passed
all V2 authoring-pattern =
  233 passed, 646 subtests passed
Ruff = pass
mypy(module) = pass
mypy(test, follow-imports=skip) = pass
compileall = pass
88-column scan = pass
git diff --check = pass
```

第二路只读 red-team 使用独立 canonical JSON/SHA 路径重算 308 个 child、set、
corpus 和 top roots，得到 `0 mismatch`；稳定版本审计结果为：

```text
P0 = 0
P1 = 0
P2 = 0
```

该 residual zero 仅表示没有在本 candidate 的声明边界内发现未解决缺陷。它不把
source-dependent implementation 变成 independent oracle，也不表示完整 external
test discovery green；此前 full discovery 的 source/prereg isolation refusal
仍按原记录保留。

## 9. Gate interpretation

| Claim | 结论 |
| --- | --- |
| 四个 source files byte-exact joined | 是；仅 whole-file identity |
| exact candidate parameter/context/scope rules | 是 |
| 15-row candidate projection | 是；source-dependent |
| 7/140 synthetic candidate corpus | 是 |
| row-to-source semantic entailment | 未证明 |
| source-independent implementation equality | 未证明 |
| normative schema/projection/error precedence | 未冻结 |
| actual sealing roots or runtime observations | 0 |
| Base/nested view/re-chain | 0 |
| final C1 or applied amendment | 无 |
| Main/GoldenOracle eligibility | false |
| G2/G3 | blocked |
| provider configuration | unauthorized |
| H1-H6 or RG-LF superiority | 无结论 |

因此原 Base schema closure audit 的环境结论应按时间解释为：

1. 当时没有 machine projection；
2. 现在有一个 exact、可重放、source-dependent candidate；
3. reusable normative closure 与 actual execution 仍未完成。

## 10. 下一顺序

后续仍只允许 provider-free research：

1. 用 distinct implementation/source tree 独立重建同一 E0 mapping，并比较完整
   bytes、rows、errors、corpus 与 roots；不能从本 helper import 或复制 literals；
2. 把 row-to-source entailment、JSON type semantics、public `E-CONFIG` precedence
   和 two-root semantic binding 变成可审阅的 normative leaves；
3. 原子选择并应用 four-pointer/A1 amendment，形成 final C1 后重算全部 source
   identity；
4. 取得 actual sealing context，再把 environment projection 接入六类 Base、
   normalized view、actual-chain preservation/re-chain 和 independent verifier；
5. 完成 Main 与 GoldenOracle 分层、R0-R8、G2/G3 和 source-lock migration；
6. 只有 G0-G3 全部通过后，才允许 provider canary、pilot 或 confirmatory LLM
   experiment。

## 11. Claim boundary

本审计支持的最强结论是：

> Environment config 的一个精确定义、可内容寻址、可攻击重放的 E0 候选已经实现，
> 其内部一致性通过独立复核；它仍只是理论和工程动机较强的候选构造，不是规范或实验
> 结论。

它不证明 receptor-gated ligand field 优于 sparse communication、blackboard、
retrieval routing、learned graph pruning 或任何其他 baseline。H1-H5 仍是可证伪
假设，H6 仍是系统级 claim gate。
