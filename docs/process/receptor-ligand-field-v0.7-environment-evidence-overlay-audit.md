# Receptor-Gated Ligand Field v0.7 Environment Evidence Overlay Audit

状态：`research-only-scoped-overlay`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与范围

本检查点为 six-family constructor resolution audit 增加一个独立、
provider-free、content-addressed evidence overlay。它只覆盖 `environment`
family，不修改或替换原 audit：

```text
original resolution audit:
  bytes = 63776
  RAW =
    sha256:448be7156c0640c46c6f83f6efe2b5568acbb4663b75d3107e85b344f63def3d
  audit_root =
    sha256:c1b3b94ff07221a953c7373f77465f28f0f39df86cb1efd05dd19c4a12557669
  rule_source_locator_count = 0
  semantic_entailment_proof_count = 0
```

原 artifact 中的两个零值保持不变。Overlay 的 scoped 覆盖是：

```text
family = environment
family rules = 15 / 15
source-ref edges = 20 / 20
locators = 26
global rules covered = 15 / 90
family_rule_coverage_complete = true
global_rule_coverage_complete = false
```

它保留原 classification：

| Status | Count |
| --- | ---: |
| `PROVEN` | 6 |
| `DERIVABLE` | 3 |
| `OPEN` | 6 |
| `CONFLICT` | 0 |

这里的 `PROVEN` 是原 author-reviewed matrix 的 status 名称，不表示 overlay
产生了 machine 或 normative semantic proof。

## 2. Exact seven-source registry

| Source | Bytes | RAW |
| --- | ---: | --- |
| active experiment profile v0.6 | 6,099 | `sha256:b1a7aa84664baacdf683af406aa4e88b118ef45b001986e7f438c5d31715a979` |
| draft experiment profile v0.7 | 119,802 | `sha256:bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6` |
| materialization plan | 44,724 | `sha256:e19f6caff36b79be3693855c77559d777277c065da77146624e23143cfd7ced9` |
| V2 closure design | 50,024 | `sha256:a462140f0a21880b479eb17e8acad0eb4e2349866210f2881de8685f769b21bb` |
| four-pointer counterfactual | 62,093 | `sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795` |
| unselected T7 A1 counterfactual | 62,094 | `sha256:3929670021f447c6f3c4f325be2db46f89809468a72428b57374bb93e80c035b` |
| T7 A1 correction audit | 6,744 | `sha256:b6736881bf1f996d261f3012b1eb902259d2ef870185b870eda219b414fdba92` |

Source-set root：

```text
sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
```

`v0.7` 仍是 draft，A1 仍是 unselected counterfactual。Exact bytes 被定位不等于
它们已进入 active profile、Main、GoldenOracle 或 runtime。

## 3. Locator 与 classification-review 边界

26 个 locators 覆盖 20 个 `rule × source_ref` edges。一个 edge 可以需要多个
locator；因此不能把 26 写成 26 个独立 semantic proofs。

允许的 locator 只有：

- exact Markdown ATX section byte range；
- canonical JSON RFC 6901 value；
- 仅对 OPEN rule 使用的 whole-source absence-review domain。

Markdown locators 固定 heading path、exact offsets、excerpt bytes/root 和 source
bytes/root。JSON locators 固定 pointer、canonical value bytes/root 和 source
bytes/root。Whole-source locator 固定完整 source range；absence review 仍只是
author-reviewed domain，不是机器证明“某语义不存在”。

每个 review 的 premise root 承诺有序
`{locator_id, locator_root}` bindings，而不只承诺 locator IDs。每条 rule 还固定
`target_rule_root + target_status + typed proposition + blockers` 的 target-binding
root，以拒绝 locator/review 集体重根、合法形状但虚构的 proposition 和 blocker
替换。

Relation counts 为：

| Review relation | Count |
| --- | ---: |
| `direct-support` | 6 |
| `conditional-derivation-review` | 3 |
| `closure-insufficiency-review` | 6 |
| `conflict-witness` | 0 |

所有 15 条记录都是 human author review：

```text
classification_author_reviewed = true
author_reviewed_semantic_record_count = 15
machine_semantic_entailment_proof_count = 0
normative_semantic_entailment_proof_count = 0
```

