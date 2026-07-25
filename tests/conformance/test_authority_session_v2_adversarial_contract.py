from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

import pytest

from pheroos.conformance.checks.authority_session_v2_contract import (
    run_governance_authority_session_conformance_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol.authority_v2 import GovernanceAuthorityReadSetV2
from pheroos.trace import TraceEvent


class _AdversarialTraceBatch:
    def __init__(self, events: tuple[TraceEvent, ...]) -> None:
        self.events = events


class _AdversarialStore:
    """A structural public Store that corrupts only one declared observation."""

    def __init__(
        self,
        delegate: GovernanceStateStoreV2,
        fault: str,
        *,
        restarted: bool = False,
    ) -> None:
        self.delegate = delegate
        self.fault = fault
        self.restarted = restarted
        self.view_calls: dict[str, int] = {}
        self.committed_attempts: set[str] = set()
        self.active_states: dict[tuple[str, str], Mapping[str, Any]] = {}

    @property
    def state_store_version(self) -> str:
        return self.delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = self.delegate.load_head_v2(scope_ref, stream_ref)
        if (
            self.fault == "verified_signal_double_advance"
            and scope_ref.endswith(":local-vertical")
            and stream_ref.startswith("authority:verified-signal:")
            and head.revision == 1
        ):
            return replace(head, revision=2, head_root="")
        if (
            self.fault == "store_version_activation"
            and scope_ref.endswith(":store-version")
            and stream_ref.startswith("authority:issuer-grant:")
            and head.revision == 0
        ):
            hostile = GovernanceHeadV2.from_dict(head.to_dict())
            object.__setattr__(hostile, "revision", 1)
            return hostile
        mutation_faults = {
            "revoke_after_session_mutation": (
                ":revoke-race",
                "authority:verified-signal:",
            ),
            "lifecycle_seal_race_mutation": (
                ":seal-race",
                "authority:verified-signal:",
            ),
            "retirement_omitted_stream_mutation": (
                ":retirement",
                "authority:domain-lifecycle",
            ),
            "authenticated_failed_activation_mutation": (
                ":authenticated",
                "authority:issuer-grant:",
            ),
        }
        selected = mutation_faults.get(self.fault)
        if (
            selected is not None
            and scope_ref.endswith(selected[0])
            and stream_ref.startswith(selected[1])
            and head.revision == 0
            and (
                self.fault != "retirement_omitted_stream_mutation"
                or "transition:retirement:omitted" in self.committed_attempts
            )
        ):
            hostile = GovernanceHeadV2.from_dict(head.to_dict())
            object.__setattr__(hostile, "revision", 1)
            return hostile
        return head

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        state = self.delegate.load_state_v2(scope_ref, stream_ref)
        key = (scope_ref, stream_ref)
        if state.get("status") == "active":
            self.active_states[key] = state
        if (
            self.fault == "revoke_after_session"
            and scope_ref.endswith(":revoke-race")
            and stream_ref.startswith("authority:issuer-grant:")
            and state.get("status") == "revoked"
            and key in self.active_states
        ):
            return self.active_states[key]
        if (
            self.fault == "verified_signal_durable_state"
            and scope_ref.endswith(":local-vertical")
            and stream_ref.startswith("authority:verified-signal:")
            and state
        ):
            changed = dict(state)
            changed["status"] = "rejected"
            return changed
        if (
            self.fault == "verified_signal_restart_durability"
            and self.restarted
            and scope_ref.endswith(":local-vertical")
            and stream_ref.startswith("authority:verified-signal:")
            and state
        ):
            changed = dict(state)
            changed["status"] = "rejected"
            return changed
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
        self.view_calls[transition_id] = self.view_calls.get(transition_id, 0) + 1
        exact_retry_faults = {
            "activation_exact_retry": "transition:activate",
            "verified_signal_exact_retry": "transition:signal:one",
            "revocation_exact_retry": "transition:revoke-race:revoke",
            "retirement_exact_retry": "transition:retirement:complete",
        }
        selected = exact_retry_faults.get(self.fault)
        if (
            selected == transition_id
            and self.view_calls[transition_id] >= 2
            and (
                scope_ref.endswith(":local-vertical")
                or scope_ref.endswith(":revoke-race")
                or scope_ref.endswith(":retirement")
            )
        ):
            return cast(GovernanceCommitViewV2, object())
        if (
            self.fault == "authenticated_activation_retry_without_verifier"
            and scope_ref.endswith(":authenticated")
            and transition_id == "transition:authenticated:activate"
            and self.view_calls[transition_id] >= 2
        ):
            return cast(GovernanceCommitViewV2, object())
        retirement_view_faults = {
            "retirement_sealed_history",
            "retirement_seal_artifact",
            "retirement_session_read_set",
            "retirement_trace_seal_binding",
        }
        if (
            self.fault in retirement_view_faults
            and scope_ref.endswith(":retirement")
            and transition_id == "transition:retirement:complete"
            and self.view_calls[transition_id] >= 3
        ):
            hostile = GovernanceCommitViewV2.from_dict(view.to_dict())
            if self.fault == "retirement_sealed_history":
                assert hostile.position_observation is not None
                object.__setattr__(
                    hostile.position_observation,
                    "position",
                    GovernanceCommitPositionV2.CURRENT,
                )
            elif self.fault == "retirement_seal_artifact":
                object.__setattr__(hostile, "committed_transition", None)
            else:
                assert hostile.committed_transition is not None
                batch = hostile.committed_transition.batch
                if self.fault == "retirement_session_read_set":
                    object.__setattr__(
                        batch,
                        "read_set",
                        GovernanceAuthorityReadSetV2(
                            entries=batch.read_set.entries[:-1]
                        ),
                    )
                else:
                    event = batch.trace_batch.events[0]
                    lineage = dict(event.lineage)
                    lineage["seal_root"] = "sha256:" + ("0" * 64)
                    object.__setattr__(
                        batch,
                        "trace_batch",
                        _AdversarialTraceBatch(
                            (
                                TraceEvent(
                                    event_type=event.event_type,
                                    protocol_id=event.protocol_id,
                                    target=event.target,
                                    reason=event.reason,
                                    lineage=lineage,
                                ),
                            )
                        ),
                    )
            return hostile
        return view

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        attempt = self.delegate.atomic_commit_v2(batch)
        self.committed_attempts.add(batch.transition_id)
        label = batch.scope_ref.rsplit(":", 1)[-1]
        early_faults = {
            ("local_activation", "local-vertical", "transition:activate"),
            (
                "verified_signal_commit",
                "local-vertical",
                "transition:signal:one",
            ),
            ("expiry_setup", "expiry", "transition:expiry:activate"),
            (
                "immutable_read_activation",
                "immutable-read",
                "transition:immutable-read:activate",
            ),
            (
                "immutable_read_signal",
                "immutable-read",
                "transition:immutable-read:signal",
            ),
            (
                "store_version_setup",
                "store-version",
                "transition:store-version:activate",
            ),
            (
                "retirement_signal_setup",
                "retirement",
                "transition:retirement:signal",
            ),
            (
                "retirement_complete_streams",
                "retirement",
                "transition:retirement:complete",
            ),
            (
                "authenticated_activation",
                "authenticated",
                "transition:authenticated:activate",
            ),
            (
                "active_setup_activation",
                "handle-boundaries",
                "transition:handle-boundaries:activate",
            ),
        }
        if (self.fault, label, batch.transition_id) in early_faults:
            return cast(GovernanceCommitAttemptV2, object())
        if (
            self.fault == "store_version_recovery"
            and label == "store-version"
            and batch.transition_id == "transition:store-version:signal"
        ):
            return cast(GovernanceCommitAttemptV2, object())
        if (
            self.fault == "lifecycle_seal_race"
            and label == "seal-race"
            and batch.transition_id == "transition:seal-race:retire"
        ):
            return cast(GovernanceCommitAttemptV2, object())
        if (
            self.fault == "retirement_omitted_stream"
            and label == "retirement"
            and batch.transition_id == "transition:retirement:omitted"
        ):
            return cast(GovernanceCommitAttemptV2, object())

        if (
            self.fault
            in {
                "verified_signal_session_read_set",
                "verified_signal_trace_or_current_inclusion",
                "verified_signal_trace_validation",
            }
            and label == "local-vertical"
            and batch.transition_id == "transition:signal:one"
            and attempt.committed_transition is not None
        ):
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            assert detached.committed_transition is not None
            committed = detached.committed_transition
            if self.fault == "verified_signal_session_read_set":
                entries = committed.batch.read_set.entries
                object.__setattr__(
                    committed.batch,
                    "read_set",
                    GovernanceAuthorityReadSetV2(entries=entries[:-1]),
                )
            elif self.fault == "verified_signal_trace_or_current_inclusion":
                assert detached.position_observation is not None
                object.__setattr__(
                    detached.position_observation,
                    "position",
                    GovernanceCommitPositionV2.SEALED,
                )
            else:
                event = committed.batch.trace_batch.events[0]
                object.__setattr__(
                    committed.batch,
                    "trace_batch",
                    _AdversarialTraceBatch(
                        (
                            TraceEvent(
                                event_type=event.event_type,
                                protocol_id="",
                                target=event.target,
                                reason=event.reason,
                                lineage=event.lineage,
                            ),
                        )
                    ),
                )
            return detached
        return attempt


class _AdversarialAdapter:
    implementation_id = "authority-session-v2-adversarial"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2

    def __init__(self, fault: str) -> None:
        self.fault = fault
        self.delegate = ReferenceGovernanceStateStoreConformanceAdapterV2()

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
        if self.fault == "local_domain_type" and scope_ref.endswith(":local-vertical"):
            return cast(AuthorityDomainV2, object())
        if self.fault == "authenticated_domain_type" and scope_ref.endswith(
            ":authenticated"
        ):
            return cast(AuthorityDomainV2, object())
        return self.delegate.create_domain_v2(scope_ref)

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        scope_ref = domains[0].scope_ref
        if self.fault == "local_store_protocol" and scope_ref.endswith(
            ":local-vertical"
        ):
            return cast(GovernanceStateStoreV2, object())
        if self.fault == "authenticated_store_protocol" and scope_ref.endswith(
            ":authenticated"
        ):
            return cast(GovernanceStateStoreV2, object())
        return _AdversarialStore(
            self.delegate.create_store_v2(domains),
            self.fault,
        )

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        if self.fault == "verified_signal_restart_store_protocol":
            return cast(GovernanceStateStoreV2, object())
        assert isinstance(store, _AdversarialStore)
        restarted = self.delegate.restart_store_v2(store.delegate)
        return _AdversarialStore(restarted, self.fault, restarted=True)

    def create_failure_injected_store_v2(
        self,
        stage: str,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        return _AdversarialStore(
            self.delegate.create_failure_injected_store_v2(stage, domains),
            self.fault,
        )

    def observe_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
    ) -> Mapping[str, object]:
        assert isinstance(store, _AdversarialStore)
        return self.delegate.observe_store_v2(store.delegate, scope_ref)

    def tamper_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None:
        assert isinstance(store, _AdversarialStore)
        self.delegate.tamper_store_v2(
            store.delegate,
            scope_ref,
            transition_id,
            case,
        )


@pytest.mark.parametrize(
    ("fault", "diagnostic"),
    (
        ("local_activation", "local_activation"),
        ("activation_exact_retry", "activation_exact_retry"),
        ("verified_signal_commit", "verified_signal_commit"),
        ("verified_signal_exact_retry", "verified_signal_exact_retry"),
        ("verified_signal_double_advance", "verified_signal_double_advance"),
        (
            "verified_signal_session_read_set",
            "verified_signal_session_read_set",
        ),
        (
            "verified_signal_trace_or_current_inclusion",
            "verified_signal_trace_or_current_inclusion",
        ),
        (
            "verified_signal_trace_validation",
            "verified_signal_trace_validation",
        ),
        ("verified_signal_durable_state", "verified_signal_durable_state"),
        (
            "verified_signal_restart_store_protocol",
            "verified_signal_restart_store_protocol",
        ),
        (
            "verified_signal_restart_durability",
            "verified_signal_restart_durability",
        ),
        ("expiry_setup", "expiry_setup"),
        ("immutable_read_activation", "immutable_read_activation"),
        ("immutable_read_signal", "immutable_read_signal"),
        ("store_version_setup", "store_version_setup"),
        ("store_version_activation", "store_version_activation"),
        ("store_version_recovery", "store_version_recovery"),
        ("revocation_exact_retry", "revocation_exact_retry"),
        ("revoke_after_session", "revoke_after_session"),
        (
            "revoke_after_session_mutation",
            "revoke_after_session_mutation",
        ),
        ("lifecycle_seal_race", "lifecycle_seal_race"),
        (
            "lifecycle_seal_race_mutation",
            "lifecycle_seal_race_mutation",
        ),
        ("retirement_signal_setup", "retirement_signal_setup"),
        ("retirement_omitted_stream", "retirement_omitted_stream"),
        (
            "retirement_omitted_stream_mutation",
            "retirement_omitted_stream_mutation",
        ),
        ("retirement_complete_streams", "retirement_complete_streams"),
        ("retirement_exact_retry", "retirement_exact_retry"),
        ("retirement_sealed_history", "retirement_sealed_history"),
        ("retirement_seal_artifact", "retirement_seal_artifact"),
        ("retirement_session_read_set", "retirement_session_read_set"),
        ("retirement_trace_seal_binding", "retirement_trace_seal_binding"),
        ("authenticated_activation", "authenticated_activation"),
        (
            "authenticated_failed_activation_mutation",
            "authenticated_failed_activation_mutation",
        ),
        (
            "authenticated_activation_retry_without_verifier",
            "authenticated_activation_retry_without_verifier",
        ),
        ("active_setup_activation", "adapter_exception:ValueError:"),
    ),
)
def test_matrix_reports_each_public_store_fault(
    fault: str,
    diagnostic: str,
) -> None:
    adapter = _AdversarialAdapter(fault)
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)

    result = run_governance_authority_session_conformance_v2(adapter)

    assert result.ok is False
    assert any(
        item == diagnostic or item.startswith(diagnostic)
        for item in result.detail.split(", ")
    ), result.detail


