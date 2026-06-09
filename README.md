# PheroOS

PheroOS is an open AI-as-OS protocol and reference kernel for governed
multi-agent runtimes. It defines stable boundaries for capability loading,
permissioning, signal governance, tool arbitration, evidence contracts, quorum
commitment, recovery, and traceable publication.

Product positioning: this repo is **PheroOS Kernel + PheroOS Protocol +
PheroOS Reference Runtime + Capability/Driver ecosystem**, not a prompt chain,
agent framework, or single-provider financial app. Capabilities declare what is
possible, OSKernel decides what is available, RuntimeMaterializer builds what is
executable, PheroOS governs what is allowed, Quorum commits what is justified,
Writer expresses what is permitted, FinalJudge verifies what can be published,
and TraceStore explains why.

当前仓库包含 PheroOS Reference Runtime：

```text
FastAPI API
  -> LangGraph Runtime
  -> SKILL.md Skill Loader
  -> LiteLLM/OpenAI-compatible Model Gateway
  -> Ollama / LM Studio / vLLM / OpenAI
```

核心原则：Codex 用来开发这个 runtime；产品运行时不依赖 Codex。PheroOS
的公开目标是稳定内核边界、协议 ABI、driver model、capability ABI、
conformance suite 和可审计兼容层。

## OSS 结构

