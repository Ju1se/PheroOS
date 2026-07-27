# Receptor-Gated Ligand Field G0-G3 Qualification Report

状态：G0、G1 通过；G2、G3 阻断；仅工程资格验证，不构成 H1-H6 结果

检查点日期：2026-07-26

## 1. 结论

本轮验证不支持 receptor-gated ligand field（RG-LF）优于 full
communication、static sparse、blackboard、BM25 retrieval、learned graph
pruning 或当前 scalar PheroOS。研究稿中的 H1-H5 是设计良好、可证伪的机制假设，
H6 是系统级 claim gate；它们都不是实验结论。“最合适方向”在当前证据下只能解释为
“理论动机很强的候选架构”。

G0 的预注册和 protocol-core 边界通过；G1 的 typed research log、diagnostic-only
oracle/random checks、deterministic replay 和 zero-authority 自检通过。G2 已实现冻结
matrix、T4 environment、compact smoke evidence 和 scale declaration geometry，但
Attack/T4 尚无可检索 typed artifact 与独立 verifier receipt，完整 scale replay 和全部
7,252 intents 的 isolated-process A/B replay 也尚未执行。G3 仍被 P durable replay、
G2 顺序前置条件和实际 per-controller cost ledger 阻断。

因此：

- `full_smoke_authorized=false`；
- provider canary、pilot 和 confirmatory LLM run 均未获授权；
- `hypothesis_conclusions={}`，没有 H1-H6 outcome 或优越性结论；
- provider call、credential read 和 network use 均为零。

API key 不是开始实验的充分条件，也不应发送给研究执行者。只有 G0-G3 全部通过后，
CLI 才允许读取本地环境变量并调用 provider。

## 2. 冻结身份与证据根

- Protocol-core branch：`codex/receptor-ligand-field-experiments`
- Protocol baseline：`e447d2c96c40b69bb7f98613e23556be7bbe3d76`
- Active preregistration commit：
  `3cba9f7f19c6bceb8a6ea545a6ea51b7833446ab`
- Active profile：`receptor-ligand-field-experiment-profile-v0.6.md`
- v0.5 profile hash：
  `52bee02d20e33ef95b71339ad66c246dbdda3c79d21457f139121379bf8d470b`
- v0.6 profile hash：
  `b1a7aa84664baacdf683af406aa4e88b118ef45b001986e7f438c5d31715a979`
- External lab branch：`codex/receptor-ligand-field-lab`
- External lab checkpoint commit：
  `982e23dd6875f17d420786a4099f423d23535587`
- External source-tree root：
  `sha256:ed15b3c4bf9600fd3af7402fc7d42239a89140ecba547e0601cdce9f2c65e9bf`
- Preregistration lock root：
  `sha256:20567d3cfc5b0c7c8dc7bf98fd8b3303da3878de167440a7d29f15693e4f8692`
- Strict preregistration verification root：
  `sha256:98ba3a0d3cdd293ab391a8db14a94051e122a8f171c8d5d0adadba386d08c6ca`
- Qualification artifact-set root：
  `sha256:7a0c65a3998f9638d46274b3933697a0d4f0978f7ca0efb6ab2a77b565b79f29`
- Baseline qualification manifest root：
  `sha256:c370390b3d7da84da1dd9b14ba93f878af8c01a48743e749669726aeaf7c415a`
- Frozen-artifact exact rebuild verification root：
  `sha256:b70ea8574b37dde65fa2125050ab54e1ed6d96798e26adcef353e78a8116f5d9`
- G0-G3 qualification root：
  `sha256:0d085c87804c8681d9033d716edb1083665cf7e170b5a2e14bfcbf38e1031577`
- G2 standalone qualification root：
  `sha256:14e4d800807e910b3afc13606a343a4c6aca23abfb9d9f624ecc9177359c2050`
- Qualification trace head：
  `sha256:b11ff82de05625b9df90613966a291480a687aec562ab4b0dc4bb4cdce5bcad7`

冻结 baseline artifact roots：

| Artifact | Root |
| --- | --- |
| Q BM25 golden fixture | `sha256:205f00f319541c7593757d2bb41f2d18e27a347f0ee69f060369782839cfd3c9` |
| S matched-density fixture | `sha256:d5098e8bc499b48f13beca0346a694f6fe43802fe3647edddf9b9182b358b57d` |
| G Decimal-34 checkpoints | `sha256:91e421f87312319e5d5012952f9e7d1c135e23d6cfa84968018232db3e9c3a3e` |
| Qualification manifest | `sha256:c370390b3d7da84da1dd9b14ba93f878af8c01a48743e749669726aeaf7c415a` |

