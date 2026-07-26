# Receptor-Gated Ligand Field Experiment Profile v0.2

状态：active G0 execution freeze；先于任何 arm execution；不构成实验结果

研究分支：`codex/receptor-ligand-field-experiments`

Protocol-core 基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

上位预注册：
[Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)

被取代的执行 profile：
[v0.1](receptor-ligand-field-experiment-profile-v0.1.md)

## 1. 版本理由和适用范围

独立 G0 审计在任何 controller arm 或 provider request 执行前发现 v0.1：

1. `P` 在 PheroOS 内建 decay/source-cap 后又施加同类惩罚；
2. `R` 的 diffusion 不能证明 attention mass 不增加；
3. `R` 可能重复投放完整历史；
4. 六维 ligand 与研究稿的八维 vector 不一致；
5. `Q` 使用伪随机 hash similarity，削弱 retrieval baseline；
6. `S` 缺少完整 matched-density construction；
7. natural-cost 与低预算 sweep 被 artificial cap 扭曲；
8. RNG、task sizes、learned baseline 和 cost clocks 不够精确。

v0.1 保留为历史记录，但不得用于实现或运行。v0.2 继承 v0.1 未被本文件替换的 wire、
authority、claim、provider 和 G0-G3 规则，并以本文件为准。External harness 的 active
lock 只能绑定 v0.2。

本 profile 仅用于 engineering smoke/pilot qualification，不允许支持 H1-H6。

## 2. `P`：当前 scalar PheroOS

`P` 只调用冻结的 durable Hybrid Replay v2：

```text
evaluate_hybrid_collective_step_v2(..., attention_only=True)
```

每个 canonical event 恰好产生一个 verified `PheromoneTrail`，不得同时生成 Scout、
Recruitment 或 Inhibition signal，以免双计。

先取最大 ligand：

```text
l* = argmax_k ligand_doses[k]
```

相同 dose 的 tie 顺序：

```text
hazard, contradiction, failure, uncertainty,
congestion, recruitment, utility, novelty
```

`strength = ligand_doses[l*]`。Trail kind：

| dominant ligand | Trail kind |
| --- | --- |
| hazard | `alarm` |
| contradiction / uncertainty | `cautionary` |
| failure / congestion | `negative` |
| recruitment / utility | `positive` |
| novelty | `novelty` |

Trail 的 source、subject、candidate、evidence、cluster、step、strength 和 TTL 逐字段来自
canonical event。Rejected/retracted/stale event 在 common gate 被移除，不生成 trail。

从 `derive_attention_breakdown(source.source_step)` 读取结果。对 exact matching
`(candidate, subject_type, subject_id)`：

```text
subject_salience =
  sum(abs(subject_priority.pressure))
```

如果没有 matching subject：

```text
candidate_salience =
  abs(attention_value) +
  recruitment_pressure +
  inhibition_pressure +
  caution_pressure +
  alarm_pressure +
  novelty_pressure
```

`priority_P(e)` 使用 subject salience，否则使用 candidate salience，否则为 `0`。Kind/sign
只决定可逆 affordance。同值按 `event_id`。禁止外层再次应用 decay、recency、source cap、
diversity、kind 或 receptor weight。G3 fixture 必须证明 adapter 不改变 PheroOS pressure。

## 3. Canonical eight-ligand emission

Ligand 顺序：

```text
utility, failure, hazard, uncertainty,
novelty, congestion, recruitment, contradiction
```

`CanonicalEventV1` 必须携带 governance-issued `ligand_doses[8]`。每维有限、非负且不超过
`1.0`。Agent self-confidence 不得直接成为 dose。

Provider-free generator：

```text
base(e) =
  clamp(validity(e) * cluster_reliability(e) * information_gain(e), 0, 1)

q(e,k) =
  clamp(base(e) * causal_relevance(event_kind,k), 0, 1)
```

三项 base factor 均为 public metadata；sealed relevance label 不参与。固定 relevance：

