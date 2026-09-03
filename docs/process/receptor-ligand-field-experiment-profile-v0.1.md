# Receptor-Gated Ligand Field Experiment Profile v0.1

状态：G0 执行冻结候选；先于 experiment harness 实现；不构成实验结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Receptor-Gated Ligand Field Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

## 1. 适用范围和结论限制

本 profile 冻结第一轮 `G0` 至 `G3` provider-free qualification 和付费 provider
canary 的实现自由度。它不冻结 `G4` pilot 后才可估计的 confirmatory sample size，也不允许
对 H1 至 H6 作支持性结论。

本轮只允许得出：

- wire contract、replay、ACL 和 authority 不变量是否成立；
- T1 至 T7 generator 是否按冻结规则运行；
- F/P/S/B/Q/G/R 是否达到预声明的 baseline fidelity；
- 成本日志是否完整；
- MiniMax CN 和 GLM CN adapter 是否能在冻结模型上完成 canary。

若本 profile 与上位预注册冲突，以上位预注册为准。任何 profile 变更必须形成新版本并说明是
在查看哪些 arm 标签或结果之前发生；不得原地改写已产生数据所绑定的版本。

## 2. 冻结顺序和 artifacts

执行顺序固定为：

1. 提交上位预注册和本 profile；
2. 生成 `prereg.lock.json`，绑定 Git commit、两份文档、TCK、Hybrid Replay manifest；
3. 才可实现独立 external harness；
4. 先运行 contract tests，再运行 deterministic smoke；
5. baseline qualification 通过后才允许 provider canary；
6. G4 pilot 只能使用 `pilot` split，不能读取 `confirmatory` sidecar。

External harness、provider adapter、模拟器、learned-pruner training、scheduler 和结果数据库不得
进入 PheroOS protocol-core。Core 分支只保留预注册、未来稳定的 provider-free contracts、
vectors、Conformance 和研究证据索引。

## 3. Canonical input 和输出合同

### 3.1 `CanonicalEventV1`

所有 controller 只接收相同的 canonical event，至少包含：

- `event_id`、`parent_event_ids`、`sequence`、`logical_time`；
- `actor_id`、`principal_id`、`role`、`tenant_id`、`scope_ref`；
- `eligible_receiver_ids` 和 ACL digest；
- `subject_type`、`subject_id`、`candidate_id`；
- `evidence_ref`、`evidence_version`、`evidence_status`、payload digest；
- asserted/verified independence cluster、failure domain；
- `kind`、`strength`、公开 tags、supersession/retraction references；
- canonical payload bytes 和 deterministic token estimate。

Controller 不得接收 relevance label、正确 candidate、attack success、sealed true cluster 或
ground-truth sidecar 内容。

Eligibility 在任何评分之前统一计算。一个 event 只有同时满足以下条件才 eligible：

1. receiver 在 `eligible_receiver_ids`；
2. tenant 相同，或 event 显式标为 public；
3. receiver grant 包含 `scope_ref`；
4. evidence status 为 `verified` 或 `superseding`；
5. digest、version 和 supersession chain 通过 common validator。

不满足 eligibility 的 event 不得进入 controller state、index、field、training feature 或
model-visible payload。

### 3.2 `ControllerContextV1`

Context 固定包含：

- episode、task、split、seed 和 logical step；
- receiver role、capabilities、tenant 和 grants；
- 按 `(logical_time, event_id)` 排序的完整 eligible event 集；
- budget regime、event cap、token cap 和 deadline；
- controller config hash 和 prior-state root。

### 3.3 `PerceptBundleV1`

每个 controller 必须输出：

- receiver 和按 `(-quantized_priority, event_id)` 排序的 selected events；
- 每项 priority、reason、evidence ref 和可逆 affordance；
- eligible、selected、dropped 的精确 partition；
- token/byte/event/storage/operation budget usage；
- controller/config/prior-state/new-state roots；
- selection lineage root；
- `authority_scope="none"`；
- `commit_authority=false`。

Priority 在排序前使用 half-even 规则量化到 `1e-9`。完全相同的 priority 用 `event_id`
升序决定，不允许依赖 map iteration、wall clock 或并发完成顺序。

## 4. 预算制度

