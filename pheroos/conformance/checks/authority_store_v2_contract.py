"""Reusable, provider-free Governance StateStore v2 conformance matrix.

The adapter hooks in this module are deliberately test-only surfaces.  They
exercise restart and failure boundaries without extending the public
``GovernanceStateStoreV2`` ABI with persistence-format or inspection methods.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from threading import Barrier
from typing import Any, NoReturn, Protocol, TypedDict, cast, runtime_checkable
import unicodedata

from pheroos.conformance.report import CheckResult
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-state-store-conformance-v2"
)
GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2 = (
    "before_validation",
    "after_identity_reconciliation",
    "after_read_set_validation",
    "after_state_head_staging",
    "after_trace_staging",
    "after_receipt_inclusion_staging",
    "after_atomic_publication",
)
GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2 = "load_commit_view"
GOVERNANCE_STATE_STORE_TAMPER_CASES_V2 = (
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

_CHECK_NAME = "authority_store_v2_contract"
_CONCURRENCY_WORKERS = 32
_OBSERVATION_FIELDS = frozenset(
    {
        "heads",
        "states",
        "trace_batches",
        "receipts",
        "inclusions",
        "transition_ids",
        "seals",
        "commit_order",
        "image_fingerprint",
        "image_bytes",
    }
)
_IMAGE_PAYLOAD_FIELDS = frozenset(
    {
        "heads",
        "states",
        "trace_batches",
        "receipts",
        "inclusions",
        "transition_ids",
        "seals",
    }
)
_DIAGNOSTIC_VALUES_V2 = (
    "authority_profile_unsupported",
    "authority_session_required",
    "authority_session_store_mismatch",
    "authority_scope_mismatch",
    "authority_operation_denied",
    "authority_binding_mismatch",
    "authority_grant_unverified",
    "authority_grant_expired",
    "authority_grant_revoked",
    "governance_read_set_invalid",
    "governance_read_set_stale",
    "governance_transition_conflict",
    "governance_domain_sealed",
    "governance_finality_unavailable",
    "governance_committed_transition_invalid",
    "governance_action_not_authorized",
    "governance_trace_lineage_invalid",
)
_FAILURE_STAGE_VALUES_V2 = (
    "validation",
    "reconciliation",
    "precondition",
    "trace",
    "commit",
    "finality",
    "load",
    "seal",
)
_INJECTED_FAILURE_RESULT_STAGES_V2 = {
    "before_validation": GovernanceFailureStageV2.VALIDATION,
    "after_identity_reconciliation": GovernanceFailureStageV2.RECONCILIATION,
    "after_read_set_validation": GovernanceFailureStageV2.PRECONDITION,
    "after_state_head_staging": GovernanceFailureStageV2.COMMIT,
    "after_trace_staging": GovernanceFailureStageV2.TRACE,
    "after_receipt_inclusion_staging": GovernanceFailureStageV2.COMMIT,
    "after_atomic_publication": GovernanceFailureStageV2.FINALITY,
}


class _StoreObservation(TypedDict):
    heads: int
    states: int
    trace_batches: int
    receipts: int
    inclusions: int
    transition_ids: int
    seals: int
    commit_order: tuple[str, ...]
    image_fingerprint: str
    image_bytes: bytes


@runtime_checkable
class GovernanceStateStoreConformanceAdapterV2(Protocol):
    """Test-only adapter for one StateStore v2 implementation.

    ``observe_store_v2`` reports category counts, actual per-scope commit
    order, and one detached canonical image.  These hooks are trusted test
    instrumentation, not an authority read API or a cryptographic attestation
    from a potentially malicious adapter.
    """

    implementation_id: str
    conformance_version: str

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2: ...

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2: ...

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2: ...

    def create_failure_injected_store_v2(
        self,
        stage: str,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2: ...

    def observe_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
    ) -> Mapping[str, object]: ...

    def tamper_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None: ...


class _ReferenceUnavailableViewStoreV2:
    """Test-only reader outage wrapper around the unmodified reference store."""

    def __init__(
        self,
        store: InMemoryGovernanceStateStoreV2,
        domains: Sequence[AuthorityDomainV2],
    ) -> None:
        self._store = store
        self._domains = {item.scope_ref: item for item in domains}

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        return self._store.atomic_commit_v2(batch)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        domain = self._domains[scope_ref]
        failure = GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            path="",
            stage=GovernanceFailureStageV2.LOAD,
        )
        return GovernanceCommitViewV2(
            domain_root=domain.domain_root,
            scope_ref=scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            expected_receipt_root=expected_receipt_root,
            disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            failure=failure,
            committed_transition=None,
            position_observation=None,
            observed_revision=None,
            observed_head_root=None,
        )


class ReferenceGovernanceStateStoreConformanceAdapterV2:
    """Run the same v2 matrix against the serialized reference owner."""

    __slots__ = ()

    implementation_id = "pheroos-in-memory-governance-state-store-v2"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2

    def create_domain_v2(self, scope_ref: str) -> AuthorityDomainV2:
        return AuthorityDomainV2(
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

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        return InMemoryGovernanceStateStoreV2(domains)

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = _reference_store(store)
        return InMemoryGovernanceStateStoreV2.from_snapshot_v2(selected.snapshot_v2())

    def create_failure_injected_store_v2(
        self,
        stage: str,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        if stage == GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2:
            selected = InMemoryGovernanceStateStoreV2(domains)
            return _ReferenceUnavailableViewStoreV2(selected, domains)
        if stage not in GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2:
            raise ValueError("unsupported reference failure stage")

        def inject(observed: str, _batch: GovernanceCommitBatchV2) -> None:
            if observed == stage:
                raise RuntimeError(f"injected:{stage}")

        return InMemoryGovernanceStateStoreV2(
            domains,
            failure_injector=inject,
        )

    def observe_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
    ) -> Mapping[str, object]:
        selected = _reference_store(store)
        payload = json.loads(selected.snapshot_v2())
        domains = payload["domains"]
        domain = next(
            (item for item in domains if item["domain"]["scope_ref"] == scope_ref),
            None,
        )
        if domain is None:
            return _empty_observation()
        commits = domain["commits"]
        image_bytes = _canonical_image_bytes(_reference_image_payload(domain))
        return {
            "heads": len(domain["heads"]),
            "states": len(domain["states"]),
            "trace_batches": len(commits),
            "receipts": len(commits),
            "inclusions": len(commits),
            "transition_ids": len(domain["transition_index"]),
            "seals": int(domain["seal_root"] is not None),
            "commit_order": tuple(
                item["transition_id"]
                for item in sorted(
                    domain["transition_index"],
                    key=lambda item: item["sequence"],
                )
            ),
            "image_fingerprint": _image_fingerprint(image_bytes),
            "image_bytes": image_bytes,
        }

    def tamper_store_v2(
        self,
        store: GovernanceStateStoreV2,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None:
        if case not in GOVERNANCE_STATE_STORE_TAMPER_CASES_V2:
            raise ValueError("unsupported StateStore v2 tamper case")
        selected = _reference_store(store)
        with selected._lock:
            image = selected._domains[scope_ref]
            sequence = image.transition_index[transition_id]
            entry = image.entries[sequence - 1]
            _tamper_reference_entry(image, entry, case)


def _reference_store(
    store: GovernanceStateStoreV2,
) -> InMemoryGovernanceStateStoreV2:
    if type(store) is InMemoryGovernanceStateStoreV2:
        return store
    if type(store) is _ReferenceUnavailableViewStoreV2:
        return store._store
    raise TypeError("reference adapter received a foreign StateStore")


def _reference_image_payload(
    domain: Mapping[str, object],
) -> Mapping[str, object]:
    commits = cast(list[dict[str, object]], domain["commits"])
    image = {
        "heads": domain["heads"],
        "states": domain["states"],
        "trace_batches": [
            cast(dict[str, object], item["batch"])["trace_batch"] for item in commits
        ],
        "receipts": [
            {"batch": item["batch"], "receipt": item["receipt"]} for item in commits
        ],
        "inclusions": {
            "proofs": [item["inclusion_proof"] for item in commits],
            "history": [
                {
                    "scope_ref": cast(dict[str, object], item["batch"])["scope_ref"],
                    "stream_ref": cast(dict[str, object], item["batch"])["stream_ref"],
                    "revision": cast(dict[str, object], item["receipt"])["revision"],
                    "committed_transition": {
                        "batch": item["batch"],
                        "receipt": item["receipt"],
                        "inclusion_proof": item["inclusion_proof"],
                    },
                }
                for item in commits
            ],
        },
        "transition_ids": {
            "index": domain["transition_index"],
            "sequences": [
                {
                    "sequence": item["sequence"],
                    "transition_id": cast(dict[str, object], item["batch"])[
                        "transition_id"
                    ],
                }
                for item in commits
            ],
        },
        "seals": {
            "seal_root": domain["seal_root"],
            "records": [
                cast(dict[str, object], item["batch"])["seal"]
                for item in commits
                if cast(dict[str, object], item["batch"])["kind"] == "seal"
            ],
        },
    }
    return image


def _canonical_image_bytes(image: Mapping[str, object]) -> bytes:
    return json.dumps(
        image,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _image_fingerprint(encoded: bytes) -> str:
    prefix = b"pheroos-conformance-authority-image-v2\x00"
    return "sha256:" + sha256(prefix + encoded).hexdigest()


def _validated_image_bytes(value: object) -> bytes:
    if type(value) is not bytes:
        raise TypeError("conformance image must be canonical bytes")
    encoded = value
    text = encoded.decode("utf-8", errors="strict")
    parsed = json.loads(
        text,
        object_pairs_hook=_unique_json_object,
        parse_float=_reject_json_number,
        parse_constant=_reject_json_number,
    )
    if type(parsed) is not dict or set(parsed) != _IMAGE_PAYLOAD_FIELDS:
        raise ValueError("conformance image category registry is invalid")
    _validate_image_json(parsed)
    canonical = _canonical_image_bytes(parsed)
    if canonical != encoded:
        raise ValueError("conformance image is not canonical JSON")
    return canonical


def _unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("conformance image contains a duplicate key")
        result[key] = item
    return result


def _reject_json_number(value: str) -> NoReturn:
    raise ValueError(f"conformance image forbids non-integer number {value!r}")


def _validate_image_json(value: object) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if not -(2**53 - 1) <= value <= 2**53 - 1:
            raise ValueError("conformance image integer is outside JSON-safe bounds")
        return
    if type(value) is str:
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError("conformance image text is not NFC")
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _validate_image_json(item)
        return
    if type(value) is dict:
        _validate_image_mapping(cast(dict[object, object], value))
        return
    raise TypeError("conformance image contains a non-JSON value")


def _validate_image_mapping(value: Mapping[object, object]) -> None:
    for key, item in value.items():
        if type(key) is not str:
            raise TypeError("conformance image key must be text")
        _validate_image_json(key)
        _validate_image_json(item)


def _tamper_reference_entry(image: Any, entry: Any, case: str) -> None:
    zero_root = "sha256:" + "0" * 64
    handlers = (
        _tamper_reference_commit,
        _tamper_reference_projection,
        _tamper_reference_trace_binding,
        _tamper_reference_seal,
        _tamper_reference_closure,
    )
    for handler in handlers:
        if handler(image, entry, case, zero_root):
            return
    raise AssertionError("unhandled StateStore v2 tamper case")


def _tamper_reference_commit(
    _image: Any,
    entry: Any,
    case: str,
    zero_root: str,
) -> bool:
    batch, receipt, inclusion = entry.batch, entry.receipt, entry.inclusion_proof
    if case == "batch_payload":
        object.__setattr__(batch, "transition_id", batch.transition_id + ":tampered")
    elif case == "batch_root":
        object.__setattr__(batch, "batch_root", zero_root)
    elif case == "receipt_payload":
        object.__setattr__(receipt, "state_root", zero_root)
    elif case == "receipt_root":
        object.__setattr__(receipt, "receipt_root", zero_root)
    elif case == "inclusion_payload":
        object.__setattr__(inclusion, "batch_root", zero_root)
    elif case == "inclusion_root":
        object.__setattr__(inclusion, "inclusion_root", zero_root)
    elif case == "history_payload":
        object.__setattr__(receipt, "parent_root", zero_root)
    else:
        return False
    return True


def _tamper_reference_projection(
    image: Any,
    entry: Any,
    case: str,
    zero_root: str,
) -> bool:
    stream_ref = entry.batch.stream_ref
    if case == "head_payload":
        object.__setattr__(image.heads[stream_ref], "batch_root", zero_root)
    elif case == "head_root":
        object.__setattr__(image.heads[stream_ref], "head_root", zero_root)
    elif case == "state_payload":
        cast(dict[str, Any], image.states[stream_ref])["tampered"] = True
    elif case == "state_root":
        object.__setattr__(image.heads[stream_ref], "state_root", zero_root)
    else:
        return False
    return True


def _tamper_reference_trace_binding(
    _image: Any,
    entry: Any,
    case: str,
    zero_root: str,
) -> bool:
    batch, receipt = entry.batch, entry.receipt
    if case == "trace_payload":
        _tamper_trace_payload(batch.trace_batch)
    elif case == "trace_root":
        object.__setattr__(batch.trace_batch, "trace_root", zero_root)
    elif case == "scope_binding":
        object.__setattr__(receipt, "scope_ref", receipt.scope_ref + ":crossed")
    elif case == "stream_binding":
        object.__setattr__(receipt, "stream_ref", receipt.stream_ref + ":crossed")
    elif case == "revision_binding":
        object.__setattr__(receipt, "revision", True)
    else:
        return False
    return True


def _tamper_reference_seal(
    image: Any,
    entry: Any,
    case: str,
    zero_root: str,
) -> bool:
    batch = entry.batch
    if case == "seal_payload":
        if batch.seal is None:
            raise ValueError("seal tamper requires a seal transition")
        object.__setattr__(
            batch.seal,
            "transition_id",
            batch.seal.transition_id + ":tampered",
        )
    elif case == "seal_root":
        if batch.seal is None:
            raise ValueError("seal tamper requires a seal transition")
        object.__setattr__(batch.seal, "seal_root", zero_root)
    elif case == "lifecycle_state":
        lifecycle = cast(
            dict[str, Any],
            image.states[GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2],
        )
        lifecycle["tampered"] = True
    elif case == "seal_marker":
        object.__setattr__(image, "seal_root", None)
    else:
        return False
    return True


def _tamper_reference_closure(
    image: Any,
    entry: Any,
    case: str,
    _zero_root: str,
) -> bool:
    stream_ref = entry.batch.stream_ref
    if case == "transition_index":
        cast(dict[str, int], image.transition_index).pop(entry.batch.transition_id)
    elif case == "projection_removal":
        cast(dict[str, Any], image.heads).pop(stream_ref)
        cast(dict[str, Any], image.states).pop(stream_ref)
    elif case == "sequence_binding":
        object.__setattr__(entry, "sequence", True)
    elif case == "cross_stream_order":
        if type(entry.sequence) is not int or entry.sequence < 2:
            raise ValueError("cross-stream order tamper requires a predecessor")
        entries = list(image.entries)
        original_index = entry.sequence - 1
        predecessor = entries[original_index - 1]
        entries[original_index - 1], entries[original_index] = (
            entry,
            predecessor,
        )
        object.__setattr__(entry, "sequence", original_index)
        object.__setattr__(predecessor, "sequence", original_index + 1)
        object.__setattr__(image, "entries", tuple(entries))
        index = cast(dict[str, int], image.transition_index)
        index[entry.batch.transition_id] = entry.sequence
        index[predecessor.batch.transition_id] = predecessor.sequence
    else:
        return False
    return True


def _tamper_trace_payload(trace_batch: GovernanceTraceBatchV2) -> None:
    snapshots = tuple(cast(list[dict[str, Any]], trace_batch.to_dict()["events"]))
    first = snapshots[0]
    first["reason"] = cast(str, first["reason"]) + ":tampered"
    object.__setattr__(trace_batch, "_event_snapshots", snapshots)


def run_governance_state_store_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the complete deterministic StateStore v2 behavior matrix."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        implementation_id = adapter.implementation_id
        conformance_version = adapter.conformance_version
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
    if conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
        return CheckResult(_CHECK_NAME, False, "adapter_version")

    problems: list[str] = []
    try:
        _evaluate_closed_registries(problems)
        _evaluate_fresh_store(adapter, problems)
        _evaluate_unknown_scope(adapter, problems)
        _evaluate_identity_and_history(adapter, problems)
        _evaluate_multi_read_atomicity(adapter, problems)
        _evaluate_concurrency(adapter, problems)
        _evaluate_failure_boundaries(adapter, problems)
        _evaluate_total_views(adapter, problems)
        _evaluate_seal(adapter, problems)
        _evaluate_seal_race(adapter, problems)
        _evaluate_stream_bound(adapter, problems)
        _evaluate_restart(adapter, problems)
        _evaluate_authenticated_restart(adapter, problems)
        _evaluate_persisted_artifact_mutations(adapter, problems)
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def check(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run this check for an explicitly selected v2 implementation adapter."""

    return run_governance_state_store_conformance_v2(adapter)


