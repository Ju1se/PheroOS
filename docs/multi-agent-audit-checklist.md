# Multi-Agent 分工审计测试清单

这份清单用于判断 runtime 是否真的做到清晰分工，而不是把多个 prompt 串起来聊天。

## 评分标准

每项按 0-2 分：

| 分数 | 含义 |
| ---: | --- |
| 0 | 不符合，职责混乱或没有证据 |
| 1 | 部分符合，但边界不清或偶尔越权 |
| 2 | 明确符合，有稳定流程和输出证据 |

总分率：

| 总分率 | 结论 |
| --- | --- |
| >=85% | 架构清晰，可以日常使用 |
| 70%-84% | 基本可用，但需要优化边界和验证 |
| 50%-69% | agent 分工形式化，实际效果不稳定 |
| <50% | 不是真正 multi-agent，只是多个 prompt 拼接 |

## 核心红线

| 红线 | 严重失败信号 |
| --- | --- |
| Writer 编事实 | Writer 加入 Research/Data/Domain 没有提供的数据、新闻、公司事实或 citation |
| Research 下最终判断 | Research 直接说买入、避免、论文结论成立等 |
| Data 没有公式 | Quant/Data 给目标价、比率、回测结果，但没有假设、公式、计算步骤、限制 |
| Critic 只会夸 | Critic 只说整体不错，不找漏洞、不分 severity、不提最小修改 |
| Orchestrator 不控成本 | 简单问题固定调用所有 agent |

## 审计表

| 模块 | 审计问题 | 分数 0-2 | 证据 | 修改建议 |
| --- | --- | ---: | --- | --- |
| Orchestrator | 是否正确判断任务类型？ |  |  |  |
| Orchestrator | 是否避免无意义调用？ |  |  |  |
| Orchestrator | 是否能处理 agent 冲突？ |  |  |  |
| Memory | 是否只提供相关上下文？ |  |  |  |
| Memory | 是否避免越权判断？ |  |  |  |
| Research | 是否使用可靠来源？ |  |  |  |
| Research | 是否检查资料日期？ |  |  |  |
| Research | 是否提供反面证据？ |  |  |  |
| Data / Quant | 是否展示公式和假设？ |  |  |  |
| Data / Quant | 是否能复现计算？ |  |  |  |
| Data / Quant | 是否有敏感性分析？ |  |  |  |
| Domain Expert | 是否基于证据做判断？ |  |  |  |
| Domain Expert | 是否避免空泛观点？ |  |  |  |
| Writer | 是否没有新增事实？ |  |  |  |
| Writer | 是否保留限制条件？ |  |  |  |
| Final Judge | 是否做最终事实/逻辑把关？ |  |  |  |
| Critic | 是否真正反驳结论？ |  |  |  |
| Critic | 是否指出 high-severity 问题？ |  |  |  |
| Executor | 是否只执行授权任务？ |  |  |  |
| Executor | 是否报告执行结果和错误？ |  |  |  |
| Handoff | agent 之间交接是否结构化？ |  |  |  |

## 标准分工

| Agent | 只负责 | 不应该做 |
| --- | --- | --- |
| Orchestrator | 分类、拆解、选 agent、控成本、设停止条件 | 直接编结论 |
| Memory | 提供相关用户偏好、历史要求、rubric、框架 | 下判断 |
| Executor | 执行工具、读写文件、运行命令、调用 API | 投资/学术/商业判断 |
| Research | 找来源、抽事实、标日期、可靠性、限制 | 最终建议 |
| Quant | 假设、公式、计算、敏感性、数据限制 | 商业叙事 |
| Domain Expert | 基于 Research/Quant 做专业判断 | 编事实、脱离数据 |
| Critic | 反驳、查 overclaim、查证据和计算 | 泛泛夸奖或重写全文 |
| Writer | 整合表达、适配格式和风格 | 新增未经验证事实 |
| Final Judge | 最终事实/逻辑把关、最小修正 overclaim | 新增事实或重写成另一篇 |

## 用例测试

### A. 简单问题

任务：

```text
解释什么是 ROIC。
```

合格：

```text
Orchestrator -> Writer
```

不应调用 Research、Quant、Domain、Critic、Executor 或 Final Judge。

### B. 投资分析

任务：

```text
分析药明康德是否符合价值投资逻辑。
```

合格：

```text
Orchestrator -> Executor -> Research -> Quant -> Domain Expert -> Critic -> Writer -> Final Judge
```

必须检查最新来源、财务数据、估值纪律、alpha 来源、反方风险和 source gap。

### C. 论文/报告审计

任务：

```text
检查我的 report 是否符合 rubric，并指出需要修改的地方。
```

合格：

```text
Orchestrator -> Memory -> Domain Expert -> Critic -> Writer -> Final Judge
```

必要时加入 Executor 读取文件。必须逐项对照 rubric，区分 major/minor issue。

### D. 代码开发

任务：

```text
帮我设计一个本地小模型 multi-agent 框架，支持 OpenAI-compatible API 和 Ollama。
```

合格：

```text
Orchestrator -> Executor -> Domain Expert -> Critic -> Writer -> Final Judge
```

需要最新框架信息时加入 Research。必须覆盖模块设计、API abstraction、config、error handling、模型路由和测试样例。

## 一句话版本

Research 只找证据，Data 只算数据，Domain Expert 只做专业判断，Writer 只负责表达，Critic 只负责反驳，Executor 只负责执行，Final Judge 只做最终事实/逻辑把关，Orchestrator 负责把它们串起来。
