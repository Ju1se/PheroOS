# Receptor-Gated Ligand Field vNext Architecture Research

状态：非规范性架构研究基线；不激活 profile、不授权实现、不修改 ABI、schema、
Trace、TCK、Conformance 或 Commit truth

日期：2026-08-06

研究分支：`codex/receptor-ligand-field-experiments`

研究检查点：`4f292de`

关联研究：

- [Comparative Study Plan](receptor-ligand-field-comparative-study-plan.md)
- [Active Experiment Profile v0.6](receptor-ligand-field-experiment-profile-v0.6.md)
- [Experiment Profile v0.7 review draft](receptor-ligand-field-experiment-profile-v0.7.md)
- [G0-G3 Qualification Report](receptor-ligand-field-g0-g3-qualification-report.md)
- [v0.7 E1 Replica Preregistration Qualification Audit](receptor-ligand-field-v0.7-e1-prereg-qualification-audit.md)

## 1. 目的和结论

本文把昆虫嗅觉神经计算、蜜蜂选巢、蚂蚁信息素决策、LLM 长期记忆、
multi-agent 通信拓扑和错误传播研究，整理为 PheroOS vNext 的候选架构与公式基线。

当前最强结论是：

> receptor-gated ligand field 值得作为独立、opt-in、attention-only 的 vNext
> 候选继续研究；它不应原地替换 Hybrid v1，也不应直接进入 Commit truth。

推荐架构不是把所有机制继续乘进一个 `novelty` 标量，而是拆成三层：

1. **受体层**：饱和、适应、输入增益控制和选择性侧抑制；
2. **群体层**：独立发现、有限招募、退出、定向 stop signal 和拥塞负反馈；
3. **选择层**：守恒式相对分配、no-action 质量和确定性 top-k。

研究直接支持问题和机制动机，但尚未证明完整 RG-LF 优于当前 scalar Hybrid、
sparse communication、blackboard、retrieval routing 或 learned graph pruning。本文中
所有具体公式、参数和版本名都是待预注册、消融和复验的工程候选。

## 2. 不可改变的 PheroOS 边界

vNext 只允许改变 attention/communication plane：

```text
agent proposal
    |
    v
Governance verification + Evidence Ledger
    |
    v
receptor-ligand field + exploration allocation
    |
    v
non-authoritative PerceptBundle
    |
    v
external runtime collects new observations
    |
    v
new verified evidence
    |
    v
existing Optimal Commit + output contract
```

以下约束是设计前提：

- `authority_scope="none"`；
- `commit_authority=false`；
- field、receptor、novelty、recruitment 和 percept 不能创建 evidence、permission、
  candidate、quorum、commit 或 output authority；
- attention 可以促使 runtime 收集新证据，但只有重新进入 Evidence/Governance 路径的
  verified evidence 才能影响后续 Commit truth；
- 固定 Evidence/Commit truth 时，改变任意 attention 参数不得改变 commit truth root；
- baseline protocol、Hybrid v1、Hybrid Replay v2、Optimal Commit 和现有 schema/TCK
  roots 必须保持独立且兼容；
- provider、model routing、embedding、agent loop、scheduler、database、experiment runner
  和 learned parameter optimizer 留在 protocol-core 之外。

## 3. 证据边界

### 3.1 外部研究直接支持的部分

