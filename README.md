# PheroOS Interaction Lab

用于研究多 agent 如何利用局部信息、共享证据和工作状态选择行动。
活跃主线只保留交互算法、薄执行、必要费用与安全边界，以及能检验机制的实验。
运行依赖只有 Python 标准库；模型提供商仅在显式调用时接入。

## 文件结构

```text
PheroOS/
├── src/pheroos_interaction/     # 纯交互核心
│   ├── records.py              # 局部租约、作用域标识和错误类型
│   ├── visibility.py           # v1 投影、动作解析和直接父引用
│   ├── policy.py               # 当前 v2 可见性与动作提示策略
│   └── ports.py                # 执行器实际使用的模型接口
├── runner/                     # 具体的本地执行
│   ├── host.py                 # 有限轮次、工具执行和源码身份记录
│   ├── driver.py               # 模型与工具分发
│   ├── session.py              # 预算预留、调用状态与取消
│   ├── evidence.py             # 来源版本、访问、领取与释放
│   ├── adapters.py             # 延迟加载的 Kimi 适配器
│   ├── accounting.py           # 唯一费用账本
│   └── cli.py                  # mock、dry-run、replay、live 入口
├── experiments/current/
│   ├── fixtures.py             # 合成来源数据，仅供 host 与评估读取
│   ├── evaluation.py           # 独立终局评分
│   ├── replay.py               # 匹配原输入的历史回放
│   └── NEXT.md                 # 下一项机制的简短实验草案
├── tests/interaction/          # 机制行为、执行边界和安装布局测试
├── evidence/INDEX.md            # 数据与历史证据索引
├── README.md
└── AGENTS.md
```

磁盘按职责分目录；安装后统一使用 `pheroos_interaction` 命名空间：
`runner/` 对应 `pheroos_interaction.runner`，`experiments/current/` 对应
`pheroos_interaction.experiments.current`。使用显式打包映射，不需要手工设置
`PYTHONPATH`，也没有旧导入名的兼容副本。源码身份检查覆盖三个目录，支持 wheel
安装与 editable 开发安装。

## 安装与运行

需要 Python 3.12 或更新版本。本地验收使用 Python 3.14。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pheroos-interaction mock --output output/mock
pheroos-interaction api-dry-run --output output/dry
python -m pytest -q
```

普通安装用 `python -m pip install .`。所有输出目录必须新建。
也可选择一个当前实验单元：

```sh
pheroos-interaction mock --world fresh_b/missing --condition eligibility_current --output output/missing
```

mock 根据可见输入完成合成运算，字节计数不是提供商 token，也不是模型效果证据。
API dry-run 只验证 mock 路径的请求 payload，不读取凭据、不打开费用账本、不发请求。
`live --help` 提供显式入口；实际付费运行需要单独授权和既有共享账本，不重置历史额度。

## 当前实验与数据

当前 v2 固定两 agent、两次决策机会，交叉比较证据表达和动作提示，并保留
证据完整、缺失、过期三种状态。任务数据与评分不进入策略模块；实验记录保留
检查意图、实际工具执行、缓存、usage 和独立终局评分。
本次目录整理没有改变提示词、轮次、缓存、动作解析或评分。

本地不可变原始数据位于 `research-data/results/`，不进入 wheel 或 Git 提交：

| 数据 | 原始文件 | 历史回复 | 工具执行 |
| --- | ---: | ---: | ---: |
| `visibility-prototype-v1/run` | 329 | 96 | 36 |
| `visibility-factorial-v2/run` | 417 | 96 | 100 |

总计 746 文件、15,125,615 字节。公开源码仓库可以直接运行 mock 与离线测试；
完整历史回放需要另外取得保留的数据目录，详见[证据索引](evidence/INDEX.md)。

```sh
pheroos-interaction replay --run research-data/results/visibility-prototype-v1/run --output output/replay-v1
pheroos-interaction replay --run research-data/results/visibility-factorial-v2/run --output output/replay-v2
```

回放先匹配原始输入，再使用历史回复；不产生新的提供商证据，也不能预测改动提示词
后的模型表现。未知缓存字段不冒充已知 0，检查意图与物理工具调用分别统计。

## 执行边界

适用范围是受信任的单机串行合成任务研究。保留真实 scope/version/readers、工具参数
检查、有界状态、持久化预算预留、取消与未知调用不重试。Session 管理调用/token，
MoneyLedger 管理 CNY；有效 usage 和无效正文可能产生不同单位的已知/未知状态。

旧协议、治理、证书、BFT/finality、Conformance、schema/TCK、旧 E/R 执行器和发布体系
已经撤下；本项目不提供其生产级保证。下一步仅保留
[局部需求与拥堵实验草案](experiments/current/NEXT.md)，尚未实现新算法。
