from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType
from typing import Any, cast

from pheroos.governance.authority_domain import (
    AUTHORITY_LEDGER_VERSION,
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    _fingerprint,
    _freeze_json,
    _portable_json,
    _require_digest,
    _require_identity,
)
from pheroos.governance.errors import GovernanceError

_CHECKPOINT_SCHEMA = "pheroos-governance-checkpoint-v1"
_SNAPSHOT_SCHEMA = "pheroos-governance-store-snapshot-v1"
_CLAIM_SCHEMA = "pheroos-governance-identity-claim-v1"
_TRACE_RECORD_SCHEMA = "pheroos-governance-trace-record-v1"
_TOMBSTONE_SCHEMA = "pheroos-governance-domain-tombstone-v1"


@dataclass(frozen=True)
class _IdentityClaim:
    body: Mapping[str, Any]
    body_root: str


@dataclass(frozen=True)
class _DomainState:
    heads: dict[str, GovernanceHead]
    states: dict[str, Mapping[str, Any]]
    claims: dict[str, _IdentityClaim]
    trace_claims: dict[str, str]
    traces: dict[str, tuple[Mapping[str, Any], ...]]
    batches: dict[str, GovernanceCommitBatch]
    receipts: dict[str, GovernanceCommitReceipt]


@dataclass(frozen=True)
class _Tombstone:
    scope_ref: str
    final_root: str
    tombstone_root: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_ref": self.scope_ref,
            "final_root": self.final_root,
            "tombstone_root": self.tombstone_root,
        }


FailureInjector = Callable[[str, GovernanceCommitBatch], None]