| kind | non-zero causal relevance |
| --- | --- |
| support | utility `1.0`, uncertainty `0.1` |
| novelty | novelty `1.0`, uncertainty `0.5` |
| alarm | hazard `1.0`, uncertainty `0.25`, congestion `0.1` |
| correction | contradiction `1.0`, failure `0.6`, uncertainty `0.4` |
| inhibition | congestion `0.8`, contradiction `0.4`, failure `0.2` |
| dependency | recruitment `1.0`, utility `0.4` |

所有 arms 看到相同 vector；tags、payload 或 controller 不能偷偷生成额外 dose。

一个 verified emission 只在 `event.logical_time == current_step` 投放一次。Uniqueness key：

```text
(evidence_ref, evidence_version, verified_cluster, causal_lineage_root)
```

同 key 不得重复。Supersession 在传播前撤销旧 emission 的 active contribution，再加入新
contradiction。Field state 必须保存 `emission -> remaining mass` lineage。

## 4. Budget-conserving field

Field 属于 tenant/scope，不属于单个 receiver。每个 ligand：

```text
C_k(t+1) =
  D_k [(1-rho_k)I + rho_k P_k^T] C_k(t) + Q_k(t)
```

`P_k` row-stochastic；isolated node self-loop；tenant/scope 之间无 edge。Subject 使用
canonical ID order。参数：

| ligand | half-life | decay `D` | `rho` |
| --- | ---: | ---: | ---: |
| utility | 8 | 0.917004043205 | 0.20 |
| failure | 8 | 0.917004043205 | 0.25 |
| hazard | 1 | 0.500000000000 | 0.60 |
| uncertainty | 4 | 0.840896415254 | 0.20 |
| novelty | 4 | 0.840896415254 | 0.35 |
| congestion | 2 | 0.707106781187 | 0.40 |
| recruitment | 2 | 0.707106781187 | 0.50 |
| contradiction | 6 | 0.890898718140 | 0.40 |

每次运算 half-even 量化 `1e-12`。同
`(verified_cluster,subject,ligand,step)` 的 deposits 取 maximum：

```text
Q(s,k) =
  min(2, sum over clusters c of max dose(e,k) in (c,s,k,step))
```

如果 `sum_s Q(s,k)>8`，等比例缩放到 `8`。Propagation 与 deposit 相加后每 node cap
`2`；若 `sum_s C(s,k)>32` 再等比例缩放到 `32` 并记录 clipped mass。

Diffusion 守恒断言发生在 caps 之前：

```text
abs(sum(propagated) - D_k*sum(previous)) <= 1e-12
```

Caps 不得掩盖 mass creation。

Ligand topology：

- utility：artifact/task dependency；
- failure：reverse dependency；
- hazard：相同 safety scope；
- uncertainty：相同 evidence subject；
- novelty：declared unexplored neighbor；
- congestion：相同 workstream；
- recruitment：capability graph；
- contradiction：相同 claim/reference。

每 node 最多四条 outgoing edges，按
`(-declared_edge_weight,destination_subject_id)` 选择后归一化。

## 5. Receptor、habituation、inhibition 和 blend

### 5.1 Receptor

Role sensitivity 按八维 ligand 顺序：

| role | utility | failure | hazard | uncertainty | novelty | congestion | recruitment | contradiction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| verifier | 0.8 | 1.0 | 1.2 | 1.2 | 0.6 | 0.6 | 0.5 | 1.25 |
| coordinator | 1.0 | 0.8 | 1.0 | 1.0 | 0.75 | 1.1 | 1.2 | 1.0 |
| explorer | 0.75 | 0.75 | 0.8 | 1.0 | 1.25 | 0.5 | 0.75 | 1.0 |
| operator | 1.0 | 1.0 | 1.25 | 0.75 | 0.5 | 1.0 | 0.75 | 0.9 |

未声明 role fail closed。ACL/capability mask `m` 在 activation 前计算。八维 `K`：

```text
0.5, 0.5, 0.25, 0.5, 0.5, 0.5, 0.5, 0.35
```

