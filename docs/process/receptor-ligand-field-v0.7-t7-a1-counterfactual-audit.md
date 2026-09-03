# Receptor-Gated Ligand Field v0.7 T7 A1 Counterfactual Audit

状态：`research-only-counterfactual-no-go`；不构成 profile amendment、final C1、
materialization、activation 或实验许可

日期：2026-07-29

## 1. 决定

Active v0.6 与 v0.7 no-estimand-change provenance 支持 T7 classification A：
intrinsic universe 为空，positions 33/34 均为 mandatory。External authoring helper
现已把建议的 A1 纠正机器化为 exact in-memory byte counterfactual：

```text
classification = "A"
source_state = "four-pointer-counterfactual-v1-not-final-c1"
candidate_state = "t7-a1-counterfactual-v1-not-final-c1"
correction_policy = "preserve-existing-event-34-copy-target-v1"
final_c1_selected = false
profile_amendment_performed = false
companion_write_performed = false
authority_scope = "none"
```

这关闭的是“建议的 A1 bytes、roots 和静态 locator 影响能否被精确复算”这一局部
research question。它没有选择 final C1，没有修改活动或候选 profile/companion，
没有关闭六类 constructor schemas/projections，也没有解除 G2/G3 NO-GO。

这里的 `A1` 专指 T7 label alternative，不是 V2 SourceFreeze 中的 official
materializer actor A1。

## 2. Exact transform

输入必须是既有 four-pointer counterfactual 的 exact canonical bytes，不接受
current 62097-byte companion、A0、already-A1、partial 或 non-canonical bytes。
A1 只有三项 substantive edits：

```text
/base_artifacts/9/parameters/task_intrinsic_challenge_event_ids
  [event:t7:9000:0:00033] -> []

/base_artifacts/9/parameters/mandatory_probe_event_ids
  [event:t7:9000:0:00034]
  -> [event:t7:9000:0:00033,event:t7:9000:0:00034]

/negative_fixtures/52/operations/0/value/path
  /mandatory_probe_event_ids/0 -> /mandatory_probe_event_ids/1
```

包含派生 roots 后，companion 恰好六个 JSON pointers 改变：

```text
/base_artifacts/9/parameters/mandatory_probe_event_ids
/base_artifacts/9/parameters/task_intrinsic_challenge_event_ids
/fixture_input_set_root
/negative_fixture_set_root
/negative_fixtures/52/operations/0/value/path
/semantic_manifest_root
```

`positive_fixture_set_root`、12/3/56 counts、Base/fixture IDs、judge、stage、
expected code、precondition 和 operation mutation target 均保持不变。

## 3. Content-addressed anchors

| Anchor | Four-pointer source | T7 A1 counterfactual |
| --- | --- | --- |
| bytes | 62093 | 62094 |
| raw root | `sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795` | `sha256:3929670021f447c6f3c4f325be2db46f89809468a72428b57374bb93e80c035b` |
| fixture-input root | `sha256:0227f38c34f9d50b81b257675065e73ab1c18e02fff684ca851603b3d963aed8` | `sha256:6cce58e91e662c282def133b6c53962a67b5b400d24e7bac1aac7e6cbe58c6b1` |
| positive root | `sha256:2a0e9ff10b6e2d5e2e42bebe77dd9c32f871a48638ad4d41a796995d1ce1613e` | unchanged |
| negative root | `sha256:5c4cf71f6985766af2ab30735900403ef2dfeee57e674b0a2abbd342590c785e` | `sha256:29b142086ae04c989390e0c0aa6cbccd315be9c5ad0f6600c2f1ce611553da1e` |
| semantic root | `sha256:eccec79803913d858ebc60b4c78ae8854a606102fffec7e681ae29c6d87a3bf2` | `sha256:7aaaaceba005b5a35946cc65d011311bb9b35d251a639aec5d201916131c51b9` |

Authoring audit 本身固定为：

```text
audit_byte_count = 6744
audit_raw_root =
  sha256:b6736881bf1f996d261f3012b1eb902259d2ef870185b870eda219b414fdba92
audit_root =
  sha256:d6edfe1f1f9dd2b193b4d1b7b8802d6c5e8c0564731dca80f2df012aa0624b1a
```

External branch 与实现锚点：

```text
branch = codex/v07-materialization-v2-authoring
implementation_commit = 6707c028dfec9fae7fdc166788e2dd7b5e56ac21
verification_head = d6e4d05c0b7db80b802394091de32efc11c929ba

src/rglf_lab/v2_t7_label_authoring.py
  sha256:e87a01b9944985d2bbe9441377abacdb5fc86305f9015e0e9a8d76ed7fd57603

tests/test_v2_t7_label_authoring.py
  sha256:d144dd5d76a968af7632f56bb76fd3dfb9f3ad6cdc57cb7a6b1ce8a0381aaedf
```

## 4. Event 34 preservation proof boundary

Source identity：

