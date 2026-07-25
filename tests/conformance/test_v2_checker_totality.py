from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.conformance.checks import (
    _commit_evidence_v2_context_support as evidence_context,
)
from pheroos.conformance.checks import (
    _commit_finality_v2_certificate_support as finality_certificate,
)
from pheroos.conformance.checks import (
    _commit_finality_v2_decision_support as finality_decision,
)
from pheroos.conformance.checks import (
    _commit_finality_v2_distributed_support as finality_distributed,
)
from pheroos.conformance.checks import (
    _commit_gate_v2_adversarial_support as gate_adversarial,
)
from pheroos.conformance.checks import (
    _commit_gate_v2_context_support as gate_context,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_finality_support as replay_finality,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_integrity_support as replay_integrity,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_race_support as replay_race,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_resource_support as replay_resource,
)
from pheroos.conformance.checks import (
    _distributed_v2_context_support as distributed_context,
)
from pheroos.conformance.checks import (
    _distributed_v2_decision_support as distributed_decision,
)
from pheroos.conformance.checks import (
    _distributed_v2_input_support as distributed_input,
)
from pheroos.conformance.checks import (
    _distributed_v2_vertical_support as distributed_vertical,
)
from pheroos.conformance.checks import (
    _hybrid_replay_v2_public_support as hybrid_public,
)
from pheroos.conformance.checks import (
    _hybrid_replay_v2_resource_support as hybrid_resource,
)
from pheroos.conformance.checks import (
    _risk_v2_context_support as risk_context,
)
from pheroos.conformance.checks import _risk_v2_core_support as risk_core
from pheroos.conformance.checks import _risk_v2_finality_support as risk_finality
from pheroos.conformance.checks import (
    _risk_v2_integrity_support as risk_integrity,
)
from pheroos.conformance.checks import _risk_v2_race_support as risk_race
from pheroos.conformance.checks import (
    _risk_v2_resource_support as risk_resource,
)
from pheroos.conformance.checks import (
    _support_v2_context_support as support_context,
)
from pheroos.conformance.checks import _support_v2_core_support as support_core
from pheroos.conformance.checks import (
    _support_v2_finality_race_support as support_finality,
)
from pheroos.conformance.checks import (
    _support_v2_integrity_support as support_integrity,
)
from pheroos.conformance.checks import (
    commit_certificate_v2_contract as certificate_checker,
)
from pheroos.conformance.checks import (
    commit_evidence_v2_contract as evidence_checker,
)
from pheroos.conformance.checks import (
    commit_finality_v2_contract as finality_checker,
)
from pheroos.conformance.checks import (
    commit_gate_v2_contract as gate_checker,
)
from pheroos.conformance.checks import (
    commit_replay_v2_contract as replay_checker,
)
from pheroos.conformance.checks import (
    distributed_commit_v2_contract as distributed_checker,
)
from pheroos.conformance.checks import (
    hybrid_replay_v2_contract as hybrid_checker,
)
from pheroos.conformance.checks import risk_v2_contract as risk_checker
from pheroos.conformance.checks import support_v2_contract as support_checker
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateIssuerAttestationVerifierV2,
)

StoreRunner = Callable[[Any], CheckResult]

STORE_RUNNERS: tuple[tuple[str, StoreRunner], ...] = (
    ("risk_v2_contract", risk_checker.run_governance_risk_conformance_v2),
    ("support_v2_contract", support_checker.run_governance_support_conformance_v2),
    (
        "commit_replay_v2_contract",
        replay_checker.run_governance_commit_replay_conformance_v2,
    ),
    ("commit_gate_v2_contract", gate_checker.run_governance_commit_gate_conformance_v2),
    (
        "commit_evidence_v2_contract",
        evidence_checker.run_governance_commit_evidence_conformance_v2,
    ),
    (
        "commit_finality_v2_contract",
        finality_checker.run_governance_commit_finality_conformance_v2,
    ),
    (
        "distributed_commit_v2_contract",
        distributed_checker.run_governance_distributed_commit_conformance_v2,
    ),
    (
        "hybrid_replay_v2_contract",
        hybrid_checker.run_governance_hybrid_replay_conformance_v2,
    ),
)


class _UnknownVersionStoreAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    conformance_version = "pheroos-governance-state-store-conformance-v999"


class _EmptyIdentityStoreAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = ""


class _ExplodingIdentityStoreAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    @property
    def implementation_id(self) -> str:
        raise LookupError("identity unavailable")


class _ExplodingExecutionStoreAdapter(
    ReferenceGovernanceStateStoreConformanceAdapterV2
):
    implementation_id = "exploding-v2-checker-adapter"

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
        raise RuntimeError(f"domain unavailable:{scope_ref}")


AttemptFault = Callable[
    [GovernanceCommitBatchV2, GovernanceCommitAttemptV2],
    GovernanceCommitAttemptV2,
]


class _AttemptFaultStore:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        fault: AttemptFault,
    ) -> None:
        self._store = store
        self._fault = fault

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self._store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        committed = self._store.atomic_commit_v2(batch)
        detached = GovernanceCommitAttemptV2.from_dict(committed.to_dict())
        return self._fault(batch, detached)


class _AttemptFaultAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = "test-boundary-fault-store-v2"

    def __init__(self, fault: AttemptFault) -> None:
        self._fault = fault

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        store = super().create_store_v2(domains)
        return cast(GovernanceStateStoreV2, _AttemptFaultStore(store, self._fault))

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = cast(_AttemptFaultStore, store)
        restarted = super().restart_store_v2(selected._store)
        return cast(GovernanceStateStoreV2, _AttemptFaultStore(restarted, self._fault))


ViewFault = Callable[
    [str, str, str, GovernanceCommitViewV2],
    GovernanceCommitViewV2,
]


class _ViewFaultStore:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        fault: ViewFault,
    ) -> None:
        self._store = store
        self._fault = fault

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        view = self._store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        detached = GovernanceCommitViewV2.from_dict(view.to_dict())
        return self._fault(scope_ref, stream_ref, transition_id, detached)

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        return self._store.atomic_commit_v2(batch)


class _ViewFaultAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = "test-boundary-view-fault-store-v2"

    def __init__(self, fault: ViewFault) -> None:
        self._fault = fault

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        store = super().create_store_v2(domains)
        return cast(GovernanceStateStoreV2, _ViewFaultStore(store, self._fault))

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = cast(_ViewFaultStore, store)
        restarted = super().restart_store_v2(selected._store)
        return cast(GovernanceStateStoreV2, _ViewFaultStore(restarted, self._fault))


HeadFault = Callable[[str, str, GovernanceHeadV2], GovernanceHeadV2]


class _HeadFaultStore:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        fault: HeadFault,
    ) -> None:
        self._store = store
        self._fault = fault

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = self._store.load_head_v2(scope_ref, stream_ref)
        detached = GovernanceHeadV2.from_dict(head.to_dict())
        return self._fault(scope_ref, stream_ref, detached)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self._store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        return self._store.atomic_commit_v2(batch)


class _HeadFaultAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = "test-boundary-head-fault-store-v2"

    def __init__(self, fault: HeadFault) -> None:
        self._fault = fault

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        store = super().create_store_v2(domains)
        return cast(GovernanceStateStoreV2, _HeadFaultStore(store, self._fault))

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = cast(_HeadFaultStore, store)
        restarted = super().restart_store_v2(selected._store)
        return cast(GovernanceStateStoreV2, _HeadFaultStore(restarted, self._fault))


def _reject_matching_attempt(fragment: str) -> AttemptFault:
    def reject(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if fragment in batch.transition_id:
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
        return attempt

    return reject


def _reject_nth_attempt(
    fragment: str,
    occurrence: int,
    *,
    scope_suffix: str | None = None,
) -> AttemptFault:
    counts: dict[str, int] = {}

    def reject(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if fragment not in batch.transition_id:
            return attempt
        if ":grant:" in batch.transition_id or batch.transition_id.endswith(":grant"):
            return attempt
        if scope_suffix is not None and not batch.scope_ref.endswith(scope_suffix):
            return attempt
        counts[batch.scope_ref] = counts.get(batch.scope_ref, 0) + 1
        if counts[batch.scope_ref] == occurrence:
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
        return attempt

    return reject


def _flip_matching_attempt(
    fragment: str,
    *,
    scope_suffix: str | None = None,
) -> AttemptFault:
    def flip(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if fragment not in batch.transition_id:
            return attempt
        if ":grant:" in batch.transition_id or batch.transition_id.endswith(":grant"):
            return attempt
        if scope_suffix is not None and not batch.scope_ref.endswith(scope_suffix):
            return attempt
        replacement = (
            GovernanceCommitDispositionV2.INVALID
            if attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
            else GovernanceCommitDispositionV2.COMMITTED
        )
        object.__setattr__(attempt, "disposition", replacement)
        return attempt

    return flip


def _set_nth_attempt_disposition(
    fragment: str,
    occurrence: int,
    disposition: GovernanceCommitDispositionV2,
    *,
    scope_suffix: str | None = None,
) -> AttemptFault:
    counts: dict[str, int] = {}

    def replace_disposition(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if fragment not in batch.transition_id:
            return attempt
        if ":grant:" in batch.transition_id or batch.transition_id.endswith(":grant"):
            return attempt
        if scope_suffix is not None and not batch.scope_ref.endswith(scope_suffix):
            return attempt
        counts[batch.scope_ref] = counts.get(batch.scope_ref, 0) + 1
        if counts[batch.scope_ref] == occurrence:
            object.__setattr__(attempt, "disposition", disposition)
        return attempt

    return replace_disposition


@pytest.mark.parametrize(("name", "runner"), STORE_RUNNERS)
def test_store_checker_adapter_boundaries_are_total(
    name: str,
    runner: StoreRunner,
) -> None:
    protocol = runner(object())
    version = runner(_UnknownVersionStoreAdapter())
    identity = runner(_EmptyIdentityStoreAdapter())
    identity_exception = runner(_ExplodingIdentityStoreAdapter())
    execution_exception = runner(_ExplodingExecutionStoreAdapter())

    assert (protocol.name, protocol.ok, protocol.detail) == (
        name,
        False,
        "adapter_protocol",
    )
    assert (version.name, version.ok, version.detail) == (
        name,
        False,
        "adapter_version",
    )
    assert (identity.name, identity.ok, identity.detail) == (
        name,
        False,
        "adapter_implementation_id",
    )
    assert identity_exception.ok is False
    assert identity_exception.detail.startswith("adapter_exception:LookupError")
    assert execution_exception.ok is False
    assert "RuntimeError" in execution_exception.detail
    assert "domain unavailable:" in execution_exception.detail


@pytest.mark.parametrize(
    ("fragment", "factory", "message"),
    [
        (
            "transition:grant:risk-v2:",
            lambda adapter: risk_context.context_v2(adapter, "activation-failure"),
            "Risk v2 Conformance grant activation failed",
        ),
        (
            "transition:support-v2:grant:",
            lambda adapter: support_context.context_v2(adapter, "activation-failure"),
            "Support v2 Conformance grant activation failed",
        ),
        (
            "transition:commit-gate-v2:grant:",
            lambda adapter: gate_context.commit_gate_context_v2(
                adapter, "activation-failure"
            ),
            "Commit Gate v2 Conformance grant activation failed",
        ),
    ],
)
def test_context_builders_reject_uncommitted_grant_activation(
    fragment: str,
    factory: Callable[[Any], object],
    message: str,
) -> None:
    adapter = _AttemptFaultAdapter(_reject_matching_attempt(fragment))

    with pytest.raises(RuntimeError, match=message):
        factory(adapter)


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        (
            "transition:principal-verification-v2:",
            "Support v2 Conformance verification commit failed",
        ),
        (
            "transition:membership-v2:",
            "Support v2 Conformance membership commit failed",
        ),
    ],
)
def test_support_upstream_builder_rejects_uncommitted_public_dependencies(
    fragment: str,
    message: str,
) -> None:
    adapter = _AttemptFaultAdapter(_reject_matching_attempt(fragment))
    context = support_context.context_v2(adapter, "upstream-failure")

    with pytest.raises(RuntimeError, match=message):
        support_context.commit_upstreams_v2(context, label="upstream-failure")


def test_support_rotated_grant_requires_a_committed_store_attempt() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:support-v2:grant:b")
    )
    context = support_context.context_v2(adapter, "rotation-failure")

    with pytest.raises(
        RuntimeError, match="Support v2 Conformance rotated grant failed"
    ):
        support_context.activate_rotated_grant_v2(context)


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        (
            "transition:principal-verification-v2:",
            "Commit Evidence v2 verification advance failed",
        ),
        (
            "transition:membership-v2:",
            "Commit Evidence v2 membership advance failed",
        ),
    ],
)
def test_evidence_upstream_builder_rejects_uncommitted_dependencies(
    fragment: str,
    message: str,
) -> None:
    adapter = _AttemptFaultAdapter(_reject_matching_attempt(fragment))
    context = support_context.context_v2(adapter, "evidence-upstream")

    with pytest.raises(RuntimeError, match=message):
        evidence_context._commit_two_principal_upstreams_v2(
            context,
            label="evidence-upstream",
        )


