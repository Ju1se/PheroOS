from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path

from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.baseline_output_v2 import (
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputTerminalStatusV2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
)
from pheroos.protocol import (
    CAPABILITY_SCHEMA_V3,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    read_capability_manifest,
)


RUN_REF = "run:scoped-output-example"
TARGET_REF = "decision:review"
ACTION_REF = "action:publish-review"
CANDIDATE_REF = "candidate:accept"
EXPECTED_BASELINE_EVENTS = (
    "baseline_manifest_activated",
    "baseline_evidence_qualified",
    "baseline_stop_resolved",
    "baseline_decision_evaluated",
    "baseline_action_permission_issued",
    "baseline_output_committed",
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_manifest() -> ScopedProtocolManifestV2:
    capability_path = Path(__file__).with_name("capability.json")
    payload = json.loads(capability_path.read_text(encoding="utf-8"))
    capability = read_capability_manifest(
        payload,
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    _require(
        type(capability) is ScopedCapabilityManifestV2,
        "capability-v3 did not produce the exact scoped capability type",
    )
    return capability.protocol


def _domain(manifest: ScopedProtocolManifestV2) -> AuthorityDomainV2:
    policy = manifest.authority_policy
    return AuthorityDomainV2(
        policy_version=policy.policy_version,
        profile=policy.profile,
        wire_version=policy.wire_version,
        canonical_version=policy.canonical_version,
        ledger_version=policy.ledger_version,
        state_store_version=policy.state_store_version,
        trace_batch_version=policy.trace_batch_version,
        read_set_version=policy.read_set_version,
        scope_ref="scope:scoped-output-example",
    )


def _grant(domain: AuthorityDomainV2) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:scoped-output-example",
        grant_ref="grant:scoped-output-example",
        grant_binding_ref=_root("scoped-output-example-grant-binding"),
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        ),
        target_refs=(TARGET_REF,),
        action_refs=(ACTION_REF,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )


def _commit_signal(
    store: InMemoryGovernanceStateStoreV2,
    capability: GovernanceIssuerCapabilityV2,
    domain: AuthorityDomainV2,
    *,
    label: str,
    source_ref: str,
) -> dict[str, str]:
    signal_ref = f"signal:{label}"
    evidence_root = _root(f"evidence:{label}")
    provenance_ref = _root(f"provenance:{label}")
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref=CANDIDATE_REF,
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=source_ref,
    )
    request = GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=RUN_REF,
        request_ref=f"request:signal:{label}",
        transition_id=f"transition:signal:{label}",
        signal_ref=signal_ref,
        target_ref=TARGET_REF,
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=2,
    )
    session = open_governance_authority_session_v2(capability, request)
    attempt = commit_verified_signal_v2(request, authority_session=session)
    _require(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.position_observation is not None
        and attempt.position_observation.position is GovernanceCommitPositionV2.CURRENT,
        f"verified signal {label} did not commit currently",
    )
    durable = store.load_state_v2(domain.scope_ref, request.stream_ref)
    _require(
        durable.get("status") == "verified"
        and durable.get("signal_root") == signal_root
        and durable.get("evidence_root") == evidence_root,
        f"verified signal {label} durable state is invalid",
    )
    return {
        "candidate_ref": CANDIDATE_REF,
        "evidence_root": evidence_root,
        "provenance_ref": provenance_ref,
        "signal_ref": signal_ref,
        "signal_root": signal_root,
        "signal_transition_id": request.transition_id,
        "source_ref": source_ref,
    }


def _output_request(
    domain: AuthorityDomainV2,
    manifest: ScopedProtocolManifestV2,
    proposals: tuple[Mapping[str, str], ...],
) -> BaselineOutputRequestV2:
    ordered = tuple(
        sorted(
            proposals,
            key=lambda item: (
                item["source_ref"].encode("utf-8"),
                item["signal_ref"].encode("utf-8"),
            ),
        )
    )
    return BaselineOutputRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:scoped-output",
        output_transition_id="transition:scoped-output",
        manifest=manifest,
        target_ref=TARGET_REF,
        action_ref=ACTION_REF,
        proposed_candidate_ref=None,
        verified_signals=ordered,
        stop_resolutions=(
            {
                "action_ref": ACTION_REF,
                "blocked": False,
                "provenance_ref": _root("scoped-output-stop-resolution"),
                "reason_ref": "reason:all-actions-clear",
            },
        ),
        output_payload={
            "candidate_ref": CANDIDATE_REF,
            "message": "deterministic provider-free output",
        },
        observed_epoch=2,
    )


def _stage_identities(
    request: BaselineOutputRequestV2,
) -> tuple[tuple[str, str, str], ...]:
    return (
        (
            "manifest",
            request.manifest_stream_ref,
            request.stage_transition_id("manifest"),
        ),
        (
            "evidence",
            request.evidence_stream_ref,
            request.stage_transition_id("evidence"),
        ),
        ("stop", request.stop_stream_ref, request.stage_transition_id("stop")),
        (
            "decision",
            request.decision_stream_ref,
            request.stage_transition_id("decision"),
        ),
        ("permission", request.permission_stream_ref, request.permission_transition_id),
        ("output", request.output_stream_ref, request.output_transition_id),
    )


