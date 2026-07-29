# Receptor-Gated Ligand Field v0.7 Six-Family Evidence Overlay-Set Audit

状态：`research-only-structural-overlay-set`；G2/G3 NO-GO 继续有效

检查日期：2026-07-29

## 1. 结论与允许发布的 claim

本检查点把 environment、suite、replica-pair、labels、source 和 process 六个
已发布 scoped evidence sidecars 绑定为一个 provider-free、content-addressed、
有序的 overlay-set。它关闭的范围严格是：

```text
ordered families = 6 / 6
ordered rule-review bindings = 90 / 90
ordered rule x source-ref edges = 149 / 149
locator bindings imported from exact children = 217 / 217
```

因此只允许发布两个 complete claim：

```text
structural_rule_review_coverage_complete = true
structural_rule_source_ref_edge_coverage_complete = true
```

`217/217` 表示相对于六个 exact child sidecars 的 locator-binding union 已完整
导入、排序和内容寻址。它不表示所有未来 schema、projection、trace、actual
evidence 或 semantic-proof locators 已经存在，也不构成 global semantic 或
global locator closure。

原 63,776-byte constructor resolution audit 没有被回写：

```text
rule_source_locator_count = 0
semantic_entailment_proof_count = 0
```

六个 child 的 `global_rule_coverage_complete` 也继续为 `false`。Overlay-set
不能把 scoped structural union 解释成任一 child、V2 contract 或研究计划的
global completion。

## 2. Exact child union

Family order 固定为：

```text
environment
suite
replica_pair
labels
source
process
```

每个 family binding 都保留 ordinal、child byte count、raw root、overlay root、
family record root、locator/review/unresolved roots 和原始 counts。Environment
通过只读 adapter 接入，其 child unresolved-policy root 固定为：

```text
sha256:bfc9a9da0af018f5f34e05267f6fb1d8fff218e3e1911761ffa86beb5e59b459
```

Adapter 不修改 environment child；全局 policy 明确固定
`family_child_mutation_performed=false`。

| Family | Rules | Edges | Locator bindings | P | D | O | C | Unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| environment | 15 | 20 | 26 | 6 | 3 | 6 | 0 | 1 |
| suite | 15 | 22 | 25 | 5 | 1 | 9 | 0 | 4 |
| replica-pair | 14 | 23 | 41 | 4 | 1 | 9 | 0 | 7 |
| labels | 16 | 34 | 46 | 5 | 3 | 7 | 1 | 8 |
| source | 16 | 27 | 37 | 6 | 2 | 8 | 0 | 8 |
| process | 14 | 23 | 42 | 5 | 3 | 6 | 0 | 5 |
| **Total** | **90** | **149** | **217** | **31** | **13** | **45** | **1** | **33** |

Set 保存 90 个 ordered rule IDs、90 个 exact child reviews 和 90 个 unique
rule-review bindings。149 个 unique rule × source-ref edges 同时验证 family-local
ordinal 与 global ordinal，并要求其 locator references all-and-only 闭合。

## 3. Locator binding 与 physical selector 必须分层

217 个 locator bindings 保留 family、rule、source edge 和 evidence role；同一
physical source location 可以被不同 rules、families 或 roles 复用。其 selector
分布为：

| Binding selector | Count |
| --- | ---: |
| exact Markdown span | 121 |
| RFC 6901 JSON pointer | 63 |
| whole-source review domain | 33 |
| **Total** | **217** |

Physical selector 以完整 canonical address 去重。Address 包含 source identity、
source raw root、selector kind、byte range 或 JSON pointer、whole-source
discriminator 和 excerpt anchors。它不按 excerpt digest 单独去重：

| Physical selector | Count |
| --- | ---: |
| exact Markdown span | 50 |
| RFC 6901 JSON pointer | 40 |
| whole-source review domain | 3 |
| **Total** | **93** |

Evidence-role bindings 保留为：

| Evidence role | Count |
| --- | ---: |
| premise | 105 |
| integrity-context | 20 |
| semantic-context | 59 |
| absence-domain | 33 |
| **Total** | **217** |

93 个 physical selectors 中，有 15 个跨 family 共享；其中 9 个在不同 bindings
中承担不同 evidence roles。Set 保留 role differences，不把物理位置相同误写为
语义用途相同。

Source-aware `(source_ref, source_raw_root, excerpt_raw_root)` content groups 为
87，而只看 excerpt digest 的 groups 为 85。这一差异证明 content hash alone
会错误折叠 source context；因此：

```text
content_hash_only_selector_deduplication_used = false
```

## 4. Reviews、unsupported targets 与 blockers

Overlay-set 不重新裁决 child reviews，只保持 frozen author-reviewed
classification：

| Status | Count | Relation |
| --- | ---: | --- |
| `PROVEN` | 31 | `direct-support` |
| `DERIVABLE` | 13 | `conditional-derivation-review` |
| `OPEN` | 45 | `closure-insufficiency-review` |
| `CONFLICT` | 1 | `conflict-witness` |

这里的 31 个 `PROVEN` 仍是 author-reviewed records，不是 machine 或 normative
semantic entailment。33 条 target propositions 被明确标记为 bound source
不支持：

```text
unsupported PROVEN = 0
unsupported DERIVABLE = 10
unsupported OPEN = 22
unsupported CONFLICT = 1
```

全部 13 条 `DERIVABLE` 都没有 replay：11 条没有 derivation AST，另外 2 条有 AST
但没有 replay。唯一 `CONFLICT` 仍是 labels family 的 frozen
`CONFLICT/conflict-witness`；set 没有清除、降级或扩散该冲突。

