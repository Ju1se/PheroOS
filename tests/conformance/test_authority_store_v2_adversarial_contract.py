from __future__ import annotations

from collections.abc import Mapping, Sequence
from threading import Event, Lock
from typing import Any, cast

import pytest

from pheroos.conformance import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION,
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
    GovernanceStateStoreConformanceAdapter,
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapter,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    run_governance_state_store_conformance,
    run_governance_state_store_conformance_v2,
)
from pheroos.governance import (
    InMemoryGovernanceStateStore,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    GovernanceStateStore,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import (
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


_ZERO_ROOT = "sha256:" + ("0" * 64)


def _clone_head(head: GovernanceHeadV2) -> GovernanceHeadV2:
    return GovernanceHeadV2.from_dict(head.to_dict())


def _clone_attempt(attempt: GovernanceCommitAttemptV2) -> GovernanceCommitAttemptV2:
    return GovernanceCommitAttemptV2.from_dict(attempt.to_dict())


def _clone_view(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
    return GovernanceCommitViewV2.from_dict(view.to_dict())


class _AdversarialStoreV2:
    """Public ABI wrapper that fabricates exactly one externally visible fact."""

    def __init__(
        self,
        delegate: GovernanceStateStoreV2,
        domain_factory: ReferenceGovernanceStateStoreConformanceAdapterV2,
        fault: str,
        *,
        restarted: bool = False,
    ) -> None:
        self.delegate = delegate
        self.domain_factory = domain_factory
        self.fault = fault
        self.restarted = restarted
        self.commit_calls: dict[tuple[str, str], int] = {}
        self.committed_ids: set[tuple[str, str]] = set()
        self.returned_attempts: dict[str, GovernanceCommitAttemptV2] = {}
        self.lock = Lock()
        self.ordinary_race_committed = Event()

    @property
    def state_store_version(self) -> str:
        if self.fault == "store_version":
            return "pheroos-governance-state-store-v999"
        return self.delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if self.fault == "unknown_reads" and scope_ref.endswith(":unknown"):
            domain = self.domain_factory.create_domain_v2(scope_ref)
            return GovernanceHeadV2.genesis(domain, stream_ref)
        try:
            head = self.delegate.load_head_v2(scope_ref, stream_ref)
        except (KeyError, ValueError) as exc:
            if self.fault == "unknown_read_exception" and scope_ref.endswith(
                ":unknown"
            ):
                raise TypeError("fabricated reader failure") from exc
            raise
        should_advance = (
            (
                self.fault == "fresh_genesis"
                and scope_ref.endswith(":fresh")
                and stream_ref == "authority:fresh"
            )
            or (
                self.fault == "identity_conflict_publish"
                and scope_ref.endswith(":identity")
                and stream_ref == "authority:alternate"
                and (scope_ref, "transition:first") in self.committed_ids
            )
            or (
                self.fault == "stale_read_publish"
                and scope_ref.endswith(":multi-read")
                and stream_ref == "authority:alpha"
                and (scope_ref, "transition:stale-multi-read") in self.committed_ids
            )
            or (
                self.fault == "failure_head_publish"
                and ":failure:" in scope_ref
                and stream_ref == "authority:failure"
                and any(item[0] == scope_ref for item in self.committed_ids)
            )
        )
        if should_advance and head.revision == 0:
            hostile = _clone_head(head)
            object.__setattr__(hostile, "revision", 1)
            return hostile
        if (
            self.restarted
            and self.fault in {"restart_projection", "authenticated_restart"}
            and (
                (scope_ref.endswith(":restart") and stream_ref == "authority:alpha")
                or (
                    scope_ref.endswith(":restart-authenticated")
                    and stream_ref == "authority:authenticated"
                )
            )
        ):
            hostile = _clone_head(head)
            object.__setattr__(hostile, "head_root", _ZERO_ROOT)
            return hostile
        return head

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if self.fault == "unknown_reads" and scope_ref.endswith(":unknown"):
            return {}
        try:
            state = self.delegate.load_state_v2(scope_ref, stream_ref)
        except (KeyError, ValueError) as exc:
            if self.fault == "unknown_read_exception" and scope_ref.endswith(
                ":unknown"
            ):
                raise TypeError("fabricated reader failure") from exc
            raise
        if (
            self.fault == "fresh_genesis"
            and scope_ref.endswith(":fresh")
            and stream_ref == "authority:fresh"
        ):
            return {"forged": True}
        if (
            self.restarted
            and self.fault == "restart_projection"
            and scope_ref.endswith(":restart")
            and stream_ref == "authority:zeta"
        ):
            return {**state, "forged": True}
        return state

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if self.fault == "unknown_reads" and scope_ref.endswith(":unknown"):
            return cast(GovernanceCommitViewV2, object())
        try:
            view = self.delegate.load_commit_view_v2(
                scope_ref,
                stream_ref,
                transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        except (KeyError, ValueError) as exc:
            if self.fault == "unknown_read_exception" and scope_ref.endswith(
                ":unknown"
            ):
                raise TypeError("fabricated reader failure") from exc
            raise
        if (
            self.fault == "sealed_missing_transition"
            and scope_ref.endswith(":seal")
            and transition_id == "transition:authority:alpha"
        ):
            first = self.returned_attempts[transition_id]
            object.__setattr__(first, "committed_transition", None)
        if self.fault == "total_view_observation" and (
            transition_id == "transition:absent"
            or scope_ref.endswith(":view-unavailable")
        ):
            hostile = _clone_view(view)
            object.__setattr__(hostile, "observed_revision", 1)
            object.__setattr__(hostile, "observed_head_root", None)
            return hostile
        if (
            self.fault == "sealed_history"
            and scope_ref.endswith(":seal")
            and transition_id == "transition:authority:alpha"
        ):
            hostile = _clone_view(view)
            assert hostile.position_observation is not None
            object.__setattr__(
                hostile.position_observation,
                "seal_root",
                _ZERO_ROOT,
            )
            return hostile
        if (
            self.restarted
            and self.fault == "restart_projection"
            and scope_ref.endswith(":restart")
            and transition_id == "transition:order:1"
        ):
            hostile = _clone_view(view)
            object.__setattr__(hostile, "observed_revision", 0)
            return hostile
        return view

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            self.fault == "seal_race_ordinary"
            and batch.scope_ref.endswith(":seal-race")
            and batch.transition_id == "transition:race-seal"
        ):
            assert self.ordinary_race_committed.wait(timeout=2)
        attempt = self.delegate.atomic_commit_v2(batch)
        key = (batch.scope_ref, batch.transition_id)
        with self.lock:
            call = self.commit_calls.get(key, 0) + 1
            self.commit_calls[key] = call
            self.committed_ids.add(key)
            self.returned_attempts[batch.transition_id] = attempt
        if (
            self.fault == "seal_race_ordinary"
            and batch.scope_ref.endswith(":seal-race")
            and batch.transition_id == "transition:race-ordinary"
        ):
            self.ordinary_race_committed.set()

        attempt = self._mutate_identity_attempt(batch, attempt, call)
        attempt = self._mutate_concurrency_attempt(batch, attempt, call)
        return self._mutate_seal_or_restart_attempt(batch, attempt, call)

    def _mutate_identity_attempt(
        self,
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
        call: int,
    ) -> GovernanceCommitAttemptV2:
        if (
            self.fault == "identity_retry"
            and batch.scope_ref.endswith(":identity")
            and batch.transition_id == "transition:first"
            and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            hostile = _clone_attempt(attempt)
            if call == 2:
                assert hostile.committed_transition is not None
                object.__setattr__(
                    hostile.committed_transition.receipt,
                    "receipt_root",
                    _ZERO_ROOT,
                )
            elif call >= 3:
                assert hostile.position_observation is not None
                object.__setattr__(
                    hostile.position_observation,
                    "position",
                    GovernanceCommitPositionV2.CURRENT,
                )
            return hostile
        if (
            self.fault == "identity_attempt_shape"
            and batch.scope_ref.endswith(":identity")
            and batch.transition_id == "transition:first"
            and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            hostile = _clone_attempt(attempt)
            if call == 1:
                object.__setattr__(hostile, "position_observation", None)
            elif call == 2:
                object.__setattr__(hostile, "committed_transition", None)
            return hostile
        return attempt

    def _mutate_concurrency_attempt(
        self,
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
        call: int,
    ) -> GovernanceCommitAttemptV2:
        if (
            self.fault == "concurrency_results"
            and batch.scope_ref.endswith(":concurrent-same")
            and call == 2
        ):
            hostile = _clone_attempt(attempt)
            object.__setattr__(
                hostile,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            assert hostile.committed_transition is not None
            object.__setattr__(
                hostile.committed_transition.receipt,
                "receipt_root",
                _ZERO_ROOT,
            )
            return hostile
        if (
            self.fault == "concurrency_results"
            and batch.scope_ref.endswith(":concurrent-conflict")
            and attempt.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
        ):
            hostile = _clone_attempt(attempt)
            object.__setattr__(
                hostile,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
            return hostile
        return attempt

    def _mutate_seal_or_restart_attempt(
        self,
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
        call: int,
    ) -> GovernanceCommitAttemptV2:
        if (
            self.fault == "seal_union"
            and batch.scope_ref.endswith(":seal")
            and batch.transition_id == "transition:seal"
            and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            object.__setattr__(batch, "seal", None)
        if (
            self.fault == "sealed_history"
            and batch.scope_ref.endswith(":seal")
            and batch.transition_id == "transition:authority:alpha"
            and call >= 2
        ):
            hostile = _clone_attempt(attempt)
            assert hostile.committed_transition is not None
            object.__setattr__(
                hostile.committed_transition.receipt,
                "receipt_root",
                _ZERO_ROOT,
            )
            return hostile
        if (
            self.fault == "stream_bound"
            and batch.scope_ref.endswith(":stream-bound")
            and batch.transition_id == "transition:bounded:005"
        ):
            hostile = _clone_attempt(attempt)
            object.__setattr__(
                hostile,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            return hostile
        if (
            self.fault == "seal_race"
            and batch.scope_ref.endswith(":seal-race")
            and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            hostile = _clone_attempt(attempt)
            object.__setattr__(
                hostile,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            return hostile
        if (
            self.restarted
            and self.fault == "authenticated_restart"
            and batch.scope_ref.endswith(":restart-authenticated")
            and batch.transition_id == "transition:authenticated"
        ):
            hostile = _clone_attempt(attempt)
            assert hostile.committed_transition is not None
            object.__setattr__(
                hostile.committed_transition.receipt,
                "receipt_root",
                _ZERO_ROOT,
            )
            return hostile
        if (
            self.restarted
            and self.fault == "restart_retry_receipt"
            and batch.scope_ref.endswith(":restart")
            and batch.transition_id in {"transition:order:1", "transition:order:4-seal"}
        ):
            hostile = _clone_attempt(attempt)
            assert hostile.committed_transition is not None
            object.__setattr__(
                hostile.committed_transition.receipt,
                "receipt_root",
                _ZERO_ROOT,
            )
            return hostile
        return attempt


class _AdversarialAdapterV2:
    implementation_id = "public-adversarial-governance-state-store-v2"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2

    def __init__(self, fault: str) -> None:
        self.fault = fault
        self.reference = ReferenceGovernanceStateStoreConformanceAdapterV2()
        self.observation_calls: dict[str, int] = {}
        self.lock = Lock()

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
        selected = (
            "scope:conformance:wrong-domain"
            if self.fault == "domain_factory" and scope_ref.endswith(":fresh")
            else scope_ref
        )
        return self.reference.create_domain_v2(selected)

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        if self.fault == "store_protocol":
            return cast(GovernanceStateStoreV2, object())
        return _AdversarialStoreV2(
            self.reference.create_store_v2(domains),
            self.reference,
            self.fault,
        )

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        if self.fault == "restart_protocol":
            return cast(GovernanceStateStoreV2, object())
        selected = cast(_AdversarialStoreV2, store)
        return _AdversarialStoreV2(
            self.reference.restart_store_v2(selected.delegate),
            self.reference,
            self.fault,
            restarted=True,
        )

    def create_failure_injected_store_v2(
        self,
        stage: str,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        return _AdversarialStoreV2(
            self.reference.create_failure_injected_store_v2(stage, domains),
            self.reference,
            self.fault,
        )

    def observe_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
    ) -> Mapping[str, object]:
        selected = cast(_AdversarialStoreV2, store)
        observed = dict(self.reference.observe_store_v2(selected.delegate, scope_ref))
        with self.lock:
            call = self.observation_calls.get(scope_ref, 0) + 1
            self.observation_calls[scope_ref] = call
        observed = self._mutate_initial_observation(observed, scope_ref)
        return self._mutate_later_observation(observed, scope_ref, call)

    def _mutate_initial_observation(
        self,
        observed: dict[str, object],
        scope_ref: str,
    ) -> dict[str, object]:
        if self.fault.startswith("observation_") and scope_ref.endswith(":fresh"):
            if self.fault == "observation_shape":
                return {"heads": 0}
            if self.fault == "observation_count":
                observed["heads"] = True
            elif self.fault == "observation_order":
                observed["commit_order"] = []
            elif self.fault == "observation_fingerprint":
                observed["image_fingerprint"] = "not-a-root"
            elif self.fault == "observation_bytes":
                observed["image_bytes"] = b"{}"
            elif self.fault == "observation_mismatch":
                observed["image_fingerprint"] = _ZERO_ROOT
        return observed

    def _mutate_later_observation(
        self,
        observed: dict[str, object],
        scope_ref: str,
        call: int,
    ) -> dict[str, object]:
        if (
            self.fault == "unknown_observation"
            and scope_ref.endswith(":unknown")
            and call >= 2
        ):
            observed["heads"] = cast(int, observed["heads"]) + 1
        if (
            self.fault == "stale_read_publish"
            and scope_ref.endswith(":multi-read")
            and call >= 2
        ):
            observed["states"] = cast(int, observed["states"]) + 1
        if (
            self.fault == "failure_head_publish"
            and ":failure:" in scope_ref
            and call >= 2
        ):
            observed["heads"] = cast(int, observed["heads"]) + 1
        if (
            self.fault == "restart_projection"
            and scope_ref.endswith(":restart")
            and call >= 2
        ):
            observed["states"] = cast(int, observed["states"]) + 1
        if (
            self.fault == "tamper_retry_observation"
            and scope_ref.endswith(":tamper:batch_payload")
            and call == 3
        ):
            observed["heads"] = cast(int, observed["heads"]) + 1
        return observed

    def tamper_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None:
        if self.fault == "missing_tamper":
            return
        selected = cast(_AdversarialStoreV2, store)
        self.reference.tamper_store_v2(
            selected.delegate,
            scope_ref,
            transition_id,
            case,
        )


def _run_fault(fault: str) -> str:
    adapter = _AdversarialAdapterV2(fault)
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = run_governance_state_store_conformance_v2(adapter)
    assert result.ok is False
    return result.detail


def test_reference_v2_store_passes_the_public_matrix() -> None:
    result = run_governance_state_store_conformance_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2()
    )

    assert result.ok is True, result.detail
    assert result.detail == ""


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("domain_factory", "domain_factory"),
        ("store_protocol", "store_protocol"),
        ("store_version", "store_version"),
        ("fresh_genesis", "fresh_genesis"),
        ("unknown_reads", "unknown_scope_head_read"),
        ("unknown_read_exception", "unknown_scope_head_read:TypeError"),
        ("unknown_observation", "unknown_scope_partial_publish"),
        ("identity_retry", "exact_retry_receipt"),
        ("identity_attempt_shape", "first_commit"),
        ("identity_conflict_publish", "cross_stream_transition_conflict_published"),
        ("stale_read_publish", "multi_read_partial_publish"),
        ("concurrency_results", "concurrent_same_disposition"),
        ("failure_head_publish", "failure_partial_publish:before_validation"),
        ("total_view_observation", "view_invalid_observed_head_pair"),
        ("seal_union", "seal_batch_union"),
        ("sealed_history", "sealed_history_root"),
        ("sealed_missing_transition", "sealed_exact_retry_fixture"),
        ("stream_bound", "stream_bound_setup:5"),
        ("seal_race", "seal_race_no_winner"),
        ("restart_protocol", "restart_store_protocol"),
        ("restart_projection", "restart_observation"),
        ("restart_retry_receipt", "restart_seal_retry_receipt"),
        ("authenticated_restart", "authenticated_restart_head"),
        ("tamper_retry_observation", "tamper_retry_partial_publish:batch_payload"),
        ("missing_tamper", "tamper_fingerprint_unchanged:batch_payload"),
    ),
)
def test_v2_matrix_rejects_publicly_observable_authority_forgery(
    fault: str,
    expected: str,
) -> None:
    detail = _run_fault(fault)

    assert expected in detail


def test_v2_matrix_accepts_deterministic_ordinary_first_seal_race() -> None:
    result = run_governance_state_store_conformance_v2(
        _AdversarialAdapterV2("seal_race_ordinary")
    )

    assert result.ok is True, result.detail


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("observation_shape", "observation_shape:fresh"),
        ("observation_count", "observation_count:fresh:heads"),
        ("observation_order", "observation_order:fresh"),
        ("observation_fingerprint", "observation_fingerprint:fresh"),
        ("observation_bytes", "observation_image_bytes:fresh"),
        ("observation_mismatch", "observation_fingerprint_mismatch:fresh"),
    ),
)
def test_v2_matrix_rejects_fabricated_instrumentation(
    fault: str,
    expected: str,
) -> None:
    detail = _run_fault(fault)

    assert expected in detail


@pytest.mark.parametrize("implementation_id", (None, "", " padded ", True))
def test_v2_matrix_rejects_noncanonical_adapter_identity(
    implementation_id: object,
) -> None:
    class InvalidIdentityAdapter(_AdversarialAdapterV2):
        pass

    adapter = InvalidIdentityAdapter("none")
    adapter.implementation_id = cast(str, implementation_id)
    result = run_governance_state_store_conformance_v2(adapter)

    assert result.ok is False
    assert result.detail == "adapter_implementation_id"


def test_v2_matrix_is_total_when_adapter_metadata_or_body_raises() -> None:
    class ExplodingMetadata:
        @property
        def implementation_id(self) -> str:
            raise RuntimeError("metadata unavailable")

        conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2

        def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
            raise AssertionError(scope_ref)

        def create_store_v2(
            self,
            domains: Sequence[AuthorityDomainV2],
        ) -> GovernanceStateStoreV2:
            raise AssertionError(domains)

        def restart_store_v2(
            self,
            store: GovernanceStateStoreV2,
        ) -> GovernanceStateStoreV2:
            raise AssertionError(store)

        def create_failure_injected_store_v2(
            self,
            stage: str,
            domains: Sequence[AuthorityDomainV2],
        ) -> GovernanceStateStoreV2:
            raise AssertionError((stage, domains))

        def observe_store_v2(
            self,
            store: GovernanceStateStoreV2,
            scope_ref: str,
        ) -> Mapping[str, object]:
            raise AssertionError((store, scope_ref))

        def tamper_store_v2(
            self,
            store: GovernanceStateStoreV2,
            scope_ref: str,
            transition_id: str,
            case: str,
        ) -> None:
            raise AssertionError((store, scope_ref, transition_id, case))

    metadata = run_governance_state_store_conformance_v2(
        cast(GovernanceStateStoreConformanceAdapterV2, ExplodingMetadata())
    )
    assert metadata.ok is False
    assert metadata.detail == "adapter_exception:RuntimeError:metadata unavailable"

    class ExplodingBody(_AdversarialAdapterV2):
        implementation_id = "exploding-public-adapter-v2"

        def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
            raise OSError(f"domain unavailable:{scope_ref}")

    body = run_governance_state_store_conformance_v2(ExplodingBody("none"))
    assert body.ok is False
    assert body.detail.startswith("adapter_exception:OSError:domain unavailable:")


def _public_transition_batch(
    adapter: ReferenceGovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
) -> GovernanceCommitBatchV2:
    domain = adapter.create_domain_v2(scope_ref)
    head = store.load_head_v2(scope_ref, stream_ref)
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                stream_ref=stream_ref,
                expected_revision=head.revision,
                expected_root=head.head_root,
            ),
        )
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_revision=head.revision,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records={"value": 1},
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        events=(
            TraceEvent(
                event_type="ext.pheroos.authority_store_v2_adversarial",
                protocol_id="protocol:authority-store-v2-adversarial",
                target=stream_ref,
                reason="exercise the public conformance instrumentation boundary",
                lineage={
                    "scope_ref": scope_ref,
                    "stream_ref": stream_ref,
                    "transition_id": transition_id,
                },
            ),
        ),
    )
    return GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        kind="transition",
        read_set=read_set,
        trace_batch=trace_batch,
        transition=transition,
    )


def test_public_unavailable_view_store_preserves_other_reader_surfaces() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    scope_ref = "scope:conformance:adversarial-view-outage"
    domain = adapter.create_domain_v2(scope_ref)
    store = adapter.create_failure_injected_store_v2(
        GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
        (domain,),
    )

    assert store.state_store_version == GOVERNANCE_STATE_STORE_VERSION_V2
    assert store.load_state_v2(scope_ref, "authority:outage") == {}


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("seal_payload", "seal tamper requires a seal transition"),
        ("seal_root", "seal tamper requires a seal transition"),
        ("cross_stream_order", "cross-stream order tamper requires a predecessor"),
    ),
)
def test_public_tamper_instrumentation_rejects_inapplicable_case(
    case: str,
    message: str,
) -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    scope_ref = f"scope:conformance:inapplicable-tamper:{case}"
    domain = adapter.create_domain_v2(scope_ref)
    store = adapter.create_store_v2((domain,))
    batch = _public_transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:tamper",
        f"transition:inapplicable:{case}",
    )
    attempt = store.atomic_commit_v2(batch)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    with pytest.raises(ValueError, match=message):
        adapter.tamper_store_v2(
            store,
            scope_ref,
            batch.transition_id,
            case,
        )


