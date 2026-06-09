基于你上传的这版说明，我的判断很直接：

> **你现在已经有 AI-as-OS + PheroOS 的核心形态，但还没完全达到“真正完整”的 AI-as-OS / PheroOS。**
> 现在最需要做的不是继续加 agent，而是做 **强制执行审计、插件边界审计、数据血缘审计、事件可复现审计、第三方能力安全审计、跨场景泛化审计**。

你的系统当前已经具备：OS Kernel 识别任务、推导 capability、检查连接、自动启用低风险能力、生成 committee plan、Runtime Materializer 热装配 RuntimeContext，再交给 LangGraph 执行；PheroOS 则负责运行中用 signals、stop-signal、quorum、evidence gate 治理 agent 行为。 连接控制也已经按“secret 不进 prompt、不进日志、不返回前端，agent 只拿 connection handle / capability handle”的方向设计。 Capability / Agent 插件系统也已经有了 entrypoints、agent manifest、workflow/data/evidence/ui schema 的方向。

但要成为真正的系统，而不是强原型，还要补齐下面这些。

---

# 1. 先给当前系统定级

我会把你现在系统定为：

> **AI-as-OS + PheroOS research prototype：基本成立。**
> **production-grade AI-as-OS / general PheroOS runtime：还没完全成立。**

当前已经达标的点：

| 维度                             | 当前状态                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| AI-as-OS 控制平面                  | 已有 OS Kernel、Capability Registry、Agent Registry、Runtime Materializer、RuntimeContext   |
| 连接与 secret 管理                  | 已有 Connection Control Plane，secret 不直接暴露给 agent/frontend/trace                        |
| Capability 插件边界                | 已有 `capability.json`、agents、workflow/data/evidence/ui entrypoint 方向                   |
| Agent 插件                       | 已有投资委员 + PheroOS governance actors                                                    |
| 投资研究 workflow                  | 已有 WRDS → Metric Registry → Data Gate → Committee → Writer / Final Judge              |
| PheroOS 信号治理                   | 已有 typed pheromone field、target、authority、lifecycle、stop-signal、quorum、evidence graph |
| Writer / Final Judge guardrail | 已经设计为阻断 formal valuation bypass、raw WRDS leak、unsupported claim 等                     |
| Decision Debugger              | 已有 timeline / why-blocked / why-committed / evidence-graph / agent-allocation API 设计  |

当前还没完全达标的点：

| 维度                                    | 缺口                    |
| ------------------------------------- | --------------------- |
| 是否所有治理 actor 真正参与 runtime enforcement | 需要代码级审计               |
| Capability entrypoint 是否真的驱动 workflow | 需要验证，不应只是 manifest    |
| Graph 是否仍然过重                          | 大概率仍需拆分               |
| Trace 是否 event-sourced、可 replay       | 需要加强                  |
| Stop-signal 是否有 resolve 机制            | 需要补                   |
| Evidence Graph 是否强绑定 final claim      | 需要补硬约束                |
| 第三方 capability sandbox                | 还不够                   |
| 多租户 / RBAC / 生产级 secret / DB          | 还没到 production        |
| 泛化到 coding/research/compliance        | 还偏 investment runtime |

一句话：**方向对，骨架强，但你现在要做的是“系统硬化”，不是“功能堆叠”。**

---

# 2. 什么才算真正的 AI-as-OS？

真正的 AI-as-OS 不是“有很多 agent”，而是满足这些硬标准：

```text
1. OS Kernel 只做控制平面，不做业务推理。
2. Capability 是真正插件，不是硬编码配置。
3. Agent 是可插拔执行单元，不能自己拿 secret / tool / model。
4. RuntimeContext 是每次 run 的安全执行上下文。
5. 所有 tool 调用必须经过 ToolRegistry。
6. 所有 model 调用必须经过 ModelGateway。
7. PermissionPolicy 是高风险行为的硬闸门。
8. SecretStore 永远不把明文暴露给 prompt / agent / frontend / trace。
9. Workflow 能由 capability entrypoint 提供，而不是都塞进 graph.py。
10. Trace 能解释 why blocked / why committed / why this agent。
11. 插件安装、运行、权限、网络、文件、secret 都有 sandbox。
12. 系统可以迁移到新 domain，例如 coding / research / compliance，而不是只服务 investment。
```

