# Receptor-Gated Ligand Field v0.7 Labels Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点在不修改 frozen six-family resolution audit、environment、suite 或
replica-pair sidecar 的前提下，新增一个独立的 `labels` evidence overlay。它只回答：

- 16 条 frozen labels rules 的 exact source evidence 在哪里；
- 哪些 source bytes 是 premise、integrity context 或 semantic context；
- 哪些 whole-source 检查只是人工 absence-review domain；
- 唯一 frozen conflict 的两个直接 witness 与未选择的 names bridge 分别是什么；
- 哪些 target propositions 含有 bound sources 无法推出的作者合成；
- 哪些 blocker 在 schema、projection、execution 或正式 amendment 前必须保持开放。

原 63,776-byte resolution artifact 保持不变，其中
`rule_source_locator_count=0`、`semantic_entailment_proof_count=0`。新 sidecar 的
scoped coverage 是：

```text
family = labels
family rules = 16 / 16
source-ref edges = 34 / 34
locators = 46
global rules covered = 16 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

Environment、suite、replica-pair 和 labels 是四个独立 artifact。当前不存在绑定其
有序、无重叠、同源 union 的 overlay-set artifact。因此不得发布 combined numerator、
coverage fraction，或把任一单体的 `global_rule_coverage_complete` 提升为 `true`。

## 2. Classification、selectors 与 evidence roles

Sidecar 不改写 frozen target statuses：

| Target status | Count | Review relation |
| --- | ---: | --- |
| `PROVEN` | 5 | `direct-support` |
| `DERIVABLE` | 3 | `conditional-derivation-review` |
| `OPEN` | 7 | `closure-insufficiency-review` |
| `CONFLICT` | 1 | `conflict-witness` |

这里的 `PROVEN` 仍只是旧 author-reviewed matrix 的 status 名称。Overlay 固定：

```text
author_reviewed_semantic_record_count = 16
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

46 个 locators 的 selector 分布是：

| Selector | Count |
| --- | ---: |
| exact Markdown span | 20 |
| RFC 6901 JSON pointer | 24 |
| whole-source absence-review domain | 2 |

Evidence-role 分布是：

| Role | Count | 边界 |
| --- | ---: | --- |
| `premise` | 28 | 只支持被严格限定的 review 命题 |
| `integrity-context` | 6 | 只绑定 counterfactual/integrity 状态 |
| `semantic-context` | 10 | 提供语义上下文，不升级为 entailment proof |
| `absence-domain` | 2 | 人工检查的完整 source domain，不是机器 absence proof |

Source locator 分布为：active v0.6 `5`、draft v0.7 `10`、V2 closure design `7`、
four-pointer counterfactual `1`、unselected A1 `9`、A1 correction audit `14`；
materialization plan 为 `0`。

每个 locator 都绑定 target rule、source ordinal、source bytes/root、selector 和
evidence role。每个 review 另外固定 target rule root、status、typed proposition、
blockers、ordered premise bindings 和 verdict。合法形状但错误的 role、target、
verdict、blocker 或 locator/review 集体重根都会 fail closed。

## 3. 唯一 conflict 保持未解决

`LABEL-PARAM-FOUR-POINTER-MEMBERSHIP-CONFLICT` 的四个 locators 是：

```text
exact four-pointer event-33 membership = premise
active v0.6 T7 intrinsic-empty rule = premise
draft v0.7 no-estimand statement = semantic-context
draft v0.7 T7 bridge = semantic-context
```

它保持：

```text
target_status = CONFLICT
relation = conflict-witness
derivation_ast = null
replay_performed = false
resolution_selected = false
normative_effect = false
authority_scope = "none"
```

两条 premise 指向的 source facts 都真实存在；frozen author-reviewed target 在假定
field-name bridge 后将它们记为 conflict。但是 v0.7 的两个 spans 只提供语义上下文，
没有正式选择 `intrinsic_challenge_event_ids` 到
`task_intrinsic_challenge_event_ids` 的 exact names bridge。A1 不是 conflict
premise，也没有被选择、激活或用于修复该 frozen conflict。

因此该 rule 同时保留 `CONFLICT/conflict-witness`，并进入
`unsupported_bound_source_rule_ids`。这不是否认 conflict，而是拒绝把未选择的
names bridge 伪称为 source-entailment。

## 4. 八条 source-unsupported target propositions

Sidecar 明确记录以下八条 frozen target proposition 含有 bound sources 不能推出的
内容：