def _durable_summary(
    store: InMemoryGovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    grant: GovernanceIssuerGrantV2,
) -> dict[str, object]:
    trace_events: list[str] = []
    positions: dict[str, str] = {}
    state_schemas: dict[str, str] = {}
    output_read_set: list[str] = []
    for role, stream_ref, transition_id in _stage_identities(request):
        view = store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            transition_id,
        )
        _require(
            view.disposition is GovernanceCommitDispositionV2.COMMITTED
            and view.position_observation is not None
            and view.position_observation.position is GovernanceCommitPositionV2.CURRENT
            and view.committed_transition is not None,
            f"{role} durable commit is not current",
        )
        assert view.position_observation is not None
        assert view.committed_transition is not None
        event = view.committed_transition.batch.trace_batch.events[0]
        event.validate()
        trace_events.append(event.event_type)
        positions[role] = view.position_observation.position.value
        state = store.load_state_v2(request.scope_ref, stream_ref)
        state_schemas[role] = str(state["schema"])
        if role == "output":
            output_read_set = [
                item.stream_ref
                for item in view.committed_transition.batch.read_set.entries
            ]

    expected_read_set = sorted(
        {
            request.output_stream_ref,
            request.manifest_stream_ref,
            request.evidence_stream_ref,
            request.stop_stream_ref,
            request.decision_stream_ref,
            request.permission_stream_ref,
            governance_issuer_grant_stream_ref_v2(
                request.scope_ref,
                grant.grant_ref,
            ),
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        key=lambda item: item.encode("utf-8"),
    )
    _require(
        tuple(trace_events) == EXPECTED_BASELINE_EVENTS, "trace path is incomplete"
    )
    _require(output_read_set == expected_read_set, "output read-set is incomplete")
    return {
        "positions": positions,
        "state_schemas": state_schemas,
        "trace_events": trace_events,
        "output_read_set": output_read_set,
    }


def run() -> dict[str, object]:
    manifest = _load_manifest()
    domain = _domain(manifest)
    store = InMemoryGovernanceStateStoreV2((domain,))
    grant = _grant(domain)
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant:activate",
        1,
    )
    _require(
        activation.disposition is GovernanceCommitDispositionV2.COMMITTED,
        "issuer grant activation failed",
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        2,
    )
    proposals = (
        _commit_signal(
            store,
            capability,
            domain,
            label="alpha",
            source_ref="source:alpha",
        ),
        _commit_signal(
            store,
            capability,
            domain,
            label="beta",
            source_ref="source:beta",
        ),
    )
    request = _output_request(domain, manifest, proposals)

    permission_session = open_baseline_output_authority_session_v2(
        capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    permission_attempt = issue_action_permission_v2(
        request,
        authority_session=permission_session,
    )
    _require(
        permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and permission_attempt.position_observation is not None
        and permission_attempt.position_observation.position
        is GovernanceCommitPositionV2.CURRENT,
        "computed permission did not commit currently",
    )
    permission_state = store.load_state_v2(
        request.scope_ref,
        request.permission_stream_ref,
    )
    permission = ActionPermissionV2.from_dict(permission_state["permission"])
    _require(
        permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
        and permission.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
        and permission.candidate_ref == CANDIDATE_REF,
        "Governance did not compute the expected permission",
    )

    output_session = open_baseline_output_authority_session_v2(
        capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    result = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    _require(
        result.disposition is GovernanceCommitDispositionV2.COMMITTED
        and result.position is GovernanceCommitPositionV2.CURRENT
        and result.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.DELIVERABLE
        and result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
        and result.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
        and result.candidate_ref == CANDIDATE_REF
        and result.authorization == permission,
        "aggregate output did not commit with current authorization",
    )

    return {
        "schema": "pheroos-scoped-output-example-result-v1",
        "capability": {
            "schema_version": CAPABILITY_SCHEMA_V3,
            "protocol_id": manifest.id,
            "protocol_version": manifest.protocol_version,
            "manifest_root": manifest.manifest_root,
        },
        "grant": {
            "operations": [item.value for item in grant.operations],
            "grant_root": grant.grant_root,
        },
        "signals": [dict(item) for item in proposals],
        "permission": {
            "commit_disposition": permission_attempt.disposition.value,
            "position": permission_attempt.position_observation.position.value,
            "disposition": permission.disposition.value,
            "terminal_status": permission.terminal_status.value,
            "candidate_ref": permission.candidate_ref,
            "permission_root": permission.permission_root,
        },
        "output": {
            "commit_disposition": result.disposition.value,
            "position": result.position.value if result.position is not None else None,
            "delivery_disposition": result.delivery_disposition.value,
            "action_disposition": result.action_disposition.value,
            "terminal_status": (
                result.terminal_status.value
                if result.terminal_status is not None
                else None
            ),
            "candidate_ref": result.candidate_ref,
            "result_root": result.result_root,
        },
        "durable": _durable_summary(store, request, grant),
    }


def main() -> None:
    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