你现在已经有很多 OS 特征：资源发现、驱动/插件、权限管理、进程装配、调度、I/O 管理、安全边界、可观测性、用户可组合 agent 等。你的架构说明里也已经把这些和 Capability Registry、Permission Policy、Runtime Materializer、Tool Registry、Model Gateway、SecretStore、PatrollerGate、DataGate、Trace Store、Evidence Graph 对应起来。

但你要真正完整，必须继续审计：**这些边界是不是强制执行，而不是只是文档约定。**

---

# 3. 什么才算真正的 PheroOS？

真正的 PheroOS 不是“trace 里有信号”，而是满足：

```text
1. Agent 只能释放 signal，不能自己把 signal 变成 verified / blocking。
2. Signal 有 canonical target，不能通过 target alias 绕过。
3. Signal 有 authority level，Data Gate / PermissionPolicy / SignalVerifier 权威高于普通 agent。
4. Signal 有 lifecycle：proposed / contested / verified / blocking / resolved / rejected。
5. Stop-signal 会实际阻断 tool、writer、final judge、API output。
6. Quorum 不是投票，而是 evidence + stop-signal + independence + risk 的候选提交机制。
7. Evidence Graph 约束 final claim；没有 evidence edge 的 claim 不能写成事实。
8. Protocol Police / Social Immunity / Capability Sandbox Auditor 真正能阻断，不只是生成报告。
9. Outcome Memory 只学习 agent 过程可靠性，不学习股票结论或任务事实。
10. PheroOS trace 可以回答 why-blocked、why-committed、why-agent、why-claim。
```

你现在 PheroOS 的核心已经非常接近：typed pheromone field 包括 constraint、permission、evidence、data_contract、risk、negative、demand、quorum、tool_health、stop_signal、contamination、quarantine、policing、homeostasis、independence、artifact_cue；每个 signal 有 target、strength、confidence、verification_state、authority_level、lifecycle_state、blocking、source_module/source_agent。 你也已经加入 governance caste，例如 Receiver Normalizer、Evidence Steward、Tool Health Sentinel、Capability Sandbox Auditor、Social Immunity、Protocol Police、Quorum Marshal、Outcome Memory Steward。

现在要审计的是：**这些 governance actor 是否真正改变执行路径。**

---

# 4. 你现在最需要审计的 15 个方面

## 4.1 控制平面 / 执行平面边界审计

目标：确认 OS Kernel 是 OS，不是 hidden analyst。

审计问题：

```text
OS Kernel 是否只做 intent / capability / connection / permission / committee_plan？
OS Kernel 是否直接分析公司、生成投资结论、生成 metric、调用模型？
RuntimeContext 是否只是 dependency container，而不是塞业务逻辑？
LangGraph 是否只编排 workflow，而不是绕过 PheroOS？
```

当前文档说 OS Kernel 负责 intent、capability、connection、permission、committee plan、graph mode 和 runtime_ready，不做投资分析。 这很好，但要做代码级审计，搜索：

```text
runtime/os_kernel.py 中是否有 valuation、Buy、Sell、target_price、financial_analysis 等业务输出；
runtime/runtime_context.py 是否出现业务决策；
app/routes/* 是否直接做业务判断。
```

验收标准：

```text
OS Kernel 不得生成业务结论；
RuntimeContext 不得生成业务结论；
API route 不得生成业务结论；
业务 workflow 必须由 capability / graph / agents / deterministic modules 处理。
```

---

## 4.2 Capability entrypoint 审计

这是你从“强 workflow”变成“真正 AI-as-OS”的关键。

你现在 capability manifest 已经有 workflow、data_contract、evidence_adapter、ui_schema entrypoints 的方向。 但必须审计：这些 entrypoint 是否真的被加载和调用。

审计问题：

```text
Capability Registry 是否校验 workflow.py / data_contract.py / evidence_adapter.py / ui.schema.json？
Runtime Materializer 是否根据 OS Plan 加载 capability workflow？
LangGraph 是否仍然硬编码投资 workflow？
value-investing-research 的 workflow 是否可以独立替换？
新增 capability 是否能提供自己的 workflow？
```

如果答案是“manifest 写了 entrypoints，但 graph.py 仍然硬编码投资逻辑”，那你还不是完整 AI-as-OS，只是 plugin-aware workflow。

