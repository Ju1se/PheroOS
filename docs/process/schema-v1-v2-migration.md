# Schema Documents, Authority vNext, and Artifact Catalog

PheroOS freezes the original unversioned schema IDs as legacy v1 compatibility
artifacts. New validation semantics use versioned v2 IDs. Schema-document
versions select a document contract; they do not replace protocol, provider, or
runtime versions carried by the payload.

## Frozen v1 Roots

The following files and IDs remain byte-for-byte immutable:

| Surface | Frozen ID | SHA-256 |
| --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json` | `5d3a88ed54d9acf83813713abec493ebb85e245cd6766de9fffa03351cdb62cf` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json` | `1abc0b228c72fc05f8ec6272d327d9c06ca3e3a7e37ea2487ccfeff60c86cdb6` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json` | `44171e85e1076231d9120f67abafcf521748ccbb8932a805df12c43823587fbd` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json` | `da2e2001a61c19d2726bc96ef05392e1acb8618c6bb6a3dfb233bcc0398e0822` |
| Capability v2 | `https://pheroos.dev/schemas/capability-v2.schema.json` | `b613b848978c32339ec47487c4c45f99f67a81b85d8f98565bf41ed908df8eb4` |
| Protocol v2 | `https://pheroos.dev/schemas/protocol-v2.schema.json` | `8f4aeb48d99827b381cb3138c9651d88eb0a2f0ce1c0de4aac8f1aaf5eebe877` |
| Scoped Trace event v1 | `https://pheroos.dev/schemas/scoped-trace-event-v1.schema.json` | `b05925809d83645734d205e814f2ced0ff8afe242a8526b2ed3aadb93dfccd01` |

The CLI aliases `capability`, `protocol`, `driver`, and `kernel` remain pinned
to these documents. They never silently move to v2.

## Active v2 Documents

| Surface | Versioned ID | Version selection |
| --- | --- | --- |
| Capability | `capability-v2.schema.json` | API/CLI selector `pheroos-capability-schema-v2` |
| Protocol | `protocol-v2.schema.json` | API/CLI selector `pheroos-protocol-schema-v2` |
| Driver | `driver-v2.schema.json` | required `descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `kernel-v2.schema.json` | required `plan_version=pheroos-kernel-plan-v2` |

Capability and Protocol keep `protocol_version=pheroos.protocol.v1`. Their v2
identifier describes the stricter schema document, not a new protocol meaning.
`DriverDescriptor.version` remains the external provider version and is never
used as the descriptor ABI discriminator.

## Scoped Authority vNext Documents

Scoped authority uses a distinct semantic version axis. The following files,
selectors, strict readers, Catalog entries, and CLI surfaces are shipped as
Draft contracts:

| Surface | File / `$id` | Selector |
| --- | --- | --- |
| Capability for `pheroos.protocol.v2` | `capability-v3.schema.json` / `https://pheroos.dev/schemas/capability-v3.schema.json` | `pheroos-capability-schema-v3` |
| Protocol for `pheroos.protocol.v2` | `protocol-v3.schema.json` / `https://pheroos.dev/schemas/protocol-v3.schema.json` | `pheroos-protocol-schema-v3` |
| Scoped authority wire | `authority-v2.schema.json` / `https://pheroos.dev/schemas/authority-v2.schema.json` | `pheroos-authority-schema-v2` |
| Scoped authority TCK | `scoped-authority-tck-v2.schema.json` / `https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json` | `pheroos-scoped-authority-tck-v2` |

Schema-document v3 is used because Capability/Protocol v2 documents are already
frozen contracts for `pheroos.protocol.v1`. Capability/Protocol v3 now perform
exact dispatch for the local scoped-authority v2 profile; selection is explicit
and never inferred from document shape. The Authority v2 schema is a closed
union over the portable StateStore, Authority Session, and Baseline Output v2
records. Reading such a record does not make it current or authoritative:
StateStore inclusion, currentness, session authority, and the applicable
Governance operation remain separate checks.

The scoped-authority TCK schema is an expected-free artifact/report vocabulary
over the exact StateStore, Authority Session, and Baseline Output matrices. It
does not silently activate the still-reserved authenticated issuer verifier or
an external aggregate profile, and it does not perform formal Stable promotion.
See the
[authority v2 decision](../protocol/authority-v2-decision.md).

