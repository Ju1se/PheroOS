from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from hashlib import sha256
from typing import Any, cast

import pytest

from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
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
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
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
    baseline_output_result_root_v2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
from pheroos.protocol.authority_manifest_v2 import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    ScopedProtocolManifestV2,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)


def _root(label: str) -> str:
    return f"sha256:{sha256(label.encode('utf-8')).hexdigest()}"


def _record_values(record: object) -> dict[str, Any]:
    return {field.name: getattr(record, field.name) for field in fields(record)}


class _BoundaryStore:
    """A protocol-shaped store that can schedule one deterministic race."""

    def __init__(self, domain: AuthorityDomainV2) -> None:
        self.backing = InMemoryGovernanceStateStoreV2((domain,))
        self._armed_stream_ref: str | None = None
        self._before_atomic: Callable[[], None] | None = None
        self._hidden_state_stream_ref: str | None = None
        self._state_transform: (
            Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None
        ) = None

    @property
    def state_store_version(self) -> str:
        return self.backing.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.backing.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if stream_ref == self._hidden_state_stream_ref:
            raise KeyError("deterministically hidden state")
        state = self.backing.load_state_v2(scope_ref, stream_ref)
        if self._state_transform is None:
            return state
        return self._state_transform(stream_ref, state)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self.backing.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        callback = self._before_atomic
        if batch.stream_ref == self._armed_stream_ref and callback is not None:
            self._armed_stream_ref = None
            self._before_atomic = None
            callback()
        return self.backing.atomic_commit_v2(batch)

    def race_once(self, stream_ref: str, callback: Callable[[], None]) -> None:
        assert self._before_atomic is None
        self._armed_stream_ref = stream_ref
        self._before_atomic = callback

    def hide_state(self, stream_ref: str) -> None:
        self._hidden_state_stream_ref = stream_ref

    def transform_state(
        self,
        callback: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        self._state_transform = callback


class _CountingReader:
    def __init__(
        self,
        store: InMemoryGovernanceStateStoreV2,
        *,
        invalid_head_stream_ref: str | None = None,
        unavailable_head_stream_ref: str | None = None,
        missing_commit_view: bool = False,
    ) -> None:
        self.store = store
        self.invalid_head_stream_ref = invalid_head_stream_ref
        self.unavailable_head_stream_ref = unavailable_head_stream_ref
        self.missing_commit_view = missing_commit_view
        self.commit_view_calls = 0

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == self.unavailable_head_stream_ref:
            raise OSError("deterministically unavailable head")
        if stream_ref == self.invalid_head_stream_ref:
            return cast(GovernanceHeadV2, object())
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        self.commit_view_calls += 1
        if self.missing_commit_view:
            raise KeyError("deterministically missing commit view")
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        return view


@dataclass(frozen=True)
class _Context:
    domain: AuthorityDomainV2
    store: _BoundaryStore
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


def _context(
    *,
    scope_ref: str,
    operations: tuple[GovernanceIssuerOperationV2, ...] | None = None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        issuer_ref="issuer:baseline-semantics",
        grant_ref="grant:baseline-semantics",
        grant_binding_ref=_root("grant-binding"),
        operations=operations
        or (
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        ),
        target_refs=("target:answer",),
        action_refs=("action:publish",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    store = _BoundaryStore(domain)
    assert isinstance(store, GovernanceStateStoreV2)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant:activate",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    return _Context(
        domain=domain,
        store=store,
        grant=grant,
        capability=capability,
    )


def _manifest(
    *,
    decision_mode: str,
    threshold: int,
    allowed_outcomes: tuple[str, ...] = ("evidence_commit", "safe_fallback"),
) -> ScopedProtocolManifestV2:
    return scoped_protocol_manifest_v2_from_dict(
        {
            "protocol_version": PROTOCOL_VERSION_V2,
            "id": "protocol:baseline-output-semantics",
            "targets": [
                {
                    "id": "target:answer",
                    "description": "Provider-free semantic test target.",
                }
            ],
            "signals": [],
            "candidates": [
                {
                    "id": "candidate:accept",
                    "target": "target:answer",
                    "label": "Accept",
                },
                {
                    "id": "candidate:fallback",
                    "target": "target:answer",
                    "label": "Fallback",
                    "safe_fallback": True,
                },
            ],
            "quorum_policy": {
                "target": "target:answer",
                "fallback_candidate": "candidate:fallback",
                "commit_threshold": threshold,
            },
            "authority_policy": {
                "policy_version": AUTHORITY_POLICY_VERSION_V2,
                "profile": AUTHORITY_LOCAL_PROFILE_V2,
                "wire_version": AUTHORITY_WIRE_VERSION_V2,
                "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
                "ledger_version": AUTHORITY_LEDGER_VERSION_V2,
                "state_store_version": GOVERNANCE_STATE_STORE_VERSION_V2,
                "trace_batch_version": GOVERNANCE_TRACE_BATCH_VERSION_V2,
                "read_set_version": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
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
                        "action_ref": "action:publish",
                        "effect": "publish",
                        "target": "target:answer",
                        "allowed_outcomes": list(allowed_outcomes),
                    }
                ],
            },
            "trace_policy": {
                "required_events": [
                    "baseline_action_permission_issued",
                    "baseline_decision_evaluated",
                    "baseline_evidence_qualified",
                    "baseline_manifest_activated",
                    "baseline_output_committed",
                    "baseline_stop_resolved",
                ]
            },
        }
    )


