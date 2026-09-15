# 当前数据与外部历史

主目录的活跃代码只有 `pheroos_interaction`。历史治理实现、旧执行器及迁移审计
工具均已移出活跃范围。历史回执中的 `authority` 字段只是原始数据，不是当前治理实现。

## 当前机制实验

- `research-data/results/visibility-prototype-v1/run`：完整 329 文件、96 个历史回复。
- `research-data/results/visibility-factorial-v2/run`：完整 417 文件、96 个历史回复。
- `research-data/MANIFEST.json`：原路径、大小及 SHA-256；数据不进入安装包。

当前配置、投影、工具意图/实际执行、usage 与独立评分均保留。模型输出只在匹配
原始请求后离线使用；回放不能证明新策略效果。

## 外部保留与本次清理审计

- [本次清理审计](/Users/scottxie/Desktop/pheroos-cleanup-audit-20260914/README.md)：
  删除范围、数据哈希、安装与测试结果、私有状态保留位置。
- [已验证的历史归档](/Users/scottxie/Desktop/pheroos-interaction-history-20260914/README.md)：
  源码、脏修改、全部旧实验、冻结包及离线恢复说明；封存 payload SHA-256 为
  `4afe2a7804869b628b0b2250dcf7fea57d3078d0cd11a5f9d17b184f0fd04ec9`。
- `/Users/scottxie/Desktop/pheroos-kimi-research` 与 `pheroos-kimi-runtime`：
  用户明确要求保留的历史工作树，本次未修改。
- `/Users/scottxie/Desktop/pheroos-interaction`：上一轮精简与迁移验证工作树，保留原样。

恢复边界已验证于本机 CPython 3.14/macOS arm64。私有凭据和旧应用状态不在公开
实验归档内；本次只对其进行仓库外的可逆迁移，不读取内容。远程响应保留观察值，
不承诺离线重新生成。
