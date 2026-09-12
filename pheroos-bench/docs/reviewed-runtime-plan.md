> **保存的校正版计划全文 / Preserved reviewed proposal.**
>
> 原始文件：[Ju1se/pheroos-runtime，`b3c0d49` 版本](https://github.com/Ju1se/pheroos-runtime/blob/b3c0d4977c466c02a200d4fe63857682de53ddfd/docs/reviewed-plan.md)。
> 下方正文逐字保留，SHA-256：`02b8a7454cdb6dc29fb6f0cdc5c3c7856736f87861bd73ec2355750ce7a366d5`。
> 这是源码仓库内供离线阅读的计划快照；正文中的“当前/未实现”描述属于校订当时，研究阈值仍未冻结。
>
> 后续交付：[G0/G1 决策和 runtime 仓库](https://github.com/Ju1se/pheroos-runtime)、
> [G1 验收数据](https://github.com/Ju1se/pheroos-runtime/tree/g1-mock-v1/results)、
> [G2/R0 测量结果](../results/r0/RESULTS.md)、
> [WSL2 复现说明](https://github.com/Ju1se/pheroos-runtime/blob/main/docs/replication.md)。
> 获取可执行 G1 runtime 需要单独 clone `https://github.com/Ju1se/pheroos-runtime.git`。

<!-- BEGIN ORIGINAL REVIEWED PLAN -->
# PheroOS：群体执行 OS 构建与实验计划

原提案日期：2026-09-11（America/Los_Angeles）

原审阅快照：Ju1se/PheroOS @ `69062beac1e2a32fdfe0028b9db1cc89dd29261c`

本次校订依据：已合并 PR #32，`0bdf729631e38933446a42494119f0b4f32196cd`；核对本地对应实现提交 `b4845e5972e74425af55ad9f306b17535957c68d`。

范围：计划与当前实现对照、重新运行所附合成诊断，并用现有包的统计函数交叉验证；核实 B5–B7 原始文献。PR #32 的 100 项本地 bench 测试与远端检查是已有证据，本轮没有重新运行完整测试或调用付费模型。

文档性质：**未冻结的研究提案及状态校订，不变更当前支持范围，也不自动授权实施 G0–G5 或 R0–R5。**

## 1. 决策摘要

发展目标是围绕现有 PheroOS 协议核研究群体交互与 agent runtime OS。当前对外定位仍为 governed authority/commit protocol，群体运行时属于拟建的外部研究项目。保留当前协议核；沿用独立 bench 包开展可证伪研究。没有新实证结果前，不恢复 swarm-native 能力表述。

第一项研究不应是“模拟完整蚁群”，而是：**在局部上下文、变化环境和固定资源预算下，溯源感知、允许纠错重新激活的稀疏环境信号，能否比强简单对照减少协作成本，同时保持外部验证成功率？**

OS 工程目标与机制有效性目标分别验收。Runtime 可以工程上正确，实验机制仍然无优势；必须允许这种结果。

## 2. 当前基线与不能丢失的证据

- 当前 README 与 current-support 将项目定位为 governed authority/commit protocol。信息素/attention 是私有实验实现，不是公开 swarm ABI，也没有实证优势声明。[R1,R2]
- 已有 Protocol、Kernel、Driver、Governance、Trace、Conformance，以及 scoped durable authority。继续使用小型 consumer candidate；不为了实验扩大全部 Draft facade。[R1,R2]
- E1 最终 FAIL_RENAME_REQUIRED。该候选 field 的通信字节中位数为 centralized 的 1.96–2.73 倍；不能推广为所有 stigmergy 的失败，但不能把历史结果改成成功。[R4]
- E2 修正弱 gossip 对照后 FAIL。旧 PASS 来自对照无条件复制邻居造成的失败；旧结论不得恢复。[R5]
- E3 当前仅 admission/void pilot，独立采样加多数聚合；没有实际 adaptive treatment 或环境介导执行闭环。[R3,R6]
- 原快照 `69062be` 使用 median，且 admission 的点估计与区间对象不一致。PR #32 已要求显式 `paired_item_mean_v1`，以 item 配对均值评估 admission、主终点和质量地板；median 仅保留诊断。旧配置被拒绝，新 E3 预测仍为 NOT_FROZEN。[R7,R9]
- 原快照在整轮结束后才写调用文件。PR #32 已逐返回写入并 flush，失败后停止后续批次，保留成功同批请求及无效答案的有效 usage；另有 dry-run 和每次运行 max_calls。尚无调用前持久预留、进程崩溃恢复或美元硬上限。[R6,R8,R9]

### 2.1 增量工作清单

| 能力 | PR #32 后的状态 | 后续验收 |
|---|---|---|
| 支持矩阵、模块归属、121-symbol Draft consumer candidate | 已有 | G0 引用现有权威清单，不复制另一份支持事实源 |
| 安装后消费者与独立 Store 替换 | 已有合同测试 | 新 runtime 必须实际接入公开路径；现有 fixture 不等于运行时 |
| item 配对均值、版本迁移、零宽区间诊断 | 已有，E3 未冻结 | 新实验声明自己的抽样单元、权重与判据 |
| 缺失/重复数据、模型漂移、未知费用校验 | 已有部分 R0 测试 | 新增进程终止和恢复边界，勿把受控异常当作任意崩溃 |
| 普通平坦 cell 合法性 | E3 仍有旧强制方差断言 | R0 单独验证，不悄悄重解释 E3 历史或判据 |
| 调用前预留、恢复后保留未知支出 | 未实现 | G1 所需最小执行账本先实现；金额定价另行校准 |
| taskboard、worker 生命周期、租约恢复与局部动作闭环 | 未实现 | 外部 G1 工程验收；不据此判定机制有效 |

## 3. 生物机制的功能映射

| 原始研究启发 | 建议工程对应 | 不应声称 |
|---|---|---|
| 收获蚁通过成功返回者接触率调整外出活动 [B1] | 根据单位成本的有效任务进展调整招募，而非 agent 自报信心 | 所有蚂蚁都通过同一种信息素工作 |
| 私有路线记忆与社会信息可以互补 [B2] | 小型私有工作记忆 + 局部共享提示，允许独立反证 | 个体完全无记忆即可产生可靠复杂智能 |
| 拥挤减少招募信号沉积 [B3] | 任务拥堵反压、重复证据去重、抑制过度招募 | 更多正反馈一定更好 |
| 蜂群交叉抑制能解除同等选项僵局 [B4] | 区分行动协调和真值判定，避免无限争论 | 达成一致证明结论正确 |
| 环境状态可承载跨个体协作 [B5] | 共享可执行 artifact、测试回执、任务状态影响下一步行动 | 一个信息素分数等于完整执行环境 |

“来源分组、原子任务领取、预算账本、fencing token、版本失效”是工程设计，不冒充动物机制。

## 4. 系统边界

reference runtime 按现有仓库约定外置，采用独立包/仓库；不立即搬动 core 或现有 bench。当前协议仓库不因这份提案自动变成 umbrella monorepo。若未来要改为同仓多包，应另作明确的仓库边界决定：

```text
PheroOS ecosystem
  protocol-core   现有项目；版本化契约、权限、提交、Trace、Conformance
  reference-runtime  新增；生命周期、任务板、上下文、调度、资源控制
  runtime-adapters   初期与 runtime 同包；模型、工具、执行沙箱、持久存储
  pheroos-bench      现有独立研究包；算法候选、环境、对照、测量与统计
  applications      代码/研究等领域任务定义，不进入 core
```

依赖只能单向：runtime 和 bench 使用公开 core；core 不导入它们。实验策略通过 runtime 的窄接口注入；runtime 默认不依赖 bench，bench 可作为外部调用者装配候选策略。外部运行时先复用已安装包的 Driver/Store/Trace 和 Baseline Output 消费路径；任务租约和策略状态不自动获得 Governance authority。

**这是一层运行在现有操作系统之上的 agent OS 服务，不是重写 Linux 或 CUDA。**

### 4.1 最小运行时能力

1. 生命周期：创建、等待、恢复、取消、退出；长调用的取消以调用边界和 provider 能力为限，不保证远端已经停止计费。
2. 任务：依赖图、版本、可检验完成条件、独占或共享工作声明、租约、失败重分配。
3. 上下文：私有工作集、按相关性分配的局部任务视图、共享 artifact 引用；没有强制全局聊天记录。
4. 资源：调用前预算预留、并发上限、实际 token/时间/存储字节计量、未知花费状态。
5. 执行：工具能力和权限检查、沙箱、幂等约束、结果验证。
6. 恢复：可持久化任务状态、调用事件日志、租约失效、重复/乱序处理、可重建注意力状态。

全局资源调度不是“全知模型经理”。调度器可以是确定性代码，只约束预算、合法任务与公平性；agent 基于局部状态做具体选择。

### 4.2 任务与成果板

建议的 runtime 私有记录：`GoalSpec`、`WorkItem`、`ArtifactRef`、`OutcomeReceipt`、`Lease`。名称均为提案。

`GoalSpec` 包含目标、约束、预算、终止条件和验证器。agent 可提出子任务，runtime 在声明/版本边界接纳，不把任意生成文本直接变成有权限的候选。验证器的能力边界必须记录，测试通过不证明全部语义正确。

任务状态示意：

```text
pending -> ready -> leased -> running -> proposed -> verified -> done
                          \-> failed -> ready / terminal_failure
任意合法阶段 -> cancelled / deadline_exceeded
```

`proposed` 与 `verified` 不能合并。任务 artifact 可被后续 agent 读取；环境应通过真实依赖、需求和测试结果触发下一步，而不是由“蚂蚁/蜜蜂角色”硬编码完整流程。

### 4.3 三类存储不可混用

- Durable artifact/evidence：版本、来源、结果、权限与引用；衰减注意力不删除证据历史。
- Attention projection：有界、可过期、可重建；只改变任务优先级/被谁观察。
- Private working set：每个 agent 有容量预算；可保留局部假设、反例与近期失败。

历史 artifact 跨任务复用必须附环境/依赖版本与再验证，不将训练集或 benchmark 测试答案混进技能缓存。

### 4.4 第一个闭环

```text
agent 读取局部可领取任务和 artifact 引用
 -> 领取任务租约
 -> 执行有限工具/模型调用
 -> 提交 artifact 和可核验输出
 -> 外部测试/环境产生结果回执
 -> 更新任务图与局部 attention
 -> 其他 agent 的下一次任务/工具选择改变
```

若“关闭环境信号”只改变最终排序而不改变任何中途行动，就没有展示协作闭环；需要另行命名为候选重排实验。

## 5. 第一项机制：稀疏、去重、可纠错的信号

### 5.1 最小字段

```text
signal_id, origin_event_id, causal_parent_ids
scope_ref, task_ref, task_version, subject_ref
source_ref, source_version, dependence_group
kind, strength, expires_at, supersedes
artifact_ref, outcome_ref
```

这些字段先在 bench/runtime 私有使用，不新增 core 公共 ABI。来源独立性未知时显式为 unknown；不同 agent ID 不能自动算不同独立证据。

### 5.2 可检验规则

- 同一 origin 的复制不会增加独立支持数。
- 只向有相关 capability/任务依赖的消费者提供局部视图。
- 一般重复消息进入去重/抑制窗口。
- 来源版本更新、有效反证、任务约束改变，可重新激活通知；不得因为“之前看过相似文本”屏蔽纠错。
- stop/cancel 与授权拒绝仍由可靠控制路径执行，不能被实验 attention gate 丢弃。
- 活跃领取者达到任务容量时，降低继续招募的优先级；不能用抑制替代任务租约的排他性。
- 暂停招募不等于认定方向错误；低注意力不等于低真值。

第一版用精确来源/版本键和任务标签，不先接 embedding 相似度。后续若加入语义检索，应把 embedding、索引更新与检索成本计入。

### 5.3 第一阶段不要加入的复杂性

不同时训练 neural receptor、进化策略、元认知 coordinator 和多级参数自适应。优先比较：精确去重 + TTL；相关性路由；版本驱动重新激活；拥挤反压。新增一个机制就增加一个匹配消融。

不需要模拟二维气味传播。语义邻域先由 task dependency、artifact dependency、capability 和 scope 定义；连续扩散只有在对照实验支持时再加入。

### 5.4 后续数值 field 的最低要求

若研究扩散场，应声明传播图、逻辑时间、来源/衰减、归一化、采样间隔、局部读写成本。可以从有界非负权重的稀疏传播算子开始；所有未显式新增的传播不得凭复制产生新的独立证据。裁剪保证幅值有界，不等于保证收敛或正确决策。必须测振荡、锁定、噪声放大、响应迟滞与稳定/适应速度权衡。

## 6. 新实验系列：不得覆盖 E1/E2/E3 历史

采用新编号 R0–R5。每次配置冻结后记录源代码、环境、数据、模型版本、对照参数、预算、统计规则和否定判据。任何看过结果后的机制变动都成为新实验。

### R0：仪器与执行可信度

**目标：**证明记录与统计在正、负、无效输入下表现正确，不证明机制有效。

- identical-arm：相同轨迹复制到两臂，成功率差应为零。
- 已知优势的合成正对照；无信号负对照。
- binary paired data 的 mean/median estimand 对照；平坦跨 cell 的合法样本。
- duplicated/missing/shuffled records 验证；同一 world 多 agent 不能当独立样本。
- 对 worker 与协调进程分别在 dispatch 前、dispatch 后、收到响应、持久提交前后注入终止；以“回执持久提交完成”为接收确认边界。收到但尚未提交就崩溃时允许 unknown_outcome，不得伪称零成本；持久提交后的回执必须恢复。
- 调用后丢响应进入 unknown_spend，而非 0 token；预留预算不能立即释放后再发新请求。
- 完整运行、任务超时、拒绝、任务失败按预注册 episode 规则计入结果；不得只比较成功子样本成本。缺失或损坏的测量记录需要显式 INVALID/ABORT，不能冒充统计 FAIL，也不能静默删样本后继续宣称完整实验。

**退出条件：**以上确定性测试通过，结果目录不覆盖历史；仍不得宣称候选算法胜出。

### R1：重复信息与环境更新

**任务：**多个局部 agent 获得带来源的证据片段；大量消息是复制；运行中有效来源/约束改变，需要发现旧结论失效。环境持有 ground truth，策略端无答案访问。

**主假设：**相对于 TTL+去重的强简单对照，相关性与版本驱动机制在外部验证成功率非劣前提下减少总交互成本。

**建议对照：**全量相关共享；稀疏随机（匹配边数/预算）；来源去重+TTL；候选策略；去掉重新激活的消融。

**指标：**每个完整 episode 的成功率、总输入输出 tokens、字段编解码与读写字节、变更到首个有效修正的延迟；重复放大、错过纠错作为过程指标。

**解释：**若只比“全量群聊”好而不能优于来源去重+TTL，不支持复杂仿生机制的必要性。

### R2：动态分工和拥挤

**任务：**持续到达、有依赖、能力要求不同的 WorkItems；某一工具成为瓶颈；中途部分 workers 退出/恢复。先用确定性小程序 agent 排除模型能力差异。

**对照：**能力匹配 FIFO、工作窃取、优先级队列或简单 bandit、中心 manager；均可采用合理故障恢复。

**干预：**只改变拥挤反压或边际有效进展驱动招募；其他策略固定。

**指标：**外部验证任务吞吐、截止时间内完成率、p95 等待、重复执行、饥饿、恢复时间、全部调度与通信成本。

**解释：**角色分化或任务分工图只是过程描述，不是性能终点。

### R3：真实 LLM、共享成果闭环

先选择两个小而可核验任务族：

- 小型代码库修复：agent 发现失败、复现、提交补丁、补充测试、复核；保留 hidden tests；所有策略可访问同一工具能力。
- 封闭证据环境：跨文档约束和版本更新，输出有来源的结构化答案，确定性检查来源与字段；不以主观文字润色作主要评分。

**对照：**同模型单 agent 的多步工具循环；独立多样采样+相同验证器；manager/图工作流；稀疏 blackboard；候选局部策略。

**资源：**在同一总体预算下比较，而非每个 agent 都给单 agent 一样的完整预算。选择器/验证器/强模型升级都计费。

**解释：**数学单题的独立投票可以校准单体能力/采样收益，但不能单独证明 OS 群体交互。

### R4：能力、内存与群体规模边界

校准后选择小/中等模型，至少跨两个模型家族进行复现。规模可先取 N=1,2,4,8,16；上下文容量选择满足协议与工具基本输入的多个档位，不机械强制超小窗口。

分别报告：固定总预算曲线；固定截止时间下的完成率/成本曲线。它们回答不同问题。

加入“不需要协作”和“强顺序依赖”负对照。群体策略应该允许退回单 agent，而不是为所有任务增加通信。生成多样性和独立来源覆盖分别测量；更换角色 prompt 不证明错误独立。

### R5：OS 可靠性与失效恢复

按威胁模型分别注入：worker 死亡、共享存储暂时不可用、coordination service 失效、消息重复/乱序、陈旧租约、工具执行完成但回执丢失、来源污染。

不得把“中心对照不许备份、field 可以复制”当公平比较。按基础设施预算匹配副本、队列和恢复机制；也可以分别报告架构固有部署成本。

目标：不越权、不因旧租约重复产生副作用、能恢复可重试任务、无法确定时明确失败/等待；保证范围依赖工具幂等和后端契约。不能对任意外部 API 承诺 exactly-once effects。

## 7. 统计与账本设计

### 7.1 主 estimand

新二元成功实验建议：

`Delta_Q = mean_over_items(mean_over_repetitions(Q_candidate - Q_control))`

在任务/世界层级做配对重采样；重复运行嵌套在任务中。跨任务族汇总权重预先指定。不得以 agent、token、通信轮次数扩大有效样本量。

如果研究确实关注中位数，保留 median，但不能解释为平均准确率差。PR #32 已完成 E3 的显式方法修正，附带的 bootstrap_diagnostic.py 是该区别的合成诊断，不能再描述为尚未修复的当前漏洞，也不是项目性能实测。

### 7.2 建议验收结构

预先定义一个主要质量非劣界限与一个成本改善终点。示例：质量差的单侧置信下界高于 -2 个百分点，且平均 episode 总成本比的单侧上界小于 0.80。**这些数字仅是讨论用设计示例，不是最终门槛。**应根据实际任务风险、独立 pilot、效应大小和功效分析冻结；小样本不能支撑很窄的非劣界限。

恢复延迟可作为独立预注册实验的主要终点，不必在同一个小实验里强求全部终点成功。多重选择、从多个策略挑最优、跨多个任务族推广均需相应推断控制与保留测试集。

### 7.3 调用状态账本

```text
planned -> budget_reserved -> dispatched -> received -> scored
                                     \-> unknown_outcome / unknown_spend
```

dispatch 前原子写入计划与预留；回执持久提交后才向调用方确认接收；异常不抹掉已提交回执。使用调用上限和在途最大成本预留，实际 usage 结算；provider 无法界定的费用保留为未知，不伪造精确节省。仅 flush 不构成主机掉电耐久性保证；声明要保证的进程/主机故障范围和后端持久提交语义。

取消与 dispatch 必须有同一个可验证的先后边界。取消提交后不能出现新的 dispatch；此前已发出的调用可能继续产生费用。恢复不得把 unresolved 预留释放再重复请求，也不得对任意非幂等外部调用自动重发。第一版 mock 可以按固定调用单位预留；真实货币保证需要价格版本和可执行的输入/输出上界。

一个不依赖完整模型响应的任务/调用事件日志就足够起步，不另造通用企业账本框架。敏感输入不写入公开结果，必要时用本地受控 artifact 引用和内容摘要。

## 8. 可交给编码代理的构建目标

所有目标默认：可编辑提案归属的 runtime/bench；**不修改冻结实验结果，不运行付费模型调用，不创建远程发布，不恢复私有 attention 导出，不削弱已有 core 契约来通过测试。**

### G0 — 冻结可核验基线、开放独立研究空间

输入：当前 SHA、README、AGENTS、current-support、E1/E2结果、E3数据契约。

交付：一份简短设计决策，引用现有支持矩阵，区分“已通过声明合同测试、仍为 Draft 的 authority core”与“研究中的 collective runtime OS”；复用现有历史结果索引，必要时补充不可变版本/校验记录及新实验路径规则。复用现有 core/bench 依赖与安装检查；新增 runtime 出现后再接入实际边界测试。

验收：旧实验和快照引用未变；没有 runtime 依赖流入 core；没有把历史失败改成宣传成功；新的目标无需修改旧实验终点。

### G1 — 最小可运行 OS vertical slice

交付：外置的独立 runtime 包，一个 mock model、一个 deterministic tool、一个持久存储适配器；FIFO 与简单局部 blackboard 两个可替换策略。以一个可验证任务形成最小闭环，再按实际归属拆模块，不预先为所有模块名建立框架。

G1 的恢复要求依赖最小持久状态：任务/租约事务、计划与调用单位预留、dispatch 与回执事件、unknown_outcome 恢复规则。这部分是 G1 前置条件，不能全部推迟到 G2。两种策略共享任务、工具、预算与验证器，第一版只改变下一项任务的选择。

验收：可运行 N=1/4/8 的相同任务；可创建/取消/恢复；中止某个 worker 后工作租约可回收；停止已取消任务的新调用；artifact 保持 scope/version；每个动作可追到任务和资源事件；无需改动 core public ABI。

不要求：证明 swarm 优势、多机 BFT、图形界面、复杂神经元模型、插件市场。

实施前明确四项：一个具体可核验任务；单机后端与事务/故障边界；取消/租约版本及未知预留的恢复规则；声明 target/action 经公开 core 路径授权的位置。旧 worker 的过期 lease 不能提交新的成果或副作用，策略评分与本地验证器均不能自行授予执行权限。

### G2 — 统计仪器与预算持久化

交付：复用 PR #32 的统计与记录反例，完成 R0 尚缺的进程故障测试、恢复后预留对账及合法平坦 cell 处理。新研究使用显式版本的分析入口，不静默改变 E3；需要时新增一个小入口，避免复制整套统计模块。真实货币计价与可执行上界独立校准。

验收：相同策略无假优势；均值 estimand 能识别已知均值增益；普通平坦 cell 不被直接判为坏数据；模拟中途崩溃保留此前回执；输入缺失和运行失败不被静默删样本。

### G3 — 一个机制、一个配套实验

交付：私有来源/版本感知策略；R1全部强简单对照和去掉纠错重新激活的消融；pilot/confirmatory隔离。

验收：克隆消息不增加独立支持；合理版本变更能重开注意力；控制消息不被普通抑制规则丢弃；每次压缩/路由成本有记录；不访问 ground truth；预注册冻结后代码/阈值不变。

性能负结果也是合格研究交付，但不得将机制晋升为默认策略。

### G4 — 动态分工 + 真实模型闭环

交付：先 R2，后小规模 R3；一个模型适配器；单 agent、独立采样、manager、blackboard与候选方法共享 tools/budgets/verifier；真实调用仅由用户显式授权启动。

验收：日志能证明一个 agent 的可验证成果改变另一 agent 的后续行动；两个任务族；无隐藏强模型补贴；报告完整质量—成本—延迟曲线；旧静态投票不得重新贴标签为群体闭环。

### G5 — OS release candidate，而非 swarm 宣传发布

交付：清晰 lifecycle SDK、故障注入集、可恢复示例、每个后端的能力与保证矩阵；profile包含单体/简单协作/实验策略；用户可选择不使用信息素。

验收：R5工程保证通过；外部消费者无需 private imports；真实模型版本与环境锁定；性能结论限定在实际测试任务/配置；默认策略只采用证据支持且维护成本合理的最简单方案。

## 9. 后续升级顺序

先最小闭环与测量，再局部稀疏通信，再动态分工，再异构模型升级，再跨任务技能复用，最后视需要研究学习型受体、跨节点传播和分布式容错。

“没有领导的任务选择”与“没有任何基础设施管理”不是同一件事。初期使用单机 task store 与确定性预算调度器完全合理；之后再用故障与扩展实验判断是否需要分片。

## 10. 成功定义

项目成功不是看信息素种类、层数、agent数量或是否出现一致意见，而是：在明确任务族与预算内，弱单体组成的系统能否在可验证完成率、总成本、延迟或失效恢复上拓展强简单对照的能力边界，并能解释来自哪个机制。

若稀疏 blackboard 已经足够，就把它作为默认；研究中的“仿生”不得成为不能删除复杂代码的理由。

## 11. 来源与阅读路径

### 仓库一手资料

R1–R8 为原提案在 `69062be` 的引用。讨论当前实现时以 PR #32 / `0bdf729` 的同路径内容及 R9 为准；E1/E2 的冻结证据和版本保持原样。

[R1] README.md（尤其 Project Status、Architecture、Non-Goals）。
[R2] docs/protocol/current-support.md；AGENTS.md。
[R3] pheroos-bench/README.md。
[R4] pheroos-bench/results/E1-negative-result.md。
[R5] pheroos-bench/results/e2/RESULTS.md。
[R6] pheroos-bench/E3-data-contract.md。
[R7] pheroos-bench/src/pheroos_bench/e3_verdict.py：版本声明、paired_item_differences、_ci_payload、assert_nonzero_cell_variance。
[R8] pheroos-bench/src/pheroos_bench/e3_llm.py：逐返回回执写入、_ChatResponseError、调用上限与 ABORT 元数据。
[R9] https://github.com/Ju1se/PheroOS/pull/32；pheroos-bench/E3-data-contract.md；pheroos-bench/results/e3/prediction.md（NOT_FROZEN）；tests/test_e3_verdict.py 与 tests/test_e3_llm.py（bench 内）。

### 原始研究与官方文档

[B1] Prabhakar, Dektar, and Gordon. 2012. “The Regulation of Ant Colony Foraging Activity without Spatial Information.” PLOS Computational Biology 8(8): e1002670. DOI: 10.1371/journal.pcbi.1002670.
[B2] Czaczkes, Grüter, Jones, and Ratnieks. 2011. “Synergy between Social and Private Information Increases Foraging Efficiency in Ants.” Biology Letters 7(4): 521–524. DOI: 10.1098/rsbl.2011.0067.
[B3] Czaczkes, Grüter, and Ratnieks. 2013. “Negative Feedback in Ants: Crowding Results in Less Trail Pheromone Deposition.” Journal of the Royal Society Interface 10: 20121009. DOI: 10.1098/rsif.2012.1009.
[B4] Seeley et al. 2012. “Stop Signals Provide Cross Inhibition in Collective Decision-Making by Honeybee Swarms.” Science 335(6064): 108–111. DOI: 10.1126/science.1210361.
[B5] Pal, Wang, and Buehler. 2026. “SwarmWorld: Stigmergic Technological Evolution in Societies of Language-Model Agents.” arXiv:2608.26081v1, 2026-08-26. 预印本；不证明所有任务的群体优势。
[B6] Mei et al. “AIOS: LLM Agent Operating System.” arXiv:2403.16971v5，2025-08-12；COLM 2025。OS 服务架构的相关先例，不把它的实验收益移植为 PheroOS 收益。
[B7] Kim et al. 2026. “Towards a Science of Scaling Agent Systems.” arXiv:2512.08296v3，2026-04-08。强调任务—架构匹配与预算控制；不把其经验阈值当普适法则。
[B8] LangChain 官方文档，“LangGraph overview”，访问日期 2026-09-11。已有 durable execution、memory、human-in-the-loop 等运行时能力，不能声称主流系统均没有这些功能。

## 12. 附带合成诊断

bootstrap_diagnostic.py 与 bootstrap_diagnostic.json：100个配对二元题目中，候选胜30、负5、平65；平均差0.25，中位数0；10,000次重采样、seed37，中位数95%百分位区间[0,0]，均值区间[0.15,0.35]。它只展示 estimand 区别，不是置信区间方法的普适性能证明，更不是 PheroOS 性能实测。

本次已重新执行附件 diagnose()，并用当前工作树中的 pheroos_bench.e3_verdict.paired_percentile_ci 在相同输入下交叉核对，两组区间一致。附件脚本和 JSON 未被覆写；该诊断没有运行任何模型，也未生成 R1 或 E3 的正式判决。
