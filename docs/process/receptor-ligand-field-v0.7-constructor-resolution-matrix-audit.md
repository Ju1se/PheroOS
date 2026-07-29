# Receptor-Gated Ligand Field v0.7 Constructor Resolution Matrix Audit

## 1. 结论

本检查点把六类 Base constructor 的当前证据整理成一个 provider-free、
content-addressed 候选解析矩阵：

- environment；
- suite；
- replica pair；
- labels；
- source；
- process。

它没有关闭任何 reusable constructor schema 或完整 normalized-view projection。
它只封存“当前证据支持怎样的研究判断”，并将判断严格分为：

- `PROVEN`：exact source 或明确声明支持该判断；不代表 active normative contract；
- `DERIVABLE`：在全部显式输入给定后，纯变换有唯一结果；不代表输入或 materialized
  view 已存在；
- `OPEN`：缺少 machine leaf/evidence，或仍有多个相容设计；
- `CONFLICT`：同一 evidence layer 中，同一语义字段存在不相容的已绑定来源。

最终矩阵包含 90 条 globally unique claims：

| Family | PROVEN | DERIVABLE | OPEN | CONFLICT | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| environment | 6 | 3 | 6 | 0 | 15 |
| suite | 5 | 1 | 9 | 0 | 15 |
| replica pair | 4 | 1 | 9 | 0 | 14 |
| labels | 5 | 3 | 7 | 1 | 16 |
| source | 6 | 2 | 8 | 0 | 16 |
| process | 5 | 3 | 6 | 0 | 14 |
| **Total** | **31** | **13** | **45** | **1** | **90** |

唯一 `CONFLICT` 是：

```text
exact four-pointer source:
  T7 event 33 ∈ task_intrinsic_challenge_event_ids

active v0.6:
  T7 intrinsic universe = empty

draft v0.7 bridge:
  no estimand change
  intrinsic semantics inherit the v0.6 sidecar
```

字段名迁移本身不是 conflict。`intrinsic_challenge_event_ids` 与
`task_intrinsic_challenge_event_ids` 可以通过显式 rename projection 相容；当前只是
formal amendment 尚未选择，因此记为 `OPEN`。

## 2. 机器边界

固定 machine leaves 为：

```text
profile_activation_state =
  "v0.6-active-v0.7-draft-not-activation-ready"

candidate_instance_source_state =
  "unselected-t7-a1-counterfactual"

classification_author_reviewed = true
rule_source_locator_count = 0
semantic_entailment_proof_count = 0

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

因此，byte-first join 证明的是：

1. exact inputs 已绑定；
2. 当前 author-reviewed classification 已封存；
3. OPEN/CONFLICT blockers、zero-execution 与 zero-authority 边界无法被重新求根伪提升。

它不证明每条解释已经由 source paragraph 机器蕴含。Rule-level section/excerpt
locators、excerpt roots 和 semantic-entailment proofs 仍为零，必须在后续 schema
closure 前补齐。

这些零值属于本 63,776-byte audit 自身，后续 artifact 不得回写或替换它们。后续
[environment evidence overlay](receptor-ligand-field-v0.7-environment-evidence-overlay-audit.md)
、
[suite evidence overlay](receptor-ligand-field-v0.7-suite-evidence-overlay-audit.md)
与
[replica-pair evidence overlay](receptor-ligand-field-v0.7-replica-pair-evidence-overlay-audit.md)
分别以独立 sidecar 绑定 scoped locators 和 author reviews；原 audit 的
locator/proof counts 继续为零。三个 sidecar 也不能在没有独立 overlay-set
artifact 时声称 combined coverage，或把任一单体 global coverage 提升为完整。

## 3. Exact inputs

### 3.1 四份研究文档

| Document | Bytes | RAW |
| --- | ---: | --- |
| experiment profile v0.6 | 6,099 | `sha256:b1a7aa84664baacdf683af406aa4e88b118ef45b001986e7f438c5d31715a979` |
| experiment profile v0.7 | 119,802 | `sha256:bbea97c5c360853a12c00bf1983f07beb7eac8f401ad3adc8f3b433d84d270e6` |
| materialization plan | 44,724 | `sha256:e19f6caff36b79be3693855c77559d777277c065da77146624e23143cfd7ced9` |
| V2 closure design | 50,024 | `sha256:a462140f0a21880b479eb17e8acad0eb4e2349866210f2881de8685f769b21bb` |

Evidence-set root：

```text
sha256:8fde324923030f51aa2156151186af04b8b12a20c0decb3f0158007bceb7f2ca
```

### 3.2 T7 counterfactual chain

```text
four-pointer source:
  bytes = 62093
  RAW = sha256:93e62153972cc5db557ccb60c4f48ac52519e4271c3a7d59ffc9e6e5daa69795

