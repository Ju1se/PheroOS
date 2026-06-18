# PheroOS

<a id="readme-language-switch"></a>

<p align="center"><strong>Read this README in / 选择阅读语言</strong></p>
<p align="center">
  <a href="#english-readme"><kbd><strong>English</strong></kbd></a>
  &nbsp;
  <a href="#chinese-readme"><kbd><strong>简体中文</strong></kbd></a>
</p>

<details open id="english-readme">
<summary><strong>English README</strong> - click to expand or collapse</summary>

<p align="right"><a href="#chinese-readme">Switch to 简体中文</a></p>

PheroOS is an open **AI-as-OS protocol core** for governed, swarm-native multi-agent runtimes.

> Agents are not authority. Protocol is authority.

PheroOS defines the protocol boundary between agents, kernel planning, governance decisions, driver capabilities, trace lineage, and conformance checks. It is intentionally small: this repository is a protocol-core package, not an app runtime.

## What This Repository Contains

This repository contains the public protocol-core surfaces for PheroOS:

- **Protocol ABI** - capability manifests, protocol manifests, schemas, loading, and validation.
- **Kernel ABI** - input envelopes, OS plans, capability resolution, permission grants, runtime contexts, and syscall-style boundaries.
- **Governance Core** - authority levels, signals, evidence, stop signals, quorum decisions, collective decisions, recovery traces, and output authorization.
- **Driver ABI** - generic driver descriptors, registry, lifecycle, health, bindings, handles, and standardized results.
- **Trace ABI** - canonical trace events, append-only records, and required-event validation.
- **Conformance Suite** - deterministic compatibility checks for protocol, kernel, governance, driver, trace, and package boundaries.
- **Provider-free examples** - minimal manifests that require no API keys, model provider, network connection, app server, or database.

## Open Protocol Materials

The public protocol materials are:

- [SPEC.md](SPEC.md) - protocol-core specification and compatibility requirements.
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - public API and ABI lifecycle policy.
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - supported extension boundaries.
- [docs/process/release-checklist.md](docs/process/release-checklist.md) - release validation checklist.
- [CHANGELOG.md](CHANGELOG.md) - notable draft ABI changes and migration notes.

## What This Repository Is Not

PheroOS protocol-core is not:

- an agent framework;
- a prompt-chain framework;
- a FastAPI product server;
- a dashboard or frontend;
- a LangGraph graph runtime;
- a model-provider router;
- a LiteLLM/OpenAI/Ollama/vLLM wrapper;
- a plugin marketplace;
- a finance, WRDS, valuation, or other domain-specific workflow package;
- a complete operating-system daemon.

Full runtime infrastructure should live outside protocol-core and implement the ABI exposed here.

## Design Model

PheroOS uses an operating-system-inspired boundary model:

| OS-style role | PheroOS surface | Responsibility |
| --- | --- | --- |
| Userspace process | Agent | Proposes work, evidence, signals, and candidates. |
| Kernel boundary | `pheroos.kernel` | Plans available capabilities and materializes run-scoped context. |
| Device driver | `pheroos.drivers` | Provides model/tool/data/storage/sandbox capability through a generic lifecycle. |
| Security / governance hook | `pheroos.governance` | Verifies authority, resolves stops, commits candidates, and authorizes output. |
| Audit / proc-style view | `pheroos.trace` | Records lineage for decisions, evidence, calls, fallback, and output. |
| Compatibility court | `pheroos.conformance` | Proves that manifests and implementations obey protocol-core invariants. |

The kernel plans availability. It does not make domain conclusions, call tools directly, or access secrets directly.

Governance decides what is allowed. Agents may propose; governance authority is required to verify.

Drivers provide capability. Protocol provides authority.

## Protocol Layers

PheroOS currently has three provider-free protocol layers.

### 1. Baseline Governed Protocol

`examples/toy-protocol/` is the smallest protocol example. It demonstrates:

- declared targets;
- declared candidates;
- safe fallback candidate;
- quorum policy;
- recovery policy;
- evidence policy;
- output policy;
- required trace events.

This is the baseline compatibility layer. It does not require swarm behavior.

### 2. Governed E2E Protocol Slice

`examples/e2e-protocol/` demonstrates a minimal end-to-end governed vertical slice:

```text
manifest -> validation -> kernel plan -> runtime context -> driver exposure -> evidence -> signal -> commit -> recovery/output trace
```

It remains provider-free and deterministic.

### 3. Swarm-Native Collective Protocol

`examples/swarm-protocol/` demonstrates optional swarm-native collective decision behavior.

