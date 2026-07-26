# Receptor-Gated Ligand Field Comparative Study Plan

状态：预注册草案；仅研究设计，尚无实现、结果或优越性结论

研究基线：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`

研究分支：`codex/receptor-ligand-field-experiments`

当前可执行冻结：
[Experiment Profile v0.2](receptor-ligand-field-experiment-profile-v0.2.md)。
v0.1 在任何 arm execution 前经独立 G0 审计被取代并保留为历史记录。

适用范围：PheroOS protocol-core 的非权威 attention/communication plane，以及位于
protocol-core 之外的独立研究 harness

## 1. 当前结论与研究问题

当前证据只支持以下表述：

> receptor-gated ligand field 是与 PheroOS 边界高度一致、理论动机明确且可证伪的候选
> attention architecture；它尚未被证明优于稀疏通信、blackboard、retrieval routing
> 或学习式 graph pruning。

本研究不尝试证明脱离任务、模型、预算和攻击条件的“普遍最优”。可检验的系统级问题是：

> 在固定 agent、model、tool、ACL、Evidence Ledger、Governance 和 Optimal Commit，
> 并施加相同信息与资源预算时，receptor-gated ligand field 是否在预声明任务分布及
> 独立复验分布上形成更好的 success-cost-robustness Pareto frontier？

经验研究不能证明所有未来环境中的普遍优越性。它可以：

1. 证明确定性的算法不变量；
2. 通过消融识别机制因果效应；
3. 在冻结范围内拒绝零假设并给出效应量与置信区间；
4. 通过独立模型、任务和时间复验建立范围限定的比较证据。

## 2. 不可改变的 PheroOS 边界

研究仅替换 attention/communication controller。Commit truth、Evidence、permission、
fallback 和 output authority 在所有处理组中保持完全相同。

```text
environment/tool observations
        |
        v
common validation + Evidence Ledger
        |
        v
controller under test
        |
        v
non-authoritative percept / retrieval / exploration directive
        |
        v
agent work and newly collected evidence
        |
        v
