# 实验数据与历史证据

公开仓库提供当前代码、合成任务和离线测试。完整原始记录保留在本地及独立归档中，
没有随本轮代码上传；它们不属于 wheel 的运行依赖。

## 当前保留数据

相对于工作目录：

| 路径 | 文件数 | 历史回复 | 工具执行 |
| --- | ---: | ---: | ---: |
| `research-data/results/visibility-prototype-v1/run` | 329 | 96 | 36 |
| `research-data/results/visibility-factorial-v2/run` | 417 | 96 | 100 |

`research-data/MANIFEST.json` 保存逐文件 SHA-256。总计 746 文件、15,125,615 字节，
复制及回放前后哈希一致。若仅从 GitHub clone 源码，请先取得保留的数据副本再运行
完整 replay；mock 和测试无需这些外部记录。

## 历史恢复与解释边界

- 旧源码、脏修改、冻结包、旧实验和恢复说明保存在独立历史归档；已验证 6,725 文件
  解包哈希和三个历史工作树的恢复状态。
- 归档标识：`pheroos-interaction-history-20260914`；payload SHA-256：
  `4afe2a7804869b628b0b2250dcf7fea57d3078d0cd11a5f9d17b184f0fd04ec9`。
- 精简清理审计标识：`pheroos-cleanup-audit-20260914`；目录整理与发布验证标识：
  `pheroos-layout-publish-audit-20260914`。这些完整审计资料在仓库外保留。
- Git 历史保留旧版本；当前活跃目录不加载旧治理、旧执行器或迁移兼容副本。

历史 `authority` 字段只作为原始数据读取，不能恢复旧治理保证。回放结果标为
`offline_replay`；未知 cached_tokens 仍保持未知，费用采用记录的原定价约定。
远程回复只能保存观察值，不能承诺离线重新生成。

私有凭据、应用状态和完整归档没有上传。冻结环境恢复已在本机 CPython 3.14/macOS arm64
验证；平台适用性与当前 CI 结果应分开报告。