改进方案：

```text
runtime/capability_runtime.py
runtime/workflows/base.py
runtime/workflows/investment.py
capabilities/value-investing-research/workflow.py
capabilities/value-investing-research/data_contract.py
capabilities/value-investing-research/evidence_adapter.py
```

目标结构：

```text
OS Kernel 只决定需要 value-investing-research
Capability Runtime 加载 workflow entrypoint
Workflow entrypoint 构建 graph nodes / contracts / swarm protocols
Core runtime 不知道具体投资细节
```

---

## 4.3 ToolRegistry / ModelGateway 接口错用审计

这是 P0。只要 agent 或 runtime 节点能绕过 ToolRegistry / ModelGateway，AI-as-OS 就不成立。

审计搜索：

```text
openai
anthropic
zhipu
minimax
requests.post
httpx.post
wrds.Connection
pandas.read_sql
subprocess
os.system
shell
web_search
fetch_url
```

审计问题：

```text
是否所有模型调用都通过 ModelGateway？
是否所有 WRDS 查询都通过 ToolRegistry / WRDS adapter？
是否所有 web_search 都受 stop-signal / permission policy 约束？
是否任何 agent 代码能直接发网络请求？
是否任何 tool 可以直接读取 SecretStore？
```

你当前设计中模型路由有 judgment / execution / critic / writer / final_judge 角色路由和 fallback chain，WRDS-only 投资任务默认不使用 web search，并强调 ToolRegistry / ModelGateway。 但必须做静态搜索审计和负向测试。

测试：

```text
test_no_direct_model_provider_calls_outside_gateway
test_no_direct_wrds_calls_outside_tool_registry
test_web_search_blocked_in_wrds_only_mode
test_tool_registry_permission_required_for_high_risk_tool
```

---

## 4.4 Secret / data leakage 审计

这是 P0。你的设计已经强调 secret 不进入 prompt、不进日志、不返回前端，只给 secret_ref / last4。 但要审计所有返回和日志路径。

审计范围：

```text
/agents/run response
/platform/connections
/platform/swarm/*
logs/*
trace_store
pheromone_signals
swarm_events
agent prompts
model error messages
dashboard state
```

搜索：

```text
api_key
token
password
secret
credential
authorization
bearer
wrds
secret_ref
last4
```

必须确认：

```text
Secret 明文不进 prompt；
Secret 明文不进 logs；
Secret 明文不进 trace；
Secret 明文不进 frontend；
Model provider error 不带 key；
Tool exception 不带 secret；
递归 redaction 能处理 nested dict/list；
agent 输出里如果复制了 secret-like text，会被 Social Immunity / Protocol Police quarantine。
```

测试：

```text
test_secret_not_in_agent_prompt
test_secret_not_in_agents_run_response
test_secret_not_in_swarm_trace
test_secret_not_in_model_error
test_recursive_redaction_nested_payload
```

---

## 4.5 WRDS raw data / financial data leakage 审计

你的投资 workflow 明确要求：WRDS raw data 不能直接进 final report，核心财务指标必须来自 deterministic metric registry，Data Gate 决定 formal valuation，Writer 不能新增事实，Final Judge 做最终事实/逻辑约束。

这还需要严审：

```text
final report 是否出现 gvkey / datadate / sale= / oancf= / raw row dump？
committee transcript 是否暴露 raw WRDS rows？
dashboard 是否展示 raw WRDS data？
metric_registry 是否只展示聚合/派生指标？
writer 是否能从 wrds_result 直接拿 raw table？
```

改进建议：

```text
RawDataEnvelope：raw data 只能在 tool layer / metric layer 内存在
MetricRegistry：唯一进入 writer 的财务数据接口
PublicReportSanitizer：final/report/dashboard 输出前检查 raw field signatures
```

测试：

```text
test_raw_wrds_rows_do_not_enter_writer_input
test_raw_wrds_fields_not_in_final
test_metric_registry_is_only_financial_data_source_for_writer
test_public_trace_redacts_raw_financial_rows
```

---

## 4.6 Fabricated data / hallucinated metric 审计

这是 PheroOS 成败的核心之一。

审计问题：

```text
WRDS 失败时是否生成假数据？
缺少 metric 时是否用 placeholder / fallback numeric value？
Data Gate warn/fail 时 Writer 是否仍然写确定性估值？
agent 是否能把自己的 estimate 写进 metric registry？
final 是否出现无 source 的数字？
```

