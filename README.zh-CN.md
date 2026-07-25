# PheroOS

语言：[English](README.md) | **简体中文**

[![tests](https://github.com/Ju1se/PheroOS/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Ju1se/PheroOS/actions/workflows/tests.yml)

PheroOS 是面向受治理、群体原生多智能体运行时的 provider-free 协议核心包。

> Agents are not authority. Protocol is authority.

PheroOS 定义外部运行时如何声明能力、隔离作用域、验证智能体输入、形成受治理的决策、
记录因果谱系并证明兼容性。它不运行智能体循环，不调用模型或工具，不托管 API，也不
提供数据库。

## 项目状态

| 属性 | 当前状态 |
| --- | --- |
| 软件包 | `pheroos 0.1.0` |
| ABI 稳定性 | 已实现并由 Conformance 支撑的 **Draft ABI** |
| Python | `>=3.12`；CI 覆盖 CPython 3.12、3.13 和 3.14 |
| 运行时依赖 | 无 |
| 已发布分发 | 无；当前文档化用户入口是源码检出，CI 与离线非发布 RC rehearsal 会构建并验证 wheel/sdist |
| 许可证 | MIT |

Draft 表示公共形状仍可能通过有迁移说明的变更继续演进，并不表示 reference path 只是
占位实现。Baseline、Hybrid Pheromone、Optimal Commit、持久权威 contract 及其原子化
reference path、Trace 与 Conformance 都已经实现并由确定性测试覆盖。在首个稳定 ABI
发布之前，使用方应固定精确 commit，以及自己实现的 schema/profile 版本。
已检入的 Stable Core candidate 仍是
`draft / promotion_candidate / formal_stable=false`；当前没有任何公共 lifecycle entry
被正式提升为 Stable。

## 快速开始

从源码克隆并安装：

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

验证最小协议并运行其选定的 Conformance profile：

```bash
pheroos version
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
```

CLI 返回 versioned JSON。通过的报告包含 `"ok": true`，以及实际应用于目标的准确
profile 和 checks。

顶层 examples 是源码检出中的测试样例，不会打进 wheel。安装后的 CLI、schema、ABI 与
TCK 命令可以从任意目录运行。

开发环境安装与验证：

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
pheroos source-conformance .
```

## 协议模型

PheroOS 将运行时执行与协议权威分离。

运行路径是：

```text
capability manifest
-> Protocol 严格验证
-> RuntimeScope 与 Kernel plan
-> 外部 Driver 绑定和 scoped invocation
-> 经过 Governance 验证的事实、报告与信号
-> 受治理的 decision 或显式 terminal outcome，包括 safe fallback
-> canonical Trace 与 output authorization
```

兼容性路径独立运行：

```text
manifest / adapter / installed artifact
-> versioned Conformance profile 或 TCK
-> 确定性 PASS 或 FAIL report
```

外部 runtime 始终是编排者。它负责 agents、模型与工具调用、调度、网络、凭据、持久化
基础设施和交付；PheroOS 负责信任边界上的 contract 与确定性 reference semantics。

## 架构与边界

| 公共表面 | 负责内容 | 明确边界 |
| --- | --- | --- |
| `pheroos.protocol` | Manifest、candidate、policy、schema、loading 与 validation | 纯 contract code；不依赖 Kernel、runtime、provider 或 Conformance |
| `pheroos.kernel` | scope-aware plan、permission、readiness、connection 与 exposure contract | 决定可用能力；不调用工具/provider，也不做领域结论 |
| `pheroos.drivers` | provider-neutral descriptor 与 `declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace` 生命周期 | 真实 adapter 与 provider SDK 位于 core 之外 |
| `pheroos.governance` | verification、evidence、quorum、swarm decision、risk、commit、certificate、finality 与 output gate | Agent 和 adaptive layer 可以提议；只有依照已声明 Protocol 行事的 Governance 才能签发 runtime decision authority |
| `pheroos.trace` | canonical `TraceEvent`、scoped envelope、validation 与 append-only store contract | 不是 database、queue、event bus 或 monitor daemon |
| `pheroos.conformance` | Manifest profile、source check、外部 adapter matrix 与 Commit TCK | 确定性、provider-free、network-free |
| `pheroos.cli` | 本地 versioned-JSON 管理命令 | 只是 thin wrapper；不是 HTTP API 或服务 |

Import graph 保持单向：Protocol、Drivers 与 Trace 是基础层；Kernel 只依赖 Protocol 和
Drivers；Governance 不依赖 Kernel runtime machinery；Conformance 组合全部核心表面；
CLI 只委托公共 facade。Private engine 不构成第二套 ABI。

## 治理不变量

- Agent、scout、learned layer、evolutionary layer 与 metacognitive layer 可以提出记录，
  但不能签发权威。
- 调用方控制的 `verified` 标志不是 verification。Scout、recruitment、inhibition 与
  quorum input 只有携带匹配的 governance-issued `SignalVerification` 才会生效。
- Governance 只能提交为当前 target 声明的 candidate；共识失败时选择该 target 已声明
  的 safe fallback。
- Pheromone 是有界 collective memory 与 attention，不是 evidence、truth、permission、
  quorum、certificate 或 output authority。
- 未知 critical version、非有限数、跨 scope 记录、畸形 authority fact 与陈旧 state
  head 全部 fail closed。
- 受治理的 Baseline Output v2 与 collective output path 必须分别通过四道独立门槛：
  对 declared candidate 的权威 commit、带 provenance 的 evidence、当前 target 至少一个
  `StopResolution` 且不存在 blocked 的同 target resolution，以及当前 publication
  permission。
- Optimal Commit 签发的每个 terminal outcome 都可以交付；publication 与 execution
  仍是彼此独立的当前 action decision，不能仅由 delivery 自动获得。

## 按需启用的决策路径

可选协议不会改变未声明它们的 baseline manifest。

| 路径 | Manifest 选择条件 | 受治理行为 | Conformance profile | 示例 |
| --- | --- | --- | --- | --- |
| Baseline | 未声明 swarm 或 Commit | verified quorum、declared candidate、safe fallback | `pheroos-core-v1` | [`toy-protocol`](examples/toy-protocol/)、[`e2e-protocol`](examples/e2e-protocol/) |
| Basic swarm | `mode=bee_swarm` 或 `mode=ant_colony` | verified scout、recruitment/inhibition、有界 pheromone memory | `pheroos-swarm-v1` | [`swarm-protocol`](examples/swarm-protocol/) |
| Hybrid Pheromone v1 | v1 manifest 中的 `mode=hybrid` | diffusion、feedback、nonlinear response、L1-L4 proposal 与有界 adjustment | `pheroos-hybrid-swarm-v1` | [`hybrid-pheromone-protocol`](examples/hybrid-pheromone-protocol/) |
| Scoped Hybrid Replay v2 | Capability/Protocol v3 document 选择 `pheroos.protocol.v2` | Store-backed durable replay 与 scoped authority | 精确的 v2 Store、session、replay 与 runtime-integration Conformance | [`hybrid-replay-protocol`](examples/hybrid-replay-protocol/) |
| Optimal Commit | `collective_commit_policy` | evidence-governed truth、stability、liveness、certificate、可选 distributed finality | assurance-specific Commit profile | [`hybrid-commit-protocol`](examples/hybrid-commit-protocol/)、[`distributed-commit-protocol`](examples/distributed-commit-protocol/) |

Optimal Commit 会根据 assurance 与已声明的 Hybrid attention semantics 选择
`pheroos-commit-integrity-v1`、`pheroos-hybrid-commit-v1`、
`pheroos-certified-commit-v1` 或 `pheroos-distributed-commit-v1`。

### Hybrid Pheromone：attention 与 collective memory

主要 Draft 路径是由 StateStore 支撑的 Hybrid Replay v2：

```text
evaluate_hybrid_collective_step_v2(...)
-> build_hybrid_replay_advance_request_v2(...)
-> open_hybrid_replay_authority_session_v2(...)
-> advance_hybrid_replay_state_v2(...)
-> 重启后 rehydrate_hybrid_replay_state_v2(...)
```

evaluator 会先验证完整 input batch，再执行有界 adjustment、deposit、evaporation、
diffusion、feedback reinforcement、nonlinear response、L1-L4 coordination、scoring、
independent-scout gate 与 commit-or-fallback。它返回的非 portable source proof 与精确
authority context 绑定。只有 StateStore 原子 commit 才能产生 durable replay authority；
portable snapshot、digest、checkpoint 或同形对象都不能产生 authority。rehydration 会证明
committed inclusion 与 position，且只有 current head 才能作为下一次 advance 的 parent。
确定性重启与 fresh-subprocess continuation 见
[`hybrid-replay-protocol`](examples/hybrid-replay-protocol/)。

`evaluate_hybrid_collective_step(...)`、`HybridReplayState` 与
`replay_state_from_hybrid_step(...)` 仅作为 Deprecated Draft 兼容面保留；它们描述旧的
process-local 路径，不是 durable v2 authority 或 restart 主路径。

### Optimal Commit：truth 与 authority

Optimal Commit 严格分离两个 channel：

| Channel | 输入 | 可以影响 | 不能执行 |
| --- | --- | --- | --- |
| Exploration/attention | Scout、pheromone、recruitment、inhibition、layer proposal | 搜索优先级、candidate attention、外部 evidence collection | 创建 evidence、改变 commit truth、签发 certificate |
| Truth/authority | 已验证的 principal、risk、membership、evidence、counterevidence、challenge、lease、stop、permission、replay 与 prior-window record | Commit metrics、terminal outcome、certificate 与 action gate | 调用 provider 或绕过 declared policy |

Manifest 选择 assurance level：

| Assurance | 所需结果 |
| --- | --- |
| `advisory` | Advisory 或 declared fallback；不产生 epistemic commit |
| `evidence_bound` | 稳定 evidence decision 加当前 local receipt |
| `certified` | Evidence-bound proof 加可独立验证的 portable certificate |
| `distributed` | Portable proof 加 static-epoch Byzantine quorum finality |

`evaluate_hybrid_commit_step(request=...)` 是统一的最终裁决边界。Assurance 不会
静默降级，identifier order 不会打破 tie，absolute deadline 也不能被延长。到达 deadline
时必须返回显式 commit 或 non-commit terminal outcome。这个保证要求外部 runtime 持续
用单调递增的 logical step 调用 evaluator；protocol-core 不负责调度调用，也不推进时钟。
Distributed assurance 验证 `n >= 3f + 1`、`2q - n > f`、精确 witness/value root、
replay、equivocation 与 conflict freeze；networking 和 witness collection 仍由外部
runtime 负责。

## 运行时集成

每个外部 runtime request 都应创建 `RuntimeScope(tenant_id, run_id, request_id)`。由
tenant/run 派生的
`scope_ref` 绑定 Kernel plan、Driver invocation/result receipt、Governance authority
domain 与 scoped Trace。来自另一个 scope 的相同 payload 不是 retry，也不能复用 authority。

持久 v2 权威通过外部 adapter 接入：

- `GovernanceStateStoreV2` 提供显式 head、compare-and-swap、immutable prepared
  transition、atomic state-plus-authority-Trace batch、receipt、rehydration、retirement
  与 tombstone。
- v2 持久序列是 `准备并验证 exact portable request（仅在该 ABI 定义时携带
  context-bound source proof）-> 绑定并打开 request-scoped authority session ->
  atomic_commit_v2(state + authority-critical Trace) -> 验证 typed committed result 与
  receipt -> 重用前 rehydrate 并重新检查 inclusion/currentness`。在精确 state 和 Trace
  batch 完成提交并通过验证前，proposal 不能暴露持久 output authority。
- `ScopedTraceStoreV2` 是面向已选 tenant/run scope 的独立 provider-neutral
  append-only lineage contract。
- 内置 in-memory store 是确定性 reference adapter，不是生产数据库。外部 store 可在
  集成前运行 `run_governance_state_store_conformance_v2(...)` 与
  `run_scoped_trace_store_conformance_v2(...)`。未版本化的
  `GovernanceStateStore` 仍是 v1 trusted-host Draft 兼容路径；generic `TraceStore`
  仍是独立的 reconstructible projection。两者都不是 v2 的 alias 或静默升级。

Driver declaration 可以使用 opaque `config_ref`；provider kind、version 与 capability
metadata 可以声明，但 credential 与具体 connection configuration 必须留在 manifest
之外。仅提供大模型 API key 还不足以运行 multi-agent system：外部 runtime 还必须提供
model/tool adapter、orchestration、符合 Conformance 的 store、取消/重试/恢复与 output
delivery。PheroOS 本身不会读取该 key。

参见 [runtime integration contract](docs/protocol/runtime-integration.md) 与
[runtime adapter guide](docs/protocol/runtime-adapter-guide.md)。

## ABI 版本与兼容性

原始无版本 schema ID 和 CLI alias 是冻结的 v1 compatibility root。新语义使用独立
document 与精确 selector：

| Surface | 冻结 v1 `$id` / alias | Versioned compatibility document | 当前精确 opt-in |
| --- | --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json`; `capability`, `capability-v1` | `schemas/capability-v2.schema.json`; `pheroos-capability-schema-v2`; payload `pheroos.protocol.v1` | `schemas/capability-v3.schema.json`; `pheroos-capability-schema-v3`; payload `pheroos.protocol.v2` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json`; `protocol`, `protocol-v1` | `schemas/protocol-v2.schema.json`; `pheroos-protocol-schema-v2`; payload `pheroos.protocol.v1` | `schemas/protocol-v3.schema.json`; `pheroos-protocol-schema-v3`; payload `pheroos.protocol.v2` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json`; `driver`, `driver-v1` | `schemas/driver-v2.schema.json` | `descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json`; `kernel`, `kernel-v1` | `schemas/kernel-v2.schema.json` | `plan_version=pheroos-kernel-plan-v2` |
| Runtime scope | 无 | 无 | `schemas/runtime-scope-v1.schema.json`; `pheroos-runtime-scope-v1` |
| Scoped authority | 无 | 无 | `schemas/authority-v2.schema.json`; `pheroos-authority-schema-v2`; `schemas/scoped-authority-tck-v2.schema.json`; `pheroos-scoped-authority-tck-v2` |

Schema-document version 与 protocol payload version 相互独立。Capability/Protocol v3
是 scoped authority v2 的精确 Draft opt-in。Driver 的 `descriptor_version` 与
`DriverDescriptor.version` 中的外部 provider version 相互独立；Kernel 使用
`plan_version` 独立选择 plan。

Reader 必须显式选择版本；object shape 或 package version 绝不会把 v1 静默升级到 v2。
Migration 不能编造 readiness、scope、capability、provider-version 或 authority fact。
公共 Python shape 与 lifecycle 分别记录在
[`public-python-api-v1.json`](pheroos/conformance/abi/public-python-api-v1.json) 和
[`public-python-api-lifecycle-v1.json`](pheroos/conformance/abi/public-python-api-lifecycle-v1.json)。

`pheroos validate`、`pheroos conformance` 与 `pheroos profile show` 选择 legacy v1
manifest profile。Capability/Protocol v3 artifact 使用精确 wire validation 和专用的 v2
Store/session/runtime Conformance；legacy command 不会根据 object shape 推断 v2。

Namespaced `x-*`、`ext.*` 与 manifest `extensions` 保持开放，但只能作为非权威 metadata。
新增能够改变 commit truth 或 authority 的 record 必须具有 versioned ABI、validation、
Trace lineage、Conformance 与 migration note。

参见 [schema migration rules](docs/process/schema-v1-v2-migration.md)、
[API lifecycle](docs/process/api-lifecycle.md) 与
[extension boundaries](docs/protocol/extension-points.md)。

## CLI 参考

本地 CLI 不会启动服务：

```bash
pheroos version
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos source-conformance .
pheroos profile show examples/hybrid-commit-protocol/capability.json
pheroos schema list
pheroos schema show commit
pheroos schema export commit > commit.schema.json
pheroos wire validate commit path/to/commit-record.json
pheroos wire validate capability-v3 examples/hybrid-replay-protocol/capability.json
pheroos tck run --version v1
pheroos tck run --version v2
pheroos abi show
pheroos abi diff
```

未知 critical version 和 malformed wire record 会返回 versioned、fail-closed JSON result，
并使用非零 exit status。

## 示例

所有示例均为 deterministic、provider-free、network-free、domain-neutral。

| 示例 | 证明内容 |
| --- | --- |
| [`toy-protocol`](examples/toy-protocol/) | 最小 manifest、declared candidate、quorum 与 fallback |
| [`e2e-protocol`](examples/e2e-protocol/) | 最小 Protocol -> Kernel -> Driver -> Governance -> Trace vertical slice |
| [`swarm-protocol`](examples/swarm-protocol/) | 基础 verified swarm signal 与 bounded pheromone memory |
| [`hybrid-pheromone-protocol`](examples/hybrid-pheromone-protocol/) | 完整 Hybrid collective step 与四个 output gate |
| [`hybrid-replay-protocol`](examples/hybrid-replay-protocol/) | Scoped Hybrid Replay v2、重启与 fresh-process continuation |
| [`adaptive-pheromone-replay`](examples/adaptive-pheromone-replay/) | 外部 adaptive proposal 与 governance-issued replay state |
| [`scoped-output-protocol`](examples/scoped-output-protocol/) | Baseline Output v2 activation、current grant 与 atomic output commit |
| [`runtime-integration-protocol`](examples/runtime-integration-protocol/) | 精确版本的 Driver、authority、Trace、recovery 与 delivery transcript |
| [`risk-v2-protocol`](examples/risk-v2-protocol/) | Store-backed risk authority 与 restart-safe currentness |
| [`support-v2-protocol`](examples/support-v2-protocol/) | Principal、membership 与 support authority v2 |
| [`hybrid-commit-protocol`](examples/hybrid-commit-protocol/) | Attention/truth 分离、stability、liveness 与 no downgrade |
| [`commit-evidence-v2-protocol`](examples/commit-evidence-v2-protocol/) | Durable evidence truth 与 counterevidence binding |
| [`commit-decision-v2-protocol`](examples/commit-decision-v2-protocol/) | 带精确 evidence lineage 的 durable terminal decision |
| [`commit-certificate-v2-protocol`](examples/commit-certificate-v2-protocol/) | Portable certificate verification、authority-leaf binding 与 tamper rejection |
| [`commit-certificate-replay`](examples/commit-certificate-replay/) | Portable certificate 重建与 mutation/replay rejection |
| [`distributed-commit-protocol`](examples/distributed-commit-protocol/) | Byzantine quorum、provisional state、conflict freeze 与 deadline |
| [`distributed-commit-v2-protocol`](examples/distributed-commit-v2-protocol/) | Durable distributed witness/finality authority |
| [`commit-finality-v2-protocol`](examples/commit-finality-v2-protocol/) | Decision-to-certificate-to-distributed finality composition |

## 一致性验证与发布完整性

冻结的 Commit TCK v1 包含 38 个 legacy adversarial vector。TCK v2 使用 23 个
expected-free declarative case：adapter 只接收 input，expected result 由 harness 持有。
公共 reference adapter 与独立 standard-library spec model 必须一致；malformed、
echo/constant、out-of-order、state-leaking 与 timeout adapter 必须被拒绝。

常用验证命令：

```bash
python -m pytest -q
pheroos source-conformance .
python scripts/generate_schema_artifacts.py --check
python scripts/generate_commit_tck.py --check
python scripts/generate_public_api_inventory.py --check
python scripts/generate_governance_public_api.py --check
```

CI 覆盖 CPython 3.12 至 3.14，验证 import DAG 与 public ABI，从外部工作目录分别测试
wheel/sdist 安装并执行 reference performance budget。Release gate 绑定完整 workflow
execution context，使用 hash-closed Ubuntu x86_64 CPython 3.12-3.14 toolchain，从原始 Git
tree/blob object 快照 candidate，并从精确 wheel/sdist metadata 与 filename 派生
CycloneDX/SPDX identity。Provenance 证明 artifact 来源，但不创建 protocol evidence 或
governance authority。已检入的 branch/tag ruleset 与 immutable-release setting 只是
inert policy，并未成为远程保护。这是 build 与 attestation pipeline，不是 GitHub Release
或 package publication 的证据。参见
[Conformance Suite](docs/conformance/conformance-suite.md) 与
[release checklist](docs/process/release-checklist.md)。

## 文档

- 核心规范：[SPEC.md](SPEC.md)
- Hybrid Pheromone：[ABI reference](docs/protocol/hybrid-pheromone-abi.md)、
  [durable Replay v2](docs/protocol/hybrid-replay-v2.md) 与
  [v1 migration](docs/protocol/hybrid-pheromone-v1-migration.md)
- Optimal Commit：[ABI reference](docs/protocol/optimal-commit-abi.md) 与
  [v1 migration](docs/protocol/optimal-commit-v1-migration.md)
- 项目流程：[development index](docs/process/index.md)、
  [CONTRIBUTING.md](CONTRIBUTING.md) 与 [CHANGELOG.md](CHANGELOG.md)
- 安全：[SECURITY.md](SECURITY.md)

## 非目标

Protocol-core 不是 agent framework、model-provider gateway、FastAPI 或 product server、
dashboard、LangGraph runtime、provider SDK wrapper、database、queue、worker pool、daemon、
plugin marketplace 或 domain workflow package。外部 runtime 可以围绕 ABI 实现这些能力。

## 开发

变更应保持 small、deterministic、domain-neutral、provider-free，并直接由 test、example、
Trace 或 Conformance 覆盖。不要为了让测试通过而削弱 package boundary。

## 许可证

参见 [LICENSE](LICENSE)。
