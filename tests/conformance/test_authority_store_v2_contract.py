from __future__ import annotations

import ast
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Any, Callable, cast

import pytest

import pheroos.conformance.authority_store_v2_spec_adapter as spec_adapter
from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2,
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks import authority_store_v2_contract
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
    GOVERNANCE_STATE_STORE_TAMPER_CASES_V2,
    GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
    GovernanceStateStoreConformanceAdapterV2,
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    run_governance_state_store_conformance_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceFailureStageV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


ROOT = Path(__file__).resolve().parents[2]
SPEC_ADAPTER = ROOT / "pheroos" / "conformance" / "authority_store_v2_spec_adapter.py"


def _sealed_independent_image() -> dict[str, Any]:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:restart-image-validation"
    stream_ref = "authority:restart-image-validation"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )
    for revision in (1, 2):
        batch = authority_store_v2_contract._transition_batch(
            adapter,
            store,
            scope_ref,
            stream_ref,
            f"transition:restart-image-validation:{revision}",
            revision,
        )
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
    seal = authority_store_v2_contract._seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:restart-image-validation:seal",
        streams=(stream_ref,),
    )
    assert (
        store.atomic_commit_v2(seal).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    return cast(dict[str, Any], store._export_image())


ImageMutator = Callable[[dict[str, Any]], None]
ObservationMutator = Callable[[dict[str, object], int], None]


def _set_image_value(
    image: dict[str, Any],
    *,
    field: str,
    value: object,
) -> None:
    image[field] = value


def _replace_only_mapping_key(
    image: dict[str, Any],
    *,
    section: str,
    replacement_key: object,
) -> None:
    mapping = cast(dict[str, object], image[section])
    image[section] = {replacement_key: next(iter(mapping.values()))}


def _duplicate_first_image_entry(
    image: dict[str, Any],
    *,
    section: str,
) -> None:
    entries = cast(list[object], image[section])
    entries.append(deepcopy(entries[0]))


def _set_first_image_entry_field(
    image: dict[str, Any],
    *,
    section: str,
    field: str,
    value: object,
) -> None:
    entries = cast(list[dict[str, object]], image[section])
    entries[0][field] = value


def _remove_first_image_entry_field(
    image: dict[str, Any],
    *,
    section: str,
    field: str,
) -> None:
    entries = cast(list[dict[str, object]], image[section])
    entries[0].pop(field)


def _duplicate_first_commit_order(image: dict[str, Any]) -> None:
    orders = cast(dict[str, list[str]], image["commit_order"])
    order = next(iter(orders.values()))
    order.append(order[0])


def _reorder_first_two_commits(image: dict[str, Any]) -> None:
    orders = cast(dict[str, list[str]], image["commit_order"])
    order = next(iter(orders.values()))
    order[0], order[1] = order[1], order[0]


def _set_observation_field(
    observed: dict[str, object],
    _call: int,
    *,
    field: str,
    value: object,
) -> None:
    observed[field] = value


def _increment_observation_field_on_second_call(
    observed: dict[str, object],
    call: int,
    *,
    field: str,
) -> None:
    if call == 2:
        observed[field] = cast(int, observed[field]) + 1


def _mutate_restart_observation(
    observed: dict[str, object],
    call: int,
) -> None:
    if call == 1:
        observed["commit_order"] = tuple(
            reversed(cast(tuple[str, ...], observed["commit_order"]))
        )
        return
    observed["heads"] = cast(int, observed["heads"]) + 1


_PARTIAL_OBSERVATION_MUTATORS: dict[str, ObservationMutator] = {
    "scope:conformance:fresh": partial(
        _set_observation_field,
        field="heads",
        value=1,
    ),
    "scope:conformance:unknown": partial(
        _increment_observation_field_on_second_call,
        field="heads",
    ),
    "scope:conformance:multi-read": partial(
        _increment_observation_field_on_second_call,
        field="states",
    ),
    "scope:conformance:concurrent-same": partial(
        _set_observation_field,
        field="transition_ids",
        value=2,
    ),
    "scope:conformance:concurrent-conflict": partial(
        _set_observation_field,
        field="receipts",
        value=2,
    ),
    "scope:conformance:seal": partial(
        _increment_observation_field_on_second_call,
        field="states",
    ),
    "scope:conformance:stream-bound": partial(
        _increment_observation_field_on_second_call,
        field="heads",
    ),
    "scope:conformance:seal-race": partial(
        _set_observation_field,
        field="transition_ids",
        value=2,
    ),
    "scope:conformance:restart": _mutate_restart_observation,
}


class _PartialPublicationObservationAdapter(
    IndependentStdlibGovernanceStateStoreV2Adapter
):
    implementation_id = "partial-publication-observation-v2"

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def observe_store_v2(self, store, scope_ref):  # type: ignore[no-untyped-def]
        observed = dict(super().observe_store_v2(store, scope_ref))
        call = self.calls.get(scope_ref, 0) + 1
        self.calls[scope_ref] = call
        mutator = _PARTIAL_OBSERVATION_MUTATORS.get(scope_ref)
        if mutator is not None:
            mutator(observed, call)
        if scope_ref.startswith("scope:conformance:failure:"):
            _increment_observation_field_on_second_call(
                observed,
                call,
                field="heads",
            )
        return observed


class _InvalidFreshStore(IndependentStdlibGovernanceStateStoreV2):
    @property
    def state_store_version(self) -> str:
        return "pheroos-governance-state-store-v999"

    def load_state_v2(self, scope_ref, stream_ref):  # type: ignore[no-untyped-def]
        if scope_ref == "scope:conformance:fresh" and stream_ref == "authority:fresh":
            return {"unexpected": "preexisting-state"}
        return super().load_state_v2(scope_ref, stream_ref)


class _InvalidFreshStoreAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
    implementation_id = "invalid-fresh-store-v2"

    def create_store_v2(self, domains):  # type: ignore[no-untyped-def]
        return _InvalidFreshStore(domains)

    def observe_store_v2(self, store, scope_ref):  # type: ignore[no-untyped-def]
        if isinstance(store, _InvalidFreshStore):
            return store._observation(scope_ref)
        return super().observe_store_v2(store, scope_ref)

    def restart_store_v2(self, store):  # type: ignore[no-untyped-def]
        if isinstance(store, _InvalidFreshStore):
            return IndependentStdlibGovernanceStateStoreV2._from_image(
                store._export_image()
            )
        return super().restart_store_v2(store)

    def tamper_store_v2(  # type: ignore[no-untyped-def]
        self,
        store,
        scope_ref,
        transition_id,
        case,
    ):
        if isinstance(store, _InvalidFreshStore):
            store._tamper(scope_ref, transition_id, case)
            return
        super().tamper_store_v2(store, scope_ref, transition_id, case)


def test_independent_stdlib_adapter_passes_the_complete_v2_matrix() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = run_governance_state_store_conformance_v2(adapter)

    assert result.name == "authority_store_v2_contract"
    assert result.ok is True, result.detail
    assert result.detail == ""


def test_reference_store_passes_the_same_complete_v2_matrix() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapterV2)
    result = run_governance_state_store_conformance_v2(adapter)

    assert result.ok is True, result.detail