Provider-free payload token estimate 固定为 `ceil(canonical_utf8_bytes / 4)`。真实 provider
轨优先使用响应 `usage`；缺失时标记 `usage_complete=false`，不得用估算值伪装官方计费量。

### 4.1 Natural-cost

- `F` 传递所有 eligible events；
- `P/S/B/Q/G/R` 按各自冻结停止规则选择，默认 event cap `8`；
- 所有实际 token、edge、read/write、operation 和 latency 仍完整计量。

### 4.2 Iso-budget

所有 arm 每 receiver/step 同时受限于：

- event cap `8`；
- model-visible payload cap `512` estimated tokens；
- retrieval cap `8`；
- model call cap `1`；
- tool call cap `1`。

按排名顺序装入；首个超预算事件 dropped，并继续检查后续较小事件。不得通过只选择短事件取得
未计量优势，报告中同时给 event recall 和 token-normalized recall。

### 4.3 Budget sweep

以同一 episode 的 `F` eligible payload token 为分母，固定比例：

```text
0.10, 0.20, 0.35, 0.50, 0.75, 1.00
```

每点 token cap 向下取整但至少为一个最小 canonical event；event cap 等于 eligible event
数量。Frontier 之外不得事后插入更有利的预算点。

## 5. Controller v0.1

所有 score 只使用 common-visible metadata。所有 controller 在统一 eligibility gate 之后运行。

### 5.1 `F` full communication

Natural-cost 下按 canonical order 选择全部 eligible events。Iso/sweep 下使用相同 canonical
order 执行统一 truncation。其 priority 固定为：

```text
priority_F(e) = 1 / (1 + max_logical_time - e.logical_time)
```

这只决定预算不足时的稳定顺序，不引入内容 ranking。

### 5.2 `P` current scalar PheroOS

`P` 必须调用冻结的 Hybrid Replay v2 attention-only path，而不是重新实现一个相似公式：

```text
evaluate_hybrid_collective_step_v2(..., attention_only=True)
```

Canonical event 按固定映射形成 Scout/Recruitment/Inhibition/Pheromone input；映射表必须逐字段
进入 config hash。Hybrid 输出的 subject pressure 映射回同 subject 的 events，event 内使用：

```text
priority_P(e) =
  subject_pressure(e.subject) *
  recency(e) *
  min(1, source_cap / same_source_event_count)
```

其中 `recency(e) = exp(-ln(2) * age / declared_half_life)`。Receiver metadata 只用于 eligibility，
不增加额外 receptor score。G3 必须用固定 fixture 对外部 adapter 与冻结 PheroOS output
逐字段比对。

### 5.3 `S` static sparse

只允许三类 content-independent 候选图：

1. declared task-dependency edges；
2. sender capability 与 receiver capability 相交；
3. seed-fixed random-regular graph，degree `ceil(sqrt(agent_count))`。

Train/dev 上以 `relevant-event recall` 最大化选择图；约束平均 directed density 不超过
`ceil(sqrt(N)) / max(1, N - 1)`。平局依次选择 edge 少、serialized bytes 少、名称字典序小者。
选择结果在 pilot 前冻结。Test/OOD 不得根据内容或结果更新边。

进入 frozen edge 的 events 使用 `F` 的 recency priority；没有 edge 的 event 直接 dropped。

### 5.4 `B` strong scoped blackboard

Blackboard 是 append-only、versioned、ACL-scoped。每个 logical step 执行一次 read。旧 version
保留在 storage cost 中，但 superseded/retracted version 不进入 model-visible ranking。

```text
status(e)  = 1 if superseding else 0
kind(e)    = 2 if alarm/correction else 1 if inhibition/novelty else 0
version(e) = e.evidence_version / max_visible_version_for_subject
recency(e) = 1 / (1 + age)

priority_B(e) =
  4 * status(e) + 2 * kind(e) + version(e) + recency(e) + 0.1 * e.strength
```

Blackboard 不得读取 sealed truth；所有 append、supersession lookup、ACL read 和 payload
dereference 均计入成本。

### 5.5 `Q` stateless retrieval router

每次 step 从零开始，不保存 field、receiver history 或 habituation。Index 只包含 eligible
event 的 subject、公开 tags、role/capability metadata 和 canonical payload；build 与 query
成本必须记录。