def _verified_signal(
    context: _Context,
    *,
    label: str,
    candidate_ref: str = "candidate:accept",
    source_ref: str | None = None,
) -> dict[str, str]:
    signal_ref = f"signal:{label}"
    transition_id = f"transition:signal:{label}"
    evidence_root = _root(f"evidence:{label}")
    provenance_ref = _root(f"provenance:{label}")
    resolved_source_ref = source_ref or f"source:{label}"
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        target_ref="target:answer",
        candidate_ref=candidate_ref,
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=resolved_source_ref,
    )
    signal_request = GovernanceVerifiedSignalRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        request_ref=f"request:signal:{label}",
        transition_id=transition_id,
        signal_ref=signal_ref,
        target_ref="target:answer",
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=2,
    )
    session = open_governance_authority_session_v2(
        context.capability,
        signal_request,
    )
    committed = commit_verified_signal_v2(
        signal_request,
        authority_session=session,
    )
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    return {
        "candidate_ref": candidate_ref,
        "evidence_root": evidence_root,
        "provenance_ref": provenance_ref,
        "signal_ref": signal_ref,
        "signal_root": signal_root,
        "signal_transition_id": transition_id,
        "source_ref": resolved_source_ref,
    }


def _request(
    context: _Context,
    *,
    label: str,
    decision_mode: str = "direct_governance",
    threshold: int = 1,
    verified_signals: tuple[dict[str, str], ...] | None = None,
    blocked: bool = False,
    allowed_outcomes: tuple[str, ...] = ("evidence_commit", "safe_fallback"),
) -> BaselineOutputRequestV2:
    if verified_signals is None:
        verified_signals = (
            (
                _verified_signal(
                    context,
                    label=f"{label}:direct",
                    source_ref=f"source:{label}:direct",
                ),
            )
            if decision_mode == "direct_governance"
            else ()
        )
    ordered_signals = tuple(
        sorted(
            verified_signals,
            key=lambda item: (
                item["source_ref"].encode("utf-8"),
                item["signal_ref"].encode("utf-8"),
            ),
        )
    )
    return BaselineOutputRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        request_ref=f"request:output:{label}",
        output_transition_id=f"transition:output:{label}",
        manifest=_manifest(
            decision_mode=decision_mode,
            threshold=threshold,
            allowed_outcomes=allowed_outcomes,
        ),
        target_ref="target:answer",
        action_ref="action:publish",
        proposed_candidate_ref=(
            "candidate:accept" if decision_mode == "direct_governance" else None
        ),
        verified_signals=ordered_signals,
        stop_resolutions=(
            {
                "action_ref": "action:publish",
                "blocked": blocked,
                "provenance_ref": _root(f"stop:{label}"),
                "reason_ref": "reason:blocked" if blocked else "reason:clear",
            },
        ),
        output_payload={"answer": f"payload:{label}"},
        observed_epoch=2,
    )