def test_v2_conformance_identifiers_and_failure_boundaries_are_exact() -> None:
    assert (
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2
        == "pheroos-governance-state-store-conformance-v2"
    )
    assert GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2 == (
        "before_validation",
        "after_identity_reconciliation",
        "after_read_set_validation",
        "after_state_head_staging",
        "after_trace_staging",
        "after_receipt_inclusion_staging",
        "after_atomic_publication",
    )
    assert GOVERNANCE_STATE_STORE_TAMPER_CASES_V2 == (
        "batch_payload",
        "batch_root",
        "receipt_payload",
        "receipt_root",
        "inclusion_payload",
        "inclusion_root",
        "head_payload",
        "head_root",
        "state_payload",
        "state_root",
        "trace_payload",
        "trace_root",
        "scope_binding",
        "stream_binding",
        "revision_binding",
        "seal_payload",
        "seal_root",
        "lifecycle_state",
        "transition_index",
        "seal_marker",
        "projection_removal",
        "sequence_binding",
        "cross_stream_order",
        "history_payload",
    )


def test_v2_conformance_rejects_incomplete_and_unknown_adapters() -> None:
    class Incomplete:
        implementation_id = "incomplete-v2"

    incomplete = run_governance_state_store_conformance_v2(cast(Any, Incomplete()))
    assert incomplete.ok is False
    assert incomplete.detail == "adapter_protocol"

    class UnknownVersion(IndependentStdlibGovernanceStateStoreV2Adapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    unknown = run_governance_state_store_conformance_v2(UnknownVersion())
    assert unknown.ok is False
    assert unknown.detail == "adapter_version"


def test_v2_conformance_is_total_at_a_third_party_adapter_boundary() -> None:
    class ExplodingAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "exploding-independent-store-v2"

        def create_store_v2(self, domains):  # type: ignore[no-untyped-def]
            raise RuntimeError("adapter is unavailable")

    result = authority_store_v2_contract.check(ExplodingAdapter())

    assert result.ok is False
    assert result.detail.startswith("adapter_exception:RuntimeError:")


def test_independent_model_imports_only_public_authority_and_trace_contracts() -> None:
    tree = ast.parse(SPEC_ADAPTER.read_text(encoding="utf-8"))
    project_imports: set[str] = set()
    defined_classes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            project_imports.update(
                alias.name for alias in node.names if alias.name.startswith("pheroos")
            )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith("pheroos"):
                project_imports.add(node.module)
        elif isinstance(node, ast.ClassDef):
            defined_classes.add(node.name)

    assert project_imports == {
        "pheroos.governance.authority_store_v2",
        "pheroos.protocol.authority_v2",
        "pheroos.trace",
    }
    assert "TraceEvent" not in defined_classes
    assert all("._" not in module for module in project_imports)


def test_independent_model_does_not_import_or_delegate_to_reference_store() -> None:
    source = SPEC_ADAPTER.read_text(encoding="utf-8")

    assert "InMemoryGovernanceStateStoreV2" not in source
    assert "pheroos.governance._" not in source
    assert "pheroos.conformance.checks" not in source
    assert "root_v2(" not in source


def test_v2_matrix_rejects_wrong_injected_failure_stage() -> None:
    class WrongStageStore(IndependentStdlibGovernanceStateStoreV2):
        def _unavailable_attempt(self, batch, stage):  # type: ignore[no-untyped-def]
            return super()._unavailable_attempt(
                batch,
                GovernanceFailureStageV2.FINALITY,
            )

    class WrongStageAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "wrong-failure-stage-v2"

        def create_failure_injected_store_v2(self, stage, domains):  # type: ignore[no-untyped-def]
            return WrongStageStore(domains, failure_stage=stage)

        def observe_store_v2(self, store, scope_ref):  # type: ignore[no-untyped-def]
            if isinstance(store, WrongStageStore):
                return store._observation(scope_ref)
            return super().observe_store_v2(store, scope_ref)

    problems: list[str] = []
    authority_store_v2_contract._evaluate_failure_boundaries(
        WrongStageAdapter(),
        problems,
    )

    assert "failure_result:before_validation" in problems
    assert "failure_result:after_identity_reconciliation" in problems


def test_v2_matrix_rejects_state_dependent_inconsistent_fingerprint(
    monkeypatch: Any,
) -> None:
    class FabricatedFingerprintAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "fabricated-image-fingerprint-v2"

        def observe_store_v2(self, store, scope_ref):  # type: ignore[no-untyped-def]
            observed = dict(super().observe_store_v2(store, scope_ref))
            if observed["states"]:
                observed["image_fingerprint"] = "sha256:" + "f" * 64
            return observed

    monkeypatch.setattr(
        authority_store_v2_contract,
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ("batch_payload",),
    )
    problems: list[str] = []
    authority_store_v2_contract._evaluate_persisted_artifact_mutations(
        FabricatedFingerprintAdapter(),
        problems,
    )

    assert any(
        item.startswith("observation_fingerprint_mismatch:tamper:batch_payload")
        for item in problems
    )


def test_v2_matrix_rejects_adapter_that_skips_required_tamper(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class SkippedTamperAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "skipped-required-tamper-v2"

        def tamper_store_v2(  # type: ignore[no-untyped-def]
            self,
            store,
            scope_ref,
            transition_id,
            case,
        ):
            return None

    monkeypatch.setattr(
        authority_store_v2_contract,
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ("batch_payload",),
    )
    problems: list[str] = []
    authority_store_v2_contract._evaluate_persisted_artifact_mutations(
        SkippedTamperAdapter(),
        problems,
    )

    assert "tamper_fingerprint_unchanged:batch_payload" in problems
    assert "tamper_view:batch_payload" in problems
    assert "tamper_retry:batch_payload" in problems


def test_independent_history_only_corruption_changes_image_and_is_typed() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:history-only"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )
    batch = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:history",
        "transition:history-only",
        1,
    )
    committed = store.atomic_commit_v2(batch)
    assert committed.committed_transition is not None
    receipt = committed.committed_transition.receipt
    current_before = store._committed[
        (scope_ref, batch.transition_id)
    ].canonical_bytes()
    history_key = (scope_ref, batch.stream_ref, receipt.revision)
    history_before = store._history[history_key].canonical_bytes()
    observed_before = dict(adapter.observe_store_v2(store, scope_ref))

    adapter.tamper_store_v2(
        store,
        scope_ref,
        batch.transition_id,
        "history_payload",
    )

    observed_after = dict(adapter.observe_store_v2(store, scope_ref))
    assert store._committed[(scope_ref, batch.transition_id)].canonical_bytes() == (
        current_before
    )
    assert store._history[history_key].canonical_bytes() != history_before
    assert observed_after["image_bytes"] != observed_before["image_bytes"]
    assert observed_after["image_fingerprint"] != observed_before["image_fingerprint"]
    view = store.load_commit_view_v2(
        scope_ref,
        batch.stream_ref,
        batch.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    assert view.failure is not None
    assert (
        view.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    retry = store.atomic_commit_v2(batch)
    assert retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retry.failure is not None
    assert retry.failure.stage is GovernanceFailureStageV2.RECONCILIATION


def test_independent_validation_fingerprint_cache_is_private_and_invalidated() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:validation-fingerprint"
    stream_ref = "authority:validation-fingerprint"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )
    first = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:validation-fingerprint:1",
        1,
    )
    assert (
        store.atomic_commit_v2(first).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert scope_ref not in store._validated_image_fingerprints

    view = store.load_commit_view_v2(scope_ref, stream_ref, first.transition_id)
    assert view.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert scope_ref in store._validated_image_fingerprints
    assert "validated_image_fingerprints" not in store._export_image()

    restored = IndependentStdlibGovernanceStateStoreV2._from_image(
        store._export_image()
    )
    assert scope_ref in restored._validated_image_fingerprints
    second = authority_store_v2_contract._transition_batch(
        adapter,
        restored,
        scope_ref,
        stream_ref,
        "transition:validation-fingerprint:2",
        2,
    )
    assert (
        restored.atomic_commit_v2(second).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert scope_ref not in restored._validated_image_fingerprints

    restored.load_commit_view_v2(scope_ref, stream_ref, second.transition_id)
    assert scope_ref in restored._validated_image_fingerprints
    adapter.tamper_store_v2(
        restored,
        scope_ref,
        second.transition_id,
        "state_payload",
    )
    assert scope_ref not in restored._validated_image_fingerprints


def test_independent_validation_fingerprint_detects_raw_orphan_commit(
    monkeypatch: Any,
) -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:validation-fingerprint-orphan"
    stream_ref = "authority:validation-fingerprint-orphan"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )
    batch = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:validation-fingerprint-orphan",
        1,
    )
    assert (
        store.atomic_commit_v2(batch).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    full_validations = 0
    original = spec_adapter._validate_store_image

    def counted_validation(*args: Any, **kwargs: Any) -> None:
        nonlocal full_validations
        full_validations += 1
        original(*args, **kwargs)

    monkeypatch.setattr(spec_adapter, "_validate_store_image", counted_validation)
    first = store.load_commit_view_v2(scope_ref, stream_ref, batch.transition_id)
    second = store.load_commit_view_v2(scope_ref, stream_ref, batch.transition_id)
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert second.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert full_validations == 1

    store._committed[(scope_ref, "transition:unindexed-orphan")] = store._committed[
        (scope_ref, batch.transition_id)
    ]
    corrupted = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        batch.transition_id,
    )
    assert full_validations == 2
    assert corrupted.disposition is GovernanceCommitDispositionV2.INVALID
    assert scope_ref not in store._validated_image_fingerprints


@pytest.mark.parametrize(
    "case",
    ("domain", "history", "trace", "transition_index", "commit_order"),
)
def test_independent_validation_fingerprint_rejects_direct_mutation(
    case: str,
) -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = f"scope:conformance:validation-fingerprint-direct:{case}"
    stream_ref = "authority:validation-fingerprint-direct"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )
    batch = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        f"transition:validation-fingerprint-direct:{case}",
        1,
    )
    attempt = store.atomic_commit_v2(batch)
    assert attempt.committed_transition is not None
    committed = attempt.committed_transition
    first = store.load_commit_view_v2(scope_ref, stream_ref, batch.transition_id)
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    validated_fingerprint = store._validated_image_fingerprints[scope_ref]
    zero_root = "sha256:" + "0" * 64

    if case == "domain":
        object.__setattr__(store._domains[scope_ref], "domain_root", zero_root)
    elif case == "history":
        history_key = (scope_ref, stream_ref, committed.receipt.revision)
        object.__setattr__(
            store._history[history_key].receipt,
            "parent_root",
            zero_root,
        )
    elif case == "trace":
        object.__setattr__(
            store._trace_batches[(scope_ref, batch.transition_id)],
            "trace_root",
            zero_root,
        )
    elif case == "transition_index":
        store._transition_index[(scope_ref, batch.transition_id)] = True
    else:
        store._commit_order[scope_ref].append("transition:unindexed-order")

    assert (
        spec_adapter._validation_image_fingerprint(store, scope_ref)
        != validated_fingerprint
    )
    corrupted = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        batch.transition_id,
    )
    assert corrupted.disposition is not GovernanceCommitDispositionV2.COMMITTED
    assert scope_ref not in store._validated_image_fingerprints