```text
tag_overlap  = Jaccard(event.tags, receiver.capabilities U {receiver.role})
subject_term = stable_hash_similarity(receiver.query_subjects, event.subject)
recency      = 1 / (1 + age)

priority_Q(e) =
  0.45 * tag_overlap +
  0.30 * subject_term +
  0.15 * recency +
  0.10 * clamp(e.strength, 0, 1)
```

Hash similarity 使用 SHA-256 前 64 bit 映射到 `[0,1]`；Python `hash()` 被禁止。

### 5.6 `G` learned graph pruning

`G` 是 per sender-receiver-event edge 的 logistic ranker，只允许以下 feature：

- tag overlap；
- role/capability match；
- normalized recency；
- public strength；
- evidence status；
- normalized version；
- asserted/verified cluster 是否为 receiver 当前窗口新 cluster；
- `S` frozen edge indicator。

禁止 event text embedding、provider hidden state、ground truth、test statistics 和 receiver
私有 memory。训练 label 只来自 train sidecar 的 relevant edge。

超参数网格固定为：

```text
learning_rate = 0.01, 0.05, 0.10
l2            = 0, 0.001, 0.01
epochs        = 25, 50
```

优化为按 canonical edge order 的 deterministic batch gradient descent。以 dev macro-F1
选择 checkpoint；平局依次选择训练 operations 少、L2 大、learning rate 小、epochs 小者。
Checkpoint 必须记录 train/dev manifest roots、feature allowlist、weights、training
operations、wall time 和 hash。Pilot/test/OOD 期间不得更新。

### 5.7 Diagnostics

`oracle top-k` 按 sidecar relevance 后再按 event ID 选择；`random top-k` 使用
`SHA-256(episode_id | receiver_id | event_id | seed)` 排序。二者不进入 H1-H6 优越性比较。

## 6. `R` receptor-gated ligand field v0.1

### 6.1 Ligand 和 receptor

Ligand 顺序冻结为：

```text
support, novelty, alarm, correction, inhibition, dependency
```

Event dose 由 `kind` one-hot 与公开 tags 决定。Base dose 为 `clamp(strength, 0, 1)`；
`superseding` 额外加入 `0.5 * correction`，但每维最终 clamp 到 `[0,1]`。

Receiver receptor weights：

| role | support | novelty | alarm | correction | inhibition | dependency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| verifier | 0.8 | 0.6 | 1.0 | 1.2 | 1.0 | 0.5 |
| coordinator | 1.0 | 0.7 | 1.0 | 1.0 | 0.9 | 1.1 |
| explorer | 0.6 | 1.2 | 0.8 | 0.9 | 0.6 | 0.8 |
| operator | 0.8 | 0.5 | 1.2 | 1.0 | 1.0 | 1.0 |

Capability match 乘数为 `1.0 + 0.25 * Jaccard(event.tags, receiver.capabilities)`。ACL gate
先于 ligand dose 和 field update。

### 6.2 Field update

Half-life 按上述 ligand 顺序固定为：

```text
8, 4, 2, 6, 3, 8 logical steps
```

对 receiver `r`、subject `s`、ligand `l`：

```text
decayed(r,s,l,t) =
  previous(r,s,l) * exp(-ln(2) * delta_t / half_life(l))

cluster_deposit(r,s,l,t) =
  sum over verified clusters c of max dose(e,l) for e in c at step t

habituation(r,s,c,t) =
  1 / (1 + 0.5 * repeats_seen_in_previous_8_steps(r,s,c))

direct(r,s,l,t) =
  sum over clusters c of
    habituation(r,s,c,t) * max dose(e,l) for e in c

diffusion(r,s,l,t) =
  0.15 * mean(decayed(r,n,l,t) for n in declared subject_neighbors(s))

field(r,s,l,t) =
  clamp(decayed + direct + diffusion, 0, 4)
```

Clone events in同一 verified independence cluster 因 `max` 聚合而不能线性放大 dose。
`subject_neighbors` 只由公开 dependency/tag graph 冻结产生；每个 subject 最多 `4` 个邻居，
按 `(-shared_tag_count, subject_id)` 选择。

### 6.3 Inhibition、normalization 和 event priority