本地检查点位于 external lab 的
`runs/g0-g3-v06-g2-checkpoint-982e23d/`。`trace.ndjson` 含两条 canonical
hash-chained records，内部验证通过并得到上述 trace head；`observations.ndjson`
只记录 wall/CPU observation，并从 replay root 排除。该目录由 Git ignore 排除，尚不是
WORM archive；长期科研留存仍需复制到 content-addressed 或 write-once storage。

## 3. Gate 结果

| Gate | 状态 | 可执行证据或阻断原因 |
| --- | --- | --- |
| G0 Boundary/Prereg | 通过 | core 仅研究文档变化；两个 worktree clean；branch、ancestor、profile/TCK/Hybrid Replay hashes、source/artifact roots 和 manifest links 全部通过 |
| G1 Controller Contract | 通过 | closed typed log、diagnostic-only oracle、seeded random、zero authority、ordinary-controller sidecar firewall 和 deterministic replay 通过 |
| G2 Deterministic Simulator | 阻断 | matrix、compact smoke 和 scale declaration geometry 在其窄范围内通过；Attack/T4 typed artifacts、ambient/taint A/B、scale attack records、full-scale replay、standalone profile identity 和 all-intent external A/B 均未通过 |
| G3 Baseline Qualification | 阻断 | P durable multistep replay 失败；G2 未通过；59-field cost contract 已闭合但 natural/iso/sweep 实际 ledger 未接入 |

`qualify-baselines` 退出码为 `2`，这是预期的 fail-closed gate refusal，不是一次
RG-LF outcome failure，也不能解释为任一架构优劣。

## 4. G2 正式覆盖与诊断证据

v0.5 冻结 matrix geometry，v0.6 进一步把每个环境的 stress 字段分为 variable、
intrinsic 和 mandatory 三个互斥集合，并冻结 exact attack-budget 公式。冻结规模为：

- 112 smoke/attack environments × 8 budgets × 7 arms = 6,272 intents；
- 140 scale declaration environments × 7 arms = 980 intents；
- 总计 252 environments、1,036 lazy manifests 和 7,252 arm-budget intents；
- scale tiers 为 `(4,100)`、`(16,1000)`、`(64,10000)`、
  `(256,100000)`、`(1024,100000)`，每个 episode 50 steps。

G2 组件必须分开解释：

| Component | 正式覆盖 | 当前资格 |
| --- | --- | --- |
| Lazy matrix enumeration | 252 env / 7,252 intents | 通过；只证明冻结 planning geometry |
| Attack label firewall v0.6 | 112 in-process diagnostics；0 formal env / 0 intents | 阻断；无可检索 preimage artifact、独立 verifier receipt、ambient/taint A/B 和 scale labels |
| T4 smoke transitions | 16 diagnostics × 20 steps；0 formal env / 0 intents | 阻断；无 typed transcript artifact、独立 receipt、transcript completeness 和 sealed-suffix attestation |
| Compact record-backed smoke | 112 env × 20 prefixes / 6,272 intents | 通过；只证明 full selected/dropped partition、ACL digest、attestation 和 receipt |
| Scale count-only declaration | 140 declaration geometries / 980 intents | 通过；只证明算术计数与 declaration geometry，descriptor 明确为 unverified/non-replay |
| Full scale replay | 0 / 980 intents | 阻断；未执行 |
| All-intent isolated-process A/B | 0 / 7,252 intents | 阻断；未绑定 byte-exact external A/B attestation |

正式 intent evidence links 共 14,504 条：

```text
7,252 matrix planning links
+ 6,272 compact smoke links
+   980 scale declaration links
= 14,504
```

该数字不是 14,504 次 controller execution，也不是 14,504 个 outcome。G2 report
明确记录：

```text
controller_execution_count = 0
evaluator_call_count = 0
provider_call_count = 0
outcome_read_count = 0
ordinary_controller_sidecar_read_count = 0
authority_scope = none
commit_authority = false
```

外层 G0 verifier 已校验实际 profile、prereg lock 和 immutable core checkout；但
standalone G2 report 尚未把这些字节及 verifier receipt 纳入自身 component root，因此
`G2-PROFILE-IDENTITY` 仍按 fail-closed 原则保留。不能用外层通过偷偷替代内层缺失证明。

## 5. T4 实现范围与不能声称的性质

T4 environment 已实现 deterministic scheduler、resource capacity、failure/recovery、
congestion、partial work、deadline、topology epochs、typed commitment 和 sealed
evaluator。Evaluator 从 config、jobs、workers、failure schedule 和 topology epochs
重建 commitment，并拒绝用 declaration 自报值替代 ground truth。

Streaming audit records 包含 typed membership-proof preimages；缺失或篡改 proof
会被拒绝。Cost counter 区分 actual 与 modeled cost，不把 modeled value 冒充
measured upper bound。