unselected T7 A1 candidate:
  bytes = 62094
  RAW = sha256:3929670021f447c6f3c4f325be2db46f89809468a72428b57374bb93e80c035b
  fixture_input_set_root =
    sha256:6cce58e91e662c282def133b6c53962a67b5b400d24e7bac1aac7e6cbe58c6b1

T7 A1 audit:
  bytes = 6744
  RAW = sha256:b6736881bf1f996d261f3012b1eb902259d2ef870185b870eda219b414fdba92
  root = sha256:d6edfe1f1f9dd2b193b4d1b7b8802d6c5e8c0564731dca80f2df012aa0624b1a
```

A1 仍未被选择；旧 71-record inventory、56-record negative audit 与 12-record
Base audit 仍需在正式选择后重建。

## 4. Resolution audit anchors

External research branch：

```text
branch = codex/v07-materialization-v2-authoring
commit = f3af7f68ea6724942ceaf1c180b58c2a2017f07d

module SHA-256 =
  7c4d7c8df5334c35811dc7ad486e94a68b4517cce9da4d0acb4da12e07016f97

test SHA-256 =
  273f3d6d3f764a0a43e773e8a6c7fe2826d164dba05180fcfd1566c9c8a05cc3
```

Generated audit：

```text
bytes = 63776
RAW =
  sha256:448be7156c0640c46c6f83f6efe2b5568acbb4663b75d3107e85b344f63def3d
audit_root =
  sha256:c1b3b94ff07221a953c7373f77465f28f0f39df86cb1efd05dd19c4a12557669
record_set_root =
  sha256:f8c6c5d1e72ed6fa9d40bf7089feca1e444abc6141a09b87f46736c80e17c20c