Swarm-native behavior is inspired by bee-swarm and ant-colony mechanisms, but encoded as protocol semantics, not as a large swarm framework.

| Biological mechanism | PheroOS protocol concept |
| --- | --- |
| Scout bee | Independent `ScoutReport` |
| Nest site | Declared candidate |
| Waggle dance | `RecruitmentSignal` |
| Stop / dissent | `InhibitionSignal` |
| Pheromone trail | `PheromoneTrail` |
| Evaporation | Pheromone confidence decay |
| Swarm quorum | Collective consensus threshold |
| Failed convergence | Declared safe fallback candidate |

A manifest may declare:

```json
"collective_decision_policy": {
  "mode": "hybrid",
  "min_independent_scouts": 2,
  "quorum_threshold": 3,
  "recruitment_enabled": true,
  "inhibition_enabled": true,
  "pheromone_enabled": true,
  "pheromone_evaporation_rate": 0.25,
  "fallback_candidate": "candidate:safe_fallback"
}
```

Supported collective modes:

```text
quorum
bee_swarm
ant_colony
hybrid
```

Swarm-specific trace and conformance checks apply only to swarm modes:

```text
bee_swarm
ant_colony
hybrid
```

Baseline quorum-only protocols continue to validate and pass conformance without swarm trace events.

## Core Invariants

PheroOS protocol-core validates these invariants:

- Protocols must declare at least one target.
- Protocols must declare at least one candidate.
- Every candidate must reference a declared target.
- Quorum fallback must reference a declared safe fallback candidate.
- Collective fallback must reference a declared safe fallback candidate, or default to the quorum fallback.
- Recovery trigger targets must be declared.
- Recovery failure candidates must be declared.
- Writers may not create facts.
- Agents may not create facts when evidence policy forbids it.
- Required trace events must be declared.
- Swarm trace events are required only for swarm collective modes.
- Public core must remain domain-neutral.
- Core packages must preserve import boundaries.

## Driver Lifecycle

Drivers are generic capability providers. The driver lifecycle is:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

Driver contracts are intentionally provider-neutral. Real provider integrations should not live in protocol-core.

## Trace ABI

`pheroos.trace.TraceEvent` is the canonical Trace ABI.

Trace events are small, explicit, and provider-neutral. Current event types include baseline governed events and swarm-native events such as:

```text
plan
explore
grant
expose
invoke
evidence
scout_report
signal
recruit
inhibit
pheromone_deposit
pheromone_evaporate
pheromone_score
pheromone_clip
pheromone_expire
pheromone_inhibit
candidate_score
consensus_check
block
commit
fallback
recovery
output
```

Trace is not a database, queue, event bus, or runtime monitor. The core package provides minimal append-only trace support for tests and conformance.

## Quick Start

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests:

```bash
python -m pytest -q
```

Validate the baseline protocol:

```bash
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
```

Validate the governed E2E protocol:

```bash
python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol
```

Validate the swarm-native protocol:

```bash
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
```

Export schemas:

```bash
python -m pheroos.cli.main schema export protocol
python -m pheroos.cli.main schema export kernel
python -m pheroos.cli.main schema export driver
python -m pheroos.cli.main schema export trace
```

If the package is installed with console scripts available, the equivalent commands are:

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos schema export protocol
```

## Repository Layout

```text
pheroos/
  protocol/       Protocol ABI models, manifest loading, schema helpers, validation.
  kernel/         Kernel ABI models, planning, permissions, runtime materialization.
  governance/     Authority, signals, evidence, quorum, collective decisions, output authorization.
  drivers/        Generic driver descriptors, registry, lifecycle, handles, results.
  trace/          Canonical trace events and append-only test store.
  conformance/    Compatibility checks and conformance reports.
  cli/            Thin command-line wrapper around core packages.

examples/
  toy-protocol/    Baseline governed protocol example.
  e2e-protocol/    Provider-free governed vertical slice.
  swarm-protocol/  Provider-free swarm-native collective protocol.