def test_independent_restart_rejects_every_orphan_scope_section() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    base = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(
            adapter,
            "scope:conformance:registered",
        ),
    )
    orphan_scope = "scope:conformance:orphan"
    orphan = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, orphan_scope),
    )
    ordinary = authority_store_v2_contract._transition_batch(
        adapter,
        orphan,
        orphan_scope,
        "authority:orphan",
        "transition:orphan",
        1,
    )
    assert (
        orphan.atomic_commit_v2(ordinary).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    seal = authority_store_v2_contract._seal_batch(
        adapter,
        orphan,
        orphan_scope,
        "transition:orphan:seal",
        streams=(ordinary.stream_ref,),
    )
    assert (
        orphan.atomic_commit_v2(seal).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    base_image = base._export_image()
    orphan_image = orphan._export_image()
    sections = (
        "heads",
        "states",
        "committed",
        "history",
        "trace_batches",
        "seals",
        "transition_index",
        "commit_order",
    )
    for section in sections:
        image = deepcopy(base_image)
        image[section] = deepcopy(orphan_image[section])
        with pytest.raises(ValueError, match="orphan scope"):
            IndependentStdlibGovernanceStateStoreV2._from_image(image)


def test_v2_matrix_rejects_restart_that_mutates_source_before_raise(
    monkeypatch: Any,
) -> None:
    class MutatingRestartAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "mutating-restart-instrumentation-v2"

        def restart_store_v2(self, store):  # type: ignore[no-untyped-def]
            assert isinstance(store, IndependentStdlibGovernanceStateStoreV2)
            key = next(iter(store._states))
            store._states[key]["restart_mutation"] = True
            raise ValueError("corrupt image rejected after source mutation")

    monkeypatch.setattr(
        authority_store_v2_contract,
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ("batch_payload",),
    )
    problems: list[str] = []
    authority_store_v2_contract._evaluate_persisted_artifact_mutations(
        MutatingRestartAdapter(),
        problems,
    )

    assert "tamper_restart_mutated_source:batch_payload" in problems


def test_v2_matrix_rejects_noop_restart_of_corrupt_image(
    monkeypatch: Any,
) -> None:
    class NoopRestartAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "noop-restart-instrumentation-v2"

        def restart_store_v2(self, store):  # type: ignore[no-untyped-def]
            return store

    monkeypatch.setattr(
        authority_store_v2_contract,
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ("batch_payload",),
    )
    result = run_governance_state_store_conformance_v2(NoopRestartAdapter())

    assert result.ok is False
    assert "restart_store_identity" in result.detail
    assert "restart_open_store_identity" in result.detail
    assert "authenticated_restart_store_identity" in result.detail
    assert "tamper_restart_accepted_corrupt_image:batch_payload" in result.detail


def test_v2_matrix_detects_missing_historical_full_read_set_replay(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        authority_store_v2_contract,
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ("cross_stream_order",),
    )
    monkeypatch.setattr(
        spec_adapter,
        "_validate_replayed_preconditions",
        lambda _batch, _domain, _heads: None,
    )

    result = run_governance_state_store_conformance_v2(
        IndependentStdlibGovernanceStateStoreV2Adapter()
    )

    assert result.ok is False
    assert "tamper_view:cross_stream_order" in result.detail
    assert "tamper_retry:cross_stream_order" in result.detail
    assert "tamper_fresh_write:cross_stream_order" in result.detail
    assert "tamper_restart_accepted_corrupt_image:cross_stream_order" in result.detail


def test_image_bytes_parser_rejects_duplicate_float_nfd_and_noncanonical() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:image-bytes"
    store = authority_store_v2_contract._new_store(adapter, scope_ref)
    canonical = adapter.observe_store_v2(store, scope_ref)["image_bytes"]
    assert type(canonical) is bytes
    malformed = (
        canonical.replace(b'{"heads":', b'{"heads":[],"heads":', 1),
        canonical.replace(b'"heads":[]', b'"heads":[1.0]', 1),
        canonical.replace(
            b'"states":[]',
            '"states":["e\u0301"]'.encode(),
            1,
        ),
        b" " + canonical,
    )

    for encoded in malformed:
        with pytest.raises((TypeError, ValueError)):
            authority_store_v2_contract._validated_image_bytes(encoded)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            partial(
                _set_image_value,
                field="version",
                value="independent-stdlib-authority-store-image-v999",
            ),
            "image version",
        ),
        (partial(_set_image_value, field="domains", value=[]), "image mappings"),
        (partial(_set_image_value, field="heads", value={}), "image arrays"),
        (
            partial(
                _replace_only_mapping_key,
                section="domains",
                replacement_key=7,
            ),
            "scope is invalid",
        ),
        (
            partial(
                _replace_only_mapping_key,
                section="domains",
                replacement_key="scope:crossed",
            ),
            "domain is invalid",
        ),
        (
            partial(_duplicate_first_image_entry, section="heads"),
            "head is duplicated",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="states",
                field="unexpected",
                value=True,
            ),
            "state image is invalid",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="states",
                field="stream_ref",
                value=7,
            ),
            "state binding is invalid",
        ),
        (
            partial(_duplicate_first_image_entry, section="states"),
            "state is duplicated",
        ),
        (
            partial(_duplicate_first_image_entry, section="committed"),
            "committed entry is duplicated",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="history",
                field="unexpected",
                value=True,
            ),
            "history image is invalid",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="history",
                field="revision",
                value=True,
            ),
            "history binding is invalid",
        ),
        (
            partial(_duplicate_first_image_entry, section="history"),
            "history entry is duplicated",
        ),
        (
            partial(
                _remove_first_image_entry_field,
                section="trace_batches",
                field="trace_batch",
            ),
            "Trace image is invalid",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="trace_batches",
                field="transition_id",
                value=7,
            ),
            "Trace binding is invalid",
        ),
        (
            partial(_duplicate_first_image_entry, section="trace_batches"),
            "Trace entry is duplicated",
        ),
        (
            partial(_duplicate_first_image_entry, section="seals"),
            "seal image is duplicated",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="transition_index",
                field="unexpected",
                value=True,
            ),
            "identity index is invalid",
        ),
        (
            partial(
                _set_first_image_entry_field,
                section="transition_index",
                field="sequence",
                value=True,
            ),
            "identity index binding is invalid",
        ),
        (
            partial(_duplicate_first_image_entry, section="transition_index"),
            "identity index is duplicated",
        ),
        (
            partial(
                _replace_only_mapping_key,
                section="commit_order",
                replacement_key=7,
            ),
            "commit order is invalid",
        ),
        (_duplicate_first_commit_order, "commit order is duplicated"),
        (_reorder_first_two_commits, "commit order was reordered"),
    ),
)
def test_independent_restart_rejects_malformed_persisted_image_sections(
    mutate: ImageMutator,
    message: str,
) -> None:
    image = deepcopy(_sealed_independent_image())
    mutate(image)

    with pytest.raises((TypeError, ValueError), match=message):
        IndependentStdlibGovernanceStateStoreV2._from_image(image)