45 个 OPEN 与一个 CONFLICT 各保留一个显式 blocker，共 46 个 blockers。Family
policy 绑定每个 child 的 unresolved set；policy、review、blocker 和 outer set roots
共同防止在 child bytes 不变时删除 blocker、提升 status 或改写报告边界。

## 5. Content-addressed graph 与 red-team closure

External helper byte-first 重建一个 resolution audit、一个 shared source corpus 和
六个 exact child overlays，再生成 ordered family、review、edge、locator、physical
selector、policy 与 blocker collections。它明确声明：

```text
distinct_resolution_audit_binding_count = 1
distinct_source_set_binding_count = 1
scientific_replication_claim = false
independent_replication_count = 0
```

六个 sidecars 使用同一 source corpus；它们不是六次独立科学复现，也不证明历史、
统计、实现或 review independence。

独立审计在 freeze 前发现并关闭了以下结构缺口：

- outer collective collections 必须参与重新求根，不能只验证缓存 root；
- 删除 premise、locator 或 edge 后，即使保持表面 count，也必须因闭包不完整而拒绝；
- family-local ordinal 与 global ordinal 必须同时绑定；
- 149 条 edge 必须按 family/rule/source order 构成 exact union；
- 非法 RFC 6901 escape，包括 `~2`、trailing `~` 和 double escape，必须拒绝。

最终 tamper matrix 还覆盖 child identity swap、family/rule/review reorder、
physical-address collision、source-aware digest collapse、role swap、status/
unsupported/conflict promotion、fake AST/replay、blocker drop/retarget、
provider/schema/authority promotion、noncanonical JSON 和 source/audit byte tamper。
所有攻击在完整重新求根后 fail closed。

## 6. External identity 与 artifact anchors

External research branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = 4c7993d09391977b892958dc0962e9a62f200d1b

module =
  src/rglf_lab/v2_constructor_rule_evidence_overlay_set_authoring.py
module SHA-256 =
  85fa8a912eec01b8fecae4b0f6aeccb001420b28c22edf406aeec7d55378dbbe

test =
  tests/test_v2_constructor_rule_evidence_overlay_set_authoring.py
test SHA-256 =
  7e3f04f66fa791c45d2322fafb5495972bfb9112799508d1471590d0e5847fa9
```

Generated in-memory artifact：

```text
bytes = 688038
RAW =
  sha256:657218e20176dff13b5049dc71be4be068762fd931e34808894de54212e3c542
overlay_set_root =
  sha256:b59de963e86845a19a282fe2e21b5eaf1bc3e35c651c02fa9a8bbae31b485201
family_binding_set_root =
  sha256:e3a08eb13f3966f9b048da7cbc6badac3384fb97e1d2ab45b0900511ebad27cc
physical_selector_set_root =
  sha256:cef35678808e50947520c1f7360fb8cf3c88cf58cce4cde526ca47c08567ad02
locator_binding_set_root =
  sha256:04c3d2246211bc8cf81a1f3910a58f0f919092f834a814fe0dfa1bb0d51bcab1
rule_review_binding_set_root =
  sha256:3dd8471359c0fda5586228f47567d717686506652e318758eedda347aea4601a
source_ref_edge_set_root =
  sha256:bbe5c9c627849e2d92bbaacaadf6eec184b8945bae67dafb6c810371f8d2d5b3
policy_set_root =
  sha256:cded966be81cdeb3c53d202e2367741b2292ac7ff5d8de1c4d0c30b79f27d0e0
blocker_set_root =
  sha256:f4e7027b1b77fefd354668a329a2c9b93800635620697b803f43ea727ca84c42
```

这些九个 digest anchors 与 byte count 只标识该 authoring artifact。它不是
normative schema root、activation root、Main root 或 GoldenOracle root。

## 7. Verification 与未运行项

Provider-free stable verification：

```text
targeted overlay-set:
  18 passed, 127 subtests passed

common + six family overlays + overlay-set:
  114 passed, 326 subtests passed

all V2 authoring-pattern tests:
  202 passed, 390 subtests passed

Ruff:
  passed

module mypy:
  passed

compileall:
  passed

88-codepoint and display-width scan:
  passed

git diff --check:
  passed

anchored read-only audit:
  passed
```

本 slice 没有运行 full external discovery，因此 `202/202` 不能写成 full suite
green。历史 full discovery 的 `1 failure + 1 error` 仍按 frozen-source/prereg
isolation 记录；它不是本 slice 的新执行，也没有被 focused tests 覆盖或抹除。

## 8. Zero-effect boundary 与下一步

Overlay-set 固定：

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

因此 P1 #1 中的 six-family structural locator-union/overlay-set 子问题已关闭，但
exact Base projections、nested schemas、全六类 machine semantic proofs 和
construction traces 仍开放。P1 总数继续是“至少 19”，不是 18。

本检查点不降低 G2/G3 NO-GO，不授权 Main、GoldenOracle、R0-R8、API key、provider
canary 或 LLM experiment，也没有生成任何 arm outcome。当前科研结论不变：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1-H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

下一步继续 provider-free：分别冻结六类 normative parameter schemas、exact Base
projections、error precedence、construction traces 以及 source/process actual
evidence contracts。只有这些 contracts 独立复核通过后，才进入 Main 与
GoldenOracle authoring；G0-G3 全部通过前不读取或配置 API key。
