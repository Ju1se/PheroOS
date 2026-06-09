# PheroOS Kernel/Protocol 执行清单

## 核心判断

Protocol is authority，Agent 不是权威；PheroOS 的下一步不是继续堆 Agent，而是把已实现的运行时能力收敛成稳定的 Kernel、Protocol、Reference Runtime 和 Capability/Driver 生态。

## 当前基线

当前分支已经完成了第一轮 PheroOS 公共身份收敛：

- README 第一屏已经从本地 Agent 平台切换为 PheroOS。
- `pyproject.toml` 已使用 `pheroos` 作为公开 package identity。
- WRDS 不再是核心 package metadata 的关键词。
- 项目叙事已经明确为 PheroOS Kernel、PheroOS Protocol、Reference Runtime 和 Capability/Driver ecosystem。

当前分支已经具备初版 Kernel 文档：

- `docs/kernel/kernel-overview.md`
- `docs/kernel/kernel-syscalls.md`
- `docs/kernel/os-plan-contract.md`
- `docs/kernel/runtime-context-contract.md`

当前分支已经具备初版机器可读 ABI：

- `schemas/pheroos.protocol.v0.1.schema.json`
- `schemas/pheroos.capability.v0.1.schema.json`
- `schemas/pheroos.signal.v0.1.schema.json`
- `schemas/pheroos.evidence.v0.1.schema.json`
- `schemas/pheroos.trace.v0.1.schema.json`

当前分支已经具备初版公共 Python 边界：

- `pheroos/protocol/` 作为协议 wrapper。
- `pheroos/drivers/` 作为 driver contract 起点。
- `pheroos validate` 和 `pheroos-conformance` 作为 CLI 起点。
- `pips/PIP-0001-process.md` 和 `pips/PIP-0002-kernel-abi-v0.1.md` 作为协议演进起点。
- `tests/conformance/test_pheroos_public_abi.py` 作为 conformance 初版。

因此，下一步重点不是重新命名项目，而是补齐可验证兼容性、最小可运行发行版和第三方能力安全路线。

## 优先级执行清单

### P0: 补强协议兼容性证明

- 扩展 `pheroos-conformance`，让第三方 capability 可以证明自己能被加载、规划、授权、治理、追踪和输出审查。
- 为有效 capability manifest 增加正向 fixture，覆盖 protocol declaration、tools、permissions、agents 和 output policy。
- 为无效 capability manifest 增加负向 fixture，覆盖缺失 protocol id、未声明 candidates、非法 recovery role、缺失 tool permission 和不完整 trace policy。
- 增加 candidate registry conformance，确保 quorum 只能 commit protocol-declared candidates。
- 增加 recovery conformance，确保 recovery 由 protocol role/capability tag 驱动，而不是硬编码 agent name。
- 增加 output conformance，确保 Writer 和 FinalJudge 不能绕过 committed candidate、EvidencePolicy、StopSignalPolicy 或 publication permission。
- 增加 trace conformance，确保 why-blocked、why-committed、which-rule、which-evidence、which-tool/provider 都能被解释。
- 增加 domain leakage guard，禁止 core runtime、public protocol、kernel ABI 中重新出现 WRDS、value investing、Buy/Sell/Watch/Avoid、formal valuation 或 investment committee 等领域假设。
- 明确 allowed paths：domain examples 可以存在于 capabilities、tools provider adapters、docs examples、tests fixtures 或 compat legacy 中。
- 更新 conformance 文档，说明兼容性的定义是“不编辑 graph、quorum、recovery、writer、final judge core modules 也能挂载能力”。

### P0: 补清协议、驱动、能力边界

- 把 WRDS 明确标注为 `DataProviderDriver` 或 reference capability，不作为核心 runtime 概念。
- 把 web research、value investing、code development、compliance 都标注为 reference capability 或 example protocol。
- 在 architecture 文档中固定三层边界：Kernel mode、User mode、Driver mode。
- 写清 User-mode agents can propose，Kernel-mode actors can verify/block/commit/publish，Driver-mode adapters can return structured results but cannot author conclusions。
- 把 governance actors 定位为 kernel services，而不是普通 agents 或 committee seats。
- 保持 `runtime/graph.py` 作为 reference runtime shell 和 compatibility bridge，不在其中新增领域分支。

### P1: 建立 PheroOS Minimal

- 新增最小发行版目录，例如 `distros/minimal/` 或 `examples/minimal/`。
- Minimal 必须只依赖 toy-review、mock model、mock tool 和本地 trace storage。
- Minimal 必须不需要 WRDS、不需要金融数据、不需要外部 API key。
- 提供一条可读的最小路径：init、run、trace。
- 如果 CLI 尚不能完整支持 minimal run，先以文档和 fixture 固化目标行为，再分 PR 实现命令。
- Minimal 的验收目标是证明 PheroOS 是通用 AI-as-OS kernel，不是金融 Agent app。

### P1: 收敛公开开发者路径

- 写清第三方 capability 作者应该编辑 manifest、protocol block、entrypoints、tools 和 agents，而不是 core runtime。
- 写清 provider 作者应该实现 driver/adapter contract，而不是让 agents 直接调用外部 provider。
- 写清协议变更必须走 PIP，普通 capability 变更不应该修改 kernel ABI。
- 补充 capability authoring 到 conformance 的闭环：author -> validate -> conformance -> mount -> trace explain。

### P2: 第三方能力安全路线

- v0.1 保持 local trusted capabilities：manifest validation、checksum display、network allowlist、permission confirmation、quarantine signal。
- v0.2 增加 signed capabilities：capability signing、public key trust store、provenance metadata、revocation list、install audit log。
- v0.3 增加 sandboxed execution：restricted imports、subprocess isolation、network policy、filesystem mount policy、resource limits。
- marketplace 不应先做 UI；先完成签名、沙箱、审计和 reviewed distribution pipeline。

## 验收标准

- 仓库第一屏和核心文档读起来是 PheroOS，而不是 Local Agent Platform。
- PheroOS Protocol、Kernel ABI、Driver Model、Capability ABI、Reference Runtime 的边界清晰可见。
- 第三方开发者能理解如何添加 capability，而不需要编辑 `runtime/graph.py`、quorum、recovery、writer 或 final judge core modules。
- WRDS 被清楚表达为 reference data provider driver/capability，而不是核心 runtime 概念。
- conformance 能覆盖 manifest validation、candidate declaration、recovery role policy、tool permission filtering、output contract、trace lineage 和 domain leakage guard。
- toy/minimal 路径可以在无 WRDS、无金融假设、无外部 API key 的条件下说明或运行。
- 所有新协议或 ABI 变更都有 PIP、schema 或 conformance 之一作为可审查依据。

## 不做什么

- 不把 PheroOS 继续做窄成 WRDS、价值投资或金融研究专用平台。
- 不把 Buy/Sell/Watch/Avoid、formal valuation、investment committee 等候选或概念写进 core runtime。
- 不让普通 Agent 直接产生 verified fact、hard blocker、committed candidate、publication permission 或 final authority。
- 不让 Agent 绕过 ToolRegistry、ModelGateway、DataGate、Writer contract 或 FinalJudge guardrails。
- 不把 provider-specific 逻辑塞进 kernel、quorum、recovery、writer 或 final judge。
- 不优先堆新 Agent；优先补协议面、ABI、driver model、conformance 和最小发行版。
