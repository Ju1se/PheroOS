# Runtime Compatibility Manifest v1

Status: **Draft / provisional**. The Python names, component identifiers, and
profile identifiers in this document are not Stable, are not approved release
names, and carry no GA compatibility promise.

`RuntimeCompatibilityManifestV1` is the small, provider-neutral declaration an
external runtime uses to determine whether its protocol-core components can be
composed exactly. The checked artifact is
`pheroos/conformance/abi/runtime-compatibility-v1.json`.

The manifest proves only version composition. It does not prove that an
implementation passed a TCK, that a provider works, that a database is durable,
that a runtime is production-ready, or that an action has Governance authority.

## Closed document

The exact top-level fields are:

- `manifest_version`
- `manifest_root`
- `required_profile`
- `optional_profiles`
- `optional_capabilities`

The required profile and every optional profile contain `profile_id`,
`profile_version`, and sorted `requirements`. A standalone optional capability
contains `capability_id` and sorted `requirements`. Each requirement contains
only `component_id` and `version_id`.

Unknown fields, unsupported document versions, duplicate JSON keys, non-finite
numbers, non-NFC text, NUL, duplicate identities, nondeterministic list order,
invalid roots, noncanonical JSON bytes, and documents over 65,536 bytes fail
closed. Canonical JSON uses UTF-8, sorted object keys, no insignificant
whitespace, and no non-finite values.

`manifest_root` is SHA-256 over a domain-separated canonical projection that
omits `manifest_root`. `artifact_digest` hashes the complete canonical wire.
These values detect drift and bind reports to exact content. They are not a
signature, trust root, authority receipt, or release attestation.

## Required scoped-baseline journey

The provisional `pheroos-runtime-scoped-baseline-profile-v1` requirement is the
WP-06 baseline composition:

| Surface | Exact components |
| --- | --- |
| Protocol | Capability Schema v3, Protocol Schema v3, `pheroos.protocol.v2`, authority canonical v2, baseline output policy v2 |
| Kernel | RuntimeScope v1 and its schema, Kernel Plan v2 |
| Drivers | invocation request/result/reply/receipt v2, Invocation Store v2, checkpoint v2 |
| Governance | StateStore v2, baseline output request/result v2 |
| Trace | scoped event v1, scoped record/store/checkpoint v2 |
| Conformance | public Python ABI artifact format v1 **and exact checked artifact byte digest**, report v2, StateStore v2 TCK, baseline output v2 TCK, Driver Invocation Store v2 TCK, Scoped TraceStore v2 TCK |

The `pheroos-public-python-api-v1` entry identifies the checked inventory
format. A separate required component binds the exact checked inventory bytes
by SHA-256, so unchanged format version plus changed Python shape fails exact
compatibility. The runtime manifest root binds that digest into the composition;
the public API inventory and source conformance still prove the shape
independently. Neither the version string nor the digest alone is an
implementation compatibility report.

The package version such as `0.1.0` is deliberately absent. Package semver is
not ABI authority and the evaluator performs no semver range guessing.

## Optional profiles and capabilities

The checked artifact advertises only active profiles that already have
registered Conformance checks:

- core v1
- swarm v1
- hybrid-swarm v1
- commit-integrity v1
- hybrid-commit v1
- certified-commit v1
- distributed-commit v1

They are availability declarations. They become requirements only when a
consumer places the profile ID in `required_optional_profiles`. A baseline
claim therefore never has to add Hybrid, Optimal Commit, certified, or
distributed behavior.

WP-05 v2 owners with standalone TCKs are listed separately under
`optional_capabilities`: authority session, Hybrid replay, commit replay, risk,
support, commit gate, commit evidence, commit decision, commit certificate,
distributed commit, and commit finality. They do not masquerade as
manifest-selected profiles. A consumer selects them explicitly through
`required_optional_capabilities`.

The required scoped-baseline composition includes the exact Runtime Integration
transcript TCK version.  Advertising that version is only an availability
claim: compatibility evaluation does not prove that a runtime passed the TCK,
and a verifier must still inspect the independently produced TCK report.
Reserved verifier/scoped-authority profiles and future Stable/GA profiles are
not declared before their own activation gates pass.

## Exact evaluation

An external runtime submits a canonical `RuntimeCompatibilityClaimV1` with:

- its exact component/version pairs;
- an explicit critical flag on extra components;
- any optional profile IDs it requires;
- any standalone optional capability IDs it requires.

`evaluate_runtime_compatibility_v1` returns a typed
`RuntimeCompatibilityReportV1`:

| Condition | Result |
| --- | --- |
| required component missing | incompatible |
| selected optional component missing | incompatible |
| exact version mismatch | incompatible |
| unknown selected profile/capability | incompatible |
| unknown critical component | incompatible |
| extra noncritical component | compatible, reported as notice |
| unselected optional profile/capability | ignored |

There is no silent downgrade, nearest-version selection, semver coercion, or
fallback to a legacy ABI.

```python
from pheroos.conformance.runtime_compatibility import (
    build_runtime_compatibility_manifest_v1,
    create_runtime_compatibility_claim_v1,
    evaluate_runtime_compatibility_v1,
)

manifest = build_runtime_compatibility_manifest_v1()
versions = {
    item.component_id: item.version_id
    for item in manifest.required_profile.requirements
}
claim = create_runtime_compatibility_claim_v1(versions)
report = evaluate_runtime_compatibility_v1(manifest, claim)
assert report.ok
```

Passing this report means only that the declared version IDs match this
manifest. The runtime must separately execute every applicable TCK and retain
its versioned Conformance reports. Transport success, provider success, Trace
append, output delivery, and this compatibility report never create evidence,
commit, publication, execution, or finality authority.

## Artifact verification

The artifact is package data and can be loaded outside the source working
directory with `load_runtime_compatibility_manifest_v1()`. Verify generator
drift with:

```bash
python scripts/generate_runtime_compatibility_manifest.py --check
python -m pytest -q \
  tests/conformance/test_runtime_compatibility_manifest.py \
  tests/conformance/test_runtime_compatibility_independent.py
```

`--write` is a maintainer operation. A changed component set changes the root
and must be reviewed as an ABI-composition decision even when the v1 document
schema remains unchanged.
