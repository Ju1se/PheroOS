# PheroOS Interaction Lab

活跃范围：交互、薄执行、必要费用与安全边界、能检验机制的实验。
旧协议/治理产品与兼容性要求属于外部历史版本，不得重新带回。

- `src/pheroos_interaction` 放纯 records/visibility/policy/ports，不能导入 runner、
  实验真值、评估或提供商代码。
- `runner` 放具体执行、来源访问、适配和记账；`experiments/current` 放数据、评分与回放。
  使用 pyproject 显式包映射，安装命名空间统一为 `pheroos_interaction`。
- 一次研究一个明确机制；复用具体工具，不建设通用 OS、治理框架或新 ABI/TCK。
- 保留真实 scope/version/readers、工具声明、有界状态、持久化预留、取消、未知不重试。
- 范围是受信任单机串行合成任务，不声称旧 authority/BFT/finality 或恶意宿主保证。
- 源码身份须覆盖核心、runner、experiment 全部包路径，包括 editable 安装时的外部目录。
- 历史数据保持原样；新实验写新目录。旧回复仅用于完全匹配的原输入并标为 offline replay。
- 提供商调用与费用授权分开处理：代码上传不授权付费实验或账本重置。
- 当前用户已授权将精简目录与 README 推送 GitHub 并替换默认主线；保留 Git 历史，
  不强推、不上传凭据、私有状态或本地原始数据，不操作无关工作树和 PR。
- 修改后验证测试、已安装 CLI、无凭据 dry-run 和相关原始记录回放；不使用旧源码路径回退。
- 安装用 `python -m pip install -e '.[dev]'`，测试用 `python -m pytest -q`。