def test_matrix_reports_noncanonical_public_adapter_products() -> None:
    cases = (
        ("local_domain_type", "adapter_exception:TypeError:"),
        ("local_store_protocol", "adapter_exception:TypeError:"),
        ("authenticated_domain_type", "adapter_exception:TypeError:"),
        ("authenticated_store_protocol", "authenticated_store_protocol"),
    )
    for fault, diagnostic in cases:
        result = run_governance_authority_session_conformance_v2(
            _AdversarialAdapter(fault)
        )
        assert result.ok is False
        assert diagnostic in result.detail


def test_matrix_rejects_invalid_and_exploding_adapter_identity() -> None:
    invalid = _AdversarialAdapter("none")
    invalid.implementation_id = ""
    result = run_governance_authority_session_conformance_v2(invalid)
    assert result.ok is False
    assert result.detail == "adapter_implementation_id"

    class ExplodingIdentity(_AdversarialAdapter):
        def __getattribute__(self, name: str) -> Any:
            if name == "implementation_id":
                raise RuntimeError("identity unavailable")
            return super().__getattribute__(name)

    exploding = run_governance_authority_session_conformance_v2(
        ExplodingIdentity("none")
    )
    assert exploding.ok is False
    assert exploding.detail.startswith("adapter_exception:RuntimeError:")