def test_evidence_context_requires_replay_grant_and_collective_policy() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:grant:commit-evidence:replay:")
    )
    with pytest.raises(
        RuntimeError, match="Commit Evidence v2 replay grant activation failed"
    ):
        evidence_context.context_v2_for_evidence(adapter, "replay-grant-failure")

    missing_policy = SimpleNamespace(
        support=SimpleNamespace(
            manifest=SimpleNamespace(collective_commit_policy=None),
        )
    )
    with pytest.raises(
        RuntimeError, match="Commit Evidence v2 requires collective commit policy"
    ):
        evidence_context.commit_replay_v2(
            cast(Any, missing_policy),
            (),
            advance_ref="advance:missing-policy",
        )


def test_evidence_replay_builder_requires_a_committed_attempt() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:commit-replay-v2:")
    )
    context = evidence_context.context_v2_for_evidence(
        adapter,
        "replay-advance-failure",
    )

    with pytest.raises(RuntimeError, match="Commit Evidence v2 replay advance failed"):
        evidence_context.commit_replay_v2(
            context,
            evidence_context.attestations_v2("replay-advance-failure"),
            advance_ref="advance:replay-advance-failure",
        )


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        (
            "transition:support-v2:",
            "Commit Gate v2 Conformance Support commit failed",
        ),
        (
            "transition:commit-replay-v2:",
            "Commit Gate v2 Conformance Replay commit failed",
        ),
        (
            "transition:risk-v2:",
            "Commit Gate v2 Conformance Risk commit failed",
        ),
    ],
)
def test_commit_gate_context_rejects_each_uncommitted_dependency(
    fragment: str,
    message: str,
) -> None:
    adapter = _AttemptFaultAdapter(_reject_matching_attempt(fragment))

    with pytest.raises(RuntimeError, match=message):
        gate_context.commit_gate_context_v2(adapter, "dependency-failure")


@pytest.mark.parametrize(
    ("operation", "scope_suffix", "problem"),
    [
        (risk_core._vertical_restart_linearity, ":vertical", "genesis_commit"),
        (
            risk_core._fixed_lineage_epoch_jump,
            ":fixed-lineage-epoch-130",
            "fixed_lineage_epoch_130_genesis",
        ),
        (risk_core._sealed_domain_matrix, ":sealed-domain", "sealed_domain_setup"),
        (
            risk_core._deterministic_transcript,
            ":deterministic",
            "deterministic_transcript",
        ),
    ],
)
def test_risk_core_checker_names_uncommitted_primary_transitions(
    operation: Callable[[Any, list[str]], None],
    scope_suffix: str,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:risk-v2:",
            1,
            scope_suffix=scope_suffix,
        )
    )
    problems: list[str] = []

    operation(adapter, problems)

    assert problem in problems


@pytest.mark.parametrize(
    ("occurrence", "problem"),
    [
        (2, "restart_child_commit"),
        (3, "stale_fork_retry"),
    ],
)
def test_risk_vertical_checker_reports_late_store_response_divergence(
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:risk-v2:",
            occurrence,
            scope_suffix=":vertical",
        )
    )
    problems: list[str] = []

    risk_core._vertical_restart_linearity(adapter, problems)

    assert problem in problems


def test_risk_core_checker_reports_revocation_and_retirement_divergence() -> None:
    revocation: list[str] = []
    retirement: list[str] = []
    risk_core._vertical_restart_linearity(
        _AttemptFaultAdapter(
            _reject_matching_attempt(
                "transition:risk-v2:revoke-after-commit",
            )
        ),
        revocation,
    )
    risk_core._sealed_domain_matrix(
        _AttemptFaultAdapter(
            _reject_matching_attempt("transition:risk-v2:sealed-domain")
        ),
        retirement,
    )

    assert "grant_revocation" in revocation
    assert "sealed_domain_retirement" in retirement


@pytest.mark.parametrize(
    ("operation", "scope_suffix", "problem"),
    [
        (
            risk_finality._lost_response_and_conflict,
            ":lost-response",
            "lost_response_finality",
        ),
        (
            risk_finality._reconciliation_and_rehydrate_finality,
            ":reconciliation-finality",
            "reconciliation_setup",
        ),
        (
            risk_finality._historical_parent_finality,
            ":parent-finality",
            "parent_finality_setup",
        ),
    ],
)
def test_risk_finality_checker_names_uncommitted_setup(
    operation: Callable[..., None],
    scope_suffix: str,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:risk-v2:",
            1,
            scope_suffix=scope_suffix,
        )
    )
    problems: list[str] = []

    operation(
        adapter,
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        problems,
    )

    assert problem in problems


def test_risk_finality_checker_reports_a_conflict_response_with_wrong_disposition() -> (
    None
):
    def accept_conflict(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            batch.scope_ref.endswith(":lost-response")
            and attempt.disposition is GovernanceCommitDispositionV2.INVALID
        ):
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
        return attempt

    problems: list[str] = []

    def divergent_advance(context: Any, request: Any, source: object) -> Any:
        attempt = risk_context.advance_v2(context, request, source)
        if attempt.disposition is GovernanceCommitDispositionV2.INVALID:
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
            return detached
        return attempt

    risk_finality._lost_response_and_conflict(
        _AttemptFaultAdapter(accept_conflict),
        risk_context.context_v2,
        risk_context.request_v2,
        divergent_advance,
        problems,
    )

    assert "canonical_transition_conflict" in problems