fixed Optimal Commit + output contract
```

规范性控制条件：

- Hybrid attention 保持 `authority_scope="none"`。
- Controller 不能提交 candidate、创建 evidence、签发 permission 或授权 output。
- 相同 verified evidence 输入必须产生相同 Commit truth；attention 的直接
  commit sensitivity 必须为零。
- 所有处理组使用相同 Evidence Ledger、candidate set、counterevidence、challenge、
  support lease、safe fallback 和 output contract。
- 任何 authority、ACL、cross-tenant 或 output violation 都是关键失败，不能由性能收益抵消。
- 现有 Hybrid v1 ABI、schemas、TCK roots 和兼容行为不在研究分支中原地修改。
- 新语义若最终被证实，仍需独立的版本化 ABI、Trace、migration 和 Conformance。

这些边界已有
[Optimal Commit 双通道](../protocol/optimal-commit-abi.md#two-independent-channels)、
[Hybrid Attention](../../pheroos/governance/attention.py) 和
[channel-separation tests](../../tests/governance/test_hybrid_commit_separation.py)
作为冻结参考。

### 2.1 冻结的 authority oracle

实验开始前冻结以下 artifact：

| Artifact | SHA-256 |
| --- | --- |
| 基线 Git commit | `e447d2c96c40b69bb7f98613e23556be7bbe3d76` |
| Commit TCK v1 | `9255ed7e1298841baaaeee8b139a7ba86df457493dd30d6d7312ce600a1d41e3` |
| Commit TCK v2 | `0cb38415b5429aec17235eff9ea55867afe44d11be8669e80397277c206af00b` |
| Hybrid Replay manifest | `3a2050bc25339adfe7caab1409ca49ae02380824d6ef880113f090daa04a13a0` |

持久实验路径以 Store-backed
`evaluate_hybrid_collective_step_v2(..., attention_only=True)`、Hybrid Replay restart
和 total `evaluate_hybrid_commit_step(request=...)` 为 authority oracle。旧
`evaluate_hybrid_collective_step` 默认 commit 分支不能进入实验 lane。

每个 paired arm 使用隔离的 fresh Store，但固定完全相同的 protocol、run、target、epoch、
current step 和 truth bundle。固定 truth 的 shadow experiment 必须断言：

- attention root 可以改变；
- `attention_commit_authority` 始终为 `False`；
- `hybrid_commit_truth_projection`、commit truth root、leader 和 outcome 完全相同。

Closed-loop experiment 中，attention 可以通过“促使 runtime 收集新的 verified evidence”
间接改变后续 truth；唯一允许的桥是显式 evidence attestation、Governance qualification
和 Store commit。自然语言消息、attention value 或外部 score 不能直接进入 truth。

## 3. 需要新增的系统级假设

原 H1 至 H5 是机制假设。即使五项都成立，也不逻辑推出完整系统优于每个强基线。因此新增：

**H6：系统级范围限定优越性。**

在相同 agent/model/tool/ACL/evidence/authority 条件下，完整 RG-LF 在冻结的
in-distribution 与 out-of-distribution 任务上：

1. task success 对每个目标基线非劣；
2. natural-cost、iso-budget 和 budget-sweep 至少形成一个可复验的成本前沿优势；
3. error propagation、Sybil、stale evidence、alarm abuse 和 topology shift 下不劣，
   且至少一个预注册鲁棒性终点显著更优；
4. authority、ACL 和 output safety 零退化；
5. 结果在独立模型家族和冻结复验集上重复出现。

只有 H6 通过，才允许对具体基线和实验范围使用“优于”表述。H1 至 H5 单独通过时，只能声称
相应机制得到支持。

## 4. 处理组和强基线

所有处理组消费同一种 canonical event/evidence representation，并输出统一的
`PerceptBundle` 概念：subject/evidence references、priority、可逆 affordance 和完整
selection lineage。Controller 的内部表示可以不同，但不能获得其他组不可见的任务答案或
ground truth。

| 代码 | 处理组 | 预注册语义 |
| --- | --- | --- |
| `F` | Full shared communication | 每个 eligible receiver 接收全部 canonical events；使用统一 truncation、ACL 和 evidence dereference 规则 |
| `P` | Current PheroOS scalar pheromone | 冻结当前 `kind + strength`、source cap、decay、diffusion 和 Hybrid attention 行为 |
| `S` | Static sparse communication | 在 dev split 上从 task-dependency、capability 和 matched-density random-regular 图中冻结最佳者；无内容学习 |
| `B` | Strong scoped blackboard | 版本化、append-only、支持 supersession、ACL 和相同 Evidence Ledger；receiver 按固定 schedule 和 global priority 读取 |
| `Q` | Stateless retrieval router | 相同索引、query/role-conditioned top-k；无持续 field、diffusion 或 receiver habituation |
| `G` | Learned graph pruning | 只使用共同可见 metadata，在 train/dev 上训练并冻结 checkpoint；test 与 OOD 不再更新 |
| `R` | Full receptor-gated ligand field | verified event、ligand vector、预算扩散、ACL/receptor、adaptation、inhibition、divisive normalization、blend 和 top-k percept |

`oracle top-k` 与 `random top-k` 只作为诊断上界和下界，不参与优越性主张。

基线不得被故意削弱：

- Blackboard 保留版本、supersession、ACL 和 evidence safety。
- Retrieval router 可使用与 RG-LF 相同的 receiver role/capability metadata。
- Learned pruning 获得与 RG-LF 参数选择相匹配的 train/dev 调参预算。
- Learned pruning 同时报告 inference-only 成本、训练成本和按不同运行寿命摊销后的总成本。
- 每个基线必须先通过 fidelity sanity checks；若采用作者实现，需记录版本和复现实验。

## 5. 两类比较矩阵

### 5.1 共同能力矩阵

所有 controller 共享：

- verified canonical events；
- evidence and supersession metadata；
- independence metadata；
- ACL 和 receiver role/capability；
- 完全相同的 model-visible payload 上限。

该矩阵用于识别 communication/attention algorithm 本身的差异，不能把更好的 Evidence
或权限卫生误算成 receptor field 的收益。

### 5.2 原生系统矩阵

每种方法使用其合理的原生工作方式，但仍共享相同 Evidence 和 authority plane。该矩阵用于评估
部署级外部效度，结果不得替代共同能力矩阵中的因果结论。

H2 至 H5 还需要 RG-LF 内部机制消融；单纯比较 `R/S/B/Q/G` 不能识别这些机制的因果效应。

## 6. 两条执行轨

### 6.1 Trace-driven counterfactual replay

所有 controller 接收完全相同、冻结并带 ground-truth sidecar 的 event/emission stream。
该轨不运行真实 LLM，主要回答：

- 相同输入下选择了哪些 receiver、subject 和 evidence；
- clone、spam、supersession、hazard 和 topology shift 如何改变 attention；
- token/byte、field、storage 和 controller compute 的确定性成本；
- 是否满足 replay、budget、ACL 和 authority 不变量。

该轨是机制因果证据的第一层，不能单独支持真实 LLM task-success 结论。

### 6.2 Closed-loop agent run

Controller 改变 agent 所见 percept 和 evidence；agent 行为又产生后续 observations。
该轨检验：

- attention 是否真正改变证据收集质量；
- 错误是否传播、恢复或导致安全 fallback；
- token、latency、tool calls 和 task success 的系统级效果；
- 在相同 Commit path 下，间接 evidence collection 差异如何影响最终结果。

每条轨再分为：

- `common-payload`：所有方法具有相同结构化信息容量，用于内部效度；
- `native-payload`：保留各方法的自然消息/查询形式，用于外部效度。

## 7. 三种预算制度

禁止只在一个任意 token budget 上比较。

1. **Natural-cost**：每个 controller 按冻结停止规则自然运行，测量真实成本。
2. **Iso-budget**：固定 model-visible tokens、completion tokens、messages、retrievals、
   tool calls、concurrency 和 deadline，比较成功率与鲁棒性。
3. **Budget sweep**：在 full-broadcast 成本的多个预注册比例上绘制完整
   success-cost frontier 和 area/hypervolume。

必须计入：

- prompt、completion、cache 和 evidence dereference tokens；
- serialized bytes、message edges、storage reads/writes；
- model/tool calls；
- controller CPU/GPU time、峰值内存；
- critical-path logical steps、p50/p95 wall latency；
- training、index build 和 embedding 成本；
- timeout、crash、retry、fallback 和未完成 episode。

如果 token 节约被 controller 的 `O(agent × subject × ligand)` 成本抵消，效率主张不成立。

## 8. 任务族

### 8.1 Provider-free deterministic suite

每个 episode manifest 固定 topology、ACL、roles、capabilities、event schedule、ground truth、
causal clusters、attack budget、seed 和 difficulty。

| 任务 | 核心变量 | 主要假设 |
| --- | --- | --- |
| `T1 Versioned-Fact Stream` | update、retraction、conflict、abstention、版本链 | H1、H2、H3、H5 |
| `T2 Correlated-Scout Cascade` | clone ID、同模型/同 prompt/同 evidence、延迟纠错、正确少数派 | H2、H4 |
| `T3 Hazard-and-Recovery` | true/false alarm、deadline、可逆 pause、长期记忆 | H2、H3、H5 |
| `T4 Dynamic Dependency Scheduler` | task/artifact/capability 图变化、拥堵、故障、资源上限 | H1、H2、H3 |
| `T5 Sparse Evidence Search` | 长历史、少量相关 evidence、多跳、knowledge update、组合 holdout | H1、H3、H5 |
| `T6 Exploration/Minority Search` | 隐藏解空间、局部最优、稀有正确候选 | H2、H3、H4 |
| `T7 ACL/Tenant Partition` | 跨权限域 canary refs、共享 subject、攻击流量 | safety gate |

规模曲线：

- simulator agents：`4/16/64/256/1024`；
- events/subjects：从 `10^2` 到 `10^5` 的预注册档位；
- 每档报告 throughput、memory、critical path 和 budget loss。

### 8.2 External LLM confirmatory suite

真实 model/provider、dataset adapter、container、vector store 和 scheduler 全部属于独立研究
harness，不进入 protocol-core。

候选任务必须在预注册冻结时完成 license、version、split 和 contamination 检查：

- [LongMemEval](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html)
  的 knowledge update、temporal reasoning 和 abstention；
- [MultiAgentBench](https://aclanthology.org/2025.acl-long.421/)
  的多种协作场景和 topology；
- reasoning/debate 的冻结子集，用于 sparse topology、conformity 和 error cascade；
- 独立外部 code-collaboration 轨可使用
  [SWE-bench Verified](https://www.swebench.com/verified.html) 的分层子集，但不得把自定义
  multi-agent 分数冒充官方 leaderboard。

真实 LLM 主规模为 `4/8/16` agents。至少覆盖三个模型家族、homogeneous 和 heterogeneous
rosters；模型 artifact、API snapshot、tokenizer、prompt 和 tool versions 必须冻结。

## 9. H1 至 H5 的预注册设计

以下 MESI 是初始科研门槛。Pilot 可基于独立 dev data 调整一次，但必须在查看
confirmatory arm 标签和结果前冻结。

### 9.1 H1：success 非劣，同时降低 token 和 latency

主比较：`R` 对 `F`；`R` 对 `S/B/Q/G` 为预注册共同对照。

共同主终点：

- task-success risk difference `ΔS`；
- total-token geometric mean ratio `G_T`；
- end-to-end latency geometric mean ratio `G_L`。

初始判据：

```text
LCB(ΔS) > -0.03
UCB(G_T) < 0.85
UCB(G_L) < 0.90
UCB(p95_latency_ratio) < 1.05
```

这是 intersection-union gate；任一条件失败均不支持 H1。更少 token 若来自更多失败、
提前退出或较低输出质量，不算收益。

### 9.2 H2：inhibition、normalization 和 habituation 抑制风暴与错误共识

采用 `lateral inhibition × divisive normalization × habituation` 的 `2×2×2`
因子实验，同时对 full RG-LF 做 leave-one-out 消融。

共同主终点：

- false-consensus episode rate；
- duplicate/redundant token ratio；
- attention storm area-over-threshold；
- task success 非劣。

初始判据：

```text
UCB(RR_false_consensus) < 0.80
UCB(ratio_redundant_tokens) < 0.80
UCB(RR_storm) < 0.70
LCB(ΔS) > -0.03
```

`storm` 必须在执行前机械定义，且同时记录 cap 前 demand。通过让系统沉默或仅靠 hard cap
隐藏负载，不支持 H2。Habituation 必须同时测 duplicate suppression 与
new-independent-evidence recovery。

### 9.3 H3：ligand blend 区分复合协作状态

处理组：

1. scalar `kind + strength`；
2. capacity-matched vector without blend；
3. vector with blend rules；
4. full receptor field。

所有处理组看到相同 observations 和 metadata；不能把 ligand 名称直接作为答案标签。
训练、dev 和 confirmatory/OOD 使用不同 task templates、subjects 和 evidence lineages。

主终点：

- held-out affordance/state macro-F1；
- downstream action regret；
- high-risk recall safety guard。

初始判据：

```text
LCB(F1_blend - F1_scalar) > 0.05
LCB(recall_high_risk_blend - recall_high_risk_scalar) > -0.03
downstream action regret is lower after multiplicity adjustment
```

若 one-hot vector 已获得同等结果，则只能支持多维表示，不能支持 blend 规则的额外价值。

### 9.4 H4：independence cluster 抵抗 clone、Sybil 和错误级联

处理组：

- agent-ID diversity；
- oracle true-cluster gate，仅作上界；
- governance-estimated cluster gate，作为可实现系统。

实验改变 clone/Sybil 数量 `1/2/4/8/16`，并交叉：

- homogeneous/heterogeneous roster；
- same/different model、prompt、evidence、tool 和 parent-message lineage；
- cluster false-merge 和 false-split rate。

核心指标：

- false-consensus attack-success curve AUC；
- cumulative error amplification；
- generation-wise `R_err(g)`；
- Sybil amplification slope；
- correct-minority survival；
- clean-task success。

定义：

```text
cumulative amplification =
  downstream new adopters / initially exposed agents