```text
Base index/pointer = 9 / /base_artifacts/9
Base ID = base:labels:T7:A4:N100:S9000:R0
negative index/pointer = 52 / /negative_fixtures/52
negative ID = N-T7-PROBE-AS-ATTACK
operation index = 0
mutation target = /variable_attack_event_ids/0
```

Exact RFC 6901 resolution：

```text
before:
  mandatory = [event:t7:9000:0:00034]
  locator = /mandatory_probe_event_ids/0
  resolved event = event:t7:9000:0:00034

after:
  mandatory =
    [event:t7:9000:0:00033,event:t7:9000:0:00034]
  locator = /mandatory_probe_event_ids/1
  resolved event = event:t7:9000:0:00034
```

因此 A1 保留了既有 negative recipe 引用的 event 34，且 mutation target 仍是
`/variable_attack_event_ids/0`。这只证明 exact bytes 下的静态 locator identity：

```text
event_34_preservation_basis =
  "static-rfc6901-copy-locator-resolution-only"
operation_execution_count = 0
reseal_execution_count = 0
judge_execution_count = 0
negative_projection_count = 0
```

它不证明 operation、reseal 或 judge 的运行结果。

## 5. Downstream invalidation 与 coverage

A1 改变 Base literal、operation literal 和相应 set roots，因此旧派生物必须全部
重建：

```text
downstream_invalidated =
  71-record-fixture-inventory-authoring
  56-record-negative-projection-audit
  12-record-base-parameter-audit
downstream_rebuild_required = true
```

测试先证明三项旧派生物在 four-pointer source 下有效，再分别把 source 换成 exact
A1 bytes；三个 byte-first joins 均 fail closed。这不是说新派生物已生成，恰好相反：

```text
negative_plan_rebuilt = false
negative_plan_complete = false
covered = [mandatory-to-variable]
uncovered = [intrinsic-to-mandatory,intrinsic-to-variable]
```

当前 56 条 negative recipes 只有 `N-T7-PROBE-AS-ATTACK` 覆盖
mandatory-to-variable。A1 纠正不能被误写为 negative-plan completeness。

## 6. Zero-authority report projection

Canonical audit 与三个公开 authoring reports 都镜像以下边界，避免只消费 report
的调用方把静态证明误读为执行或 promotion：

```text
normative_schema_count = 0
constructor_execution_count = 0
normalized_view_count = 0
base_materialization_count = 0
operation_execution_count = 0
reseal_execution_count = 0
judge_execution_count = 0
negative_projection_count = 0
provider_call_count = 0
outcome_read_count = 0
network_used = false
authority_scope = "none"
main_contract_eligible = false
golden_oracle_eligible = false
materialization_authorized = false
activation_authorized = false
```

Authoring module 的公开 API 只接受和返回 bytes/report，不接受路径，不提供 write、
execute、judge、provider、promotion 或 CLI entrypoint。

## 7. Verification

最终验证：

```text
targeted pytest:
  15 passed, 18 subtests passed

combined V2 authoring pytest:
  76 passed, 49 subtests passed

combined unittest:
  Ran 76 tests
  OK

Python 3.12 / 3.13 / 3.14:
  each ran the 15 T7 A1 tests
  OK

targeted Ruff:
  All checks passed

py_compile:
  passed

independent post-fix reviews:
  P0=0
  P1=0
  P2=0
  P3=0
```

测试使用 test-local frozen anchors，独立重算四个顶层 roots，递归严格区分
`false` 与 `0`、`true` 与 `1`，拒绝 A0、event 35、reorder、unrelated field、
stage/code、root、canonical-byte、state/promotion 和 unknown-key tamper。AST
防火墙使用 exact import/symbol allowlist，并检查 direct 与 attribute calls。

全 external lab 的既有 Ruff debt 不在本改动范围；这里只声明两个新增文件的 targeted
Ruff 通过，不声明整个 lab lint-clean。

## 8. Claim boundary 与下一顺序

本检查点证明：

- protocol-motivated A1 可从 exact four-pointer source 唯一复算；
- event 34 的 RFC 6901 locator identity 在该反事实中保持；
- A1 的 byte/root blast radius 和三项 downstream invalidation 可机读；
- authoring helper 在其声明边界内 fail closed、provider-free、zero-authority。

本检查点不证明：

- A1 已被选择为 final C1；
- profile/companion amendment 已发生；
- 六类 reusable constructor schemas/projections 已闭合；
- negative plan、Main、GoldenOracle、R0-R8、G2 或 G3 已完成；
- provider/LLM behavior；
- H1-H6；
- receptor-gated ligand field 优于 sparse communication、blackboard、
  retrieval routing 或 learned graph pruning。

下一顺序仍是 provider-free gate work：

1. 研究并分别冻结六类 exact schemas/projections/error precedence/traces；
2. 形成正式、原子的 A correction candidate，重建三项 invalidated artifacts 和缺失
   negative relations；
3. 独立生成 Main 与 GoldenOracle，完成 source freeze 和 R0-R8；
4. 重新资格化 G2/G3；
5. 只有 G0-G3 全部通过后，才允许读取新轮换 API key 并运行 provider canary。
