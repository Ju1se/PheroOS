# PheroOS

语言：[English](README.md) | **简体中文**

PheroOS 是面向受治理、群体原生多智能体运行时的 protocol-core package。

Agents are not authority. Protocol is authority.

本仓库定义 ABI contract、validation、governance semantics、driver boundary、trace lineage 和 conformance checks。它不是应用运行时。

## 状态

PheroOS 当前是 draft ABI。

公共接口由 conformance 支撑，但尚未稳定。兼容性变更应尽量保持 additive，并且不应强迫 baseline protocol 满足 swarm-specific requirements。

## 文档

- [SPEC.md](SPEC.md) - protocol-core 规范。
- [docs/protocol/runtime-integration.md](docs/protocol/runtime-integration.md) - 外部 runtime 如何与 PheroOS 组合。
- [docs/protocol/extension-points.md](docs/protocol/extension-points.md) - 扩展边界。
- [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) - 公共 API 与 ABI 生命周期。
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

## Runtime 集成

外部 runtime 可以 fork 或依赖本仓库，并围绕 ABI 构建自己的 agent loop、model call、tool call、database、memory store、scheduling、queue、server 和 secret management。

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

Manifest extension 是 metadata，除非被协议不变量正式采用。Extension metadata 不创建 evidence、permission、quorum、commit authority 或 output authority。

## 开发

保持变更 small、deterministic、provider-free、network-free 和 domain-neutral。

优先使用 dataclass、pure function、explicit validation、small schema、provider-free example、direct test 和 conformance check。

不要为了让测试通过而削弱 package boundary。

## License

参见 [LICENSE](LICENSE)。
