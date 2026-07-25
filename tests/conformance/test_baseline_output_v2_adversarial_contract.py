from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import pytest

from pheroos.conformance import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    run_governance_baseline_output_conformance_v2,
)
from pheroos.governance import (
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.trace import TraceEvent


_ZERO_ROOT = "sha256:" + ("0" * 64)
_BASELINE_MANIFEST = "authority:baseline-manifest:"
_BASELINE_EVIDENCE = "authority:baseline-evidence:"
_BASELINE_STOP = "authority:baseline-stop:"
_BASELINE_PERMISSION = "authority:baseline-action-permission:"
_BASELINE_OUTPUT = "authority:baseline-output:"
_VERIFIED_SIGNAL = "authority:verified-signal:"


class _Proxy:
    """Expose one forged public-ABI observation while delegating all else."""

    def __init__(self, delegate: object, **overrides: object) -> None:
        self._delegate = delegate
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._delegate, name)


def _failed_attempt(
    batch: GovernanceCommitBatchV2,
    *,
    finality: bool = False,
) -> GovernanceCommitAttemptV2:
    if finality:
        code = AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
        disposition = GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
        stage = GovernanceFailureStageV2.FINALITY
    else:
        code = AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
        disposition = GovernanceCommitDispositionV2.RETRY_REQUIRED
        stage = GovernanceFailureStageV2.PRECONDITION
    failure = GovernanceFailureV2(code=code, path="/read_set", stage=stage)
    return GovernanceCommitAttemptV2(
        domain_root=batch.domain.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=disposition,
        failure=failure,
        committed_transition=None,
        position_observation=None,
    )


def _finality_view(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
    failure = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        path="/transition_id",
        stage=GovernanceFailureStageV2.LOAD,
    )
    return GovernanceCommitViewV2(
        domain_root=view.domain_root,
        scope_ref=view.scope_ref,
        stream_ref=view.stream_ref,
        transition_id=view.transition_id,
        expected_receipt_root=view.expected_receipt_root,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=failure,
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )


class _AdversarialStoreV2:
    """A third-party StateStore that fabricates one narrowly scoped fact."""

    def __init__(
        self,
        delegate: GovernanceStateStoreV2,
        *,
        fault: str,
        target_scope: str,
        restarted: bool = False,
    ) -> None:
        self.delegate = delegate
        self.fault = fault
        self.target_scope = target_scope
        self.restarted = restarted
        self.output_committed = False
        self.permission_committed = False
        self.issuer_revoked = False
        self.output_grant_stream: str | None = None
        self.done: set[str] = set()
        self.view_counts: dict[str, int] = {}
        self.transitions: dict[str, object] = {}
        self.output_attempt: GovernanceCommitAttemptV2 | None = None

    @property
    def state_store_version(self) -> str:
        return self.delegate.state_store_version

    def _targets(self, scope_ref: str) -> bool:
        return scope_ref == self.target_scope

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = self.delegate.load_head_v2(scope_ref, stream_ref)
        if not self._targets(scope_ref):
            return head
        if (
            self.fault == "permission-separation"
            and stream_ref.startswith(_BASELINE_OUTPUT)
            and not self.output_committed
            and "permission-separation" not in self.done
        ):
            self.done.add("permission-separation")
            return cast(GovernanceHeadV2, _Proxy(head, revision=1))
        if (
            self.fault == "binding-head"
            and stream_ref.startswith(_BASELINE_PERMISSION)
            and "binding-head" not in self.done
        ):
            self.done.add("binding-head")
            return cast(GovernanceHeadV2, _Proxy(head, revision=1))
        if (
            self.fault == "operation-head"
            and stream_ref.startswith(_BASELINE_MANIFEST)
            and "operation-head" not in self.done
        ):
            self.done.add("operation-head")
            return cast(GovernanceHeadV2, _Proxy(head, revision=1))
        if (
            self.fault == "issuer-history"
            and self.issuer_revoked
            and stream_ref == self.output_grant_stream
            and "issuer-history" not in self.done
        ):
            self.done.add("issuer-history")
            return cast(GovernanceHeadV2, _Proxy(head, revision=99))
        return head

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        state = self.delegate.load_state_v2(scope_ref, stream_ref)
        if not self._targets(scope_ref):
            return state
        state = self._mutate_pre_output_state(state, stream_ref)
        if not self.output_committed:
            return state
        state = self._mutate_committed_state(state, stream_ref)
        return self._mutate_evidence_state(state, stream_ref)

    def _mutate_pre_output_state(
        self,
        state: Mapping[str, Any],
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if (
            self.fault == "verified-signal-state"
            and stream_ref.startswith(_VERIFIED_SIGNAL)
            and "verified-signal-state" not in self.done
        ):
            self.done.add("verified-signal-state")
            return {**state, "status": "forged"}
        if (
            self.fault == "durable-permission"
            and self.permission_committed
            and not self.output_committed
            and stream_ref.startswith(_BASELINE_PERMISSION)
            and "durable-permission" not in self.done
        ):
            self.done.add("durable-permission")
            permission = dict(cast(Mapping[str, Any], state["permission"]))
            permission["action_ref"] = "action:forged"
            permission["permission_root"] = ""
            return {**state, "permission": permission}
        return state

    def _mutate_committed_state(
        self,
        state: Mapping[str, Any],
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if (
            self.fault == "terminal-attempt-toctou"
            and stream_ref.startswith(_BASELINE_MANIFEST)
            and "terminal-attempt-toctou" not in self.done
        ):
            self.done.add("terminal-attempt-toctou")
            assert self.output_attempt is not None
            object.__setattr__(self.output_attempt, "committed_transition", None)
            return state
        if (
            self.fault == "durable-schema"
            and stream_ref.startswith(_BASELINE_MANIFEST)
            and "durable-schema" not in self.done
        ):
            self.done.add("durable-schema")
            return {**state, "schema": "forged-state-v2"}
        if (
            self.fault == "durable-links"
            and stream_ref.startswith(_BASELINE_MANIFEST)
            and "durable-links" not in self.done
        ):
            self.done.add("durable-links")
            return {**state, "manifest_root": _ZERO_ROOT}
        if (
            self.fault == "stop-closure"
            and stream_ref.startswith(_BASELINE_STOP)
            and "stop-closure" not in self.done
        ):
            self.done.add("stop-closure")
            return {**state, "resolutions": ()}
        return state

    def _mutate_evidence_state(
        self,
        state: Mapping[str, Any],
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if (
            self.fault.startswith("evidence-")
            and stream_ref.startswith(_BASELINE_EVIDENCE)
            and "evidence" not in self.done
        ):
            self.done.add("evidence")
            if self.fault == "evidence-container":
                return {**state, "signals": "forged"}
            records = [
                dict(item)
                for item in cast(Sequence[Mapping[str, Any]], state["signals"])
            ]
            if self.fault == "evidence-record":
                records[0] = cast(dict[str, Any], "forged")
            elif self.fault == "evidence-binding":
                records[0]["source_ref"] = "source:forged"
            else:
                records[0]["verified_signal_receipt_root"] = "forged"
            return {**state, "signals": records}
        return state

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        view = self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if not self._targets(scope_ref):
            return view
        view = self._mutate_restart_view(
            view,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if not self.output_committed:
            return view
        return self._mutate_committed_view(view, transition_id)

    def _mutate_restart_view(
        self,
        view: GovernanceCommitViewV2,
        transition_id: str,
        *,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if (
            self.fault == "restart-recovery"
            and self.restarted
            and transition_id == "transition:currentness-first:output"
            and "restart-recovery" not in self.done
        ):
            self.done.add("restart-recovery")
            return _finality_view(view)
        if (
            self.fault == "restart-exact-retry"
            and self.restarted
            and transition_id == "transition:currentness-first:output"
        ):
            count = self.view_counts.get(transition_id, 0) + 1
            self.view_counts[transition_id] = count
            if count == 2:
                return _finality_view(view)
        if (
            self.fault == "superseded-view"
            and self.restarted
            and expected_receipt_root is not None
            and transition_id == "transition:currentness-first:output"
        ):
            observation = cast(Any, view.position_observation)
            forged = _Proxy(observation, position=GovernanceCommitPositionV2.CURRENT)
            return cast(
                GovernanceCommitViewV2,
                _Proxy(view, position_observation=forged),
            )
        return view

    def _mutate_committed_view(
        self,
        view: GovernanceCommitViewV2,
        transition_id: str,
    ) -> GovernanceCommitViewV2:
        if (
            self.fault == "current-inclusion"
            and transition_id.endswith(":manifest")
            and "current-inclusion" not in self.done
        ):
            self.done.add("current-inclusion")
            return cast(
                GovernanceCommitViewV2,
                _Proxy(
                    view,
                    disposition=GovernanceCommitDispositionV2.INVALID,
                    committed_transition=None,
                    position_observation=None,
                ),
            )
        if (
            self.fault == "shifted-transition"
            and transition_id.endswith(":manifest")
            and "shifted-transition" not in self.done
        ):
            self.done.add("shifted-transition")
            return cast(
                GovernanceCommitViewV2,
                _Proxy(
                    view,
                    committed_transition=self.transitions[
                        "baseline_evidence_qualified"
                    ],
                ),
            )
        if (
            self.fault == "trace-batch"
            and transition_id.endswith(":manifest")
            and "trace-batch" not in self.done
        ):
            self.done.add("trace-batch")
            transition = cast(Any, view.committed_transition)
            batch = transition.batch
            trace_batch = _Proxy(batch.trace_batch, events=())
            forged_batch = _Proxy(batch, trace_batch=trace_batch)
            forged_transition = _Proxy(transition, batch=forged_batch)
            return cast(
                GovernanceCommitViewV2,
                _Proxy(view, committed_transition=forged_transition),
            )
        if (
            self.fault == "trace-validation-root"
            and transition_id.endswith(":output")
            and "trace-validation-root" not in self.done
        ):
            self.done.add("trace-validation-root")
            transition = cast(Any, view.committed_transition)
            batch = transition.batch
            event = batch.trace_batch.events[0]
            bad_event = TraceEvent(
                event_type="",
                protocol_id=event.protocol_id,
                target=event.target,
                reason=event.reason,
                lineage={**event.lineage, "read_set_root": _ZERO_ROOT},
            )
            trace_batch = _Proxy(batch.trace_batch, events=(bad_event,))
            forged_batch = _Proxy(batch, trace_batch=trace_batch)
            forged_transition = _Proxy(transition, batch=forged_batch)
            return cast(
                GovernanceCommitViewV2,
                _Proxy(view, committed_transition=forged_transition),
            )
        if self.fault == "exact-retry" and transition_id.endswith(":permission"):
            count = self.view_counts.get(transition_id, 0) + 1
            self.view_counts[transition_id] = count
            if count == 2:
                return _finality_view(view)
        return view

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        attempt = self.delegate.atomic_commit_v2(batch)
        events = batch.trace_batch.events
        event_type = events[0].event_type
        self._record_commit_attempt(batch, attempt, event_type)
        if not self._targets(batch.scope_ref):
            return attempt
        return self._mutate_commit_attempt(batch, attempt, event_type)

    def _record_commit_attempt(
        self,
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
        event_type: str,
    ) -> None:
        if attempt.committed_transition is not None:
            self.transitions[event_type] = attempt.committed_transition
        if event_type == "baseline_action_permission_issued":
            self.permission_committed = True
        elif event_type == "baseline_output_committed":
            self.output_committed = True
            self.output_attempt = attempt
        elif event_type == "issuer_grant_revoked":
            self.issuer_revoked = True
        if "output-grant-activate" in batch.transition_id:
            self.output_grant_stream = batch.stream_ref

    def _mutate_commit_attempt(
        self,
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
        event_type: str,
    ) -> GovernanceCommitAttemptV2:
        if (
            self.fault == "grant-activation"
            and event_type == "issuer_grant_activated"
            and "grant-activation" not in self.done
        ):
            self.done.add("grant-activation")
            return _failed_attempt(batch)
        if self.fault == "signal-commit" and event_type == "signal_verified":
            return _failed_attempt(batch)
        if (
            self.fault
            in {
                "permission-commit",
                "currentness-initial",
                "issuer-initial",
            }
            and event_type == "baseline_action_permission_issued"
        ):
            return _failed_attempt(batch)
        if (
            self.fault == "terminal-result"
            and event_type == "baseline_output_committed"
        ):
            return _failed_attempt(batch, finality=True)
        if (
            self.fault == "successor-commit"
            and event_type == "baseline_action_permission_issued"
            and "currentness-successor" in batch.transition_id
        ):
            return _failed_attempt(batch)
        return attempt


class _AdversarialAdapterV2(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = "tests-adversarial-baseline-output-v2"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2

    def __init__(self, fault: str, *, target_label: str = "quorum") -> None:
        self.fault = fault
        self.target_scope = f"scope:baseline-output-v2:{target_label}"

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
        if self.fault == "noncanonical-domain" and scope_ref == self.target_scope:
            return cast(AuthorityDomainV2, object())
        return super().create_domain_v2(scope_ref)

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        if (
            self.fault == "nonconforming-store"
            and domains
            and domains[0].scope_ref == self.target_scope
        ):
            return cast(GovernanceStateStoreV2, object())
        delegate = super().create_store_v2(domains)
        return _AdversarialStoreV2(
            delegate,
            fault=self.fault,
            target_scope=self.target_scope,
        )

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = cast(_AdversarialStoreV2, store)
        if self.fault == "restart-store":
            return cast(GovernanceStateStoreV2, object())
        delegate = super().restart_store_v2(selected.delegate)
        return _AdversarialStoreV2(
            delegate,
            fault=self.fault,
            target_scope=self.target_scope,
            restarted=True,
        )


class _ExplodingMetadataAdapter(_AdversarialAdapterV2):
    @property
    def implementation_id(self) -> str:
        raise RuntimeError("metadata unavailable")


class _BlankImplementationAdapter(_AdversarialAdapterV2):
    implementation_id = ""


class _PaddedImplementationAdapter(_AdversarialAdapterV2):
    implementation_id = " padded-baseline-output-v2 "


def _run_fault(
    fault: str,
    diagnostic: str,
    *,
    target_label: str = "quorum",
) -> None:
    adapter = _AdversarialAdapterV2(fault, target_label=target_label)
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)

    result = run_governance_baseline_output_conformance_v2(adapter)

    assert result.ok is False
    assert diagnostic in result.detail, result.detail


def test_public_runner_totally_rejects_exploding_and_invalid_metadata() -> None:
    exploding = run_governance_baseline_output_conformance_v2(
        _ExplodingMetadataAdapter("none")
    )
    assert exploding.ok is False
    assert exploding.detail == "adapter_exception:RuntimeError:metadata unavailable"

    for adapter in (
        _BlankImplementationAdapter("none"),
        _PaddedImplementationAdapter("none"),
    ):
        result = run_governance_baseline_output_conformance_v2(adapter)
        assert result.ok is False
        assert result.detail == "adapter_implementation_id"


@pytest.mark.parametrize(
    ("fault", "exception_fragment"),
    [
        ("noncanonical-domain", "non-canonical authority domain"),
        ("nonconforming-store", "non-conforming StateStore v2"),
        ("grant-activation", "grant activation failed"),
        ("signal-commit", "verified signal commit failed"),
        ("verified-signal-state", "verified signal state is invalid"),
    ],
)
def test_public_runner_is_total_for_invalid_store_results(
    fault: str,
    exception_fragment: str,
) -> None:
    result = run_governance_baseline_output_conformance_v2(_AdversarialAdapterV2(fault))

    assert result.ok is False
    assert result.detail.startswith("adapter_exception:")
    assert exception_fragment in result.detail


@pytest.mark.parametrize(
    ("fault", "diagnostic"),
    [
        ("permission-commit", "quorum_permission_commit"),
        ("durable-permission", "quorum_durable_permission"),
        ("terminal-result", "quorum_terminal_result"),
        ("permission-separation", "permission_session_separation"),
        ("exact-retry", "quorum_exact_retry"),
        ("durable-schema", "quorum_durable_state_schemas"),
        ("durable-links", "quorum_durable_authority_links"),
        ("evidence-container", "quorum_durable_verified_evidence"),
        ("evidence-record", "quorum_durable_verified_evidence"),
        ("evidence-binding", "quorum_durable_verified_evidence"),
        ("evidence-receipt", "quorum_durable_verified_evidence"),
        ("stop-closure", "quorum_durable_stop_closure"),
    ],
)
def test_public_matrix_diagnoses_cas_and_durable_state_fabrication(
    fault: str,
    diagnostic: str,
) -> None:
    _run_fault(fault, diagnostic)


@pytest.mark.parametrize(
    ("fault", "diagnostics"),
    [
        (
            "current-inclusion",
            ("quorum_manifest_current_inclusion", "quorum_complete_trace_path"),
        ),
        (
            "shifted-transition",
            (
                "quorum_manifest_read_set",
                "quorum_manifest_trace_lineage",
                "quorum_complete_trace_path",
            ),
        ),
        (
            "trace-batch",
            ("quorum_manifest_trace_batch", "quorum_complete_trace_path"),
        ),
        (
            "trace-validation-root",
            (
                "quorum_output_trace_validation",
                "quorum_complete_trace_path",
            ),
        ),
        (
            "terminal-attempt-toctou",
            (
                "quorum_terminal_read_set_trace_root",
                "quorum_exact_retry",
            ),
        ),
    ],
)
def test_public_matrix_diagnoses_commit_view_and_trace_fabrication(
    fault: str,
    diagnostics: tuple[str, ...],
) -> None:
    adapter = _AdversarialAdapterV2(fault)

    result = run_governance_baseline_output_conformance_v2(adapter)

    assert result.ok is False
    for diagnostic in diagnostics:
        assert diagnostic in result.detail, result.detail


@pytest.mark.parametrize(
    "target_label",
    [
        "binding-candidate_ref",
        "binding-source_ref",
        "binding-provenance_ref",
    ],
)
def test_public_matrix_rejects_binding_failures_that_publish_state(
    target_label: str,
) -> None:
    field_name = target_label.removeprefix("binding-")
    _run_fault(
        "binding-head",
        f"verified_signal_{field_name}_substitution",
        target_label=target_label,
    )


@pytest.mark.parametrize(
    "target_label",
    [
        "missing-qualify-evidence",
        "missing-resolve-stop",
        "missing-evaluate-quorum",
    ],
)
def test_public_matrix_rejects_operation_denials_that_publish_state(
    target_label: str,
) -> None:
    _run_fault(
        "operation-head",
        f"permission_operation_{target_label}",
        target_label=target_label,
    )


@pytest.mark.parametrize(
    ("fault", "diagnostic"),
    [
        ("currentness-initial", "currentness_initial_commit"),
        ("restart-store", "currentness_restart_store"),
        ("restart-recovery", "currentness_restart_recovery"),
        ("restart-exact-retry", "currentness_restart_exact_retry"),
        ("successor-commit", "currentness_successor_commit"),
        ("superseded-view", "currentness_superseded_denial"),
    ],
)
def test_public_matrix_diagnoses_restart_and_currentness_fabrication(
    fault: str,
    diagnostic: str,
) -> None:
    _run_fault(fault, diagnostic, target_label="currentness")


@pytest.mark.parametrize(
    ("fault", "diagnostic"),
    [
        ("issuer-initial", "issuer_revocation_initial_commit"),
        ("issuer-history", "issuer_revocation_historical_delivery"),
    ],
)
def test_public_matrix_diagnoses_revocation_history_fabrication(
    fault: str,
    diagnostic: str,
) -> None:
    _run_fault(fault, diagnostic, target_label="issuer-revocation")