def _issue(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> GovernanceCommitAttemptV2:
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    return issue_action_permission_v2(
        request,
        authority_session=session,
    )


def _authorize(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> BaselineOutputResultV2:
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    return evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=session,
    )


def _permission(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> ActionPermissionV2:
    state = context.store.load_state_v2(
        request.scope_ref,
        request.permission_stream_ref,
    )
    return ActionPermissionV2.from_dict(state["permission"])


def test_public_prepare_authorize_and_recover_bind_all_reads_and_lineage() -> None:
    context = _context(scope_ref="scope:baseline-semantics:vertical")
    request = _request(context, label="vertical")
    signal = request.verified_signals[0]
    signal_stream_ref = governance_verified_signal_stream_ref_v2(
        request.scope_ref,
        cast(str, signal["signal_ref"]),
        request.target_ref,
    )
    grant_stream_ref = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        context.grant.grant_ref,
    )

    permission_attempt = _issue(context, request)

    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    stage_contracts = {
        "manifest": (
            request.manifest_stream_ref,
            BASELINE_MANIFEST_STATE_SCHEMA_V2,
            "baseline_manifest_activated",
            {
                request.manifest_stream_ref,
                grant_stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            },
        ),
        "evidence": (
            request.evidence_stream_ref,
            BASELINE_EVIDENCE_STATE_SCHEMA_V2,
            "baseline_evidence_qualified",
            {
                request.evidence_stream_ref,
                request.manifest_stream_ref,
                signal_stream_ref,
                grant_stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            },
        ),
        "stop": (
            request.stop_stream_ref,
            BASELINE_STOP_STATE_SCHEMA_V2,
            "baseline_stop_resolved",
            {
                request.stop_stream_ref,
                request.manifest_stream_ref,
                grant_stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            },
        ),
        "decision": (
            request.decision_stream_ref,
            BASELINE_DECISION_STATE_SCHEMA_V2,
            "baseline_decision_evaluated",
            {
                request.decision_stream_ref,
                request.manifest_stream_ref,
                request.evidence_stream_ref,
                request.stop_stream_ref,
                grant_stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            },
        ),
        "permission": (
            request.permission_stream_ref,
            BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
            "baseline_action_permission_issued",
            {
                request.permission_stream_ref,
                request.manifest_stream_ref,
                request.evidence_stream_ref,
                request.stop_stream_ref,
                request.decision_stream_ref,
                grant_stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            },
        ),
    }
    for role, (
        stream_ref,
        schema,
        event_type,
        expected_reads,
    ) in stage_contracts.items():
        view = context.store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            request.stage_transition_id(role),
        )
        assert view.disposition is GovernanceCommitDispositionV2.COMMITTED
        assert view.committed_transition is not None
        batch = view.committed_transition.batch
        assert batch.transition is not None
        assert batch.transition.state_records["schema"] == schema
        assert {entry.stream_ref for entry in batch.read_set.entries} == expected_reads
        assert tuple(entry.stream_ref for entry in batch.read_set.entries) == tuple(
            sorted(expected_reads, key=lambda item: item.encode("utf-8"))
        )
        assert len(batch.trace_batch.events) == 1
        event = batch.trace_batch.events[0]
        assert event.event_type == event_type
        assert event.protocol_id == PROTOCOL_VERSION_V2
        assert event.target == request.target_ref
        assert event.lineage["domain_root"] == request.domain_root
        assert event.lineage["scope_ref"] == request.scope_ref
        assert event.lineage["stream_ref"] == stream_ref
        assert event.lineage["transition_id"] == request.stage_transition_id(role)
        assert event.lineage["request_root"] == request.request_root
        assert event.lineage["operation"] == (
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION.value
        )

    permission = _permission(context, request)
    assert permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
    assert permission.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT

    result = _authorize(context, request)

    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert result.position is GovernanceCommitPositionV2.CURRENT
    assert result.delivery_disposition is (
        BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert result.authorization == permission
    assert result.commit_attempt.committed_transition is not None
    output_batch = result.commit_attempt.committed_transition.batch
    assert output_batch.transition is not None
    assert (
        output_batch.transition.state_records["schema"]
        == BASELINE_OUTPUT_STATE_SCHEMA_V2
    )
    assert {entry.stream_ref for entry in output_batch.read_set.entries} == {
        request.output_stream_ref,
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        grant_stream_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    output_event = output_batch.trace_batch.events[0]
    assert output_event.event_type == "baseline_output_committed"
    assert output_event.lineage["operation"] == (
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT.value
    )
    assert output_event.lineage["permission_root"] == permission.permission_root
    assert output_event.lineage["result_root"] == result.result_root
    assert output_event.lineage["read_set_root"] == output_batch.read_set.root()

    restored = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.store.backing.snapshot_v2()
    )
    reader = _CountingReader(restored)
    recovered = recover_baseline_output_result_v2(
        request,
        state_reader=reader,
    )

    assert reader.commit_view_calls == 1
    assert recovered == result
    assert recovered.canonical_bytes() == result.canonical_bytes()
    assert recovered.authorization == permission


@pytest.mark.parametrize(
    "raced_role",
    ("manifest", "evidence", "stop", "decision"),
)
def test_preparation_conflict_returns_retry_and_stops_remaining_stages(
    raced_role: str,
) -> None:
    context = _context(scope_ref=f"scope:baseline-semantics:prepare-race:{raced_role}")
    request = _request(context, label="loser")
    rival = _request(context, label="winner")
    stream_by_role = {
        "manifest": request.manifest_stream_ref,
        "evidence": request.evidence_stream_ref,
        "stop": request.stop_stream_ref,
        "decision": request.decision_stream_ref,
        "permission": request.permission_stream_ref,
    }
    rival_attempts: list[GovernanceCommitAttemptV2] = []
    context.store.race_once(
        stream_by_role[raced_role],
        lambda: rival_attempts.append(_issue(context, rival)),
    )

    raced = _issue(context, request)

    assert len(rival_attempts) == 1
    assert rival_attempts[0].disposition is GovernanceCommitDispositionV2.COMMITTED
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.stream_ref == stream_by_role[raced_role]
    assert raced.transition_id == request.stage_transition_id(raced_role)
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ordered_roles = ("manifest", "evidence", "stop", "decision", "permission")
    first_uncommitted = ordered_roles.index(raced_role)
    for role in ordered_roles[first_uncommitted:]:
        view = context.store.load_commit_view_v2(
            request.scope_ref,
            stream_by_role[role],
            request.stage_transition_id(role),
        )
        assert view.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )


@pytest.mark.parametrize(
    "attack",
    ("superseded-transition", "undeclared-candidate"),
)
def test_verified_signal_preparation_fails_closed_on_unbound_proposals(
    attack: str,
) -> None:
    context = _context(scope_ref=f"scope:baseline-semantics:signal-binding:{attack}")
    proposal = _verified_signal(
        context,
        label=attack,
        source_ref="source:independent",
    )
    if attack == "superseded-transition":
        successor = GovernanceVerifiedSignalRequestV2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            run_ref="run:one",
            request_ref="request:signal:successor",
            transition_id="transition:signal:successor",
            signal_ref=proposal["signal_ref"],
            target_ref="target:answer",
            signal_root=proposal["signal_root"],
            evidence_root=proposal["evidence_root"],
            status="verified",
            observed_epoch=2,
        )
        successor_session = open_governance_authority_session_v2(
            context.capability,
            successor,
        )
        successor_attempt = commit_verified_signal_v2(
            successor,
            authority_session=successor_session,
        )
        assert successor_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    else:
        proposal["candidate_ref"] = "candidate:undeclared"
        proposal["signal_root"] = baseline_verified_signal_proposal_root_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            run_ref="run:one",
            target_ref="target:answer",
            candidate_ref=proposal["candidate_ref"],
            signal_ref=proposal["signal_ref"],
            evidence_root=proposal["evidence_root"],
            provenance_ref=proposal["provenance_ref"],
            source_ref=proposal["source_ref"],
        )
    request = _request(
        context,
        label=attack,
        decision_mode="quorum",
        threshold=1,
        verified_signals=(proposal,),
    )

    denied = _issue(context, request)

    assert denied.disposition is GovernanceCommitDispositionV2.INVALID
    assert denied.stream_ref == request.evidence_stream_ref
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    for stream_ref in (
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        request.output_stream_ref,
    ):
        assert context.store.load_head_v2(request.scope_ref, stream_ref).revision == 0