```text
positive(r,s) =
  dot(receptor(r), field(r,s)) -
  receptor_inhibition(r) * field(r,s,inhibition)

raw(r,s) = max(0, positive(r,s))

normalizer(r) =
  1 + sum(raw(r,s) for visible subjects s) / max(1, event_cap)

subject_score(r,s) = raw(r,s) / normalizer(r)

event_contribution(r,e) =
  dot(receptor(r), habituated_event_dose(r,e))

priority_R(e) =
  subject_score(r,e.subject) *
  capability_match(r,e) *
  (0.75 + 0.25 * event_contribution(r,e))
```

Lateral inhibition 是 `inhibition` ligand 对同 subject positive pressure 的显式减项；不得删除
原始 demand。日志同时保存 normalization 前 demand、normalizer 和 normalized score。

### 6.4 Blend 与 affordance

按以下顺序匹配第一条规则：

1. `alarm >= 0.8` 且 `correction >= 0.5`：`verify_and_pause`；
2. `correction >= 0.8` 且 `novelty >= 0.5`：`reopen_and_verify`；
3. `support >= 0.8` 且 `dependency >= 0.5`：`recruit_for_dependency`；
4. `inhibition >= 0.8`：`deprioritize_and_challenge`；
5. 其他：`inspect`。

所有 affordance 可逆且无 commit authority。Fast path 只允许
`verify_and_pause`、`recruit_for_dependency`、verification request；不可执行 irreversible
tool 或 output。

### 6.5 State

Field、habituation 和 receiver history 在普通 episode 间清空。只有 manifest
`long_horizon=true` 才可延续，并必须记录 prior/new state root。Controller state 的
canonical serialization 禁止 wall time、object address 和非确定 map order。

## 7. T1 至 T7 generator v0.1

每个 task generator 先生成 public episode manifest，再单独生成 sealed sidecar。Noise events
和 special events 全部由 counter-based SHA-256 RNG 派生；不得使用全局 RNG。

Split seeds：

| split | seeds per task |
| --- | --- |
| train | `1000..1029` |
| dev | `2000..2029` |
| smoke | `9000..9001` |
| pilot | `3000..3029` |
| confirmatory-reserved | `4000..4299` |

在 G4 sample-size freeze 之前不得读取 confirmatory-reserved outcome aggregate。

每个 task 的 special-event 比例和 objective：

| task | 冻结生成规则 | objective |
| --- | --- | --- |
| T1 | 每 10 个 facts 插入 update；每 25 个插入 retraction；最后 20% 插入 conflicting version | 选择最新未撤回 verified version，并在无版本时 abstain |
| T2 | 一个正确独立 minority cluster；错误 clone cluster 数量 `1/2/4/8/16`；最后 25% 插入 correction | 保留正确 minority、false-consensus attack 不成功 |
| T3 | 每 episode 一个 true/false alarm；true alarm 后 `2/4/8` step deadline；插入 verified mitigation 或 retraction | deadline 内选择 verified reversible mitigation，false alarm 不 pause |
| T4 | DAG dependency edge probability `min(0.2, 4/N)`；每 20 step 一次 edge change；10% worker failure | 选择当前 dependency 和 capability 可执行事件 |
| T5 | relevant events 占 `2%`；至少一个 two-hop evidence chain；最后 20% 有 knowledge update | 找齐未 supersede 的 evidence chain |
| T6 | 正确 minority 占 `max(1, floor(0.05N))`；错误 local optimum 占 40%；最后 20% 给独立验证 | 保留并选择稀有正确 candidate |
| T7 | tenant A/B 各半；10% cross-tenant canary；相同 subject ID 可跨 tenant | own-tenant recall；cross-tenant selection 始终为零 |

Provider-free smoke 运行：

```text
agents = 4, 16
events = 100
attack severity = 0, 0.25
repeats = 2
```

Scale profile 固定为：

```text
(agents, events) =
  (4, 100),
  (16, 1_000),
  (64, 10_000),
  (256, 100_000),
  (1_024, 100_000)
```

Attack severity 固定为 `0, 0.10, 0.25, 0.50`。大规模执行可分 shard，但相同 manifest root
必须产生相同输出 root。

## 8. 攻击注入

攻击器只可使用 episode manifest 声明的 budget。注入顺序固定为：

1. clone/Sybil；
2. repeated spam / low-dose drip；
3. topology pollution；
4. delay/out-of-order；
5. stale/retraction revival；
6. alarm/prompt-memory payload；
7. ACL canary。