def test_risk_race_checker_reports_wrong_public_outcome_sets() -> None:
    same_problems: list[str] = []
    parent_problems: list[str] = []
    forks_problems: list[str] = []
    risk_race._same_request_race(
        _AttemptFaultAdapter(
            _flip_matching_attempt(
                "transition:risk-v2:",
                scope_suffix=":race-same-request",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        same_problems,
    )
    risk_race._fork_race(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                1,
                scope_suffix=":race-forks",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        parent_problems,
    )

    counts: dict[str, int] = {}

    def accept_stale_forks(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if "transition:risk-v2:" not in batch.transition_id:
            return attempt
        counts[batch.scope_ref] = counts.get(batch.scope_ref, 0) + 1
        if counts[batch.scope_ref] >= 3:
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
        return attempt

    risk_race._fork_race(
        _AttemptFaultAdapter(accept_stale_forks),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        forks_problems,
    )

    assert same_problems == ["race_32_same_request"]
    assert parent_problems == ["race_fork_parent_setup"]
    assert "race_32_forks_one_winner" in forks_problems


def test_risk_vertical_checker_detects_returned_read_set_and_trace_tamper() -> None:
    def corrupt_returned_risk(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            batch.scope_ref.endswith(":vertical")
            and "transition:risk-v2:" in batch.transition_id
            and attempt.committed_transition is not None
        ):
            returned_batch = attempt.committed_transition.batch
            object.__setattr__(returned_batch.read_set, "entries", ())
            event = returned_batch.trace_batch.events[0]
            object.__setattr__(event, "event_type", "risk_tampered")
        return attempt

    problems: list[str] = []
    risk_core._vertical_restart_linearity(
        _AttemptFaultAdapter(corrupt_returned_risk),
        problems,
    )

    assert "complete_authority_read_set" in problems
    assert "atomic_trace_lineage" in problems


def test_risk_vertical_checker_names_invalid_exact_retry_view() -> None:
    def remove_child_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if (
            committed is not None
            and committed.batch.transition.state_records["request"]["advance_ref"]
            == "advance:child:a"
        ):
            object.__setattr__(view, "committed_transition", None)
        return view

    retry_problems: list[str] = []
    risk_core._vertical_restart_linearity(
        _ViewFaultAdapter(remove_child_view),
        retry_problems,
    )

    assert "exact_retry_after_revocation" in retry_problems


def test_risk_fixed_lineage_checker_names_second_commit_divergence() -> None:
    rejected: list[str] = []
    risk_core._fixed_lineage_epoch_jump(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                2,
                scope_suffix=":fixed-lineage-epoch-130",
            )
        ),
        rejected,
    )

    assert rejected == ["fixed_lineage_epoch_130"]


def test_risk_sealed_checker_names_invalid_exact_retry_view() -> None:
    reads: dict[str, int] = {}

    def remove_second_genesis_view(
        _scope_ref: str,
        _stream_ref: str,
        transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if (
            committed is not None
            and committed.batch.transition.state_records["request"]["advance_ref"]
            == "advance:sealed-domain:genesis"
        ):
            reads[transition_id] = reads.get(transition_id, 0) + 1
            if reads[transition_id] == 2:
                object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    risk_core._sealed_domain_matrix(
        _ViewFaultAdapter(remove_second_genesis_view),
        problems,
    )

    assert "sealed_domain_exact_retry" in problems


def test_risk_source_checker_names_observable_zero_write_anomalies() -> None:
    context = risk_context.context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "source-zero-write",
    )
    request, source = risk_context.request_v2(
        context,
        advance_ref="advance:source-zero-write",
    )
    session = risk_core.open_risk_authority_session_v2(context.capability, request)

    def increment_risk_head(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if "authority:risk-v2:" in stream_ref:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    observable = replace(
        context,
        store=cast(
            GovernanceStateStoreV2,
            _HeadFaultStore(context.store, increment_risk_head),
        ),
    )
    problems: list[str] = []

    risk_core._raw_source_and_session_binding(
        observable,
        request,
        source,
        session,
        problems,
    )

    assert "raw_source_zero_write" in problems
    assert "source_session_zero_write" in problems


def test_risk_finality_checker_names_factory_and_head_divergence() -> None:
    def increment_committed_risk_head(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if "authority:risk-v2:" in stream_ref and head.revision:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    lost_head: list[str] = []
    risk_finality._lost_response_and_conflict(
        _HeadFaultAdapter(increment_committed_risk_head),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        lost_head,
    )

    saved: GovernanceCommitAttemptV2 | None = None

    def stale_retry(context: Any, request: Any, source: object) -> Any:
        nonlocal saved
        attempt = risk_context.advance_v2(context, request, source)
        if source is not None:
            saved = attempt
            return attempt
        assert saved is not None
        detached = GovernanceCommitAttemptV2.from_dict(saved.to_dict())
        object.__setattr__(
            detached,
            "disposition",
            GovernanceCommitDispositionV2.INVALID,
        )
        return detached

    lost_retry: list[str] = []
    risk_finality._lost_response_and_conflict(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        risk_context.context_v2,
        risk_context.request_v2,
        stale_retry,
        lost_retry,
    )

    def accept_finality(context: Any, request: Any, source: object) -> Any:
        attempt = risk_context.advance_v2(context, request, source)
        if source is None:
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
            return detached
        return attempt

    reconciliation: list[str] = []
    risk_finality._reconciliation_and_rehydrate_finality(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        risk_context.context_v2,
        risk_context.request_v2,
        accept_finality,
        reconciliation,
    )

    def accept_historical_finality(
        context: Any,
        request: Any,
        source: object,
    ) -> Any:
        attempt = risk_context.advance_v2(context, request, source)
        if request.advance_ref.endswith(":child"):
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.COMMITTED,
            )
            return detached
        return attempt

    historical: list[str] = []
    risk_finality._historical_parent_finality(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        risk_context.context_v2,
        risk_context.request_v2,
        accept_historical_finality,
        historical,
    )

    assert {
        "lost_response_atomic_publication",
        "conflict_zero_write",
    } <= set(lost_head)
    assert "lost_response_exact_retry" in lost_retry
    assert "reconciliation_finality_unavailable" in reconciliation
    assert "historical_parent_finality_unavailable" in historical

    reconciliation_head: list[str] = []
    risk_finality._reconciliation_and_rehydrate_finality(
        _HeadFaultAdapter(increment_committed_risk_head),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        reconciliation_head,
    )
    historical_head: list[str] = []
    risk_finality._historical_parent_finality(
        _HeadFaultAdapter(increment_committed_risk_head),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        historical_head,
    )

    assert {
        "reconciliation_finality_zero_write",
        "rehydrate_finality_zero_write",
    } <= set(reconciliation_head)
    assert "historical_parent_finality_zero_write" in historical_head


@pytest.mark.parametrize(
    ("occurrence", "problem"),
    [
        (1, "initialize_not_committed"),
        (2, "issue_not_committed"),
        (3, "switch_not_committed"),
        (4, "revoke_not_committed"),
    ],
)
def test_support_core_checker_names_each_uncommitted_transition(
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:support-v2:",
            occurrence,
            scope_suffix=":vertical",
        )
    )
    problems: list[str] = []

    support_core._vertical_restart_and_evaluation(adapter, problems)

    assert problem in problems


def test_support_trace_checker_reports_missing_commit_and_wrong_event_types() -> None:
    missing: list[str] = []
    wrong: list[str] = []
    request = SimpleNamespace(
        stream_ref="stream:support",
        transition_id="transition:support",
    )
    missing_context = SimpleNamespace(
        domain=SimpleNamespace(scope_ref="scope:support"),
        store=SimpleNamespace(
            load_commit_view_v2=lambda *_args: SimpleNamespace(
                committed_transition=None
            )
        ),
    )
    wrong_context = SimpleNamespace(
        domain=SimpleNamespace(scope_ref="scope:support"),
        store=SimpleNamespace(
            load_commit_view_v2=lambda *_args: SimpleNamespace(
                committed_transition=SimpleNamespace(
                    batch=SimpleNamespace(
                        trace_batch=SimpleNamespace(
                            events=(SimpleNamespace(event_type="wrong"),)
                        )
                    )
                )
            )
        ),
    )

    support_core._check_trace_types(
        cast(Any, missing_context),
        cast(Any, request),
        ("expected",),
        "missing",
        missing,
    )
    support_core._check_trace_types(
        cast(Any, wrong_context),
        cast(Any, request),
        ("expected",),
        "wrong",
        wrong,
    )

    assert missing == ["missing_missing_commit"]
    assert wrong == ["wrong_types"]


@pytest.mark.parametrize(
    ("operation", "scope_suffix", "occurrence", "problem"),
    [
        (
            support_integrity._lost_response_exact_retry,
            ":lost-response",
            1,
            "lost_response_initialize",
        ),
        (
            support_integrity._lost_response_exact_retry,
            ":lost-response",
            2,
            "lost_response_initial_commit",
        ),
        (
            support_integrity._stale_parent_and_membership,
            ":stale-parent",
            1,
            "stale_parent_initialize",
        ),
        (
            support_integrity._stale_parent_and_membership,
            ":stale-parent",
            2,
            "stale_parent_winner",
        ),
        (
            support_integrity._stale_parent_and_membership,
            ":stale-membership",
            1,
            "stale_membership_initialize",
        ),
        (
            support_integrity._issuer_rotation,
            ":issuer-rotation",
            1,
            "issuer_rotation_initialize",
        ),
        (
            support_integrity._issuer_rotation,
            ":issuer-rotation",
            2,
            "issuer_rotation_issue",
        ),
        (
            support_integrity._issuer_rotation,
            ":issuer-rotation",
            3,
            "issuer_rotation_switch",
        ),
        (
            support_integrity._canonical_wire_and_resource,
            ":canonical-resource",
            1,
            "canonical_resource_initialize",
        ),
    ],
)
def test_support_integrity_checker_names_divergent_commit_attempts(
    operation: Callable[[Any, list[str]], None],
    scope_suffix: str,
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:support-v2:",
            occurrence,
            scope_suffix=scope_suffix,
        )
    )
    problems: list[str] = []

    operation(adapter, problems)

    assert problem in problems


def test_support_integrity_checker_names_invalid_exact_retries() -> None:
    def remove_issued_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if committed is None:
            return view
        request = committed.batch.transition.state_records["request"]
        if request.get("issued_lease") is not None:
            object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    support_integrity._lost_response_exact_retry(
        _ViewFaultAdapter(remove_issued_view),
        problems,
    )

    assert "lost_response_exact_retry" in problems
    assert "lost_response_retry_after_revoke" in problems


def test_support_integrity_checker_names_grant_revoke_divergence() -> None:
    problems: list[str] = []
    support_integrity._lost_response_exact_retry(
        _AttemptFaultAdapter(
            _reject_matching_attempt("transition:support-v2:grant-revoked-after-commit")
        ),
        problems,
    )

    assert "lost_response_grant_revoke" in problems


def test_support_finality_checker_reports_setup_retirement_and_denial_divergence() -> (
    None
):
    initialize: list[str] = []
    retirement: list[str] = []
    support_finality._seal_finality_and_tamper(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:support-v2:",
                1,
                scope_suffix=":finality-tamper",
            )
        ),
        initialize,
    )
    support_finality._assert_sealed_domain_behavior(
        _AttemptFaultAdapter(_reject_matching_attempt("transition:support-v2:retire")),
        retirement,
    )

    assert initialize == ["finality_tamper_initialize"]
    assert retirement == ["domain_seal_not_committed"]


def test_support_sealed_checker_names_uncommitted_initialize() -> None:
    problems: list[str] = []
    support_finality._assert_sealed_domain_behavior(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:support-v2:",
                1,
                scope_suffix=":sealed",
            )
        ),
        problems,
    )

    assert problems == ["sealed_initialize"]


def test_support_race_checker_reports_nonconforming_public_outcomes() -> None:
    problems: list[str] = []

    def distort_races(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            "transition:support-v2:" not in batch.transition_id
            or ":grant:" in batch.transition_id
        ):
            return attempt
        if batch.scope_ref.endswith(":race-identical") or (
            batch.scope_ref.endswith(":race-conflicting")
            and attempt.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
        ):
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
        return attempt

    support_finality._race_32(
        _AttemptFaultAdapter(distort_races),
        problems,
    )

    assert "race_32_same_request" in problems
    assert "race_32_forks_one_winner" in problems


def test_support_race_checker_names_observable_head_revision_divergence() -> None:
    def increment_committed_support_head(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if "authority:support-v2:" in stream_ref and head.revision:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    problems: list[str] = []
    support_finality._race_32(
        _HeadFaultAdapter(increment_committed_support_head),
        problems,
    )

    assert "race_32_same_request_revision" in problems
    assert "race_32_forks_revision" in problems


def test_commit_replay_context_requires_committed_grant_activation() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:commit-replay-v2:grant")
    )

    with pytest.raises(
        RuntimeError, match="commit replay conformance grant activation failed"
    ):
        replay_checker._context(adapter, "grant-failure")


@pytest.mark.parametrize(
    ("occurrence", "problem"),
    [
        (1, "genesis_commit"),
        (2, "restart_child"),
        (3, "stale_fork"),
    ],
)
def test_commit_replay_vertical_checker_names_store_response_divergence(
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:commit-replay-v2:",
            occurrence,
            scope_suffix=":vertical",
        )
    )
    problems: list[str] = []

    replay_checker._vertical_restart_and_fork(adapter, problems)

    assert problem in problems


def test_commit_replay_vertical_checker_detects_returned_batch_tamper() -> None:
    def corrupt_returned_replay(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            batch.scope_ref.endswith(":vertical")
            and "transition:commit-replay-v2:" in batch.transition_id
            and attempt.committed_transition is not None
        ):
            returned_batch = attempt.committed_transition.batch
            object.__setattr__(returned_batch.read_set, "entries", ())
            event = returned_batch.trace_batch.events[0]
            object.__setattr__(event, "event_type", "commit_replay_tampered")
        return attempt

    problems: list[str] = []
    replay_checker._vertical_restart_and_fork(
        _AttemptFaultAdapter(corrupt_returned_replay),
        problems,
    )

    assert "complete_read_set" in problems
    assert "atomic_trace" in problems


def test_commit_replay_vertical_checker_names_invalid_exact_retry_view() -> None:
    def remove_child_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if (
            committed is not None
            and committed.batch.transition.state_records["request"]["advance_ref"]
            == "advance:child:a"
        ):
            object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    replay_checker._vertical_restart_and_fork(
        _ViewFaultAdapter(remove_child_view),
        problems,
    )

    assert "exact_retry" in problems


def test_commit_replay_source_checker_names_rejected_valid_source() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:commit-replay-v2:",
            1,
            scope_suffix=":deterministic",
        )
    )
    problems: list[str] = []

    replay_checker._source_and_determinism(adapter, problems)

    assert "source_commit" in problems

    deterministic: list[str] = []
    replay_checker._source_and_determinism(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-replay-v2:",
                2,
                scope_suffix=":deterministic",
            )
        ),
        deterministic,
    )
    assert "deterministic_transcript" in deterministic


def test_commit_replay_finality_checker_names_parent_and_lost_response_setup() -> None:
    parent_problems: list[str] = []
    lost_problems: list[str] = []

    def reject_parent(context: Any, request: Any, source: object) -> Any:
        attempt = replay_checker._advance(context, request, source)
        if request.advance_ref == "advance:public-parent-finality:1":
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            return detached
        return attempt

    replay_finality._evaluate_finality(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        reject_parent,
        parent_problems,
    )
    replay_finality._evaluate_lost_response(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-replay-v2:",
                1,
                scope_suffix=":public-lost-response",
            )
        ),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        lost_problems,
    )

    assert parent_problems == ["parent_finality_setup"]
    assert "post_publication_lost_response" in lost_problems


def test_commit_replay_lost_response_checker_names_public_view_loss() -> None:
    def remove_replay_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        if view.committed_transition is not None:
            object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    replay_finality._evaluate_lost_response(
        _ViewFaultAdapter(remove_replay_view),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        problems,
    )

    assert "canonical_exact_retry" in problems
    assert "canonical_retry_conflict" in problems


def test_commit_replay_race_checker_reports_divergent_factory_results() -> None:
    same: list[str] = []
    parent: list[str] = []

    def reject_all(context: Any, request: Any, source: object) -> Any:
        attempt = replay_checker._advance(context, request, source)
        detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
        object.__setattr__(
            detached,
            "disposition",
            GovernanceCommitDispositionV2.INVALID,
        )
        return detached

    replay_race._evaluate_same_request_race(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        reject_all,
        same,
    )
    replay_race._evaluate_two_fork_race(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        reject_all,
        parent,
    )

    assert same == ["concurrent_same_request"]
    assert parent == ["concurrent_fork_parent"]