schemas/           Exported protocol schema artifacts.
docs/              ABI-focused documentation.
tests/             Deterministic protocol-core tests.
```

## Conformance

`pheroos.conformance` is the compatibility gate for PheroOS protocol-core.

Checks include:

- manifest schema;
- candidate declaration;
- quorum policy;
- collective policy;
- safe collective fallback;
- pheromone policy;
- pheromone behavior;
- recovery policy;
- output contract;
- trace contract;
- swarm trace contract;
- driver contract;
- domain-neutral public core;
- kernel import boundary.

Conformance checks must stay deterministic, provider-free, network-free, and explicit about the invariant they enforce.

## API and ABI Management

PheroOS is currently a draft ABI. Public package exports, schema artifacts, CLI commands, provider-free examples, and conformance checks are managed as the public compatibility surface.

Changes to public API or ABI should include:

- tests or conformance coverage;
- schema updates when manifest or artifact shape changes;
- changelog notes;
- migration notes when behavior changes;
- no new runtime, provider, server, dashboard, database, or domain workflow dependency.

The compatibility rule is additive by default: new behavior should be opt-in when possible, and baseline protocols should not be forced into swarm-specific requirements.

## AI Coding Assistants

If you are using Codex or another AI coding assistant, read `AGENTS.md` before changing code.

Important rules:

- Do not restore the removed app runtime.
- Do not add provider SDKs, web frameworks, dashboards, or domain workflows to protocol-core.
- Do not add broad protection-layer frameworks.
- Keep swarm-native work inside protocol, governance, trace, conformance, examples, and tests.
- Preserve baseline protocol compatibility.
- Add tests before or alongside behavior.

## Project Status

| Surface | Status |
| --- | --- |
| Protocol models | implemented, draft ABI |
| Protocol validation | implemented |
| Kernel models | implemented, minimal ABI |
| Runtime materializer | implemented, minimal ABI |
| Governance primitives | implemented |
| Collective decision primitives | implemented, draft ABI |
| Driver lifecycle | implemented, minimal ABI |
| Trace ABI | implemented, minimal provider-free surface |
| Conformance runner | implemented |
| CLI | implemented |
| Toy protocol | implemented |
| E2E protocol | implemented |
| Swarm protocol | implemented |
| Stable public ABI | draft |
| Full runtime daemon | out of scope for this repository |

## Development Principles

PheroOS should evolve through small, testable ABI increments.

Prefer:

- explicit dataclasses;
- pure functions;
- deterministic examples;
- provider-free conformance tests;
- stable package boundaries;
- minimal dependencies.

Avoid:

- speculative orchestration layers;
- broad safety/protection managers;
- product runtime code;
- provider-specific integrations;
- domain-specific workflows;
- changes that force baseline protocols to become swarm protocols.

## License

See `LICENSE`.

</details>

<details id="chinese-readme">
<summary><strong>简体中文 README</strong> - 点击展开或收起</summary>

<p align="right"><a href="#english-readme">Switch to English</a></p>

PheroOS 是一个开放的 **AI-as-OS 协议核心**，面向受治理、群体原生的多智能体运行时。

> Agents are not authority. Protocol is authority.

PheroOS 定义智能体、内核规划、治理决策、驱动能力、追踪谱系和一致性检查之间的协议边界。它刻意保持小而聚合：本仓库是 protocol-core package，不是应用运行时。

## 本仓库包含什么

本仓库包含 PheroOS 的公共 protocol-core 表面：

- **Protocol ABI** - capability manifest、protocol manifest、schema、加载和验证。
- **Kernel ABI** - 输入信封、OS plan、能力解析、权限授予、运行时上下文和 syscall 风格边界。
- **Governance Core** - 权威等级、信号、证据、stop signal、quorum 决策、collective decision、恢复 trace 和输出授权。
- **Driver ABI** - 通用驱动描述符、注册表、生命周期、健康状态、绑定、handle 和标准化结果。
- **Trace ABI** - 规范 trace event、append-only record 和 required-event validation。
- **Conformance Suite** - 针对 protocol、kernel、governance、driver、trace 和 package boundary 的确定性兼容性检查。
- **Provider-free examples** - 最小 manifest 示例，不需要 API key、模型 provider、网络连接、应用服务器或数据库。

## 开放协议材料

公共协议材料包括：

- [SPEC.md](SPEC.md) - protocol-core 规范和兼容性要求。
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - 公共 API 与 ABI 生命周期策略。
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - 支持的扩展边界。
- [docs/process/release-checklist.md](docs/process/release-checklist.md) - 发布验证清单。
- [CHANGELOG.md](CHANGELOG.md) - draft ABI 的重要变更和迁移说明。

## 本仓库不是什么

PheroOS protocol-core 不是：

- agent framework；
- prompt-chain framework；
- FastAPI product server；
- dashboard 或 frontend；
- LangGraph graph runtime；
- model-provider router；
- LiteLLM/OpenAI/Ollama/vLLM wrapper；
- plugin marketplace；
- finance、WRDS、valuation 或其他领域特定 workflow package；
- 完整的 operating-system daemon。

完整运行时基础设施应该位于 protocol-core 之外，并实现这里暴露的 ABI。

## 设计模型

PheroOS 使用类似操作系统的边界模型：

| OS 风格角色 | PheroOS 表面 | 职责 |
| --- | --- | --- |
| Userspace process | Agent | 提出 work、evidence、signal 和 candidate。 |
| Kernel boundary | `pheroos.kernel` | 规划可用能力并物化 run-scoped context。 |
| Device driver | `pheroos.drivers` | 通过通用生命周期提供 model/tool/data/storage/sandbox 能力。 |
| Security / governance hook | `pheroos.governance` | 验证 authority、解析 stop、提交 candidate，并授权 output。 |
| Audit / proc-style view | `pheroos.trace` | 记录 decision、evidence、call、fallback 和 output 的 lineage。 |
| Compatibility court | `pheroos.conformance` | 证明 manifest 和 implementation 遵守 protocol-core invariant。 |

Kernel 规划可用性。它不做领域结论，不直接调用工具，也不直接访问 secret。

Governance 决定什么被允许。Agent 可以提出建议；验证需要 governance authority。

Driver 提供能力。Protocol 提供权威。

## 协议层

PheroOS 当前有三个 provider-free 协议层。

### 1. Baseline Governed Protocol

`examples/toy-protocol/` 是最小协议示例。它展示：

- declared targets；
- declared candidates；
- safe fallback candidate；
- quorum policy；
- recovery policy；
- evidence policy；
- output policy；
- required trace events。

这是 baseline compatibility layer。它不要求 swarm behavior。

### 2. Governed E2E Protocol Slice

`examples/e2e-protocol/` 展示最小端到端治理垂直切片：

```text
manifest -> validation -> kernel plan -> runtime context -> driver exposure -> evidence -> signal -> commit -> recovery/output trace
```

它保持 provider-free 和 deterministic。

### 3. Swarm-Native Collective Protocol

`examples/swarm-protocol/` 展示可选的 swarm-native collective decision behavior。

Swarm-native behavior 受蜂群和蚁群机制启发，但编码为协议语义，而不是大型 swarm framework。

| 生物机制 | PheroOS 协议概念 |
| --- | --- |
| Scout bee | Independent `ScoutReport` |
| Nest site | Declared candidate |
| Waggle dance | `RecruitmentSignal` |
| Stop / dissent | `InhibitionSignal` |
| Pheromone trail | `PheromoneTrail` |
| Evaporation | Pheromone confidence decay |
| Swarm quorum | Collective consensus threshold |
| Failed convergence | Declared safe fallback candidate |

Manifest 可以声明：

```json
"collective_decision_policy": {
  "mode": "hybrid",
  "min_independent_scouts": 2,
  "quorum_threshold": 3,
  "recruitment_enabled": true,
  "inhibition_enabled": true,
  "pheromone_enabled": true,
  "pheromone_evaporation_rate": 0.25,
  "fallback_candidate": "candidate:safe_fallback"
}
```

支持的 collective modes：

```text
quorum
bee_swarm
ant_colony
hybrid
```

Swarm-specific trace 和 conformance checks 只适用于 swarm modes：

```text
bee_swarm
ant_colony
hybrid
```

Baseline quorum-only protocol 可以继续验证并通过 conformance，不需要 swarm trace events。

## 核心不变量

PheroOS protocol-core 验证以下不变量：

- Protocol 必须声明至少一个 target。
- Protocol 必须声明至少一个 candidate。
- 每个 candidate 必须引用已声明 target。
- Quorum fallback 必须引用已声明的 safe fallback candidate。
- Collective fallback 必须引用已声明的 safe fallback candidate，或者默认使用 quorum fallback。
- Recovery trigger target 必须已声明。
- Recovery failure candidate 必须已声明。
- Writer 不得创建 fact。
- 当 evidence policy 禁止时，agent 不得创建 fact。
- Required trace events 必须声明。
- Swarm trace events 只在 swarm collective modes 下要求。
- Public core 必须保持 domain-neutral。
- Core packages 必须保持 import boundaries。

## Driver Lifecycle

Driver 是通用能力 provider。Driver lifecycle 是：

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

Driver contract 刻意保持 provider-neutral。真实 provider integration 不应放在 protocol-core 内。

## Trace ABI

`pheroos.trace.TraceEvent` 是规范 Trace ABI。

Trace event 小、明确、provider-neutral。当前 event types 包含 baseline governed events 和 swarm-native events，例如：

```text
plan
explore
grant
expose
invoke
evidence
scout_report
signal
recruit
inhibit
pheromone_deposit
pheromone_evaporate
pheromone_score
pheromone_clip
pheromone_expire
pheromone_inhibit
candidate_score
consensus_check
block
commit
fallback
recovery
output
```

Trace 不是 database、queue、event bus 或 runtime monitor。Core package 只为测试和 conformance 提供最小 append-only trace 支持。

## 快速开始

```bash
git clone https://github.com/Ju1se/PheroOS.git
cd PheroOS
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

