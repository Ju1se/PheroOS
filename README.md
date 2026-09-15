# PheroOS

一个本地二元补证工具：按显式模型假设和损失配置决定是否检查，执行前固定结果对应的动作。
只保留纯策略、来源权限、持久化预留、调用上限、取消、未知不重试，以及计划与回执回放。

## 安装与运行

需要 Python 3.12+，运行依赖仅 Python 标准库。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pheroos-interaction inspect \
  --config experiments/current/inspection-example/request.json \
  --source experiments/current/inspection-example/source \
  --output output/inspection
pheroos-interaction inspect-replay --run output/inspection
python -m pytest -q
```

输出目录必须新建。`source.json` 声明 scope、版本、读者、工具与内容摘要；只有决定购买、
持久化预留并通过权限检查后才读取 `value.json`。示例只读取本地文件，不访问模型或费用账本。

## 核心文件

- `src/pheroos_interaction/inspection.py`：成本提前退出、保守角点、六项分支损失。
- `src/pheroos_interaction/records.py`：租约与错误类型。
- `runner/inspection.py`：来源读取、冻结计划、回执验证和只读回放。
- `runner/session.py`、`evidence.py`、`driver.py`：执行约束与工具派发。
- `runner/identity.py`、`cli.py`：完整源码身份和两个命令入口。

安装仅包含 `pheroos_interaction` 和 `pheroos_interaction.runner`。
旧实验、旧策略、研究命令和模型调用代码均已删除。历史原始数据保存在本地
`research-data/results/`，不打包或上传；当前程序不再运行旧实验回放。
已保存的本地 inspection 记录可使用 `inspect-replay --historical --run ...`，明确允许源码身份变化，
仍验证冻结计划、原始回执和执行记录。

## 适用边界

仅支持固定先验、对称二元测量、固定正面复制参考和矩形参数范围；不支持的输入显式拒绝。
概率范围、来源说明、版本、适用条件、三种损失和查询成本必须明确提供。
格式通过不表示真实来源独立或概率已校准。查询成本是与错误、弃权损失同单位的效用值，
不代表费用授权。当前策略只补证一步，调用上限由配置声明。

适用范围是受信任单机串行任务；没有通用语义理解、依赖学习、多步补证或恶意宿主保证。