def test_commit_replay_race_checker_names_corrupted_fork_families() -> None:
    problems: list[str] = []

    def invalidate_returned_forks(
        context: Any,
        request: Any,
        source: object,
    ) -> Any:
        attempt = replay_checker._advance(context, request, source)
        if request.advance_ref.startswith("advance:public-race-fork:"):
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            object.__setattr__(detached, "failure", None)
            return detached
        return attempt

    replay_race._evaluate_two_fork_race(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        invalidate_returned_forks,
        problems,
    )

    assert "concurrent_two_fork_disposition" in problems
    assert "concurrent_two_fork_diagnostic" in problems


def _committed_replay_fixture(label: str) -> tuple[Any, Any]:
    context = replay_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        label,
    )
    request, source = replay_checker._request(
        context,
        advance_ref=f"advance:{label}",
        receipt=replay_checker._receipt(701, suffix=f":{label}"),
        current_step=1,
    )
    attempt = replay_checker._advance(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return context, request


def test_commit_replay_integrity_mutators_reject_unknown_and_irrelevant_inputs() -> (
    None
):
    context, request = _committed_replay_fixture("integrity-mutators")
    view = context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    irrelevant = GovernanceCommitViewV2.from_dict(view.to_dict())
    object.__setattr__(irrelevant, "transition_id", "transition:other")

    read_set_mutator = replay_integrity._read_set_mutator(
        request.transition_id,
        request,
        "state",
        "unknown",
    )
    read_set_mutator(irrelevant)
    with pytest.raises(ValueError, match="unknown Commit Replay read-set mutation"):
        read_set_mutator(view)

    trace_mutator = replay_integrity._trace_read_set_root_mutator(request.transition_id)
    trace_mutator(irrelevant)
    artifact_mutator = replay_integrity._artifact_mutator(
        request.transition_id,
        view.committed_transition,
        "receipt_delete",
    )
    artifact_mutator(irrelevant)

    with pytest.raises(ValueError, match="unknown Commit Replay State mutation"):
        replay_integrity._mutate_state_artifact(
            SimpleNamespace(state_records={"snapshot": {}}),
            SimpleNamespace(state_records={"snapshot": {}}),
            "unknown",
        )
    with pytest.raises(ValueError, match="unknown Commit Replay commit mutation"):
        replay_integrity._mutate_commit_artifact(
            cast(Any, view),
            view.committed_transition,
            "unknown",
        )


def test_commit_replay_integrity_expectations_name_acceptance_and_exceptions() -> None:
    context, request = _committed_replay_fixture("integrity-expectations")
    accepted: list[str] = []
    reconciliation: list[str] = []
    malformed: list[str] = []
    reconciliation_exception: list[str] = []

    replay_integrity._expect_invalid_rehydration(
        context,
        request,
        "accepted",
        accepted,
    )
    replay_integrity._expect_invalid_reconciliation(
        context,
        request,
        "accepted",
        reconciliation,
    )
    replay_integrity._expect_invalid_rehydration(
        SimpleNamespace(domain=object(), store=object()),
        SimpleNamespace(to_dict=lambda: None),
        "malformed",
        malformed,
    )
    replay_integrity._expect_invalid_reconciliation(
        SimpleNamespace(capability=object()),
        request,
        "malformed",
        reconciliation_exception,
    )
    pickle_problems: list[str] = []
    replay_integrity._expect_pickle_rejection(
        {"portable": True},
        "pickle_accepted",
        pickle_problems,
    )

    assert accepted == ["accepted"]
    assert reconciliation == ["accepted_reconciliation"]
    assert malformed == ["malformed"]
    assert reconciliation_exception == ["malformed_reconciliation_exception"]
    assert pickle_problems == ["pickle_accepted"]


def test_commit_replay_parent_checker_rejects_a_still_current_parent() -> None:
    context, request = _committed_replay_fixture("current-parent")
    current = replay_checker.rehydrate_commit_replay_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    problems: list[str] = []

    replay_race._check_superseded_parent(current, problems)

    assert problems == [
        "superseded_parent_currentness",
        "superseded_parent_requirement",
    ]


def test_commit_replay_integrity_checker_names_initial_and_donor_setup_failures() -> (
    None
):
    def reject_initial(context: Any, request: Any, source: object) -> Any:
        attempt = replay_checker._advance(context, request, source)
        detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
        object.__setattr__(
            detached,
            "disposition",
            GovernanceCommitDispositionV2.INVALID,
        )
        return detached

    initial: list[str] = []
    replay_integrity._evaluate_historical_integrity(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        reject_initial,
        initial,
    )

    def reject_donor(context: Any, request: Any, source: object) -> Any:
        attempt = replay_checker._advance(context, request, source)
        if request.advance_ref == "advance:public-historical-donor":
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            return detached
        return attempt

    donor: list[str] = []
    replay_integrity._evaluate_historical_integrity(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        reject_donor,
        donor,
    )

    assert initial == ["historical_integrity_setup"]
    assert donor == ["historical_donor_setup"]


def test_commit_replay_integrity_checker_names_missing_donor_view() -> None:
    def remove_donor_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if (
            committed is not None
            and committed.batch.transition.state_records["request"]["advance_ref"]
            == "advance:public-historical-donor"
        ):
            object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    replay_integrity._evaluate_historical_integrity(
        _ViewFaultAdapter(remove_donor_view),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        replay_checker._advance,
        problems,
    )

    assert "historical_donor_view" in problems


def test_commit_replay_integrity_checker_names_historical_head_mutation() -> None:
    def mutate_head_after_donor(
        context: Any,
        request: Any,
        source: object,
    ) -> Any:
        attempt = replay_checker._advance(context, request, source)
        if request.advance_ref == "advance:public-historical-donor":
            base = context.store._store

            def increment_replay_head(
                _scope_ref: str,
                stream_ref: str,
                head: GovernanceHeadV2,
            ) -> GovernanceHeadV2:
                if "authority:commit-replay-v2:" in stream_ref:
                    object.__setattr__(head, "revision", head.revision + 1)
                return head

            context.store._store = _HeadFaultStore(
                base,
                increment_replay_head,
            )
        return attempt

    problems: list[str] = []
    replay_integrity._evaluate_historical_integrity(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        mutate_head_after_donor,
        problems,
    )

    assert "historical_tamper_zero_write" in problems


def test_commit_replay_rehydration_expectation_names_wrong_diagnostic() -> None:
    context, request = _committed_replay_fixture("wrong-diagnostic")
    foreign = replay_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "wrong-diagnostic-foreign",
    )
    problems: list[str] = []

    replay_integrity._expect_invalid_rehydration(
        replace(context, domain=foreign.domain),
        request,
        "wrong_diagnostic",
        problems,
    )

    assert problems == ["wrong_diagnostic"]


def test_commit_replay_context_integrity_names_head_and_valid_setup_divergence() -> (
    None
):
    contexts: list[Any] = []

    def enable_head_faults_after_requests(
        context: Any,
        **kwargs: object,
    ) -> Any:
        request = replay_checker._request(context, **kwargs)
        if context not in contexts:
            contexts.append(context)
        if len(contexts) == 2 and kwargs["advance_ref"] == (
            "advance:public-authority:alternate"
        ):
            for selected in contexts:
                base = selected.store._store

                def increment_replay_head(
                    _scope_ref: str,
                    stream_ref: str,
                    head: GovernanceHeadV2,
                ) -> GovernanceHeadV2:
                    if "authority:commit-replay-v2:" in stream_ref:
                        object.__setattr__(head, "revision", head.revision + 1)
                    return head

                selected.store._store = _HeadFaultStore(
                    base,
                    increment_replay_head,
                )
        return request

    problems: list[str] = []
    replay_integrity._evaluate_context_and_portability(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        replay_checker._context,
        replay_checker._receipt,
        enable_head_faults_after_requests,
        problems,
    )

    assert "authority_rejection_zero_write" in problems

    rejected: list[str] = []
    replay_integrity._evaluate_context_and_portability(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-replay-v2:",
                1,
                scope_suffix=":public-authority-a",
            )
        ),
        replay_checker._context,
        replay_checker._receipt,
        replay_checker._request,
        rejected,
    )

    assert "authority_valid_setup" in rejected


def test_commit_replay_resource_checker_names_fast_malformed_vectors() -> None:
    baseline = SimpleNamespace(
        scope_ref="scope:replay-resource",
        stream_ref="authority:commit-replay-v2:resource",
        target_ref="target:replay-resource",
        snapshot=SimpleNamespace(
            domain_root="invalid",
            scope_ref="scope:replay-resource",
            manifest_root="invalid",
            commit_policy_root="invalid",
            profile="invalid",
            assurance="invalid",
            protocol_ref="protocol:invalid",
            run_ref="run:invalid",
            target_ref="target:replay-resource",
            observed_epoch=1,
        ),
    )

    class DivergentStore:
        atomic_commits = 0

        def __init__(self) -> None:
            self._reads = 0

        def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
            self._reads += 1
            return SimpleNamespace(
                revision=self._reads,
                head_root=f"head:{self._reads}",
            )

        def reset_observations(self) -> None:
            self.atomic_commits = 1

    problems = replay_resource.run_public_commit_replay_resource_matrix_v2(
        context=object(),
        store=DivergentStore(),
        request_factory=lambda *_args, **_kwargs: (baseline, object()),
    )

    assert {
        "resource_rejection_zero_write",
        "resource_count_exact",
        "resource_text_exact",
        "resource_snapshot_vector",
    } <= set(problems)


@pytest.mark.parametrize(
    ("operation", "scope_suffix", "occurrence", "problem"),
    [
        (evidence_checker._vertical_restart, ":vertical", 1, "vertical_commit"),
        (
            evidence_checker._source_and_order,
            ":source-order",
            1,
            "single_source_commit",
        ),
        (evidence_checker._conflicting_fork, ":fork", 1, "fork_winner"),
        (evidence_checker._conflicting_fork, ":fork", 2, "fork_stale_loser"),
    ],
)
def test_commit_evidence_checker_names_store_response_divergence(
    operation: Callable[[Any, list[str]], None],
    scope_suffix: str,
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:commit-evidence-v2:",
            occurrence,
            scope_suffix=scope_suffix,
        )
    )
    problems: list[str] = []

    operation(adapter, problems)

    assert problem in problems


def test_commit_evidence_checker_detects_read_set_and_trace_response_tamper() -> None:
    def corrupt_returned_evidence(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            batch.scope_ref.endswith(":vertical")
            and "transition:commit-evidence-v2:" in batch.transition_id
            and attempt.committed_transition is not None
        ):
            returned_batch = attempt.committed_transition.batch
            object.__setattr__(returned_batch.read_set, "entries", ())
            event = returned_batch.trace_batch.events[0]
            object.__setattr__(event, "event_type", "commit_evidence_tampered")
        return attempt

    problems: list[str] = []
    evidence_checker._vertical_restart(
        _AttemptFaultAdapter(corrupt_returned_evidence),
        problems,
    )

    assert "complete_authority_read_set" in problems
    assert "atomic_trace_lineage" in problems