class InMemoryGovernanceStateStore:
    """Copy-on-write reference implementation of the Governance ledger ABI.

    The implementation is deliberately process-local and provider-free.  It
    demonstrates CAS, idempotency, atomic state+trace publication, restart,
    retirement, and scope isolation without implying a database runtime.
    """

    __slots__ = (
        "__domains",
        "__failure_injector",
        "__lock",
        "__tombstones",
    )

    def __init__(self, *, failure_injector: FailureInjector | None = None) -> None:
        self.__domains: dict[str, _DomainState] = {}
        self.__tombstones: dict[str, _Tombstone] = {}
        self.__failure_injector = failure_injector
        self.__lock = RLock()

    def load_head(self, scope_ref: str, stream: str) -> GovernanceHead:
        domain = AuthorityDomain(scope_ref)
        _require_identity(stream, "governance stream")
        with self.__lock:
            self._require_active(domain.scope_ref)
            state = self.__domains.get(domain.scope_ref)
            if state is None:
                return GovernanceHead.genesis(domain.scope_ref, stream)
            head = state.heads.get(
                stream,
                GovernanceHead.genesis(domain.scope_ref, stream),
            )
            return _copy_head(head)

    def load_state(self, scope_ref: str, stream: str) -> Mapping[str, Any]:
        domain = AuthorityDomain(scope_ref)
        _require_identity(stream, "governance stream")
        with self.__lock:
            self._require_active(domain.scope_ref)
            state = self.__domains.get(domain.scope_ref)
            if state is None or stream not in state.states:
                return MappingProxyType({})
            return _detached_mapping(
                state.states[stream],
                path="governance_state_snapshot",
            )

    def trace_records(
        self,
        scope_ref: str,
        stream: str,
    ) -> tuple[Mapping[str, Any], ...]:
        domain = AuthorityDomain(scope_ref)
        _require_identity(stream, "governance stream")
        with self.__lock:
            self._require_active(domain.scope_ref)
            state = self.__domains.get(domain.scope_ref)
            if state is None:
                return ()
            return tuple(
                _detached_mapping(
                    record,
                    path=f"governance_trace_snapshot[{index}]",
                )
                for index, record in enumerate(state.traces.get(stream, ()))
            )

    def load_receipt(
        self,
        scope_ref: str,
        transition_id: str,
    ) -> GovernanceCommitReceipt | None:
        domain = AuthorityDomain(scope_ref)
        _require_identity(transition_id, "governance transition id")
        with self.__lock:
            self._require_active(domain.scope_ref)
            state = self.__domains.get(domain.scope_ref)
            if state is None:
                return None
            receipt = state.receipts.get(transition_id)
            return None if receipt is None else _copy_receipt(receipt)

    def claim_identity(
        self,
        scope_ref: str,
        identity_id: str,
        body: Mapping[str, Any],
    ) -> str:
        domain = AuthorityDomain(scope_ref)
        _require_identity(identity_id, "governance identity claim id")
        if not isinstance(body, Mapping):
            raise GovernanceError("governance identity claim body must be a mapping")
        frozen = _freeze_json(body, path=f"identity_claims.{identity_id}")
        body_root = _fingerprint(
            _CLAIM_SCHEMA,
            {
                "scope_ref": domain.scope_ref,
                "identity_id": identity_id,
                "body": _portable_json(frozen),
            },
        )
        with self.__lock:
            self._require_active(domain.scope_ref)
            current = self.__domains.get(domain.scope_ref, _empty_domain_state())
            existing = current.claims.get(identity_id)
            if existing is not None:
                if existing.body_root != body_root:
                    raise GovernanceError(
                        "governance_identity_conflict: identity replay changed its body"
                    )
                return existing.body_root
            claims = dict(current.claims)
            claims[identity_id] = _IdentityClaim(body=frozen, body_root=body_root)
            self.__domains[domain.scope_ref] = _replace_domain(
                current,
                claims=claims,
            )
            return body_root

    def compare_and_advance(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt:
        return self.atomic_commit(batch)

    def commit(self, batch: GovernanceCommitBatch) -> GovernanceCommitReceipt:
        return self.atomic_commit(batch)

    def atomic_commit(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt:
        if not isinstance(batch, GovernanceCommitBatch):
            raise GovernanceError("governance commit batch is invalid")
        # Never retain caller-owned dataclass instances: frozen dataclasses can
        # still be mutated with object.__setattr__, so canonical round-tripping
        # is part of the authority boundary.
        batch = GovernanceCommitBatch.from_dict(batch.to_dict())
        transition = batch.transition
        scope_ref = transition.domain.scope_ref
        with self.__lock:
            self._require_active(scope_ref)
            current_domain = self.__domains.get(scope_ref, _empty_domain_state())
            existing_batch = current_domain.batches.get(transition.transition_id)
            existing_receipt = current_domain.receipts.get(transition.transition_id)
            if existing_batch is not None or existing_receipt is not None:
                if (
                    existing_batch is not None
                    and existing_receipt is not None
                    and existing_batch.batch_root == batch.batch_root
                ):
                    return _copy_receipt(existing_receipt)
                raise GovernanceError(
                    "governance_transition_conflict: transition id replay changed its batch"
                )

            current_head = current_domain.heads.get(
                transition.stream,
                GovernanceHead.genesis(scope_ref, transition.stream),
            )
            if (
                current_head.revision != transition.expected_revision
                or current_head.parent_root != transition.expected_parent_root
                or current_head.state_root != transition.expected_state_root
            ):
                raise GovernanceError(
                    "governance_cas_conflict:retry_required: expected revision, parent, or root is stale"
                )

            claim_updates: dict[str, _IdentityClaim] = {}
            for identity_id, body in transition.identity_claims.items():
                body_root = _fingerprint(
                    _CLAIM_SCHEMA,
                    {
                        "scope_ref": scope_ref,
                        "identity_id": identity_id,
                        "body": _portable_json(body),
                    },
                )
                existing = current_domain.claims.get(identity_id)
                if existing is not None and existing.body_root != body_root:
                    raise GovernanceError(
                        "governance_identity_conflict: identity replay changed its body"
                    )
                if existing is None:
                    claim_updates[identity_id] = _IdentityClaim(
                        body=body,
                        body_root=body_root,
                    )

            trace_updates: dict[str, str] = {}
            for record in batch.trace_records:
                trace_id = record["trace_id"]
                if trace_id in current_domain.trace_claims:
                    raise GovernanceError(
                        "governance_trace_conflict: a new transition reused an existing trace id"
                    )
                trace_updates[trace_id] = _fingerprint(
                    _TRACE_RECORD_SCHEMA,
                    {"record": _portable_json(record)},
                )

            self._inject("before_commit", batch)
            new_head = GovernanceHead(
                scope_ref=scope_ref,
                stream=transition.stream,
                revision=current_head.revision + 1,
                parent_root=current_head.state_root,
                state_root=transition.state_root,
                transition_id=transition.transition_id,
            )
            heads = dict(current_domain.heads)
            heads[transition.stream] = new_head
            states = dict(current_domain.states)
            states[transition.stream] = transition.state_records
            claims = dict(current_domain.claims)
            claims.update(claim_updates)
            self._inject("after_state_prepare", batch)

            traces = dict(current_domain.traces)
            traces[transition.stream] = (
                *traces.get(transition.stream, ()),
                *batch.trace_records,
            )
            trace_claims = dict(current_domain.trace_claims)
            trace_claims.update(trace_updates)
            self._inject("after_trace_prepare", batch)

            receipt = GovernanceCommitReceipt(
                scope_ref=scope_ref,
                stream=transition.stream,
                transition_id=transition.transition_id,
                revision=new_head.revision,
                parent_root=new_head.parent_root,
                state_root=new_head.state_root,
                trace_root=batch.trace_root,
                batch_root=batch.batch_root,
            )
            batches = dict(current_domain.batches)
            batches[transition.transition_id] = batch
            receipts = dict(current_domain.receipts)
            receipts[transition.transition_id] = receipt
            candidate = _DomainState(
                heads=heads,
                states=states,
                claims=claims,
                trace_claims=trace_claims,
                traces=traces,
                batches=batches,
                receipts=receipts,
            )
            self._inject("before_publish", batch)
            self.__domains[scope_ref] = candidate
            return _copy_receipt(receipt)

    def checkpoint(self, scope_ref: str) -> Mapping[str, Any]:
        domain = AuthorityDomain(scope_ref)
        with self.__lock:
            self._require_active(domain.scope_ref)
            state = self.__domains.get(domain.scope_ref, _empty_domain_state())
            return _checkpoint_payload(domain.scope_ref, state)

    @classmethod
    def from_checkpoint(
        cls,
        payload: Mapping[str, Any],
        *,
        failure_injector: FailureInjector | None = None,
    ) -> InMemoryGovernanceStateStore:
        store = cls(failure_injector=failure_injector)
        store.rehydrate(payload)
        return store

    def rehydrate(self, payload: Mapping[str, Any]) -> tuple[GovernanceHead, ...]:
        domain = _checkpoint_domain(payload)
        batches = _checkpoint_batches(payload["batches"], domain=domain)
        temporary = InMemoryGovernanceStateStore()
        for batch in batches:
            temporary.atomic_commit(batch)
        _rehydrate_checkpoint_claims(
            temporary,
            payload["identity_claims"],
            scope_ref=domain.scope_ref,
        )
        declared_heads = _checkpoint_heads(payload["heads"])
        temporary_state = temporary.__domains.get(
            domain.scope_ref,
            _empty_domain_state(),
        )
        actual_heads = tuple(
            temporary_state.heads[stream] for stream in sorted(temporary_state.heads)
        )
        if declared_heads != actual_heads:
            raise GovernanceError(
                "governance checkpoint heads do not match replayed state"
            )
        regenerated = temporary.checkpoint(domain.scope_ref)
        if _portable_json(regenerated) != _portable_json(payload):
            raise GovernanceError("governance checkpoint is not replay-canonical")

        with self.__lock:
            if domain.scope_ref in self.__domains:
                raise GovernanceError("governance checkpoint scope is already active")
            self._require_active(domain.scope_ref)
            self.__domains[domain.scope_ref] = temporary_state
        return tuple(_copy_head(head) for head in actual_heads)

    @classmethod
    def from_snapshot(
        cls,
        payload: Mapping[str, Any],
        *,
        failure_injector: FailureInjector | None = None,
    ) -> InMemoryGovernanceStateStore:
        store = cls(failure_injector=failure_injector)
        store.rehydrate_snapshot(payload)
        return store

    def rehydrate_snapshot(self, payload: Mapping[str, Any]) -> None:
        domains, tombstones = _snapshot_collections(payload)
        temporary = InMemoryGovernanceStateStore()
        _rehydrate_snapshot_domains(temporary, domains)
        temporary.__tombstones.update(
            _snapshot_tombstones(
                tombstones,
                active_scopes=frozenset(temporary.__domains),
            )
        )
        if _portable_json(temporary.snapshot()) != _portable_json(payload):
            raise GovernanceError("governance store snapshot is not replay-canonical")
        with self.__lock:
            if self.__domains or self.__tombstones:
                raise GovernanceError("governance store is not empty")
            self.__domains = dict(temporary.__domains)
            self.__tombstones = dict(temporary.__tombstones)

    def retire(self, scope_ref: str) -> str:
        domain = AuthorityDomain(scope_ref)
        with self.__lock:
            existing = self.__tombstones.get(domain.scope_ref)
            if existing is not None:
                return existing.tombstone_root
            state = self.__domains.pop(domain.scope_ref, _empty_domain_state())
            checkpoint = _checkpoint_payload(domain.scope_ref, state)
            final_root = checkpoint["checkpoint_root"]
            tombstone_root = _fingerprint(
                _TOMBSTONE_SCHEMA,
                {"scope_ref": domain.scope_ref, "final_root": final_root},
            )
            self.__tombstones[domain.scope_ref] = _Tombstone(
                scope_ref=domain.scope_ref,
                final_root=final_root,
                tombstone_root=tombstone_root,
            )
            return tombstone_root

    def is_retired(self, scope_ref: str) -> bool:
        domain = AuthorityDomain(scope_ref)
        with self.__lock:
            return domain.scope_ref in self.__tombstones

    def snapshot(self) -> Mapping[str, Any]:
        with self.__lock:
            body = {
                "version": AUTHORITY_LEDGER_VERSION,
                "domains": [
                    _checkpoint_payload(scope_ref, self.__domains[scope_ref])
                    for scope_ref in sorted(self.__domains)
                ],
                "tombstones": [
                    self.__tombstones[scope_ref].to_dict()
                    for scope_ref in sorted(self.__tombstones)
                ],
            }
            return {
                **body,
                "snapshot_root": _fingerprint(_SNAPSHOT_SCHEMA, body),
            }

    def fingerprint(self) -> str:
        return cast(str, self.snapshot()["snapshot_root"])

    @property
    def active_domain_count(self) -> int:
        with self.__lock:
            return len(self.__domains)

    @property
    def tombstone_count(self) -> int:
        with self.__lock:
            return len(self.__tombstones)

    @property
    def retained_authority_record_count(self) -> int:
        with self.__lock:
            return sum(
                len(state.heads)
                + len(state.states)
                + len(state.claims)
                + len(state.trace_claims)
                + sum(len(records) for records in state.traces.values())
                + len(state.batches)
                + len(state.receipts)
                for state in self.__domains.values()
            )

    def _require_active(self, scope_ref: str) -> None:
        if scope_ref in self.__tombstones:
            raise GovernanceError(
                "governance_domain_retired: digest tombstone rejects authority replay"
            )

    def _inject(self, stage: str, batch: GovernanceCommitBatch) -> None:
        if self.__failure_injector is not None:
            self.__failure_injector(stage, batch)


def _checkpoint_domain(payload: Mapping[str, Any]) -> AuthorityDomain:
    if not isinstance(payload, Mapping):
        raise GovernanceError("governance checkpoint must be a mapping")
    expected_fields = {
        "version",
        "scope_ref",
        "batches",
        "identity_claims",
        "heads",
        "checkpoint_root",
    }
    if set(payload) != expected_fields:
        raise GovernanceError("governance checkpoint fields are invalid")
    if payload["version"] != AUTHORITY_LEDGER_VERSION:
        raise GovernanceError("governance checkpoint version is unsupported")
    domain = AuthorityDomain(payload["scope_ref"])
    body = {
        key: _portable_json(payload[key])
        for key in expected_fields - {"checkpoint_root"}
    }
    if payload["checkpoint_root"] != _fingerprint(_CHECKPOINT_SCHEMA, body):
        raise GovernanceError("governance checkpoint root does not match its payload")
    return domain


def _checkpoint_batches(
    payload: object,
    *,
    domain: AuthorityDomain,
) -> list[GovernanceCommitBatch]:
    if not isinstance(payload, list):
        raise GovernanceError("governance checkpoint batches must be an array")
    batches: list[GovernanceCommitBatch] = []
    for item in payload:
        if not isinstance(item, Mapping):
            raise GovernanceError("governance checkpoint batch must be an object")
        batch = GovernanceCommitBatch.from_dict(item)
        if batch.transition.domain.scope_ref != domain.scope_ref:
            raise GovernanceError("governance checkpoint batch crosses authority scope")
        batches.append(batch)
    batches.sort(
        key=lambda item: (
            item.transition.stream,
            item.transition.expected_revision,
            item.transition.transition_id,
        )
    )
    return batches


def _rehydrate_checkpoint_claims(
    temporary: InMemoryGovernanceStateStore,
    payload: object,
    *,
    scope_ref: str,
) -> None:
    if not isinstance(payload, Mapping):
        raise GovernanceError("governance checkpoint claims must be an object")
    for identity_id, claim_body in sorted(payload.items()):
        if not isinstance(claim_body, Mapping):
            raise GovernanceError("governance checkpoint claim body must be an object")
        temporary.claim_identity(scope_ref, identity_id, claim_body)


def _checkpoint_heads(payload: object) -> tuple[GovernanceHead, ...]:
    if not isinstance(payload, list):
        raise GovernanceError("governance checkpoint heads must be an array")
    return tuple(
        GovernanceHead.from_dict(item)
        if isinstance(item, Mapping)
        else _raise_invalid_checkpoint_head()
        for item in payload
    )


def _snapshot_collections(
    payload: Mapping[str, Any],
) -> tuple[list[object], list[object]]:
    if not isinstance(payload, Mapping):
        raise GovernanceError("governance store snapshot must be a mapping")
    expected_fields = {"version", "domains", "tombstones", "snapshot_root"}
    if set(payload) != expected_fields:
        raise GovernanceError("governance store snapshot fields are invalid")
    if payload["version"] != AUTHORITY_LEDGER_VERSION:
        raise GovernanceError("governance store snapshot version is unsupported")
    body = {
        key: _portable_json(payload[key]) for key in expected_fields - {"snapshot_root"}
    }
    if payload["snapshot_root"] != _fingerprint(_SNAPSHOT_SCHEMA, body):
        raise GovernanceError(
            "governance store snapshot root does not match its payload"
        )
    domains = payload["domains"]
    tombstones = payload["tombstones"]
    if not isinstance(domains, list) or not isinstance(tombstones, list):
        raise GovernanceError("governance store snapshot collections must be arrays")
    return domains, tombstones


def _rehydrate_snapshot_domains(
    temporary: InMemoryGovernanceStateStore,
    domains: list[object],
) -> None:
    for checkpoint in domains:
        if not isinstance(checkpoint, Mapping):
            raise GovernanceError(
                "governance store domain checkpoint must be an object"
            )
        temporary.rehydrate(checkpoint)


def _snapshot_tombstones(
    tombstones: list[object],
    *,
    active_scopes: frozenset[str],
) -> dict[str, _Tombstone]:
    restored: dict[str, _Tombstone] = {}
    for item in tombstones:
        if not isinstance(item, Mapping) or set(item) != {
            "scope_ref",
            "final_root",
            "tombstone_root",
        }:
            raise GovernanceError("governance domain tombstone fields are invalid")
        scope_ref = AuthorityDomain(item["scope_ref"]).scope_ref
        final_root = _require_digest(
            item["final_root"],
            "governance tombstone final root",
        )
        expected_tombstone = _fingerprint(
            _TOMBSTONE_SCHEMA,
            {"scope_ref": scope_ref, "final_root": final_root},
        )
        if item["tombstone_root"] != expected_tombstone:
            raise GovernanceError("governance domain tombstone root is invalid")
        if scope_ref in active_scopes or scope_ref in restored:
            raise GovernanceError("governance store snapshot scope is duplicated")
        restored[scope_ref] = _Tombstone(
            scope_ref=scope_ref,
            final_root=final_root,
            tombstone_root=expected_tombstone,
        )
    return restored


def _empty_domain_state() -> _DomainState:
    return _DomainState(
        heads={},
        states={},
        claims={},
        trace_claims={},
        traces={},
        batches={},
        receipts={},
    )


def _replace_domain(
    state: _DomainState,
    *,
    claims: dict[str, _IdentityClaim],
) -> _DomainState:
    return _DomainState(
        heads=state.heads,
        states=state.states,
        claims=claims,
        trace_claims=state.trace_claims,
        traces=state.traces,
        batches=state.batches,
        receipts=state.receipts,
    )


def _copy_head(head: GovernanceHead) -> GovernanceHead:
    return GovernanceHead.from_dict(head.to_dict())


def _copy_receipt(receipt: GovernanceCommitReceipt) -> GovernanceCommitReceipt:
    return GovernanceCommitReceipt.from_dict(receipt.to_dict())


def _detached_mapping(value: Mapping[str, Any], *, path: str) -> Mapping[str, Any]:
    detached = _freeze_json(_portable_json(value), path=path)
    return cast(Mapping[str, Any], detached)


def _checkpoint_payload(scope_ref: str, state: _DomainState) -> dict[str, Any]:
    batches = sorted(
        state.batches.values(),
        key=lambda item: (
            item.transition.stream,
            item.transition.expected_revision,
            item.transition.transition_id,
        ),
    )
    body = {
        "version": AUTHORITY_LEDGER_VERSION,
        "scope_ref": scope_ref,
        "batches": [batch.to_dict() for batch in batches],
        "identity_claims": {
            identity_id: _portable_json(state.claims[identity_id].body)
            for identity_id in sorted(state.claims)
        },
        "heads": [state.heads[stream].to_dict() for stream in sorted(state.heads)],
    }
    return {
        **body,
        "checkpoint_root": _fingerprint(_CHECKPOINT_SCHEMA, body),
    }


def _raise_invalid_checkpoint_head() -> GovernanceHead:
    raise GovernanceError("governance checkpoint head must be an object")


__all__ = ["InMemoryGovernanceStateStore"]