| 机制 | 研究支持 | PheroOS 可采用的含义 |
| --- | --- | --- |
| 受体饱和 | 昆虫嗅觉受体的 dose-response 可用 Hill 型曲线拟合 | 使用有界、单调的 receptor response |
| 输入增益控制 | 果蝇触角叶中总体 ORN 活动提高通道饱和门槛，input-gain model 优于简单 output scaling | 把适应和竞争池放进非线性分母，而不是最后减分 |
| 时间适应 | 昆虫 ORN 会按刺激时间统计调整响应，重复 pulse 的响应降低并在间隔后恢复 | visitation/habituation 必须有半衰期和恢复 |
| 蜜蜂独立发现与招募 | 选巢模型把 discovery、recruitment、abandonment 分开，并受有限未承诺 scout 池约束 | 独立探索不能被 social recruitment 吞没；招募必须饱和 |
| 蜜蜂定向 stop signal | scouts 主要抑制竞争地点的 dance，cross-inhibition 改变 deadlock 和 speed-accuracy trade-off | inhibition 必须显式 target，普通 dissent 应是有界软抑制 |
| 蚂蚁相对分支选择 | pheromone choice 依赖候选间相对信号并可产生 symmetry breaking | 最终选择应跨 eligible candidates 归一化 |
| 蚂蚁拥塞负反馈 | crowding 可在旧 pheromone 仍存在时抵消正反馈并促进重新分配 | congestion 抑制新 exploration/reinforcement，不删除历史 field |
| 稀疏通信 | 多项 multi-agent 研究显示稀疏拓扑可降低 token 成本并保持相近结果 | topology、edge count、token 和 fan-out 应是一等预算 |
| 相关错误 | 不同模型、架构或 provider 的错误仍可能高度相关 | `source_id` 不能充当独立性证明 |
| 旧记忆污染 | outdated memory 会降低长期交互和检索推理质量 | append-only history 与 deterministic active/superseded view 必须分离 |

### 3.2 尚未被证明的部分

以下均为工程假设，不是昆虫学或 multi-agent 文献已经证明的最优设计：

- `utility/failure/hazard/uncertainty/novelty/congestion/recruitment/contradiction`
  八 ligand ontology；
- 将 verified agent signal 映射为“气味浓度”；
- 具体 Hill coefficient、半饱和常数、half-life、抑制矩阵和 blend threshold；
- EIG、dependence group 和 causal lineage 与昆虫群体机制的组合；
- mass-conserving field 能提高 LLM task success；
- 本文最终组合公式优于现有 Hybrid 或强基线；
- biological plausibility 等价于工程优越性。

## 4. 当前 PheroOS 与 vNext 的差距

| 当前实现 | vNext 需要 | 设计决定 |
| --- | --- | --- |
| `PheromoneTrail(kind, strength)` 是全局 scalar trail | 版本化 ligand vector、receiver context 和 receptor state | 不修改旧 `PheromoneTrail`；新增独立 profile |
| diversity 主要按 `source_id` 计数 | causal-lineage dedup 和 dependence-group cap | 先折叠，再进入任何非线性 |
| BFS diffusion 保留 root 并添加派生 trail | per-ligand row-stochastic、caps 前质量守恒的 field reducer | 不复用现有 BFS 作为守恒 reducer |
| 聚合 trail 不保存逐 emission 残余质量 | supersession 后精确撤销已扩散贡献 | 保存 `emission -> node x ligand remaining contribution` |
| `AttentionBreakdown` 面向当前 Hybrid | receiver-specific `PerceptBundle` | 新建 versioned attention binder，继续证明零 Commit sensitivity |
| Hybrid Replay v2 保存当前 Hybrid 状态 | field、topology、receiver adaptation、supersession 和 percept roots | 新建独立 Store-backed Replay；不扩展旧 snapshot |

## 5. 候选数学语义

本节是候选 reference semantics，不是已生效规范。

### 5.1 Canonical numeric contract

所有规范数值使用 Q12 定点整数：

```text
S = 10^12
real_value = integer_value / S
```

定义统一 Hill 算子：

\[
\operatorname{Hill}^{+}_{S}(x;K,n)
=
\operatorname{RHE}
\left(
S\frac{x^n}{K^n+x^n}
\right)
\]

\[
\operatorname{Hill}^{-}_{S}(x;K,n)
=S-\operatorname{Hill}^{+}_{S}(x;K,n)
\]

其中：

- `RHE` 是 round-half-even；
- `x >= 0`、`K > 0`；
- 第一版只允许整数 `n in {1, 2}`；
- 使用整数幂并在最后一次除法舍入；
- 非有限值、负数、未知版本和越界参数 fail closed；
- 所有中间量、update order、cap 和 tie-break 必须规范化。

