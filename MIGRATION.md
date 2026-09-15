# Interaction-only 迁移交付

新分支 `codex/interaction-only` 提供独立的 `pheroos-interaction==0.1.0.dev1`。
默认安装、mock、API dry-run 和保留轨迹回放均已在没有旧 core/runtime/bench
的全新环境运行。此次只提取现有行为，没有实现新协调策略或追加模型实验。

## 范围与体积

基线为 research `28c798c` 的已归档脏修改，实际接受的 core 0.1.0、runtime dev5、
bench dev9；不是把较旧 main 或上传包中的 dev8 当作当前状态。
物理行包含空行；非空行仍包含注释和文档字符串。以下完整自有运行闭包包含全部
必需自有包，不能与某次实际加载的模块数混为一谈。

| 口径 | 提取前 | 提取后 |
| --- | ---: | ---: |
| 必需自有 Python 模块 | 669 | 14 |
| 必需自有源码：物理 / 非空行 | 232,655 / 213,020 | 2,521 / 2,245 |
| 其中新包外的必需自有依赖 | core + runtime | 0 |
| 必需第三方运行依赖 | NumPy（元数据要求） | 0 |
| 测试 Python 文件：物理 / 非空行 | 351：183,254 / 164,983 | 6：548 / 462 |
| 自有运行 wheel 总字节 | 2,095,807 | 48,256 |
| 活跃源码中的 re-export 候选 | 31：6,572 / 6,438 行 | 0 |
| 活跃文档/设计 | 157 文件，2,193,210 字节 | 5 份短文档，逐文件大小见最终清单 |
| 历史结果/发布资料 | 142,680,904 字节 | 默认包与工作树中为 0；外置保留 |

生成代码标记扫描两侧均为 0，这只是启发式检测，不能推出旧代码没有生成来源。
旧扫描的二进制 41,127,936 字节、archive 41,399,303 字节、wheel 16,167,890 字节
是格式分类，与上表的用途分类重叠，不能相加。新工作树不保留这些历史副本。
旧构建/安装副本 43,248,433 字节单列；新构建产物与验证环境也在工作树之外。
测试、开发验证脚本、文档、归档均未算入 2,245 行运行源码；两个纯可见性模块
合计 463 物理行。没有将删掉的源码转入另一必装包。

完整定义、逐文件哈希、构建产物、测试依赖及安装 RECORD：
[盘点目录](/Users/scottxie/Desktop/pheroos-interaction-inventory-20260914)。
安装后默认 required dependencies 为空；pytest 及其依赖仅用于 dev 测试，
setuptools 84 仅用于本次构建。动态 mock/replay 只加载新包模块。
单次带检测的测量：旧 CLI import 15.104 ms，随后 dry-run 158.882 ms；新纯策略
import 0.480 ms，追加 CLI import 0.081 ms，mock 执行 52.146 ms。
执行工作量和检测方式不同，这些数字不是速度提升基准。

## 保留、提取、归档与删除

| 处理 | 内容与当前消费者 |
| --- | --- |
| KEEP | 版本化实验身份、历史引用、LICENSE、最小失败反例测试；用于复现与解释当前结果 |
| EXTRACT / SIMPLIFY | v1/v2 投影、顺序、parser、直接父引用；v1 回放和当前 v2 host 使用 |
| EXTRACT / SIMPLIFY | Session、证据读取、driver、MoneyLedger 的具体必要行为；保留实际权限、版本、预算和取消检查 |
| OPTIONAL_EXTERNAL | Kimi 传输仅由显式 live 或 payload dry-run 加载；旧本地模型适配器、数值分析保留在外置历史范围 |
| ARCHIVE | 全部旧 core/authority/Conformance、E/R runner、旧测试、schema/TCK、发布配置、结果及冻结包 |
| DELETE | 上述退役能力在新分支的活跃副本、旧入口与依赖、重复构建产物；原工作树和独立归档仍保留 |

MIT 来源：session/evidence/driver/records 从 runtime dev5 的具体模块提取；
accounting/adapters 从 runtime dev5 的 remote_kimi_v1 提取；visibility/factorial、fixtures
和 evaluation 来自冻结可见性模块；host 从最新 v2 内层有限循环提取。
旧完整 runner 没有作为第二实现留在默认包内。

## 离线验收