- PheroOS Protocol：[docs/protocol/overview.md](docs/protocol/overview.md)
- PheroOS Kernel ABI：[docs/kernel/kernel-overview.md](docs/kernel/kernel-overview.md)
- PheroOS conformance：[docs/conformance/conformance-suite.md](docs/conformance/conformance-suite.md)
- PheroOS Protocol spec v0.1：[docs/protocol/protocol-spec-v0.1.md](docs/protocol/protocol-spec-v0.1.md)
- Protocol examples：[docs/examples/open-multi-agent-protocol-examples.md](docs/examples/open-multi-agent-protocol-examples.md)
- 架构说明：[docs/architecture.md](docs/architecture.md)
- Kernel/User/Driver 边界：[docs/architecture/kernel-user-driver-boundaries.md](docs/architecture/kernel-user-driver-boundaries.md)
- 当前状态：[docs/architecture/current-state.md](docs/architecture/current-state.md)
- 扩展指南：[docs/extensions.md](docs/extensions.md)
- Capability authoring：[docs/capability-authoring.md](docs/capability-authoring.md)
- Agent authoring：[docs/agent-authoring.md](docs/agent-authoring.md)
- Connection control plane：[docs/connection-control-plane.md](docs/connection-control-plane.md)
- OS Kernel：[docs/os-kernel.md](docs/os-kernel.md)
- Runtime Materializer：[docs/runtime-materializer.md](docs/runtime-materializer.md)
- Investment workflow：[docs/investment-research-workflow.md](docs/investment-research-workflow.md)
- Security and permissions：[docs/security-and-permissions.md](docs/security-and-permissions.md)
- Capability security roadmap：[docs/security/capability-security-roadmap.md](docs/security/capability-security-roadmap.md)
- Dashboard：[docs/dashboard.md](docs/dashboard.md)
- PheroOS signal spec：[docs/swarm_signal_spec.md](docs/swarm_signal_spec.md)
- Known gaps：[docs/known-gaps.md](docs/known-gaps.md)
- Living plan：[PLANS.md](PLANS.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全策略：[SECURITY.md](SECURITY.md)
- 许可证：[LICENSE](LICENSE)

主要扩展点：

- `capabilities/*/capability.json`：AI OS Capability 插件声明，是模型、工具、数据源、skills 的统一扩展单元
- `capabilities/*/agents/*.json`：可插拔 Agent 声明，投资委员会成员由这里装配
- `runtime.capability_registry.CapabilityRegistry`：扫描本地已审核 capabilities
- `runtime.agent_registry.AgentRegistry`：扫描 capability 内的 agent manifests
- `runtime.os_kernel.OSKernel`：根据用户需求规划能力缺口、自动启用低风险 capability、生成下一轮 runtime plan
- `runtime.permission_policy`：集中控制 capability 权限和确认策略
- `runtime.ports.ChatModelClient`：替换模型网关
- `runtime.ports.ToolExecutor`：替换或包装工具执行
- `runtime.ports.SkillRegistry`：替换 skill registry
- `runtime.factory.build_runtime`：组装运行时
- `ToolRegistry(extra_tools=..., extra_tool_manifest=...)`：注册外部工具
- `/platform/config`：Dashboard-managed BYOK/BYOD connection registry
- `/platform/connections/*`：AI-as-OS connection control plane，负责 key 识别、连接测试、能力发现、确认激活和热生效

## 当前已实现

- `GET /health`
- `POST /agents/run`
- `GET /skills`
- `GET /skills/{name}`
- `GET /tools`
- `GET /platform/config`
- `POST /platform/connections/infer`
- `POST /platform/connections/confirm`
- `GET /platform/connections`
- `POST /platform/connections/{id}/test`
- `POST /platform/connections/{id}/discover`
- `GET /platform/capabilities`
- `GET /platform/agents`
- `GET /platform/capability-catalog`
- `POST /platform/capabilities/resolve`
- `POST /platform/capabilities/enable`
- `POST /platform/capabilities/{id}/disable`
- `GET /platform/capabilities/active`
- `POST /platform/os/plan`
- `PUT /platform/model-providers/{id}`
- `PUT /platform/data-sources/{id}`
- `GET /wrds/status`
- `GET /wrds/libraries`
- `POST /wrds/tables`
- `POST /wrds/describe`
- `POST /wrds/query`
- `POST /wrds/company/search`
- `POST /wrds/company/financials`
- LangGraph 日常节点：orchestrator -> memory_agent -> executor -> research_agent -> quant_agent -> domain_expert -> critic -> writer -> final_judge
- 投资委员会节点：orchestrator -> executor -> research_agent -> quant_agent -> committee_opening -> committee_discussion -> investment_committee -> critic -> writer -> final_judge
- 投资委员会席位升级为 Jane Street 风格八席：CIO、Data Auditor、Fundamental Analyst、Quant Researcher、Industry Strategist、Market Execution、Risk Manager、Red Team
- PheroOS governance caste 已插件化并可视化：Swarm Scheduler、Receiver Normalizer、Evidence Steward、Quorum Marshal、Social Immunity、Protocol Police、Tool Health Sentinel、Outcome Memory Steward、Capability Sandbox Auditor、Independent Scout
- Governance caste 不作为普通分析委员消耗 token；它们在 LangGraph 安全边界以确定性 actor 运行，负责接收/归一化、证据链接、工具健康、capability 沙箱、社会免疫、worker policing、quorum commit 和 outcome learning
- 委员会 opening 阶段 Data Auditor 先出数据/来源审计包，后续委员会收到已有委员输出作为上下文；Data Auditor 和 Risk Manager 均有 hard veto 权限
- 日常 multi-agent 分工：总控拆解和控成本，Memory 只取上下文，Executor 只跑工具，Research 只抽证据，Quant 只算数据，Domain Expert/投资委员会做专业判断，Critic 反驳验证，Writer 负责成稿，Final Judge 做 GLM 事实/逻辑把关
- LiteLLM/OpenAI-compatible 客户端：`runtime/llm.py`
- `skills/*/SKILL.md` loader 和 keyword matching
- 安全工具层：`list_files`、`read_file`、`write_file`、`run_pytest`
- 联网工具层：`provider_web_search`、`web_search`、`fetch_url`
- executor 会执行 Orchestrator plan 中的 `tool_calls`；没有 `tool_calls` 时会让 Executor Agent 选择受控工具
- 示例 skill：`skills/fastapi-api/SKILL.md`
- 联网 skill：`skills/web-research/SKILL.md`
- 价值投资研究 skill：`skills/value-investing-research/SKILL.md`
- WRDS 专业数据 skill：`skills/wrds-data/SKILL.md`
- AI OS Kernel：用户输入需求后自动规划需要的模型、金融数据、工具、skills capability；低风险本地 capability 自动启用，高风险 capability 需要确认
- 通用任务 taxonomy：`investment_analysis`、`portfolio_review`、`financial_data_retrieval`、`web_research`、`code_development`、`document_writing`、`data_analysis`、`general_chat`
- Capability 插件目录：`capabilities/*/capability.json`，已内置 `ai-model-provider`、`wrds-financial-data`、`value-investing-research`、`web-research`、`fastapi-api`
- Agent 插件目录：`capabilities/*/agents/*.json`，Dashboard 的 `Agent Plugins` 面板会展示这些 agent，用户可用 `AI choose` / `Core` / `All` 或手动勾选来组成投资委员会，并通过 `metadata.committee_member_ids` 热生效到下一轮 run
- Dashboard 的 `Agent Plugins` 现在区分可选投资委员会席位和 OS-level Governance Actors；后者由 PheroOS 协议自动运行，不被用户误选为 analyst
- WRDS Agent：单独负责从 WRDS/Compustat/CRSP/IBES 等专业数据库获取只读数据，不参与投资判断或最终建议
- 公司名/股票名输入会自动触发 WRDS 公司解析和 Compustat 年度财务数据预取；投资分析默认 `WRDS_ONLY`，不会调用 `provider_web_search` / `web_search` / `fetch_url`
- Metric Registry 会把 CRSP、IBES、Compustat Segment 和 peer comparison 等 WRDS 数据包转换成确定性 `street_eps`、`segment_*`、`peer_*` 指标；Data Gate 会分别控制 forward valuation、segment claims、peer valuation 是否允许进入正式报告
- 联网研究默认保留用户原始语言，不再强制英文翻译或英文来源
- 非投资联网研究默认优先使用 GLM/Z.AI 原生 Web Search（经 LiteLLM 透传 `tools: [{"type":"web_search"}]`），失败时自动回退到本地 `web_search`
- 已知公司/股票输入会自动进入 WRDS-only 投资路径；只有显式选择 `web-research` 且不是投资分析时才走联网资料
- 代理为可选配置；默认直连公网，不再强制使用 Misty/V2Ray 端口
- 网页抓取会优先提取正文内容，并支持 PDF 年报/演示稿文本抽取
- web research 搜索后会自动抓取候选来源正文；没有抓到正文时 Critic 会降级为 `needs_sources`
- 运行审计日志：默认写入 `logs/agent_runs.jsonl`，记录 run_id、每个 agent 的模型/耗时/失败原因、工具调用摘要、Research/Quant/Committee/Domain/Critic 输出；写入前会递归 redaction，避免 secret-like 内容落盘
- First-class run trace：`GET /runs/{run_id}/trace?tenant_id=...` 会在 tenant 校验后聚合 redacted audit summary、PheroOS timeline、pheromone snapshot、quorum、Evidence Graph、agent allocation、tool events 和 permission events
- PheroOS 全局视图也按 tenant 过滤：`/platform/swarm/signals`、`/platform/swarm/events`、`/platform/swarm/agent-profiles` 支持 `tenant_id`，旧本地记录默认归属 `default`
- 前端 Agent Trace 展示 `Agent Metrics`，可直接查看每个 agent 的耗时、模型名、是否实际调用模型和失败原因
- Multi-agent 分工审计清单：`docs/multi-agent-audit-checklist.md`
- pytest 覆盖：skill loader、safe tools、API、mocked graph run

## 模型路由

默认使用 GLM + MiniMax：

- `glm-5.1`：Orchestrator、Memory、Research、Quant、CIO、Data Auditor、Fundamental Analyst、Quant Researcher、Industry Strategist、Risk Manager、Investment Committee、Domain Expert、Final Judge
- `minimax-m2.7`：Executor、Market Execution、Red Team、Committee Discussion、Critic、Writer
- GLM 与 MiniMax 都支持多级自动 fallback：GLM 角色默认先试 `glm-5.1-standard` 再切 `minimax-m2.7`；MiniMax 角色遇到上下文窗口、限流、余额/资源包、超时或临时上游错误时会切到 `glm-5.1-standard` / `glm-5.1`
- Research / Quant / Committee / Critic / Writer / Final Judge 等模型节点统一走 fallback-aware chat path，避免单个 provider 短暂失败中断整次 run
- Python/工具层：真实执行和可追踪操作

`configs/litellm.yaml` 已配置：

- `glm-5.1` -> 智谱 CN Coding Plan endpoint `https://open.bigmodel.cn/api/coding/paas/v4`，上游模型名 `GLM-5.1`
- `glm-5.1-standard` -> 智谱 CN standard endpoint `https://open.bigmodel.cn/api/paas/v4`，上游模型名 `glm-5.1`
- `glm-5.1-coding` -> 同 `glm-5.1`，显式 coding alias
- `minimax-m2.7` -> MiniMax CN OpenAI-compatible endpoint `https://api.minimaxi.com/v1`，上游模型名 `MiniMax-M2.7`

MiniMax 国际 Token Plan key 通常使用 `https://api.minimax.io/v1`；你当前本地配置使用的是 MiniMax 中国开放平台 key，因此走 `https://api.minimaxi.com/v1`。

可用环境变量调整全局 fallback 顺序：

```bash
GLM_FALLBACK_MODELS=glm-5.1-standard,minimax-m2.7
MINIMAX_FALLBACK_MODELS=glm-5.1-standard,glm-5.1
DEFAULT_FALLBACK_MODELS=
MODEL_GATEWAY_INTERNAL_FALLBACK=false
```

默认由 LangGraph 节点层执行 fallback，这样 Agent Metrics 会记录 `fallback from ...`。`MODEL_GATEWAY_INTERNAL_FALLBACK=true` 只建议给非 graph 的低层模型调用使用。

开发模式仍可把密钥放在本地 `.env.local`：

```bash
ZHIPU_API_KEY="..."
MINIMAX_API_KEY="..."
WRDS_USERNAME="..."
WRDS_PASSWORD="..."
```

`.env.local` 已加入 `.gitignore`，不要把真实 key 写进 README、代码或测试。

产品模式推荐通过 Dashboard 粘贴 key/凭据：

```text
User intent + raw credential
-> provider inference
-> connection test / capability discovery
-> user confirmation
-> active connection + enabled capability
-> next /agents/run hot materializes RuntimeContext
```

原始 secret 不进入 agent prompt、日志或前端响应；API 只返回 provider、configured、last4 和 capability 摘要。

产品路径推荐从 Dashboard 粘贴 key，让 AI-as-OS 控制平面自动识别、测试、确认并热生效。默认 OSS/self-host 模式会把确认后的 secret 写入 `.local/secrets.json` 并用本地 secret key 加密；生产可设置 `PLATFORM_SECRET_STORE_BACKEND=vault`，通过 Vault KV-v2 adapter 只在本地连接记录里保存 `vault:*` secret handle。

AI-as-OS 现在会根据用户提供的模型 key 自动配置路由和 fallback：

- GLM/Zhipu key：判断、研究、估值、Final Judge 优先 GLM，并自动配置 MiniMax/OpenAI/Claude 等可用 provider 作为 fallback
- MiniMax key：执行、写作、Critic 优先 MiniMax；如果只提供 MiniMax，所有角色自动降级到 MiniMax
- OpenAI key：自动识别为 OpenAI provider，默认模型族从 `/models` 发现，无法发现时使用内置 GPT 候选；所有 agent 自动路由到 OpenAI
- Claude/Anthropic key：自动识别为 Anthropic provider，支持 native `/messages` 调用；所有 agent 自动路由到 Claude，或与 OpenAI/MiniMax/GLM 组成 fallback 链
- 多 provider 同时存在时：OS Kernel / Runtime Materializer 每次 run 热生成 tenant-scoped `ModelConfig`，不需要用户手写 `.env` 或重启服务

## 本机模型 fallback

已检测到的 Ollama 模型：

- `gemma4:e4b`
- `gemma4:26b`
- `bge-m3:latest`

`configs/litellm.yaml` 默认把：

- `local-fast` 指向 `ollama/gemma4:e4b`
- `local-coder` 指向 `ollama/gemma4:e4b`
- `local-reviewer` 指向 `ollama/gemma4:26b`

## 安装

```bash
cd /Users/scottxie/Desktop/multi-agent
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

如果要在本机启动 LiteLLM Proxy：

```bash
.venv/bin/pip install -e ".[proxy]"
export LITELLM_MASTER_KEY="sk-local-master-key"
export ZAI_API_KEY="你的智谱 CN API Key"
export MINIMAX_API_KEY="你的 MiniMax API Key"
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
.venv/bin/litellm --config configs/litellm.yaml --port 4000
```

也可以直接用脚本：

```bash
scripts/start_litellm.sh
```

## 启动 API

```bash
export LITELLM_BASE_URL="http://127.0.0.1:4000/v1"
export LITELLM_MASTER_KEY="sk-local-master-key"
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"
# 可选：需要代理时再设置 WEB_PROXY_URL / WEB_PROXY_REQUIRED
export WEB_PROXY_REQUIRED="false"
export WEB_SEARCH_ENGLISH_ONLY="false"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

也可以直接用脚本：

```bash
scripts/start_api.sh
```

打开前端：

```text
http://127.0.0.1:8000
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

查看 skills：

```bash
curl http://127.0.0.1:8000/skills
```

查看 tools：

```bash
curl http://127.0.0.1:8000/tools
```

检查 WRDS 配置：

```bash
curl "http://127.0.0.1:8000/wrds/status?check_connection=true"
```

列出 WRDS libraries/schemas：

```bash
curl "http://127.0.0.1:8000/wrds/libraries?pattern=comp&max_results=20"
```

执行只读 WRDS SQL：

```bash
curl http://127.0.0.1:8000/wrds/query \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "select gvkey, datadate, fyear, tic, conm, at, sale, ni from comp.funda where tic = '\''AAPL'\'' order by datadate desc",
    "max_rows": 5
  }'
