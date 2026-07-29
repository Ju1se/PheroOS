# Receptor-Gated Ligand Field v0.7 Replica-Pair Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点在不修改 frozen six-family resolution audit、environment sidecar 或
suite sidecar 的前提下，新增一个独立的 `replica_pair` evidence overlay。它只回答：

- 14 条 frozen replica-pair rules 的 exact source evidence 在哪里；
- 哪些 source bytes 可作为 premise、integrity context 或 semantic context；
- 哪些 whole-source 检查只是人工 absence-review domain；
- 哪些 frozen target propositions 含有 bound sources 无法推出的作者合成；
- 哪些 blocker 在 schema、projection、execution 或 actual A/B evidence
  materialize 前必须继续保持开放。

原 63,776-byte resolution artifact 保持不变，其中
`rule_source_locator_count=0`、`semantic_entailment_proof_count=0`。新 sidecar 的
scoped coverage 是：

```text
family = replica_pair
family rules = 14 / 14
source-ref edges = 23 / 23
locators = 41
global rules covered = 14 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

Environment、suite 和 replica-pair 是三个独立 artifact；当前不存在绑定其有序、
无重叠、同源 union 的 overlay-set artifact。因此不得发布 combined numerator、
coverage fraction，或把任一单体的 `global_rule_coverage_complete` 提升为
`true`。

## 2. Classification、selectors 与 evidence roles

Sidecar 不改写 frozen target statuses：

| Target status | Count | Review relation |
| --- | ---: | --- |
| `PROVEN` | 4 | `direct-support` |
| `DERIVABLE` | 1 | `conditional-derivation-review` |
| `OPEN` | 9 | `closure-insufficiency-review` |
| `CONFLICT` | 0 | `conflict-witness` |

这里的 `PROVEN` 仍只是旧 author-reviewed matrix 的 status 名称。Overlay 固定：

```text
author_reviewed_semantic_record_count = 14
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

41 个 locators 的 selector 分布是：

| Selector | Count |
| --- | ---: |
| exact Markdown span | 27 |
| RFC 6901 JSON pointer | 5 |
| whole-source absence-review domain | 9 |

27 个 Markdown locators 复用 18 个 exact byte spans；5 个 JSON locators 各自固定
pointer、canonical value bytes 和 root。Evidence-role 分布是：

| Role | Count | 边界 |
| --- | ---: | --- |
| `premise` | 15 | 只支持被严格限定的 review 命题 |
| `integrity-context` | 2 | 只绑定 counterfactual/integrity 状态 |
| `semantic-context` | 15 | 提供语义上下文，不升级为 entailment proof |
| `absence-domain` | 9 | 人工检查的完整 source domain，不是机器 absence proof |

每个 locator 都绑定 target rule、source ordinal、source bytes/root、selector 和
evidence role。每个 review 另外固定 target rule root、status、typed proposition、
blockers、ordered premise bindings 和 verdict。这样合法形状但错误的 role、target、
verdict、blocker 或 locator/review 集体重根都会 fail closed。

## 3. 七条 source-unsupported target propositions

Sidecar 明确记录以下七条 frozen target proposition 含有 bound sources 不能推出的
内容：

| Rule | 尚未由 bound source 推出的内容 |
| --- | --- |
| `PAIR-PARAM-DISTINCT` | reusable replica identifiers 的 generic distinctness rule |
| `PAIR-PARAM-DOMAIN-AND-SYMMETRY` | closed identifier domain 与交换对称性 |
| `PAIR-PROJECT-TWO-BY-SEVEN` | 两个 replica × 七个 views 的 all-field projection |
| `PAIR-PROJECT-COPY-REFERENCE-RECHAIN` | copy/reference/re-chain 的唯一 storage contract |
| `PAIR-ERROR-PARAMETERS` | pair-specific parameter error assignment 与 total precedence |
| `PAIR-TRACE-CANDIDATE` | literal constructor trace sequence |
| `PAIR-OPEN-SWAP-RELATION` | A/B swap 后 root 的规范关系 |

`unsupported_bound_source_count=7` 由 exact verdict set 重算，不能自由填写。

### 3.1 `PAIR-PROJECT-TWO-BY-SEVEN` 反过度结论

该 rule 为保持旧 resolution audit 不变而继续使用 frozen `DERIVABLE` status，但
sidecar 固定：

```text
relation = conditional-derivation-review
verdict suffix = unsupported-by-bound-source
derivation_ast = null
replay_performed = false
schema_closure_sufficient = false
resolution_selected = false
machine_semantic_entailment = false
normative_effect = false
```

