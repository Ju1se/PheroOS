# Receptor-Gated Ligand Field G0-G3 Qualification Report

状态：G0 通过；G1-G3 阻断；仅工程资格验证，不构成 H1-H6 结果

日期：2026-07-26

## 1. 结论

本轮验证不支持 receptor-gated ligand field（RG-LF）优于 full
communication、static sparse、blackboard、BM25 retrieval、learned graph
pruning 或当前 scalar PheroOS。RG-LF 仍是理论动机较强、值得继续检验的候选架构。

G0 的预注册和协议边界已经通过。G1-G3 尚未通过，因此 full smoke、provider
canary、pilot 和任何 H1-H6 outcome claim 均未获授权。验证过程没有读取 sealed
outcome sidecar，没有发起 provider 网络请求，`hypothesis_conclusions` 为空。

## 2. 冻结身份与可复现证据

- Protocol-core branch：`codex/receptor-ligand-field-experiments`
- Protocol baseline：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`
- Active preregistration commit：
  `fe05d8fa888b4a8fb771f14b58d812bff437d579`
- External lab branch：`codex/receptor-ligand-field-lab`
- External lab commit：`ef7c4213836f521d5df0085bacde18ea0329b370`
- External lab source-tree root：
  `sha256:17ec5b3269f11cbef655a50ffea5a80204d3331445d598c77ff939622bc7fb54`
- Qualification root：
  `sha256:87bda0681e041c2768ac1d683d65cc403d9799105ae2b7fba2893777e3cbdf6d`
- Qualification trace head：
  `sha256:17b09c3933bb57d13d45c1069096ccefda1cfbba9e3609848f41eb460af3ae2e`
- Fresh-process deterministic replay root：
  `sha256:d83bef27e423816f1d5cb7289af94b2c78872aa78001c47f09a159d878898093`

Active plan、v0.2 profile、TCK v1/v2 和 Hybrid Replay manifest 的冻结摘要均被
preregistration verifier 逐项核对。外部 lab 的 23 项单元测试通过，Python
compile check 通过；同一冻结输入在全新进程中得到完全相同的 replay root。
Provider contract 检查通过，但只检查 endpoint、model、参数、无内联 secret 和
fail-closed 行为；`network_used=false`，不能据此推断模型可用性或实验效果。

## 3. Gate 结果

| Gate | 状态 | 本轮证据或阻断原因 |
| --- | --- | --- |
| G0 Boundary/Prereg | 通过 | 研究分支、祖先提交、冻结 artifact hash、core 边界和 clean worktree 均通过 |
| G1 Controller Contract | 阻断 | 完整版本化研究日志 schema、oracle diagnostic 和 random diagnostic 尚未实现 |
| G2 Deterministic Simulator | 阻断 | T4-T6 环境语义不完整；完整 scale/attack counterfactual matrix 尚未资格化 |
| G3 Baseline Qualification | 阻断 | P/S/Q/G/R 仍有保真度缺口；完整冻结成本核算尚未实现 |

`F` 和 `B` 只获得 engineering-qualified：它们通过 exact replay、可见分区和
zero-authority 等不变量。这不是与 RG-LF 的性能比较，也不是科学基线充分性的
证明。所有 controller 的现有 smoke 同样只证明没有跨 tenant canary 泄露、输出
分区成立且 controller 不能创造 authority。

## 4. Baseline 与 RG-LF 阻断项

- `P`：v0.2 指定的 v2-to-legacy pressure 调用对 tokenless source 不可执行；
  长生命周期 route-to-candidate diffusion 在第二步触发 receipt payload replay
  mismatch；拓扑和 candidate universe 还不是与内容无关的预注册量，存在 prefix
  causality 风险。
- `S`：尚未用 dev-only、matched-density 程序冻结 static sparse 图。
- `Q`：尚未冻结独立实现的 BM25 golden fixture，不能只用自身实现证明自身。
- `G`：Decimal-34 train/dev grid、选择规则和 checkpoint 尚未冻结。
- `R`：当前 `EpisodeManifest` 不能精确表达 v0.2 声明的八种 ligand topology；
  已通过的 mass conservation、clone invariance、ACL-partitioned receptor state
  和 zero authority 只是局部工程不变量。
- 成本：尚缺完整的 logical clock、CPU、消息、字节、token 和失败/timeout 统一核算。

因此本轮正确动作是拒绝 full smoke，而不是把一个不完整的对照实验运行起来。

## 5. API Key 与 provider 实验边界

API Key 不是开始科学实验的充分条件。Provider 调用还要求：

1. G1-G3 全部通过；
2. model ID、endpoint、tokenizer/API snapshot、prompt、roster、预算和 timeout
   均冻结；
3. 使用新轮换的凭据，并只通过
   `PHEROOS_MINIMAX_API_KEY`、`PHEROOS_ZHIPU_API_KEY` 环境变量注入；
4. 先运行单请求 canary，再运行 dev-only pilot；canary 和 pilot 都不能支持
   H1-H6；
5. 不把 secret、原始 Authorization header 或可逆凭据写入 trace、Git 或报告。

任何曾粘贴到对话中的 key 都应视为已暴露，必须在 provider 控制台撤销并轮换。
本轮没有保存或使用这些 key。

## 6. 下一冻结点

在执行 provider canary 之前，需要以 v0.3 amendment 明确并冻结：

1. `P` 的 Hybrid Replay v2 pressure projection，以及内容无关、prefix-causal 的
   topology/candidate universe；
2. `R` 的八 ligand 显式图合同；
3. `S` 的 matched-density dev selection、`Q` 的独立 BM25 golden、`G` 的
   Decimal-34 training/checkpoint；
4. T4-T6 环境语义、完整 scale/attack matrix、oracle/random diagnostics；
5. 版本化日志和完整成本账本。

这些修改属于实验规范与外部 harness 的资格化工作；在形成足够证据前，不修改
PheroOS protocol-core 的生产算法，也不提前改变 H1-H6、estimand 或 claim gate。
