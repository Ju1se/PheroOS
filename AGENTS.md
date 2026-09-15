# PheroOS Interaction Lab

用户已将主目录缩小为交互研究：交互、薄执行、必要费用与安全边界、机制实验。
旧协议/治理产品及其兼容性要求属于外部历史版本，不得重新带回活跃主线。

- 一次只研究一个明确机制；有负结果也可完成实验。复用已有具体工具，避免新框架。
- 核心在 `src/pheroos_interaction`。每个模块必须有当前实验消费者或必要执行职责。
- 纯可见性/策略与提供商适配、任务真值、终局评分分离。
- 保留真实 scope/version/readers、工具参数声明、有界状态、持久化预算预留、
  取消与未知调用不重试；不要用假成功替代检查。
- 范围是受信任、单机、串行、合成只读任务；不声称旧 authority/BFT/finality、
  恶意宿主、跨租户或分布式 exactly-once 保证。
- 不引入旧 core/runtime/bench、治理、Conformance、schema/TCK、发布体系或通用 OS。
- `research-data` 中现有配置、请求、回执、评分保持原样；新实验写新目录。
- 回放只把旧回复用于完全匹配的旧输入，明确标为 offline replay。
- 本次清理不授权新 API 消费、密钥读取、push、merge 或发布；后续 live 需单独授权，
  沿用既有费用账本，不重置额度。
- 使用 `.venv/bin/python -m pytest -q`、mock、API dry-run 和相关原始记录回放验证变更。
- 测试、默认安装与 CLI 不需要旧包、凭据、模型下载或网络。历史归档在仓库之外。