def _evaluate_closed_registries(problems: list[str]) -> None:
    if tuple(item.value for item in AuthorityDiagnosticCodeV2) != (
        _DIAGNOSTIC_VALUES_V2
    ):
        problems.append("diagnostic_registry")
    if tuple(item.value for item in GovernanceFailureStageV2) != (
        _FAILURE_STAGE_VALUES_V2
    ):
        problems.append("failure_stage_registry")


def _evaluate_fresh_store(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:fresh"
    domain = adapter.create_domain_v2(scope_ref)
    if type(domain) is not AuthorityDomainV2 or domain.scope_ref != scope_ref:
        problems.append("domain_factory")
        return
    store = adapter.create_store_v2((domain,))
    if not isinstance(store, GovernanceStateStoreV2):
        problems.append("store_protocol")
        return
    if store.state_store_version != GOVERNANCE_STATE_STORE_VERSION_V2:
        problems.append("store_version")
    head = store.load_head_v2(scope_ref, "authority:fresh")
    if (
        head != GovernanceHeadV2.genesis(domain, "authority:fresh")
        or store.load_state_v2(scope_ref, "authority:fresh") != {}
    ):
        problems.append("fresh_genesis")
    observed = _observation(adapter, store, scope_ref, problems, "fresh")
    if observed is not None and observed != _empty_observation():
        problems.append("fresh_store_not_empty")


def _evaluate_unknown_scope(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    known_scope = "scope:conformance:known"
    unknown_scope = "scope:conformance:unknown"
    store = _new_store(adapter, known_scope)
    unknown_domain = adapter.create_domain_v2(unknown_scope)
    preparation_store = adapter.create_store_v2((unknown_domain,))
    batch = _transition_batch(
        adapter,
        preparation_store,
        unknown_scope,
        "authority:unknown",
        "transition:unknown-scope",
        1,
        domain=unknown_domain,
    )
    before = _observation(
        adapter,
        store,
        unknown_scope,
        problems,
        "unknown_scope_before",
    )
    result = store.atomic_commit_v2(batch)
    _expect_failure(
        result,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
        "/scope_ref",
        problems,
        "unknown_scope_commit",
    )
    after = _observation(
        adapter,
        store,
        unknown_scope,
        problems,
        "unknown_scope_after",
    )
    if before is not None and after != before:
        problems.append("unknown_scope_partial_publish")
    if after is not None and after != _empty_observation():
        problems.append("unknown_scope_implicitly_registered")

    _expect_parameter_read_rejected(
        lambda: store.load_head_v2(unknown_scope, "authority:unknown"),
        problems,
        "unknown_scope_head_read",
    )
    _expect_parameter_read_rejected(
        lambda: store.load_state_v2(unknown_scope, "authority:unknown"),
        problems,
        "unknown_scope_state_read",
    )
    _expect_parameter_read_rejected(
        lambda: store.load_commit_view_v2(
            unknown_scope,
            "authority:unknown",
            batch.transition_id,
        ),
        problems,
        "unknown_scope_view_read",
    )


def _evaluate_identity_and_history(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:identity"
    store = _new_store(adapter, scope_ref)
    stream_ref = "authority:decision"
    first = _transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:first",
        1,
    )
    committed = store.atomic_commit_v2(first)
    _expect_committed(committed, problems, "first_commit")
    retry = store.atomic_commit_v2(first)
    _expect_committed(retry, problems, "exact_retry")
    if _receipt_root(retry) != _receipt_root(committed):
        problems.append("exact_retry_receipt")

    conflict = _transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        first.transition_id,
        999,
    )
    conflict_result = store.atomic_commit_v2(conflict)
    _expect_failure(
        conflict_result,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        "/transition_id",
        problems,
        "scope_wide_transition_conflict",
    )
    cross_stream_conflict = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:alternate",
        first.transition_id,
        1000,
    )
    _expect_failure(
        store.atomic_commit_v2(cross_stream_conflict),
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        "/transition_id",
        problems,
        "scope_wide_cross_stream_transition_conflict",
    )
    if store.load_head_v2(scope_ref, "authority:alternate").revision != 0:
        problems.append("cross_stream_transition_conflict_published")

    successor = _transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:successor",
        2,
    )
    _expect_committed(
        store.atomic_commit_v2(successor),
        problems,
        "successor_commit",
    )
    receipt_root = _receipt_root(committed)
    view = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        first.transition_id,
        expected_receipt_root=receipt_root,
    )
    _expect_committed_view(
        view,
        GovernanceCommitPositionV2.SUPERSEDED,
        problems,
        "historical_superseded",
    )
    retry_after_successor = store.atomic_commit_v2(first)
    _expect_committed(retry_after_successor, problems, "historical_retry")
    if (
        _receipt_root(retry_after_successor) != receipt_root
        or retry_after_successor.position_observation is None
        or retry_after_successor.position_observation.position
        is not GovernanceCommitPositionV2.SUPERSEDED
    ):
        problems.append("historical_retry_position")