Hill coefficient `n=2`：

```text
z = sensitivity(a,k) * C(s,k)
r(a,s,k) = m(a,s,k) * z^2 / (K_k^2 + z^2)
```

### 5.2 Habituation

八维 `beta`：

```text
0.8, 0.8, 0.5, 0.8, 0.8, 0.5, 0.5, 0.8
```

对 prior state `h`，如果当前 step 有 receiver 前八 step 未见的新 verified cluster，
`h_effective=0.25*h`；否则 `h_effective=h`：

```text
u = max(0, r - 0.75*h_effective)
h_next = beta*h + (1-beta)*r
```

普通 episode state 从零开始。Superseded state 可留作恢复分析，但旧 concentration 不得继续
产生 activation。

### 5.3 Lateral inhibition

`L[target,source]` 非零项：

```text
L[utility,hazard]          = 0.75
L[utility,contradiction]   = 0.75
L[utility,failure]         = 0.50
L[utility,uncertainty]     = 0.25
L[recruitment,congestion]  = 0.75
L[recruitment,hazard]      = 0.50
L[novelty,congestion]      = 0.50
L[novelty,failure]         = 0.25
L[failure,utility]         = 0.25
L[uncertainty,utility]     = 0.25
```

```text
v(target) =
  max(0, u(target) - sum_source L[target,source]*u(source))
```

### 5.4 Divisive normalization

每 subject/ligand：

```text
y(k) = v(k) / (0.25 + v(k) + 0.25*sum_{j != k}v(j))
```

Blend 和 thresholds 只作用于 `y`。Subject salience：

```text
salience =
  1.50*y_utility +
  2.00*y_failure +
  3.00*y_hazard +
  1.25*y_uncertainty +
  0.75*y_novelty +
  1.25*y_congestion +
  1.00*y_recruitment +
  2.50*y_contradiction +
  0.50*I(any blend matched)
```

### 5.5 Blend precedence

按顺序匹配第一条：

1. hazard `>=0.45`：`verify_and_pause`；
2. contradiction `>=0.45`：`review`；
3. failure `>=0.50` 且 utility `<0.35`：`reroute`；
4. congestion `>=0.50`：`stop_recruiting`；
5. utility `>=0.45` 且 uncertainty `>=0.35`：`verify_before_use`；
6. utility `>=0.50` 且 `max(hazard,uncertainty,contradiction)<0.30`：`retrieve`；
7. novelty `>=0.45` 且 congestion `<0.35`：`explore`；
8. recruitment `>=0.45` 且 congestion `<0.35`：`recruit_capability`；
9. 其他：`inspect`。

Fast path 只有 `verify_and_pause`、`recruit_capability` 和 verification request；全部可逆且
`commit_authority=false`。

Natural R 选择 top-4 subjects，每 subject top-2 evidence refs。

## 6. Strong baselines

### 6.1 `Q` stateless BM25

Tokenizer：Unicode NFC、lowercase，Latin token regex `[a-z0-9_:.+-]+`；CJK 字串按单个
Unicode code point token 化。Document 包含 subject、candidate、公开 tags、role/capability
metadata 和 canonical payload。Query 包含 receiver query subjects、role、capabilities 和
task public tags。

BM25 `k1=1.2`、`b=0.75`：

```text
idf(term) =
  ln(1 + (N-df(term)+0.5)/(df(term)+0.5))

priority_Q =
  BM25 +
  2.00*I(exact subject) +
  1.00*Jaccard(event.tags,receiver.capabilities) +
  0.50*I(role match) +
  0.25/(1+age)
```

Priority half-even `1e-9`，tie `event_id`。每 step 只索引 current active eligible events，
从零重建；Q 不保留 receiver state。Build、tokenize、read 和 query 全计成本。

### 6.2 `S` matched-density static sparse

每 task family 先在 dev 计算 R 的 mean selected receiver out-degree：

```text
d = clamp(1,N-1,round_half_even(mean_R_out_degree))
```

三个候选：

