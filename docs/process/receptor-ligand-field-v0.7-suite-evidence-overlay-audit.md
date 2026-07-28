# Receptor-Gated Ligand Field v0.7 Suite Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点在不修改 environment sidecar 和 frozen six-family resolution audit 的前提下，
新增一个独立的 `suite` evidence overlay。它只回答：

- frozen suite rules 的 exact source evidence 在哪里；
- 哪些文本可作为 direct premise；
- 哪些文本只能作为 semantic context；
- 哪些 absence 仍只是 author review；
- 哪些旧命题包含 bound source 无法推出的作者合成。

原 resolution artifact 保持：

```text
bytes = 63776
RAW =
  sha256:448be7156c0640c46c6f83f6efe2b5568acbb4663b75d3107e85b344f63def3d
audit_root =
  sha256:c1b3b94ff07221a953c7373f77465f28f0f39df86cb1efd05dd19c4a12557669
rule_source_locator_count = 0
semantic_entailment_proof_count = 0
```

Suite sidecar 的 scoped coverage 是：

```text
family = suite
family rules = 15 / 15
source-ref edges = 22 / 22
locators = 25
global rules covered = 15 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

Environment 和 suite 是两个独立 artifact。现在可以做 `15 + 15 = 30` 的研究进度
算术，但尚无 overlay-set artifact 证明 disjoint union，因此任何单体 artifact 都不能
声称 `30/90` 或 global coverage complete。

## 2. Classification 与 evidence roles

Frozen target statuses 没有被 sidecar 改写：

| Target status | Count | Review relation |
| --- | ---: | --- |
| `PROVEN` | 5 | `direct-support` |
| `DERIVABLE` | 1 | `conditional-derivation-review` |
| `OPEN` | 9 | `closure-insufficiency-review` |
| `CONFLICT` | 0 | `conflict-witness` |

`PROVEN` 仍只是旧 author-reviewed matrix 的 status 名称。Overlay 固定：

```text
author_reviewed_semantic_record_count = 15
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

25 个 locator 的 roles 是：

| Role | Count | 含义 |
| --- | ---: | --- |
| `premise` | 7 | 文本直接支持被严格限定的 review 命题 |
| `integrity-context` | 1 | 只绑定 counterfactual 状态，不证明参数语义 |
| `semantic-context` | 14 | 提供解释上下文，但不能升级 semantic proof |
| `absence-domain` | 3 | whole-source 人工缺失审查域，不是机器 absence proof |

25 个 locator 只覆盖 22 个 edges，因为 `SUITE-PROJECT-INTENT-ID` 在 v0.7 profile
和 V2 source 两个 edge 上都同时绑定 targeted context 与 whole-source absence
domain；`SUITE-OPEN-ARM-ORDER-EVIDENCE` 在同一个 v0.7 edge 上分别绑定 arm 列表
context 和“canonical order 继承 v0.5”的 premise。

## 3. 四条 source-unsupported target propositions

Sidecar 明确记录 4 条 frozen target proposition 含有 bound source 不能推出的内容：

| Rule | Source-unsupported synthesis |
| --- | --- |
| `SUITE-PROJECT-ORDINAL` | `environment_ordinal * 7 + arm_ordinal` 行优先约定 |
| `SUITE-ERROR-ID-AND-REPLICA` | `E-FIXTURE-PRECONDITION` 与 total precedence |
| `SUITE-TRACE-CANDIDATE` | literal suite construction step sequence |
| `SUITE-OPEN-STORAGE-SHAPE` | 三个具体 storage alternative 的枚举 |

对应 verdict 都以 `-by-bound-source` 结尾，且
`unsupported_bound_source_count=4` 由 exact verdict set 机械重算，不能自由填写。

### 3.1 Ordinal 反过度结论

Profile 明确给出 `140 * 7 = 980`，但没有：

```text
environment_ordinal
arm_ordinal
row-major enumeration rule
environment_ordinal * 7 + arm_ordinal
```