搜索：

```text
mock
dummy
sample
fake
placeholder
fallback
estimated
assumed
TODO
default_value
```

规则：

```text
没有 source 的数字不能进入 final；
没有 metric_registry source 的估值不能写成事实；
agent 推断可以作为 hypothesis，但必须 caveated；
缺数据必须进入 risk / data_gap / caveat；
Data Gate fail 必须导致 Insufficient Data / defect memo / degraded output。
```

测试：

```text
test_wrds_failure_does_not_create_fake_metrics
test_missing_fcf_blocks_formal_valuation
test_agent_numeric_claim_requires_metric_source
test_final_does_not_upgrade_hypothesis_to_fact
```

---

## 4.7 PheroOS signal authority 审计

你现在最重要的机制是：agent 不能自己说“我已验证”、不能自己硬阻断、Writer 不能绕过 Data Gate、Red Team 不能把观点变成事实、外部内容不能直接变 evidence。

审计问题：

```text
agent emitted signal 如果带 verification_state=verified，会不会被降级？
agent emitted signal 如果带 blocking=true，会不会被拒绝或转 contested？
普通 analyst 是否能发 stop_signal？
Red Team stop_signal 是否必须经 Signal Verifier / Data Gate / Critic 支持？
external_content 是否能变 evidence signal？
```

改进建议：

```text
runtime/swarm/authority.py：定义谁能 verified / blocking / resolve
runtime/swarm/lifecycle.py：定义合法状态转移
runtime/swarm/signal_policy.py：统一 agent signal 降级策略
```

测试：

```text
test_agent_cannot_emit_verified_signal_directly
test_agent_cannot_emit_blocking_without_can_block
test_red_team_stop_signal_remains_contested_without_support
test_external_content_cannot_emit_evidence
test_data_gate_can_emit_blocking_formal_valuation_signal
```

---

## 4.8 Canonical target / alias bypass 审计

这是很容易被忽略的 P0。

你已经有 canonical target 方向，用来防止 `formal_valuation` / `valuation` / `target_price` 漂移。 但必须审计所有 target alias。

风险例子：

```text
stop_signal target = decision:formal_valuation
writer 输出 target_price
quorum candidate = formal_valuation
final judge 检查 valuation
结果 target alias 不匹配，绕过阻断
```

必须统一：

```text
decision:formal_valuation
decision:report_publication
tool:web_search
candidate:investment:buy
candidate:investment:sell
candidate:investment:insufficient_data
claim:valuation
permission:trade_execute
```

测试：

```text
test_formal_valuation_aliases_all_blocked
test_target_price_blocked_when_formal_valuation_blocked
test_report_publication_alias_blocked
test_web_search_alias_fetch_url_provider_search_blocked
```

---

## 4.9 Stop-signal enforcement + resolution 审计

你现在 stop-signal 已经能阻断 Writer / Final Judge 输出，例如 formal_valuation blocked 但输出 Buy/Sell/目标价、quorum committed = Insufficient Data 但输出正式投资结论、Evidence Steward 标记 unsupported claim 但 writer 继续用、final report 泄露 raw WRDS fields、report_publication 被 block 但 writer 仍发布等。

现在还缺一个关键：**resolution**。

审计问题：

```text
blocking stop-signal 是否能被解除？
谁有权限解除？
Data Gate 补齐数据后能否 recheck？
Resolved signal 是否保留 trace？
Writer 是否只在 resolved 后恢复 formal valuation？
```

新增模块：

```text
runtime/swarm/resolution.py
```

Signal lifecycle：

```text
proposed
→ contested
→ verified
→ blocking
→ resolved
→ archived
```

测试：

```text
test_formal_valuation_stop_signal_resolved_after_data_gate_recheck
test_unresolved_stop_signal_continues_to_block_writer
test_resolved_signal_keeps_audit_lineage
test_only_authorized_module_can_resolve_blocking_signal
```

---

## 4.10 Quorum / CIO 权限审计

你现在已经把决策权拆开：CIO = candidate synthesizer，Data Gate = data sufficiency authority，Signal Verifier = signal truth authority，Protocol Police = boundary authority，Quorum Marshal = commit authority，Final Judge = output consistency authority。