def _evaluate_multi_read_atomicity(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:multi-read"
    store = _new_store(adapter, scope_ref)
    streams = ("authority:alpha", "authority:beta")
    frozen_heads = {stream: store.load_head_v2(scope_ref, stream) for stream in streams}
    stale = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:alpha",
        "transition:stale-multi-read",
        10,
        read_streams=streams,
        heads=frozen_heads,
    )
    beta = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:beta",
        "transition:advance-beta",
        20,
    )
    _expect_committed(store.atomic_commit_v2(beta), problems, "multi_read_setup")
    before = _observation(adapter, store, scope_ref, problems, "multi_read_before")
    result = store.atomic_commit_v2(stale)
    _expect_failure(
        result,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/read_set",
        problems,
        "multi_read_stale",
    )
    after = _observation(adapter, store, scope_ref, problems, "multi_read_after")
    if before is not None and after != before:
        problems.append("multi_read_partial_publish")
    if store.load_head_v2(scope_ref, "authority:alpha").revision != 0:
        problems.append("multi_read_target_advanced")


def _evaluate_concurrency(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    same_scope = "scope:conformance:concurrent-same"
    same_store = _new_store(adapter, same_scope)
    same_batch = _transition_batch(
        adapter,
        same_store,
        same_scope,
        "authority:decision",
        "transition:shared",
        1,
    )
    with ThreadPoolExecutor(max_workers=_CONCURRENCY_WORKERS) as executor:
        same_results = tuple(
            executor.map(
                lambda _index: same_store.atomic_commit_v2(same_batch),
                range(_CONCURRENCY_WORKERS),
            )
        )
    if any(
        result.disposition is not GovernanceCommitDispositionV2.COMMITTED
        for result in same_results
    ):
        problems.append("concurrent_same_disposition")
    if len({_receipt_root(result) for result in same_results}) != 1:
        problems.append("concurrent_same_receipt")
    same_observation = _observation(
        adapter,
        same_store,
        same_scope,
        problems,
        "concurrent_same",
    )
    if same_observation is not None and (
        same_observation["transition_ids"] != 1
        or same_observation["receipts"] != 1
        or same_observation["commit_order"] != ("transition:shared",)
    ):
        problems.append("concurrent_same_double_publish")

    conflict_scope = "scope:conformance:concurrent-conflict"
    conflict_store = _new_store(adapter, conflict_scope)
    conflict_batches = tuple(
        _transition_batch(
            adapter,
            conflict_store,
            conflict_scope,
            "authority:decision",
            f"transition:worker:{index}",
            index,
        )
        for index in range(_CONCURRENCY_WORKERS)
    )
    with ThreadPoolExecutor(max_workers=_CONCURRENCY_WORKERS) as executor:
        conflict_results = tuple(
            executor.map(conflict_store.atomic_commit_v2, conflict_batches)
        )
    dispositions = tuple(result.disposition for result in conflict_results)
    if (
        dispositions.count(GovernanceCommitDispositionV2.COMMITTED) != 1
        or dispositions.count(GovernanceCommitDispositionV2.RETRY_REQUIRED)
        != _CONCURRENCY_WORKERS - 1
    ):
        problems.append("concurrent_conflict_disposition")
    conflict_observation = _observation(
        adapter,
        conflict_store,
        conflict_scope,
        problems,
        "concurrent_conflict",
    )
    if conflict_observation is not None and (
        conflict_observation["transition_ids"] != 1
        or conflict_observation["receipts"] != 1
        or len(conflict_observation["commit_order"]) != 1
    ):
        problems.append("concurrent_conflict_double_publish")


def _evaluate_failure_boundaries(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    for stage in GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2[:-1]:
        scope_ref = f"scope:conformance:failure:{stage}"
        store = _new_failure_store(adapter, scope_ref, stage)
        batch = _transition_batch(
            adapter,
            store,
            scope_ref,
            "authority:failure",
            f"transition:{stage}",
            1,
        )
        before = _observation(adapter, store, scope_ref, problems, f"{stage}:before")
        result = store.atomic_commit_v2(batch)
        _expect_failure(
            result,
            GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "",
            problems,
            f"failure_result:{stage}",
            stage=_INJECTED_FAILURE_RESULT_STAGES_V2[stage],
        )
        after = _observation(adapter, store, scope_ref, problems, f"{stage}:after")
        if before is not None and after != before:
            problems.append(f"failure_partial_publish:{stage}")
        if store.load_head_v2(scope_ref, "authority:failure").revision != 0:
            problems.append(f"failure_head_visible:{stage}")

    stage = GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2[-1]
    scope_ref = "scope:conformance:failure:post-publication"
    store = _new_failure_store(adapter, scope_ref, stage)
    batch = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:failure",
        "transition:published-response-lost",
        1,
    )
    result = store.atomic_commit_v2(batch)
    _expect_failure(
        result,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        "",
        problems,
        "post_publication_result",
        stage=GovernanceFailureStageV2.FINALITY,
    )
    view = store.load_commit_view_v2(
        scope_ref,
        batch.stream_ref,
        batch.transition_id,
    )
    _expect_committed_view(
        view,
        GovernanceCommitPositionV2.CURRENT,
        problems,
        "post_publication_reconciliation",
    )


def _evaluate_total_views(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:views"
    store = _new_store(adapter, scope_ref)
    stream_ref = "authority:view"
    batch = _transition_batch(
        adapter,
        store,
        scope_ref,
        stream_ref,
        "transition:view",
        1,
    )
    committed = store.atomic_commit_v2(batch)
    _expect_committed(committed, problems, "view_setup")
    valid = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        batch.transition_id,
    )
    _expect_committed_view(
        valid,
        GovernanceCommitPositionV2.CURRENT,
        problems,
        "view_committed",
    )
    invalid = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        "transition:absent",
    )
    _expect_view_failure(
        invalid,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        problems,
        "view_invalid",
    )
    mismatched = store.load_commit_view_v2(
        scope_ref,
        stream_ref,
        batch.transition_id,
        expected_receipt_root="sha256:" + "0" * 64,
    )
    _expect_view_failure(
        mismatched,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        problems,
        "view_receipt_mismatch",
    )

    unavailable_scope = "scope:conformance:view-unavailable"
    unavailable_store = _new_failure_store(
        adapter,
        unavailable_scope,
        GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
    )
    unavailable_batch = _transition_batch(
        adapter,
        unavailable_store,
        unavailable_scope,
        stream_ref,
        "transition:view-unavailable",
        1,
    )
    _expect_committed(
        unavailable_store.atomic_commit_v2(unavailable_batch),
        problems,
        "view_unavailable_setup",
    )
    unavailable = unavailable_store.load_commit_view_v2(
        unavailable_scope,
        stream_ref,
        unavailable_batch.transition_id,
    )
    _expect_view_failure(
        unavailable,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        problems,
        "view_unavailable",
    )