昆虫实验可出现约 `n=1.4-1.7` 的拟合，但任意分数指数会增加跨实现一致性成本。
`n=3/2` 只有在另一个版本明确冻结整数平方根或 golden lookup 算法时才可进入 ABI。

### 5.2 Causal-lineage 和 dependence-group 折叠

任何 dose、EIG、recruitment 或 inhibition 在进入 Hill 前先折叠。

对 causal lineage `l`：

\[
x_l=\max_{e:\operatorname{lineage}(e)=l}x_e
\]

对 Governance 签发的 dependence group `g`：

\[
x_g=\max_{l:\operatorname{group}(l)=g}x_l
\]

跨 group 聚合：

\[
\bar{x}
=
\begin{cases}
\dfrac{\sum_g w_gx_g}{\sum_gw_g}, & \sum_gw_g>0 \\
0, & \text{otherwise}
\end{cases}
\]

约束：

- `dependence_group_ref` 和 `w_g` 必须绑定 Governance receipt 与 membership snapshot；
- agent、provider 或 model 名称不能自行证明独立；
- 同一 causal root 声称属于多个 group 必须拒绝；
- 同一 evidence/version/lineage 重放不能增加数值；
- supersession 先撤销旧 lineage 的 active contribution，再执行本节聚合。

### 5.3 自适应 input-gain receptor

对 receiver `a`、candidate/subject `c`、ligand `k`、step `t`，令
`C_hat(c,k,t)` 是经过验证、dedup、supersession 和 field reducer 后的浓度。

ACL 是计算前硬门：

\[
ACL_{a,c,k,t}=0
\Longrightarrow
r_{a,c,k,t}=0
\]

未授权时不得读取浓度、进入 normalization pool、暴露 evidence ref 或更新 receiver state。

授权后：

\[
u_{a,c,k,t}=s_{a,k}\widehat{C}_{c,k,t}
\]

适应衰减：

\[
\rho_{a,k}=2^{-\Delta t/T^{hab}_{a,k}}
\]

该指数式只用于说明 half-life。ABI 不在运行时调用任意实数幂；profile 必须携带已经
冻结的 Q12 单步衰减因子，并使用规范的 Q12 乘法重复推进 `Delta t`。

\[
H_{a,c,k,t}
=
\rho_{a,k}H_{a,c,k,t-1}
+
(1-\rho_{a,k})
\operatorname{clip}
\left(
\frac{u_{a,c,k,t}}{C^{ref}_{a,k}},0,1
\right)
\]

当前响应必须读取 `H(t-1)`，完成输出后才写入 `H(t)`。

半饱和门槛：

\[
K^{eff}_{a,c,k,t}
=
K^0_{a,k}
\left(
1+\beta_{a,k}H_{a,c,k,t-1}
\right)
\]

选择性输入抑制池：

\[
P_{a,c,k,t}
=
\sum_{j\ne k}
W_{a,kj}
\operatorname{clip}
\left(
\frac{u_{a,c,j,t}}{C^{ref}_{a,j}},0,1
\right)
\]

候选 receptor response：

\[
\boxed{
r_{a,c,k,t}
=
m_{a,k}
\frac{u_{a,c,k,t}^{n_{a,k}}}
{
u_{a,c,k,t}^{n_{a,k}}
+
(K^{eff}_{a,c,k,t})^{n_{a,k}}
+
(\gamma_{a,k}P_{a,c,k,t})^{n_{a,k}}
}
}
\]

性质和约束：

- `P=0`、`beta=0` 时退化为标准 Hill saturation；
- adaptation 增大输入门槛，不删除历史；
- inhibition 位于饱和之前，形成 input-gain control；
- `W(k,j) >= 0`、`W(k,k)=0`、每行和不超过 `1`；
- pool 只能包含 receiver 可见、verified、lineage/group-capped 的输入；
- `hazard` 和 `contradiction` 默认 `beta=0`、`gamma=0`，不能被 habituation 或
  benign activity 稀释；