审计问题：

```text
CIO 是否还能直接决定 final recommendation？
Writer 是否引用 CIO 决策而不是 Quorum Marshal committed candidate？
Data Gate blocking 时 Buy / Sell / target price 是否真的 blocked？
Insufficient Data 是否能被 Writer 改写成 Hold / Watch / Buy？
Quorum 是否考虑 source independence？
```

改进：

```text
QuorumResult 必须成为 Writer input 的唯一 candidate source
CIO output 只能进入 candidate proposals
Final Judge 必须检查 final candidate == committed_candidate
```

测试：

```text
test_cio_cannot_override_quorum
test_writer_must_follow_committed_candidate
test_data_gate_block_forces_insufficient_data
test_quorum_penalizes_correlated_support
test_independent_scout_support_increases_quorum_confidence
```

---

## 4.11 Evidence Graph / final claim 强绑定审计

你现在 Evidence Graph 是审计地图：metric nodes、permission nodes、signal nodes、candidate decision nodes、claim nodes、review nodes；edges 表达 signal block 哪些 permission/candidate、metric 支持哪些 claim、critic finding challenge 哪些 claim。

下一步要强制：

```text
final report 每个关键 claim 必须有 claim node；
每个 claim node 必须有 verified evidence edge 或 caveat；
没有 evidence edge 的 claim 不能写成事实；
critic challenge 必须链接到 claim；
blocked claim 不能进入 final；
unsupported recommendation 必须被 block。
```

审计问题：

```text
final answer 是否能生成 EvidenceGraphClaim？
final claim 是否能反查 metric / signal / data_contract？
Writer 新增的句子是否被 Evidence Steward 捕获？
unsupported claim 是否只在 trace 里标记但仍进入 final？
```

测试：

```text
test_final_claims_have_evidence_edges
test_unsupported_recommendation_blocked
test_writer_cannot_create_claim_without_evidence
test_critic_challenge_links_to_claim
test_blocked_claim_not_in_final
```

---

## 4.12 Governance actors 是否只是 report，而不是 controller

这是你当前最大的风险之一。

你已经有 Receiver Normalizer、Evidence Steward、Tool Health Sentinel、Capability Sandbox Auditor、Social Immunity、Protocol Police、Quorum Marshal、Outcome Memory Steward。 但要审计：它们是否真的改变 runtime。

每个治理 actor 都必须有：

```text
input contract
output contract
enforcement target
trace event
test case
```

例如 Protocol Police：

```text
input: writer draft + tool calls + signals + data_gate + committed_candidate
output: policing signals + blocking stop-signals + profile penalty
enforcement target: Writer / Final Judge / ToolRegistry / Quorum
trace: policing_trace
tests: writer bypass / raw WRDS leak / web_search misuse
```

审计问题：

```text
Receiver Normalizer 是否真的把散文转成 claims/evidence_refs/risks/gaps？
Evidence Steward 是否真的写 Evidence Graph？
Protocol Police 是否真的生成 blocking signal？
Social Immunity quarantine 后，污染内容是否真的不能进入 Writer？
Tool Health Sentinel 降级后，ToolRegistry 是否真的改变 route？
Outcome Memory 是否真的更新 profile，而不是只显示报告？
```

如果只是“report 里有”，不算完整 PheroOS。

---

## 4.13 Social Immunity / prompt injection 审计

你现在 Social Immunity 负责检测 prompt injection、secret-like text、污染 artifact。 这必须变成强制隔离。

审计问题：

```text
外部网页 / 文档 / tool output 是否被视为 data，不是 instruction？
prompt injection-like 内容是否 quarantine？
quarantine artifact 是否不能进入 Evidence Graph？
quarantine artifact 是否不能进入 Writer？
外部内容是否不能直接 emit evidence？
secret-like text 是否触发 contamination signal？
```

测试：

```text
test_prompt_injection_artifact_quarantined
test_quarantined_content_not_in_writer_input
test_external_content_cannot_be_evidence_without_verification
test_secret_like_tool_output_redacted_and_quarantined
```

---

## 4.14 Trace Store / event sourcing / replay 审计

现在系统有 `/platform/swarm/runs/{run_id}/timeline`、`why-blocked`、`why-committed`、`evidence-graph`、`agent-allocation` 等 Decision Debugger API。 这很好，但真正可审计系统需要 event sourcing。