def _evaluate_seal(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:seal"
    store = _new_store(adapter, scope_ref)
    streams = ("authority:alpha", "authority:beta")
    first_attempts = tuple(
        store.atomic_commit_v2(
            _transition_batch(
                adapter,
                store,
                scope_ref,
                stream_ref,
                f"transition:{stream_ref}",
                index,
            )
        )
        for index, stream_ref in enumerate(streams, start=1)
    )
    for index, attempt in enumerate(first_attempts):
        _expect_committed(attempt, problems, f"seal_setup:{index}")

    before_omission = _observation(
        adapter,
        store,
        scope_ref,
        problems,
        "seal_omission_before",
    )
    omitted = _seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:seal-omitted",
        streams=(streams[0],),
    )
    _expect_failure(
        store.atomic_commit_v2(omitted),
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/read_set",
        problems,
        "seal_omission",
    )
    after_omission = _observation(
        adapter,
        store,
        scope_ref,
        problems,
        "seal_omission_after",
    )
    if before_omission is not None and after_omission != before_omission:
        problems.append("seal_omission_partial_publish")

    added = _seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:seal-added",
        streams=(*streams, "authority:phantom"),
    )
    _expect_failure(
        store.atomic_commit_v2(added),
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/read_set",
        problems,
        "seal_addition",
    )

    seal_batch = _seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:seal",
        streams=streams,
    )
    seal_attempt = store.atomic_commit_v2(seal_batch)
    _expect_committed(seal_attempt, problems, "seal_commit")
    if seal_batch.seal is None:
        problems.append("seal_batch_union")
        return
    old = store.load_commit_view_v2(
        scope_ref,
        streams[0],
        first_attempts[0].transition_id,
        expected_receipt_root=_receipt_root(first_attempts[0]),
    )
    _expect_committed_view(
        old,
        GovernanceCommitPositionV2.SEALED,
        problems,
        "sealed_history",
    )
    if (
        old.position_observation is None
        or old.position_observation.seal_root != seal_batch.seal.seal_root
    ):
        problems.append("sealed_history_root")
    first_committed = first_attempts[0].committed_transition
    if first_committed is None:
        problems.append("sealed_exact_retry_fixture")
        return
    retried = store.atomic_commit_v2(first_committed.batch)
    _expect_committed(retried, problems, "sealed_exact_retry")
    if _receipt_root(retried) != _receipt_root(first_attempts[0]):
        problems.append("sealed_exact_retry_receipt")

    denied_batch = _transition_batch(
        adapter,
        store,
        scope_ref,
        streams[0],
        "transition:after-seal",
        999,
    )
    _expect_failure(
        store.atomic_commit_v2(denied_batch),
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
        "/domain_root",
        problems,
        "post_seal_denial",
    )