给定两个 order 也不能唯一推出 nested-loop orientation。该 rule 保留 frozen
`DERIVABLE` status 仅为了不篡改旧 audit，同时 sidecar 固定：

```text
relation = conditional-derivation-review
locator role = semantic-context
derivation_ast = null
replay_performed = false
schema_closure_sufficient = false
resolution_selected = false
machine_semantic_entailment = false
normative_effect = false
```

因此 row-major formula 仍是待显式规范的候选约定，不是实验或机器结论。

### 3.2 Arm order 边界

两个 exact v0.7 locators 分别证明：

1. `[967,1046)` 出现 `F/P/S/B/Q/G/R` slash list，但该句只说 v0.7 amendment
   不改变 arm 定义、预算层、输入或比较关系；
2. `[80702,80960)` 说 intent-binding set 使用“v0.5 canonical intent order”。

这两段没有组成 v0.7 normative order table，且 exact v0.5 bytes 不在 seven-source
corpus 中。所以 `SUITE-OPEN-ARM-ORDER-EVIDENCE` 必须保持 OPEN。

## 4. 仍开放的 suite closure

当前 evidence 可以严格支持：

- unselected A1 counterfactual 的 current parameter 是
  `{"producer_replica":"A"}`；
- declared geometry 是 140 environments × 7 arms = 980 bindings；
- intent-binding payload 要求 zero execution 和 zero authority fields；
- ReviewAuditCompilerV1 只可构造 declaration inventory，不能代替 runtime-140；
- coverage failure 先于 guarded sequence predicate。

它不能关闭：

- reusable replica domain 与 producer replica namespace；
- `intent_id` preimage、collision rule 与 stable-ID inventory；
- producer replica 是 semantic payload 还是 construction metadata；
- exact storage shape、all-field projection 与 root formula；
- runtime-140 environment construction、join 和 sealing context；
- literal construction trace；
- suite-specific constructor preflight codes 与 total precedence；
- exact v0.5 arm order evidence。

尤其是 7 个 review environment Base views 不能充当 140 个 runtime environments，
declared `980` 也不能充当 980 个已 materialize records。

## 5. Exact anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = 5a9f9f8500aeafb8655692adcb3610bf99cc7e69

common engine SHA-256 =
  bfe192a31788ff4509e2558c42ede5181494583289f88492e0c82526b2c76215
common tests SHA-256 =
  5160bbdbc0f49011780ee76737111c7e31a15247380f0e66b6ef599c533c10c4
suite module SHA-256 =
  f4423daee4acb84c2422c56b8e5f9782e6729edf8ee951e2e7ef26434265fed1
suite tests SHA-256 =
  3ebd38c8be466577e8242ae26c02f2975c82c3509f2b957e50e2a50485f349fb
```

本次最终 suite overlay anchors 是：

```text
bytes = 54745
RAW =
  sha256:4c7c23cecc2c1c02512ecdfbb816f6b93d3db91411afe2da9e77ef4d341df7b0
overlay_root =
  sha256:792829d3cf1fd4989f7d7f5f3b00aecc61b8ce030f1e8934e3f32f888c0f693b
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:45ef83cf98fd07cf7aff8b4de71fd383442a1b36a48acb0caec2d596b7748307
classification_review_set_root =
  sha256:9ceed149d924a24d9fd40d40991b8a5d7bd11f05fd396894b40ed8a4248c97da
unresolved_set_root =
  sha256:10f021a1e6b800debb44febdd4e917c7cbb503e88382b0cdef564c75af2c0007