审计问题：

```text
Trace 是 snapshot 还是 event log？
能否从事件重建最终状态？
每个 signal 何时 created / verified / blocked / resolved？
每个 candidate 为什么 committed？
每个 writer guardrail 是否有 event？
每个 Protocol Police block 是否有 lineage？
```

建议事件类型：

```text
signal.created
signal.verified
signal.rejected
signal.promoted_to_blocking
signal.resolved
candidate.created
candidate.blocked
candidate.committed
agent.activated
tool.blocked
writer.blocked
final_judge.corrected
artifact.quarantined
claim.blocked
```

存储建议：

```text
当前 JSONL 可以保留；
新增 SQLiteTraceStore；
未来 Postgres / ClickHouse。
```

表：

```text
swarm_events
pheromone_signals
quorum_decisions
evidence_nodes
evidence_edges
tool_events
model_events
permission_events
policing_events
```

测试：

```text
test_event_log_reconstructs_pheromone_snapshot
test_why_blocked_uses_event_lineage
test_why_committed_uses_candidate_events
test_trace_redaction_before_persist
```

---

## 4.15 多租户 / RBAC / production boundary 审计

如果只是本地原型，可以稍后；如果想成为真正 AI-as-OS，必须做。

审计问题：

```text
所有 records 是否有 tenant_id？
tenant A 能否读取 tenant B 的 trace？
secret_ref 是否 tenant scoped？
agent profile 是否 tenant scoped？
capability enable state 是否 tenant scoped？
/platform/swarm/* 是否需要 auth？
/wrds/* 是否默认关闭或 token 保护？
admin endpoints 是否和 user endpoints 区分？
```

测试：

```text
test_tenant_cannot_read_other_tenant_connections
test_tenant_cannot_read_other_tenant_swarm_trace
test_secret_ref_tenant_scoped
test_agent_profile_tenant_scoped
test_admin_endpoint_requires_auth
```

---

# 5. 最重要的改进方案

## P0：治理执行合约化

现在每个 governance actor 都要从“角色说明”升级成“runtime contract”。

新增：

```text
runtime/swarm/governance_contracts.py
runtime/swarm/enforcement_bus.py
runtime/swarm/governance_results.py
```

每个治理 actor 输出统一结构：

```json
{
  "actor": "protocol_police",
  "status": "pass | warn | block",
  "signals": [],
  "blocked_targets": [],
  "required_caveats": [],
  "writer_constraints": [],
  "final_judge_checks": [],
  "profile_updates": [],
  "trace_events": []
}
```

核心原则：

```text
没有 enforcement target 的治理 actor 不算真正治理 actor。
```

---

## P1：Capability workflow 真正插件化

当前 capability 已经声明 entrypoints，但你要确保 runtime 真调用它们。

目标：

```text
runtime/graph.py 不再知道 value-investing 细节；
value-investing-research/workflow.py 提供 workflow；
data_contract.py 提供 contract；
evidence_adapter.py 提供 graph mapping；
ui.schema.json 提供 dashboard schema。
```

新增：

```text
runtime/capability_runtime.py
runtime/workflows/base.py
runtime/workflows/loader.py
```

验收：

```text
test_value_investing_workflow_loaded_from_capability_entrypoint
test_capability_data_contract_loaded
test_capability_evidence_adapter_loaded
test_unknown_capability_cannot_register_unsafe_workflow_without_permission
```

---

## P2：拆分 runtime/graph.py

Graph 不能成为第二个“巨型内核”。

拆成：

```text
runtime/graph.py                         # 只做编排
runtime/nodes/orchestrator.py
runtime/nodes/patroller.py
runtime/nodes/wrds_executor.py
runtime/nodes/data_gate_node.py
runtime/nodes/committee_opening.py
runtime/nodes/committee_discussion.py
runtime/nodes/critic_node.py
runtime/nodes/writer_node.py
runtime/nodes/final_judge_node.py
runtime/swarm_pipeline.py
runtime/writer_guardrails.py
runtime/final_judge_guardrails.py
```

目标：

```text
高内聚；
低耦合；
投资 workflow 可以替换；
PheroOS pipeline 可以复用到 coding/research/compliance。
```

---

## P3：Stop-signal resolution

不要让系统只会 block，不会恢复。

新增：