def _evaluate_stream_bound(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:stream-bound"
    store = _new_store(adapter, scope_ref)
    for index in range(127):
        result = store.atomic_commit_v2(
            _transition_batch(
                adapter,
                store,
                scope_ref,
                f"authority:bounded:{index:03d}",
                f"transition:bounded:{index:03d}",
                index,
            )
        )
        if result.disposition is not GovernanceCommitDispositionV2.COMMITTED:
            problems.append(f"stream_bound_setup:{index}")
            return
    before = _observation(adapter, store, scope_ref, problems, "stream_bound_before")
    overflow = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:bounded:127",
        "transition:bounded:127",
        127,
    )
    _expect_failure(
        store.atomic_commit_v2(overflow),
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
        "/read_set",
        problems,
        "stream_bound_rejection",
    )
    after = _observation(adapter, store, scope_ref, problems, "stream_bound_after")
    if before is not None and after != before:
        problems.append("stream_bound_partial_publish")


def _evaluate_seal_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:seal-race"
    store = _new_store(adapter, scope_ref)
    ordinary = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:race",
        "transition:race-ordinary",
        1,
    )
    seal = _seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:race-seal",
        streams=(),
    )
    barrier = Barrier(2)

    def commit_after_barrier(
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        barrier.wait()
        return store.atomic_commit_v2(batch)

    with ThreadPoolExecutor(max_workers=2) as executor:
        ordinary_future = executor.submit(commit_after_barrier, ordinary)
        seal_future = executor.submit(commit_after_barrier, seal)
        ordinary_result = ordinary_future.result()
        seal_result = seal_future.result()
    if ordinary_result.disposition is GovernanceCommitDispositionV2.COMMITTED:
        _expect_failure(
            seal_result,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/read_set",
            problems,
            "seal_race_seal_loser",
        )
    elif seal_result.disposition is GovernanceCommitDispositionV2.COMMITTED:
        _expect_failure(
            ordinary_result,
            GovernanceCommitDispositionV2.DENIED,
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
            "/domain_root",
            problems,
            "seal_race_ordinary_loser",
        )
    else:
        problems.append("seal_race_no_winner")
    observation = _observation(
        adapter,
        store,
        scope_ref,
        problems,
        "seal_race",
    )
    if observation is not None and observation["transition_ids"] != 1:
        problems.append("seal_race_partial_publish")
    _evaluate_deterministic_seal_orders(adapter, problems)


def _evaluate_deterministic_seal_orders(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    ordinary_scope = "scope:conformance:seal-order:ordinary-first"
    ordinary_store = _new_store(adapter, ordinary_scope)
    ordinary = _transition_batch(
        adapter,
        ordinary_store,
        ordinary_scope,
        "authority:race",
        "transition:ordinary-first",
        1,
    )
    stale_seal = _seal_batch(
        adapter,
        ordinary_store,
        ordinary_scope,
        "transition:seal-second",
        streams=(),
    )
    _expect_committed(
        ordinary_store.atomic_commit_v2(ordinary),
        problems,
        "seal_order_ordinary_winner",
    )
    _expect_failure(
        ordinary_store.atomic_commit_v2(stale_seal),
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/read_set",
        problems,
        "seal_order_stale_seal",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )

    seal_scope = "scope:conformance:seal-order:seal-first"
    seal_store = _new_store(adapter, seal_scope)
    denied_ordinary = _transition_batch(
        adapter,
        seal_store,
        seal_scope,
        "authority:race",
        "transition:ordinary-second",
        1,
    )
    winning_seal = _seal_batch(
        adapter,
        seal_store,
        seal_scope,
        "transition:seal-first",
        streams=(),
    )
    _expect_committed(
        seal_store.atomic_commit_v2(winning_seal),
        problems,
        "seal_order_seal_winner",
    )
    _expect_failure(
        seal_store.atomic_commit_v2(denied_ordinary),
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
        "/domain_root",
        problems,
        "seal_order_denied_ordinary",
        stage=GovernanceFailureStageV2.SEAL,
    )


def _evaluate_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:restart"
    store = _new_store(adapter, scope_ref)
    operations = (
        ("authority:zeta", "transition:order:1", 1),
        ("authority:alpha", "transition:order:2", 2),
        ("authority:zeta", "transition:order:3", 3),
    )
    committed: list[GovernanceCommitAttemptV2] = []
    for stream_ref, transition_id, value in operations:
        read_streams = (
            ("authority:alpha", "authority:zeta")
            if transition_id == "transition:order:3"
            else None
        )
        attempt = store.atomic_commit_v2(
            _transition_batch(
                adapter,
                store,
                scope_ref,
                stream_ref,
                transition_id,
                value,
                read_streams=read_streams,
            )
        )
        _expect_committed(attempt, problems, f"restart_setup:{transition_id}")
        committed.append(attempt)
    seal_batch = _seal_batch(
        adapter,
        store,
        scope_ref,
        "transition:order:4-seal",
        streams=("authority:alpha", "authority:zeta"),
    )
    seal_attempt = store.atomic_commit_v2(seal_batch)
    _expect_committed(seal_attempt, problems, "restart_seal")
    expected_order = tuple(item[1] for item in operations) + (
        "transition:order:4-seal",
    )
    before = _observation(adapter, store, scope_ref, problems, "restart_before")
    if before is not None and before["commit_order"] != expected_order:
        problems.append("restart_source_commit_order")
    head_before = {
        stream: store.load_head_v2(scope_ref, stream).to_dict()
        for stream in (
            "authority:alpha",
            "authority:zeta",
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
    }
    state_before = {
        stream: dict(store.load_state_v2(scope_ref, stream))
        for stream in (
            "authority:alpha",
            "authority:zeta",
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
    }
    restarted = adapter.restart_store_v2(store)
    if not isinstance(restarted, GovernanceStateStoreV2):
        problems.append("restart_store_protocol")
        return
    if restarted is store:
        problems.append("restart_store_identity")
    after = _observation(adapter, restarted, scope_ref, problems, "restart_after")
    if before is not None and after != before:
        problems.append("restart_observation")
    for stream in head_before:
        if restarted.load_head_v2(scope_ref, stream).to_dict() != head_before[stream]:
            problems.append(f"restart_head:{stream}")
        if dict(restarted.load_state_v2(scope_ref, stream)) != state_before[stream]:
            problems.append(f"restart_state:{stream}")
    for attempt in committed:
        assert attempt.committed_transition is not None
        view = restarted.load_commit_view_v2(
            scope_ref,
            attempt.stream_ref,
            attempt.transition_id,
            expected_receipt_root=attempt.committed_transition.receipt.receipt_root,
        )
        _expect_committed_view(
            view,
            GovernanceCommitPositionV2.SEALED,
            problems,
            f"restart_history:{attempt.transition_id}",
        )
    seal_view = restarted.load_commit_view_v2(
        scope_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        seal_batch.transition_id,
        expected_receipt_root=_receipt_root(seal_attempt),
    )
    _expect_committed_view(
        seal_view,
        GovernanceCommitPositionV2.SEALED,
        problems,
        "restart_seal_view",
    )
    seal_retry = restarted.atomic_commit_v2(seal_batch)
    _expect_committed(seal_retry, problems, "restart_seal_exact_retry")
    _expect_same_receipt(
        seal_retry,
        seal_attempt,
        problems,
        "restart_seal_retry_receipt",
    )
    first = committed[0]
    assert first.committed_transition is not None
    retried = restarted.atomic_commit_v2(first.committed_transition.batch)
    _expect_committed(retried, problems, "restart_exact_retry")
    _expect_same_receipt(retried, first, problems, "restart_retry_receipt")
    conflicting = _transition_batch(
        adapter,
        restarted,
        scope_ref,
        first.stream_ref,
        first.transition_id,
        999,
    )
    _expect_failure(
        restarted.atomic_commit_v2(conflicting),
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        "/transition_id",
        problems,
        "restart_identity_conflict",
    )
    post_restart = _transition_batch(
        adapter,
        restarted,
        scope_ref,
        "authority:alpha",
        "transition:restart-after-seal",
        1000,
    )
    _expect_failure(
        restarted.atomic_commit_v2(post_restart),
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
        "/domain_root",
        problems,
        "restart_post_seal_denial",
        stage=GovernanceFailureStageV2.SEAL,
    )
    _evaluate_open_restart(adapter, problems)


def _evaluate_open_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:restart-open"
    store = _new_store(adapter, scope_ref)
    first = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:open",
        "transition:open:1",
        1,
    )
    first_attempt = store.atomic_commit_v2(first)
    _expect_committed(first_attempt, problems, "restart_open_first")
    second = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:open",
        "transition:open:2",
        2,
    )
    second_attempt = store.atomic_commit_v2(second)
    _expect_committed(second_attempt, problems, "restart_open_second")
    restarted = adapter.restart_store_v2(store)
    if restarted is store:
        problems.append("restart_open_store_identity")
    _expect_committed_view(
        restarted.load_commit_view_v2(
            scope_ref,
            first.stream_ref,
            first.transition_id,
            expected_receipt_root=_receipt_root(first_attempt),
        ),
        GovernanceCommitPositionV2.SUPERSEDED,
        problems,
        "restart_open_superseded",
    )
    _expect_committed_view(
        restarted.load_commit_view_v2(
            scope_ref,
            second.stream_ref,
            second.transition_id,
            expected_receipt_root=_receipt_root(second_attempt),
        ),
        GovernanceCommitPositionV2.CURRENT,
        problems,
        "restart_open_current",
    )


def _evaluate_authenticated_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    scope_ref = "scope:conformance:restart-authenticated"
    domain = _domain_with_profile(
        adapter.create_domain_v2(scope_ref),
        AUTHORITY_AUTHENTICATED_PROFILE_V2,
    )
    store = adapter.create_store_v2((domain,))
    batch = _transition_batch(
        adapter,
        store,
        scope_ref,
        "authority:authenticated",
        "transition:authenticated",
        1,
        domain=domain,
    )
    committed = store.atomic_commit_v2(batch)
    _expect_committed(committed, problems, "authenticated_restart_setup")
    head_before = store.load_head_v2(scope_ref, batch.stream_ref)
    restarted = adapter.restart_store_v2(store)
    if restarted is store:
        problems.append("authenticated_restart_store_identity")
    head_after = restarted.load_head_v2(scope_ref, batch.stream_ref)
    if (
        batch.domain.profile != AUTHORITY_AUTHENTICATED_PROFILE_V2
        or head_after.to_dict() != head_before.to_dict()
        or head_after.domain_root != domain.domain_root
    ):
        problems.append("authenticated_restart_head")
    view = restarted.load_commit_view_v2(
        scope_ref,
        batch.stream_ref,
        batch.transition_id,
        expected_receipt_root=_receipt_root(committed),
    )
    _expect_committed_view(
        view,
        GovernanceCommitPositionV2.CURRENT,
        problems,
        "authenticated_restart_view",
    )
    retry = restarted.atomic_commit_v2(batch)
    _expect_committed(retry, problems, "authenticated_restart_retry")
    if _receipt_root(retry) != _receipt_root(committed):
        problems.append("authenticated_restart_retry_receipt")


def _evaluate_persisted_artifact_mutations(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    seal_cases = frozenset(
        {"seal_payload", "seal_root", "lifecycle_state", "seal_marker"}
    )
    trace_cases = frozenset({"trace_payload", "trace_root"})
    for case in GOVERNANCE_STATE_STORE_TAMPER_CASES_V2:
        scope_ref = f"scope:conformance:tamper:{case}"
        store = _new_store(adapter, scope_ref)
        if case == "cross_stream_order":
            predecessor = _transition_batch(
                adapter,
                store,
                scope_ref,
                "authority:tamper:alpha",
                f"transition:tamper:{case}:alpha",
                1,
            )
            _expect_committed(
                store.atomic_commit_v2(predecessor),
                problems,
                f"tamper_setup:{case}:alpha",
            )
            selected = _transition_batch(
                adapter,
                store,
                scope_ref,
                "authority:tamper:beta",
                f"transition:tamper:{case}:beta",
                2,
                read_streams=(
                    "authority:tamper:alpha",
                    "authority:tamper:beta",
                ),
            )
            _expect_committed(
                store.atomic_commit_v2(selected),
                problems,
                f"tamper_setup:{case}:beta",
            )
        else:
            ordinary = _transition_batch(
                adapter,
                store,
                scope_ref,
                "authority:tamper",
                f"transition:tamper:{case}:ordinary",
                1,
            )
            _expect_committed(
                store.atomic_commit_v2(ordinary),
                problems,
                f"tamper_setup:{case}:ordinary",
            )
            selected = ordinary
            if case in seal_cases:
                selected = _seal_batch(
                    adapter,
                    store,
                    scope_ref,
                    f"transition:tamper:{case}:seal",
                    streams=(ordinary.stream_ref,),
                )
                _expect_committed(
                    store.atomic_commit_v2(selected),
                    problems,
                    f"tamper_setup:{case}:seal",
                )
        fresh_identity = _transition_batch(
            adapter,
            store,
            scope_ref,
            "authority:tamper:fresh",
            f"transition:tamper:{case}:fresh",
            2,
        )

        before = _observation(
            adapter,
            store,
            scope_ref,
            problems,
            f"tamper:{case}:before",
        )
        adapter.tamper_store_v2(
            store,
            scope_ref,
            selected.transition_id,
            case,
        )
        tampered = _observation(
            adapter,
            store,
            scope_ref,
            problems,
            f"tamper:{case}:after",
        )
        if before is not None and tampered is not None:
            if before["image_fingerprint"] == tampered["image_fingerprint"]:
                problems.append(f"tamper_fingerprint_unchanged:{case}")

        expected_code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID
            if case in trace_cases
            else AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )
        view = store.load_commit_view_v2(
            scope_ref,
            selected.stream_ref,
            selected.transition_id,
        )
        _expect_view_failure(
            view,
            GovernanceCommitDispositionV2.INVALID,
            expected_code,
            problems,
            f"tamper_view:{case}",
        )
        retry = store.atomic_commit_v2(selected)
        _expect_failure(
            retry,
            GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "",
            problems,
            f"tamper_retry:{case}",
            stage=GovernanceFailureStageV2.RECONCILIATION,
        )
        after_retry = _observation(
            adapter,
            store,
            scope_ref,
            problems,
            f"tamper:{case}:retry",
        )
        if tampered is not None and after_retry != tampered:
            problems.append(f"tamper_retry_partial_publish:{case}")
        fresh_result = store.atomic_commit_v2(fresh_identity)
        _expect_failure(
            fresh_result,
            GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "",
            problems,
            f"tamper_fresh_write:{case}",
            stage=GovernanceFailureStageV2.RECONCILIATION,
        )
        after_fresh = _observation(
            adapter,
            store,
            scope_ref,
            problems,
            f"tamper:{case}:fresh",
        )
        if after_retry is not None and after_fresh != after_retry:
            problems.append(f"tamper_fresh_write_partial_publish:{case}")
        _expect_corrupt_restart(
            adapter,
            store,
            scope_ref,
            tampered,
            problems,
            case,
        )


def _expect_corrupt_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    tampered: _StoreObservation | None,
    problems: list[str],
    case: str,
) -> None:
    try:
        adapter.restart_store_v2(store)
    except (TypeError, ValueError):
        _expect_source_store_unchanged(
            adapter,
            store,
            scope_ref,
            tampered,
            problems,
            case,
        )
        return
    _expect_source_store_unchanged(
        adapter,
        store,
        scope_ref,
        tampered,
        problems,
        case,
    )
    # A restart helper is a reconstruction boundary, not a quarantine wrapper.
    # Returning any StateStore from a corrupt persistent image exposes a reader
    # or writer before complete image validation and therefore fails conformance.
    problems.append(f"tamper_restart_accepted_corrupt_image:{case}")


def _expect_source_store_unchanged(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    tampered: _StoreObservation | None,
    problems: list[str],
    case: str,
) -> None:
    source_after = _observation(
        adapter,
        store,
        scope_ref,
        problems,
        f"tamper:{case}:source-after-restart",
    )
    if tampered is not None and source_after != tampered:
        problems.append(f"tamper_restart_mutated_source:{case}")


def _domain_with_profile(
    source: AuthorityDomainV2,
    profile: str,
) -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=source.policy_version,
        profile=profile,
        wire_version=source.wire_version,
        canonical_version=source.canonical_version,
        ledger_version=source.ledger_version,
        state_store_version=source.state_store_version,
        trace_batch_version=source.trace_batch_version,
        read_set_version=source.read_set_version,
        scope_ref=source.scope_ref,
    )