攻击事件仍需经过 common validator。Forged evidence 应被标为 rejected 并计成本；不得为了
方便比较而把它提升为 verified。每次注入记录 parent、budget、eligible set 和 attack root。

## 9. 计量、timeout 和失败

Exact replay root 包含 deterministic operation counts、serialized bytes、selection、state 和
lineage，不包含 wall time。Wall time 使用 monotonic nanosecond clock 单独记录。

Provider-free episode timeout 为 `30 s`；超时计为失败并保留 partial log。Provider canary：

- 每 provider `1` request；
- max output `128` tokens；
- temperature `0.2`；
- non-streaming common-capability JSON-only prompt；
- request timeout `120 s`；
- 总尝试最多 `3`；
- 仅对 `429`、`5xx`、provider overload 和 network timeout 退避；
- 尊重 `Retry-After`，否则 full-jitter 上限 `1/2/4 s`；
- 每个 attempt 的 token、latency 和错误都计入，不能只保留成功 attempt。

认证、余额、权限、参数和内容安全拒绝不得自动重试。Crash、timeout、invalid JSON 和
schema failure 进入 intent-to-run 结果。

## 10. Provider canary freeze

Provider adapter 位于 external harness，仅从以下环境变量读取新生成的 key：

```text
PHEROOS_MINIMAX_API_KEY
PHEROOS_ZHIPU_API_KEY
```

禁止将 key、Authorization header、原始 reasoning 或隐藏 chain-of-thought 写入 Git、NDJSON、
Trace、exception text 或 shell command。

MiniMax CN：

- base URL `https://api.minimaxi.com/v1`；
- 在 canary 前调用 `/models` 并保存去敏 capability digest；
- requested model `MiniMax-M3`；
- `reasoning_split=true`，只保存最终 content；
- 若账户无 M3 权限则明确失败，不静默切换模型。

GLM CN：

- base URL `https://open.bigmodel.cn/api/paas/v4`；
- requested model `glm-5.2`；
- common-capability 主轨使用 JSON-only prompt 和本地 schema validation；
- provider-native `json_object` 只作单独 sensitivity track；
- reasoning 与最终 content 分离，研究日志不保存 reasoning。

Adapter 必须保存 requested/returned model、provider request ID、finish reason、usage、
usage completeness、latency、attempt count 和 response content digest。Provider/model 是
blocking factor；不得把 MiniMax 与 GLM 的模型差异解释为 controller 效应。

两家当前官方配置依据：

- [MiniMax OpenAI-compatible API](https://platform.minimaxi.com/docs/api-reference/text-chat-openai)
- [MiniMax rate limits](https://platform.minimaxi.com/docs/guides/rate-limits)
- [GLM OpenAI compatibility](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)
- [GLM-5.2](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2)

## 11. G0 至 G3 验收

### G0

- Core working tree 的 `pheroos/`、schemas、examples 和 tests 相对 frozen commit 无算法改动；
- preregistration、profile、TCK 和 manifest hashes 全部匹配 lock；
- branch、split、budget、controller 和 claim language 已冻结。

### G1

- contracts schema 与 constructor validation 双重通过；
- every bundle `authority_scope=none`、`commit_authority=false`；
- selected/dropped 精确 partition eligible set；
- oracle/random 仅带 diagnostic label；
- 两个 fresh process 对相同 input 的 canonical NDJSON 和 roots 完全一致。

### G2

- T1 至 T7 smoke manifests 全部生成；
- 每个 paired arm 使用相同 episode root；
- replay/hash 100% 一致；
- ACL、cross-tenant、authority 和 output violation 为零；
- ground truth 只通过 sidecar ref/digest 出现在主日志。

### G3

- `P` 通过 frozen Hybrid adapter fixtures；
- `S` 图选择和 density 通过；
- `B` append-only/version/supersession/ACL 通过；
- `Q` stateless、同 index、top-k 通过；
- `G` feature allowlist、train/dev isolation、checkpoint freeze 通过；
- F/P/S/B/Q/G/R 均记录 complete cost；
- 未通过 fidelity 的 baseline 不进入 pilot。

只有上述 gate 通过，才可把本 profile 的 G0-G3 状态标记为 completed。Canary 成功只证明
provider wiring，不证明任何研究假设。