```text
runtime/swarm/resolution.py
```

例如：

```text
Data Gate 阻断 formal valuation
→ 后续补齐 WRDS 数据
→ Data Gate recheck pass
→ formal valuation stop-signal resolved
→ Buy / Watch / Sell candidates 可以重新进入 quorum
```

---

## P4：Evidence Graph 作为 Writer 输入合同

现在不是“Writer 参考 Evidence Graph”，而应是：

```text
Writer 只能从 Evidence Graph + committed_candidate + required_caveats 写。
```

Writer input：

```json
{
  "committed_candidate": "...",
  "verified_claims": [],
  "caveated_claims": [],
  "blocked_claims": [],
  "required_caveats": [],
  "forbidden_phrases": [],
  "allowed_metrics": []
}
```

Final Judge 检查：

```text
final 每个强 claim 是否能映射到 verified_claim；
final 是否包含 required_caveats；
final 是否包含 blocked_claim；
final 是否新增 unsupported claim。
```

---

## P5：Plugin sandbox / marketplace safety

真正 AI-as-OS 必须支持第三方 capability，但不能被打穿。

新增：

```text
runtime/capability_sandbox.py
runtime/capability_manifest_schema.py
runtime/plugin_signature.py
runtime/plugin_permissions.py
```

Capability manifest 增加：

```json
{
  "trust_level": "third_party_untrusted",
  "sandbox": {
    "network": "deny_by_default",
    "filesystem": "read_only",
    "secrets": "no_direct_access",
    "model_calls": "gateway_only",
    "tools": "registry_only"
  },
  "swarm_permissions": {
    "can_emit_verified": false,
    "can_emit_blocking": false,
    "default_signal_state": "unverified"
  }
}
```

验收：

```text
third-party capability 不能直接访问 secret；
third-party capability 不能直接调用 model；
third-party capability 不能直接调用 arbitrary network；
third-party capability 不能 emit verified/blocking；
third-party artifact 进入 Social Immunity quarantine pipeline。
```

---

## P6：Outcome feedback / learning hardening

Outcome Memory Steward 当前设计正确：只记录 agent process reliability，不记录“AAPL 买入”这类结论。

需要明确学习对象：

可以记：

```text
agent signal 被 verified 的比例；
agent signal 被 rejected 的比例；
agent false block rate；
agent useful risk detection rate；
agent writer bypass attempts；
tool failure rate；
model reliability per role；
capability sandbox violations。
```

不能记：

```text
某公司应该 Buy；
某公司估值是多少；
某行业未来会怎样；
某股票长期结论。
```

新增：

```text
runtime/swarm/outcome_feedback.py
runtime/swarm/profile_policy.py
```

测试：

```text
test_outcome_memory_updates_process_reliability
test_outcome_memory_does_not_store_stock_recommendation
test_agent_reliability_penalized_after_false_block
test_agent_threshold_adjusted_after_verified_signal
```

---

# 6. 你现在最该补的测试包

如果你只做一件事，就做这个测试包。它会直接证明系统不是“文档型 PheroOS”。

```text
test_secret_not_in_prompt_frontend_trace
test_no_direct_model_calls_outside_gateway
test_no_direct_tool_calls_outside_tool_registry
test_web_search_blocked_in_wrds_only_mode
test_raw_wrds_data_not_in_writer_input
test_raw_wrds_data_not_in_final
test_data_gate_blocks_formal_valuation
test_writer_cannot_write_target_price_when_formal_valuation_blocked
test_quorum_forces_insufficient_data_when_data_gate_blocks
test_cio_cannot_override_quorum
test_writer_must_follow_committed_candidate
test_agent_cannot_emit_verified_signal_directly
test_agent_cannot_emit_blocking_without_authority
test_red_team_stop_signal_requires_verifier_support
test_external_content_cannot_directly_become_evidence
test_prompt_injection_artifact_quarantined
test_quarantined_content_not_in_writer_input
test_evidence_steward_blocks_unsupported_claim
test_final_claims_have_evidence_edges
test_protocol_police_detects_writer_bypass
test_protocol_police_emits_blocking_signal
test_formal_valuation_aliases_all_blocked
test_event_log_reconstructs_swarm_state
test_why_blocked_returns_signal_lineage
test_outcome_memory_does_not_store_stock_conclusion
```