def _expect_parameter_read_rejected(
    action: Callable[[], object],
    problems: list[str],
    label: str,
) -> None:
    try:
        action()
    except (KeyError, ValueError):
        return
    except Exception as exc:
        problems.append(f"{label}:{type(exc).__name__}")
        return
    problems.append(label)


def _new_store(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    scope_ref: str,
) -> GovernanceStateStoreV2:
    return adapter.create_store_v2((adapter.create_domain_v2(scope_ref),))


def _new_failure_store(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    scope_ref: str,
    stage: str,
) -> GovernanceStateStoreV2:
    return adapter.create_failure_injected_store_v2(
        stage,
        (adapter.create_domain_v2(scope_ref),),
    )


def _transition_batch(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    value: int,
    *,
    read_streams: Sequence[str] | None = None,
    heads: Mapping[str, GovernanceHeadV2] | None = None,
    domain: AuthorityDomainV2 | None = None,
) -> GovernanceCommitBatchV2:
    selected_domain = domain or adapter.create_domain_v2(scope_ref)
    selected_streams = tuple(read_streams or (stream_ref,))
    if stream_ref not in selected_streams:
        selected_streams = (*selected_streams, stream_ref)
    observed = {
        selected: (
            heads[selected]
            if heads is not None and selected in heads
            else store.load_head_v2(scope_ref, selected)
        )
        for selected in selected_streams
    }
    read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(
            GovernanceReadPreconditionV2(
                stream_ref=selected,
                expected_revision=observed[selected].revision,
                expected_root=observed[selected].head_root,
            )
            for selected in sorted(observed, key=lambda item: item.encode("utf-8"))
        )
    )
    target = observed[stream_ref]
    transition = PreparedGovernanceTransitionV2(
        domain_root=selected_domain.domain_root,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_revision=target.revision,
        expected_root=target.head_root,
        read_set_root=read_set.root(),
        state_records={"value": value},
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=selected_domain.domain_root,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        events=(_trace_event(scope_ref, stream_ref, transition_id),),
    )
    return GovernanceCommitBatchV2(
        domain=selected_domain,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        kind="transition",
        read_set=read_set,
        trace_batch=trace_batch,
        transition=transition,
    )


