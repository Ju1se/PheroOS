# PIP-0002: PheroOS Kernel ABI v0.1

Status: Draft
Type: Kernel
Created: 2026-06-09
Requires: PIP-0001

## Abstract

Define the initial PheroOS Kernel ABI around OS planning, runtime
materialization, capability resolution, driver exposure, signal governance,
quorum, recovery, output, and trace explanation.

## Motivation

External contributors need a stable kernel surface. Without an ABI, PheroOS
looks like an internal LangGraph application rather than a protocol kernel.

## Specification

The initial syscall set is documented in
`docs/kernel/kernel-syscalls.md`. `OSPlan` and `RuntimeContext` are documented
in `docs/kernel/os-plan-contract.md` and
`docs/kernel/runtime-context-contract.md`.

## Compatibility

The v0.1 ABI wraps current `runtime/*` modules. Existing imports remain valid.
Future work may move implementations under `pheroos/kernel/` after compatibility
tests are in place.

## Security Considerations

User-mode agents may propose. Kernel-mode actors may verify, block, commit,
publish, and explain. Driver-mode adapters may return structured results but
cannot author conclusions.

## Reference Implementation

The current reference implementation lives in `runtime/`, `runtime/swarm/`,
`runtime/tool_registry.py`, and `runtime/runtime_context.py`.

## Conformance Tests

Initial conformance tests live in `tests/conformance/`.

## Migration Plan

Additive wrappers and schemas come first. Directory moves and import-path
renames require a later PIP.
