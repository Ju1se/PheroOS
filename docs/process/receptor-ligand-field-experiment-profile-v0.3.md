# Receptor-Gated Ligand Field Experiment Profile v0.3

状态：active G1-G3 qualification amendment；先于任何 outcome-bearing arm；
不构成 H1-H6 结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

被取代的执行 profile：
[v0.2](receptor-ligand-field-experiment-profile-v0.2.md)

首次资格验证：
[G0-G3 Qualification Report](receptor-ligand-field-g0-g3-qualification-report.md)

## 1. Change control 与 outcome firewall

v0.3 只修复第一次 G0-G3 资格验证暴露的可执行性、对照保真度和标签泄漏问题。
形成本 amendment 前：

- 没有执行 provider request；
- 没有读取 sealed outcome sidecar；
- 没有运行 full smoke、pilot 或 confirmatory arm；
- 只查看了 contract validation、determinism、exception、hash、ACL/authority 和
  baseline-fidelity diagnostic；
- `hypothesis_conclusions` 为空。

因此本次修订不是根据 RG-LF 的 success、cost、robustness 或 H1-H6 结果调参。H1-H6、
estimand、MESI、统计规则、task split、seed range、共同预算、claim gate 和
protocol-core baseline 均不改变。v0.2 保留为历史记录；本文件未明确替换的条款继续适用。

## 2. Manifest-declared universe

External `EpisodeManifestV1` 必须在 controller 看到事件前规范声明：

```text
declared_subjects
declared_candidates
ligand_topologies[8]
environment_parameters
```

这些声明必须由 `task_id/split/seed/repeat/size/attack profile` 和公开 environment
specification 生成，不能扫描 future event payload、tag、candidate choice 或 sidecar
outcome 后反推。

每个 subject declaration 绑定：

```text
tenant_id, scope_ref, acl_digest, is_public, subject_id
```

Field ID 和 subject-node ID 使用带 schema 的 canonical JSON digest；禁止用裸分隔符拼接。
Manifest 必须拒绝：

- event 引用未声明 subject 或 candidate；
- topology 引用未声明 node；
- tenant、scope、ACL 或 public partition 之间的 edge；
- 少于或多于八种 ligand；
- 同一 ligand/source/destination 重复 edge；
- 非有限、非正、超过 `1` 或超过 q12 精度的 weight；
- 每 source row 质量不精确等于 `1.000000000000`；
- 每 source/ligand 多于四条 outgoing edge。

为读取旧 engineering fixture，可以接受空 universe/topology；其唯一语义是 self-only、
零跨 subject 传播，并必须记录：

```text
topology_qualified=false
topology_mode=fail_closed_self_only
environment_qualified=false
```

空声明不能通过 R-G3，也不能进入 outcome-bearing arm。

## 3. Eight-ligand topology

显式 topology 仍遵循 v0.2 的八种语义：

| ligand | declared relation |
| --- | --- |
| utility | artifact/task dependency |
| failure | reverse dependency |
| hazard | safety-scope relation |
| uncertainty | evidence-subject relation |
| novelty | unexplored-neighbor relation |
| congestion | workstream relation |
| recruitment | capability relation |
| contradiction | claim/reference relation |

每个 row 先按 `(-declared_edge_weight,destination_node_id)` 选择最多四条，再用
Decimal q12、half-even 规范化为 row-stochastic。R 只能消费 manifest 中的八张图；
禁止从 event tag、payload、candidate overlap 或完整 episode suffix 动态推图。

G3 fixture 至少证明：

1. utility 的 `A -> B` 传播方向与 failure 的 `B -> A` 相反；
2. 未声明 edge 不传播；
3. 修改未来 payload/tag 不改变 prefix field；
4. tenant/scope/ACL partition 不互相影响；
5. universe/topology 的输入顺序不改变 manifest root；
6. delimiter-adversarial ID 不发生结构碰撞。

## 4. `P` scalar comparator amendment

### 4.1 Hybrid Replay v2 pressure projection

Hybrid Replay v2 source proof 是 tokenless durable proof，不能调用要求 legacy
process-local token 的 `derive_attention_breakdown(source.source_step)`。v0.3 将该调用替换为
外部、只读、零 authority 的：

```text
pheroos-v2-attention-pressure-projection-v1
```

它只能读取 v2 `source_step` 中 public active trails、scores 和 score breakdown，数值定义与
v0.2 相同。输出必须命名为 `pressure_projection_root`，不得冒充 core
`attention_root`。Lineage 同时绑定：