def _seal_batch(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    transition_id: str,
    *,
    streams: Sequence[str],
) -> GovernanceCommitBatchV2:
    domain = adapter.create_domain_v2(scope_ref)
    selected = (GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2, *streams)
    heads = {stream: store.load_head_v2(scope_ref, stream) for stream in selected}
    ordered = tuple(sorted(heads, key=lambda item: item.encode("utf-8")))
    read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(
            GovernanceReadPreconditionV2(
                stream_ref=stream,
                expected_revision=heads[stream].revision,
                expected_root=heads[stream].head_root,
            )
            for stream in ordered
        )
    )
    lifecycle = heads[GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2]
    final_heads = tuple(
        {
            "stream_ref": stream,
            "revision": heads[stream].revision,
            "head_root": heads[stream].head_root,
        }
        for stream in ordered
        if stream != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    )
    seal = GovernanceDomainSealV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        transition_id=transition_id,
        expected_revision=lifecycle.revision,
        expected_root=lifecycle.head_root,
        final_heads=final_heads,
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=scope_ref,
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        transition_id=transition_id,
        events=(
            _trace_event(
                scope_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
                transition_id,
                seal_root=seal.seal_root,
            ),
        ),
    )
    return GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=scope_ref,
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        transition_id=transition_id,
        kind="seal",
        read_set=read_set,
        trace_batch=trace_batch,
        seal=seal,
    )