| 检查 | 实际结果 |
| --- | --- |
| 历史可恢复性 | 6,725 文件解包哈希一致；3 棵 Git 树连同脏修改恢复一致；冻结环境与一键恢复演练各 117 项针对性测试通过 |
| 全新安装 | 外部 fresh venv，`python -I`，无旧 PYTHONPATH、editable 或源码回退；14 个安装模块逐字节匹配 wheel |
| 新范围测试 | **58 passed in 1.26s**；交叉作用域、过期读取、重复调用、超预算、取消、未知回执、非法目标、回放输入污染均覆盖 |
| 已安装 CLI | 默认 mock 完成，4 次 mock 生成、6 次合成工具执行、2 个终局答案；console entry point 实际运行通过 |
| API dry-run | 禁止 credential、HTTP、socket 和 MoneyLedger 构造时仍通过；创建的是 mock Session SQLite，不打开费用账本 |
| v1 精确回放 | **16 cells / 96 responses / 36 tools / ¥0.1791162**，PASS |
| v2 精确回放 | **24 cells / 96 responses / 100 tools / ¥0.2229812**，PASS |
| 新 host 驱动旧 v2 回复 | **96 次输入逐条匹配，100 tools / 36 inspection intents / 48 final / 0 cache**；1,855 项核对通过 |
| 冻结输入与费用 | 回放前后 746 个输入文件哈希未变；共享账本只读核对仍为 250 请求、¥0.5360475、0 未知费用；本次新增调用 0 |

回放逐项比较允许/选择/物化/发送的记录、完整投影顺序、最终 messages、实际读取、
父引用、解析与拒绝原因、工具意图/物理执行/cache、原始 usage、既有费率和独立评分。
v1 有 48 条、v2 有 54 条 usage 未提供 cached_tokens，仍标未知并按原上界定价；
没有把它补成供应商报告的 0。历史回放不映射或抹掉 ID，不重验旧 authority 保证。
保留回复只在原输入完全匹配时使用，所有结果标为 offline replay。
此外，`tools/verify_native_replay.py` 在已安装的新 host 上重新执行真实本地读取、
发布和 dispatch，每次 count_tokens/generate 先匹配完整历史消息及生成参数。
新 Session 中的 usage 明确来自历史观察；旧 provider ID 和费用置于历史 provenance，
不制造新的供应商回执。新本地作用域、artifact 引用、permission 和计时仅在已声明的
非 prompt 字段发生变化。完整投影内容和有序父引用没有归一化掉差异。

[验证日志与产物](/Users/scottxie/Desktop/pheroos-interaction-validation-20260914)
包含 fresh 安装报告、测试输出、CLI 日志、wheel、sdist 与哈希。
最小 CI 已改成新包测试与 mock；远程 CI 未运行，退役测试不算新包通过项。

## 新边界与复现

受信任、单机、串行、合成只读工具范围内保留真实 lease/run-id/scope/version/readers、
工具和参数声明、发布校验、有限私有状态、持久化预留、取消及未知调用不重试。
Session 独占任务/调用/token 状态，MoneyLedger 独占 CNY 费用。
有效 usage 与无效正文可能使 CNY 已知但 Session token 预留仍未知，按单位分别报告。

新 storage/event/profile 与历史 ABI 不兼容：旧 authority 字段被移除，事件变为普通
本地记录；新 run/lease/call namespace 和非 prompt 的运行元数据明确属于新执行。
不提供旧证书、BFT/finality、恶意宿主、跨租户安全或分布式 exactly-once 保证；
没有通过 `return True` 保留假兼容。mock 字节计数也不是提供商 token 或模型表现。

```sh
python -m pip install .
pheroos-interaction mock --output /tmp/interaction-new-mock
pheroos-interaction api-dry-run --output /tmp/interaction-new-dry
pheroos-interaction replay --run /path/to/restored/visibility-prototype-v1/run --output /tmp/interaction-new-v1
pheroos-interaction replay --run /path/to/restored/visibility-factorial-v2/run --output /tmp/interaction-new-v2
```

更严格的安装检验：用新环境的 `python -I /path/to/pheroos-interaction/tools/verify_install.py`，提供 `--wheel`、
`--v1`、`--v2`、`--output`，并从源码树之外运行。历史恢复命令和路径见
[历史索引](evidence/INDEX.md)。所有输出目录必须新建。
未来 live 需要单独授权与既有共享账本；此次未使用密钥、未 push/merge/publish。

归档封存主体 133,624,157 字节，其中 payload tar 为 87,098,061 字节；可读副本和
恢复 scratch 另计。已复核封存哈希；凭据和 main/.local 私有旧应用状态明确排除、
原位保留。冻结环境恢复仅实证于现有 CPython 3.14/macOS arm64；缺少的 setuptools
原 wheel 采用明确标注的 installed-source fallback。远程回复只保留观察值，不保证
离线再生成。新包尚未做跨平台实测。

下一步仅留[局部需求与拥堵的实验草案](experiments/current/NEXT.md)，本次没有实现它。
