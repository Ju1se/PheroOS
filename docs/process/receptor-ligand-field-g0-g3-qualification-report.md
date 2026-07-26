# Receptor-Gated Ligand Field G0-G3 Qualification Report

状态：G0、G1 通过；G2、G3 阻断；仅工程资格验证，不构成 H1-H6 结果

日期：2026-07-27

## 1. 结论

本轮验证不支持 receptor-gated ligand field（RG-LF）优于 full
communication、static sparse、blackboard、BM25 retrieval、learned graph
pruning 或当前 scalar PheroOS。RG-LF 仍是理论动机较强、需要继续检验的候选架构。

G0 的预注册和 protocol-core 边界通过；G1 的 typed research log、oracle/random
diagnostics、deterministic replay 和 zero-authority 自检通过。G2 的 T4 完整环境与
7,252-intent matrix 尚未实现；G3 的 P durable replay 和实际 per-run cost ledger
尚未通过。因此 full smoke、provider canary、pilot 和任何 H1-H6 outcome claim
均未获授权。

资格验证中的 oracle diagnostic 按声明读取了 sealed sidecar，且明确排除在 hypothesis
claim 之外；普通 F/P/S/B/Q/G/R controller 没有读取 sidecar。本轮没有读取或保存
provider credential，没有发起网络请求，`hypothesis_conclusions` 为空。

## 2. 冻结身份与可复现证据