```

| Family | A1 candidate instance-set root | Resolution record root |
| --- | --- | --- |
| environment | `sha256:81240ee9d65b0b33b9ed2cba01e4a3a8c7b4dbedde7074181210cd3754365e38` | `sha256:044cd4dc4de3e5ff61b08fe4b53a66e1ca94a1abdbedaee2f3121c43a9be28ca` |
| suite | `sha256:b2d9c72945d24516f190bb6c2348249af08aada7fac154575c3f331c62dedaf6` | `sha256:fcd3d3fd607588aed9364b96c81054c3cb341eb5b9a7af059cc4d2b84298fd97` |
| replica pair | `sha256:82439d51a80f09faaff4045930804e74a761f64c3fedd4d3e778c6072e230e96` | `sha256:ec996571c2f572b9af88ba85b764dba12084de3390f2dc7f9158276adab0a629` |
| labels | `sha256:f9b329fc7cf5b3e50607f2424736bdaaa103ff61bfb5c6ee52b6debff2ff124a` | `sha256:71e2af3121b755b7eb200da752d5941bc1749be22d4c2b59a36901f706078c29` |
| source | `sha256:8a0182441de5ac72e1ce18bccdc6f61f3e9c3424645adfb860d012db7770f048` | `sha256:7c55170c42169f805f054e1717aecc1736daf29aa919382f36c883ab4c8c60e7` |
| process | `sha256:4d4f3bb94d464d5a010fc37e36f85605949b0ac60704b1fb39cf4913441a5f26` | `sha256:1cc9b1f81814b91c06204336c53c52fa1c57450d39720e457b1536dd68125504` |

## 5. 六类结论

### 5.1 Environment

已支持：

- six-key literal shape 与 runtime `7×5×2×2=140` domain；
- five exact `(agent_count,event_count)` pairs；
- full config 中的 declared literals；
- parameter copy、T4 `fixture_mode` 和完整 config 后的 environment-key derivation；
- review-seven 与 runtime-140 invocation scope 必须分离。

仍开放：

- 两个 dependency roots 的 exact sealing context；
- source-bound actual artifact 与 source-neutral fixture view 采用 dual layer 还是
  full re-chain；
- raw NDJSON preimage；
- receiver/event/job/step/directive/failure/terminal/unrevealed-edge 的 all-field
  map-to-view projection；
- constructor preflight codes、trace leaves 和 exact roots。

### 5.2 Suite

已支持：

- 140 declarations、七 arms、980 zero-execution/zero-authority bindings；
- coverage 必须先于 guarded sequence。

仍开放：

- 旧矩阵虽把 ordinal formula 标作 `DERIVABLE`，但 bound profile 只证明
  `140 * 7 = 980`，不能推出 row-major
  `environment_ordinal * 7 + arm_ordinal`；该项现由 suite sidecar 明确标作
  source-unsupported conditional candidate；
- exact v0.5 arm-order source 尚未进入本 evidence set；
- `intent_id` preimage/collision rule；
- producer replica namespace 与 semantic-vs-construction placement；
- 980-record storage shape；
- 140-config inventory construction/sealing context；
- trace 与 preflight precedence。

### 5.3 Replica pair

已支持：

- current A-then-B literal direction；
- proposed view 只涉及两组 review-seven projections，不是两次 runtime-140 execution；
- B-side mutation exact target；
- root/chain/filename integrity 先于 `E-AB-BYTE-MISMATCH`。

仍开放：

- replica namespaces、generic distinctness rule 与 pair symmetry；
- copy/reference/re-chain storage；
- source-neutral semantic equality 与 actual artifact/manifest equality 的双层 envelope；
- exact trace、sealing context 与 preflight precedence。

后续 replica-pair sidecar 已为 14/14 rules、23/23 source-ref edges 绑定 41 个
locators，但明确记录其中七条 target propositions 含 bound source 无法推出的作者
合成。尤其 `PAIR-PROJECT-TWO-BY-SEVEN` 只保留 frozen `DERIVABLE` 名称，
`derivation_ast=null` 且未 replay；`PAIR-OPEN-ACTUAL-EVIDENCE` 只由当前
zero-actual counts 与 absence review 支持 OPEN 边界。这些 provenance 进展不关闭
上述 schema、projection、storage 或 actual-evidence 问题。

### 5.4 Labels

已支持：

- active v0.6、draft v0.7 bridge 与 exact four-pointer source 之间的真实 membership
  conflict；
- unselected A1 的 intrinsic empty、mandatory 33/34、variable empty；
- mandatory IDs derivation；
- mandatory/variable/sealed direct copies；
- selected amendment 后的 intrinsic rename-copy；
- pairwise disjointness。

仍开放：

- formal A selection 与 versioned field-name amendment；
- label episode 到 environment Base 的 all-field join；
- intrinsic-to-mandatory 和 intrinsic-to-variable 两个 negative fixtures；
- downstream inventory/audit rebuild；
- trace 与 internal preflight precedence。

### 5.5 Source

已支持：

- exact seven declaration-order records；
- current modes/strings；
- NFC/frame predicates 与 Unicode permutation `[1,0,2,3,4,5,6]`；
- synthetic source fixture 与 actual Git/runtime evidence 必须分层；
- source-stage public precedence。

仍开放：

- generic path/mode/frame/AST policy；
- frozen Python grammar、interpreter identities 与 execution receipts；
- path-keyed view 与 sorted-pair root preimage 的 exact mapping；
- order witness schema；
- actual Git source freeze 和 loaded runtime identity；
- trace 与 constructor preflight precedence。

### 5.6 Process

已支持：

- exact 13 synthetic literals；
- current strict-base64/count fact；
- declared synthetic RSS source mapping；
- current baseline/peak/delta `1/2/1 MiB` 与 elapsed `1 ns` derivation；
- synthetic transcript 不能替代 actual Observation；
- resource-stage order 与 RSS/OOM/crash guards。

仍开放：

- reusable range/nullability/exit/base64/frame/count/clock/wait4 schema；
- exact synthetic transcript/measurement view 与 roots；
- total timeout/partial predicates；
- actual ObservationV07、OS receipts、source/process identity 与 judge-input selection；
- trace 与 preflight precedence。

## 6. Verification

最终 provider-free verification：

```text
targeted pytest:
  12 passed, 15 subtests passed