- dependency：out-degree 超过 `d` 时按
  `(dependency_distance,receiver_id)` 剪到 `d`，不补边；
- capability：out-degree 超过 `d` 时按
  `(-Jaccard(required_tags,receiver_capabilities),receiver_id)` 剪到 `d`，不补边；
- matched random regular：agents 按
  `SHA256(task_family|dev_root|agent_id)` 排成环，位置 `i` 连接
  `i+1..i+d mod N`，in/out degree 都为 `d`。

Self-edge 禁止。每 task family 按 dev relevant-edge recall、task success、edge count、bytes、
graph name 依次破平。Pilot/test/OOD 不更新。

### 6.3 `G` deterministic learned pruning

每 edge feature 顺序：

```text
1,
tag_jaccard,
role_exact,
capability_jaccard,
1/(1+age),
clamp(strength,0,1),
I(superseding),
version/max_visible_version,
I(new_verified_cluster),
I(S_frozen_edge)
```

Feature 量化 `1e-12`。Label 只来自 train sidecar relevant edge；每 task family 单独训练。
类别权 `a_c=N/(2*N_c)`，weights 从零开始。每 epoch 按 canonical edge order 计算 full-batch
weighted logistic gradient：

```text
p_i = sigmoid(clamp(w dot x_i,-30,30))
g_j =
  sum_i a_yi*(p_i-y_i)*x_ij / sum_i a_yi +
  l2*w_j
w = q12(w-learning_rate*g)
```

Intercept 不正则。Decimal precision `34`、`ROUND_HALF_EVEN`，禁止 BLAS 并行。

Grid：

```text
learning_rate = 0.01, 0.05, 0.10
l2            = 0, 0.001, 0.01
epochs        = 25, 50
native_k      = 4, 8, 16
```

Dev 依次按 selected-edge macro-F1 高、task success 高、operations 少、L2 大、learning rate
小、epochs 小、k 小破平。Inference `priority_G=sigmoid(clipped dot)`，量化 `1e-9`，tie
`event_id`。Checkpoint 绑定 train/dev roots、feature allowlist、cost 和 hash。

### 6.4 `F` 与 `B`

F natural 选择全部 eligible。预算不足时 selection rank newest-first；最终 model payload
重新按 `(logical_time,event_id)` 排列。`PerceptBundleV1` 分开记录 `selection_order` 与
`payload_order`。

B append-only、versioned、ACL-scoped。旧 version 计 storage cost，但不进入 active ranking：

```text
kind_score =
  2 for alarm/correction
  1 for inhibition/novelty
  0 otherwise

priority_B =
  4*I(superseding) +
  2*kind_score +
  version/max(1,max_visible_version_for_subject) +
  1/(1+age) +
  0.1*clamp(strength,0,1)
```

## 7. Budget regimes

Natural-cost 不施加共同 cap：

- F：全部 eligible；
- P：native top-8；
- S：frozen incoming edges 上的全部 eligible；
- B：top-16 current active versions/read；
- Q：top-8；
- G：dev 冻结 `k in {4,8,16}`；
- R：top-4 subjects，每 subject top-2 refs。

Iso 每 receiver-step：

```text
events=8, tokens=512, dereferences=8, model_calls=1, tool_calls=1
```

Sweep ratio：

```text
0.10, 0.20, 0.35, 0.50, 0.75, 1.00
```

每 receiver-step：

```text
token_cap = floor(ratio*F_eligible_tokens)
edge_cap  = floor(ratio*F_eligible_edges)
ref_cap   = 2*edge_cap
```

Cap 小于最小 eligible event 时选择零个，禁止强制一个；记录 effective fraction。

## 8. RNG、tasks 和 attacks

Seed bytes：

```text
seed_bytes =
  SHA256(
    "pheroos-rglf-v0.2\0" |
    task_id | "\0" | split | "\0" |
    decimal(seed) | "\0" | decimal(repeat)
  )

draw(namespace,counter) =
  first_u64_big_endian(
    SHA256(
      seed_bytes | "\0" | namespace | "\0" |
      counter_as_u64_big_endian
    )
  )
```