- Protocol-core branch：`codex/receptor-ligand-field-experiments`
- Protocol baseline：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`
- Active profile：`receptor-ligand-field-experiment-profile-v0.5.md`
- Active preregistration commit：
  `01b9253bb06000282e25a991e0892897e3fbe6bb`
- External lab branch：`codex/receptor-ligand-field-lab`
- External lab commit：
  `6ac6902e13b6eb15e39e945bcd4b56e97bbff7f9`
- External source-tree root：
  `sha256:10f5cd353e22a848f67147fae0ce8cfd37be32309f4ed02f1074539afd44e4a0`
- Strict preregistration verification root：
  `sha256:3428ce761472923d1d1535132ca67fb64d0c8576cca5d80b61ab0a9bd0e65a19`
- Qualification artifact-set root：
  `sha256:7a46a02a9f43a12c0ff6088ae4bddc713bddc0480170d18f4326e790dd20ae55`
- Baseline qualification manifest root：
  `sha256:0744ab29d122bfb9e3865d9e0d6bcbb93f936252eb07583349eeb92936adc3b1`
- Qualification root：
  `sha256:61e08609af77f98d01b1b7a0dab922191461467d814d9a4af678ac99df59e777`
- Qualification trace head：
  `sha256:18a969e3d48163a503cce4b6515ee954a4773ef0b162736c12f12ab89f250009`
- Fresh-process deterministic fingerprint root：
  `sha256:41fa9b05c6f63aa7453b5c836009502ae2dc4d0e10ffe2f4b87d4dfb5cd4819d`
- Provider-contract report root：
  `sha256:da822627dbcb138e9e9e108f1dea5b93627e0d8eea0ad1974fe306dfa5a5662d`

Strict verifier 核对了 branch、ancestor、clean worktree、plan/profile/TCK/Hybrid
Replay hashes、external source root、四个 frozen qualification files、manifest
links 和 artifact-set root。外部 lab 的 99 项单元测试通过，compile check 通过；
两个 fresh Python process 对相同 qualification input 产生完全相同的 fingerprint。

本地 trace 位于 external lab 的
`runs/g0-g3-v05-g1-checkpoint-6ac6902/trace.ndjson`。它有两条 canonical
hash-chained records，内部验证 head 与上列值一致。该目录不是 WORM archive；长期
留存仍需独立保存 head root 并复制到 content-addressed 或 write-once storage。

## 3. Gate 结果

| Gate | 状态 | 可执行证据或阻断原因 |
| --- | --- | --- |
| G0 Boundary/Prereg | 通过 | core 仅 docs 改动；两个 worktree clean；全部冻结 hash、ancestor、source/artifact roots 和 manifest links 通过 |
| G1 Controller Contract | 通过 | closed typed log、diagnostic-only oracle、seeded random、zero authority、ordinary-controller sidecar firewall 和 exact replay 通过 |
| G2 Deterministic Simulator | 阻断 | v0.5 已预注册 7,252 intents；T4 scheduler/resource/failure/congestion/evaluator 和完整 matrix 尚未实现/资格化 |
| G3 Baseline Qualification | 阻断 | P durable multistep replay 失败；59-field cost contract 已闭合，但各 arm 的 natural/iso/sweep 实际 ledger 尚未接入 |

`full_smoke_authorized=false`。当前 report 的 `qualify-baselines` 退出码为 `2`，
这是预期的 gate refusal，不是实验失败或 RG-LF outcome。

## 4. Baseline 与 RG-LF 的精确资格范围

所有 controller 都保持：

```text
authority_scope = none
commit_authority = false
controller_qualified_for_G3 = false
g3_complete = false
```

- `F`、`B`：provider-free deterministic mechanics 通过；实际 cost ledger 和完整 T4
  fidelity 未通过。
- `Q`：独立 BM25 golden fixture 已冻结并验证；artifact root 为
  `sha256:8bb33c9fa95aaca4a2d19dbd54944d9cbe969838aa8a85bed2cf597810d56582`。
- `S`：dev-only matched-density graph 已冻结；artifact root 为
  `sha256:6f5a714cf5652d78c2783ec29ff718cb9f47d8aef64ace47b2673ab42d0ff2f6`；
  T4 只包含 baseline mechanics。
- `G`：每个 T1-T7 task 的 54-point Decimal-34 train/dev grid、30 train seeds、30 dev
  seeds 和 checkpoint 已冻结；artifact root 为
  `sha256:145a321380f207bf88688211692915493119335dd24e96a0b2da88a3b7cbf85d`；
  T4 只包含 baseline mechanics。
- `R`：八 ligand、两个 topology epochs、prefix causality、partition isolation、
  restart/canonical roots 和 mass conservation 的 mechanics 通过；T4
  `environment_qualified=false`。
- `P`：numeric projection 和 prefix-causal declared universe 已修复；one-step durable
  fixture 通过。但 decayed long-lived root 在第二步仍触发
  `P-G3-DIFFUSION-REPLAY`。在不修改冻结 PheroOS ABI 的本研究范围内，没有用 zero
  decay、删除 diffusion、改 ID、downgrade 或外部替代品伪装成 P。
- 成本：closed schema 明确区分 measured zero、`not_applicable` 和 missing；
  deterministic replay tests 通过。它仍只是 contract qualification，不是实际
  F/P/S/B/Q/G/R cost coverage。

因此，“mechanics qualified”不能改写成“G3 complete”，更不能改写成相对性能结论。

## 5. G2 v0.5 冻结与失败记录

v0.5 在任何 G2 implementation、full smoke 或 provider request 之前冻结：

- T4 job/worker/failure/recovery/partial-work/deadline state machine；
- sealed future schedule 与 prefix-causal controller view；
- zero-authority no-op diagnostic，使 G2 simulator 与 G3 baseline fidelity 可独立判定；
- compact eligibility descriptor，禁止显式 materialize 最大
  `1024 * 100000 = 102400000` receiver-event pairs；
- 每 budget layer 的 784 个 smoke/attack intents，共 6,272；
- 上位计划五个 scale tiers 的 980 个 capability-only intents；
- 总计 7,252 个不重复 arm-budget intents，以及 fresh-process exact replay gate。

历史 `1232` 计数混用了 manifest/arm/budget 单位；早期 v0.5 草案的 `6664` 又遗漏三个
scale tiers，二者均在实现前更正，未接触 outcome。此前一次 strong-baseline 开发回归为
7/8：测试错误地修改 episode identity 却仍要求 declaration root 不变。该失败被保留、
测试被收紧，冻结工件随后从 fresh process 全量重建；没有删除或重标任何 outcome。

## 6. API Key 与 provider 边界

API key 不是开始实验的充分条件。CLI 只有在 G0-G3 全部通过后才会调用 provider
adapter 或读取对应环境变量。本轮实际执行：

- MiniMax `provider-canary`：退出 `2`，`provider_accessed=false`，
  `credential_read=false`；
- Zhipu `pilot`：退出 `2`，`provider_accessed=false`，
  `credential_read=false`；
- provider contract verification：MiniMax `MiniMax-M3` 与 Zhipu `glm-5.2`
  request contracts 通过，`network_used=false`。

任何曾粘贴到聊天、issue、terminal history 或 log 的 key 都视为已暴露，必须撤销。
未来仅可使用在 recorded conversation 外新生成的 key，并只通过
`PHEROOS_MINIMAX_API_KEY`、`PHEROOS_ZHIPU_API_KEY` 继承；不得写入 Git、Trace、
command argument、report 或 `.env`。

## 7. 下一执行点

下一步按 gate 顺序只实现 provider-free G2：

1. external lab 中实现 v0.5 T4 environment 与 prefix firewall；
2. 生成完整 7,252 intent ledger，并用两个 fresh process 对 matrix roots 做 exact replay；
3. 验证 compact sharding、ACL/capacity/authority violation 为零；
4. 在 G2 通过后再接入各 controller 的实际 natural/iso/sweep cost ledger；
5. 保留 P durable replay blocker，除非形成独立、版本化且不违反当前研究边界的解决路径。

在 G2、G3 全部通过之前，不运行真实 provider canary/pilot，不修改 PheroOS production
algorithm，不提前改变 H1-H6、estimand、MESI 或 claim gate。