```

按公司名/代码自动解析并取 Compustat 财务数据：

```bash
curl http://127.0.0.1:8000/wrds/company/financials \
  -H "Content-Type: application/json" \
  -d '{
    "query": "沪电股份",
    "max_years": 5
  }'
```

输入公司名时，Orchestrator 会把 WRDS 预取插入计划第一步：

```text
wrds_company_financials -> data_gate -> deterministic research/quant -> investment committee
```

通过 Agent 调用 WRDS：

```bash
curl http://127.0.0.1:8000/agents/run \
  -H "Content-Type: application/json" \
  -d '{
    "task": "用 WRDS 查询 Compustat 中 AAPL 最近 5 条年度财务数据",
    "skill_names": ["wrds-data"]
  }'
```

WRDS Agent 安全边界：

```text
只允许 SELECT/WITH 查询
拒绝多语句和写入/删除/修改类 SQL
默认限制返回行数，最高 500 行
不会在日志、前端或报告中输出 WRDS 账号密码
```

联网 research 示例：

```bash
curl http://127.0.0.1:8000/agents/run \
  -H "Content-Type: application/json" \
  -d '{
    "task": "分析药明康德",
    "skill_names": ["web-research"]
  }'
```

默认联网策略：

```text
用户原始问题 -> Orchestrator 选择搜索 query -> provider_web_search
provider_web_search 通过 LiteLLM 调用 GLM/Z.AI 原生 Web Search
provider_web_search 失败 -> 自动 fallback 到本地 web_search
web_search/fetch_url 默认直连公网；仅在 WEB_PROXY_URL 配置后使用代理
过滤词典页、低相关结果、内网/localhost/private IP
```

Provider-native web search 可用环境变量：

```bash
PROVIDER_WEB_SEARCH_ENABLED=true
PROVIDER_WEB_SEARCH_MODEL=glm-5.1-standard
PROVIDER_WEB_SEARCH_ENGINE=search-prime
PROVIDER_WEB_SEARCH_RECENCY_FILTER=noLimit
PROVIDER_WEB_SEARCH_CONTENT_SIZE=medium
PROVIDER_WEB_SEARCH_MAX_RESULTS=5
```

运行 agent：

```bash
curl http://127.0.0.1:8000/agents/run \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Build a FastAPI file upload endpoint with tests.",
    "skill_names": ["fastapi-api"]
  }'
```

## 测试

```bash
.venv/bin/pytest
```

浏览器级 dashboard 视觉回归测试：

```bash
npm install
npx playwright install chromium
npm run test:visual
```

这组测试会启动本地 FastAPI、用 Chromium 覆盖 desktop/mobile 视口、mock
后端 API，并校验首页 compose、OS setup / agent 插件面板、Research Trace /
Swarm Governance 面板的布局契约。截图工件写入
`output/playwright/visual-regression/`。

当前验证结果：

```text
167 pytest passed
6 Playwright visual tests passed
```

## 可选：直连 Ollama Wrapper

`server.py` 是前一步创建的零依赖 Ollama OpenAI-compatible wrapper。它可以单独启动：

```bash
python3 server.py
```

这个文件适合临时把 Ollama 暴露成 `http://127.0.0.1:8000/v1`，但正式 runtime 路径应该通过 LiteLLM：

```text
runtime/llm.py -> LiteLLM Proxy -> Ollama/LM Studio/vLLM/OpenAI
```