## Static Artifact Catalog

`pheroos.conformance.schema_catalog` is the sole static registry for all 21
checked JSON Schema artifacts and 25 CLI names. Each entry records its path,
`$id`, schema version, owning factory, typed reader, semantic validator (or an
explicit not-applicable reason), wire validator, frozen root, CLI aliases,
package-data decision, profiles, and TCKs. Core packages retain their schema
factories and validators and never import the Conformance catalog.

The Catalog also fixes validation-layer ownership:

- the strict JSON loader rejects duplicate keys, byte-order marks, and
  non-finite JSON tokens;
- structural Schema checks object shape and primitive constraints;
- typed readers enforce exact discriminators and construct canonical records;
- semantic validators enforce cross-field protocol invariants;
- Conformance proves behavior across implementations.

JSON Schema is not claimed to detect duplicate object keys. The strict loader
owns that invariant explicitly.

## Reader Selection

Legacy documents have no embedded discriminator and therefore require an
explicit v1 reader. Authoritative readers never infer a version from shape.

```python
from pheroos.protocol import CAPABILITY_SCHEMA_V2, read_capability_manifest
from pheroos.drivers import driver_descriptor_from_dict
from pheroos.kernel import os_plan_from_dict

manifest = read_capability_manifest(
    capability_payload,
    schema_version=CAPABILITY_SCHEMA_V2,
)
driver_document = driver_descriptor_from_dict(driver_payload)
plan_document = os_plan_from_dict(plan_payload)
```

Missing, unknown, or cross-surface Driver/Kernel discriminators raise a typed
version error with `code` and `path`. Protocol schema selectors reject missing
or unknown versions and still enforce the supported payload
`protocol_version` before returning authority-bearing typed objects.

## Explicit v1 Upgrade

Driver v1 permits values that v2 intentionally rejects. Use
`upgrade_driver_descriptor_v1`; it either returns a complete v2 document or
fails with `driver_descriptor_v1_not_migratable`. It never removes duplicate
capabilities or permissions and never drops empty declarations silently.

Kernel v1 does not contain run scope, readiness snapshots, probe snapshots, or
driver capability/version bindings. `os_plan_v1_from_dict` therefore returns a
non-authoritative `LegacyOSPlan`, not an `OSPlan`. `upgrade_os_plan_v1` requires
the caller to provide:

- canonical `run_id` and matching `scope_ref`;
- connection-readiness snapshots;
- driver-probe snapshots;
- explicit capabilities and provider version for every exposed driver.

Missing or contradictory facts reject migration. A legacy plan is never
materialized or authorized by inventing defaults.

## CLI

Use explicit versioned surfaces for new integrations:

```bash
pheroos schema export capability-v2
pheroos schema export protocol-v2
pheroos schema export driver-v2
pheroos schema export kernel-v2
pheroos schema export capability-v3
pheroos schema export protocol-v3
pheroos schema export authority-v2
pheroos schema export scoped-authority-tck-v2

pheroos wire validate driver-v2 descriptor.json
pheroos wire validate kernel-v2 plan.json
```

`pheroos schema list` is derived from the Catalog and reports the canonical
surface, checked path, ID, schema-document version, lifecycle state, frozen or
writeable state, package-data decision, and canonical SHA-256. `show` and
`export` emit the exact checked bytes, including legacy property ordering.
Explicit `*-v1` surfaces and the old aliases remain available for compatibility
inspection.

`pheroos version` provides machine-readable version discovery through
`capability_schema_versions`, `protocol_schema_versions`,
`driver_descriptor_version`, and `kernel_plan_version`. Integrations should use
these fields instead of inferring compatibility from package versions.

## Drift Gate

Run the single generator check before merging or releasing:

```bash
python scripts/generate_schema_artifacts.py --check
```

`--check` rejects missing or orphan artifacts, duplicate paths/IDs/aliases,
factory-byte drift, invalid Catalog metadata, and frozen-root drift. `--write`
regenerates only entries marked writeable and refuses to run when any frozen or
structural Catalog problem exists. A second `--write` is byte-identical. The
CLI remains the supported distribution export surface for entries whose
Catalog metadata says package data is not required.