```text
value_root, context_root, source_step_root,
domain_root, scope_ref, run_ref, current_step
```

G3 differential fixture 必须覆盖全部 trail kind、正负号、同 kind 抵消、subject/candidate
fallback 和边界强度，并逐字段等于 public legacy projection 在可签发 legacy token 的同输入
fixture 上的数值。Projection 仍不得增加外层 decay、source cap、diversity、kind 或 receptor
weight。

### 4.2 Prefix causality

`P` 的 candidates 和 route subjects 只能来自 manifest-declared universe。Route ID 使用
canonical JSON digest，绑定 subject、candidate、tenant、scope 和 ACL partition；禁止从
完整 future event list 建 manifest 或 topology。

### 4.3 Durable diffusion blocker

当前冻结 Hybrid Replay v2 对长生命周期、跨 edge 的 decayed receipt 在第二步 fail closed：
相同 receipt ID 对应变化后的 payload 会触发 replay mismatch。v0.3 不通过删除 diffusion、
每步换 ID、改用 deprecated legacy evaluator、全历史重算或外部近似来伪造“当前 PheroOS”
强基线。

在以下任一方案完成版本化、迁移、Trace、Conformance 和 differential fixture 前，`P`
保持 G3 blocked：

1. protocol-core 发布明确的新 replay contract；或
2. 独立 reference semantics 被证明与完整 Hybrid Pheromone ABI 的多步输出等价，并与
   runtime cost 分开报告。

任何 self-only/no-diffusion 诊断必须使用不同 arm ID，不能标为 `P`。

## 5. Ground-truth label firewall

Controller-visible `tag`、subject/candidate ID、payload、ligand dose 和 environment metadata
不得直接包含 `true`、`false`、`correct`、`relevant`、`attack-success` 等 outcome label。
正确性、relevance、attack identity 和 expected affordance 只存在 sealed sidecar。

Provider-free fixtures 至少使用：

- T3：true/false alarm 对 controller 都是中性 `hazard-signal`；mitigation 是中性
  `mitigation-receipt`，真假与 deadline 只在 sidecar；
- T4：relevant edge 只由 required `capability:*` 与 receiver capability 决定，公共
  `task:t4` tag 不得让所有 label 变为正类；
- T5：公开 `reference-chain/hop` 只描述结构，不声明 relevance；knowledge update 必须
  引用同 subject 的 superseded evidence；
- T6：公开 `minority-hypothesis/dominant-hypothesis` 不声明正确性；最后 20% 是独立
  verification receipt chain，相关性只在 sidecar；
- T7：公开 `tenant-local-evidence` 不声明正确性；cross-tenant canary 和 mandatory probe
  与 severity attack budget 分开。

Oracle diagnostic 是唯一可在 controller-like ranking 中读取 sidecar 的 arm。它必须标为
`diagnostic_only=true`、`sealed_sidecar_read=true`、无 Commit authority，且不得进入
H1-H6 比较。普通 `F/P/S/B/Q/G/R` 均不得读取 sidecar。

## 6. G1 research event 与 diagnostics

G1 使用闭合、版本化的 `ResearchEventV1`。每条 replay-stable event 必须绑定：

- run/code/prereg/controller/dataset/RNG identity；
- actor/principal/role/tenant/scope/ACL 和 zero-authority；
- evidence、lineage、cluster 和 failure domain；
- 完整 eligible/selected/dropped partition、payload order 和每条 reason；
- 八 ligand 的 dose、decay、diffusion、adaptation、normalization；
- deterministic token/byte/storage/call/operation cost；
- outcome 字段或明确 `not-evaluated/not-authorized`；
- upstream trace root 和 sidecar-read flag。

Schema 必须拒绝 unknown field、NaN/Infinity、authority escalation、破损 partition、
非 canonical NDJSON、重复 event ID、非连续 sequence 和 hash-chain tampering。

Wall、CPU、latency、peak Python allocation 和 RSS 使用独立 observation schema，绑定 trace
record root，但明确不进入 replay root。

G1 同时冻结两个同预算 diagnostics：

- sealed oracle top-k：relevant edge 优先，再按 event ID；
- seeded random top-k：
  `SHA256(episode|receiver|event|seed)`，再按 event ID。

两者必须 fresh-process byte-exact replay、zero authority，并从 hypothesis claims 排除。

## 7. Strong baseline qualification

### 7.1 `Q`