six V2 authoring modules:
  88 passed, 64 subtests passed

combined unittest:
  Ran 88 tests
  OK

Python 3.12 / 3.13 / 3.14:
  12 resolution-audit tests per interpreter
  OK

targeted Ruff:
  All checks passed

py_compile:
  passed

git diff --check:
  passed

independent code review:
  P0=P1=P2=P3=0

independent semantic review:
  P0=P1=P2=P3=0

independent tamper review:
  P0=P1=P2=P3=0
```

Tamper review 在重新计算所有可见 roots 后拒绝：

- 任一 family instance root 替换或跨 family swap；
- 删除 OPEN、重分类 rule 或删除 four-pointer conflict reference；
- unknown/duplicate source refs、duplicate rule IDs 或空 blocker；
- normative/schema/projection/execution/observation/provider/network/authority 假提升；
- report boundary fields 假提升；
- same-length document、four-pointer 或 A1 source 替换。

后续 environment overlay 在 external commit
`ea73fe1add86529884adbf0ece7f6622fe4e3fa9` 上完成：

```text
environment rules = 15 / 15
source-ref edges = 20 / 20
locators = 26
global rules covered = 15 / 90
global_rule_coverage_complete = false

overlay bytes = 55432
overlay RAW =
  sha256:76eb5d9d7c613fe5c7ace130837bd0eb0fa50d67cc3d235fbe524bd7662bd5f6
overlay root =
  sha256:abb8c6eee795b8dc1076d0f35c5289e615988ba790e813af0e6c2abe5c5b273c
```

它将 20 条 environment source-ref edges 定位到 exact Markdown/RFC 6901/absence
review domains，但 machine/normative semantic proof、schema、projection、
execution、materialization 与 observation 的相关 counts 仍为 0，
`network_used=false`、`authority_scope=none`。尤其 strict-integer bound source
不蕴含 Python `type(value) is int`；详情见独立 overlay audit。

后续 suite overlay 在 external commit
`5a9f9f8500aeafb8655692adcb3610bf99cc7e69` 上完成：

```text
suite rules = 15 / 15
source-ref edges = 22 / 22
locators = 25
global rules covered = 15 / 90
global_rule_coverage_complete = false

overlay bytes = 54745
overlay root =
  sha256:792829d3cf1fd4989f7d7f5f3b00aecc61b8ce030f1e8934e3f32f888c0f693b
```

它把四条 source-unsupported propositions 与 unresolved/report policy 绑定，但没有
生成 suite schema、980 records、execution 或 authority。

再后续 replica-pair overlay 在 external commit
`00e6ba609ee8cda617004a503741f108c0b8b70c` 上完成：

```text
replica-pair rules = 14 / 14
source-ref edges = 23 / 23
locators = 41
global rules covered = 14 / 90
global_rule_coverage_complete = false