- 普通 receptor 建议 `n=1` 作为 reference，`n=2` 作为消融；
- 主要阈值非线性应放在 recruitment/quorum 层，避免连续多层幂放大。

### 5.4 Expected information gain 与 fallback surrogate

严格 EIG 仅在 external runtime 拥有校准预测分布、且能产生可验证 receipt 时使用。

对 dependence group `g`：

\[
j_g(c)
=
\max_{l\in g}
\left[
IG_l(c)
P_{valid,l}(c)
(1-U^{alea}_l(c))
\right]
\]

\[
J(c)
=
\begin{cases}
\dfrac{\sum_gw_gj_g(c)}{\sum_gw_g}, & \sum_gw_g>0 \\
0, & \text{otherwise}
\end{cases}
\]

其中：

- `U_epi` 是可通过观察减少的 epistemic uncertainty；
- `U_alea` 是噪声、不可辨识性或不可验证性造成的 irreducible uncertainty；
- `P_valid` 是探索动作取得有效 observation 的预期概率；
- EIG receipt 不得读取未来结果、sealed evaluator、attack label 或 agent 自报 confidence。

没有校准模型时使用 provider-free surrogate：

\[
J_{surrogate}(c)
=
U^{epi}(c)
T(c)
P_{valid}(c)
(1-U^{alea}(c))
\]

`T(c)` 是 testability。该值必须命名为
`expected_reducible_uncertainty_reduction`，不能冒充严格信息论 EIG。

### 5.5 可恢复 visitation 和 congestion

只统计 Governance 验证的 completed exploration receipts，并按 action/causal root 去重：

\[
V_{c,t}
=
\lambda_vV_{c,t-1}
+
(1-\lambda_v)
\operatorname{clip}
\left(
\frac{visit\_mass_{c,t}}{B_v},0,1
\right)
\]

\[
G_V(c)=\operatorname{Hill}^{-}(V_{c,t};K_V,n_V)
\]

拥塞由当前资源状态定义：

\[
C_{c,t}
=
\operatorname{clip}
\left(
\frac{active\_load_{c,t}}{declared\_capacity_{c,t}},0,1
\right)
\]

\[
G_C(c)
=
I(capacity\ available)
\operatorname{Hill}^{-}(C_{c,t};K_C,n_C)
\]

设计含义：

- visitation 是可恢复的 attention pressure，不是永久计数；
- congestion 先通过硬 capacity gate，再通过平滑 Hill 降载；
- congestion 抑制新 exploration/reinforcement，不删除已有 field；
- history 仍按各 ligand 的独立 decay/supersession 规则更新。

### 5.6 独立发现 Novelty drive

定义 `I_fresh(c)` 为当前 `(candidate, evidence_version, epoch)` 第一次合格曝光，最多生效
一次。独立发现驱动力：

\[
\boxed{
D_t(c)
=
\operatorname{clip}_{[0,1]}
\left[
\epsilon_{first}I_{fresh}(c)
+
\operatorname{Hill}^{+}(J(c);K_I,n_I)
G_V(c)
G_C(c)
\right]
}
\]

相比最初的
`novelty proportional to EIG / (1 + visitation) * (1 - congestion)`，该式：

- 把 `proportional to` 变成可重放的精确函数；
- 先饱和 EIG，防止单个乐观预测垄断；
- 让 visitation 衰减并恢复；
- 用 threshold-like congestion 负反馈替代线性硬悬崖；
- 给真正新候选一次 bounded first-discovery floor；
- 不把 social recruitment 混成证据新颖性。

### 5.7 Recruitment、stop signal 与 safety

社会昆虫模型把独立发现、招募、退出和 cross-inhibition 分开：

\[
\dot y_c
=
y_UD_c
+
y_Ur_cy_c
-
a_cy_c
-
y_c\sum_{d\ne c}s_{d\rightarrow c}y_d
\]

\[
y_U=1-\sum_cy_c
\]

