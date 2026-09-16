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

## 共享执行账本

`CoordinationSession` 支持多个声明 agent、带依赖的工作和发布后读取；身份由受信任宿主传入。
工作角色决定谁能执行，来源和 inspection 的两层 `readers` 交集决定谁能执行检查、发布及读取产物。
依赖只检查产物已存在，消费者读取时仍须通过当前版本与权限检查。

- `publish_received(agent, call_id, verify=...)` 复用已结算回执；租约过期时原子地重新领取并发布，
  不重新调用工具、不增加费用或调用名额。取消、来源变化、无权限、其他持有者的有效租约，
  或同一工作仍有未知派发，都会阻止新发布。相同回执已发布后，权限仍有效时重复调用返回原引用。
- `artifacts(agent)` 只枚举当前可见的已发布产物引用、工作、版本和观测键；
  `read_artifact(agent, ref)` 返回 JSON 副本，不可见或过期时返回 `None`。
  取消会话或未声明读者会报错。两者不恢复租约、不执行工具、不写事件。

`verify` 必须是纯本地校验；拒绝或异常会回滚本次领取与发布，SQLite 无法回滚校验器的外部副作用。
本地 `inspect` 已使用这一发布入口；结算后返回中断仍保留原回执并停止，不自动补跑。
`receive` 不受租约约束，迟到回执仍可结算；未知派发没有超时释放出口。
`call`、`snapshot` 和回放是宿主审计入口，不能作为 agent 的内容读取接口。

`max_control_operations` 限制成功领取租约与已接受的来源更新总数，包括发布恢复时重新领取、
以及重复提交相同来源更新。已有持久化事件就是计数依据，重新打开会话不会重置额度。
耗尽时抛出 `BudgetExceeded`，本次事务的状态和事件全部回滚；校验失败也不消耗额度。
读取、未领取到工作和已发布回执的幂等返回不消耗额度。调用的预留、派发和结算另受
`max_calls` 与 token 上限约束；租约过期恢复、取消和迟到回执结算在控制额度耗尽后仍可进行，
有效租约也仍可发布。过期回执需要新租约才能发布，因此需要剩余控制额度。
来源更新被拒绝时原声明保持不变，宿主仍可取消会话。
源码身份匹配的 inspection 回放会验证控制计数；明确允许源码差异的历史回放不把新限制追溯到旧记录。

这些是执行与访问约束，不是策略收益证据；尚未加入工作枚举、占用投影或拒绝日志，模型调用保持关闭。

## 适用边界

仅支持固定先验、对称二元测量、固定正面复制参考和矩形参数范围；不支持的输入显式拒绝。
概率范围、来源说明、版本、适用条件、三种损失和查询成本必须明确提供。
格式通过不表示真实来源独立或概率已校准。查询成本是与错误、弃权损失同单位的效用值，
不代表费用授权。当前策略只补证一步，调用上限由配置声明。

适用范围是受信任单机串行任务；没有通用语义理解、依赖学习、多步补证或恶意宿主保证。
