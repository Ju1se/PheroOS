# Receptor-Gated Ligand Field v0.7 Process Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点在不修改 frozen six-family resolution audit 或此前 evidence helpers 的
前提下，新增一个独立的 `process` evidence overlay。它只回答：

- 14 条 frozen process rules 的 exact source evidence 在哪里；
- 哪些 source bytes 是 premise、integrity context 或 semantic context；
- 哪些 whole-source 检查只是人工 absence-review domain；
- 哪些 target propositions 含有 bound sources 无法推出的作者合成；
- 哪些 actual supervisor、clock、OS、rusage、source/process identity 和
  Observation evidence 仍不存在；
- 哪些 blocker 在 schema、projection、execution 或正式 process audit 前必须保持
  开放。

原 63,776-byte resolution artifact 保持不变，其中
`rule_source_locator_count=0`、`semantic_entailment_proof_count=0`。新 sidecar 的
scoped coverage 是：

```text
family = process
family ordinal = 5
family record root =
  sha256:1cc9b1f81814b91c06204336c53c52fa1c57450d39720e457b1536dd68125504
current candidate root =
  sha256:4d4f3bb94d464d5a010fc37e36f85605949b0ac60704b1fb39cf4913441a5f26
family rules = 14 / 14
source-ref edges = 23 / 23
locators = 42
global rules covered = 14 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

在本 process slice 生成时，environment、suite、replica-pair、labels、source 和
process 仍是六个独立 scoped artifacts，尚无 overlay-set。后续
[six-family evidence overlay-set audit](receptor-ligand-field-v0.7-six-family-evidence-overlay-set-audit.md)
已将其 exact children 绑定为有序、source-aware、保留跨 family 共享位置的
union，并只发布 90/90 rule-review 与 149/149 rule × source-ref edge 的
structural coverage。该后续 artifact 不回写本 sidecar，也不把本 sidecar 的
`global_rule_coverage_complete=false` 提升为 `true`；不得把 structural union
表述成 global semantic/locator closure。

## 2. Classification、selectors 与 evidence roles

Sidecar 不改写 frozen target statuses：

| Target status | Count | Review relation |
| --- | ---: | --- |
| `PROVEN` | 5 | `direct-support` |
| `DERIVABLE` | 3 | `conditional-derivation-review` |
| `OPEN` | 6 | `closure-insufficiency-review` |
| `CONFLICT` | 0 | `conflict-witness` |

这里的 `PROVEN` 仍只是旧 author-reviewed matrix 的 status 名称。Overlay 固定：

```text
author_reviewed_semantic_record_count = 14
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

42 个 locators 的 selector 分布是：

| Selector | Count |
| --- | ---: |
| exact Markdown span | 20 |
| RFC 6901 JSON pointer | 14 |
| whole-source absence-review domain | 8 |

Evidence-role 分布是：

| Role | Count | 边界 |
| --- | ---: | --- |
| `premise` | 20 | 只支持被严格限定的 review 命题 |
| `integrity-context` | 4 | 只绑定 unselected A1 与 correction-audit 状态 |
| `semantic-context` | 10 | 提供语义上下文，不升级为 entailment proof |
| `absence-domain` | 8 | 人工检查的完整 source domain，不是机器 absence proof |

Source locator 分布为：draft v0.7 `17`、V2 closure design `11`、unselected A1
`10`、A1 correction audit `4`；active v0.6、materialization plan 与
four-pointer counterfactual 均为 `0`。

每个 locator 都绑定 target rule、source ordinal、source bytes/root、selector 和
evidence role。每个 review 另外固定 target rule root、status、typed proposition、
blockers、ordered premise bindings 和 verdict。合法形状但错误的 role、target、
verdict、blocker 或 locator/review 集体重根都会 fail closed。

## 3. Synthetic transcript 与 actual process evidence 必须分层

本 sidecar 支持的 process 事实严格限于当前 unselected synthetic fixture 和研究
设计：

- A1 中 13 个 clean synthetic parameter literals 的 exact instance；
- 当前 `Cg==` segment、byte count 与 provided-count literals；
- draft v0.7 声明的 synthetic RSS input mapping 和条件公式；
- 当前 clock start/end literals；
- synthetic fixture 与未来 `ObservationV07` 的分层；
- resource-stage order、RSS applicability 与 OOM/crash guard 声明；
- review lifecycle 保持 provider-free、zero-authority。

它不产生或观察：

- actual child supervisor、process namespace 或 source/process identity；
- monotonic clock、OS、rusage、wait4、exit、signal、OOM、crash 或 timeout receipts；
- `ObservationV07` bytes、actual measurement view 或 judge-input selection；
- reusable process parameter schema、normalized transcript 或 all-field projection；
- process constructor output、literal trace、input/output roots 或 replay receipt；
- Main、GoldenOracle、R0-R8、provider outcome 或科研 arm outcome。

`PROCESS-PROJECT-ACTUAL-OBSERVATION` 和
`PROCESS-OPEN-ACTUAL-EVIDENCE` 使用的 whole-source locators，只表明审阅者在已绑定
source domain 中没有找到相应 actual records。它们是人工 absence review，不是
machine absence proof，更不是 actual OS/process qualification evidence。