R_err(g) =
  new adopters at generation g+1 / active adopters at generation g
```

“adopt”只从公开 proposal、retrieval 或 action 观测，不读取隐藏 chain-of-thought。

初始判据：

```text
UCB(AUC_false_consensus_cluster / AUC_false_consensus_agent_ID) < 0.70
adjusted UCB(R_err) < 1
LCB(ΔS_clean) > -0.03
```

只有 oracle cluster 成立、可实现 estimator 不成立时，H4 不通过。

### 9.5 H5：fast reversible reflex 与 sparse associative retrieval 双通路

采用 `fast reflex on/off × associative retrieval on/off` 的 `2×2` 因子实验，并加入
unified single-path 对照。

共同主终点：

- dual 对 slow-only 的 deadline-penalized verified mitigation time；
- dual 对 fast-only 的 post-shift normalized performance AUC；
- false-pause/alarm rate；
- ordinary-task success。

初始判据：

```text
UCB(time_dual / time_slow_only) < 0.80
LCB(AUC_dual - AUC_fast_only) > 0.05
UCB(Δfalse_alarm) < 0.02
LCB(ΔS_ordinary) > -0.03
```

Fast path 只能触发可逆 pause、recruit 或 verification request，不能 commit 或执行不可逆
动作。更快但依赖大量误报、未验证 action 或 alarm DoS，不支持 H5。

## 10. 攻击与压力矩阵

每个 controller 面对相同攻击能力、权限和消息预算：

- Sybil / agent-ID churn；
- same-lineage clone；
- high-frequency repeated spam；
- low-dose drip 和 TTL refresh；
- high-degree topology pollution；
- delayed correction、retraction 和 stale-evidence revival；
- forged or persuasive alarm；
- prompt injection hidden in referenced memory；
- ACL/cross-tenant canary；
- network partition、delay 和 out-of-order delivery；
- learned-pruner OOD topology 和 retained-edge adaptive attack；
- correct minority under an incorrect correlated majority。

Optimal Commit 下，错误 attention 应表现为检索浪费、证据收集延迟、安全 fallback 或 deadline
miss，而不能直接形成错误 authority。任何直接 authority/output violation 仍必须为零。

## 11. 随机化、样本量与统计

分析单位是完整 task episode。Agent、message、trail 和 step 是 episode 内重复测量，不能被当作
独立样本。

设计要求：

- 每个 `task × environment seed × model roster × attack condition` 在全部 arms 上配对；
- arm 顺序 block-randomized，并跨时间交错运行以降低 provider drift；
- 每个 arm 使用由 episode ID 派生的隔离随机流；
- workspace、cache、receiver adaptation state 和 private memory 在普通 episode 间重置；
- 只有预声明的 long-horizon episode 可以延续 receiver state，并记录 state root；
- objective receipt 优先；人工或 LLM judge 对 arm 盲法；
- intent-to-run：timeout、crash 和攻击成功都是结果，不能事后删除；
- ground-truth cluster 只存在 sealed evaluator sidecar；controller 只能看到 verified/estimated
  cluster。

Pilot：

1. 每个任务族至少 30 个独立 task clusters；
2. 每 arm 至少 2 个 stochastic repeats；
3. 估计 binary paired discordance、log-cost paired variance、ICC 和稀有事件率；
4. 用 simulation 计算 confirmatory `N`，目标 joint power 至少 90%；
5. 冻结 controller、split、MESI、sample size、analysis code 和最大运行预算。

Confirmatory 每个 task/arm 初始计划至少 3 个 nested repeats，但统计功效仍以独立 task cluster
计算。安全事件若希望零观察时的 95% 上界低于 1%，至少需要约 300 个独立机会；低于 0.1%
约需 3,000 个机会。

分析方法：

- binary outcomes：paired risk difference/ratio、McNemar 或 conditional logistic；
- token/latency：episode-level log ratio、paired cluster bootstrap、p50/p95；
- count/rate：rate ratio；过度离散时使用 negative-binomial sensitivity model；
- deadline：restricted-mean 或 deadline-penalized response time；
- report effect size、multiplicity-compatible 95% confidence bounds 和 heterogeneity；
- H1 至 H5 的 co-primary claims 使用 intersection-union tests；
- 五个 hypothesis families 使用 Holm 控制 family-wise error `0.05`；
- `R` 对 `S/B/Q/G` 的共同对照使用 Dunnett 或 Holm-adjusted paired randomization；
- 大量 per-task、per-class 和高阶交互只作 exploratory，并标记 BH `q=0.05`。

首选固定 sample size。若必须 interim，只允许在 50% 和 75% information fractions 使用
预注册的 O'Brien-Fleming alpha spending。不得根据中期结果修改 endpoints、MESI、task mix、
比较器或最大 `N`。

## 12. Trace-compatible 研究日志

日志采用 versioned NDJSON 或等价不可变记录；ground truth 存放在独立 sealed sidecar。
禁止记录隐藏 chain-of-thought。

事件类型至少包括：

- `run_manifest`
- `episode_start`
- `observation`
- `ground_truth_update`
- `emission_proposed`
- `emission_verified` / `emission_rejected`
- `communication_eligible`
- `communication_selected` / `communication_dropped`
- `field_step`
- `receptor_activation`
- `evidence_retrieval`
- `agent_action`
- `governance_decision`
- `attack_injected`
- `metric_observation`
- `episode_end`

每个记录至少绑定：

- schema/version、run/episode/event/parent IDs、sequence 和 logical time；
- Git commit、branch、preregistration hash、controller/version/config hash；
- dataset/version/split/task seed/difficulty；
- model artifact、prompt、tool、tokenizer 和 RNG hashes；
- actor/principal/role/tenant/scope/ACL；
- subject/candidate/evidence refs、evidence version/status/digest；
- causal lineage、asserted/verified independence cluster、principal/failure domain；
- 全部 eligible edges、selected/dropped edges 和 reason；
- ligand doses、pre/post decay/diffusion/adaptation/normalization；
- receptor profile/state hash、top-k percept；
- tokens、bytes、storage、model calls、controller compute 和 latency；
- reward、fallback、safety、output、field root、ledger root 和 Trace root。

必须记录 controller 在当时有资格看到的完整集合，否则无法审计选择偏差。

## 13. 阶段门与交付物

| Gate | 内容 | 通过条件 |
| --- | --- | --- |
| `G0 Boundary/Prereg` | 冻结 H1-H6、estimands、基线、预算、split、排除和统计计划 | 无实现先于假设；v1 ABI 不变 |
| `G1 Controller Contract` | 统一 canonical input 和 `PerceptBundle`、日志 schema、oracle/random diagnostics | authority scope none；exact replay |
| `G2 Deterministic Simulator` | T1-T7、规模/攻击向量、counterfactual replay | replay/hash 100% 一致；ACL/authority violation 0 |
| `G3 Baseline Qualification` | S/B/Q/G/P fidelity、预算核算、learned checkpoint freeze | 无 strawman；成本完整 |
| `G4 Pilot` | dev-only 调参与方差估计 | 不形成 confirmatory 结论；冻结 MESI/N/code |
| `G5 Confirmatory Mechanisms` | H2-H4 因子和消融、sealed synthetic suite | 所有结果保留；不边看边改 |
| `G6 Closed-loop LLM` | H1/H5、ID/OOD、攻击和预算曲线 | 固定 Commit path、model snapshot 和 split |
| `G7 External Replication` | LongMemEval/MultiAgentBench/可选 code task、时间或模型独立复验 | 不再调参；复验 artifact 完整 |
| `G8 Claim Gate` | H6、Pareto、异质性、negative/null results | 只允许范围限定结论 |

## 14. 证明等级与结论语言

| 等级 | 所需证据 | 允许结论 |
| --- | --- | --- |
| `E0` | 文献和理论动机 | “候选机制” |
| `E1` | deterministic invariants 和 replay | “算法性质得到证明” |
| `E2` | sealed synthetic 消融 | “在受控环境中支持机制 Hx” |
| `E3` | locked closed-loop confirmatory | “在冻结任务/模型范围内优于 baseline X” |
| `E4` | OOD、攻击和独立复验 | “在声明范围内形成可复验优势” |

不得使用事后加权总分宣布“总冠军”。必须报告 Pareto frontier、每个基线的配对结果、task/model
heterogeneity、所有 negative/null outcomes 和 sensitivity analyses。

只有在以下条件全部满足时，才能声称完整 RG-LF 在研究范围内优于每个目标强基线：

1. H6 的 success non-inferiority、cost frontier 和 robustness gates 全部通过；
2. `R` 对 `S/B/Q/G` 的 multiplicity-adjusted pairwise claims 全部通过；
3. confirmatory 和 independent replication 方向一致；
4. 没有 task/model/safety-critical stratum 出现超过预注册 margin 的伤害；
5. authority、ACL、cross-tenant 和 output violation 始终为零；
6. learned baseline 的训练成本和 RG-LF 的规则/调参成本均被完整报告。

如果只在部分任务、预算或基线上获胜，结论必须降级为条件性结果。“最合适方向”只有在
上述范围限定后才是科研上可接受的表达。

## 15. Protocol-core 与外部 lab 的交付边界

本研究分支当前只应承载：

- 本预注册计划；
- 后续版本化、provider-free 的 experiment record contracts；
- pure controller/reducer reference semantics；
- deterministic synthetic vectors；
- Trace 和 Conformance checks；
- provider-free examples 和 tests。

以下内容属于独立研究 harness：

- LLM/provider adapters；
- benchmark datasets 和 license-controlled artifacts；
- embeddings、vector databases 和 retrieval services；
- learned graph-pruning training；
- environment simulation 和 agent runtime；
- Docker task execution；
- experiment scheduler、analytics database 和 dashboards；
- model-specific prompts、secrets 和 paid API lifecycle。

研究结果不能绕过 protocol-core 的版本治理，也不能把实验 runtime、provider 或训练系统带回
PheroOS core。

## 16. 主要效度威胁

- benchmark contamination 和 template leakage；
- model/API snapshot、tokenizer 和 provider drift；
- homogeneous clone agents 被误当独立样本；
- synthetic receipts 比真实工具反馈更干净；
- simulator 忽略网络、并发、队列和尾延迟；
- learned pruning 的 train/test leakage 和训练成本遗漏；
- hand-authored receptors 携带任务答案先验；
- ligand vector 容量大于 scalar comparator；
- blackboard/index/storage/embedding 成本漏记；
- LLM-as-judge bias；
- timeout、crash 或 attack-success 被排除造成 survivorship bias；
- adaptation state 跨 episode 泄漏造成 carry-over；
- 短实验无法代表长期 memory growth、supersession 和 habituation；
- attack simulator 与真实 Sybil、prompt injection 或 persuasive agent 不一致。

若总体显著但关键 task、model 或 safety stratum 方向相反，必须降级结论，而不能用总体平均掩盖。

## 17. 参考研究

- [LongMemEval, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html)
- [AgentPrune, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/bbc461518c59a2a8d64e70e2c38c4a0e-Abstract-Conference.html)
- [Scaling LLM Multi-Agent Collaboration / MacNet, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/66a026c0d17040889b50f0dfa650e5e0-Abstract-Conference.html)
- [Sparse Communication Topology, Findings of EMNLP 2024](https://aclanthology.org/2024.findings-emnlp.427/)
- [ReConcile, ACL 2024](https://aclanthology.org/2024.acl-long.381/)
- [MultiAgentBench, ACL 2025](https://aclanthology.org/2025.acl-long.421/)
- [Free-MAD, Findings of ACL 2026](https://aclanthology.org/2026.findings-acl.1600/)

这些工作用于建立动机和强基线，不构成 RG-LF 优越性的先验结论。