def test_output_conflict_returns_nonterminal_retry_without_output_commit() -> None:
    context = _context(scope_ref="scope:baseline-semantics:output-race")
    request = _request(context, label="loser")
    rival = _request(context, label="winner")
    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    rival_attempts: list[GovernanceCommitAttemptV2] = []
    context.store.race_once(
        request.output_stream_ref,
        lambda: rival_attempts.append(_issue(context, rival)),
    )

    result = _authorize(context, request)

    assert len(rival_attempts) == 1
    assert rival_attempts[0].disposition is GovernanceCommitDispositionV2.COMMITTED
    assert result.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert result.delivery_disposition is (
        BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED
    )
    assert result.terminal_status is None
    assert result.candidate_ref is None
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert result.authorization is None
    assert BaselineOutputResultV2.from_dict(result.to_dict()) == result
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )


def test_revoked_permission_issuer_cannot_be_reused_by_an_output_only_grant() -> None:
    context = _context(scope_ref="scope:baseline-semantics:two-grants")
    request = _request(context, label="two-grants")
    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    output_grant = GovernanceIssuerGrantV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        issuer_ref="issuer:output-only",
        grant_ref="grant:output-only",
        grant_binding_ref=_root("output-only-binding"),
        operations=(GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,),
        target_refs=(request.target_ref,),
        action_refs=(request.action_ref,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        output_grant,
        "transition:grant:output-only:activate",
        2,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    output_capability = bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        output_grant,
        request.run_ref,
        request.observed_epoch,
    )
    output_session = open_baseline_output_authority_session_v2(
        output_capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:grant:permission-issuer:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED

    denied = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )

    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert denied.permission_root == permission.permission_root
    assert denied.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert denied.authorization is None
    assert denied.commit_attempt.failure is not None
    assert denied.commit_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    )
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )


def test_revoked_output_session_grant_fails_before_loading_or_writing_output() -> None:
    context = _context(scope_ref="scope:baseline-semantics:revoked-output-session")
    request = _request(context, label="revoked-output-session")
    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    output_session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:grant:output-session:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED

    denied = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )

    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert denied.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert denied.authorization is None
    assert denied.commit_attempt.failure is not None
    assert denied.commit_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    )
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )


def test_operation_revalidates_manifest_authority_after_session_open() -> None:
    context = _context(scope_ref="scope:baseline-semantics:manifest-revalidation")
    request = _request(context, label="manifest-revalidation")
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    object.__setattr__(
        request.manifest.authority_policy,
        "profile",
        AUTHORITY_AUTHENTICATED_PROFILE_V2,
    )

    denied = issue_action_permission_v2(
        request,
        authority_session=session,
    )

    assert denied.disposition is GovernanceCommitDispositionV2.INVALID
    assert denied.failure is not None
    assert denied.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED
    )
    for stream_ref in (
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        request.output_stream_ref,
    ):
        assert context.store.load_head_v2(request.scope_ref, stream_ref).revision == 0


def test_missing_inputs_and_unreliable_currentness_reads_fail_closed() -> None:
    context = _context(scope_ref="scope:baseline-semantics:fail-closed")
    request = _request(context, label="missing")

    missing = _authorize(context, request)

    assert missing.disposition is GovernanceCommitDispositionV2.INVALID
    assert missing.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert missing.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert missing.authorization is None
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )

    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    committed = _authorize(context, request)
    assert committed.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    restored = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.store.backing.snapshot_v2()
    )
    currentness_readers = (
        _CountingReader(
            restored,
            invalid_head_stream_ref=request.permission_stream_ref,
        ),
        _CountingReader(
            restored,
            unavailable_head_stream_ref=request.permission_stream_ref,
        ),
    )
    for reader in currentness_readers:
        recovered = recover_baseline_output_result_v2(
            request,
            state_reader=reader,
        )

        assert reader.commit_view_calls == 1
        assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
        assert recovered.delivery_disposition is (
            BaselineOutputDeliveryDispositionV2.DELIVERABLE
        )
        assert recovered.action_disposition is BaselineOutputActionDispositionV2.DENIED
        assert recovered.authorization is None
        assert recovered.result_root == committed.result_root

    missing_view_reader = _CountingReader(restored, missing_commit_view=True)
    missing_view = recover_baseline_output_result_v2(
        request,
        state_reader=missing_view_reader,
    )
    assert missing_view_reader.commit_view_calls == 1
    assert missing_view.disposition is GovernanceCommitDispositionV2.INVALID
    assert missing_view.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert missing_view.authorization is None

    hidden_context = _context(
        scope_ref="scope:baseline-semantics:fail-closed:hidden-state"
    )
    hidden_request = _request(hidden_context, label="hidden-state")
    assert _issue(hidden_context, hidden_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    hidden_context.store.hide_state(hidden_request.permission_stream_ref)

    hidden = _authorize(hidden_context, hidden_request)

    assert hidden.disposition is GovernanceCommitDispositionV2.DENIED
    assert hidden.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert hidden.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert hidden.authorization is None
    assert hidden.commit_attempt.failure is not None
    assert hidden.commit_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED
    )
    assert (
        hidden_context.store.load_head_v2(
            hidden_request.scope_ref,
            hidden_request.output_stream_ref,
        ).revision
        == 0
    )


