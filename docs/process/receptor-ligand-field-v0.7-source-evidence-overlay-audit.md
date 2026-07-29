# Receptor-Gated Ligand Field v0.7 Source Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点在不修改 frozen six-family resolution audit 或此前 evidence helpers 的
前提下，新增一个独立的 `source` evidence overlay。它只回答：

- 16 条 frozen source rules 的 exact source evidence 在哪里；
- 哪些 source bytes 是 premise、integrity context 或 semantic context；
- 哪些 whole-source 检查只是人工 absence-review domain；
- 哪些 target propositions 含有 bound sources 无法推出的作者合成；
- 哪些 actual Git、Python/interpreter 和 loaded-runtime evidence 仍不存在；
- 哪些 blocker 在 schema、projection、execution 或正式 source audit 前必须保持
  开放。

原 63,776-byte resolution artifact 保持不变，其中
`rule_source_locator_count=0`、`semantic_entailment_proof_count=0`。新 sidecar 的
scoped coverage 是：

```text
family = source
family rules = 16 / 16
source-ref edges = 27 / 27
locators = 37
global rules covered = 16 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

Environment、suite、replica-pair、labels 和 source 是五个独立 scoped artifacts。
当前不存在绑定其有序、无重叠、同源 union 的 overlay-set artifact。因此不得发布
combined numerator、coverage fraction，或把任一单体的
`global_rule_coverage_complete` 提升为 `true`。

## 2. Classification、selectors 与 evidence roles

Sidecar 不改写 frozen target statuses：

| Target status | Count | Review relation |
| --- | ---: | --- |
| `PROVEN` | 6 | `direct-support` |
| `DERIVABLE` | 2 | `conditional-derivation-review` |
| `OPEN` | 8 | `closure-insufficiency-review` |
| `CONFLICT` | 0 | `conflict-witness` |

这里的 `PROVEN` 仍只是旧 author-reviewed matrix 的 status 名称。Overlay 固定：

```text
author_reviewed_semantic_record_count = 16
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

37 个 locators 的 selector 分布是：

| Selector | Count |
| --- | ---: |
| exact Markdown span | 17 |
| RFC 6901 JSON pointer | 10 |
| whole-source absence-review domain | 10 |

Evidence-role 分布是：

| Role | Count | 边界 |
| --- | ---: | --- |
| `premise` | 12 | 只支持被严格限定的 review 命题 |
| `integrity-context` | 5 | 只绑定 unselected A1 与 correction-audit 状态 |
| `semantic-context` | 10 | 提供语义上下文，不升级为 entailment proof |
| `absence-domain` | 10 | 人工检查的完整 source domain，不是机器 absence proof |

Source locator 分布为：draft v0.7 `10`、materialization plan `3`、V2 closure
design `14`、unselected A1 `5`、A1 correction audit `5`；active v0.6 与
four-pointer counterfactual 均为 `0`。

每个 locator 都绑定 target rule、source ordinal、source bytes/root、selector 和
evidence role。每个 review 另外固定 target rule root、status、typed proposition、
blockers、ordered premise bindings 和 verdict。合法形状但错误的 role、target、
verdict、blocker 或 locator/review 集体重根都会 fail closed。

## 3. Source fixture 与 actual evidence 必须分层

本 sidecar 支持的 source 事实严格限于当前 synthetic fixture 和研究设计：

- A1 中七条 file records 的 literal declaration order、path、content 与 mode；
- input order 与候选 Unicode-derived order 是两个不同层；
- synthetic source fixture 不能替代 actual Git/source-freeze evidence；
- source judge stage 在 draft v0.7 中有声明顺序；
- review lifecycle 保持 provider-free、zero-authority。

它不产生或观察：

- Git commit/tree/blob/file-mode inventory；
- Python grammar freeze、interpreter build 或 execution receipt；
- executable path、`sys.path`、loaded-module 或 loaded-code identity；
- source constructor output、normalized source view 或 order witness；
- source-freeze manifest、runtime source manifest 或 process-start evidence。

`SOURCE-OPEN-ACTUAL-GIT-EVIDENCE` 和
`SOURCE-OPEN-RUNTIME-IDENTITY` 使用的 whole-source locators，只表明审阅者在已绑定
source domain 中没有找到相应 actual records。它们是人工 absence review，不是
machine absence proof，更不是 actual Git/runtime qualification evidence。

## 4. 八条 source-unsupported target propositions

Sidecar 明确记录以下八条 frozen target proposition 含有 bound sources 不能推出的
内容：

