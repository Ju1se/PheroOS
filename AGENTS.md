# PheroOS

活跃范围仅为本地二元补证策略、薄执行与必要的执行边界。

- `src/pheroos_interaction` 只放纯策略和 records，不能导入 runner、实验真值、评估或提供商。
- `runner` 放本地来源访问、执行和回放；使用 pyproject 显式包映射，统一命名空间 `pheroos_interaction`。
  `experiments/current/inspection-example` 仅保留运行所需示例数据，不作为 Python 包。
- 只增加当前策略需要的逻辑；不恢复已删除的旧机制、研究命令、提供商、OS 或协议框架。
- 保留真实 scope/version/readers、工具声明、有界状态、持久化预留、取消和未知不重试。
  一步补证是当前策略范围，执行上限由配置决定。
- 模型假设与损失显式配置；格式验证不等于内容真实、依赖识别或概率校准。
- 范围是受信任单机串行任务，不声称旧 authority/BFT/finality 或恶意宿主保证。
- 源码身份覆盖所有已安装核心与 runner 包路径，包括 editable 安装的外部目录；新增包时同步覆盖。
- 历史原始数据与费用账本保持原样；新输出写新目录，不恢复旧源码来回放旧实验。
  当前本地 inspection 回放匹配冻结计划和原始回执，历史源码差异必须显式声明。
- 当前没有提供商调用入口。代码上传不授权付费实验或账本重置。
- 已有精简目录与 README 的 GitHub 推送授权继续有效；保留 Git 历史，不强推，
  不上传凭据、私有状态或本地原始数据，不操作无关工作树和 PR。
- 安装用 `python -m pip install -e '.[dev]'`，测试用 `python -m pytest -q`。
  修改后验证已安装 CLI、无凭据本地示例和相关 inspection 原始记录回放。