Profile 可以支持“两组 review-seven projections”的候选几何，但不能唯一推出
14 个 all-field records 的 stable-ID、storage、source-neutral/actual-chain
placement、root formula 或 re-chain 规则。因此 `2 × 7` 算术不等于 projection
contract，也不等于 materialized pair evidence。

### 3.2 Actual-evidence OPEN 边界

`PAIR-OPEN-ACTUAL-EVIDENCE` 不在七条 unsupported set 中。Bound resolution audit
明确把 actual observation、materialization、provider 和 outcome counts 固定为零；
whole-source review 可以支持“当前 corpus 没有绑定 fresh A/B artifact 或 manifest
comparison record”这一 OPEN 边界。

这仍不是机器证明未来或外部系统中不存在相关证据。它只把“本次 exact
seven-source corpus 未绑定可升级该 rule 的 artifact”封存为 author-reviewed
OPEN 判断；不构成 machine 或 normative absence proof。

## 4. Exact anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = 00e6ba609ee8cda617004a503741f108c0b8b70c

module SHA-256 =
  555274a6fd81992d20f6ec76608743b068b788524e30573c52a5caa65f1a77a8
test SHA-256 =
  43ea068aef8c9df9d0e17d4ad4d3135d6cc04835e555616512d42f868173dfb6
```

Generated replica-pair overlay：

```text
bytes = 69838
RAW =
  sha256:829c377728f42d44ae6ea800dc6bb6a57d36ee846bae3468e4b2271e438c75c8
overlay_root =
  sha256:953c8abc4629415fbfcb53405bd2d92caa722a968f9c256e0a3bfdf57517013b
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:c9667b26609679ed79d2a6cfbd29a2e6d0c892b5f3e13ada6f62ae35f584fa51
classification_review_set_root =
  sha256:e92ed8b747599f41b355416e6c9d414cdaf9f129020177555557fd177fc6de83
unresolved_set_root =
  sha256:b1f81868d50aa96959234d3b55ba95170ea0149c269db8cc9f446ac2341ac915
```

`artifact_anchors_validated=true` 与
`report_policy_anchor_validated=true` 必须同时成立。后者把 unresolved/report
blocker policy 与 exact definition 绑定，防止 overlay bytes 不变但报告把 blocker
改写为已关闭。

Environment 和 suite modules、tests、generated bytes 与 roots 在本 slice 后保持
byte-identical；replica-pair wrapper 只导入 common evidence engine，不导入
resolution producer。

## 5. Zero boundary

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
pair projection、Base/actual artifact、Main、GoldenOracle、R0-R8 receipt 或科研
outcome。

## 6. Verification

Provider-free final verification：

```text
replica-pair dedicated:
  13 / 13 passed

common + environment + suite + replica-pair:
  46 / 46 passed

all V2 authoring-pattern tests:
  134 / 134 passed

py_compile:
  passed

88-codepoint and display-width scan:
  passed

git diff --check:
  passed

independent final code/semantic/tamper review:
  P0=P1=P2=P3=0
```

独立 verifier 不调用生产 root helper，使用 NFC、canonical JSON 和 SHA-256 重算
audit/family、14 rule roots、14 target-binding roots、7 sources、41 locators、
14 reviews、premise sets、aggregates、unresolved 和 overlay 共 126 项检查，
`0 mismatch`。

Tamper tests 覆盖 source/audit/overlay anchors、locator 缺失/新增/重排、合法 role
替换、whole-source rule/status、target root、unsupported set、verdict 协同重根、
unresolved policy 和 cross-family definition。所有攻击都 fail closed。

`134/134` 只指 V2 authoring-pattern tests，不是 external lab 的完整 qualification
suite。此前完整 discovery 的 frozen source/prereg guard 非绿色结果没有在本 slice
重写、隐藏或宣称已通过。

## 7. 对科研结论与下一步的影响

本 slice 只减少 replica-pair evidence provenance 的混淆。它不降低 G2/G3 NO-GO，
不授权 Main、GoldenOracle、R0-R8、API key 或 LLM run，也没有生成任何 arm outcome。

所以当前结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一 provider-free 顺序是：

1. 以相同边界为 labels、source、process 补独立 scoped overlays；在专门的
   overlay-set artifact 出现前，environment、suite、replica-pair 永久保留各自
   `15/90`、`15/90`、`14/90` 的单体范围；
2. 另行规范 replica identifier domain、distinctness/symmetry、all-field
   two-by-seven projection、copy/reference/re-chain storage、dual-evidence
   envelope、preflight 和 literal trace；
3. 六类 normative schema/projection 全部关闭并独立复核后，才进入 Main contract
   与 GoldenOracle authoring；
4. G0-G3 全部通过前，不读取或配置 LLM API key，不调用 provider。
