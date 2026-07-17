# PheroOS

语言：[English](README.md) | **简体中文**

PheroOS 是面向受治理、群体原生多智能体运行时的 protocol-core package。

Agents are not authority. Protocol is authority.

本仓库定义 ABI contract、validation、governance semantics、driver boundary、trace lineage 和 conformance checks。它不是应用运行时。

## 状态

PheroOS 当前是 draft ABI。

公共接口由 conformance 支撑，但尚未稳定。兼容性变更应尽量保持 additive，并且不应强迫 baseline protocol 满足 swarm-specific requirements。

仓库内的 schema artifact 覆盖完整 capability manifest 形状，以及 protocol、
kernel、driver、trace、Commit Wire 和 Commit TCK ABI surface。

Bee-swarm、ant-colony 和 Hybrid 的 collective signal 都必须携带由 governance
签发的 `SignalVerification`。Hybrid pheromone manifest 使用
`pheroos-hybrid-swarm-v1` conformance profile；其完整 reference path 还要求所有数值输入
必须是有限数，并且 output 除 commit、
evidence provenance 和 publication permission 外，还必须具备 target-scoped stop
resolution；当前 target 的任一 blocked resolution 都会拒绝 output。

可选的 Optimal Commit Draft ABI 进一步提供 evidence/counterevidence、challenge、
support lease、risk、稳定窗口、有界 liveness、可移植证书和 Byzantine distributed
finality contract。Hybrid pheromone 与 layer 行为只进入 attention channel；单独改变
attention 不能改变 commit 或 certificate。

## Schema 文档版本

四个核心 schema surface 都具有不可变的 legacy v1 alias，以及独立的 strict v2 文档：

| Surface | 冻结的 v1 `$id` 与 CLI alias | Strict v2 artifact 与 selector |
| --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json`；`capability`/`capability-v1` | `schemas/capability-v2.schema.json`；`pheroos-capability-schema-v2` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json`；`protocol`/`protocol-v1` | `schemas/protocol-v2.schema.json`；`pheroos-protocol-schema-v2` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json`；`driver`/`driver-v1` | `schemas/driver-v2.schema.json`；`descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json`；`kernel`/`kernel-v1` | `schemas/kernel-v2.schema.json`；`plan_version=pheroos-kernel-plan-v2` |

旧的无版本 `$id` 和 CLI alias 永久固定到 v1；它们绝不会根据文档形状或 package
版本选择 v2。Capability 与 Protocol v2 是 schema-document 版本，其 payload 仍声明
`protocol_version=pheroos.protocol.v1`。Driver 的 `descriptor_version` 与
`DriverDescriptor.version` 中的外部 provider 版本相互独立；Kernel 使用自己的
`plan_version` discriminator。

Typed v1-to-v2 迁移必须显式且无损。Driver 迁移使用
`upgrade_driver_descriptor_v1`，不可迁移输入会产生 typed error。Kernel 的
`os_plan_v1_from_dict` 返回非权威 `LegacyOSPlan`；`upgrade_os_plan_v1` 要求调用者提供
scope、readiness、probe、capability 和 provider-version 事实，不会编造默认值。

## 文档

- [SPEC.md](SPEC.md) - protocol-core 规范。
- [CONTRIBUTING.md](CONTRIBUTING.md) - 贡献流程和 patch 要求。
- [SECURITY.md](SECURITY.md) - 漏洞报告和协议安全边界。
- [docs/process/index.md](docs/process/index.md) - 源树 process 入口。
- [docs/protocol/runtime-integration.md](docs/protocol/runtime-integration.md) - 外部 runtime 如何与 PheroOS 组合。
- [docs/protocol/hybrid-pheromone-abi.md](docs/protocol/hybrid-pheromone-abi.md) - Hybrid Pheromone 的规范 ABI。
- [docs/protocol/hybrid-pheromone-v1-migration.md](docs/protocol/hybrid-pheromone-v1-migration.md) - draft Hybrid v1 迁移说明。
- [docs/protocol/optimal-commit-abi.md](docs/protocol/optimal-commit-abi.md) - 完整 Optimal Commit Draft ABI 语义。
- [docs/protocol/optimal-commit-v1-migration.md](docs/protocol/optimal-commit-v1-migration.md) - opt-in manifest 与 runtime 迁移。
- [docs/protocol/runtime-adapter-guide.md](docs/protocol/runtime-adapter-guide.md) - 如何将 `DriverSpec` 映射到外部 adapter。
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - 扩展边界。
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - 公共 API 与 ABI 生命周期。
- [docs/process/schema-v1-v2-migration.md](docs/process/schema-v1-v2-migration.md) - 冻结的 v1 schema alias 与显式 v2 迁移。
- [docs/conformance/conformance-suite.md](docs/conformance/conformance-suite.md) - 兼容性检查。
- [docs/process/release-checklist.md](docs/process/release-checklist.md) - 发布门槛。
- [CHANGELOG.md](CHANGELOG.md) - draft ABI 变更和迁移说明。
- [AGENTS.md](AGENTS.md) - coding agent 的仓库规则。

## 目录结构

```text
pheroos/
  protocol/       Manifest objects, schema helpers, validation.
  kernel/         Capability planning, permissions, runtime context contracts.
  governance/     Authority, evidence, quorum, collective decision, output checks.
  drivers/        Provider-neutral driver ABI and lifecycle objects.
  trace/          Canonical trace events and append-only test store.
  conformance/    Deterministic compatibility checks.
  cli/            Thin wrapper around core packages.