overlay bytes = 69838
overlay root =
  sha256:953c8abc4629415fbfcb53405bd2d92caa722a968f9c256e0a3bfdf57517013b
```

它固定 4 `PROVEN`、1 `DERIVABLE`、9 `OPEN` 与 7 条
source-unsupported propositions；proof/schema/projection/execution/
materialization/provider/outcome/authority 仍为零/false/none。三个 sidecars 相互
独立，没有 content-addressed overlay-set，因此这里不发布 `44/90` combined
coverage。

在隔离 authoring branch 上运行旧 frozen qualification 时，Q exact-rebuild 会拒绝：

```text
tests/test_baseline_qualification.py::
StrongBaselineQualificationTests::
test_builders_replay_frozen_canonical_artifacts

ValueError:
  frozen artifact differs from builder: q-bm25-golden-v1.json
```

Frozen qualification 绑定 canonical active lab commit `2f1d473a6edb9fba61ccfa39d7214b0d688e44d7`
的 source-tree root
`sha256:9e3b1884fce7185e910b1d953c0ab1c1c7e690791e9ced2396429cb410352061`。
在 resolution module 出现前，authoring parent
`d6e4d05c0b7db80b802394091de32efc11c929ba` 的 source-tree root 已是
`sha256:2a9907610d4ab19d83bb39e26038b3fcc019d90bed3dde09c3f48bc3928b0710`；
`f3af7f68ea6724942ceaf1c180b58c2a2017f07d` 又变为
`sha256:10f044bd978270b0dedcf232995b13859c059cad0fe48344f10c0f4291e28eb0`。

因此该 refusal 是隔离 authoring branch 改变 source identity 后按设计发生的 frozen
qualification invalidation，不是 active-baseline defect，也不是 resolution/overlay
module 引入的行为回归。Canonical lab 的 frozen qualification 继续以 `9e3b...` 为准；
不得在 authoring branch refreeze baseline artifact 来掩盖隔离。同一 exact-rebuild
test 的最终配对复现是 canonical `2f1d473` `1 passed in 48.96s`，authoring
`ea73fe1` 按预期 `1 failed in 49.02s`。

## 7. 对实验结论的影响

本检查点没有生成任何 RG-LF、sparse communication、blackboard、retrieval routing
或 learned graph pruning 的观测。

所以当前严谨结论仍是：

> receptor-gated ligand field 是理论动机较强、已形成可证伪 H1–H5 的候选架构；
> 尚无证据证明它优于稀疏通信、黑板、检索路由或学习式图剪枝。

当前矩阵只减少 constructor research 中“哪些事实已支持、哪些设计仍开放”的混淆，
不降低 G2/G3 NO-GO，不授权 provider key，不开始 Main/Golden/R0-R8，也不产生科研
结果。

## 8. 下一 provider-free 顺序

1. Environment、suite 与 replica-pair 的独立 scoped locator/review slices
   已完成；以同样边界依次覆盖 labels、source、process。原 audit locator/proof
   count 与所有 machine/normative semantic proof count 继续为零；没有
   overlay-set artifact 前不得声称 combined global coverage。
2. 依次解决 environment 的 source-neutral/re-chain 与 all-field projection。
3. Suite 的 evidence locations 已绑定，但仍需新增 normative arm-order、
   intent-ID、storage 和 sealing-context contract；sidecar 不能代替这些 contract。
4. 冻结 replica namespaces、symmetry、storage 与 dual-evidence envelope。
5. 只有在正式选择 A 后，执行 label amendment、补两个 negatives 并重建三项
   downstream audits。
6. 冻结 source map/root projection 与 process reusable schema；actual Git/runtime/
   Observation evidence 继续保持独立阶段。
7. 六类 schema/projection 经独立实现与 tamper review 后，才可进入 Main contract 与
   GoldenOracle authoring。
8. G0–G3 全部正式通过前，不读取或配置任何 LLM API key，不调用 provider，不开始
   R0–R8。