def test_commit_evidence_fork_checker_names_observable_head_divergence() -> None:
    def increment_committed_evidence_head(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if "authority:commit-evidence-v2:" in stream_ref and head.revision:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    problems: list[str] = []
    evidence_checker._conflicting_fork(
        _HeadFaultAdapter(increment_committed_evidence_head),
        problems,
    )

    assert "fork_single_head" in problems


def test_commit_gate_atomic_attempt_checker_names_each_atomic_invariant() -> None:
    context = gate_context.commit_gate_context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "atomic-attempt-totality",
    )
    request, source = gate_context.prepare_stop_v2(
        context,
        "atomic-attempt-totality",
    )
    attempt = gate_context.resolve_stop_v2(context, request, source)
    malformed = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
    assert malformed.committed_transition is not None
    object.__setattr__(malformed.committed_transition.batch.read_set, "entries", ())
    event = malformed.committed_transition.batch.trace_batch.events[0]
    object.__setattr__(event, "event_type", "wrong")
    problems: list[str] = []

    gate_checker._validate_atomic_attempt(
        "malformed",
        request,
        malformed,
        "commit_stop_resolved_v2",
        problems,
    )
    gate_checker._validate_atomic_attempt(
        "missing",
        request,
        cast(
            Any,
            SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                committed_transition=None,
            ),
        ),
        "commit_stop_resolved_v2",
        problems,
    )

    assert problems == [
        "malformed_eight_entry_read_set",
        "malformed_atomic_trace",
        "missing_genesis_commit",
    ]


@pytest.mark.parametrize(
    ("fragment", "scope_suffix", "occurrence", "problem"),
    [
        ("transition:commit-stop-v2:", ":vertical", 1, "stop_genesis_commit"),
        (
            "transition:commit-permission-v2:",
            ":vertical",
            1,
            "permission_genesis_commit",
        ),
        (
            "transition:principal-verification-v2:",
            ":verification-toctou",
            2,
            "verification_toctou_setup",
        ),
        (
            "transition:commit-stop-v2:",
            ":conflict",
            1,
            "conflicting_winner",
        ),
    ],
)
def test_commit_gate_checker_names_uncommitted_public_attempts(
    fragment: str,
    scope_suffix: str,
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            fragment,
            occurrence,
            scope_suffix=scope_suffix,
        )
    )
    problems: list[str] = []
    operation = (
        gate_checker._vertical_restart_exact_retry
        if scope_suffix == ":vertical"
        else (
            gate_checker._principal_verification_toctou
            if scope_suffix == ":verification-toctou"
            else gate_checker._conflict_and_source_authority
        )
    )

    operation(adapter, problems)

    assert problem in problems


def test_commit_gate_adversarial_checker_names_uncommitted_fixture_attempts() -> None:
    finality = gate_adversarial.run_commit_gate_v2_finality_integrity_matrix(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-permission-v2:",
                1,
                scope_suffix=":public-finality-integrity",
            )
        )
    )
    seal = gate_adversarial.run_commit_gate_v2_seal_matrix(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-stop-v2:",
                1,
                scope_suffix=":public-seal",
            )
        )
    )

    assert finality == ("tamper_fixture_commit",)
    assert seal == ("sealed_fixture_commit",)


def test_commit_gate_adversarial_races_name_returned_attempt_divergence() -> None:
    identical = gate_adversarial.run_commit_gate_v2_race_matrix(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-permission-v2:",
                1,
                scope_suffix=":public-race-identical",
            )
        )
    )
    conflicting = gate_adversarial.run_commit_gate_v2_race_matrix(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:commit-stop-v2:",
                1,
                scope_suffix=":public-race-conflicting",
            )
        )
    )

    assert "race_32_identical_exact_retry" in identical
    assert "race_32_conflicting_one_winner" in conflicting


def test_commit_gate_seal_checker_names_retirement_and_retry_divergence() -> None:
    retirement = gate_adversarial.run_commit_gate_v2_seal_matrix(
        _AttemptFaultAdapter(
            _reject_matching_attempt("transition:commit-gate-v2:public-seal")
        )
    )

    def remove_stop_view(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if committed is not None:
            records = committed.batch.transition.state_records
            if "request" in records and "stop" in records["request"]["schema"]:
                object.__setattr__(view, "committed_transition", None)
        return view

    retry = gate_adversarial.run_commit_gate_v2_seal_matrix(
        _ViewFaultAdapter(remove_stop_view)
    )

    assert "domain_seal" in retirement
    assert "sealed_historical_exact_retry" in retry


class _AlwaysVerifier:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return all((issuer_ref, attestation_ref, body_root))


class _NeverVerifier:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return not any((issuer_ref, attestation_ref, body_root))


class _PermissiveCertificateAdapter:
    implementation_id = "permissive-certificate-adapter"
    conformance_version = (
        certificate_checker.GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2
    )

    def attestation_ref_v2(self, issuer_ref: str, body_root: str) -> str:
        assert issuer_ref
        assert body_root
        return "attestation:permissive"

    def verifier_v2(self) -> CommitCertificateIssuerAttestationVerifierV2:
        return cast(CommitCertificateIssuerAttestationVerifierV2, _AlwaysVerifier())


class _RejectingCertificateAdapter(_PermissiveCertificateAdapter):
    implementation_id = "rejecting-certificate-adapter"

    def verifier_v2(self) -> CommitCertificateIssuerAttestationVerifierV2:
        return cast(CommitCertificateIssuerAttestationVerifierV2, _NeverVerifier())


class _UnknownVersionCertificateAdapter(_PermissiveCertificateAdapter):
    conformance_version = "pheroos-governance-commit-certificate-conformance-v999"


class _EmptyIdentityCertificateAdapter(_PermissiveCertificateAdapter):
    implementation_id = ""


class _ExplodingIdentityCertificateAdapter(_PermissiveCertificateAdapter):
    @property
    def implementation_id(self) -> str:
        raise LookupError("certificate identity unavailable")


class _ExplodingCertificateAdapter(_PermissiveCertificateAdapter):
    implementation_id = "exploding-certificate-adapter"

    def attestation_ref_v2(self, issuer_ref: str, body_root: str) -> str:
        raise RuntimeError(f"attestation unavailable:{issuer_ref}:{body_root}")


def test_permissive_certificate_verifier_cannot_bypass_canonical_integrity() -> None:
    result = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _PermissiveCertificateAdapter()
    )

    assert result == CheckResult("commit_certificate_v2_contract", True, "")


def test_commit_certificate_checker_reports_canonical_and_adapter_failures() -> None:
    rejected = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _RejectingCertificateAdapter()
    )
    unknown = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _UnknownVersionCertificateAdapter()
    )
    empty = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _EmptyIdentityCertificateAdapter()
    )
    identity = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _ExplodingIdentityCertificateAdapter()
    )
    execution = certificate_checker.run_governance_commit_certificate_conformance_v2(
        _ExplodingCertificateAdapter()
    )
    protocol = certificate_checker.run_governance_commit_certificate_conformance_v2(
        object()
    )

    assert rejected.detail == "canonical_round_trip"
    assert unknown.detail == "adapter_version"
    assert empty.detail == "adapter_implementation_id"
    assert identity.detail == "adapter_exception:LookupError"
    assert execution.detail.startswith("adapter_exception:RuntimeError:")
    assert protocol.detail == "adapter_protocol"


@dataclass(frozen=True)
class _ThresholdEnvelope:
    extensions: dict[str, object]
    threshold_root: str = ""


@dataclass(frozen=True)
class _SnapshotEnvelope:
    threshold: _ThresholdEnvelope
    snapshot_root: str = ""
    encoded_size: int = 0

    def canonical_bytes(self) -> bytes:
        return b"x" * self.encoded_size


@dataclass(frozen=True)
class _DiscardingThresholdEnvelope:
    extensions: dict[str, object]
    threshold_root: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "extensions", {})


@dataclass(frozen=True)
class _AssessmentEnvelope:
    assessment_ref: str
    assessment_root: str = ""


def test_risk_resource_checker_helpers_expose_both_totality_outcomes() -> None:
    assert risk_resource._rejects(lambda: 1) is False
    assert risk_resource._rejects(lambda: (_ for _ in ()).throw(ValueError("bad")))

    problems: list[str] = []

    def malformed_factory(
        _context: object,
        *,
        risk_input_roots: Sequence[str] = (),
        rationale_codes: Sequence[str] = (),
        source_trace_roots: Sequence[str] = (),
        **_kwargs: object,
    ) -> tuple[object, None]:
        assessment = SimpleNamespace(
            risk_input_roots=(),
            rationale_codes=(),
            source_trace_roots=(),
        )
        if (
            len(risk_input_roots) > 1
            or len(rationale_codes) > 1
            or len(source_trace_roots) > 1
        ):
            return SimpleNamespace(
                snapshot=SimpleNamespace(assessment=assessment)
            ), None
        return SimpleNamespace(snapshot=SimpleNamespace(assessment=assessment)), None

    risk_resource._collection_bounds(object(), malformed_factory, problems)

    assert {
        "resource_input_exact",
        "resource_input_over",
        "resource_rationale_exact",
        "resource_rationale_over",
        "resource_trace_exact",
        "resource_trace_over",
    } <= set(problems)


def test_risk_resource_checker_reports_nonrejecting_test_boundaries() -> None:
    assessment_problems: list[str] = []
    permissive_problems: list[str] = []
    discarding_problems: list[str] = []
    snapshot_problems: list[str] = []
    oversized_problems: list[str] = []
    base = SimpleNamespace(
        snapshot=SimpleNamespace(
            assessment=_AssessmentEnvelope("assessment:resource"),
        )
    )

    risk_resource._individual_text_bound(base, assessment_problems)
    risk_resource._portable_tree_bounds(
        _ThresholdEnvelope({}),
        permissive_problems,
    )
    risk_resource._portable_tree_bounds(
        _DiscardingThresholdEnvelope({}),
        discarding_problems,
    )
    risk_resource._snapshot_byte_bound(
        _SnapshotEnvelope(_ThresholdEnvelope({}), encoded_size=1),
        snapshot_problems,
    )
    risk_resource._snapshot_byte_bound(
        _SnapshotEnvelope(
            _ThresholdEnvelope({}),
            encoded_size=risk_resource.MAX_RISK_SNAPSHOT_BYTES_V2 + 1,
        ),
        oversized_problems,
    )

    assert assessment_problems == ["resource_text_over"]
    assert {
        "resource_depth_over",
        "resource_nodes_over",
        "resource_aggregate_text_over",
        "resource_cycle",
    } <= set(permissive_problems)
    assert {
        "resource_depth_exact",
        "resource_nodes_exact",
        "resource_aggregate_text_exact",
    } <= set(discarding_problems)
    assert {"resource_snapshot_exact", "resource_snapshot_over"} <= set(
        snapshot_problems
    )
    assert oversized_problems == ["resource_snapshot_fixture"]


def test_risk_integrity_shape_guards_name_the_rejected_wire_shape() -> None:
    snapshot_problems: list[str] = []
    record_problems: list[str] = []
    reordered_snapshot_problems: list[str] = []
    reordered_record_problems: list[str] = []
    reordered_array_problems: list[str] = []

    snapshot_request = SimpleNamespace(to_dict=lambda: {"snapshot": None})
    record_request = SimpleNamespace(
        to_dict=lambda: {"snapshot": {"assessment": None, "threshold": None}}
    )
    reordered_snapshot = SimpleNamespace(to_dict=lambda: {"snapshot": None})
    reordered_record = SimpleNamespace(
        to_dict=lambda: {"snapshot": {"assessment": None}}
    )
    reordered_array = SimpleNamespace(
        to_dict=lambda: {
            "snapshot": {
                "assessment": {
                    "risk_input_roots": None,
                    "rationale_codes": [],
                    "source_trace_roots": [],
                }
            }
        }
    )

    assert (
        risk_integrity._check_empty_root_rejection(
            object(), object(), snapshot_request, snapshot_problems
        )
        is False
    )
    assert (
        risk_integrity._check_empty_root_rejection(
            object(), object(), record_request, record_problems
        )
        is False
    )
    risk_integrity._check_reordered_array_rejection(
        object(), object(), reordered_snapshot, reordered_snapshot_problems
    )
    risk_integrity._check_reordered_array_rejection(
        object(), object(), reordered_record, reordered_record_problems
    )
    risk_integrity._check_reordered_array_rejection(
        object(), object(), reordered_array, reordered_array_problems
    )

    assert snapshot_problems == ["noncanonical_wire_snapshot_shape"]
    assert record_problems == ["noncanonical_wire_record_shape"]
    assert reordered_snapshot_problems == ["noncanonical_wire_reordered_snapshot_shape"]
    assert reordered_record_problems == ["noncanonical_wire_reordered_record_shape"]
    assert reordered_array_problems == ["noncanonical_wire_reordered_array_shape"]