def _trace_event(
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    *,
    seal_root: str | None = None,
) -> TraceEvent:
    lineage: dict[str, Any] = {
        "scope_ref": scope_ref,
        "stream_ref": stream_ref,
        "transition_id": transition_id,
    }
    if seal_root is not None:
        lineage["seal_root"] = seal_root
    return TraceEvent(
        event_type="ext.pheroos.authority_store_v2_conformance",
        protocol_id="protocol:authority-store-v2-conformance",
        target=stream_ref,
        reason="verify the provider-neutral StateStore v2 contract",
        lineage=lineage,
    )


def _expect_committed(
    attempt: GovernanceCommitAttemptV2,
    problems: list[str],
    label: str,
) -> None:
    if (
        type(attempt) is not GovernanceCommitAttemptV2
        or attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.failure is not None
        or attempt.committed_transition is None
        or attempt.position_observation is None
    ):
        problems.append(label)


def _expect_failure(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    problems: list[str],
    label: str,
    *,
    stage: GovernanceFailureStageV2 | None = None,
) -> None:
    if (
        type(attempt) is not GovernanceCommitAttemptV2
        or attempt.disposition is not disposition
        or attempt.failure is None
        or attempt.failure.code is not code
        or attempt.failure.path != path
        or (stage is not None and attempt.failure.stage is not stage)
        or attempt.committed_transition is not None
        or attempt.position_observation is not None
    ):
        problems.append(label)


def _expect_committed_view(
    view: GovernanceCommitViewV2,
    position: GovernanceCommitPositionV2,
    problems: list[str],
    label: str,
) -> None:
    if (
        type(view) is not GovernanceCommitViewV2
        or view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.failure is not None
        or view.committed_transition is None
        or view.position_observation is None
        or view.position_observation.position is not position
        or view.observed_revision != view.position_observation.observed_revision
        or view.observed_head_root != view.position_observation.observed_head_root
    ):
        problems.append(label)


def _expect_view_failure(
    view: GovernanceCommitViewV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
    problems: list[str],
    label: str,
) -> None:
    expected_path = (
        "/committed_transition/batch/trace_batch"
        if code is AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID
        else ""
        if disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
        else "/transition_id"
    )
    if (
        type(view) is not GovernanceCommitViewV2
        or view.disposition is not disposition
        or view.failure is None
        or view.failure.code is not code
        or view.failure.stage is not GovernanceFailureStageV2.LOAD
        or view.failure.path != expected_path
        or view.committed_transition is not None
        or view.position_observation is not None
    ):
        problems.append(label)
        return
    if disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE and (
        view.observed_revision is not None or view.observed_head_root is not None
    ):
        problems.append(f"{label}_observed_head")
    if (view.observed_revision is None) != (view.observed_head_root is None):
        problems.append(f"{label}_observed_head_pair")


def _receipt_root(attempt: GovernanceCommitAttemptV2) -> str:
    if attempt.committed_transition is None:
        return ""
    return attempt.committed_transition.receipt.receipt_root


def _expect_same_receipt(
    actual: GovernanceCommitAttemptV2,
    expected: GovernanceCommitAttemptV2,
    problems: list[str],
    label: str,
) -> None:
    if _receipt_root(actual) != _receipt_root(expected):
        problems.append(label)


def _observation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    store: GovernanceStateStoreV2,
    scope_ref: str,
    problems: list[str],
    label: str,
) -> _StoreObservation | None:
    raw = adapter.observe_store_v2(store, scope_ref)
    if not isinstance(raw, Mapping) or set(raw) != _OBSERVATION_FIELDS:
        problems.append(f"observation_shape:{label}")
        return None
    for field in _OBSERVATION_FIELDS - {
        "commit_order",
        "image_fingerprint",
        "image_bytes",
    }:
        count = raw[field]
        if type(count) is not int or count < 0:
            problems.append(f"observation_count:{label}:{field}")
            return None
    order = raw["commit_order"]
    if type(order) is not tuple or any(type(item) is not str for item in order):
        problems.append(f"observation_order:{label}")
        return None
    fingerprint = raw["image_fingerprint"]
    if (
        type(fingerprint) is not str
        or len(fingerprint) != 71
        or not fingerprint.startswith("sha256:")
        or any(item not in "0123456789abcdef" for item in fingerprint[7:])
    ):
        problems.append(f"observation_fingerprint:{label}")
        return None
    image_bytes = raw["image_bytes"]
    try:
        canonical = _validated_image_bytes(image_bytes)
    except (TypeError, ValueError, UnicodeError):
        problems.append(f"observation_image_bytes:{label}")
        return None
    if fingerprint != _image_fingerprint(canonical):
        problems.append(f"observation_fingerprint_mismatch:{label}")
        return None
    return cast(_StoreObservation, dict(raw))


def _empty_observation() -> _StoreObservation:
    image_bytes = _canonical_image_bytes(
        {
            "heads": [],
            "states": [],
            "trace_batches": [],
            "receipts": [],
            "inclusions": {"proofs": [], "history": []},
            "transition_ids": {"index": [], "sequences": []},
            "seals": {"seal_root": None, "records": []},
        }
    )
    return {
        "heads": 0,
        "states": 0,
        "trace_batches": 0,
        "receipts": 0,
        "inclusions": 0,
        "transition_ids": 0,
        "seals": 0,
        "commit_order": (),
        "image_fingerprint": _image_fingerprint(image_bytes),
        "image_bytes": image_bytes,
    }


GovernanceStateStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
ReferenceGovernanceStateStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
run_governance_state_store_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2",
    "GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2",
    "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
    "GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2",
    "GovernanceStateStoreConformanceAdapterV2",
    "ReferenceGovernanceStateStoreConformanceAdapterV2",
    "check",
    "run_governance_state_store_conformance_v2",
]