@pytest.mark.parametrize(
    ("attack", "expected_code"),
    (
        (
            "candidate-substitution",
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        ),
        (
            "expired-at-request-epoch",
            AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
        ),
    ),
)
def test_output_rejects_canonical_but_unbound_permission_state(
    attack: str,
    expected_code: AuthorityDiagnosticCodeV2,
) -> None:
    context = _context(scope_ref=f"scope:baseline-semantics:permission-state:{attack}")
    request = _request(context, label=attack)
    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )

    def substitute_permission(
        stream_ref: str,
        state: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if stream_ref != request.permission_stream_ref:
            return state
        permission_wire = ActionPermissionV2.from_dict(state["permission"]).to_dict()
        if attack == "candidate-substitution":
            permission_wire["candidate_ref"] = "candidate:fallback"
        else:
            permission_wire["issued_epoch"] = 1
            permission_wire["expires_at_epoch"] = request.observed_epoch
        permission_wire["permission_root"] = ""
        substituted = ActionPermissionV2.from_dict(permission_wire)
        return {
            **state,
            "permission": substituted.to_dict(),
            "permission_root": substituted.permission_root,
        }

    context.store.transform_state(substitute_permission)

    denied = _authorize(context, request)

    assert denied.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert denied.authorization is None
    assert denied.commit_attempt.failure is not None
    assert denied.commit_attempt.failure.code is expected_code
    assert (
        context.store.backing.load_head_v2(
            request.scope_ref,
            request.output_stream_ref,
        ).revision
        == 0
    )


def test_quorum_counts_distinct_sources_and_breaks_ties_by_candidate_ref() -> None:
    context = _context(scope_ref="scope:baseline-semantics:quorum")
    tied = (
        _verified_signal(
            context,
            label="tie:fallback",
            candidate_ref="candidate:fallback",
            source_ref="source:zulu",
        ),
        _verified_signal(
            context,
            label="tie:accept",
            candidate_ref="candidate:accept",
            source_ref="source:alpha",
        ),
    )
    tied_request = _request(
        context,
        label="tie",
        decision_mode="quorum",
        threshold=1,
        verified_signals=tied,
    )

    assert _issue(context, tied_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    tied_permission = _permission(context, tied_request)
    assert tied_permission.candidate_ref == "candidate:accept"
    assert tied_permission.terminal_status is (
        BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
    )
    assert tied_permission.disposition is ActionPermissionDispositionV2.AUTHORIZED

    same_source = (
        _verified_signal(
            context,
            label="same-source:one",
            source_ref="source:shared",
        ),
        _verified_signal(
            context,
            label="same-source:two",
            source_ref="source:shared",
        ),
    )
    fallback_request = _request(
        context,
        label="same-source",
        decision_mode="quorum",
        threshold=2,
        verified_signals=same_source,
    )

    assert _issue(context, fallback_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    fallback_permission = _permission(context, fallback_request)
    assert fallback_permission.candidate_ref == "candidate:fallback"
    assert fallback_permission.terminal_status is (
        BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    )
    assert fallback_permission.disposition is (ActionPermissionDispositionV2.AUTHORIZED)


def test_public_boundaries_reject_ambiguous_or_unreachable_values() -> None:
    context = _context(scope_ref="scope:baseline-semantics:boundaries")
    request = _request(context, label="boundaries")

    with pytest.raises(ValueError, match="stage role is unsupported"):
        request.stage_transition_id("output")
    with pytest.raises(TypeError, match="exact request"):
        baseline_output_result_root_v2(
            request.to_dict(),  # type: ignore[arg-type]
            terminal_status=BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            candidate_ref="candidate:accept",
            permission_root=_root("permission"),
        )
    with pytest.raises(TypeError, match="terminal_status is invalid"):
        baseline_output_result_root_v2(
            request,
            terminal_status="evidence_commit",  # type: ignore[arg-type]
            candidate_ref="candidate:accept",
            permission_root=_root("permission"),
        )
    with pytest.raises(TypeError, match="exact request type"):
        open_baseline_output_authority_session_v2(
            context.capability,
            request.to_dict(),  # type: ignore[arg-type]
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as operation_denied:
        open_baseline_output_authority_session_v2(
            context.capability,
            request,
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        )
    assert operation_denied.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED
    )

    epoch_wire = request.to_dict()
    epoch_wire["observed_epoch"] = MAX_AUTHORITY_REVISION_V2
    with pytest.raises(ValueError, match="leaves no permission expiry epoch"):
        BaselineOutputRequestV2.from_dict(epoch_wire)

    stop_wire = deepcopy(request.to_dict())
    stop_wire["stop_resolutions"][0]["blocked"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="blocked must be an exact bool"):
        BaselineOutputRequestV2.from_dict(stop_wire)

    request_values = _record_values(request)
    with pytest.raises(TypeError, match="exact scoped manifest"):
        BaselineOutputRequestV2(
            **{**request_values, "manifest": object()}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="target is not declared"):
        BaselineOutputRequestV2(**{**request_values, "target_ref": "target:undeclared"})
    manifest_without_candidates = ScopedProtocolManifestV2.from_dict(
        request.manifest.to_dict()
    )
    object.__setattr__(manifest_without_candidates, "candidates", ())
    with pytest.raises(ValueError, match="target has no declared candidates"):
        BaselineOutputRequestV2(
            **{**request_values, "manifest": manifest_without_candidates}
        )
    mismatched_action_manifest = ScopedProtocolManifestV2.from_dict(
        request.manifest.to_dict()
    )
    object.__setattr__(
        mismatched_action_manifest.output_policy.actions[0],
        "target",
        "target:other",
    )
    with pytest.raises(ValueError, match="action target is mismatched"):
        BaselineOutputRequestV2(
            **{**request_values, "manifest": mismatched_action_manifest}
        )
    with pytest.raises(ValueError, match="candidate is not declared"):
        BaselineOutputRequestV2(
            **{
                **request_values,
                "proposed_candidate_ref": "candidate:undeclared",
            }
        )
    quorum_request = _request(
        context,
        label="quorum-boundary",
        decision_mode="quorum",
        verified_signals=(),
    )
    with pytest.raises(ValueError, match="cannot carry a direct candidate"):
        BaselineOutputRequestV2(
            **{
                **_record_values(quorum_request),
                "proposed_candidate_ref": "candidate:accept",
            }
        )
    with pytest.raises(ValueError, match="action is not declared exactly once"):
        BaselineOutputRequestV2(**{**request_values, "action_ref": "action:undeclared"})
    with pytest.raises(TypeError, match="verified_signals must be an exact tuple"):
        BaselineOutputRequestV2(
            **{
                **request_values,
                "verified_signals": list(request.verified_signals),
            }
        )
    with pytest.raises(ValueError, match="must be unique and UTF-8 sorted"):
        BaselineOutputRequestV2(
            **{
                **request_values,
                "verified_signals": (
                    request.verified_signals[0],
                    request.verified_signals[0],
                ),
            }
        )
    with pytest.raises(TypeError, match="verified_signals/0 must be a mapping"):
        BaselineOutputRequestV2(**{**request_values, "verified_signals": (object(),)})
    incomplete_signal = dict(request.verified_signals[0])
    incomplete_signal.pop("source_ref")
    with pytest.raises(ValueError, match="verified_signals/0 fields are invalid"):
        BaselineOutputRequestV2(
            **{**request_values, "verified_signals": (incomplete_signal,)}
        )
    with pytest.raises(TypeError, match="stop_resolutions must be an exact tuple"):
        BaselineOutputRequestV2(
            **{
                **request_values,
                "stop_resolutions": list(request.stop_resolutions),
            }
        )
    with pytest.raises(ValueError, match="must cover every declared target action"):
        BaselineOutputRequestV2(**{**request_values, "stop_resolutions": ()})

    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    permission_wire = permission.to_dict()
    expired_permission = {**permission_wire, "permission_root": ""}
    expired_permission["expires_at_epoch"] = permission_wire["issued_epoch"]
    with pytest.raises(ValueError, match="expiry must follow issuance"):
        ActionPermissionV2.from_dict(expired_permission)

    blocked_permission = {
        **permission_wire,
        "terminal_status": BaselineOutputTerminalStatusV2.BLOCKED.value,
        "permission_root": "",
    }
    with pytest.raises(ValueError, match="cannot be authorized"):
        ActionPermissionV2.from_dict(blocked_permission)

    permission_values = _record_values(permission)
    with pytest.raises(ValueError, match="effect is unsupported"):
        ActionPermissionV2(**{**permission_values, "effect": "side-effect"})
    with pytest.raises(TypeError, match="terminal_status is invalid"):
        ActionPermissionV2(
            **{
                **permission_values,
                "terminal_status": "evidence_commit",
            }  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="disposition is invalid"):
        ActionPermissionV2(
            **{
                **permission_values,
                "disposition": "authorized",
            }  # type: ignore[arg-type]
        )

    result = _authorize(context, request)
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    result_values = _record_values(result)
    with pytest.raises(TypeError, match="exact commit attempt"):
        BaselineOutputResultV2(
            **{
                **result_values,
                "commit_attempt": object(),
            }  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="delivery disposition is invalid"):
        BaselineOutputResultV2(
            **{
                **result_values,
                "delivery_disposition": "deliverable",
            }  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="action disposition is invalid"):
        BaselineOutputResultV2(
            **{
                **result_values,
                "action_disposition": "authorized",
            }  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="authorization is invalid"):
        BaselineOutputResultV2(
            **{
                **result_values,
                "authorization": object(),
            }  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="denied baseline result"):
        BaselineOutputResultV2(
            **{
                **result_values,
                "action_disposition": BaselineOutputActionDispositionV2.DENIED,
            }
        )

    successor = _request(context, label="boundary-successor")
    assert _issue(context, successor).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    assert _authorize(context, successor).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    historical = _authorize(context, request)
    assert historical.position is GovernanceCommitPositionV2.SUPERSEDED
    with pytest.raises(ValueError, match="requires a current commit"):
        BaselineOutputResultV2(
            **{
                **_record_values(historical),
                "action_disposition": BaselineOutputActionDispositionV2.AUTHORIZED,
                "authorization": permission,
            }
        )

    denied_context = _context(
        scope_ref="scope:baseline-semantics:boundaries:denied-permission"
    )
    denied_request = _request(
        denied_context,
        label="denied-permission",
        verified_signals=(),
    )
    assert _issue(denied_context, denied_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    denied_permission = _permission(denied_context, denied_request)
    denied_result = _authorize(denied_context, denied_request)
    with pytest.raises(ValueError, match="authorization must be authorized"):
        BaselineOutputResultV2(
            **{
                **_record_values(denied_result),
                "action_disposition": BaselineOutputActionDispositionV2.AUTHORIZED,
                "authorization": denied_permission,
            }
        )

    unprepared_context = _context(
        scope_ref="scope:baseline-semantics:boundaries:unprepared"
    )
    unprepared_request = _request(unprepared_context, label="unprepared")
    unprepared = _authorize(unprepared_context, unprepared_request)
    unprepared_values = _record_values(unprepared)
    with pytest.raises(ValueError, match="commit attempt binding is mismatched"):
        BaselineOutputResultV2(
            **{**unprepared_values, "scope_ref": "scope:substituted"}
        )
    with pytest.raises(TypeError, match="requires terminal status"):
        BaselineOutputResultV2(
            **{
                **unprepared_values,
                "terminal_status": "invalid",
            }  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="requires candidate_ref"):
        BaselineOutputResultV2(**{**unprepared_values, "candidate_ref": None})
    with pytest.raises(ValueError, match="result_root is mismatched"):
        BaselineOutputResultV2(
            **{**unprepared_values, "result_root": _root("substituted-result")}
        )

    retry_wire = unprepared.to_dict()
    retry_wire.update(
        {
            "terminal_status": None,
            "candidate_ref": None,
            "delivery_disposition": (
                BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED.value
            ),
        }
    )
    with pytest.raises(ValueError, match="retry result must remain non-terminal"):
        BaselineOutputResultV2.from_dict(retry_wire)