| Rule | 尚未由 bound source 推出的内容 |
| --- | --- |
| `SOURCE-PARAM-CURRENT-FRAME` | reusable NFC/framing validation procedure |
| `SOURCE-PARAM-PYTHON-GRAMMAR-EVIDENCE` | frozen Python grammar、interpreter matrix 与 execution receipts |
| `SOURCE-PARAM-GENERIC-POLICY` | generic path/mode/frame/collision/grammar policy |
| `SOURCE-PROJECT-UNICODE-PERMUTATION` | selected normalized Unicode-order witness |
| `SOURCE-PROJECT-POINTER-SHAPE` | path-keyed view、nested fields 与 sorted-pair root preimage mapping |
| `SOURCE-ERROR-CONSTRUCTOR-DETAIL` | source-specific predicate order 与 public error assignment |
| `SOURCE-TRACE-CANDIDATE` | literal source-construction trace sequence 与 output roots |
| `SOURCE-OPEN-ORDER-OUTPUT` | selected order-witness output schema |

`unsupported_bound_source_count=8` 由 exact verdict set 重算，不能自由填写。

两条 `DERIVABLE` rules：

```text
SOURCE-PARAM-CURRENT-FRAME
SOURCE-PROJECT-UNICODE-PERMUTATION
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

因此 `DERIVABLE` 不是已执行的 derivation，也不是 normative source projection
closure。

## 5. Exact anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = c1233a2bf7f71ae013973783fcb8f2612cfa1b09

module SHA-256 =
  161ebdb7a3f3a96a680a4d7bb1ef6abfd5587ac03a574ce5879a96296d08ffe2
test SHA-256 =
  0cace828e8b9b9362cd543035e57866691ca851df47fd56a3e647d13f36cf878
```

Generated source overlay 的七个 exact anchors：

```text
bytes = 69160
RAW =
  sha256:c9f8607496eb565e2f13e55842b22f46520293e322c787cc4214e371d679226f
overlay_root =
  sha256:cae3c99002f146b89fd8ac8c551782ce108a6c3199715488f6b75e5844f80999
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:22fb4114e662e9b53a06aec93242067f2736c02e1ed1609be5964e67e56c9f5a
classification_review_set_root =
  sha256:215860f96261637c774365aa73140cddc863f2a426227e4a7583c2427c151ee1
unresolved_set_root =
  sha256:94d5002c1cd826442ba603d91befc4aae5b08ff10c5df2edf69eae884d3d42f2
```

`artifact_anchors_validated=true` 与
`report_policy_anchor_validated=true` 必须同时成立。Independent red-team 对 exact
source、locator、review、report-policy 和 aggregate roots 做只读复算，并通过
anchored build 与 tamper checks。此前 common engine 及 environment、suite、
replica-pair、labels evidence helpers 保持 byte-identical；原 resolution audit
也保持不变。

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
resolution-producer import 或 write entrypoint。它没有生成 source policy/schema、
normalized view、Base/actual artifact、Git/runtime observation、Main、
GoldenOracle、R0-R8 receipt 或科研 outcome。

Provider-free final verification：

```text
source dedicated:
  16 passed, 35 subtests passed

common + environment + suite + replica-pair + labels + source:
  80 passed, 162 subtests passed

all V2 authoring-pattern tests:
  168 passed, 226 subtests passed

targeted Ruff, module mypy, py_compile:
  passed

88-codepoint and display-width scan:
  passed

git diff --check:
  passed

independent final anchor/code/semantic/tamper red-team:
  passed
```

Tamper tests 覆盖 source/audit/overlay、七个 anchors、report-policy、static
binding/locator/role、whole-source、collective reroot、authority escalation 和
cross-family artifacts；所有攻击都 fail closed。

`80/80` 和 `168/168` 只指 scoped evidence/V2 authoring-pattern tests，不是
external lab 的完整 qualification suite。此前完整 discovery 的 frozen
source/prereg guard 非绿色结果没有在本 slice 重写、隐藏或宣称已通过。

## 7. 对科研结论与下一步的影响

本 slice 只减少 source evidence provenance 的混淆。它不降低 G2/G3 NO-GO，不授权
Main、GoldenOracle、R0-R8、API key 或 LLM run，也没有生成任何 arm outcome。

所以当前结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一 provider-free 顺序是：

1. 以相同边界为 process 补最后一个独立 scoped overlay；在专门的 overlay-set
   artifact 出现前，五个现有 sidecars 永久保留各自单体范围；
2. 另行规范 source path/mode/frame/grammar policy、Unicode/order projection、
   source preflight、literal trace 和 actual Git/runtime evidence contracts；
3. 六类 normative schema/projection 全部关闭并独立复核后，才进入 Main contract
   与 GoldenOracle authoring；
4. G0-G3 全部通过前，不读取或配置 LLM API key，不调用 provider。