```

`unresolved_set_root` 不写入 frozen overlay schema；它属于 fixed definition/report
policy anchor。这样 exact artifact bytes 保持 family-overlay schema compatible，同时
防止只替换 report blocker list 后仍自称 anchors validated。

## 6. Zero boundary

Common engine 对所有 family 硬编码：

```text
normative_schema_count = 0
normative_projection_count = 0
constructor_execution_count = 0
normalized_view_count = 0
base_materialization_count = 0
actual_observation_count = 0
provider_call_count = 0
outcome_read_count = 0
network_used = false
authority_scope = "none"
main_contract_eligible = false
golden_oracle_eligible = false
materialization_authorized = false
```

Common engine 不导入 resolution producer，也不读 filesystem、environment、API key、
provider、network 或 outcome。Family-specific public wrapper 固定 suite definition；
artifact 不能自选 family/spec。

## 7. Verification

Provider-free verification：

```text
suite tests:
  10 / 10 passed

common + suite:
  17 / 17 passed

environment + common + suite:
  33 / 33 passed

nine V2 authoring modules:
  121 / 121 passed

Python 3.12 / 3.13 / 3.14:
  17 / 17 per interpreter

py_compile:
  passed

88-column scan:
  passed

git diff --check:
  passed

independent locator recomputation:
  25 locators / 22 exact source-ref edges

independent code, semantic and tamper re-review:
  P0=P1=P2=P3=0
```

Exact authoring-branch full discovery 也被保留为负结果，而不是改写成
green suite：

```text
command = PYTHONPATH=src python3 -m unittest discover -s tests -q
commit = 5a9f9f8500aeafb8655692adcb3610bf99cc7e69
tests run = 383
elapsed = 1885.990 s
failures = 1
errors = 1
```

两项都来自 canonical freeze/boundary gates 对 authoring worktree 的预期拒绝：

- `test_builders_replay_frozen_canonical_artifacts` 的 Q rebuild 仅在
  `preregistration.external_source_tree_root` 及其派生 `artifact_root` 不同。
  Frozen canonical source root 是
  `sha256:9e3b1884fce7185e910b1d953c0ab1c1c7e690791e9ced2396429cb410352061`；
  authoring source root 是
  `sha256:e116a67a319424f18ef6825c7d70c93867161c066df1bcccd8fa7488e5eb6f78`。
  在 canonical `2f1d473a6edb9fba61ccfa39d7214b0d688e44d7` worktree 中，Q
  builder 与 frozen Q exact-equal。
- `test_preregistration_lock_and_core_boundary` 观察到的 external branch 是
  `codex/v07-materialization-v2-authoring`，而 frozen gate 只接受
  `codex/receptor-ligand-field-lab`；运行时 core docs 也尚未提交，所以
  `core_worktree_clean=false`。

因此不能宣称 authoring branch 的 full discovery 通过；也不能把这两项
source/branch identity refusal 归因于 suite overlay 语义回归。新 slice 的可归因
验证范围仍是上述 17/17 focused tests、121/121 V2 authoring tests 与独立终审。

Environment overlay 保持 byte-identical：

```text
bytes = 55432
module SHA-256 =
  8cabf1129f422d5b35bb52947807685114489f4bb2a2558e57e2c90493a97757
test SHA-256 =
  2a351a81fc3d35f6f5f165da2b9e52d51161c00c3c9b6470f3b68be86fd57f47
```

## 8. 科研含义与下一步

这一步强化了“假设”和“已证结论”的区分。Suite evidence sidecar 不证明：

- receptor-gated ligand field 优于稀疏通信、黑板、检索路由或学习式图剪枝；
- 980 intent bodies 已存在或可唯一构造；
- G2/G3、Main、GoldenOracle 或 R0-R8 已通过；
- 可以读取或配置 LLM API key。

当前科研表述仍应是：

> receptor-gated ligand field 是理论动机较强、H1-H5 可证伪的候选架构；现有
> evidence 尚不足以形成 comparative superiority 结论。

下一步仍是 provider-free：为 replica-pair、labels、source、process 分别建立独立
scoped overlay，并先关闭它们自己的 source-unsupported propositions。六类 evidence
定位完成后，仍需单独新增 normative schema/projection；不能把 evidence overlay
升级为 constructor 实现。