def test_risk_integrity_mutator_rejects_missing_and_unknown_public_view_parts() -> None:
    with pytest.raises(
        ValueError, match="Risk v2 mutation requires a committed public view"
    ):
        risk_integrity._mutate_view(
            cast(Any, SimpleNamespace(committed_transition=None)), "inclusion"
        )

    transitionless = SimpleNamespace(
        batch=SimpleNamespace(transition=None, read_set=SimpleNamespace(entries=()))
    )
    with pytest.raises(ValueError, match="Risk v2 mutation requires transition state"):
        risk_integrity._mutate_view(
            cast(
                Any,
                SimpleNamespace(
                    committed_transition=transitionless,
                    position_observation=None,
                ),
            ),
            "state",
        )

    with pytest.raises(ValueError, match="unsupported Risk v2 detached-view mutation"):
        risk_integrity._mutate_view(
            cast(
                Any,
                SimpleNamespace(
                    committed_transition=transitionless,
                    position_observation=None,
                ),
            ),
            "unknown",
        )


def test_risk_position_mutator_handles_irrelevant_and_missing_observations() -> None:
    irrelevant = SimpleNamespace(
        transition_id="transition:other",
        position_observation=None,
    )
    risk_integrity._forge_parent_current(
        cast(Any, irrelevant),
        "transition:parent",
    )
    assert irrelevant.position_observation is None

    with pytest.raises(ValueError, match="Risk v2 position observation is absent"):
        risk_integrity._forge_parent_current(
            cast(
                Any,
                SimpleNamespace(
                    transition_id="transition:parent",
                    position_observation=None,
                ),
            ),
            "transition:parent",
        )


def _committed_risk_fixture(label: str) -> tuple[Any, Any]:
    context = risk_context.context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        label,
    )
    request, source = risk_context.request_v2(
        context,
        advance_ref=f"advance:{label}",
    )
    attempt = risk_context.advance_v2(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return context, request


def test_risk_integrity_checker_names_each_rejected_setup() -> None:
    noncanonical: list[str] = []
    risk_integrity._noncanonical_portable_wire(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                1,
                scope_suffix=":noncanonical-portable-wire",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        noncanonical,
    )

    detached: list[str] = []
    risk_integrity._detached_view_mutation(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                1,
                scope_suffix=":detached-inclusion",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        "inclusion",
        detached,
    )

    parent: list[str] = []
    child: list[str] = []
    risk_integrity._forged_current_position(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                1,
                scope_suffix=":forged-current-position",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        parent,
    )
    risk_integrity._forged_current_position(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                2,
                scope_suffix=":forged-current-position",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        child,
    )

    cross_domain: list[str] = []
    risk_integrity._cross_domain_rehydration(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:risk-v2:",
                1,
                scope_suffix=":rehydrate-domain",
            )
        ),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        cross_domain,
    )

    assert noncanonical == ["noncanonical_wire_setup"]
    assert detached == ["inclusion_setup"]
    assert parent == ["forged_position_parent_setup"]
    assert child == ["forged_position_child_setup"]
    assert cross_domain == ["cross_domain_setup"]


def test_risk_integrity_checker_names_a_retry_that_bypasses_public_view_checks() -> (
    None
):
    saved: GovernanceCommitAttemptV2 | None = None

    def return_saved_commit(context: Any, request: Any, source: object) -> Any:
        nonlocal saved
        if source is None:
            assert saved is not None
            return GovernanceCommitAttemptV2.from_dict(saved.to_dict())
        saved = risk_context.advance_v2(context, request, source)
        return saved

    problems: list[str] = []
    risk_integrity._detached_view_mutation(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        risk_context.context_v2,
        risk_context.request_v2,
        return_saved_commit,
        "inclusion",
        problems,
    )

    assert problems == ["inclusion_retry_not_typed_fail_closed"]


def test_risk_integrity_expectations_name_acceptance_wrong_code_and_zero_write() -> (
    None
):
    context, request = _committed_risk_fixture("integrity-expectations")
    foreign = risk_context.context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "integrity-expectations-foreign",
    )
    foreign_domain = replace(context, domain=foreign.domain)

    class ObservationProbe:
        def __init__(self, atomic_commits: int) -> None:
            self.atomic_commits = atomic_commits

        def reset_observations(self) -> None:
            return None

    accepted: list[str] = []
    risk_integrity._expect_portable_wire_rejection(
        context,
        ObservationProbe(1),
        request,
        request.to_dict(),
        "valid_wire",
        accepted,
    )
    diagnostic: list[str] = []
    risk_integrity._expect_portable_wire_rejection(
        foreign_domain,
        ObservationProbe(0),
        request,
        request.to_dict(),
        "wrong_domain",
        diagnostic,
    )

    valid_rehydrate: list[str] = []
    wrong_rehydrate: list[str] = []
    risk_integrity._expect_typed_rehydrate_failure(
        context,
        request,
        valid_rehydrate,
        "valid",
    )
    risk_integrity._expect_typed_rehydrate_failure(
        foreign_domain,
        request,
        wrong_rehydrate,
        "wrong_domain",
    )

    assert accepted == ["valid_wire_accepted", "valid_wire_zero_write"]
    assert diagnostic == ["wrong_domain_diagnostic"]
    assert valid_rehydrate == ["valid_rehydrate_not_fail_closed"]
    assert wrong_rehydrate == ["wrong_domain_rehydrate_diagnostic"]


def test_risk_integrity_checker_names_observable_post_commit_head_mutation() -> None:
    def increment_second_revision(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if "authority:risk-v2:" in stream_ref and head.revision >= 2:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    problems: list[str] = []
    risk_integrity._forged_current_position(
        _HeadFaultAdapter(increment_second_revision),
        risk_context.context_v2,
        risk_context.request_v2,
        risk_context.advance_v2,
        problems,
    )

    assert "forged_current_position_mutation" in problems


def test_risk_bool_epoch_guard_names_acceptance_and_observable_write() -> None:
    @dataclass(frozen=True)
    class ReplaceableRequest:
        epoch: int
        request_root: str
        scope_ref: str
        stream_ref: str

    request = ReplaceableRequest(
        epoch=1,
        request_root="sha256:" + "0" * 64,
        scope_ref="scope:risk-bool",
        stream_ref="authority:risk-v2:bool",
    )
    context = SimpleNamespace(
        store=SimpleNamespace(
            load_head_v2=lambda *_args: SimpleNamespace(revision=2),
        )
    )
    store = SimpleNamespace(atomic_commits=1)
    problems: list[str] = []

    risk_integrity._check_bool_epoch_rejection(
        context,
        store,
        request,
        problems,
    )

    assert problems == ["bool_epoch_exact_type", "bool_epoch_exact_type_zero_write"]


def test_risk_noncanonical_matrix_stops_after_a_malformed_snapshot_shape() -> None:
    @dataclass(frozen=True)
    class MalformedRequest:
        scope_ref: str
        epoch: int = 1
        request_root: str = "sha256:" + "0" * 64
        stream_ref: str = "authority:risk-v2:malformed"

        def to_dict(self) -> dict[str, object]:
            return {"snapshot": None}

    def request_factory(context: Any, **_kwargs: object) -> tuple[Any, object]:
        return MalformedRequest(scope_ref=context.domain.scope_ref), object()

    def committed_factory(*_args: object, **_kwargs: object) -> Any:
        return SimpleNamespace(disposition=GovernanceCommitDispositionV2.COMMITTED)

    problems: list[str] = []
    risk_integrity._noncanonical_portable_wire(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        risk_context.context_v2,
        request_factory,
        committed_factory,
        problems,
    )

    assert "noncanonical_wire_snapshot_shape" in problems


def test_risk_cross_domain_checker_names_same_domain_acceptance() -> None:
    context = risk_context.context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "same-domain-cross-check",
    )
    problems: list[str] = []

    risk_integrity._cross_domain_rehydration(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        lambda *_args, **_kwargs: context,
        risk_context.request_v2,
        risk_context.advance_v2,
        problems,
    )

    assert problems == ["cross_domain_rehydration"]


class _PublicStoreDelegate:
    state_store_version = "delegate-store-v2"

    def __init__(self) -> None:
        self.head = SimpleNamespace(revision=0, head_root="head:zero")
        self.state = {"state": "detached"}
        self.view = SimpleNamespace(
            committed_transition=None,
            position_observation=None,
        )
        self.attempt = SimpleNamespace(disposition="delegated")

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> Any:
        assert scope_ref == "scope:delegate"
        assert stream_ref == "stream:delegate"
        return self.head

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        assert scope_ref == "scope:delegate"
        assert stream_ref == "stream:delegate"
        return self.state

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        assert (scope_ref, stream_ref, transition_id, expected_receipt_root) == (
            "scope:delegate",
            "stream:delegate",
            "transition:delegate",
            None,
        )
        return self.view

    def atomic_commit_v2(self, batch: object) -> Any:
        assert batch == "batch:delegate"
        return self.attempt


def test_commit_gate_fault_reader_delegates_the_complete_store_protocol() -> None:
    delegate = _PublicStoreDelegate()
    reader = gate_adversarial.PublicCommitGateFaultStoreV2(
        cast(GovernanceStateStoreV2, delegate),
        "sha256:" + "0" * 64,
    )

    assert reader.state_store_version == "delegate-store-v2"
    assert reader.load_head_v2("scope:delegate", "stream:delegate") is delegate.head
    assert reader.load_state_v2("scope:delegate", "stream:delegate") is delegate.state
    assert (
        reader.load_commit_view_v2(
            "scope:delegate",
            "stream:delegate",
            "transition:delegate",
        )
        is delegate.view
    )
    assert reader.atomic_commit_v2(cast(Any, "batch:delegate")) is delegate.attempt

    gate_adversarial._remove_inclusion(cast(Any, delegate.view))
    gate_adversarial._forge_position(cast(Any, delegate.view))
    assert delegate.view.committed_transition is None
    assert delegate.view.position_observation is None


def test_commit_gate_rehydrate_probe_reports_a_valid_public_state() -> None:
    context = gate_context.commit_gate_context_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "rehydrate-success",
    )
    request, source = gate_context.prepare_permission_v2(
        context,
        "rehydrate-success",
    )
    committed = gate_context.issue_permission_v2(context, request, source)

    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert gate_adversarial._rehydrate_succeeds(
        context,
        context.store,
        request.to_dict(),
    )


def test_support_reader_override_delegates_non_view_store_operations() -> None:
    delegate = _PublicStoreDelegate()
    reader = support_finality._ReaderOverrideV2(
        cast(GovernanceStateStoreV2, delegate),
        "sha256:" + "0" * 64,
        "transition:delegate",
        mode="pass",
    )

    assert reader.state_store_version == "delegate-store-v2"
    assert reader.load_head_v2("scope:delegate", "stream:delegate") is delegate.head
    assert reader.load_state_v2("scope:delegate", "stream:delegate") is delegate.state
    assert reader.atomic_commit_v2("batch:delegate") is delegate.attempt