抽样位置也按 digest 排序。禁止 Python `hash()` 和 global RNG。Split：

```text
train=1000..1029, dev=2000..2029, smoke=9000..9001,
pilot=3000..3029, confirmatory_reserved=4000..4299
```

Train/dev repeat `1`；smoke/pilot repeat `2`。

```text
logical_time(i) = floor(i*steps/events)
```

Smoke full cross：

```text
receiver agents=4,16; events=100; steps=20;
severity=0,0.25; seeds=9000,9001; repeats=2
```

Pilot：

```text
receiver agents=16; events=1,000; steps=40; repeats=2;
severity=[0,0.10,0.25,0.50][(seed-3000) mod 4]
```

Task sizes（smoke/pilot）：

| task | size |
| --- | --- |
| T1 | facts `20/100` |
| T2 | candidates `4/8`; clone event multiplier `[1,2,4,8,16][seed mod 5]` |
| T3 | artifacts `16/32`; deadline `[2,4,8][seed mod 3]` |
| T4 | jobs `32/64` |
| T5 | subjects `50/200`; relevant count `max(3,ceil(0.02*events))` |
| T6 | candidates `20/64`; correct minority agents `max(1,floor(0.05*agents))` |
| T7 | subjects per tenant `16/64` |

T2 clone multiplier 是 emission/Sybil principal 数，不是 receiver agent 数；clones 共享
verified cluster、evidence digest 和 parent lineage，correction 来自不同 cluster。

Special positions 使用 counter digest 排序选固定 `floor/ceil` 数量。Attack count：

```text
floor(severity*attackable_slots)
```

不得 Bernoulli sampling 导致实际 budget 漂移。T7 同时生成：

1. common gate 拒绝的 cross-tenant canary，写入
   `emission_rejected/communication_ineligible`；
2. own-tenant、same-subject adversarial collision，进入 controller eligible set。

Scale pairs 沿用上位计划，标记 capability-only、steps `50`、无 outcome claim。

## 9. Cost clocks、timeouts 和 ordering

Provider-free 单线程 timing：

- wall：`perf_counter_ns`；
- CPU：`thread_time_ns`；
- peak Python allocation：`tracemalloc`；
- RSS：`resource.getrusage`，macOS bytes/Linux KiB 规范化；
- storage reads/writes/bytes：显式计数。

Controller timer 从收到完整 `ControllerContextV1` 到 immutable `PerceptBundleV1` 完成，包含
index build/query、P Store、state serialization/hash；排除 generator、common eligibility、
sealed scorer 和 NDJSON disk flush，这些另计。不做 empty-call subtraction。

Wall/CPU/RSS 不进入 replay root。Timeout：

```text
smoke episode        30 s
train/dev/pilot     120 s
G checkpoint train  600 s per task
scale               900 s
provider attempt    120 s
```

Timeout 保留 partial log并进入 intent-to-run。

## 10. Mechanical G0-G3 assertions

任何 arm execution 前：

1. v0.2 与上位预注册已提交；
2. external lock 绑定新 commit 和 v0.2 hash；
3. v0.1 被标记 superseded；
4. contracts 支持 eight-ligand dose、selection/payload order、完整 eligible partition 和
   zero authority；
5. `P/Q/S/G/R` tests 覆盖本文件公式；
6. 尚无 outcome 的事实写入 G0 log。

G1-G3 至少机械证明：

```text
sum(C_next) <= sum(decayed_C_previous) + applied_deposit

same-cluster clone multiplier 1/2/4/8/16
does not change applied cluster deposit

P adapter pressure exactly matches frozen Hybrid Replay v2 fixture

selected U dropped == eligible
selected intersection dropped == empty

authority_scope == none
commit_authority == false

cross-tenant selected edges == 0
```

Canary 和 smoke 只能证明 wiring、determinism、fidelity 与安全不变量，不支持 H1-H6。
