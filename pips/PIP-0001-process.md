# PIP-0001: PheroOS Improvement Proposal Process

Status: Draft
Type: Process
Created: 2026-06-09

## Abstract

PheroOS Improvement Proposals define how protocol, kernel ABI, driver model,
security model, trace contract, and conformance changes are proposed and
reviewed.

## Motivation

PheroOS should evolve as open infrastructure, not as an ad hoc private runtime.
Protocol-facing changes need compatibility notes, security review, and tests.

## Specification

Each PIP should include:

- Abstract
- Motivation
- Specification
- Compatibility
- Security Considerations
- Reference Implementation
- Conformance Tests
- Migration Plan

PIP status values are Draft, Accepted, Final, Deprecated, and Rejected.

## Compatibility

PIPs are required for changes that alter schema versions, kernel syscalls,
driver contracts, capability ABI, conformance levels, trace semantics, or
security authority.

## Security Considerations

Security-sensitive PIPs must describe user-mode, kernel-mode, and driver-mode
authority boundaries.

## Reference Implementation

The reference implementation lives in this repository until a separate
distribution process exists.

## Conformance Tests

Accepted protocol/kernel PIPs must name conformance tests before becoming
Final.

## Migration Plan

Breaking changes require compatibility aliases, deprecation notes, or an
explicit major-version boundary.