def test_support_reader_override_handles_irrelevant_and_missing_tamper_targets() -> (
    None
):
    delegate = _PublicStoreDelegate()
    missing = support_finality._ReaderOverrideV2(
        cast(GovernanceStateStoreV2, delegate),
        "sha256:" + "0" * 64,
        "transition:delegate",
        mode="tamper",
    )
    irrelevant = support_finality._ReaderOverrideV2(
        cast(GovernanceStateStoreV2, delegate),
        "sha256:" + "0" * 64,
        "transition:other",
        mode="tamper",
    )

    assert (
        missing.load_commit_view_v2(
            "scope:delegate",
            "stream:delegate",
            "transition:delegate",
        )
        is delegate.view
    )
    assert (
        irrelevant.load_commit_view_v2(
            "scope:delegate",
            "stream:delegate",
            "transition:delegate",
        )
        is delegate.view
    )


@pytest.mark.parametrize(
    "guard",
    [
        distributed_context._require_committed,
        distributed_decision._require_committed,
        distributed_input._require_committed,
    ],
)
def test_distributed_fixture_guards_reject_uncommitted_attempts(
    guard: Callable[[GovernanceCommitDispositionV2, str], None],
) -> None:
    with pytest.raises(
        RuntimeError, match="Distributed Commit v2 rejected setup failed"
    ):
        guard(GovernanceCommitDispositionV2.INVALID, "rejected")


@pytest.fixture(scope="module")
def distributed_vertical_fixture() -> Any:
    return distributed_checker.build_verified_distributed_vertical_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "totality-fixture",
    )


@pytest.fixture(scope="module")
def distributed_conflict_fixture(distributed_vertical_fixture: Any) -> Any:
    return distributed_checker.freeze_external_witness_conflict_v2(
        distributed_vertical_fixture,
        "totality-conflict",
    )


def test_distributed_vertical_checker_names_lane_and_stream_anomalies() -> None:
    duplicate_stream = "stream:distributed:duplicate"

    def state() -> Any:
        return SimpleNamespace(
            snapshot=SimpleNamespace(
                scope_ref="scope:distributed:malformed",
                protocol_ref="protocol:distributed:malformed",
                run_ref="run:distributed:malformed",
                target_ref="target:distributed:malformed",
                lane=object(),
                stream_ref=duplicate_stream,
                status=object(),
                revision=0,
            )
        )

    class MalformedVertical:
        epoch = state()
        proposal = state()
        witness = state()
        certificate = state()

        @property
        def epoch_request(self) -> Any:
            raise RuntimeError("stop after distributed state guards")

    problems: list[str] = []

    with pytest.raises(RuntimeError, match="stop after distributed state guards"):
        distributed_checker._evaluate_verified_vertical_v2(
            cast(Any, MalformedVertical()),
            problems,
        )

    assert "lane_currentness:proposal" in problems
    assert "four_fixed_streams" in problems


def test_distributed_vertical_checker_names_missing_public_view_and_trace(
    distributed_vertical_fixture: Any,
) -> None:
    epoch_transition_id = distributed_vertical_fixture.epoch_request.transition_id

    def remove_epoch_view(
        _scope_ref: str,
        _stream_ref: str,
        transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        if transition_id == epoch_transition_id:
            object.__setattr__(view, "committed_transition", None)
        return view

    store = _ViewFaultStore(
        distributed_vertical_fixture.context.store,
        remove_epoch_view,
    )
    context = replace(
        distributed_vertical_fixture.context,
        store=cast(GovernanceStateStoreV2, store),
    )
    malformed = replace(distributed_vertical_fixture, context=context)
    problems: list[str] = []

    distributed_checker._evaluate_verified_vertical_v2(malformed, problems)

    assert "committed_view_missing" in problems
    assert "four_lane_trace" in problems


def test_distributed_restart_checker_names_same_store_identity(
    distributed_vertical_fixture: Any,
) -> None:
    class SameStoreRestartAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
        def restart_store_v2(
            self,
            store: GovernanceStateStoreV2,
        ) -> GovernanceStateStoreV2:
            return store

    problems: list[str] = []
    distributed_checker._evaluate_restart_v2(
        SameStoreRestartAdapter(),
        distributed_vertical_fixture,
        problems,
    )

    assert problems == ["restart_store_identity"]


def test_distributed_lane_setup_guard_names_an_invalid_public_attempt(
    distributed_vertical_fixture: Any,
) -> None:
    request, _source = distributed_vertical.prepare_distributed_certificate_v2(
        decision_state=distributed_vertical_fixture.decision,
        central_certificate_state=distributed_vertical_fixture.central,
        membership_state=distributed_vertical_fixture.identity.membership,
        epoch_state=distributed_vertical_fixture.epoch,
        proposal_state=distributed_vertical_fixture.proposal,
        witness_state=distributed_vertical_fixture.witness,
        manifest=distributed_vertical_fixture.context.manifest,
        trusted_verifier=distributed_vertical_fixture.verifier,
        certificate_ref="certificate:distributed:invalid-source",
        provenance_ref="urn:pheroos:conformance:distributed:invalid-source",
        mutation_ref="mutation:distributed:invalid-source",
        mutation_issuer_ref=distributed_vertical_fixture.context.grant.issuer_ref,
        current_step=10,
        parent_state=distributed_vertical_fixture.certificate,
    )

    with pytest.raises(RuntimeError, match="Distributed Commit v2 lane setup failed"):
        distributed_vertical._advance_v2(
            distributed_vertical_fixture.context,
            request,
            object(),
        )


def test_finality_distributed_fixture_requires_a_committed_successor(
    distributed_vertical_fixture: Any,
) -> None:
    def reject_owner_successor(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        request = batch.transition.state_records.get("request", {})
        if "certificate-successor" in request.get("mutation_ref", ""):
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            object.__setattr__(attempt, "committed_transition", None)
        return attempt

    isolated_store = (
        ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
            distributed_vertical_fixture.context.store
        )
    )
    context = replace(
        distributed_vertical_fixture.context,
        store=cast(
            GovernanceStateStoreV2,
            _AttemptFaultStore(
                isolated_store,
                reject_owner_successor,
            ),
        ),
    )
    vertical = replace(distributed_vertical_fixture, context=context)

    with pytest.raises(RuntimeError, match="Distributed owner successor failed"):
        finality_distributed.advance_distributed_owner_successor_v2(
            vertical,
            "owner-failure",
        )


def test_distributed_input_checker_requires_collective_policy_before_replay() -> None:
    missing_policy = SimpleNamespace(
        manifest=SimpleNamespace(collective_commit_policy=None)
    )

    with pytest.raises(
        RuntimeError, match="Distributed Commit v2 policy is unavailable"
    ):
        distributed_input._replay_and_evidence_v2(
            cast(Any, missing_policy),
            cast(Any, object()),
            label="missing-policy",
            claim_root="sha256:" + "0" * 64,
        )


def test_distributed_conflict_checker_names_public_view_loss(
    distributed_conflict_fixture: Any,
) -> None:
    transition_id = distributed_conflict_fixture.witness_request.transition_id

    def remove_conflict_view(
        _scope_ref: str,
        _stream_ref: str,
        observed_transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        if observed_transition_id == transition_id:
            object.__setattr__(view, "committed_transition", None)
        return view

    wrapped = _ViewFaultStore(
        distributed_conflict_fixture.baseline.context.store,
        remove_conflict_view,
    )
    baseline_context = replace(
        distributed_conflict_fixture.baseline.context,
        store=cast(GovernanceStateStoreV2, wrapped),
    )
    baseline = replace(
        distributed_conflict_fixture.baseline,
        context=baseline_context,
    )
    conflict = replace(distributed_conflict_fixture, baseline=baseline)
    problems: list[str] = []

    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        distributed_checker._evaluate_conflict_vertical_v2(
            _ViewFaultAdapter(remove_conflict_view),
            conflict,
            problems,
        )

    assert "external_conflict_trace" in problems
    assert "external_conflict_exact_retry" in problems


def test_distributed_conflict_checker_names_noncurrent_nonfrozen_state(
    distributed_conflict_fixture: Any,
) -> None:
    conflict = replace(
        distributed_conflict_fixture,
        witness=distributed_conflict_fixture.baseline.witness,
    )
    problems: list[str] = []

    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        distributed_checker._evaluate_conflict_vertical_v2(
            ReferenceGovernanceStateStoreConformanceAdapterV2(),
            conflict,
            problems,
        )

    assert "external_conflict_freeze" in problems


def test_distributed_conflict_checker_names_authority_head_divergence(
    distributed_conflict_fixture: Any,
) -> None:
    proposal_stream = distributed_conflict_fixture.baseline.proposal.stream_ref

    def increment_proposal_head(
        _scope_ref: str,
        stream_ref: str,
        head: GovernanceHeadV2,
    ) -> GovernanceHeadV2:
        if stream_ref == proposal_stream:
            object.__setattr__(head, "revision", head.revision + 1)
        return head

    baseline = distributed_conflict_fixture.baseline
    isolated = ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
        baseline.context.store
    )
    context = replace(
        baseline.context,
        store=cast(
            GovernanceStateStoreV2,
            _HeadFaultStore(
                isolated,
                increment_proposal_head,
            ),
        ),
    )
    conflict = replace(
        distributed_conflict_fixture,
        baseline=replace(baseline, context=context),
    )
    problems: list[str] = []

    distributed_checker._evaluate_conflict_vertical_v2(
        _HeadFaultAdapter(increment_proposal_head),
        conflict,
        problems,
    )

    assert "external_conflict_advanced_authority" in problems


def test_distributed_conflict_decision_fixture_requires_a_committed_successor(
    distributed_conflict_fixture: Any,
) -> None:
    baseline = distributed_conflict_fixture.baseline
    isolated = ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
        baseline.context.store
    )

    def reject_decision_successor(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        request = batch.transition.state_records.get("request", {})
        if "conflict-decision" in request.get("mutation_ref", ""):
            object.__setattr__(
                attempt,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
        return attempt

    context = replace(
        baseline.context,
        store=cast(
            GovernanceStateStoreV2,
            _AttemptFaultStore(isolated, reject_decision_successor),
        ),
    )
    conflict = replace(
        distributed_conflict_fixture,
        baseline=replace(baseline, context=context),
    )

    with pytest.raises(
        RuntimeError,
        match="Distributed conflict Decision successor failed",
    ):
        distributed_vertical.advance_conflict_decision_v2(
            conflict,
            "decision-failure",
        )


def test_finality_certificate_fixture_requires_a_committed_owner() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:commit-certificate-v2:")
    )
    decision = finality_decision.certified_decision_vertical_v2(
        adapter,
        "certificate-owner-failure",
    )

    with pytest.raises(RuntimeError, match="Finality Certificate commit failed"):
        finality_certificate.verified_certificate_v2(
            decision,
            "certificate-owner-failure",
        )


def test_finality_fixture_guards_require_policy_and_committed_attempts() -> None:
    with pytest.raises(
        TypeError, match="finality conformance requires collective commit policy"
    ):
        finality_decision._manifest_with_assurance_v2(
            cast(Any, SimpleNamespace(collective_commit_policy=None)),
            assurance=cast(Any, "unused"),
            certificate_mode="unused",
        )

    with pytest.raises(RuntimeError, match="Finality Decision rejected failed"):
        finality_decision._require_committed(
            cast(
                Any,
                SimpleNamespace(
                    disposition=GovernanceCommitDispositionV2.INVALID,
                    failure=None,
                ),
            ),
            "rejected",
        )


def test_finality_expectation_helpers_name_retry_and_outcome_divergence() -> None:
    retry: list[str] = []
    finality_checker._expect_retry_v2(
        cast(
            Any,
            SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                failure=None,
            ),
        ),
        retry,
        "invalid_retry",
    )
    outcome: list[str] = []
    finality_checker._expect_outcome_v2(
        cast(
            Any,
            SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                committed_transition=None,
            ),
        ),
        cast(Any, SimpleNamespace(snapshot=SimpleNamespace(outcome=None))),
        cast(Any, object()),
        outcome,
        "invalid_outcome",
    )

    assert retry == ["invalid_retry"]
    assert outcome == ["invalid_outcome"]