def test_independent_adapter_rejects_invalid_configuration_and_foreign_stores() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    domain = adapter.create_domain_v2("scope:conformance:adapter-boundary")

    with pytest.raises(ValueError, match="failure stage"):
        IndependentStdlibGovernanceStateStoreV2(
            (domain,),
            failure_stage="after_unbounded_publication",
        )
    with pytest.raises(ValueError, match="scope is duplicated"):
        IndependentStdlibGovernanceStateStoreV2((domain, domain))

    store = IndependentStdlibGovernanceStateStoreV2((domain,))
    with pytest.raises(TypeError, match="GovernanceCommitBatchV2"):
        store.atomic_commit_v2(cast(Any, object()))
    with pytest.raises(ValueError, match="tamper case"):
        store._tamper(domain.scope_ref, "transition:absent", "invented_tamper")

    foreign = cast(Any, object())
    with pytest.raises(TypeError, match="foreign StateStore"):
        adapter.restart_store_v2(foreign)
    with pytest.raises(TypeError, match="foreign StateStore"):
        adapter.observe_store_v2(foreign, domain.scope_ref)
    with pytest.raises(TypeError, match="foreign StateStore"):
        adapter.tamper_store_v2(
            foreign,
            domain.scope_ref,
            "transition:absent",
            "batch_payload",
        )


