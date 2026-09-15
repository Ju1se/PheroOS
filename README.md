# PheroOS Interaction Lab

活跃主线只保留交互算法、薄执行、必要的费用与安全边界，以及能检验机制的实验。
当前核心为 `src/pheroos_interaction/` 中的 14 个模块，运行仅依赖 Python 标准库。

## 保留的执行路径

- `visibility` / `factorial`：每个 agent 可见的信息、内容投影、顺序和动作解析。
- `session` / `evidence` / `records`：有界状态、来源版本、读取权限、领取与释放。
- `host` / `driver`：当前两 agent、两轮实验的有限执行与真实工具回复。
- `accounting` / `adapters`：调用前预算预留、实际 usage、未知费用保留、显式远程适配。
- `fixtures` / `evaluation` / `replay`：合成任务、独立评分、原输入匹配的历史回放。
- `cli` 与包入口：运行上述路径。`tests/interaction` 验证必要边界和实验行为。

不再包含旧协议、治理、证书、BFT/finality、Conformance、schema/TCK、旧 E/R
执行器及其 CI、测试和发布配置。范围是受信任的单机串行合成任务研究工具；
局部 scope/version/readers、工具白名单、预算、取消和不隐藏重试仍是真实检查。

## 本地运行

本目录的 `.venv` 安装的是精简包及测试依赖：

```sh
.venv/bin/pheroos-interaction mock --output /tmp/interaction-mock
.venv/bin/pheroos-interaction api-dry-run --output /tmp/interaction-dry
.venv/bin/python -m pytest -q
```

新环境可运行 `python -m pip install '.[dev]'`。默认 mock 使用可见输入做合成运算；
其字节计数不是提供商 token，也不是模型实验结果。API dry-run 只验证 payload，
不读取凭据、不打开费用账本、不发请求。未来 `live` 需显式授权和既有共享账本；
本次清理没有新增 API 调用。

## 当前实验数据

`research-data/results/` 原样保留：

| 数据 | 完整文件数 | 历史模型回复 | 工具执行 |
| --- | ---: | ---: | ---: |
| `visibility-prototype-v1/run` | 329 | 96 | 36 |
| `visibility-factorial-v2/run` | 417 | 96 | 100 |

共 746 文件、15,125,615 字节；SHA-256 清单位于 `research-data/MANIFEST.json`。
这些是本地保留的不可变数据，不进入 wheel 或自动 Git 提交。其余历史实验保留在
旧研究工作树和独立归档，路径见[证据索引](evidence/INDEX.md)。

```sh
.venv/bin/pheroos-interaction replay --run research-data/results/visibility-prototype-v1/run --output /tmp/interaction-v1
.venv/bin/pheroos-interaction replay --run research-data/results/visibility-factorial-v2/run --output /tmp/interaction-v2
```

输出目录必须新建。回放先匹配原输入，再使用保留回复；它验证迁移与数据一致性，
不产生新的供应商证据。费用的未知缓存字段不会伪装成已知 0。

下一项机制只留[局部需求与拥堵实验草案](experiments/current/NEXT.md)，尚未实现新算法。