| Rule | 尚未由 bound source 推出的内容 |
| --- | --- |
| `LABEL-PARAM-MANDATORY-IDS` | typed episode-input 到 normalized mandatory-ID output 的 projection |
| `LABEL-PARAM-FOUR-POINTER-MEMBERSHIP-CONFLICT` | 未选择的 exact field-name bridge |
| `LABEL-PARAM-INTRINSIC-NAME-TRANSITION` | 两个 intrinsic field names 的正式 rename compatibility |
| `LABEL-PROJECT-RENAME-COPY` | selected path-level rename-copy projection |
| `LABEL-PROJECT-DIRECT-COPIES` | 三个 target paths 的 selected direct-copy projection |
| `LABEL-PROJECT-EPISODE-JOIN` | label episode 到 environment Base 的 all-field join |
| `LABEL-ERROR-CONSTRUCTOR-DETAIL` | label-specific predicate order 与 error assignment |
| `LABEL-TRACE-CANDIDATE` | literal constructor trace sequence 与 output roots |

`unsupported_bound_source_count=8` 由 exact verdict set 重算，不能自由填写。

三条 `DERIVABLE` rules 都保留 frozen status，但同时固定：

```text
derivation_ast = null
replay_performed = false
derivation_input_root = null
derivation_output_root = null
schema_closure_sufficient = false
resolution_selected = false
machine_semantic_entailment = false
normative_effect = false
```

因此 `DERIVABLE` 不是已执行的 derivation，也不是 normative projection closure。

## 5. Exact anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = ccc38d65a89df79929aae4b14566a7be1d810435

module SHA-256 =
  3cf0242b608201768d6a96404b313d2780ba1d74e80ebe3d8247a60a5e77deb2
test SHA-256 =
  42ee43abe5f94ffa1dcb9b5d87f8372131cfc14596be8c4a32227d5592154e52
```

Generated labels overlay：

```text
bytes = 78044
RAW =
  sha256:1a6938b89e29d9a55ecb6a691b590e4d2181c9fbb60e481f238faa6261256fef
overlay_root =
  sha256:881a36a51ae14db6d4dd5df3069a1faf9453204cc5b7ea86e27817963ba075de
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:89e799a410f68b437609dcc148129df40c75890c6b2bd0cd156f9d02dedd3050
classification_review_set_root =
  sha256:dda4504e7f124a0cf6f02ee2b87dbc31cd740783b0fd3a9b638ddd80425d99b2
unresolved_set_root =
  sha256:a76da2433defff5e003effa563c26e00befc1435e4b31797f0dfc110aa5a3b32
```

`artifact_anchors_validated=true` 与
`report_policy_anchor_validated=true` 必须同时成立。两次相互独立的标准库
canonical JSON 与 domain-separated SHA-256 recomputation 未采信待冻结常量，
并与 anchored build validation 得到相同结果。

Environment、suite 和 replica-pair modules、tests、generated bytes 与 roots 在本
slice 后保持 byte-identical。Labels wrapper 只导入 common evidence engine，不导入
resolution producer。

## 6. Zero boundary 与 verification

Common engine 对该 family 固定：

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

Module 没有 filesystem I/O、environment/secret 读取、provider/network access、
resolution-producer import 或 write entrypoint。它没有选择 A1，没有生成 schema、
label projection、Base/actual artifact、Main、GoldenOracle、R0-R8 receipt 或科研
outcome。

Provider-free final verification：

```text
labels dedicated:
  18 passed, 33 subtests passed

common + environment + suite + replica-pair + labels:
  64 passed, 127 subtests passed

all V2 authoring-pattern tests:
  152 passed, 191 subtests passed

targeted Ruff, module mypy, py_compile:
  passed

88-codepoint and display-width scan:
  passed

git diff --check:
  passed

independent final anchor/code/semantic/tamper red-team:
  reported defects = 0
```

Tamper tests 覆盖 source/audit/overlay、七个 anchors、report-policy、static
binding/locator/role、whole-source、collective reroot、authority escalation 和
cross-family artifacts；所有攻击都 fail closed。

`152/152` 只指 V2 authoring-pattern tests，不是 external lab 的完整 qualification
suite。此前完整 discovery 的 frozen source/prereg guard 非绿色结果没有在本 slice
重写、隐藏或宣称已通过。

## 7. 对科研结论与下一步的影响

本 slice 只减少 labels evidence provenance 的混淆。它不降低 G2/G3 NO-GO，不授权
Main、GoldenOracle、R0-R8、API key 或 LLM run，也没有生成任何 arm outcome。

所以当前结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一 provider-free 顺序是：

1. 以相同边界为 source、process 补独立 scoped overlays；在专门的 overlay-set
   artifact 出现前，四个现有 sidecars 永久保留各自单体范围；
2. 另行规范 label field-name amendment、typed mandatory-ID projection、
   rename/direct-copy、episode join、negative fixtures、preflight 和 literal trace；
3. 六类 normative schema/projection 全部关闭并独立复核后，才进入 Main contract
   与 GoldenOracle authoring；
4. G0-G3 全部通过前，不读取或配置 LLM API key，不调用 provider。