def test_commit_replay_resource_helpers_cover_success_and_exhaustion() -> None:
    context = replay_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "resource-helper-totality",
    )
    baseline, _ = replay_checker._request(
        context,
        advance_ref="advance:resource-helper-totality",
        receipt=None,
        current_step=1,
    )
    receipt = replay_checker._receipt(1, suffix=":resource-helper")

    assert replay_resource._allocate_text([[4096]], 1) is False
    assert (
        replay_resource._prepare_error(
            baseline,
            "advance:resource-helper-valid",
            (receipt,),
        )
        is None
    )
    assert replay_resource._snapshot_error(baseline.snapshot.to_dict()) is None
    assert (
        replay_resource._snapshot_replace_error(
            baseline.snapshot,
            baseline.snapshot.receipts,
        )
        is None
    )


def test_hybrid_resource_helpers_report_missing_vectors_and_late_acceptance() -> None:
    context = hybrid_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "resource-helper-totality",
    )
    source = hybrid_checker._source(context, current_step=1)
    request = hybrid_checker._request(
        context,
        source,
        "advance:resource-helper-totality",
        observed_epoch=3,
    )
    payload = request.snapshot.to_dict()
    later: list[str] = []
    resource: list[str] = []
    vectors: list[str] = []

    assert hybrid_resource._snapshot_error(payload) is None
    hybrid_resource._expect_later_error(
        payload,
        "an error that a valid snapshot cannot contain",
        "later_acceptance",
        later,
    )
    hybrid_resource._expect_resource_error(
        payload,
        "an error that a valid snapshot cannot contain",
        "resource_acceptance",
        resource,
    )
    hybrid_resource._check_aggregate_causal_bound(
        {**payload, "replay_receipts": []},
        vectors,
    )
    hybrid_resource._check_final_snapshot_bound(
        {**payload, "active_trails": []},
        vectors,
    )
    usage = hybrid_resource._ResourceUsageV2()
    hybrid_resource._walk_resource(
        {1: "value"},
        depth=0,
        lineage=False,
        usage=usage,
    )

    assert later == ["later_acceptance"]
    assert resource == ["resource_acceptance"]
    assert vectors == ["resource_causal_vector", "resource_snapshot_vector"]
    assert usage.nodes == 3
    assert usage.text_bytes == len("value")


def _committed_hybrid_fixture(label: str) -> tuple[Any, Any, Any]:
    context = hybrid_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        label,
    )
    source = hybrid_checker._source(context, current_step=1)
    request = hybrid_checker._request(
        context,
        source,
        f"advance:{label}",
        observed_epoch=3,
    )
    attempt = hybrid_checker._advance(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return context, request, source


def test_hybrid_context_requires_committed_grant_activation() -> None:
    adapter = _AttemptFaultAdapter(
        _reject_matching_attempt("transition:grant-activation")
    )

    with pytest.raises(
        ValueError, match="Hybrid Replay conformance grant activation failed"
    ):
        hybrid_checker._context(adapter, "grant-failure")


@pytest.mark.parametrize(
    ("occurrence", "problem"),
    [
        (1, "genesis_commit"),
        (2, "restart_child_commit"),
        (3, "concurrent_fork_is_retry"),
    ],
)
def test_hybrid_vertical_checker_names_store_response_divergence(
    occurrence: int,
    problem: str,
) -> None:
    adapter = _AttemptFaultAdapter(
        _reject_nth_attempt(
            "transition:hybrid-replay-v2:",
            occurrence,
            scope_suffix=":vertical",
        )
    )
    problems: list[str] = []

    hybrid_checker._evaluate_vertical_restart_and_fork(adapter, problems)

    assert problem in problems


def test_hybrid_vertical_checker_names_invalid_exact_retry_view() -> None:
    def remove_child_inclusion(
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        view: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        committed = view.committed_transition
        if (
            committed is not None
            and committed.batch.transition.state_records["request"]["advance_ref"]
            == "advance:child-a"
        ):
            object.__setattr__(view, "committed_transition", None)
        return view

    problems: list[str] = []
    hybrid_checker._evaluate_vertical_restart_and_fork(
        _ViewFaultAdapter(remove_child_inclusion),
        problems,
    )

    assert "exact_retry_reconciliation" in problems


def test_hybrid_vertical_checker_detects_returned_read_set_and_trace_tamper() -> None:
    def corrupt_returned_hybrid(
        batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        if (
            batch.scope_ref.endswith(":vertical")
            and "transition:hybrid-replay-v2:" in batch.transition_id
            and attempt.committed_transition is not None
        ):
            returned_batch = attempt.committed_transition.batch
            object.__setattr__(returned_batch.read_set, "entries", ())
            event = returned_batch.trace_batch.events[0]
            object.__setattr__(event, "event_type", "hybrid_replay_tampered")
        return attempt

    problems: list[str] = []
    hybrid_checker._evaluate_vertical_restart_and_fork(
        _AttemptFaultAdapter(corrupt_returned_hybrid),
        problems,
    )

    assert "complete_authority_read_set" in problems
    assert "atomic_trace_lineage" in problems


def test_hybrid_determinism_checker_names_commit_and_root_divergence() -> None:
    rejected: list[str] = []
    hybrid_checker._evaluate_deterministic_transcript(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:hybrid-replay-v2:",
                1,
                scope_suffix=":deterministic",
            )
        ),
        rejected,
    )

    calls = 0

    def change_second_root(
        _batch: GovernanceCommitBatchV2,
        attempt: GovernanceCommitAttemptV2,
    ) -> GovernanceCommitAttemptV2:
        nonlocal calls
        calls += 1
        if calls == 2 and attempt.committed_transition is not None:
            object.__setattr__(
                attempt.committed_transition.batch,
                "batch_root",
                "sha256:" + "f" * 64,
            )
        return attempt

    divergent: list[str] = []
    hybrid_checker._evaluate_deterministic_transcript(
        _AttemptFaultAdapter(change_second_root),
        divergent,
    )

    assert rejected == ["deterministic_commit"]
    assert divergent == ["deterministic_roots"]


def test_hybrid_public_checker_names_rejected_finality_and_historical_setups() -> None:
    parent: list[str] = []

    def reject_parent(context: Any, request: Any, source: object) -> Any:
        attempt = hybrid_checker._advance(context, request, source)
        if request.advance_ref == "advance:public-parent-finality:1":
            detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
            object.__setattr__(
                detached,
                "disposition",
                GovernanceCommitDispositionV2.INVALID,
            )
            return detached
        return attempt

    hybrid_public._evaluate_public_finality_and_reconciliation(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        hybrid_checker._context,
        hybrid_checker._source,
        hybrid_checker._request,
        reject_parent,
        parent,
    )

    def reject_all(context: Any, request: Any, source: object) -> Any:
        attempt = hybrid_checker._advance(context, request, source)
        detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
        object.__setattr__(
            detached,
            "disposition",
            GovernanceCommitDispositionV2.INVALID,
        )
        return detached

    historical: list[str] = []
    hybrid_public._evaluate_public_historical_integrity(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        hybrid_checker._context,
        hybrid_checker._source,
        hybrid_checker._request,
        reject_all,
        historical,
    )

    assert parent == ["parent_finality_setup"]
    assert "public-read-set-state-missing_setup" in historical
    assert "public-canonical-view-inclusion_delete_setup" in historical
    assert "trace_read_set_root_setup" in historical


def test_hybrid_lost_response_checker_names_a_divergent_store_response() -> None:
    problems: list[str] = []
    hybrid_public._evaluate_lost_response_reconciliation(
        _AttemptFaultAdapter(
            _reject_nth_attempt(
                "transition:hybrid-replay-v2:",
                1,
                scope_suffix=":public-lost-response",
            )
        ),
        hybrid_checker._context,
        hybrid_checker._source,
        hybrid_checker._request,
        problems,
    )

    assert "post_publication_lost_response" in problems


def test_hybrid_public_mutators_and_rehydration_expectations_are_total() -> None:
    context, request, _source = _committed_hybrid_fixture("public-mutators")
    view = context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )

    with pytest.raises(ValueError, match="unknown public read-set mutation"):
        hybrid_public._mutate_read_set(
            view,
            request,
            "state",
            "unknown",
        )
    with pytest.raises(ValueError, match="unknown public canonical-view mutation"):
        hybrid_public._canonical_view_mutator("unknown")(view)

    malformed: list[str] = []
    accepted: list[str] = []
    hybrid_public._expect_invalid_rehydration(
        SimpleNamespace(domain=object(), store=object()),
        cast(Any, SimpleNamespace(to_dict=lambda: None)),
        "malformed",
        malformed,
    )
    hybrid_public._expect_invalid_rehydration(
        context,
        request,
        "accepted",
        accepted,
    )

    assert malformed == ["malformed"]
    assert accepted == ["accepted"]


def test_hybrid_binding_expectation_names_a_non_attempt() -> None:
    problems: list[str] = []

    hybrid_checker._expect_binding_rejection(
        cast(Any, SimpleNamespace()),
        "missing_attempt_shape",
        problems,
    )

    assert problems == ["missing_attempt_shape"]


def test_hybrid_resource_checker_names_hostile_vector_and_store_anomalies() -> None:
    context = hybrid_checker._context(
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        "hostile-resource-vectors",
    )
    source = hybrid_checker._source(context, current_step=1)
    request = hybrid_checker._request(
        context,
        source,
        "advance:hostile-resource-vectors",
        observed_epoch=3,
    )
    payload = request.snapshot.to_dict()
    payload["candidate_projection"] = hybrid_resource._nested_lists(70)
    payload["topology_projection"] = [None] * (
        hybrid_resource._MAX_RESOURCE_NODES_V2 + 1
    )
    payload["source_trace_roots"] = [
        "x" * (hybrid_resource._MAX_RESOURCE_TEXT_BYTES_V2 + 1)
    ]
    payload["active_trails"] = []
    payload["replay_receipts"] = []

    class DivergentHeadStore:
        atomic_commits = 0

        def __init__(self) -> None:
            self._read = 0

        def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
            self._read += 1
            return SimpleNamespace(
                revision=self._read - 1, head_root=f"head:{self._read}"
            )

        def reset_observations(self) -> None:
            self.atomic_commits = 1

    problems = hybrid_resource.run_public_hybrid_replay_resource_matrix_v2(
        context=context,
        store=DivergentHeadStore(),
        source_factory=lambda *_args, **_kwargs: object(),
        request_factory=lambda *_args, **_kwargs: SimpleNamespace(
            snapshot=SimpleNamespace(to_dict=lambda: payload),
            scope_ref="scope:hostile",
            stream_ref="stream:hostile",
        ),
    )

    assert {
        "resource_rejection_zero_write",
        "resource_depth_vector",
        "resource_node_vector",
        "resource_text_vector",
        "resource_lineage_vector",
        "resource_causal_vector",
        "resource_snapshot_vector",
    } <= set(problems)


def test_hybrid_snapshot_resource_checker_names_malformed_active_trails() -> None:
    context, request, _source = _committed_hybrid_fixture("malformed-active-trails")
    payload = request.snapshot.to_dict()
    template = dict(payload["active_trails"][0])
    del template["candidate_ref"]
    payload["active_trails"] = [template]
    problems: list[str] = []

    hybrid_resource._check_final_snapshot_bound(payload, problems)

    assert problems == ["resource_snapshot_vector"]


def test_state_store_conformance_protocol_version_constant_is_exact() -> None:
    assert GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2 == (
        "pheroos-governance-state-store-conformance-v2"
    )
    assert issubclass(
        ReferenceGovernanceStateStoreConformanceAdapterV2,
        ReferenceGovernanceStateStoreConformanceAdapterV2,
    )
    assert GovernanceCommitAttemptV2 is not GovernanceStateStoreV2