examples/
  toy-protocol/    Minimal governed protocol.
  e2e-protocol/    Provider-free governed vertical slice.
  swarm-protocol/  Swarm-native collective decision example.
  hybrid-pheromone-protocol/  完整 Hybrid Pheromone ABI 示例。
  adaptive-pheromone-replay/  trace-like adaptive input replay 示例。
  hybrid-commit-protocol/     Hybrid attention 与 evidence-governed commit 示例。
  commit-certificate-replay/  可移植证书重建与 mutation 拒绝示例。
  distributed-commit-protocol/  Byzantine quorum、provisional、conflict 与 deadline 示例。

schemas/           Exported ABI schema artifacts.
docs/              Protocol and process documentation.
tests/             Provider-free deterministic tests.
```

## 核心表面

`pheroos.protocol` 负责声明和验证。

`pheroos.kernel` 负责 planning boundary。它不调用工具、模型、provider 或 secret。

`pheroos.governance` 负责 authority 和 decision semantics。Agent 可以提出建议；governance 负责验证。

`pheroos.drivers` 负责通用 capability contract。真实 provider adapter 应位于 protocol-core 之外。

`pheroos.trace` 负责 provider-neutral lineage。它不是 database、queue、event bus 或 runtime monitor。

`pheroos.conformance` 证明 ABI compatibility。

以上 package facade 是对外高聚合入口。内部实现按 commit state、support、certificate、
distributed finality、Hybrid evaluation、swarm 和 pheromone lifecycle 拆成单向依赖的
private engine。Private module path 不是 ABI；facade 保持 canonical object identity，
并委托给唯一实现 owner，不使用动态 service registry。

内置 Commit Wire 与 Trace dispatch 由 immutable static contract registry 驱动，schema
生成与 validation 共享同一规则所有者。Namespaced extension 仍可作为非权威 metadata
扩展，但不能在运行时安装新的 authority handler。

## 管理 CLI

本地 thin CLI 通过 versioned JSON 提供协议管理能力，不会启动 API server：

```bash
pheroos version
pheroos profile show examples/hybrid-commit-protocol/capability.json
pheroos schema list
pheroos schema show commit
pheroos schema export capability-v2
pheroos schema export protocol-v2
pheroos schema export driver-v2
pheroos schema export kernel-v2
pheroos wire validate commit record.json
pheroos wire validate driver-v2 descriptor.json
pheroos wire validate kernel-v2 plan.json
pheroos tck run --version v2
pheroos abi show
pheroos abi diff
```

Schema drift 使用 `python scripts/generate_schema_artifacts.py --check` 检查。
`--write` 只重新生成 v2 artifact，绝不会改写冻结的 v1 文件。

未知 critical version 与畸形 wire record 会 fail closed。HTTP API、认证、限流、
远程路由和 service discovery 属于外部 runtime/gateway，不进入 protocol-core。

## Runtime 集成

外部 runtime 可以 fork 或依赖本仓库，并围绕 ABI 构建自己的 agent loop、model call、tool call、database、memory store、scheduling、queue、server 和 secret management。

每个 request 都构造 `RuntimeScope(tenant_id, run_id, request_id)`，并将由 tenant/run
派生的 `scope_ref` 贯穿 Kernel、Driver、Governance 与 scoped Trace。持久权威通过外部
`GovernanceStateStore` adapter 提供：state 与 Trace 原子提交，compare-and-swap head
拒绝 fork，只有验证过的 store receipt 才能完成持久 output authority。仓库内的
in-memory store 只是 reference adapter，不是数据库。

推荐组合路径：

```text
manifest
-> validation
-> kernel plan
-> external adapter binding
-> evidence, scout reports, and signals
-> governance decision
-> trace lineage
-> output authorization
-> conformance
```

Provider 配置应留在 manifest 之外。使用 `config_ref` 这类 opaque external reference；不要把 API key、password、token、credential 或 secret 写入协议文件。

## Swarm 语义

Swarm-native behavior 是协议行为，不是 swarm framework。

蜂群概念映射为 scout report、recruitment signal、inhibition signal、quorum、consensus 和 safe fallback。

蚁群概念映射为 pheromone trail、evaporation、positive 或 negative feedback、bounded source contribution 和 traceable collective memory。

Pheromone 不是 evidence、truth、permission、quorum 或 output authority。

所有 swarm mode 的 scout 和已启用 collective signal 只有通过 governance verification
后才能计数或影响评分。Hybrid runtime 还向 `evaluate_hybrid_collective_step(...)` 提交
trail、topology、feedback、layer proposal、performance snapshot、
strategy bias 以及有界 policy-adjustment proposal。这个 pure reference step 按 manifest
声明执行 deposit、evaporation、diffusion、reinforcement、coordination、scoring、scout
gate 和 commit-or-fallback，并返回该真实路径产生的 canonical `trace_events`。

`LayerCoordinationState` 是 governance output，不是具有 authority 的 Hybrid input。外部
runtime 必须提交 `LayerProposal` 及相关 proposal input，由 governance 重新计算协调结果。
Manifest ABI 只有一个 canonical `PheromoneKindProfile`，由 `pheroos.protocol` 导出；
`pheroos.governance` 中的同名符号是同一个 compatibility type。

## 不在范围内

本仓库不应成为：

- agent framework
- model-provider gateway
- FastAPI 或 product server
- dashboard
- LangGraph runtime
- LiteLLM/OpenAI/Ollama/vLLM wrapper
- database、queue、worker pool 或 daemon
- plugin marketplace
- domain workflow package

## 兼容性

Baseline governed protocol 在没有 swarm behavior 时仍然有效。

Swarm-specific conformance 只在 manifest 声明 swarm collective mode 时适用。

Hybrid declaration 选择 `pheroos-hybrid-swarm-v1`，其中包含 core、swarm 和 Hybrid
required checks。Baseline quorum 和 basic swarm protocol 不会因此增加 Hybrid-only required
field 或 check。

Optimal Commit 同样是 opt-in。只有显式声明 `collective_commit_policy` 的 manifest
才选择 Commit profile；baseline、swarm 与 Hybrid v1 manifest 保持原有 profile、result
和 trace 行为。

## 发布完整性

CI 覆盖 Python 3.12 至 3.14，并在外部工作目录分别验证 wheel 与 sdist。只有通过这些
检查的精确 distribution bytes 才能进入 deterministic CycloneDX/SPDX SBOM 生成和受信
main branch provenance attestation。Pull request 始终保持 read-only permission。Build
provenance 只说明 artifact 来源，不会创建 protocol evidence 或 governance authority。
详见[发布检查清单](docs/process/release-checklist.md)。

## Hybrid Pheromone Draft ABI

完整 Hybrid reference path 已作为确定性、provider-free 的 protocol-core vertical slice
交付：governance signal verification、有界 deposit/evaporation/diffusion/reinforcement、
L1–L4 coordination、run-scoped policy adjustment、declared-candidate consensus 或 safe
fallback、四个 output gate，以及可因果重放的 trace/conformance。Pheromone 始终只是
collective memory，不会成为 evidence 或 authority。

外部 runtime 只能使用 `replay_state_from_hybrid_step(...)` 返回的 governance-issued
`HybridReplayState` 继续 Hybrid run。Replay receipt 会绑定 deposit、diffusion、feedback 和
adjustment payload；trace conformance 会拒绝 payload substitution、跨 lifecycle identity
collision，以及缺少匹配 issued prior state 的 replay claim。详见
[ABI 参考](docs/protocol/hybrid-pheromone-abi.md)和
[迁移说明](docs/protocol/hybrid-pheromone-v1-migration.md)。

可通过以下 provider-free reference 验证：

```bash
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-pheromone-protocol
.venv/bin/python examples/hybrid-pheromone-protocol/run.py
.venv/bin/python examples/adaptive-pheromone-replay/replay.py
```

## Optimal Commit Draft ABI

Optimal Commit 将探索压力与事实权威分离。通过治理验证的 principal、risk、membership、
observation、counterevidence、challenge、support lease、stop、permission、replay 和
prior-window head 共同决定精确的 fixed-point commit metrics。唯一 leader 必须在连续稳定
窗口内满足全部声明 gate；candidate identifier 不会用于打破 tie。

Manifest 可选择 `advisory`、`evidence_bound`、`certified` 或 `distributed`
assurance。缺少当前 assurance 所需证明时，不会静默产生低等级 commit。新 attention、
evidence、leader 变化、reset 或 finality delay 都不能延长 absolute deadline。

这个 liveness 保证的前提是外部 runtime 持续推进单调 logical step 并重复调用
evaluator。它保证终态响应，而不是强制 evidence commit：`safe_fallback`、
`advisory`、`blocked`、`invalid`、`finality_unavailable` 与
`safety_violation` 仍是显式 non-commit outcome。

`evaluate_hybrid_commit_step(request=...)` 在 governance envelope 可用时返回权威 progress
或 terminal outcome，并携带精确 window/replay head、所需 certificate/finality record、
terminal 时适用的 output decision、canonical trace、diagnostics，以及绑定全部
authority leaf 的 root。
Malformed authority fact 会 fail closed。缺失、畸形或与当前 step 不匹配的 attention
会被隔离为非权威诊断，不能否决本来有效的 commit path。每个已签发 terminal outcome
都能 deliver；publish 与 execute 仍需独立、当前 action authority。

Distributed assurance 验证 `n >= 3f + 1` 与 `2q - n > f`、精确 witness proposal
digest、semantic commit-value root、membership/epoch scope、replay/equivocation 和
conflict freeze。同一语义值的 proof-envelope 重试不会冻结 epoch；candidate、claim、
output 或任一 authority root 不同才构成冲突。Core 只定义 record 与确定性 governance；
network、witness collector、scheduler、provider 和 storage 留在外部。

冻结的 TCK v1 覆盖 38 个 legacy 对抗 vector。TCK v2 新增 23 个 expected-free
声明式 request case：adapter 只能看到 input，expected 由 harness 持有。公共 reference
adapter 与独立 standard-library spec model 必须一致；echo/constant、malformed、乱序、
state leakage 与 timeout adapter 都必须失败。Active Commit conformance 没有 skip 或
N/A 路径。运行方式：

```bash
.venv/bin/python -c \
  'from pheroos.conformance import run_commit_tck; assert run_commit_tck().ok'
.venv/bin/python -m pheroos.cli.main tck run --version v2
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-commit-protocol
.venv/bin/python -m pheroos.cli.main conformance examples/distributed-commit-protocol
.venv/bin/python examples/hybrid-commit-protocol/run.py
.venv/bin/python examples/commit-certificate-replay/replay.py
.venv/bin/python examples/distributed-commit-protocol/run.py
```

Manifest extension 是 metadata，除非被协议不变量正式采用。Extension metadata 不创建 evidence、permission、quorum、commit authority 或 output authority。

## 开发

保持变更 small、deterministic、provider-free、network-free 和 domain-neutral。

优先使用 dataclass、pure function、explicit validation、small schema、provider-free example、direct test 和 conformance check。

不要为了让测试通过而削弱 package boundary。

## License

参见 [LICENSE](LICENSE)。