该 ODE 是设计依据，不是建议直接放进第一版 ABI。PheroOS reference reducer 应使用
有界离散项。

对 dependence-aware recruitment pressure `Q(c)`：

\[
R(c)=\operatorname{Hill}^{+}(Q(c);K_R,n_R)
\]

对显式 target 到候选 `c` 的 verified ordinary stop pressure `S(c)`：

\[
G_X(c)
=
1-\lambda_X
\operatorname{Hill}^{+}(S(c);K_X,n_X),
\qquad 0\le\lambda_X\le0.5
\]

普通 dissent 最多减少一半探索优先级，避免一个竞争或恶意来源完全消音候选。只有
verified hard safety stop 才能归零。

安全门使用未经 benign divisive normalization 稀释的响应：

\[
G_S(c)
=
I(no\ verified\ hard\ stop)
(1-r_{hazard})
(1-r_{contradiction})
(1-\omega_fr_{failure})
\]

最终候选 activation：

\[
\boxed{
X_t(c)
=
G_S(c)
G_X(c)
\left[
(1-\omega_R)D_t(c)
+
\omega_RR_t(c)
\right]
}
\]

建议 `omega_R <= 0.5`，使真正独立发现始终保留至少一半通道。`G_S=0` 只禁止相应
exploration action 并产生 `verify_and_pause` 或 `review` percept；它不修改 Commit
truth。

### 5.8 守恒式相对 attention allocation

对通过 hard eligibility checks 的候选集合 `E`：

\[
Z_t
=
\sigma^\eta
+
\sum_{d\in E}X_t(d)^\eta
\]

\[
\pi_t(c)
=
(1-\epsilon)
\frac{X_t(c)^\eta}{Z_t}
+
\frac{\epsilon}{|E|}
\]

\[
\pi_t(none)
=
(1-\epsilon)
\frac{\sigma^\eta}{Z_t}
\]

因此：

\[
\sum_{c\in E}\pi_t(c)+\pi_t(none)=1
\]

约束：

- `E` 为空时，唯一输出是 `pi(none)=1`；
- `epsilon` 是总探索预算，不是每候选额外加分；
- `sigma` 保存 no-action 质量；
- hard-stopped candidate 不进入 `E`；
- `eta=1` 是 reference，`eta=2` 仅作为 symmetry-breaking 消融；
- protocol-core 不随机抽样或执行 softmax；
- rational shares 转成 Q12 后使用 canonical largest-remainder 分配剩余最小单位，
  remainder 相同时按 `(candidate_id, none)` 固定顺序，确保总质量精确为 `S`；
- 输出按 `(-priority, oldest_last_visit_step, candidate_id)` 确定性排序；
- external runtime 可以消费 attention budget，但不得把它解释成 quorum 或 commit。

### 5.9 固定 reducer 顺序

候选 reference order：

```text
1. strict version/scope/ACL/membership validation
2. apply evidence supersession and retraction
3. collapse causal lineage and dependence group
4. decay previous per-emission field contributions
5. per-ligand mass-conserving diffusion
6. aggregate current deposits and apply explicit caps
7. compute adaptive input-gain receptor response
8. update receiver habituation state
9. compute EIG/surrogate, visitation and congestion
10. compute independent discovery novelty
11. compute recruitment and targeted stop pressure
12. apply non-habituating safety gate
13. conserve attention across eligible candidates and no-action
14. select deterministic PerceptBundle
15. persist snapshot, transition receipt and Trace roots atomically
```

同一步 supersession 必须在 diffusion 前生效。Caps 前逐 ligand 质量守恒；clipped mass
单独记录，不能用 cap 掩盖 mass creation。

## 6. 候选参数 profile

以下是建议预注册的第一轮工程默认，不是昆虫学常数：