def test_independent_commit_rejects_tampered_batch_and_domain_binding() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:tampered-commit-boundary"
    stream_ref = "authority:tampered-commit-boundary"
    store = cast(
        IndependentStdlibGovernanceStateStoreV2,
        authority_store_v2_contract._new_store(adapter, scope_ref),
    )

    malformed = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:tampered-payload",
        1,
    )
    object.__setattr__(malformed, "batch_root", "sha256:" + "0" * 64)
    rejected = store.atomic_commit_v2(malformed)
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert rejected.failure.stage is GovernanceFailureStageV2.VALIDATION

    crossed = authority_store_v2_contract._transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:crossed-domain-binding",
        2,
    )
    registered = store._domains[scope_ref]
    object.__setattr__(registered, "scope_ref", "scope:conformance:crossed")
    rejected = store.atomic_commit_v2(crossed)
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_public_matrix_rejects_malformed_observation_contracts() -> None:
    class MalformedObservationAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        implementation_id = "malformed-observation-contract-v2"

        def observe_store_v2(self, store, scope_ref):  # type: ignore[no-untyped-def]
            observed = dict(super().observe_store_v2(store, scope_ref))
            if scope_ref == "scope:conformance:fresh":
                return {}
            if scope_ref == "scope:conformance:unknown":
                observed["heads"] = True
            elif scope_ref == "scope:conformance:multi-read":
                observed["commit_order"] = list(
                    cast(tuple[str, ...], observed["commit_order"])
                )
            elif scope_ref == "scope:conformance:concurrent-same":
                observed["image_fingerprint"] = "sha256:" + "g" * 64
            elif scope_ref == "scope:conformance:concurrent-conflict":
                observed["image_bytes"] = b"{}"
            return observed

    result = run_governance_state_store_conformance_v2(MalformedObservationAdapter())

    assert result.ok is False
    for expected in (
        "observation_shape:fresh",
        "observation_count:unknown_scope_before:heads",
        "observation_order:multi_read_before",
        "observation_fingerprint:concurrent_same",
        "observation_image_bytes:concurrent_conflict",
    ):
        assert expected in result.detail


