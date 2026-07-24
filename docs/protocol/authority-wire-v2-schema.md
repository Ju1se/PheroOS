# Authority Wire v2 Schema (Draft)

`schemas/authority-v2.schema.json` is the additive Draft schema document for
portable scoped-authority v2 records. Its exact identifiers are:

- selector: `pheroos-authority-schema-v2`
- `$id`: `https://pheroos.dev/schemas/authority-v2.schema.json`

The document is a closed, discriminator-backed union over the current public
portable records from Governance StateStore v2, Authority Session v2, and
Baseline Output v2. It covers 21 top-level record shapes. Every branch requires
its exact `schema` value, all declared fields, and no unknown fields. Nested
StateStore records are closed through local `$defs`; the Protocol v3 manifest
and canonical Trace event remain references to their existing schema owners so
this document does not create a second contract owner.

The direct Draft API is `pheroos.governance.authority_schema_v2`:

```python
from pheroos.governance.authority_schema_v2 import (
    AUTHORITY_SCHEMA_V2,
    authority_schema_v2,
    loads_authority_wire_record_v2,
    read_authority_wire_record_v2,
)
```

`read_authority_wire_record_v2` performs exact discriminator dispatch into the
already implemented canonical record readers. `loads_authority_wire_record_v2`
adds strict UTF-8 JSON handling: duplicate object keys, BOMs, non-finite
numbers, malformed bytes, unknown discriminators, bool-as-int substitutions,
unknown fields, bad roots, and semantic/root mismatches fail closed with
`AuthorityWireValidationErrorV2`.

JSON Schema is the structural interchange contract. The strict loader owns
properties JSON Schema cannot observe, such as duplicate keys. Canonical record
readers own semantic bindings, ordering, exact Python integer identity, and
content-root recomputation. The `x-pheroos-exact-integer` annotation records
that boundary for schema tooling.

A valid portable record is data, not authority. Possession or successful schema
validation does not authorize commit, publication, execution, or replay
currentness. Those decisions still require the applicable Governance operation
and current StateStore evidence.

This surface is Draft. It is not a Stable promotion and it does not modify any
legacy schema artifact or ID.