运行测试：

```bash
python -m pytest -q
```

验证 baseline protocol：

```bash
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
```

验证 governed E2E protocol：

```bash
python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol
```

验证 swarm-native protocol：

```bash
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
```

导出 schema：

```bash
python -m pheroos.cli.main schema export protocol
python -m pheroos.cli.main schema export kernel
python -m pheroos.cli.main schema export driver
python -m pheroos.cli.main schema export trace
```

如果 package 已安装并可使用 console script，等价命令为：

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos schema export protocol
```

## 仓库结构

```text
pheroos/
  protocol/       Protocol ABI models, manifest loading, schema helpers, validation.
  kernel/         Kernel ABI models, planning, permissions, runtime materialization.
  governance/     Authority, signals, evidence, quorum, collective decisions, output authorization.
  drivers/        Generic driver descriptors, registry, lifecycle, handles, results.
  trace/          Canonical trace events and append-only test store.
  conformance/    Compatibility checks and conformance reports.
  cli/            Thin command-line wrapper around core packages.

examples/
  toy-protocol/    Baseline governed protocol example.
  e2e-protocol/    Provider-free governed vertical slice.
  swarm-protocol/  Provider-free swarm-native collective protocol.

schemas/           Exported protocol schema artifacts.
docs/              ABI-focused documentation.
tests/             Deterministic protocol-core tests.
```

## Conformance

`pheroos.conformance` 是 PheroOS protocol-core 的 compatibility gate。

Checks 包括：

- manifest schema；
- candidate declaration；
- quorum policy；
- collective policy；
- safe collective fallback；
- pheromone policy；
- pheromone behavior；
- recovery policy；
- output contract；
- trace contract；
- swarm trace contract；
- driver contract；
- domain-neutral public core；
- kernel import boundary。

Conformance checks 必须保持 deterministic、provider-free、network-free，并明确说明它们 enforced 的 invariant。

## API 与 ABI 管理

PheroOS 当前是 draft ABI。Public package exports、schema artifacts、CLI commands、provider-free examples 和 conformance checks 被作为公共兼容性表面管理。

Public API 或 ABI 的变更应该包含：

- tests 或 conformance coverage；
- manifest 或 artifact shape 变化时的 schema updates；
- changelog notes；
- behavior 变化时的 migration notes；
- 不引入 runtime、provider、server、dashboard、database 或 domain workflow dependency。

兼容性规则默认是 additive：新行为应尽量 opt-in，baseline protocol 不应被迫满足 swarm-specific requirements。

## AI Coding Assistants

如果你使用 Codex 或其他 AI coding assistant，在改代码前请阅读 `AGENTS.md`。

重要规则：

- 不要恢复已移除的 app runtime。
- 不要向 protocol-core 添加 provider SDK、web framework、dashboard 或 domain workflow。
- 不要添加宽泛的 protection-layer framework。
- 将 swarm-native work 保持在 protocol、governance、trace、conformance、examples 和 tests 内。
- 保持 baseline protocol compatibility。
- 在行为变更前或同时添加测试。

## 项目状态

| Surface | Status |
| --- | --- |
| Protocol models | implemented, draft ABI |
| Protocol validation | implemented |
| Kernel models | implemented, minimal ABI |
| Runtime materializer | implemented, minimal ABI |
| Governance primitives | implemented |
| Collective decision primitives | implemented, draft ABI |
| Driver lifecycle | implemented, minimal ABI |
| Trace ABI | implemented, minimal provider-free surface |
| Conformance runner | implemented |
| CLI | implemented |
| Toy protocol | implemented |
| E2E protocol | implemented |
| Swarm protocol | implemented |
| Stable public ABI | draft |
| Full runtime daemon | out of scope for this repository |

## 开发原则

PheroOS 应通过小而可测试的 ABI increments 演进。

Prefer：

- explicit dataclasses；
- pure functions；
- deterministic examples；
- provider-free conformance tests；
- stable package boundaries；
- minimal dependencies。

Avoid：

- speculative orchestration layers；
- broad safety/protection managers；
- product runtime code；
- provider-specific integrations；
- domain-specific workflows；
- changes that force baseline protocols to become swarm protocols。

## License

参见 `LICENSE`。

</details>