def test_public_matrix_detects_partial_publication_observation_lies(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        authority_store_v2_contract,
        "_DIAGNOSTIC_VALUES_V2",
        ("synthetic-registry-drift",),
    )
    monkeypatch.setattr(
        authority_store_v2_contract,
        "_FAILURE_STAGE_VALUES_V2",
        ("synthetic-stage-drift",),
    )
    result = run_governance_state_store_conformance_v2(
        _PartialPublicationObservationAdapter()
    )

    assert result.ok is False
    for expected in (
        "diagnostic_registry",
        "failure_stage_registry",
        "fresh_store_not_empty",
        "unknown_scope_partial_publish",
        "unknown_scope_implicitly_registered",
        "multi_read_partial_publish",
        "concurrent_same_double_publish",
        "concurrent_conflict_double_publish",
        "failure_partial_publish:before_validation",
        "seal_omission_partial_publish",
        "stream_bound_partial_publish",
        "seal_race_partial_publish",
        "restart_source_commit_order",
        "restart_observation",
    ):
        assert expected in result.detail


def test_public_matrix_reports_invalid_adapter_metadata_without_raising() -> None:
    class ExplodingMetadataAdapter(IndependentStdlibGovernanceStateStoreV2Adapter):
        @property
        def implementation_id(self) -> str:  # type: ignore[override]
            raise RuntimeError("metadata unavailable")

    exploded = run_governance_state_store_conformance_v2(
        cast(Any, ExplodingMetadataAdapter())
    )
    assert exploded.ok is False
    assert exploded.detail.startswith("adapter_exception:RuntimeError:")

    for implementation_id in (None, "", " padded "):

        class InvalidImplementationAdapter(
            IndependentStdlibGovernanceStateStoreV2Adapter
        ):
            pass

        InvalidImplementationAdapter.implementation_id = cast(Any, implementation_id)
        invalid = run_governance_state_store_conformance_v2(
            InvalidImplementationAdapter()
        )
        assert invalid.ok is False
        assert invalid.detail == "adapter_implementation_id"


