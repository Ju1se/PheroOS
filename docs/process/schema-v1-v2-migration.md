# Schema Document v1/v2 Migration

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

pheroos wire validate driver-v2 descriptor.json
pheroos wire validate kernel-v2 plan.json
```

`pheroos schema list` reports the ID, schema-document version, lifecycle status,
and canonical SHA-256 for every surface. Explicit `*-v1` surfaces and the old
aliases remain available for compatibility inspection.

`pheroos version` provides machine-readable version discovery through
`capability_schema_versions`, `protocol_schema_versions`,
`driver_descriptor_version`, and `kernel_plan_version`. Integrations should use
these fields instead of inferring compatibility from package versions.

## Drift Gate

Run the single generator check before merging or releasing:

```bash
python scripts/generate_schema_artifacts.py --check
```

`--write` regenerates only v2 artifacts. It never rewrites frozen v1 files.
Changing a frozen generator or artifact fails the check against the recorded
root.
