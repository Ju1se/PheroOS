# Stable Core Consumer Contract

Status: Draft promotion-candidate guide. This document does not declare a
formally Stable ABI.

The machine-readable source of truth is
[`stable-python-api-v1.json`](../../pheroos/conformance/abi/stable-python-api-v1.json).
Its lifecycle must remain:

```text
stability=draft
status=promotion_candidate
formal_stable=false
```

The combined lifecycle is
`draft / promotion_candidate / formal_stable=false`.

Formal stability begins only after the separately governed external-runtime,
final-RC, independent-audit, and protected-main promotion gates complete.

## Consumer Boundary

The candidate is a type-closed projection of six public package facades. A
consumer must:

- import candidate symbols only from the package facades below;
- treat private modules, reference-adapter internals, and Draft Expert exports
  outside the candidate closure as non-contractual;
- use the packaged `pheroos/py.typed` marker and run a strict type checker;
- pin the exact package artifact and candidate artifact digest during RC
  validation;
- validate exact schema, protocol, Store, Trace, Driver, and TCK versions
  instead of inferring compatibility from Python shape;
- keep provider SDKs, credentials, databases, agent scheduling, and external
  effects outside protocol-core.

The current candidate roots are:

| Facade | Candidate roots |
| --- | --- |
| `pheroos.protocol` | `ProtocolSchemaVersionError`, `capability_schema_v3`, `protocol_schema_v3`, `read_capability_manifest`, `validate_capability_manifest` |
| `pheroos.kernel` | `InputEnvelope`, `OSKernel`, `RuntimeMaterializer`, `RuntimeScope`, `os_plan_from_dict` |
| `pheroos.drivers` | `DriverInvocationReplyV2`, `DriverInvocationRequestV2`, `DriverInvocationStoreV2`, `bind`, `expose`, `probe`, `register` |
| `pheroos.governance` | `AuthorityDomainV2`, `BaselineOutputRequestV2`, `BaselineOutputResultV2`, `GovernanceIssuerGrantV2`, `GovernanceStateStoreV2`, `IssuerGrantVerifierV2`, `activate_governance_issuer_grant_v2`, `baseline_verified_signal_proposal_root_v2`, `evaluate_and_commit_governed_baseline_output_v2`, `recover_baseline_output_result_v2`, `revoke_governance_issuer_grant_v2` |
| `pheroos.trace` | `ScopedTraceEvent`, `ScopedTraceStoreV2`, `TraceEvent`, `validate_event_lineage` |
| `pheroos.conformance` | `GovernanceStateStoreConformanceAdapterV2`, `run_conformance`, `run_governance_baseline_output_conformance_v2`, `run_governance_state_store_conformance_v2`, `run_source_conformance` |

Dependencies referenced by those roots are part of the checked candidate
closure even when they are not roots. The JSON artifact, not this prose table,
owns exact closure membership, signatures, canonical owners, constants,
exceptions, and public-base relationships.

## Governed Write Journey

The aggregate write entry point is:

```text
pheroos.governance.evaluate_and_commit_governed_baseline_output_v2
```

It is Governance-owned and composes the complete Baseline Output v2 write
path. The caller supplies portable declarations and a selected
`GovernanceStateStoreV2`; it does not receive an opaque authority capability or
session. The journey covers:

1. exact scoped grant activation;
2. verified signal preparation;
3. current action permission;
4. atomic output commit and receipt verification;
5. duplicate-free exact retry;
6. same-root restart recovery;
7. successor currentness denial;
8. revoked or expired grant denial;
9. blocked publication while preserving terminal delivery.

`BaselineOutputResultV2` is a durable Governance result. Delivery is not
publication or execution. Those external effects require a current,
target/action/payload-bound authorization and remain runtime responsibilities.

The executable strict-typing consumer is
[`tests/typing/stable_consumer.py`](../../tests/typing/stable_consumer.py).
The same file is executed after separate wheel and sdist installation from an
external working directory.

## External Adapter Rule

An external Store implementation should implement the public Protocol and pass
the public Conformance adapter contract. It must not copy or import the
reference Store's authority algorithm as its independent oracle.

At minimum, a runtime consumer must bind itself to:

- the checked
  [`runtime-compatibility-v1.json`](../../pheroos/conformance/abi/runtime-compatibility-v1.json);
- Capability/Protocol schema v3 and `pheroos.protocol.v2`;
- `GovernanceStateStoreV2`, `DriverInvocationStoreV2`, and
  `ScopedTraceStoreV2`;
- Baseline Output v2 and Runtime Integration v1 Conformance;
- the exact candidate package and artifact roots used for the run.

A self-reported root, digest, boolean, transport response, model result, or
portable projection cannot replace Store-backed authority verification.

## Verification

From a source checkout:

```bash
python -m pheroos.cli.main abi show --stable-only
python -m pheroos.cli.main abi diff --stable-only
python scripts/generate_stable_api_candidate.py --check
python scripts/check_stable_typing.py --check
python -m pytest -q \
  tests/conformance/test_stable_api_candidate.py \
  tests/packaging/test_stable_candidate_distributions.py
```

The distribution test is authoritative for package-data and external-CWD
consumption. A source-only import is not sufficient release evidence.

## Change and Promotion Rules

While the artifact is Draft, a reviewed candidate change may still alter the
closure. Such a change must update the generated artifact, migration notes,
strict consumer, distribution tests, and compatibility evidence together.

Formal promotion must not be inferred from a green candidate diff. It requires
the lifecycle-only protected-main promotion change, at least two RCs, exact
final-RC external/runtime validation, and independent audit described by the
[API lifecycle](../process/api-lifecycle.md) and the
[production-readiness plan](../process/production-readiness-hardening-goal-plan.md).