当前只验证 structural suffix non-interference：固定已声明 prefix 时，更改未暴露
suffix 不改变 prefix-visible structure。研究没有声称 seeded future schedule 对
controller 不可预测，`future_unpredictability_claimed=false`。在缺少持久化 typed
transcript 和独立 verifier receipt 时，上述实现与 16 × 20 in-process diagnostics
仍不能计入正式 G2 T4 coverage。

同理，sidecar diagnostic 只证明：

1. 显式 context-builder API 不接受 sidecar 参数；
2. 两次相同显式输入产生相同输出。

它尚未证明真实 ambient/taint A/B sidecar-suffix non-interference，因而正式 Attack
coverage 仍为零。

## 6. Baseline 与 RG-LF 的精确资格范围

所有 controller 都保持：

```text
authority_scope = none
commit_authority = false
controller_qualified_for_G3 = false
g3_complete = false
```

- `F`、`B`：provider-free deterministic mechanics 通过；实际 cost ledger 和完整
  G2 fidelity 未通过。
- `Q`：独立 BM25 golden fixture 已冻结并验证；只证明 fixture-bound mechanics。
- `S`：dev-only matched-density graph 已冻结；只证明冻结图的 mechanics。
- `G`：每个 T1-T7 task 的 54-point Decimal-34 train/dev grid、30 train seeds、
  30 dev seeds 和 checkpoint 已冻结；没有在资格检查中重新训练。
- `R`：八 ligand、两个 topology epochs、prefix causality、partition isolation、
  restart/canonical roots 和 mass conservation 的 topology mechanics 通过；
  `environment_qualified=false`。
- `P`：numeric projection、prefix-causal declared universe 和 one-step durable fixture
  通过；decayed long-lived root 在后续 step 仍触发
  `P-G3-DIFFUSION-REPLAY`。在不修改冻结 Hybrid Replay v2、ABI 或完整 declared
  path 的约束下，没有用 zero decay、删除 diffusion、改 ID、downgrade 或外部替代品
  伪装成 P。
- 成本：59-field closed schema 区分 measured zero、`not_applicable` 和 missing，
  contract self-check 通过；各 controller 的 natural/iso/sweep 实际 per-run ledger
  仍未接入。

因此，“mechanics qualified”不能改写成“G3 complete”，更不能改写成相对性能结论。

## 7. 验证与安全记录

外部 lab 的完整测试在冻结后、提交前运行 191 项：190 项通过，唯一失败是预期的
`external_lab_worktree_clean=false`。提交后该 clean-gate 测试单独通过。这里不把
两次运行合并伪称为一次 `191/191` 全绿运行。

其他验证包括：

- T4：26/26；
- attack + matrix + compact + T4 targeted：70/70；
- unified qualification + CLI：18/18；
- frozen artifacts 从当前源码 exact rebuild：四项全部通过；
- clean commit 后 strict `prereg-verify`：通过；
- provider CLI env-read trap：gate refusal 发生在 credential read 之前；
- secret filename pattern scan：未发现 credential 或 `.env` 文件；
- Python compile 和 Git diff check：通过。

本轮没有读取或保存 provider credential，没有发起网络请求。任何曾粘贴到聊天、
issue、terminal history 或 log 的 key 都视为已暴露，必须撤销。未来只可在 G0-G3
通过后，使用在记录外新生成的 key，并通过
`PHEROOS_MINIMAX_API_KEY`、`PHEROOS_ZHIPU_API_KEY` 由本地环境继承；不得写入
Git、Trace、command argument、report 或 `.env`。

## 8. 下一执行点

下一步仍只做 provider-free gate work：

1. 为 112 Attack cells 和 16 × 20 T4 transitions 生成可检索 typed preimage
   artifacts，并实现独立 verifier receipts；
2. 完成真实 ambient/taint A/B 与 T4 transcript-completeness、tamper-rejection、
   sealed-suffix attestations；
3. 对 140 scale environments / 980 intents 执行完整 record-backed replay；
4. 在隔离 workspace/process 中对全部 7,252 intents 生成 byte-exact A/B attestation，
   并把 profile/prereg/core identity receipt 绑定进 G2 root；
5. G2 全部通过后，接入 F/P/S/B/Q/G/R 的 actual natural/iso/sweep cost ledgers；
6. 保留 P durable replay blocker，除非出现独立、版本化且不改变冻结 ABI/path 的
   合法解决方案。

在 G2、G3 全部通过之前，不读取 API key，不运行真实 provider canary/pilot，不修改
PheroOS production algorithm，也不提前改变 H1-H6、estimand、MESI、split、seed、
repeat、budget 或 claim gate。