### 3.1 Strict integer 反过度结论

`ENV-PARAM-STRICT-INTEGER` 保留原 `DERIVABLE` status，但 bound source 只区分抽象
`boolean` 与 `integer` node kind，不能推出 Python-specific：

```text
type(value) is int
```

特别是它不能推出“Python `bool` 必然被排除”。该 locator 的 role 是
`integrity-context`，固定 verdict 为：

```text
unsupported-python-specific-transform-by-bound-source
```

所以该项仍需 future normative source/validator contract；不能用当前 overlay 把它
提升为已证明的 constructor rule。

## 4. Exact overlay anchors

External authoring branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = ea73fe1add86529884adbf0ece7f6622fe4e3fa9

module SHA-256 =
  8cabf1129f422d5b35bb52947807685114489f4bb2a2558e57e2c90493a97757

test SHA-256 =
  2a351a81fc3d35f6f5f165da2b9e52d51161c00c3c9b6470f3b68be86fd57f47
```

Generated overlay：

```text
bytes = 55432
RAW =
  sha256:76eb5d9d7c613fe5c7ace130837bd0eb0fa50d67cc3d235fbe524bd7662bd5f6
overlay_root =
  sha256:abb8c6eee795b8dc1076d0f35c5289e615988ba790e813af0e6c2abe5c5b273c
source_set_root =
  sha256:81553b90b8912f9846974705da7f35687e1f13baaea9517cf147cb2f7df8b039
locator_set_root =
  sha256:0616c7bdbab23be6990b8edaa206ec205592302a5db943e2cc74d6768e7c3ecf
classification_review_set_root =
  sha256:4f639f680b0d8e2698c3749e6abba3008f27878a2bf00314b3659099eaa53ed0
```

## 5. Zero boundary

Overlay 固定：

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

它没有执行 constructor，没有生成 normalized view/Base bytes，没有选择 A1，没有
读取 outcome 或 credential，也没有调用 provider/network。

## 6. Verification

最终 provider-free verification：

```text
targeted tests:
  16 passed, 35 subtests passed

seven V2 authoring modules:
  104 unittest tests passed

Python 3.12 / 3.13 / 3.14:
  16 overlay tests per interpreter
  OK

Ruff:
  All checks passed

py_compile:
  passed

git diff --check:
  passed

independent code, semantic and tamper review:
  P0=P1=P2=P3=0

paired frozen-Q boundary check:
  canonical lab 2f1d473: 1 passed in 48.96 s
  authoring branch ea73fe1: expected source-identity refusal,
    1 failed in 49.02 s
```

Tamper review 会重算 locator roots、premise-binding roots、review/set roots、
overlay root，并临时替换外层 freeze anchors；它仍拒绝：

- source、selector、RFC 6901、exact offset、excerpt 和 edge/ordinal 替换；
- locator/review target-rule collective rewrite；
- well-shaped proposition、blocker、status、relation 或 verdict 替换；
- review 只承诺 ID、不承诺 locator content 的降级；
- conditional/unsupported/semantic/authority aggregate 假提升；
- A1 selection、v0.7 activation、global coverage 或 schema/execution 假提升。

## 7. 对科研与下一步的影响

本 slice 只减少 environment evidence provenance 的混淆。它不降低 G2/G3 NO-GO，
不授权 Main、GoldenOracle、R0-R8、API key 或 LLM run，也不产生任何 arm outcome。

所以当前结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一 provider-free 顺序是：

1. 以同样边界为 suite、replica pair、labels、source、process 补 scoped
   locator/review overlays；本 environment artifact 永久保持 `15/90`，后续
   artifact 报告自己的 scoped coverage 或已覆盖 union，只有 `90/90` 才能令
   global coverage complete；
2. 单独解决 environment source-neutral/actual re-chain、all-field projection、
   sealing context、constructor preflight 和 literal trace；
3. 六类 normative schema/projection 关闭后，才进入 Main contract 与独立
   GoldenOracle authoring；二者分别冻结并通过独立复核后，才讨论 materialization；
4. G0-G3 全部通过前，不读取或配置 LLM API key。