| 参数 | Reference | Ablation / bound |
| --- | ---: | --- |
| receptor `n` | `1` | `2` |
| information `n_I` | `1` | `2` |
| visitation `n_V` | `1` | `2` |
| congestion `n_C` | `2` | `1` |
| recruitment `n_R` | `2` | `1` |
| ordinary stop `n_X` | `2` | `1` |
| relative choice `eta` | `1` | `2` |
| social share `omega_R` | `<= 0.50` | sweep |
| ordinary stop cap `lambda_X` | `<= 0.50` | sweep |
| total exploration `epsilon` | `0.025` | preregistered sweep |
| visitation half-life | `4 steps` | preregistered sweep |

不要同时把 receptor、EIG、recruitment 和 relative choice 全部设为高阶幂。连续陡峭
正反馈会降低动态范围、加剧 early lock-in，并使 clone、噪声和小数值误差被放大。

## 7. 候选版本和 ABI 边界

若研究证据达到 core-entry gate，建议通过独立 ADR 决定版本。候选命名是：

```text
semantic protocol:  pheroos.protocol.v3
schema documents:   capability-v4 / protocol-v4
attention profile:  pheroos-receptor-field-attention-v1
state/replay:       pheroos-receptor-field-state-v1
governance module:  pheroos.governance.receptor_field_v1
```

这些名称尚未被选择或实现。

候选 `ScopedProtocolManifestV3` 使用独立字段：

```text
attention_policy: ReceptorFieldAttentionPolicyV1
authority_scope: "none"
commit_authority: false
```

不得：

- 给现有 `CollectiveDecisionPolicy` 或 `PheromoneTrail` 原地增加主动语义；
- 借 `extensions` 绕过 strict schema 和 conformance；
- 扩展 `HybridReplaySnapshotV2` 来承载不可投影的新状态；
- 自动把 scalar trail/snapshot 迁移成 ligand vector；
- 修改现有 Hybrid score、source diversity、exploration floor 或 commit outcome。

vNext 应从 verified canonical emission/evidence ledger 建立 fresh genesis。旧 snapshot
不能无损推断 ligand vector、receiver state、dependence group 或逐 emission mass。

## 8. 最小 vertical slice

第一版只实现完整但最小的 attention 路径：

### 8.1 Protocol

- `ReceptorFieldAttentionPolicyV1`；
- versioned ligand-set ID，例如 experimental `pheroos-rglf-8-v1`；
- receptor role/profile；
- topology、decay、caps、selection 和 resource bounds；
- const `authority_scope="none"`、`commit_authority=false`。

### 8.2 Governance

- untrusted `EmissionProposalV1`；
- Governance-issued `VerifiedEmissionV1`；
- `DependenceGroupReceiptV1`，不使用未经证明的 `independence` 命名；
- `ReceptorFieldSnapshotV1`；
- pure total step reducer；
- `PerceptBundleV1`；
- vNext-specific attention/Commit channel binder。

Verified emission 至少绑定：

```text
domain / scope / run / target / epoch / step
evidence_ref / evidence_version / evidence_digest
causal_lineage_root / dependence_group_ref
membership_snapshot_root / ACL root
ligand_set_id / dose vector
supersedes / retracts
```

### 8.3 Trace and Replay

继续使用 canonical `pheroos.trace.TraceEvent`，但 Draft 期只产生明确的非权威、
namespaced receptor-field receipts。若未来成为 built-in Trace semantics，发布新 Trace
版本，而不是改变 frozen Trace v1 的有效集合。

Store-backed snapshot 至少保存：

- domain/scope/run/target/epoch 和 manifest/profile roots；
- topology、membership、ACL roots；
- active emissions 和 supersession ledger；
- `emission -> node x ligand remaining contribution`；
- receiver habituation state；
- field、percept、transition 和 source Trace roots；
- parent revision/root、idempotency 和 CAS information；
- exact resource counters。

### 8.4 External runtime

以下始终留在独立 runtime/research repository：

- model/provider clients；
- evidence database 和 private memory；
- learned EIG、topology、receptor parameters 或 dependence estimator；
- agent execution loop、scheduler、worker、queue 和 server；
- benchmark datasets、sealed evaluator、cost ledger 和 experiment orchestration；
- prompt/retrieval adapter 和 natural-language rendering。

