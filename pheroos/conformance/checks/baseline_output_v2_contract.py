"""Active provider-free Conformance matrix for Baseline Output v2.

The matrix is deliberately a composition test, not a second output evaluator.
It drives the public Protocol v3 reader and public Governance operations, then
checks independently declared expectations against durable StateStore records,
read-sets, inclusion positions, and Trace events.  The same matrix therefore
applies unchanged to the reference and independent StateStore v2 adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    governance_issuer_grant_stream_ref_v2,
    governance_verified_signal_stream_ref_v2,
    open_governance_authority_session_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.baseline_output_v2 import (
    BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
    BASELINE_DECISION_STATE_SCHEMA_V2,
    BASELINE_EVIDENCE_STATE_SCHEMA_V2,
    BASELINE_MANIFEST_STATE_SCHEMA_V2,
    BASELINE_OUTPUT_STATE_SCHEMA_V2,
    BASELINE_STOP_STATE_SCHEMA_V2,
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
from pheroos.protocol import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    CAPABILITY_SCHEMA_V2,
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_VERSION_V2,
    ProtocolSchemaVersionError,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    read_capability_manifest,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.trace import TraceEvent


GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2 = (
    "pheroos-baseline-output-conformance-v2"
)

_CHECK_NAME = "baseline_output_v2_contract"
_RUN_REF = "run:baseline-output-v2"
_TARGET_REF = "target:answer"
_ACTION_REF = "action:publish"
_CANDIDATE_REF = "candidate:accept"
_FALLBACK_REF = "candidate:safe-fallback"
_REQUIRED_BASELINE_EVENTS = frozenset(
    {
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    }
)
_PERMISSION_OPERATIONS = (
    GovernanceIssuerOperationV2.VERIFY_SIGNAL,
    GovernanceIssuerOperationV2.EVALUATE_QUORUM,
    GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
    GovernanceIssuerOperationV2.RESOLVE_STOP,
    GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
)


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    permission_grant: GovernanceIssuerGrantV2
    output_grant: GovernanceIssuerGrantV2
    permission_capability: GovernanceIssuerCapabilityV2
    output_capability: GovernanceIssuerCapabilityV2
    manifest: ScopedProtocolManifestV2


def run_governance_baseline_output_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Execute every active local Baseline Output v2 check without skips."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        implementation_id = adapter.implementation_id
        store_conformance_version = adapter.conformance_version
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )
    if (
        type(implementation_id) is not str
        or not implementation_id
        or implementation_id != implementation_id.strip()
    ):
        return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    if store_conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
        return CheckResult(_CHECK_NAME, False, "adapter_version")

    problems: list[str] = []
    try:
        _evaluate_protocol_v3_opt_in(problems)
        _evaluate_vertical_case(
            adapter,
            problems,
            label="quorum",
            decision_mode="quorum",
            threshold=2,
            signal_sources=("source:alpha", "source:beta"),
            blocked=False,
            expected_status=BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            expected_candidate=_CANDIDATE_REF,
            expected_authorized=True,
            require_permission_separation=True,
        )
        _evaluate_vertical_case(
            adapter,
            problems,
            label="direct",
            decision_mode="direct_governance",
            threshold=2,
            signal_sources=("source:direct",),
            blocked=False,
            expected_status=BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            expected_candidate=_CANDIDATE_REF,
            expected_authorized=True,
        )
        _evaluate_vertical_case(
            adapter,
            problems,
            label="direct-zero-evidence",
            decision_mode="direct_governance",
            threshold=2,
            signal_sources=(),
            blocked=False,
            expected_status=BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            expected_candidate=_CANDIDATE_REF,
            expected_authorized=False,
        )
        _evaluate_vertical_case(
            adapter,
            problems,
            label="fallback-zero-evidence",
            decision_mode="quorum",
            threshold=2,
            signal_sources=(),
            blocked=False,
            expected_status=BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
            expected_candidate=_FALLBACK_REF,
            expected_authorized=False,
        )
        _evaluate_vertical_case(
            adapter,
            problems,
            label="fallback",
            decision_mode="quorum",
            threshold=2,
            signal_sources=("source:fallback",),
            blocked=False,
            expected_status=BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
            expected_candidate=_FALLBACK_REF,
            expected_authorized=True,
        )
        _evaluate_vertical_case(
            adapter,
            problems,
            label="blocked",
            decision_mode="direct_governance",
            threshold=2,
            signal_sources=("source:blocked",),
            blocked=True,
            expected_status=BaselineOutputTerminalStatusV2.BLOCKED,
            expected_candidate=_FALLBACK_REF,
            expected_authorized=False,
        )
        _evaluate_signal_binding_substitutions(adapter, problems)
        _evaluate_required_permission_operations(adapter, problems)
        _evaluate_restart_retry_and_currentness(adapter, problems)
        _evaluate_permission_issuer_revocation(adapter, problems)
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _evaluate_protocol_v3_opt_in(problems: list[str]) -> None:
    payload = _capability_payload(decision_mode="quorum", threshold=2)
    selected = read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)
    if (
        type(selected) is not ScopedCapabilityManifestV2
        or type(selected.protocol) is not ScopedProtocolManifestV2
        or selected.protocol.protocol_version != PROTOCOL_VERSION_V2
        or selected.protocol.output_policy.policy_version
        != BASELINE_OUTPUT_POLICY_VERSION_V2
        or selected.protocol.authority_policy.profile
        != "pheroos-scoped-authority-local-v2"
        or selected.protocol.collective_decision_policy is not None
        or selected.protocol.collective_commit_policy is not None
        or not _REQUIRED_BASELINE_EVENTS.issubset(
            set(selected.protocol.trace_policy.required_events)
        )
    ):
        problems.append("protocol_v3_explicit_opt_in")
    try:
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V2)
    except ProtocolSchemaVersionError as exc:
        if exc.code != "capability_schema_document_invalid":
            problems.append("protocol_v3_cross_selector_diagnostic")
    else:
        problems.append("protocol_v3_shape_inference")


def _evaluate_vertical_case(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
    *,
    label: str,
    decision_mode: str,
    threshold: int,
    signal_sources: tuple[str, ...],
    blocked: bool,
    expected_status: BaselineOutputTerminalStatusV2,
    expected_candidate: str,
    expected_authorized: bool,
    require_permission_separation: bool = False,
) -> None:
    context = _context(adapter, label, decision_mode, threshold)
    proposals = tuple(
        _commit_verified_signal(context, label=f"{label}:{index}", source_ref=source)
        for index, source in enumerate(signal_sources)
    )
    request = _request(
        context,
        label=label,
        proposals=proposals,
        blocked=blocked,
    )

    if require_permission_separation:
        _assert_permission_is_required(context, request, problems)

    issue_session, permission_attempt = _issue_permission(context, request)
    if not _is_current_commit(permission_attempt):
        problems.append(f"{label}_permission_commit")
        return
    permission = _load_permission(context.store, request)
    expected_permission = (
        ActionPermissionDispositionV2.AUTHORIZED
        if expected_authorized
        else ActionPermissionDispositionV2.DENIED
    )
    if (
        permission.disposition is not expected_permission
        or permission.terminal_status is not expected_status
        or permission.candidate_ref != expected_candidate
        or permission.target_ref != _TARGET_REF
        or permission.action_ref != _ACTION_REF
        or permission.output_payload_root != request.output_payload_root
        or permission.manifest_root != context.manifest.manifest_root
        or permission.output_policy_root != context.manifest.output_policy.policy_root
        or permission.grant_root != context.permission_grant.grant_root
    ):
        problems.append(f"{label}_durable_permission")

    output_session, result = _commit_output(context, request)
    expected_action = (
        BaselineOutputActionDispositionV2.AUTHORIZED
        if expected_authorized
        else BaselineOutputActionDispositionV2.DENIED
    )
    authorization_matches = (
        result.authorization == permission
        if expected_authorized
        else result.authorization is None
    )
    if (
        type(result) is not BaselineOutputResultV2
        or result.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or result.position is not GovernanceCommitPositionV2.CURRENT
        or result.terminal_status is not expected_status
        or result.candidate_ref != expected_candidate
        or result.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or result.action_disposition is not expected_action
        or not authorization_matches
    ):
        problems.append(f"{label}_terminal_result")
        return

    _inspect_durable_artifacts(
        context,
        request,
        proposals,
        issue_session,
        output_session,
        permission_attempt,
        result,
        expected_status,
        expected_candidate,
        expected_authorized,
        problems,
        label,
    )
    retry_attempt = issue_action_permission_v2(
        request,
        authority_session=issue_session,
    )
    retry_result = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    if (
        not _same_commit(permission_attempt, retry_attempt)
        or not _same_commit(result.commit_attempt, retry_result.commit_attempt)
        or retry_result.result_root != result.result_root
        or retry_result.action_disposition is not expected_action
    ):
        problems.append(f"{label}_exact_retry")


def _assert_permission_is_required(
    context: _Context,
    request: BaselineOutputRequestV2,
    problems: list[str],
) -> None:
    _session, result = _commit_output(context, request)
    output_head = context.store.load_head_v2(
        request.scope_ref,
        request.output_stream_ref,
    )
    if (
        result.disposition is not GovernanceCommitDispositionV2.INVALID
        or result.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or result.authorization is not None
        or output_head.revision != 0
    ):
        problems.append("permission_session_separation")


def _inspect_durable_artifacts(
    context: _Context,
    request: BaselineOutputRequestV2,
    proposals: tuple[Mapping[str, str], ...],
    issue_session: GovernanceAuthoritySessionV2,
    output_session: GovernanceAuthoritySessionV2,
    permission_attempt: GovernanceCommitAttemptV2,
    result: BaselineOutputResultV2,
    expected_status: BaselineOutputTerminalStatusV2,
    expected_candidate: str,
    expected_authorized: bool,
    problems: list[str],
    label: str,
) -> None:
    states = _load_durable_states(context.store, request)
    _inspect_durable_state_links(
        context,
        request,
        proposals,
        result,
        expected_status,
        expected_candidate,
        expected_authorized,
        states,
        problems,
        label,
    )
    _inspect_stage_batches(
        context,
        request,
        proposals,
        issue_session,
        output_session,
        permission_attempt,
        result,
        problems,
        label,
    )


def _load_durable_states(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
) -> dict[str, Mapping[str, Any]]:
    return {
        "manifest": store.load_state_v2(request.scope_ref, request.manifest_stream_ref),
        "evidence": store.load_state_v2(request.scope_ref, request.evidence_stream_ref),
        "stop": store.load_state_v2(request.scope_ref, request.stop_stream_ref),
        "decision": store.load_state_v2(request.scope_ref, request.decision_stream_ref),
        "permission": store.load_state_v2(
            request.scope_ref, request.permission_stream_ref
        ),
        "output": store.load_state_v2(request.scope_ref, request.output_stream_ref),
    }


def _inspect_durable_state_links(
    context: _Context,
    request: BaselineOutputRequestV2,
    proposals: tuple[Mapping[str, str], ...],
    result: BaselineOutputResultV2,
    expected_status: BaselineOutputTerminalStatusV2,
    expected_candidate: str,
    expected_authorized: bool,
    states: Mapping[str, Mapping[str, Any]],
    problems: list[str],
    label: str,
) -> None:
    expected_schemas = {
        "manifest": BASELINE_MANIFEST_STATE_SCHEMA_V2,
        "evidence": BASELINE_EVIDENCE_STATE_SCHEMA_V2,
        "stop": BASELINE_STOP_STATE_SCHEMA_V2,
        "decision": BASELINE_DECISION_STATE_SCHEMA_V2,
        "permission": BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
        "output": BASELINE_OUTPUT_STATE_SCHEMA_V2,
    }
    if any(
        states[role].get("schema") != schema
        for role, schema in expected_schemas.items()
    ):
        problems.append(f"{label}_durable_state_schemas")

    manifest_state = states["manifest"]
    evidence_state = states["evidence"]
    stop_state = states["stop"]
    decision_state = states["decision"]
    permission_state = states["permission"]
    output_state = states["output"]
    permission = _load_permission(context.store, request)
    expected_action = "authorized" if expected_authorized else "denied"
    if (
        manifest_state.get("manifest") != context.manifest.to_dict()
        or manifest_state.get("manifest_root") != context.manifest.manifest_root
        or manifest_state.get("output_policy_root")
        != context.manifest.output_policy.policy_root
        or evidence_state.get("qualified_signal_count") != len(proposals)
        or decision_state.get("candidate_ref") != expected_candidate
        or decision_state.get("terminal_status") != expected_status.value
        or permission_state.get("permission_root") != permission.permission_root
        or output_state.get("permission_root") != permission.permission_root
        or output_state.get("candidate_ref") != expected_candidate
        or output_state.get("terminal_status") != expected_status.value
        or output_state.get("action_disposition") != expected_action
        or output_state.get("result_root") != result.result_root
        or output_state.get("output_payload_root") != request.output_payload_root
    ):
        problems.append(f"{label}_durable_authority_links")
    if not _durable_evidence_matches(
        evidence_state,
        proposals,
        scope_ref=request.scope_ref,
    ):
        problems.append(f"{label}_durable_verified_evidence")
    resolutions = stop_state.get("resolutions")
    if (
        not isinstance(resolutions, (list, tuple))
        or len(resolutions) != 1
        or not isinstance(resolutions[0], Mapping)
        or resolutions[0].get("action_ref") != _ACTION_REF
        or resolutions[0].get("blocked")
        != (expected_status is BaselineOutputTerminalStatusV2.BLOCKED)
    ):
        problems.append(f"{label}_durable_stop_closure")


def _inspect_stage_batches(
    context: _Context,
    request: BaselineOutputRequestV2,
    proposals: tuple[Mapping[str, str], ...],
    issue_session: GovernanceAuthoritySessionV2,
    output_session: GovernanceAuthoritySessionV2,
    permission_attempt: GovernanceCommitAttemptV2,
    result: BaselineOutputResultV2,
    problems: list[str],
    label: str,
) -> None:
    expected_stage_streams = _expected_stage_streams(context, request, proposals)
    roles = _stage_identities(request)
    expected_events = {
        "manifest": "baseline_manifest_activated",
        "evidence": "baseline_evidence_qualified",
        "stop": "baseline_stop_resolved",
        "decision": "baseline_decision_evaluated",
        "permission": "baseline_action_permission_issued",
        "output": "baseline_output_committed",
    }
    observed_events: set[str] = set()
    for role, (stream_ref, transition_id) in roles.items():
        view = context.store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            transition_id,
        )
        transition = view.committed_transition
        if (
            view.disposition is not GovernanceCommitDispositionV2.COMMITTED
            or view.position_observation is None
            or view.position_observation.position
            is not GovernanceCommitPositionV2.CURRENT
            or transition is None
        ):
            problems.append(f"{label}_{role}_current_inclusion")
            continue
        session = output_session if role == "output" else issue_session
        if not _batch_matches(
            transition.batch,
            expected_stage_streams[role],
            session,
            additional_grant_session=(issue_session if role == "output" else None),
        ):
            problems.append(f"{label}_{role}_read_set")
        event = _validated_single_event(
            transition.batch,
            problems,
            label=label,
            role=role,
        )
        if event is None:
            continue
        if not _event_links_match(
            event,
            context,
            request,
            expected_event=expected_events[role],
            output_operation=role == "output",
        ):
            problems.append(f"{label}_{role}_trace_lineage")
        observed_events.add(event.event_type)
    if observed_events != _REQUIRED_BASELINE_EVENTS:
        problems.append(f"{label}_complete_trace_path")

    permission_transition = permission_attempt.committed_transition
    output_transition = result.commit_attempt.committed_transition
    if (
        permission_transition is None
        or output_transition is None
        or output_transition.batch.trace_batch.events[0].lineage.get("read_set_root")
        != output_transition.batch.read_set.root()
    ):
        problems.append(f"{label}_terminal_read_set_trace_root")


def _expected_stage_streams(
    context: _Context,
    request: BaselineOutputRequestV2,
    proposals: tuple[Mapping[str, str], ...],
) -> dict[str, set[str]]:
    permission_grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref,
        context.permission_grant.grant_ref,
    )
    output_grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref,
        context.output_grant.grant_ref,
    )
    signal_streams = {
        governance_verified_signal_stream_ref_v2(
            request.scope_ref,
            proposal["signal_ref"],
            request.target_ref,
        )
        for proposal in proposals
    }
    return {
        "manifest": {
            request.manifest_stream_ref,
            permission_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        "evidence": {
            request.evidence_stream_ref,
            request.manifest_stream_ref,
            *signal_streams,
            permission_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        "stop": {
            request.stop_stream_ref,
            request.manifest_stream_ref,
            permission_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        "decision": {
            request.decision_stream_ref,
            request.manifest_stream_ref,
            request.evidence_stream_ref,
            request.stop_stream_ref,
            permission_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        "permission": {
            request.permission_stream_ref,
            request.manifest_stream_ref,
            request.evidence_stream_ref,
            request.stop_stream_ref,
            request.decision_stream_ref,
            permission_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
        "output": {
            request.output_stream_ref,
            request.manifest_stream_ref,
            request.evidence_stream_ref,
            request.stop_stream_ref,
            request.decision_stream_ref,
            request.permission_stream_ref,
            permission_grant_stream,
            output_grant_stream,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        },
    }


def _stage_identities(
    request: BaselineOutputRequestV2,
) -> dict[str, tuple[str, str]]:
    return {
        "manifest": (
            request.manifest_stream_ref,
            request.stage_transition_id("manifest"),
        ),
        "evidence": (
            request.evidence_stream_ref,
            request.stage_transition_id("evidence"),
        ),
        "stop": (request.stop_stream_ref, request.stage_transition_id("stop")),
        "decision": (
            request.decision_stream_ref,
            request.stage_transition_id("decision"),
        ),
        "permission": (
            request.permission_stream_ref,
            request.permission_transition_id,
        ),
        "output": (request.output_stream_ref, request.output_transition_id),
    }


def _validated_single_event(
    batch: GovernanceCommitBatchV2,
    problems: list[str],
    *,
    label: str,
    role: str,
) -> TraceEvent | None:
    events = batch.trace_batch.events
    if len(events) != 1 or type(events[0]) is not TraceEvent:
        problems.append(f"{label}_{role}_trace_batch")
        return None
    event = events[0]
    try:
        event.validate()
    except (TypeError, ValueError):
        problems.append(f"{label}_{role}_trace_validation")
        return None
    return event


def _event_links_match(
    event: TraceEvent,
    context: _Context,
    request: BaselineOutputRequestV2,
    *,
    expected_event: str,
    output_operation: bool,
) -> bool:
    expected_operation = (
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT.value
        if output_operation
        else GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION.value
    )
    expected_grant = (
        context.output_grant if output_operation else context.permission_grant
    )
    return bool(
        event.event_type == expected_event
        and event.lineage.get("request_root") == request.request_root
        and event.lineage.get("manifest_root") == context.manifest.manifest_root
        and event.lineage.get("output_policy_root")
        == context.manifest.output_policy.policy_root
        and event.lineage.get("grant_root") == expected_grant.grant_root
        and event.lineage.get("target_ref") == request.target_ref
        and event.lineage.get("action_ref") == request.action_ref
        and event.lineage.get("operation") == expected_operation
    )


def _durable_evidence_matches(
    evidence_state: Mapping[str, Any],
    proposals: tuple[Mapping[str, str], ...],
    *,
    scope_ref: str,
) -> bool:
    records = evidence_state.get("signals")
    if not isinstance(records, (list, tuple)) or len(records) != len(proposals):
        return False
    for expected, observed in zip(proposals, records, strict=True):
        if not isinstance(observed, Mapping):
            return False
        if any(observed.get(key) != value for key, value in expected.items()):
            return False
        receipt_root = observed.get("verified_signal_receipt_root")
        stream_ref = observed.get("verified_signal_stream_ref")
        if (
            type(receipt_root) is not str
            or not receipt_root.startswith("sha256:")
            or stream_ref
            != governance_verified_signal_stream_ref_v2(
                scope_ref,
                expected["signal_ref"],
                _TARGET_REF,
            )
        ):
            return False
    return True


def _batch_matches(
    batch: GovernanceCommitBatchV2,
    expected_streams: set[str],
    session: GovernanceAuthoritySessionV2,
    *,
    additional_grant_session: GovernanceAuthoritySessionV2 | None,
) -> bool:
    entries = batch.read_set.entries
    refs = tuple(item.stream_ref for item in entries)
    by_stream = {item.stream_ref: item for item in entries}
    grant_stream = governance_issuer_grant_stream_ref_v2(
        session.scope_ref,
        session.grant_ref,
    )
    grant = by_stream.get(grant_stream)
    lifecycle = by_stream.get(GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2)
    target = by_stream.get(batch.stream_ref)
    transition = batch.transition
    additional_grant_matches = _additional_grant_matches(
        by_stream,
        additional_grant_session,
    )
    return bool(
        set(refs) == expected_streams
        and refs == tuple(sorted(refs, key=lambda item: item.encode("utf-8")))
        and len(refs) == len(set(refs))
        and batch.read_set_root == batch.read_set.root()
        and transition is not None
        and transition.read_set_root == batch.read_set.root()
        and target is not None
        and target.expected_revision == transition.expected_revision
        and target.expected_root == transition.expected_root
        and grant is not None
        and grant.expected_revision == session.grant_expected_revision
        and grant.expected_root == session.grant_expected_root
        and lifecycle is not None
        and lifecycle.expected_revision == session.lifecycle_expected_revision
        and lifecycle.expected_root == session.lifecycle_expected_root
        and additional_grant_matches
    )


def _additional_grant_matches(
    by_stream: Mapping[str, Any],
    session: GovernanceAuthoritySessionV2 | None,
) -> bool:
    if session is None:
        return True
    stream_ref = governance_issuer_grant_stream_ref_v2(
        session.scope_ref,
        session.grant_ref,
    )
    entry = by_stream.get(stream_ref)
    return bool(
        entry is not None
        and entry.expected_revision == session.grant_expected_revision
        and entry.expected_root == session.grant_expected_root
    )


def _evaluate_signal_binding_substitutions(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    replacements: dict[str, str] = {
        "candidate_ref": _FALLBACK_REF,
        "source_ref": "source:substituted",
        "provenance_ref": _root("provenance:substituted"),
    }
    for field_name, replacement in replacements.items():
        context = _context(adapter, f"binding-{field_name}", "quorum", 1)
        original = _commit_verified_signal(
            context,
            label=f"binding:{field_name}",
            source_ref="source:original",
        )
        mutated = dict(original)
        mutated[field_name] = replacement
        mutated["signal_root"] = baseline_verified_signal_proposal_root_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            run_ref=_RUN_REF,
            target_ref=_TARGET_REF,
            candidate_ref=mutated["candidate_ref"],
            signal_ref=mutated["signal_ref"],
            evidence_root=mutated["evidence_root"],
            provenance_ref=mutated["provenance_ref"],
            source_ref=mutated["source_ref"],
        )
        request = _request(
            context,
            label=f"binding-{field_name}",
            proposals=(mutated,),
            blocked=False,
        )
        _session, attempt = _issue_permission(context, request)
        head = context.store.load_head_v2(
            request.scope_ref,
            request.permission_stream_ref,
        )
        if (
            attempt.disposition is not GovernanceCommitDispositionV2.INVALID
            or attempt.failure is None
            or attempt.failure.code
            is not AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
            or head.revision != 0
        ):
            problems.append(f"verified_signal_{field_name}_substitution")


def _evaluate_required_permission_operations(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    cases = (
        (
            "missing-qualify-evidence",
            "direct_governance",
            tuple(
                item
                for item in _PERMISSION_OPERATIONS
                if item is not GovernanceIssuerOperationV2.QUALIFY_EVIDENCE
            ),
        ),
        (
            "missing-resolve-stop",
            "direct_governance",
            tuple(
                item
                for item in _PERMISSION_OPERATIONS
                if item is not GovernanceIssuerOperationV2.RESOLVE_STOP
            ),
        ),
        (
            "missing-evaluate-quorum",
            "quorum",
            tuple(
                item
                for item in _PERMISSION_OPERATIONS
                if item is not GovernanceIssuerOperationV2.EVALUATE_QUORUM
            ),
        ),
    )
    for label, decision_mode, operations in cases:
        context = _context(
            adapter,
            label,
            decision_mode,
            1,
            permission_operations=operations,
        )
        proposal = _commit_verified_signal(
            context,
            label=label,
            source_ref=f"source:{label}",
        )
        request = _request(
            context,
            label=label,
            proposals=(proposal,),
            blocked=False,
        )
        _session, attempt = _issue_permission(context, request)
        baseline_heads = tuple(
            context.store.load_head_v2(request.scope_ref, stream_ref)
            for stream_ref in (
                request.manifest_stream_ref,
                request.evidence_stream_ref,
                request.stop_stream_ref,
                request.decision_stream_ref,
                request.permission_stream_ref,
            )
        )
        if (
            attempt.disposition is not GovernanceCommitDispositionV2.DENIED
            or attempt.failure is None
            or attempt.failure.code
            is not AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED
            or attempt.failure.path != "/operation"
            or any(head.revision != 0 for head in baseline_heads)
        ):
            problems.append(f"permission_operation_{label}")


def _evaluate_restart_retry_and_currentness(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = _context(adapter, "currentness", "direct_governance", 1)
    proposal = _commit_verified_signal(
        context,
        label="currentness",
        source_ref="source:currentness",
    )
    first = _request(
        context,
        label="currentness-first",
        proposals=(proposal,),
        blocked=False,
    )
    _issue_session, first_permission = _issue_permission(context, first)
    _output_session, first_result = _commit_output(context, first)
    if (
        not _is_current_commit(first_permission)
        or first_result.action_disposition
        is not BaselineOutputActionDispositionV2.AUTHORIZED
        or first_result.commit_attempt.committed_transition is None
    ):
        problems.append("currentness_initial_commit")
        return
    first_receipt = (
        first_result.commit_attempt.committed_transition.receipt.receipt_root
    )

    restarted = adapter.restart_store_v2(context.store)
    if not isinstance(restarted, GovernanceStateStoreV2):
        problems.append("currentness_restart_store")
        return
    restarted_permission_capability = bind_governance_issuer_capability_v2(
        restarted,
        context.domain,
        context.permission_grant,
        _RUN_REF,
        2,
    )
    restarted_output_capability = bind_governance_issuer_capability_v2(
        restarted,
        context.domain,
        context.output_grant,
        _RUN_REF,
        2,
    )
    restarted_context = _Context(
        context.domain,
        restarted,
        context.permission_grant,
        context.output_grant,
        restarted_permission_capability,
        restarted_output_capability,
        context.manifest,
    )
    recovered = recover_baseline_output_result_v2(
        first,
        state_reader=restarted,
    )
    if (
        recovered.position is not GovernanceCommitPositionV2.CURRENT
        or recovered.action_disposition
        is not BaselineOutputActionDispositionV2.AUTHORIZED
        or recovered.authorization is None
        or recovered.commit_attempt.committed_transition is None
        or recovered.commit_attempt.committed_transition.receipt.receipt_root
        != first_receipt
    ):
        problems.append("currentness_restart_recovery")
    _replay_session, replay = _commit_output(restarted_context, first)
    if (
        replay.commit_attempt.committed_transition is None
        or replay.commit_attempt.committed_transition.receipt.receipt_root
        != first_receipt
        or replay.position is not GovernanceCommitPositionV2.CURRENT
        or replay.action_disposition is not BaselineOutputActionDispositionV2.AUTHORIZED
    ):
        problems.append("currentness_restart_exact_retry")

    successor = _request(
        restarted_context,
        label="currentness-successor",
        proposals=(proposal,),
        blocked=False,
        payload="successor-output",
    )
    _successor_issue_session, successor_permission = _issue_permission(
        restarted_context,
        successor,
    )
    _successor_output_session, successor_result = _commit_output(
        restarted_context,
        successor,
    )
    if (
        not _is_current_commit(successor_permission)
        or successor_result.position is not GovernanceCommitPositionV2.CURRENT
        or successor_result.action_disposition
        is not BaselineOutputActionDispositionV2.AUTHORIZED
    ):
        problems.append("currentness_successor_commit")
        return

    _historical_session, historical = _commit_output(restarted_context, first)
    recovered_history = recover_baseline_output_result_v2(
        first,
        state_reader=restarted,
    )
    view = restarted.load_commit_view_v2(
        first.scope_ref,
        first.output_stream_ref,
        first.output_transition_id,
        expected_receipt_root=first_receipt,
    )
    if (
        historical.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or historical.position is not GovernanceCommitPositionV2.SUPERSEDED
        or historical.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or historical.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or historical.authorization is not None
        or recovered_history.position is not GovernanceCommitPositionV2.SUPERSEDED
        or recovered_history.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or recovered_history.action_disposition
        is not BaselineOutputActionDispositionV2.DENIED
        or recovered_history.authorization is not None
        or view.position_observation is None
        or view.position_observation.position
        is not GovernanceCommitPositionV2.SUPERSEDED
    ):
        problems.append("currentness_superseded_denial")


def _evaluate_permission_issuer_revocation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = _context(adapter, "issuer-revocation", "direct_governance", 1)
    proposal = _commit_verified_signal(
        context,
        label="issuer-revocation",
        source_ref="source:issuer-revocation",
    )
    request = _request(
        context,
        label="issuer-revocation",
        proposals=(proposal,),
        blocked=False,
    )
    _issue_session, permission_attempt = _issue_permission(context, request)
    _output_session, committed = _commit_output(context, request)
    transition = committed.commit_attempt.committed_transition
    if (
        not _is_current_commit(permission_attempt)
        or committed.action_disposition
        is not BaselineOutputActionDispositionV2.AUTHORIZED
        or transition is None
    ):
        problems.append("issuer_revocation_initial_commit")
        return
    receipt_root = transition.receipt.receipt_root

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.permission_grant.grant_ref,
        "transition:issuer-revocation:permission-grant",
        3,
    )
    permission_grant_head = context.store.load_head_v2(
        context.domain.scope_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref,
            context.permission_grant.grant_ref,
        ),
    )
    historical_output_grant_head = context.store.load_head_v2(
        context.domain.scope_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref,
            context.output_grant.grant_ref,
        ),
    )
    _historical_session, historical = _commit_output(context, request)
    historical_transition = historical.commit_attempt.committed_transition
    if (
        not _is_current_commit(revoked)
        or historical.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or historical.position is not GovernanceCommitPositionV2.CURRENT
        or historical.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or historical.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or historical.authorization is not None
        or historical_transition is None
        or historical_transition.receipt.receipt_root != receipt_root
        or permission_grant_head.revision != 2
        or historical_output_grant_head.revision != 1
    ):
        problems.append("issuer_revocation_historical_delivery")


def _context(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
    decision_mode: str,
    threshold: int,
    *,
    permission_operations: tuple[
        GovernanceIssuerOperationV2, ...
    ] = _PERMISSION_OPERATIONS,
) -> _Context:
    manifest = _read_manifest(decision_mode=decision_mode, threshold=threshold)
    domain = adapter.create_domain_v2(f"scope:baseline-output-v2:{label}")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("adapter returned a non-canonical authority domain")
    store = adapter.create_store_v2((domain,))
    if not isinstance(store, GovernanceStateStoreV2):
        raise TypeError("adapter returned a non-conforming StateStore v2")
    permission_grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:baseline-output-v2:permission",
        grant_ref="grant:baseline-output-v2:permission",
        grant_binding_ref=_root(f"grant-binding:{label}:permission"),
        operations=permission_operations,
        target_refs=(_TARGET_REF,),
        action_refs=(_ACTION_REF,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    output_grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:baseline-output-v2:output",
        grant_ref="grant:baseline-output-v2:output",
        grant_binding_ref=_root(f"grant-binding:{label}:output"),
        operations=(GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,),
        target_refs=(_TARGET_REF,),
        action_refs=(_ACTION_REF,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    permission_activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        permission_grant,
        f"transition:{label}:permission-grant-activate",
        1,
    )
    output_activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        output_grant,
        f"transition:{label}:output-grant-activate",
        1,
    )
    if not all(
        _is_current_commit(attempt)
        for attempt in (permission_activation, output_activation)
    ):
        raise ValueError("baseline Conformance grant activation failed")
    permission_capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        permission_grant,
        _RUN_REF,
        2,
    )
    output_capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        output_grant,
        _RUN_REF,
        2,
    )
    return _Context(
        domain,
        store,
        permission_grant,
        output_grant,
        permission_capability,
        output_capability,
        manifest,
    )


def _commit_verified_signal(
    context: _Context,
    *,
    label: str,
    source_ref: str,
) -> Mapping[str, str]:
    signal_ref = f"signal:{label}"
    transition_id = f"transition:{label}:signal"
    evidence_root = _root(f"evidence:{label}")
    provenance_ref = _root(f"provenance:{label}")
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=_RUN_REF,
        target_ref=_TARGET_REF,
        candidate_ref=_CANDIDATE_REF,
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=source_ref,
    )
    request = GovernanceVerifiedSignalRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=_RUN_REF,
        request_ref=f"request:{label}:signal",
        transition_id=transition_id,
        signal_ref=signal_ref,
        target_ref=_TARGET_REF,
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=2,
    )
    session = open_governance_authority_session_v2(
        context.permission_capability,
        request,
    )
    attempt = commit_verified_signal_v2(request, authority_session=session)
    if not _is_current_commit(attempt):
        raise ValueError("baseline Conformance verified signal commit failed")
    state = context.store.load_state_v2(request.scope_ref, request.stream_ref)
    if (
        state.get("status") != "verified"
        or state.get("signal_root") != signal_root
        or state.get("evidence_root") != evidence_root
    ):
        raise ValueError("baseline Conformance verified signal state is invalid")
    return {
        "candidate_ref": _CANDIDATE_REF,
        "evidence_root": evidence_root,
        "provenance_ref": provenance_ref,
        "signal_ref": signal_ref,
        "signal_root": signal_root,
        "signal_transition_id": transition_id,
        "source_ref": source_ref,
    }


def _request(
    context: _Context,
    *,
    label: str,
    proposals: tuple[Mapping[str, str], ...],
    blocked: bool,
    payload: str = "deterministic-output",
) -> BaselineOutputRequestV2:
    sorted_proposals = tuple(
        sorted(
            proposals,
            key=lambda item: (
                item["source_ref"].encode("utf-8"),
                item["signal_ref"].encode("utf-8"),
            ),
        )
    )
    direct = context.manifest.output_policy.decision_mode == "direct_governance"
    return BaselineOutputRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=_RUN_REF,
        request_ref=f"request:{label}:output",
        output_transition_id=f"transition:{label}:output",
        manifest=context.manifest,
        target_ref=_TARGET_REF,
        action_ref=_ACTION_REF,
        proposed_candidate_ref=_CANDIDATE_REF if direct else None,
        verified_signals=sorted_proposals,
        stop_resolutions=(
            {
                "action_ref": _ACTION_REF,
                "blocked": blocked,
                "provenance_ref": _root(f"stop:{label}"),
                "reason_ref": "reason:blocked" if blocked else "reason:clear",
            },
        ),
        output_payload={"output": payload},
        observed_epoch=2,
    )


def _issue_permission(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> tuple[GovernanceAuthoritySessionV2, GovernanceCommitAttemptV2]:
    session = open_baseline_output_authority_session_v2(
        context.permission_capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    return session, issue_action_permission_v2(request, authority_session=session)


def _commit_output(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> tuple[GovernanceAuthoritySessionV2, BaselineOutputResultV2]:
    session = open_baseline_output_authority_session_v2(
        context.output_capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    return session, evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=session,
    )


def _load_permission(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
) -> ActionPermissionV2:
    state = store.load_state_v2(request.scope_ref, request.permission_stream_ref)
    return ActionPermissionV2.from_dict(state["permission"])


def _read_manifest(*, decision_mode: str, threshold: int) -> ScopedProtocolManifestV2:
    value = read_capability_manifest(
        _capability_payload(decision_mode=decision_mode, threshold=threshold),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    if type(value) is not ScopedCapabilityManifestV2:
        raise TypeError("Protocol v3 reader returned a non-scoped capability")
    return value.protocol


def _capability_payload(*, decision_mode: str, threshold: int) -> dict[str, object]:
    return {
        "id": "baseline-output-v2-conformance",
        "name": "Baseline Output v2 Conformance",
        "version": "0.2.0rc1",
        "permissions": [],
        "required_connections": [],
        "drivers": [],
        "protocol": {
            "protocol_version": PROTOCOL_VERSION_V2,
            "id": "protocol:baseline-output-v2-conformance",
            "targets": [
                {
                    "id": _TARGET_REF,
                    "description": "Provider-free Baseline Output v2 target.",
                }
            ],
            "signals": [],
            "candidates": [
                {
                    "id": _CANDIDATE_REF,
                    "target": _TARGET_REF,
                    "label": "Accept",
                },
                {
                    "id": _FALLBACK_REF,
                    "target": _TARGET_REF,
                    "label": "Safe fallback",
                    "safe_fallback": True,
                },
            ],
            "quorum_policy": {
                "target": _TARGET_REF,
                "fallback_candidate": _FALLBACK_REF,
                "commit_threshold": threshold,
            },
            "authority_policy": {
                "policy_version": "pheroos-scoped-authority-policy-v2",
                "profile": "pheroos-scoped-authority-local-v2",
                "wire_version": "pheroos-authority-wire-v2",
                "canonical_version": "pheroos-authority-canonical-v2",
                "ledger_version": "pheroos-governance-authority-ledger-v2",
                "state_store_version": "pheroos-governance-state-store-v2",
                "trace_batch_version": "pheroos-governance-trace-batch-v2",
                "read_set_version": "pheroos-governance-authority-read-set-v2",
            },
            "recovery_protocols": [],
            "evidence_policy": {
                "require_provenance": True,
                "allow_agent_fact_creation": False,
            },
            "output_policy": {
                "policy_version": BASELINE_OUTPUT_POLICY_VERSION_V2,
                "decision_mode": decision_mode,
                "actions": [
                    {
                        "action_ref": _ACTION_REF,
                        "effect": "publish",
                        "target": _TARGET_REF,
                        "allowed_outcomes": [
                            "evidence_commit",
                            "safe_fallback",
                        ],
                    }
                ],
            },
            "trace_policy": {
                "required_events": sorted(
                    _REQUIRED_BASELINE_EVENTS
                    | {"block", "commit", "output", "recovery"}
                ),
            },
        },
    }


def _is_current_commit(attempt: GovernanceCommitAttemptV2) -> bool:
    return bool(
        type(attempt) is GovernanceCommitAttemptV2
        and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.failure is None
        and attempt.committed_transition is not None
        and attempt.position_observation is not None
        and attempt.position_observation.position is GovernanceCommitPositionV2.CURRENT
    )


def _same_commit(
    first: GovernanceCommitAttemptV2,
    second: GovernanceCommitAttemptV2,
) -> bool:
    return bool(
        first.disposition is GovernanceCommitDispositionV2.COMMITTED
        and second.disposition is GovernanceCommitDispositionV2.COMMITTED
        and first.committed_transition is not None
        and second.committed_transition is not None
        and first.committed_transition.receipt.receipt_root
        == second.committed_transition.receipt.receipt_root
    )


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


run_governance_baseline_output_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2",
    "run_governance_baseline_output_conformance_v2",
]
