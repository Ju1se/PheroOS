"""Provider-free restart journey for the public durable Risk v2 ABI."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import cast

from pheroos.conformance import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    VerifiedRiskSourceV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
)
from pheroos.protocol import (
    COMMIT_INTEGRITY_PROFILE_VERSION,
    PROTOCOL_SCHEMA_V3,
    ScopedProtocolManifestV2,
    read_protocol_manifest,
)


RESULT_SCHEMA = "pheroos-risk-v2-example-result-v1"
REFERENCE_STORE = "reference-conformance-adapter:test-only"
RUN_REF = "run:risk-v2-example"
SCOPE_REF = "scope:risk-v2-example"
TARGET_REF = "decision:risk-v2"
ISSUER_REF = "issuer:risk-v2-example"
FIRST_EPOCH = 7
NEXT_EPOCH = FIRST_EPOCH + 130


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        Path(__file__).with_name("manifest.json").read_text(encoding="utf-8")
    )
    manifest = read_protocol_manifest(payload, schema_version=PROTOCOL_SCHEMA_V3)
    _require(
        type(manifest) is ScopedProtocolManifestV2,
        "protocol-v3 did not produce the exact scoped manifest type",
    )
    return cast(ScopedProtocolManifestV2, manifest)


def _grant(domain_root: str) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain_root,
        scope_ref=SCOPE_REF,
        issuer_ref=ISSUER_REF,
        grant_ref="grant:risk-v2-example",
        grant_binding_ref=_root("risk-v2-example-grant-binding"),
        operations=(GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,),
        target_refs=(TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=1_000,
        revocation_generation=0,
    )


def _prepare(
    *,
    manifest: ScopedProtocolManifestV2,
    domain_root: str,
    epoch: int,
    current_step: int,
    advance_ref: str,
    parent_snapshot: RiskStateSnapshotV2 | None = None,
) -> tuple[RiskStateAdvanceRequestV2, VerifiedRiskSourceV2]:
    return prepare_risk_state_advance_v2(
        domain_root=domain_root,
        scope_ref=SCOPE_REF,
        manifest=manifest,
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=epoch,
        advance_ref=advance_ref,
        current_step=current_step,
        assessment_ref=f"assessment:{advance_ref}",
        risk_band=RiskBand.LOW,
        risk_input_roots=(_root(f"risk-input:{advance_ref}"),),
        rationale_codes=("provider_free_declared_assessment",),
        assessment_method="declared-risk-example-v1",
        issuer_ref=ISSUER_REF,
        issued_at_step=current_step,
        expires_at_step=100,
        provenance_ref=f"urn:pheroos:example:risk:{advance_ref}",
        source_trace_roots=(_root(f"source-trace:{advance_ref}"),),
        parent_snapshot=parent_snapshot,
    )


def main() -> None:
    manifest = _manifest()
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    domain = adapter.create_domain_v2(SCOPE_REF)
    _require(
        domain.profile == manifest.authority_policy.profile,
        "manifest authority selector does not match the reference domain",
    )
    store = adapter.create_store_v2((domain,))
    grant = _grant(domain.domain_root)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:risk-v2-example:grant-activation",
        1,
    )
    _require(
        activated.disposition is GovernanceCommitDispositionV2.COMMITTED,
        "Risk v2 example grant activation failed",
    )
    first_capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        FIRST_EPOCH,
    )
    first_request, first_source = _prepare(
        manifest=manifest,
        domain_root=domain.domain_root,
        epoch=FIRST_EPOCH,
        current_step=2,
        advance_ref="advance:risk-v2-example:first",
    )
    first_session = open_risk_authority_session_v2(
        first_capability,
        first_request,
    )
    first_attempt = advance_risk_state_v2(
        first_request,
        source=first_source,
        authority_session=first_session,
    )
    _require(
        first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and first_attempt.committed_transition is not None,
        "first Risk v2 transition did not commit",
    )
    first_transition = first_attempt.committed_transition
    if first_transition is None:
        raise RuntimeError("first Risk v2 transition is unavailable")
    portable_text = first_request.canonical_bytes().decode("utf-8")

    restarted = adapter.restart_store_v2(store)
    _require(restarted is not store, "restart did not create a fresh reader")
    restored_parent = rehydrate_risk_state_v2(
        json.loads(portable_text),
        domain=domain,
        state_reader=restarted,
    )
    _require(
        risk_state_is_current_v2(restored_parent),
        "restored Risk v2 parent is not current",
    )
    parent_snapshot = require_current_risk_state_v2(restored_parent)
    next_capability = bind_governance_issuer_capability_v2(
        restarted,
        domain,
        grant,
        RUN_REF,
        NEXT_EPOCH,
    )
    next_request, next_source = _prepare(
        manifest=manifest,
        domain_root=domain.domain_root,
        epoch=NEXT_EPOCH,
        current_step=3,
        advance_ref="advance:risk-v2-example:epoch-137",
        parent_snapshot=parent_snapshot,
    )
    next_session = open_risk_authority_session_v2(next_capability, next_request)
    next_attempt = advance_risk_state_v2(
        next_request,
        source=next_source,
        authority_session=next_session,
    )
    _require(
        next_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and next_attempt.committed_transition is not None,
        "second Risk v2 transition did not commit",
    )
    next_transition = next_attempt.committed_transition
    if next_transition is None:
        raise RuntimeError("second Risk v2 transition is unavailable")
    current = rehydrate_risk_state_v2(
        next_request.to_dict(),
        domain=domain,
        state_reader=restarted,
    )
    _require(
        first_request.stream_ref == next_request.stream_ref
        and not risk_state_is_current_v2(restored_parent)
        and risk_state_is_current_v2(current)
        and current.position is GovernanceCommitPositionV2.CURRENT,
        "Risk v2 fixed-lineage currentness failed",
    )

    payload = {
        "schema": RESULT_SCHEMA,
        "manifest": {
            "schema_version": PROTOCOL_SCHEMA_V3,
            "protocol_id": manifest.id,
            "protocol_version": manifest.protocol_version,
            "manifest_root": manifest.manifest_root,
        },
        "reference_store": {
            "implementation": REFERENCE_STORE,
            "restart_between_epochs": True,
            "fresh_reader_identity": True,
            "production_persistence": False,
        },
        "grant": {
            "operation": GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
            "issuer_ref": grant.issuer_ref,
            "expires_at_epoch": grant.expires_at_epoch,
        },
        "portable": {
            "request_root": first_request.request_root,
            "canonical_bytes_sha256": _root(portable_text),
            "verified_source_serialized": False,
            "rehydrated_by_fresh_reader": True,
        },
        "lineage": {
            "stream_ref": next_request.stream_ref,
            "same_stream_across_epoch_jump": True,
            "first_epoch": first_request.epoch,
            "next_epoch": next_request.epoch,
            "next_parent_epoch": next_request.snapshot.parent_epoch,
            "revisions": [
                first_request.snapshot.revision,
                next_request.snapshot.revision,
            ],
            "window_reset_required": next_request.snapshot.assessment.window_reset_required,
            "positions": [restored_parent.position.value, current.position.value],
        },
        "trace_events": [
            [event.event_type for event in first_transition.batch.trace_batch.events],
            [event.event_type for event in next_transition.batch.trace_batch.events],
        ],
        "receipts": [
            first_transition.receipt.receipt_root,
            next_transition.receipt.receipt_root,
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