## 9. Conformance 和 TCK 不变量

vNext Draft 至少必须证明：

1. 任意 field/percept 都保持零 authority 和零 commit authority；
2. 固定 evidence/commit truth 时改变 field、receptor、novelty 或 top-k，不改变 commit
   truth root、leader 或 outcome；
3. 无 current membership、evidence version/digest、ACL 或 provenance 的 emission 原子拒绝；
4. 同 causal root 或 dependence group 的 `1/2/16/100` clones 不增加有效 dose；
5. 新的、Governance 验证的不同 dependence group 可以增加受限贡献；
6. ligand vector 必须 exact-key、有限、非负、Q12、有界；
7. caps 前逐 ligand 质量守恒，isolated node 使用 self-loop，多路径累积确定；
8. clipped mass 显式记录，cap 不能掩盖 mass creation；
9. supersession 在传播前完整撤销旧 emission 的所有 node/ligand contribution；
10. 同一 field 对不同 role/ACL 可产生不同 percept，但不能泄漏不可见引用；
11. habituation 抑制重复输入，在一个 half-life 后精确按规范恢复；
12. `IG` 增大时 novelty 非减，visitation/congestion/stop 增大时对应输出非增；
13. 普通 stop 只抑制显式 target，hard safety 不被 benign normalization 稀释；
14. attention 和 no-action 质量之和精确为 `1`；
15. 输入顺序、dict 顺序、进程重启和 replay 不改变 state/percept/trace roots；
16. duplicate transition 幂等，相同 ID 不同 payload 拒绝；
17. stale parent、跨 domain/scope/run/target 或 root mismatch 全部 fail closed；
18. 双 successor CAS 竞争只能有一个成功；
19. receiver/subject/ligand/emission 数量和 snapshot bytes 有显式上限；
20. toy、baseline、swarm、Hybrid manifests、Hybrid Replay v2、schema hashes、public API
    inventory 和旧 TCK 保持不变。

## 10. 推荐消融和评价指标

不要只比较完整系统。建议按以下顺序增加机制：

```text
static scalar / sparse baselines
-> causal-lineage + dependence-group collapse
-> static Hill
-> adaptive K
-> input-gain inhibition
-> visitation decay
-> congestion Hill
-> recruitment Hill
-> targeted ordinary stop
-> non-habituating safety gate
-> conservative relative allocation
```

主要指标：

- task success 与 safe fallback rate；
- total messages、tokens、fan-out、latency 和 complete cost；
- new verified evidence per token；
- clone amplification factor；
- correlated false consensus 和错误锁定率；
- first independent counterevidence latency；
- stale/superseded evidence activation rate；
- congestion recovery 和 dynamic-environment switching time；
- ACL、cross-tenant、authority 和 output violations；
- attention mutation 对 commit root 的严格零敏感度。

至少比较 full communication、current scalar Hybrid、static sparse、blackboard、BM25
retrieval 和 learned graph pruning。参数必须在 sealed outcome 之前冻结。

## 11. 当前 Gate 与实施路线

截至本文检查点：

- G0、G1 通过；G2、G3 阻断；
- 没有 H1-H6 结果或 comparative superiority conclusion；
- v0.6 是 active research profile；v0.7 仍是 review draft；
- v0.7 E1 replica 三次 preregistration 均被拒绝；official implementation、runtime、
  Main 和 GoldenOracle 仍为 NO-GO；
- current production hardening 的 WP-00 至 WP-11 已完成，WP-12 external reference
  runtime 和 WP-13 final release/promotion 仍未完成。

推荐双轨：

### 11.1 Formal evidence-first lane

1. 关闭 E1 replica 的 normative source/typed-fact/artifact/fault/comparison gaps；
2. 完成 source-distinct review，达到 `P0=0, P1=0`；
3. 完成 v0.7 materialization、golden-oracle firewall 和 exact join；
4. 激活 G3 methodology descriptors、budget、common reducer 和 actual cost ledger；
5. 完成 G2 full-scale replay/isolated A/B 和全部 G3 subgates；
6. 获得 sealed synthetic mechanism evidence 后再提出 core Draft；
7. closed-loop evidence、独立复验和 H6 后才考虑 Stable promotion。