这些测试比再加任何新 agent 都重要。

---

# 7. 完整度路线图

## v0.7：可信研究原型

目标：

```text
所有 P0 安全边界有测试；
writer/final guardrail 全覆盖；
Data Gate / Quorum / Evidence Graph 强绑定；
Protocol Police / Social Immunity 真的能 block。
```

你现在接近这个阶段。

---

## v0.8：真正 PheroOS runtime

目标：

```text
governance actors 合约化；
event-sourced trace；
stop-signal resolution；
outcome feedback；
Decision Debugger 可解释每个阻断和提交。
```

这是你下一步最该做的。

---

## v0.9：真正 AI-as-OS runtime

目标：

```text
capability workflow entrypoint 真正驱动；
graph.py 瘦身；
capability sandbox；
generic workflow contract；
支持 coding / research / compliance capability。
```

这一步完成后，才是真正从 investment runtime 走向 OS runtime。

---

## v1.0：production-grade PheroOS / AI-as-OS

目标：

```text
SQLite/Postgres/ClickHouse trace store；
tenant isolation；
RBAC；
KMS/Vault；
plugin signature；
sandboxed execution；
observability metrics；
cost/latency budget；
deployment docs；
security audit。
```

---

# 8. 最终判断

你现在系统已经有完整方向：AI-as-OS 负责连接、能力、模型、工具、agent 插件和 runtime context 的自动配置与热装配；PheroOS 负责运行中的群体治理，用 pheromone signals、stop-signals、quorum、evidence graph、protocol policing 和 writer guardrails 控制 agent 行为与最终输出边界。

但要成为真正完整系统，还必须证明四句话：

```text
1. 所有能力都通过 OS 装配，不能绕过 RuntimeContext。
2. 所有行为都通过 ToolRegistry / ModelGateway / PermissionPolicy，不能绕过边界。
3. 所有结论都通过 Evidence Graph / Data Gate / Quorum / Writer Guardrails，不能靠 agent 散文进入 final。
4. 所有治理 actor 都能改变 runtime 执行，而不是只在 trace 里展示。
```

最优先的三件事：

```text
1. 做 P0 安全与治理测试包。
2. 把 governance actors 合约化，并接入 enforcement bus。
3. 把 capability workflow entrypoint 真正落地，开始拆 runtime/graph.py。
```

如果这三件事完成，你的系统才可以比较有底气地称为：

> **真正的 Swarm-Governed AI-as-OS Runtime，而不是一个带治理 trace 的 multi-agent workflow。**

---

# 9. 2026-06-01 实现收口记录

上述 P0/P1 改进已经落到代码和测试中：

```text
1. P0 安全与治理测试包已补齐：
   - Provider SDK / direct model call boundary tests
   - ToolRegistry / WRDS / shell boundary tests
   - Writer Evidence Contract tests
   - raw WRDS leak / unsupported claim / quorum mismatch failure tests

2. Governance actors 已合约化并接入 enforcement bus：
   - governance_contracts
   - governance_results
   - enforcement_bus
   - evidence_contract
   - writer_contract
   - final judge guardrails

3. Capability workflow entrypoint 已落地，graph.py 已拆分：
   - value-investing-research/runtime_nodes.py owns Data Gate / research / quant / committee / CIO nodes
   - value-investing-research/support.py owns committee selection, context, parsing, scorecard, fallback, deterministic WRDS-only payloads
   - wrds-financial-data/runtime_nodes.py owns WRDS retrieval planning, action normalization, redaction, rendering
   - runtime/nodes/output_chain.py owns Critic / Writer / Final Judge
   - runtime/nodes/preflight.py and runtime/nodes/memory.py own preflight and memory nodes

4. Dashboard / visual verification 已补齐：
   - compose-first home surface
   - agent plugin picker
   - OS plan / capabilities / swarm trace panels
   - browser visual regression tests for desktop and mobile
```

当前全量验证：

```text
.venv/bin/pytest -q        => 281 passed, 1 warning
npm run test:visual        => 6 passed
```

剩余事项已降级为 production hardening，而不是当前 AI-as-OS / PheroOS 架构成立的阻断项：

```text
RBAC / auth
PostgreSQL production trace store
real marketplace signature verification
sandboxed third-party code execution
Vault/KMS operations runbook
cost / latency / retention policy
```