def test_public_matrix_detects_wrong_fresh_store_version_and_genesis_state() -> None:
    result = run_governance_state_store_conformance_v2(_InvalidFreshStoreAdapter())

    assert result.ok is False
    assert "store_version" in result.detail
    assert "fresh_genesis" in result.detail


def test_reference_adapter_rejects_unknown_stage_tamper_and_foreign_store() -> None:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    domain = adapter.create_domain_v2("scope:conformance:reference-boundary")
    store = adapter.create_store_v2((domain,))
    unavailable = adapter.create_failure_injected_store_v2(
        GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
        (domain,),
    )
    assert adapter.observe_store_v2(store, domain.scope_ref)["heads"] == 0
    assert adapter.observe_store_v2(unavailable, domain.scope_ref)["heads"] == 0

    with pytest.raises(ValueError, match="failure stage"):
        adapter.create_failure_injected_store_v2("unknown-stage", (domain,))
    with pytest.raises(ValueError, match="tamper case"):
        adapter.tamper_store_v2(
            store,
            domain.scope_ref,
            "transition:absent",
            "unknown-tamper",
        )
    with pytest.raises(TypeError, match="foreign StateStore"):
        adapter.restart_store_v2(cast(Any, object()))


def test_image_bytes_parser_rejects_wrong_type_shape_and_integer_bounds() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    scope_ref = "scope:conformance:image-byte-bounds"
    store = authority_store_v2_contract._new_store(adapter, scope_ref)
    canonical = adapter.observe_store_v2(store, scope_ref)["image_bytes"]
    assert type(canonical) is bytes

    with pytest.raises(TypeError, match="canonical bytes"):
        authority_store_v2_contract._validated_image_bytes(bytearray(canonical))
    with pytest.raises(ValueError, match="category registry"):
        authority_store_v2_contract._validated_image_bytes(b"[]")
    out_of_range = canonical.replace(
        b'"heads":[]',
        b'"heads":[9007199254740992]',
        1,
    )
    with pytest.raises(ValueError, match="JSON-safe bounds"):
        authority_store_v2_contract._validated_image_bytes(out_of_range)