### 11.2 External engineering prototype lane

可以立即在 protocol-core 之外实现 deterministic fake-workload prototype，但必须标记：

```text
not qualification evidence
not an active PheroOS profile
not a superiority result
```

该 prototype 不得读取 sealed research outcome、反馈给 blind E1 replica 或回溯冒充
G2/G3 evidence。

### 11.3 Core-entry decision

若在证据 gate 前进入 protocol-core，只能作为显式批准的 experimental Draft，并接受：

- current release candidate、schema catalog、public API inventory、TCK、SBOM 和 RC evidence
  全部重新建立；
- 完整 version/migration/Trace/Conformance 工作；
- default-off、可回退 Hybrid v1；
- 不宣称优越性；
- 不计入 formal G2/G3 evidence。

## 12. 最终建议

最适合 PheroOS 的 vNext 不是“更复杂的 pheromone score”，而是：

> 一个 versioned、receiver-specific、dependence-aware、supersession-correct、
> budget-conserving 的 attention field；它通过适应性受体、有限招募、定向抑制和
> 可恢复探索来控制信息流，但永远不能绕过 Evidence、Governance 或 Optimal Commit。

优先级应是：

1. provenance、causal lineage、dependence group 和 supersession；
2. exact numeric、mass/resource conservation 和 durable replay；
3. static/adaptive receptor；
4. visitation、congestion、recruitment 和 targeted stop；
5. external learned optimization；
6. 证据充分后才进行 ABI promotion。

## 13. Primary Sources

昆虫嗅觉与神经计算：

- [Distinct signaling of Drosophila chemoreceptors in olfactory sensory neurons](https://pubmed.ncbi.nlm.nih.gov/26831094/)
- [Divisive normalization in olfactory population codes](https://pubmed.ncbi.nlm.nih.gov/20435004/)
- [Lateral presynaptic inhibition mediates gain control in an olfactory circuit](https://www.nature.com/articles/nature06864)
- [Moth olfactory receptor neurons adjust their encoding efficiency to temporal statistics of pheromone fluctuations](https://pubmed.ncbi.nlm.nih.gov/30422975/)
- [Temporal novelty detection and multiple timescale integration drive Drosophila orientation dynamics in temporally diverse olfactory environments](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1010606)

社会昆虫集体决策：

- [Making good choices with variable information: a stochastic model for nest-site selection by honeybees](https://pmc.ncbi.nlm.nih.gov/articles/PMC2375933/)
- [Stop signals provide cross inhibition in collective decision-making by honeybee swarms](https://pubmed.ncbi.nlm.nih.gov/22157081/)
- [A mechanism for value-sensitive decision-making](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0073216)
- [Sensory coding of nest-site value in honeybee swarms](https://journals.biologists.com/jeb/article/211/23/3691/17956/Sensory-coding-of-nest-site-value-in-honeybee)
- [Negative feedback enables fast and flexible collective decision-making in ants](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0044501)
- [Individual rules for trail pattern formation in Argentine ants](https://pmc.ncbi.nlm.nih.gov/articles/PMC3400603/)

Multi-agent、相关错误和长期记忆：

- [AgentPrune: Reducing Multi-Agent Communication with Graph Pruning](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html)
- [Sparse Communication Topology for Multi-Agent Debate](https://aclanthology.org/2024.findings-emnlp.427/)
- [ReConcile: Round-Table Conference Improves Reasoning via Consensus among Diverse LLMs](https://aclanthology.org/2024.acl-long.381/)
- [Correlated Errors in Large Language Models](https://proceedings.mlr.press/v267/kim25e.html)
- [Free-MAD: Consensus-Free Multi-Agent Debate](https://aclanthology.org/2026.findings-acl.1600/)
- [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html)