class _AdversarialLegacyStore:
    """Legacy public Store wrapper used to prove the v1 matrix is fail-closed."""

    def __init__(
        self,
        delegate: GovernanceStateStore,
        fault: str,
        *,
        restored: bool = False,
    ) -> None:
        self.delegate = delegate
        self.fault = fault
        self.restored = restored
        self.lock = Lock()
        self.atomic_calls: dict[tuple[str, str], int] = {}
        self.claim_calls: dict[tuple[str, str], int] = {}
        self.ledger_scope: str | None = None
        self.other_scope: str | None = None
        self.retry_scope: str | None = None
        self.conflict_scope: str | None = None
        self.stale_attempted = False
        self.retired_scopes: set[str] = set()
        self.receipts: dict[tuple[str, str], GovernanceCommitReceipt] = {}

    def load_head(self, scope_ref: str, stream: str) -> GovernanceHead:
        if self.fault == "opaque_scope" and scope_ref == "tenant-or-run-identifier":
            return cast(GovernanceHead, object())
        try:
            head = self.delegate.load_head(scope_ref, stream)
        except GovernanceError:
            if self.fault == "retirement_projection" and self.restored:
                return cast(GovernanceHead, object())
            raise
        if (
            (
                self.fault == "commit_contract"
                and scope_ref == self.ledger_scope
                and self.stale_attempted
            )
            or (self.fault == "retry_divergence" and scope_ref == self.retry_scope)
            or (
                self.fault == "conflict_divergence" and scope_ref == self.conflict_scope
            )
        ):
            hostile = GovernanceHead.from_dict(head.to_dict())
            object.__setattr__(hostile, "revision", head.revision + 1)
            return hostile
        if (
            self.fault == "checkpoint_projection"
            and self.restored
            and head.revision == 1
        ):
            hostile = GovernanceHead.from_dict(head.to_dict())
            object.__setattr__(hostile, "revision", 2)
            return hostile
        return head

    def load_state(self, scope_ref: str, stream: str) -> Mapping[str, Any]:
        state = self.delegate.load_state(scope_ref, stream)
        if (
            self.fault == "cross_scope" and scope_ref == self.ledger_scope and state
        ) or (
            self.fault == "retirement_projection"
            and (scope_ref == self.other_scope or (self.restored and bool(state)))
        ):
            return {"state": {"value": 999}}
        return state

    def trace_records(
        self,
        scope_ref: str,
        stream: str,
    ) -> tuple[Mapping[str, Any], ...]:
        records = self.delegate.trace_records(scope_ref, stream)
        if (
            (
                self.fault == "commit_contract"
                and scope_ref == self.ledger_scope
                and self.stale_attempted
            )
            or (
                self.fault == "checkpoint_projection"
                and self.restored
                and bool(records)
            )
            or (
                self.fault == "retry_divergence"
                and scope_ref == self.retry_scope
                and bool(records)
            )
            or (
                self.fault == "conflict_divergence"
                and scope_ref == self.conflict_scope
                and bool(records)
            )
        ):
            return (*records, records[0])
        return records

    def load_receipt(
        self,
        scope_ref: str,
        transition_id: str,
    ) -> GovernanceCommitReceipt | None:
        receipt = self.delegate.load_receipt(scope_ref, transition_id)
        if (
            self.fault == "retry_divergence"
            and scope_ref == self.retry_scope
            and receipt is not None
        ):
            return None
        return receipt

    def claim_identity(
        self,
        scope_ref: str,
        identity_id: str,
        body: Mapping[str, Any],
    ) -> str:
        key = (scope_ref, identity_id)
        with self.lock:
            call = self.claim_calls.get(key, 0) + 1
            self.claim_calls[key] = call
        try:
            root = self.delegate.claim_identity(scope_ref, identity_id, body)
        except GovernanceError:
            if self.fault == "commit_contract":
                return "sha256:" + ("f" * 64)
            raise
        if self.fault == "commit_contract" and call >= 2:
            return "sha256:" + ("e" * 64)
        return root

    def compare_and_advance(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt:
        return self.atomic_commit(batch)

    def atomic_commit(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt:
        transition = batch.transition
        scope_ref = transition.domain.scope_ref
        transition_id = transition.transition_id
        self._record_scope_role(scope_ref, transition_id)
        key = (scope_ref, transition_id)
        with self.lock:
            call = self.atomic_calls.get(key, 0) + 1
            self.atomic_calls[key] = call
        if self.fault == "retry_exception" and transition_id == "transition:shared":
            raise OSError("fabricated retry persistence outage")
        try:
            receipt = self.delegate.atomic_commit(batch)
        except GovernanceError as exc:
            return self._translate_commit_error(exc, scope_ref, transition_id)
        self.receipts[key] = receipt
        return self._mutate_commit_receipt(receipt, scope_ref, transition_id, call)

    def _record_scope_role(self, scope_ref: str, transition_id: str) -> None:
        if transition_id == "transition:winner":
            if self.ledger_scope is None:
                self.ledger_scope = scope_ref
            elif scope_ref != self.ledger_scope:
                self.other_scope = scope_ref
        elif transition_id == "transition:shared":
            self.retry_scope = scope_ref
        elif transition_id.startswith("transition:"):
            self.conflict_scope = scope_ref

    def _translate_commit_error(
        self,
        error: GovernanceError,
        scope_ref: str,
        transition_id: str,
    ) -> GovernanceCommitReceipt:
        if self.fault == "commit_contract" and transition_id == "transition:stale":
            self.stale_attempted = True
            return self.receipts[(scope_ref, "transition:winner")]
        if (
            self.fault == "retirement_projection"
            and transition_id == "transition:winner"
            and scope_ref in self.retired_scopes
        ):
            return self.receipts[(scope_ref, transition_id)]
        if self.fault == "conflict_outcome":
            raise GovernanceError("fabricated non-CAS conflict") from error
        if self.fault == "conflict_unexpected":
            raise OSError("fabricated persistence outage") from error
        raise error

    def _mutate_commit_receipt(
        self,
        receipt: GovernanceCommitReceipt,
        scope_ref: str,
        transition_id: str,
        call: int,
    ) -> GovernanceCommitReceipt:
        if self.fault == "commit_contract" and scope_ref == self.ledger_scope:
            hostile = GovernanceCommitReceipt.from_dict(receipt.to_dict())
            object.__setattr__(hostile, "batch_root", _ZERO_ROOT)
            object.__setattr__(
                hostile,
                "receipt_root",
                "sha256:" + (("a" if call == 1 else "b") * 64),
            )
            return hostile
        if (
            self.fault == "retry_divergence"
            and transition_id == "transition:shared"
            and call >= 2
        ):
            hostile = GovernanceCommitReceipt.from_dict(receipt.to_dict())
            object.__setattr__(
                hostile,
                "receipt_root",
                "sha256:" + (f"{call % 10}" * 64),
            )
            return hostile
        return receipt

    def checkpoint(self, scope_ref: str) -> Mapping[str, Any]:
        checkpoint = self.delegate.checkpoint(scope_ref)
        if self.fault == "checkpoint_projection" and self.restored:
            return {**checkpoint, "forged": True}
        return checkpoint

    def rehydrate(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[GovernanceHead, ...]:
        return self.delegate.rehydrate(payload)

    def rehydrate_snapshot(self, payload: Mapping[str, Any]) -> None:
        self.delegate.rehydrate_snapshot(payload)

    def retire(self, scope_ref: str) -> str:
        tombstone = self.delegate.retire(scope_ref)
        self.retired_scopes.add(scope_ref)
        if self.fault == "retirement_projection" and scope_ref in self.retired_scopes:
            calls = sum(
                1
                for selected_scope, transition_id in self.atomic_calls
                if selected_scope == scope_ref and transition_id == "transition:winner"
            )
            if calls and scope_ref in self.retired_scopes:
                if not hasattr(self, "_retire_returned"):
                    self._retire_returned = True
                else:
                    return "sha256:" + ("d" * 64)
        return tombstone

    def snapshot(self) -> Mapping[str, Any]:
        snapshot = self.delegate.snapshot()
        if self.fault == "retirement_projection" and self.restored:
            return {**snapshot, "forged": True}
        return snapshot

    def fingerprint(self) -> str:
        fingerprint = self.delegate.fingerprint()
        if self.fault == "retirement_projection" and self.restored:
            return "sha256:" + ("c" * 64)
        return fingerprint


class _AdversarialLegacyAdapter(ReferenceGovernanceStateStoreConformanceAdapter):
    implementation_id = "public-adversarial-governance-state-store-v1"

    def __init__(self, fault: str) -> None:
        self.fault = fault
        self.create_calls = 0
        self.main_store: _AdversarialLegacyStore | None = None

    def create_store(self) -> GovernanceStateStore:
        self.create_calls += 1
        selected_fault = self.fault
        if self.fault in {
            "opaque_scope",
            "commit_contract",
            "cross_scope",
            "retirement_projection",
        }:
            selected_fault = self.fault if self.create_calls == 1 else "none"
        elif self.fault == "retry_exception":
            selected_fault = "retry_exception" if self.create_calls == 2 else "none"
        elif self.fault == "retry_divergence":
            selected_fault = "retry_divergence" if self.create_calls == 2 else "none"
        elif self.fault in {
            "conflict_outcome",
            "conflict_unexpected",
            "conflict_divergence",
        }:
            selected_fault = self.fault if self.create_calls == 3 else "none"
        store = _AdversarialLegacyStore(
            InMemoryGovernanceStateStore(),
            selected_fault,
        )
        if self.create_calls == 1:
            self.main_store = store
        return store

    def restore_checkpoint(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        restored = super().restore_checkpoint(payload)
        return _AdversarialLegacyStore(
            restored,
            "checkpoint_projection"
            if self.fault == "checkpoint_projection"
            else "none",
            restored=True,
        )

    def restore_snapshot(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        restored = super().restore_snapshot(payload)
        store = _AdversarialLegacyStore(
            restored,
            "retirement_projection"
            if self.fault == "retirement_projection"
            else "none",
            restored=True,
        )
        if self.main_store is not None:
            store.ledger_scope = self.main_store.ledger_scope
            store.other_scope = self.main_store.other_scope
        return store

    def create_failure_injected_store(
        self,
        stage: str,
    ) -> GovernanceStateStore:
        return super().create_failure_injected_store(stage)


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("opaque_scope", "opaque_scope_shape"),
        ("commit_contract", "receipt_binding"),
        ("cross_scope", "cross_scope_pollution"),
        ("checkpoint_projection", "checkpoint_rehydrate"),
        ("retirement_projection", "retire_retry"),
        ("retry_exception", "concurrent_retry_exception:OSError"),
        ("retry_divergence", "concurrent_retry_receipt_divergence"),
        ("conflict_outcome", "concurrent_conflict_outcome"),
        ("conflict_unexpected", "concurrent_conflict_outcome"),
        ("conflict_divergence", "concurrent_conflict_double_publish"),
    ),
)
def test_legacy_matrix_rejects_public_authority_forgery(
    fault: str,
    expected: str,
) -> None:
    adapter = _AdversarialLegacyAdapter(fault)
    result = run_governance_state_store_conformance(adapter)

    assert result.ok is False
    assert expected in result.detail


class _LegacyBadRestoreAdapter(ReferenceGovernanceStateStoreConformanceAdapter):
    implementation_id = "legacy-public-bad-restore"

    def __init__(self, fault: str) -> None:
        self.fault = fault
        self.create_calls = 0

    def create_store(self) -> GovernanceStateStore:
        self.create_calls += 1
        if self.fault == "store_protocol" and self.create_calls == 1:
            return cast(GovernanceStateStore, object())
        if self.fault == "concurrency_protocol" and self.create_calls >= 2:
            return cast(GovernanceStateStore, object())
        return InMemoryGovernanceStateStore()

    def restore_checkpoint(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        if self.fault == "checkpoint_protocol":
            return cast(GovernanceStateStore, object())
        return super().restore_checkpoint(payload)

    def restore_snapshot(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        if self.fault == "snapshot_protocol":
            return cast(GovernanceStateStore, object())
        return super().restore_snapshot(payload)

    def create_failure_injected_store(
        self,
        stage: str,
    ) -> GovernanceStateStore:
        if self.fault == "failure_protocol":
            return cast(GovernanceStateStore, object())
        return super().create_failure_injected_store(stage)


@pytest.mark.parametrize(
    ("fault", "expected"),
    (
        ("store_protocol", "store_protocol"),
        ("checkpoint_protocol", "checkpoint_store_protocol"),
        ("failure_protocol", "failure_store_protocol:after_state_prepare"),
        ("concurrency_protocol", "concurrent_retry_store_protocol"),
        ("snapshot_protocol", "snapshot_store_protocol"),
    ),
)
def test_legacy_matrix_rejects_public_protocol_breaks(
    fault: str,
    expected: str,
) -> None:
    adapter = _LegacyBadRestoreAdapter(fault)
    assert isinstance(adapter, GovernanceStateStoreConformanceAdapter)

    result = run_governance_state_store_conformance(adapter)

    assert result.ok is False
    assert expected in result.detail


@pytest.mark.parametrize("implementation_id", (None, "", " padded "))
def test_legacy_matrix_rejects_noncanonical_identity(
    implementation_id: object,
) -> None:
    adapter = _LegacyBadRestoreAdapter("none")
    adapter.implementation_id = cast(str, implementation_id)
    adapter.conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION

    result = run_governance_state_store_conformance(adapter)

    assert result.ok is False
    assert result.detail == "adapter_implementation_id"


def test_legacy_matrix_is_total_for_adapter_exception() -> None:
    class ExplodingLegacyAdapter(_LegacyBadRestoreAdapter):
        implementation_id = "exploding-legacy-public-adapter"

        def create_store(self) -> GovernanceStateStore:
            raise OSError("legacy backend unavailable")

    result = run_governance_state_store_conformance(ExplodingLegacyAdapter("none"))

    assert result.ok is False
    assert result.detail == "adapter_exception:OSError:legacy backend unavailable"


def test_imported_public_legacy_types_are_runtime_compatible() -> None:
    """Guard imports used by third-party adapters without touching private owners."""

    store = InMemoryGovernanceStateStore()
    assert isinstance(store, GovernanceStateStore)
    assert GovernanceHead.__module__ == "pheroos.governance.authority_domain"
    assert GovernanceCommitBatch.__module__ == "pheroos.governance.authority_domain"
    assert GovernanceCommitReceipt.__module__ == "pheroos.governance.authority_domain"
    assert GOVERNANCE_STATE_STORE_VERSION_V2 == ("pheroos-governance-state-store-v2")