`PROCESS-PARAM-EXACT-THIRTEEN` 等 exact-instance `PROVEN` 结论只适用于未选择的 A1
synthetic fixture。A1 不是实际 child process、supervisor、clock 或 OS evidence。

## 4. 五条 source-unsupported target propositions

Sidecar 明确记录以下五条 frozen target proposition 含有 bound sources 不能推出的
内容：

| Rule | 尚未由 bound source 推出的内容 |
| --- | --- |
| `PROCESS-PARAM-FRAME-CURRENT` | reusable strict base64/frame/count decode procedure |
| `PROCESS-PARAM-REUSABLE-SCHEMA` | generic process parameter policy |
| `PROCESS-PROJECT-CLOCK-CURRENT` | frozen elapsed-field projection |
| `PROCESS-ERROR-TOTAL-PREDICATES` | total process preflight predicates |
| `PROCESS-TRACE-CANDIDATE` | literal trace 与 output roots |

`unsupported_bound_source_count=5` 由 exact verdict set 重算，不能自由填写。

三条 `DERIVABLE` rules：

```text
PROCESS-PARAM-FRAME-CURRENT
PROCESS-PROJECT-RSS-CURRENT
PROCESS-PROJECT-CLOCK-CURRENT
```

都保留 frozen status，但同时固定：

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

其中只有 `PROCESS-PROJECT-RSS-CURRENT` 的 conditional synthetic formula 有 source
支持；它仍没有 AST、input/output roots 或实际 replay。其余两条也不能凭当前 literals
升级为 reusable frame 或 clock projection。因此 `DERIVABLE` 不是已执行的
derivation，更不是 normative process closure。

## 5. Exact anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = 8d4c4d3221b95180f5b2d159b6855eeb0b755dee

module SHA-256 =
  158eaa3d35166064a060d3e081c557c506cdc4249d1475775cacc1f1fe1f6afa
test SHA-256 =
  2366742d3523a3aacccbae5373d81b653065304ccbd741276f2e74d688928e91
```

Generated process overlay 的七个 exact anchors：

```text
bytes = 71805
RAW =
  sha256:5e988e74e20114b6cd3418b67f3a5da26b486155920ff0f48e3d0ff33db07ac9
overlay_root =
  sha256:bb9c2e148bb3da4685d95fffcaba81a93e6d9677b0f717b2b470854664995a58
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:907ad0b1fed2abc2c0f51ab85f054c67111e7f604530b583922d2654ba7d2c3e
classification_review_set_root =
  sha256:9aad694d0ce76baf4f3d9a97dbe3234178238d5c985ebc1aae52754ae63c7573
unresolved_set_root =
  sha256:7cf7c728147619e5db31141be936af71da7c801ee9e9ae9aee447ed83a4b3616
```

`artifact_anchors_validated=true` 与
`report_policy_anchor_validated=true` 必须同时成立。两次 independent final
red-team 对 exact source、locator、review、report-policy 和 aggregate roots 做
只读复算，并通过 anchored build 与 tamper checks。此前 common engine 及
environment、suite、replica-pair、labels、source evidence helpers 保持
byte-identical；原 resolution audit 也保持不变。

## 6. Zero boundary 与 verification

Common engine 对该 family 固定：

```text
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
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
resolution-producer import 或 write entrypoint。它没有生成 process policy/schema、
normalized view、Base/actual artifact、OS/runtime observation、Main、
GoldenOracle、R0-R8 receipt 或科研 outcome。

Provider-free final verification：

```text
process dedicated:
  16 passed, 37 subtests passed

common + environment + suite + replica-pair + labels + source + process:
  96 passed, 199 subtests passed

all V2 authoring-pattern tests:
  184 passed, 263 subtests passed

targeted Ruff, module mypy, py_compile:
  passed

88-codepoint and display-width scan:
  passed

git diff --check:
  passed

two independent final anchor/code/semantic/tamper red-teams:
  passed
```

Tamper tests 覆盖 source/audit/overlay、七个 anchors、report-policy、static
binding/locator/role、whole-source、collective reroot、authority escalation 和
cross-family artifacts；所有攻击都 fail closed。

`96/96` 和 `184/184` 只指 scoped evidence/V2 authoring-pattern tests，不是
external lab 的完整 qualification suite。本 slice 未运行完整 external discovery，
因此不得宣称 full external suite green。

## 7. 对科研结论与下一步的影响

本 slice 只减少 process evidence provenance 的混淆。它不降低 G2/G3 NO-GO，不授权
Main、GoldenOracle、R0-R8、API key 或 LLM run，也没有生成任何 arm outcome。

所以当前结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一 provider-free 顺序是：

1. Six-family overlay-set 的 structural locator-union 子问题已关闭；其允许的
   complete claim 仅限 90/90 rule-review 与 149/149 rule × source-ref edges，
   不改变本 sidecar 的 global-incomplete flag；
2. 继续规范六类 normative parameter schemas、all-field projections、error
   precedence、traces 和 source/process actual-evidence contracts；sidecar 不能
   代替这些 contracts；
3. 六类 normative schema/projection 全部关闭并独立复核后，才进入 Main contract
   与 GoldenOracle authoring；
4. G0-G3 全部通过前，不读取或配置 LLM API key，不调用 provider。