Q golden reference 必须是独立实现，不能 import controller 的 tokenizer、BM25、Jaccard 或
ranking helper。Fixture 覆盖 NFC、case、Latin regex、CJK code point、repeated query term、
zero-match、age、role、capability、exact subject、tie 和 active-version filtering。Controller
与 golden 逐 event q9 score、排序和 top-k 完全相同后才可 qualification。

### 7.2 `S`

S 的三张候选图只由 manifest/environment declaration 构造，不能读取 payload、future
event content 或 test/smoke sidecar。`d` 仍由 dev-only R mean selected receiver
out-degree 冻结；candidate selection 使用 v0.2 的 relevant-edge recall、task success、
edge count、bytes、graph name 顺序。Artifact 绑定全部 dev roots、候选图 roots、degree、
metric vector、winner 和 tie-break。

### 7.3 `G`

G 必须使用 v0.2 完整 grid：

```text
3 learning rates * 3 l2 * 2 epochs * 3 native_k = 54
```

每个 T1-T7 task family 使用 train `1000..1029` 和 dev `2000..2029`；test、smoke、pilot、
confirmatory 或 provider data 不得参与。Decimal context 固定 precision `34`、
`ROUND_HALF_EVEN`，full-batch canonical order，无 BLAS 并行。每个 checkpoint 绑定：

```text
train roots, dev roots, feature allowlist,
S frozen edge root, full grid, all dev metrics,
selection rule, weights, native_k, training cost, checkpoint root
```

任一 task family 没有正负 train/dev label、读取禁止 split、缩小 grid/seed 或缺失 cost，
都保持 G3 blocked。

## 8. Cost completeness

Deterministic ledger 至少分开记录：

```text
eligible/selected events and bytes
prompt/completion/reasoning/cached tokens
controller operations
index build/query
graph build/read
state serialization/hash
storage reads/writes/bytes
P Store/replay
B append-only history
Q rebuild/tokenize/query
S frozen graph
G train/inference/checkpoint and amortized training
R field/diffusion/receptor
model/tool calls, retries, timeout and partial work
trace bytes
```

缺失值不能写成零；必须使用 explicit `not_applicable` 或阻断 qualification。Wall、CPU、
allocation 和 RSS 进入 observation，不进入 replay root。Natural、iso 和 sweep 均报告
controller cost；shared generator/common eligibility/sealed evaluator/NDJSON flush 分账。

## 9. Provider canary correction

Provider canary 仍只在 G1-G3 全部通过后运行。冻结配置：

| provider | base | model | output parameter | reasoning |
| --- | --- | --- | --- | --- |
| MiniMax CN | `https://api.minimaxi.com/v1` | `MiniMax-M3` | `max_completion_tokens=128` | `reasoning_split=true`，不保存 reasoning |
| Zhipu CN | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` | `max_tokens=128` | `thinking.type=disabled` |

共同参数：

```text
temperature=0.2
non-streaming
request timeout=120 s
max attempts=3
```

只有 `429`、冻结的 `5xx`、overload 和 network timeout 可重试；尊重不超过 60 秒的
`Retry-After`，否则使用 `1/2/4 s` full jitter cap。认证、余额、权限、参数、内容安全、
invalid JSON 和 schema failure 不重试。

每次 attempt 必须保留 sanitized status、HTTP category、latency 和 cost。最终记录必须包含
requested/returned model、request ID、finish reason、usage、usage completeness、attempt
count、final content digest 和 MiniMax `/models` capability digest。Returned model 不等于
requested model时 fail closed，不静默 fallback。

凭据只从新轮换后的：

```text
PHEROOS_MINIMAX_API_KEY
PHEROOS_ZHIPU_API_KEY
```

读取。任何出现在聊天中的 key 都视为已暴露，不得使用。

## 10. Gate consequences

v0.3 生效后重新验证 G0 artifact hashes 和 external source-tree root。Gate 只可由可执行
evidence 升级，不能根据本文件文字升级：

- G1：typed log、oracle/random、fresh-process replay 和 zero-authority 全部通过后才通过；
- G2：T1-T7 neutral-label environment、显式 universe/topology、完整 smoke/attack/scale
  counterfactual matrix 和 ACL invariants 全部通过后才通过；
- G3：Q/S/G/R/cost 全部 qualification，且 `P` durable multistep blocker 被合规解决后才通过。

在 G1-G3 全部通过前，full smoke、provider canary 和 pilot 继续 fail closed。
